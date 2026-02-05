"""Union sub-command CLI handling

The union sub-command merges a given OSTree reference (e.g. branch or commit
hash) with local changes (e.g. copied from an adjusted module using the isolate
sub-command).
"""

import logging
import os
import subprocess
import shutil

from tcbuilder.backend import union as ub
from tcbuilder.backend.common import \
    (images_unpack_executed, image_has_cfs_support, get_storage_dir)
from tcbuilder.backend.ostree import OSTreeKey
from tcbuilder.cli.common import parse_ostree_key
from tcbuilder.errors import InvalidArgumentError, PathNotExistError

log = logging.getLogger("torizon." + __name__)


def check_and_append_dirs(changes_dirs, new_changes_dirs, temp_dir):
    """Check and append additional directories with changes"""

    for changes_dir in new_changes_dirs:
        if not os.path.exists(changes_dir):
            raise PathNotExistError(f'Changes directory "{changes_dir}" does not exist')

        copy_src = os.path.join(changes_dir, ".")
        copy_dest = os.path.join(temp_dir, changes_dir)
        shutil.copytree(copy_src, copy_dest, symlinks=True)
        temp_change_dir = os.path.join(temp_dir, changes_dir)
        set_acl_attributes(temp_change_dir)
        changes_dirs.append(os.path.abspath(temp_change_dir))


def apply_tcattr_acl(files):
    """
    Apply ACLs based on .tcattr files. It just needs to be done once for
    each ".tcattr" file found in each sub directory of the tree.

    :param files: A list with the elements being a tuple of the base_dir
                  of all '.tcattr' files and all filenames that we should
                  apply the ACL attributes.
    """

    for tcattr_basedir in {tcattr[0] for tcattr in files}:
        tcattr_file = os.path.join(tcattr_basedir, '.tcattr')
        setfacl_cmd = ['setfacl', f'--restore={tcattr_file}']
        subprocess.run(setfacl_cmd, cwd=tcattr_basedir, check=True)


def set_file_mode(filename, mode):
    """
    Set file mode and ownership if filename is a regular file or a directory.
    If filename is a symbolic link, set just the ownership since it is not
    possible to set the mode (permissions) for a symbolic link in Linux.

    :param filename: Filename to set the mode to.
    :param mode: Mode to be set on the file.
    """

    root_uid = 0
    root_gid = 0

    os.chown(filename, root_uid, root_gid, follow_symlinks=False)

    if not os.path.islink(filename):
        os.chmod(filename, mode)


def apply_default_acl(files):
    """
    Apply default ACL to files and directories.
      - For executables files: 0770.
      - For non-executables files: 0660.
      - For directories: 0755.
      - For symbolic links just the user and group will be set.
      - For all files and directories the user and group will be "root".

    :param files: A list of files to apply default ACL.
    """

    default_file_mode = 0o660
    default_dir_mode = 0o755
    default_exec_mode = 0o770

    for filename in files:
        mode = default_file_mode
        if os.path.isdir(filename):
            mode = default_dir_mode
        else:
            # Check if file is an executable file
            status = os.stat(filename, follow_symlinks=False)
            if status.st_mode & 0o111:
                mode = default_exec_mode
        set_file_mode(filename, mode)


def remove_links_from_tcattr(base_dir):
    """
    Remove any symbolic link from the '.tcattr' file.
    It's need because we cannot set mode (permissions) for symbolic
    links in Linux.

    :param base_dir: Base directory where there is a '.tcattr' file.
    """

    tcattr = []
    tcattr_file = os.path.join(base_dir, '.tcattr')
    tcattr_file_tmp = os.path.join(base_dir, '.tcattr.tmp')
    field_separator = '%TCB%'

    with open(tcattr_file, "r", encoding="utf-8") as fd_tcattr:
        for line in fd_tcattr:
            if line.startswith('\n'):
                tcattr.append(field_separator)
            else:
                tcattr.append(line)
    tcattr = ''.join(tcattr)

    with open(tcattr_file_tmp, "w", encoding="utf-8") as fd_tcattr_tmp:
        for file_attr in tcattr.split(field_separator):
            filename = file_attr.split('\n')[0].replace('# file: ', '')
            if not os.path.islink(os.path.join(base_dir, filename)):
                fd_tcattr_tmp.write(file_attr+'\n')

    os.rename(tcattr_file_tmp, tcattr_file)


def set_acl_attributes(change_dir):
    """
    From "change_dir" onward, find all ".tcattr" files and create two lists
    which the content should be:
      - Files and/or directories that must have ".tcattr" ACLs
      - The other files and/or directories that must have "default" ACLs
    Each ".tcattr" file should be created by the "isolate" command or
    manually by the user.
    Having both lists in hand, set the attributes.

    :param change_dir: Directory with changes to be incorporated into an
                       OSTree commit.
    """

    files_to_apply_tcattr_acl = []
    files_to_apply_default_acl = []

    for base_dir, _, filenames in os.walk(change_dir):
        if '.tcattr' not in filenames:
            continue
        remove_links_from_tcattr(base_dir)
        with open(os.path.join(base_dir, '.tcattr'),
                  "r", encoding="utf-8") as fd_tcattr:
            files_to_apply_tcattr_acl = [
                (base_dir, line.strip().replace('# file: ', ''))
                for line in fd_tcattr
                if '# file: ' in line]

    for base_dir, dirnames, filenames in os.walk(change_dir):
        for filename in dirnames + filenames:
            if filename != '.tcattr' and \
               os.path.join(base_dir, filename) not in [
                       os.path.join(*f)
                       for f in files_to_apply_tcattr_acl]:
                files_to_apply_default_acl.append(os.path.join(base_dir, filename))

    apply_tcattr_acl(files_to_apply_tcattr_acl)
    apply_default_acl(files_to_apply_default_acl)


def make_dirs_labels(changes_dirs, stor_pref, work_pref):
    """Create a mapping between changes directories and labels

    The labels are of the form WORKDIR/<dirname> or STORAGE/<dirname>
    and are intended just for displaying to the user.

    """
    # Ensure prefixes have a leading slash.
    stor_pref = os.path.join(stor_pref, '')
    work_pref = os.path.join(work_pref, '')

    dirs_labels = {}
    for fulldir in changes_dirs:
        if fulldir.startswith(stor_pref):
            dirs_labels[fulldir] = f"STORAGE/{fulldir[len(stor_pref):]}"
        elif fulldir.startswith(work_pref):
            dirs_labels[fulldir] = f"WORKDIR/{fulldir[len(work_pref):]}"
        else:
            assert False, f"Unhandled prefix: {fulldir}"

    return dirs_labels


def _check_parse_ostree_key_args(ostree_key_dir, ostree_key, *,
                                 check_seck=True, check_pubk=True):
    """Parse and validate arguments to --ostree-key/--ostree-key-dir."""

    if ostree_key_dir and not ostree_key:
        raise InvalidArgumentError(
            "Error: ostree-key-dir was passed but ostree-key was not provided. Aborting.")

    if image_has_cfs_support():
        if ostree_key is None:
            # Abort the operation to avoid producing non-bootable images.
            raise InvalidArgumentError(
                "Error: The image has support for the root filesystem protection, but the "
                "ostree-key parameter has not been passed; the parameter is required for "
                "signing the commit.")
    else:
        if ostree_key is not None:
            raise InvalidArgumentError(
                "Error: The ostree-key parameter has been passed for an image that has no "
                "support for the root filesystem protection. Aborting.")

    if ostree_key is None:
        return None

    if ostree_key_dir is not None and not os.path.isdir(ostree_key_dir):
        raise PathNotExistError(
            f"Error: OSTree keys directory '{ostree_key_dir}' does not exist. Aborting.")

    ostree_key_dir = ostree_key_dir or "."
    ostree_key_obj = parse_ostree_key(ostree_key, ostree_key_dir=ostree_key_dir)

    if check_seck:
        seck_file = ostree_key_obj.get_sec_key_path()
        if not os.path.isfile(seck_file):
            raise PathNotExistError(
                f"Error: Cannot read secret key file '{seck_file}'.")

    if check_pubk:
        pubk_file = ostree_key_obj.get_pub_key_path()
        if not os.path.isfile(pubk_file):
            raise PathNotExistError(
                f"Error: Cannot read public key file '{pubk_file}'.")

    return ostree_key_obj


def union(changes_dirs, union_branch, *,
          commit_subject=None, commit_body=None,
          ostree_key_dir=None, ostree_key=None):
    """Perform the actual work of the union subcommand"""

    images_unpack_executed()

    ostree_key_obj = _check_parse_ostree_key_args(ostree_key_dir, ostree_key)

    # Automatically add directories from storage. The order in which we
    # apply these directories to an ostree commit must be exactly like it is
    # set up in here so the "initramfs.img" file produced by the "splash"
    # command will not be overwritten by the "initramfs.img" produced by
    # the "kernel" command.
    storage_dir_ = get_storage_dir()
    changes_dirs_ = []
    for subdir in ["changes", "kernel", "splash", "dt"]:
        changed_dir = os.path.join(storage_dir_, subdir)
        if os.path.isdir(changed_dir):
            if subdir == "changes":
                set_acl_attributes(changed_dir)
            changes_dirs_.append(changed_dir)

    temp_dir_extra = os.path.join("/tmp", "changes_dirs")
    if changes_dirs:
        os.mkdir(temp_dir_extra)
        check_and_append_dirs(changes_dirs_, changes_dirs, temp_dir_extra)

    dirs_labels = make_dirs_labels(changes_dirs_, storage_dir_, temp_dir_extra)

    # Callback to show the label when backend is about to apply it:
    def apply_callback(fulldir):
        log.info(f"Applying changes from {dirs_labels[fulldir]}.")

    commit = ub.union_changes(
        changes_dir=changes_dirs_,
        union_branch=union_branch,
        subject=commit_subject,
        body=commit_body,
        ostree_key=ostree_key_obj,
        pre_apply_callback=apply_callback)

    log.info(f"Commit {commit} has been generated for changes and is ready"
             " to be deployed.")


def do_union(args):
    """Run "union" subcommand"""

    union(
        args.changes_dirs,
        args.union_branch,
        commit_subject=args.subject,
        commit_body=args.body,
        ostree_key_dir=args.ostree_key_dir,
        ostree_key=args.ostree_key)


def init_parser(subparsers):
    """Initialize argument parser"""
    subparser = subparsers.add_parser(
        "union",
        help="Create a commit out of isolated changes for unpacked Toradex Easy Installer Image.",
        allow_abbrev=False)

    subparser.add_argument(
        "--changes-directory", dest="changes_dirs", action='append',
        help=("Path to the directory containing user changes (can be specified multiple times). "
              "If you have changes in the storage, the changes passed in this parameter will be "
              "applied on top of them."))
    subparser.add_argument(
        "--subject", dest="subject",
        help="OSTree commit subject. Defaults to 'TorizonCore Builder [timestamp]'.")
    subparser.add_argument(
        "--body", dest="body", help="OSTree commit body message")

    subparser.add_argument(
        "--ostree-key",
        dest="ostree_key",
        metavar="OSTREE_KEY",
        help=("OSTree signing key information in the form 'name=<NAME>;algo=<ALGO>' where <NAME> "
              "is the key name and <ALGO> corresponds to the signing algorithm (e.g. "
              "'name=prod;algo=ed25519'). If <ALGO> is not provided, it defaults to "
              f"'{OSTreeKey.OSTREE_KEY_DEFAULT_ALGO}'. "
              "This switch must be specified if (and only if) the image being customized has "
              "support for the root filesystem protection."))
    subparser.add_argument(
        "--ostree-key-dir",
        dest="ostree_key_dir",
        metavar="OSTREE_KEY_DIR",
        help=("OSTree key directory path. This directory must contain a private key file named "
              "<NAME>.sec, where <NAME> must be specified through the --ostree-key switch. "
              "(default: working directory)"))

    subparser.add_argument(
        dest="union_branch",
        metavar="UNION_BRANCH",
        help="Name of branch containing the changes committed to the unpacked repository.")

    subparser.set_defaults(func=do_union)
