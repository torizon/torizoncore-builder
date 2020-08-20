import os
import logging
import traceback
import shutil
from tcbuilder.backend import isolate
from tcbuilder.errors import TorizonCoreBuilderError
from tcbuilder.backend.common import resolve_remote_host

log = logging.getLogger("torizon." + __name__)  # use name hierarchy for "main" to be the parent


def isolate_subcommand(args):
    storage_dir = os.path.abspath(args.storage_directory)
    if args.diff_dir is None:
        diff_dir = os.path.join(storage_dir, "changes")
        if not os.path.exists(diff_dir):
            os.mkdir(diff_dir)
    else:
        diff_dir = os.path.abspath(args.diff_dir)
        if not os.path.exists(diff_dir):
            log.error(f'{args.diff_dir} does not exist')
            return

    if os.listdir(diff_dir):
        ans = input(f"{diff_dir} is not empty. Delete contents before continuing? [y/N] ")
        if ans.lower() != "y":
            return

        shutil.rmtree(diff_dir)
        os.mkdir(diff_dir)


    try:
        r_ip = resolve_remote_host(args.remote_host, args.mdns_source)
        ret = isolate.isolate_user_changes(diff_dir, r_ip, args.remote_username,
                                           args.remote_password)
        if ret == isolate.NO_CHANGES:
            log.info("no change is made in /etc by user")

        log.info("isolation command completed")
    except TorizonCoreBuilderError as ex:
        log.error(ex.msg)  # msg from all kinds of Exceptions
        if ex.det is not None:
            log.info(ex.det)  # more elaborative message
        log.debug(traceback.format_exc())  # full traceback to be shown for debugging only

def init_parser(subparsers):
    subparser = subparsers.add_parser("isolate", help="""\
    capture /etc changes.
    """)

    subparser.add_argument("--diff-directory", dest="diff_dir",
                           help="""Directory for changes to be stored on the host system.
                            Must be a file system capable of carrying Linux file system 
                            metadata (Unix file permissions and xattr).""")
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
