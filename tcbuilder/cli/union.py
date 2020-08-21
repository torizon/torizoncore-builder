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

def union_subcommand(args):
    """Run \"union\" subcommand"""
    log = logging.getLogger("torizon." + __name__)
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
    else:
        for changes_dir in args.changes_dirs:
            changes_dirs.append(os.path.abspath(changes_dir))
            if not os.path.exists(changes_dir):
                log.error(f'Changes directory "{changes_dir}" does not exist')
                return

    union_branch = args.union_branch

    src_ostree_archive_dir = os.path.join(storage_dir, "ostree-archive")

    try:
        commit = union.union_changes(changes_dirs, src_ostree_archive_dir, union_branch)
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
    subparser.add_argument("--union-branch", dest="union_branch",
                           help="""Name of branch containing the changes committed to
                           the unpacked repo.
                           """,
                           required=True)

    subparser.set_defaults(func=union_subcommand)
