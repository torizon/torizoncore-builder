"""Union sub-command CLI handling

The union sub-command merges a given OSTree reference (e.g. branch or commit
hash) with local changes (e.g. copied from an adjusted module using the isolate
sub-command).
"""

import os
import logging
import traceback
from tcbuilder.backend import union
from tcbuilder.errors import TorizonCoreBuilderError

log = logging.getLogger("torizon." + __name__)

def check_and_append_dirs(changes_dirs, new_changes_dirs):
    """Check and append additional directories with changes"""

    for changes_dir in new_changes_dirs:
        if not os.path.exists(changes_dir):
            log.error(f'Changes directory "{changes_dir}" does not exist')
            return False

        changes_dirs.append(os.path.abspath(changes_dir))

    return True

def union_subcommand(args):
    """Run \"union\" subcommand"""
    storage_dir = os.path.abspath(args.storage_directory)

    if not os.path.exists(storage_dir):
        log.error(f'Storage directory "{storage_dir}" does not exist.')
        return

    changes_dirs = []
    if args.changes_dirs is None:
        # Automatically add the ones present...
        if os.path.isdir("/storage/changes"):
            changes_dirs.append("/storage/changes")
        if os.path.isdir("/storage/splash"):
            changes_dirs.append("/storage/splash")
        if os.path.isdir("/storage/dt"):
            changes_dirs.append("/storage/dt")
    else:
        if not check_and_append_dirs(changes_dirs, args.changes_dirs):
            return

    if args.extra_changes_dirs is not None:
        if not check_and_append_dirs(changes_dirs, args.extra_changes_dirs):
            return

    union_branch = args.union_branch

    src_ostree_archive_dir = os.path.join(storage_dir, "ostree-archive")

    try:
        commit = union.union_changes(changes_dirs, src_ostree_archive_dir, union_branch,
                                     args.subject, args.body)
        log.info(f"Commit {commit} has been generated for changes and ready to be deployed.")
    except TorizonCoreBuilderError as ex:
        log.error(ex.msg)  # msg from all kinds of Exceptions
        if ex.det is not None:
            log.info(ex.det)  # more elaborative message
        log.debug(traceback.format_exc())  # full traceback to be shown for debugging only

def init_parser(subparsers):
    """Initialize argument parser"""
    subparser = subparsers.add_parser("union", help="""\
    Create a commit out of isolated changes for unpacked Tezi Image""")
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
                           "TorzionCore Builder [timestamp]"
                           """)
    subparser.add_argument("--body", dest="body",
                           help="""OSTree commit body message""")

    subparser.set_defaults(func=union_subcommand)
