import os
import logging
import shutil
from tcbuilder.backend import isolate
from tcbuilder.errors import PathNotExistError, UserAbortError

log = logging.getLogger("torizon." + __name__)  # use name hierarchy for "main" to be the parent


def isolate_subcommand(args):
    storage_dir = os.path.abspath(args.storage_directory)
    if args.changes_dir is None:
        changes_dir = os.path.join(storage_dir, "changes")
        if not os.path.exists(changes_dir):
            os.mkdir(changes_dir)
    else:
        changes_dir = os.path.abspath(args.changes_dir)
        if not os.path.exists(changes_dir):
            raise PathNotExistError(f'Changes directory "{args.changes_dir}" does not exist.')
            

    if os.listdir(changes_dir):
        ans = input(f"{changes_dir} is not empty. Delete contents before continuing? [y/N] ")
        if ans.lower() != "y":
            raise UserAbortError()

        shutil.rmtree(changes_dir)
        os.mkdir(changes_dir)

    ret = isolate.isolate_user_changes(changes_dir, args.remote_host,
                                       args.remote_username, args.remote_password,
                                       args.mdns_source)
    if ret == isolate.NO_CHANGES:
        log.info("no change is made in /etc by user")

    log.info("isolation command completed")


def init_parser(subparsers):
    subparser = subparsers.add_parser("isolate", help="""\
    capture /etc changes.
    """)

    subparser.add_argument("--changes-directory", dest="changes_dir",
                           help="""Directory for changes to be stored on the host system.
                           Must be a file system capable of carrying Linux file system
                           metadata (Unix file permissions and xattr). Defaults to
                           a directory in the internal storage volume.""")
    subparser.add_argument("--remote-host", dest="remote_host",
                           help="""name/IP of remote machine""",
                           required=True)
    subparser.add_argument("--remote-username", dest="remote_username",
                           help="""user name of remote machine""",
                           required=True)
    subparser.add_argument("--remote-password", dest="remote_password",
                           help="""password of remote machine""",
                           required=True)
    subparser.add_argument("--mdns-source", dest="mdns_source",
                           help="""Use the given IP address as mDNS source.
                           This is useful when multiple interfaces are used, and
                           mDNS multicast requests are sent out the wrong
                           network interface.""")

    subparser.set_defaults(func=isolate_subcommand)
