import os
import sys
import logging
import subprocess
from tcbuilder.backend import isolate


def isolate_subcommand(args):
    try:
        isolate.isolate_user_changes(args)
    except Exception as ex:
        print("Failed to get diff: " + str(ex), file=sys.stderr)


def init_parser(subparsers):
    subparser = subparsers.add_parser("isolate", help="""\
    capture /etc changes.
    """)

    subparser.add_argument("--diff-directory", dest="diff_dir",
                           help="""Directory for changes to be stored on the host system""",
                           required=True)
    subparser.add_argument("--remote-ip", dest="remoteip",
                           help="""name/IP of remote machine""",
                           required=True)
    subparser.add_argument("--remote-username", dest="remote_username",
                           help="""user name of remote machine""",
                           required=True)
    subparser.add_argument("--remote-password", dest="remote_password",
                           help="""password of remote machine""",
                           required=True)

    subparser.set_defaults(func=isolate_subcommand)
