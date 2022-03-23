"""Push sub-command CLI handling

The push sub-command makes use of aktualizr's SOTA tools (specifically
garage-push and garage-sign) to sign & push a new OSTree to be deployed over OTA
to the devices.
"""

import os
import logging
import datetime
import argparse

from tcbuilder.backend import push
from tcbuilder.errors import InvalidArgumentError, PathNotExistError, TorizonCoreBuilderError

log = logging.getLogger("torizon." + __name__)


def push_subcommand(args):
    """Run \"push\" subcommand"""

    if args.canonicalize_only:
        # pylint: disable=singleton-comparison
        if args.canonicalize == False:
            raise TorizonCoreBuilderError(
                "Error: The '--no-canonicalize' and '--canonicalize-only' "
                "options cannot be used at the same time. Please, run "
                "torizoncore-builder push --help for more information.")
        lock_file, _ = push.canonicalize_compose_file(args.ref, args.force)
        log.info(f"Not pushing '{os.path.basename(lock_file)}' to OTA server.")
        return

    if not args.credentials:
        raise TorizonCoreBuilderError("--credentials parameter is required.")

    storage_dir = os.path.abspath(args.storage_directory)
    credentials = os.path.abspath(args.credentials)

    if args.ref.endswith(".yml") or args.ref.endswith(".yaml"):
        if args.hardwareids and any(hwid != "docker-compose" for hwid in args.hardwareid):
            raise InvalidArgumentError("Error: --hardware is only valid when pushing "
                                       "OSTree reference. The hardware id for a "
                                       "docker-compose package can only be "
                                       "\"docker-compose\"")

        compose_file = os.path.abspath(args.ref)
        target = args.target or "docker-compose_file.yml"
        version = args.version or datetime.datetime.today().strftime("%Y-%m-%d")
        push.push_compose(credentials, target, version, compose_file,
                          args.canonicalize, args.force)
    else:
        if args.ostree is not None:
            src_ostree_archive_dir = os.path.abspath(args.ostree)
        else:
            src_ostree_archive_dir = os.path.join(storage_dir, "ostree-archive")

        tuf_repo = os.path.join("/deploy", "tuf-repo")

        if not os.path.exists(storage_dir):
            raise PathNotExistError(f"{storage_dir} does not exist")

        push.push_ref(src_ostree_archive_dir, tuf_repo, credentials,
                      args.ref, args.version, args.target, args.hardwareids,
                      args.verbose)


def init_parser(subparsers):
    """Initialize argument parser"""

    subparser = subparsers.add_parser("push", help="Push branch to OTA server")
    subparser.add_argument(
        "--credentials", dest="credentials",
        help="Relative path to credentials.zip.")
    subparser.add_argument(
        "--repo", dest="ostree",
        help="OSTree repository to push from.", required=False)
    subparser.add_argument(
        "--hardwareid", dest="hardwareids", action="append",
        help=("Hardware ID to use when pushing an OSTree package (can be specified "
              "multiple times). Will allow this package to be compatible with "
              "devices of the same Hardware ID."),
        required=False, default=None)
    subparser.add_argument(
        "--package-name", dest="target",
        help="Package name for docker-compose file or OSTree reference.",
        required=False, default=None)
    subparser.add_argument(
        "--package-version", dest="version",
        help="Package version for docker-compose file or OSTree reference.",
        required=False, default=None)
    subparser.add_argument(
        metavar="REF", dest="ref",
        help="OSTree reference or docker-compose file to push to Torizon OTA.")
    subparser.add_argument(
        "--canonicalize", dest="canonicalize", action=argparse.BooleanOptionalAction,
        help="Canonicalize the docker-compose file before pushing to Torizon OTA.")
    subparser.add_argument(
        "--canonicalize-only", dest="canonicalize_only", action="store_true",
        help="Canonicalize the docker-compose.yml file but do not send it to OTA server.",
        required=False, default=False)
    subparser.add_argument(
        "--force", dest="force", action="store_true", default=False,
        help="Force removal of the canonicalized file if it already exists.")
    subparser.add_argument(
        "--verbose", dest="verbose",
        action="store_true",
        help="Show more output", required=False)

    subparser.set_defaults(func=push_subcommand)
