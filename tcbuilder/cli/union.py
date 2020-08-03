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
    diff_dir = os.path.abspath(args.diff_dir)
    union_branch = args.union_branch

    if args.sysroot_directory is None:
        sysroot_dir = os.path.join(storage_dir, "sysroot")
    else:
        sysroot_dir = os.path.abspath(args.sysroot_directory)

    src_ostree_archive_dir = os.path.join(storage_dir, "ostree-archive")

    if not os.path.exists(sysroot_dir):
        log.error(f"{sysroot_dir} does not exist")
        return

    if not os.path.exists(diff_dir):
        log.error(f"{diff_dir} does not exist")
        return

    if not os.path.exists(storage_dir):
        log.error(f"{storage_dir} does not exist")
        return

    try:
        commit = union.union_changes(storage_dir, diff_dir, sysroot_dir,
                                     src_ostree_archive_dir, union_branch)
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
    subparser.add_argument("--sysroot-directory", dest="sysroot_directory",
                           help="""Path to source sysroot storage.""")
    subparser.add_argument("--union-branch", dest="union_branch",
                        help="""Name of branch containing the changes committed to 
                        the unpacked repo.  
                        """,
                        required=True)

    subparser.set_defaults(func=union_subcommand)
