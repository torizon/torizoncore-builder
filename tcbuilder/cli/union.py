"""Union sub-command CLI handling

The union sub-command merges a given OSTree reference (e.g. branch or commit
hash) with local changes (e.g. copied from an adjusted module using the isolate
sub-command).
"""

import argparse
import logging
import os
import subprocess

from tcbuilder.backend import union as ub
from tcbuilder.errors import PathNotExistError, InvalidArgumentError

log = logging.getLogger("torizon." + __name__)


def check_and_append_dirs(changes_dirs, new_changes_dirs, temp_dir):
    """Check and append additional directories with changes"""

    for changes_dir in new_changes_dirs:
        if not os.path.exists(changes_dir):
            raise PathNotExistError(f'Changes directory "{changes_dir}" does not exist')

        os.makedirs(f"{temp_dir}/{changes_dir}")
        # Review: not appropriately handling especial directory names (FIXME).
        cp_command = f"cp -r {changes_dir}/. {temp_dir}/{changes_dir}"
        subprocess.check_output(cp_command, shell=True,
                                stderr=subprocess.STDOUT)
        temp_change_dir = os.path.join(temp_dir, changes_dir)
        set_acl_attributes(temp_change_dir)
        changes_dirs.append(os.path.abspath(temp_change_dir))


def apply_tcattr_acl(files):
    """
    Apply ACLs based on .tcattr files. It just needs to be done once for
    each ".tcattr" file found in each sub directory of the tree.
    """

    # Review: not appropriately handling especial directory names (FIXME).
    for tcattr_basedir in {tcattr[0] for tcattr in files}:
        setfacl_cmd = f"cd {tcattr_basedir} && \
                        setfacl --restore={tcattr_basedir}/.tcattr"
        subprocess.run(setfacl_cmd, shell=True, check=True)


def apply_default_acl(files):
    """
    Apply default ACL to files and directories.
      - For executables files: 0770.
      - For non-executables files: 0660.
      - For directories: 0755.
      - For all files and directories the user and group will be "root".
    """

    default_file_mode = "0660"
    default_dir_mode = "0755"
    default_exec_mode = "0770"

    for filename in files:
        mode = default_file_mode
        if os.path.isdir(filename):
            mode = default_dir_mode
        else:
            # Check if file is an executable file
            status = os.stat(filename)
            if status.st_mode & 0o777 & 0o111:
                mode = default_exec_mode

        # Review: not appropriately handling especial directory names (FIXME).
        default_acl_cmd = f'chmod {mode} \'{filename}\' && \
                            chown root.root \'{filename}\''
        subprocess.run(default_acl_cmd, shell=True, check=True)


def set_acl_attributes(change_dir):
    """
    From "change_dir" onward, find all ".tcattr" files and create two lists
    which the contents should be:
      - Files and/or directories that must have ".tcattr" ACLs
      - The other files and/or directories that must have "default" ACLs
    Each ".tcattr" file should be created by the "isolate" command or
    manually by the user.
    """

    files_to_apply_tcattr_acl = []
    files_to_apply_default_acl = []

    for base_dir, _, filenames in os.walk(change_dir):
        if '.tcattr' not in filenames:
            continue
        with open(f'{base_dir}/.tcattr') as fd_tcattr:
            for line in fd_tcattr:
                if '# file: ' in line:
                    line = line.strip().replace('# file: ', '')
                    files_to_apply_tcattr_acl.append((f'{base_dir}', line))

    for base_dir, dirnames, filenames in os.walk(change_dir):
        for filename in dirnames + filenames:
            # Review: Reduce nesting (FIXME).
            if filename != '.tcattr':
                full_filename = f'{base_dir}/{filename}'
                if full_filename not in ['/'.join(f)
                                         for f in files_to_apply_tcattr_acl]:
                    files_to_apply_default_acl.append(full_filename)

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


def union(changes_dirs, storage_dir, union_branch,
          commit_subject=None, commit_body=None):
    """Perform the actual work of the union subcommand"""

    storage_dir_ = os.path.abspath(storage_dir)
    if not os.path.exists(storage_dir_):
        raise PathNotExistError(
            f"Storage directory \"{storage_dir_}\" does not exist.")

    changes_dirs_ = []

    # Automatically add directories from storage.
    for subdir in ["changes", "splash", "dt", "kernel"]:
        changed_dir = os.path.join(storage_dir_, subdir)
        if os.path.isdir(changed_dir):
            if subdir == "changes":
                set_acl_attributes(changed_dir)
            changes_dirs_.append(changed_dir)

    temp_dir_extra = os.path.join("/tmp", "changes_dirs")
    if changes_dirs:
        os.mkdir(temp_dir_extra)
        check_and_append_dirs(changes_dirs_, changes_dirs, temp_dir_extra)

    src_ostree_archive_dir = os.path.join(storage_dir_, "ostree-archive")
    dirs_labels = make_dirs_labels(changes_dirs_, storage_dir_, temp_dir_extra)

    # Callback to show the label when backend is about to apply it:
    def apply_callback(fulldir):
        log.info(f"Applying changes from {dirs_labels[fulldir]}.")

    log.debug(f"union: subject='{commit_subject}' body='{commit_body}'")
    commit = ub.union_changes(
        changes_dirs_, src_ostree_archive_dir,
        union_branch, commit_subject, commit_body,
        pre_apply_callback=apply_callback)

    log.info(f"Commit {commit} has been generated for changes and is ready"
             " to be deployed.")


def do_union(args):
    """Run "union" subcommand"""

    # Temporary solution to provide better messages (DEPRECATED since 2021-05-17).
    if args.changes_dirs_compat:
        raise InvalidArgumentError(
            "Error: "
            "the switch --extra-changes-directory has been removed; "
            "please use switch --changes-directory instead.")

    # Temporary solution to provide better messages (DEPRECATED since 2021-05-17).
    if args.union_branch_compat:
        raise InvalidArgumentError(
            "Error: "
            "the switch --union-branch has been removed; "
            "please provide the branch name without passing the switch.")

    # Temporary solution to provide better messages (DEPRECATED since 2021-05-17).
    if not args.union_branch:
        raise InvalidArgumentError(
            "Error: "
            "the UNION_BRANCH positional argument is required.")

    union(args.changes_dirs, args.storage_directory,
          args.union_branch, args.subject, args.body)


def init_parser(subparsers):
    """Initialize argument parser"""
    subparser = subparsers.add_parser(
        "union",
        help=("Create a commit out of isolated changes for unpacked "
              "Toradex Easy Installer Image"),
        epilog=("NOTE: the switch --extra-changes-directory has been "
                "removed; please use --changes-directory instead."))
    subparser.add_argument(
        "--changes-directory", dest="changes_dirs", action='append',
        help=("Path to the directory containing user changes (can be "
              "specified multiple times). If you have changes in the "
              "storage, the changes passed in this parameter will be "
              "applied on top of them."))
    subparser.add_argument(
        "--subject", dest="subject",
        help=("OSTree commit subject. "
              "Defaults to TorizonCore Builder [timestamp]"))
    subparser.add_argument(
        "--body", dest="body", help="OSTree commit body message")

    # The nargs='?' argument below can be removed together with the
    # --extra-changes-directory and --union-branch switches that currently
    # exist just to allow for better messages (DEPRECATED since 2021-05-17).
    subparser.add_argument(
        dest="union_branch",
        metavar="UNION_BRANCH",
        nargs='?',
        help=("Name of branch containing the changes committed to the "
              "unpacked repository (REQUIRED)."))

    # Temporary solution to provide better messages (DEPRECATED since 2021-05-17).
    subparser.add_argument(
        "--extra-changes-directory",
        dest="changes_dirs_compat", action='append', help=argparse.SUPPRESS)
    subparser.add_argument(
        "--union-branch",
        dest="union_branch_compat", help=argparse.SUPPRESS)

    subparser.set_defaults(func=do_union)
