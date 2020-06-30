import os
import sys
import logging
import subprocess
import shutil
import traceback
from tcbuilder.backend import union
from tcbuilder.backend.common import TorizonCoreBuilderError


def union_subcommand(args):
    log = logging.getLogger("torizon." + __name__)
    storage_dir = os.path.abspath(args.storage_directory)
    changes_dir = os.path.abspath(args.diff_dir)
    diff_branch = args.diff_branch
    try:
        commit = union.union_changes(storage_dir, changes_dir, diff_branch)
        log.info(f"Commit {commit} has been generated for changes and ready to be deployed.")
    except TorizonCoreBuilderError as ex:
        log.error(ex.msg)  # msg from all kinds of Exceptions
        if ex.det is not None:
            log.info(ex.det)  # more elaborative message
        log.debug(traceback.format_exc())  # full traceback to be shown for debugging only

def init_parser(subparsers):
    subparser = subparsers.add_parser("union", help="""\
    Create a commit out of isolated changes for unpacked Tezi Image""")
    subparser.add_argument("--diff-directory", dest="diff_dir",
                       help="""Path to the directory containing user changes
                        (must be same as provided for isolate).
                        Must be a file system capable of carrying Linux file system 
                        metadata (Unix file permissions and xattr).""",
                        default="/storage/changes")
    subparser.add_argument("--diff-branch", dest="diff_branch",
                        help="""Name of branch containing the changes commited to 
                        the unpacked repo.  
                        """,
                        required=True)

    subparser.set_defaults(func=union_subcommand)
