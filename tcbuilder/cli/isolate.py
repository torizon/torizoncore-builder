"""
CLI handling for isolate subcommand
"""

import os
import logging
import shutil

from tcbuilder.backend import isolate, common
from tcbuilder.errors import OperationFailureError

# use name hierarchy for "main" to be the parent
log = logging.getLogger("torizon." + __name__)


def create_changes_directory(dir_name, force_removal=False):
    """
    Create the changes directory for the "isolated" files.

    :param dir_name: Directory name.
    :param force_removal: Completely remove the directory before creating a
                          new one.
    :raises:
        OperationFailureError: If changes directory is not empty and a "force"
                               removal was not provided.
    """

    if not os.path.exists(dir_name):
        os.mkdir(dir_name)
    elif not force_removal:
        raise OperationFailureError("There is already a directory with "
                                    "isolated changes. If you want to replace "
                                    "it, please use --force.")
    else:
        shutil.rmtree(dir_name)
        os.mkdir(dir_name)


def isolate_subcommand(args):
    """
    Check all parameters and prepare everything to call the "isolate"
    backend service.

    :param args: Arguments provided to the "isolate" subcommand.
    """

    storage_dir = os.path.abspath(args.storage_directory)
    changes_dir = os.path.join(storage_dir, "changes")

    if args.changes_dir:
        changes_dir = os.path.abspath(args.changes_dir)

    create_changes_directory(changes_dir, force_removal=args.force)

    ret = isolate.isolate_user_changes(changes_dir,
                                       args.remote_host,
                                       args.remote_username,
                                       args.remote_password,
                                       args.mdns_source)
    if ret == isolate.NO_CHANGES:
        log.info("There are no changes in /etc to be isolated.")
    else:
        if args.changes_dir:
            common.set_output_ownership(changes_dir)
        log.info("Changes in /etc successfully isolated.")


def init_parser(subparsers):
    """
    Parse for "isolate" command.
    """

    subparser = subparsers.add_parser("isolate",
                                      help="capture /etc changes.")

    subparser.add_argument("--changes-directory",
                           dest="changes_dir",
                           help="Directory to save the isolated changes from "
                                "the device. Must be a file system capable "
                                "of carrying Linux file system metadata "
                                "(Unix file permissions and xattr). If not "
                                "passed, defaults to a directory in the "
                                "storage volume.")
    subparser.add_argument("--force",
                           dest="force",
                           action="store_true",
                           help="Force removal of storage changes directory",
                           default=False)
    subparser.add_argument("--remote-host",
                           dest="remote_host",
                           help="name/IP of remote machine",
                           required=True)
    common.add_username_password_arguments(subparser)
    subparser.add_argument("--mdns-source",
                           dest="mdns_source",
                           help="Use the given IP address as mDNS source. "
                                "This is useful when multiple interfaces "
                                "are used, and mDNS multicast requests are "
                                "sent out the wrong network interface.")

    subparser.set_defaults(func=isolate_subcommand)
