import os
import sys
import logging
import subprocess
import shutil
from tcbuilder.backend import union


def union_subcommand(args):
    storage_dir = os.path.abspath(args.storage_directory)
    changes_dir = os.path.abspath(args.diff_dir)
    final_branch = args.fbranch
    try:
        union.union_changes(storage_dir, changes_dir, final_branch)
    except Exception as ex:
        print("issue at union:" + str(ex))

def init_parser(subparsers):
    subparser = subparsers.add_parser("union", help="""\
    Create a commit out of isolated changes for unpacked Tezi Image""")
    subparser.add_argument("--diff-directory", dest="diff_dir",
                       help="""Path to the directory containing user changes
                        (must be same as provided for isolate).
                        Must be a file system capable of carrying Linux file system 
                        metadata (Unix file permissions and xattr).""",
                        default="/storage")
    subparser.add_argument("--storage-directory", dest="storage_directory",
                        help="""Path to the unpacked base Tezi Image.
                        (must be same as provided for unpack).""",
                        default="/storage")
    subparser.add_argument("--final-branch", dest="fbranch",
                        help="""Name of branch containing the changes commited to 
                        the unpacked repo.  
                        """,
                        required=True)

    subparser.set_defaults(func=union_subcommand)
