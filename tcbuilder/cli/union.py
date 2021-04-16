"""Union sub-command CLI handling

The union sub-command merges a given OSTree reference (e.g. branch or commit
hash) with local changes (e.g. copied from an adjusted module using the isolate
sub-command).
"""

import os
import logging
import subprocess
from tcbuilder.backend import union
from tcbuilder.errors import PathNotExistError

log = logging.getLogger("torizon." + __name__)

def check_and_append_dirs(changes_dirs, new_changes_dirs, temp_dir):
    """Check and append additional directories with changes"""

    for changes_dir in new_changes_dirs:
        if not os.path.exists(changes_dir):
            raise PathNotExistError(f'Changes directory "{changes_dir}" does not exist')

        os.makedirs(f"{temp_dir}/{changes_dir}")
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
            if filename != '.tcattr':
                full_filename = f'{base_dir}/{filename}'
                if full_filename not in ['/'.join(f)
                                         for f in files_to_apply_tcattr_acl]:
                    files_to_apply_default_acl.append(full_filename)

    apply_tcattr_acl(files_to_apply_tcattr_acl)
    apply_default_acl(files_to_apply_default_acl)


def union_subcommand(args):
    """Run \"union\" subcommand"""
    storage_dir = os.path.abspath(args.storage_directory)

    if not os.path.exists(storage_dir):
        raise PathNotExistError(f'Storage directory "{storage_dir}" does not exist.')

    changes_dirs = []
    if args.changes_dirs is None:
        # Automatically add the ones present...
        for subdir in ["changes", "splash", "dt", "kernel"]:
            changed_dir = os.path.join(storage_dir, subdir)
            if os.path.isdir(changed_dir):
                if subdir == "changes":
                    set_acl_attributes(changed_dir)
                changes_dirs.append(changed_dir)
    else:
        temp_dir = os.path.join("/tmp", "changes_dirs")
        os.mkdir(temp_dir)
        check_and_append_dirs(changes_dirs, args.changes_dirs, temp_dir)

    if args.extra_changes_dirs is not None:
        temp_dir_extra = os.path.join("/tmp", "extra_changes_dirs")
        os.mkdir(temp_dir_extra)
        check_and_append_dirs(changes_dirs, args.extra_changes_dirs, temp_dir_extra)

    union_branch = args.union_branch

    src_ostree_archive_dir = os.path.join(storage_dir, "ostree-archive")

    commit = union.union_changes(changes_dirs, src_ostree_archive_dir, union_branch,
                                 args.subject, args.body)
    log.info(f"Commit {commit} has been generated for changes and ready to be deployed.")

def init_parser(subparsers):
    """Initialize argument parser"""
    subparser = subparsers.add_parser("union", help="""\
    Create a commit out of isolated changes for unpacked Toradex Easy Installer Image""")
    subparser.add_argument("--changes-directory", dest="changes_dirs", action='append',
                           help="""Path to the directory containing user changes.
                           Can be specified multiple times!""")
    subparser.add_argument("--extra-changes-directory", dest="extra_changes_dirs", action='append',
                           help="""Additional path with user changes to be committed.
                           Can be specified multiple times!""")
    subparser.add_argument("--union-branch", dest="union_branch",
                           help="""Name of branch containing the changes committed to
                           the unpacked repo.
                           """,
                           required=True)
    subparser.add_argument("--subject", dest="subject",
                           help="""OSTree commit subject. Defaults to
                           "TorizonCore Builder [timestamp]"
                           """)
    subparser.add_argument("--body", dest="body",
                           help="""OSTree commit body message""")

    subparser.set_defaults(func=union_subcommand)
