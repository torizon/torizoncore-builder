"""Push sub-command CLI handling

The push sub-command makes use of aktualizr's SOTA tools (specifically
garage-push and garage-sign) to sign & push a new OSTree to be deployed over OTA
to the devices.
"""

import os
import datetime

from tcbuilder.backend import push
from tcbuilder.errors import PathNotExistError


def push_subcommand(args):
    """Run \"push\" subcommand"""
    storage_dir = os.path.abspath(args.storage_directory)
    credentials = os.path.abspath(args.credentials)

    if args.ref.endswith(".yml") or args.ref.endswith(".yaml"):
        compose_file = os.path.abspath(args.ref)
        target = args.target or "docker-compose_file.yml"
        version = args.version or datetime.datetime.today().strftime("%Y-%m-%d")
        push.push_compose(credentials, target, version, compose_file)
    else:
        if args.ostree is not None:
            src_ostree_archive_dir = os.path.abspath(args.ostree)
        else:
            src_ostree_archive_dir = os.path.join(storage_dir, "ostree-archive")

        tuf_repo = os.path.join("/deploy", "tuf-repo")

        if not os.path.exists(storage_dir):
            raise PathNotExistError(f"{storage_dir} does not exist")

        hardwareids = None
        if args.hardwareids is not None:
            hardwareids = ",".join(args.hardwareids)
        push.push_ref(src_ostree_archive_dir, tuf_repo, credentials,
                      args.ref, args.version, args.target, hardwareids,
                      args.verbose)

def init_parser(subparsers):
    """Initialize argument parser"""

    subparser = subparsers.add_parser("push", help="Push branch to OTA server")
    subparser.add_argument(
        "--credentials", dest="credentials",
        help="Relative path to credentials.zip.", required=True)
    subparser.add_argument(
        "--repo", dest="ostree",
        help="OSTree repository to push from.", required=False)
    subparser.add_argument(
        "--hardwareid", dest="hardwareids", action="append",
        help="Hardware IDs to use when creating and signing targets.json.",
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
        metavar="REF", nargs="?", dest="ref",
        help="OSTree reference or docker-compose file to push to Torizon OTA.")
    subparser.add_argument(
        "--verbose", dest="verbose",
        action="store_true",
        help="Show more output", required=False)

    subparser.set_defaults(func=push_subcommand)
