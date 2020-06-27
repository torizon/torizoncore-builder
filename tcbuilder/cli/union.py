import os
import sys
import logging
import subprocess
import shutil
import traceback
from tcbuilder.backend import union


def union_subcommand(args):
    log = logging.getLogger("torizon." + __name__)
    storage_dir = os.path.abspath(args.storage_directory)
    changes_dir = os.path.abspath(args.diff_dir)
    final_branch = args.fbranch
    try:
        commit = union.union_changes(storage_dir, changes_dir, final_branch)
        log.info(f"Commit {commit} has been generated for changes and ready to be deployed.")
    except Exception as ex:
        if hasattr(ex, "msg"):
            log.error(ex.msg)  # msg from all kinds of Exceptions
            log.info(ex.det)  # more elaborative message
        else:
            log.error(str(ex))

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
    subparser.add_argument("--final-branch", dest="fbranch",
                        help="""Name of branch containing the changes commited to 
                        the unpacked repo.  
                        """,
                        required=True)

    subparser.set_defaults(func=union_subcommand)
