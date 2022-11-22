"""
CLI for the splash command
"""

import argparse
import os
import shutil
import logging

from tcbuilder.errors import PathNotExistError, InvalidArgumentError
from tcbuilder.backend import splash as sbe
from tcbuilder.backend.common import images_unpack_executed

log = logging.getLogger("torizon." + __name__)  # use name hierarchy for "main" to be the parent


def splash(splash_image, storage_dir):
    """Prepare everything to call the "splash" backend service.

    :param splash_image: Path to the image splash filename.
    :param storage_dir: Storage volume directory.
    :raises:
        PathNotExistError: If could not find the splash image file.
    """

    storage_dir = os.path.abspath(storage_dir)

    work_dir = os.path.join(storage_dir, "splash")
    if os.path.exists(work_dir):
        shutil.rmtree(work_dir)
    os.mkdir(work_dir)

    splash_image = os.path.abspath(splash_image)
    if not os.path.exists(splash_image):
        raise PathNotExistError(f"Unable to find splash image {splash_image}")

    src_ostree_archive_dir = os.path.join(storage_dir, "ostree-archive")

    sbe.create_splash_initramfs(work_dir, splash_image, src_ostree_archive_dir)
    log.info("splash screen merged to initramfs")


def do_splash(args):
    """Check for deprecated parameters.

    :param args: Arguments provided to the "isolate" subcommand.
    :raises:
        InvalidArgumentError: If a deprecated switch was passed.
    """

    # Temporary solution to provide better messages (DEPRECATED since 2021-05-17).
    if args.image_compat:
        raise InvalidArgumentError(
            "Error: "
            "the switch --image has been removed; "
            "please provide the image filename without passing the switch.")

    # Temporary solution to provide better messages (DEPRECATED since 2021-05-17).
    if args.work_dir_compat:
        raise InvalidArgumentError(
            "Error: "
            "the switch --work-dir has been removed; "
            "the initramfs file should be created in storage.")

    images_unpack_executed(args.storage_directory)

    splash(args.splash_image, args.storage_directory)


def init_parser(subparsers):
    """Parser for "splash" command."""

    subparser = subparsers.add_parser(
        "splash",
        help="change splash screen",
        epilog="NOTE: the switches --image and --work-dir have been removed.",
        allow_abbrev=False)

    subparser.add_argument(
        dest="splash_image",
        metavar="SPLASH_IMAGE",
        help=("Path and name of splash screen image (REQUIRED)."))

    # Temporary solution to provide better messages (DEPRECATED since 2021-05-17).
    subparser.add_argument(
        "--image",
        dest="image_compat",
        action="store_true",
        default=False,
        help=argparse.SUPPRESS)

    # Temporary solution to provide better messages (DEPRECATED since 2021-05-17).
    subparser.add_argument(
        "--work-dir",
        dest="work_dir_compat",
        type=str,
        default="",
        help=argparse.SUPPRESS)

    subparser.set_defaults(func=do_splash)
