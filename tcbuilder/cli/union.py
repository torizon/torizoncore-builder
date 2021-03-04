"""Union sub-command CLI handling

The union sub-command merges a given OSTree reference (e.g. branch or commit
hash) with local changes (e.g. copied from an adjusted module using the isolate
sub-command).
"""

import os
import logging
from tcbuilder.backend import union
from tcbuilder.errors import PathNotExistError

log = logging.getLogger("torizon." + __name__)

def check_and_append_dirs(changes_dirs, new_changes_dirs):
    """Check and append additional directories with changes"""

    for changes_dir in new_changes_dirs:
        if not os.path.exists(changes_dir):
            raise PathNotExistError(f'Changes directory "{changes_dir}" does not exist')

        changes_dirs.append(os.path.abspath(changes_dir))    

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
                changes_dirs.append(changed_dir)
    else:
        check_and_append_dirs(changes_dirs, args.changes_dirs)

    if args.extra_changes_dirs is not None:
        check_and_append_dirs(changes_dirs, args.extra_changes_dirs)

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
