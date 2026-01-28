"""
CLI for the splash command
"""

import argparse
import os
import logging

from tcbuilder.errors import \
    (InvalidArgumentError, PathNotExistError)
from tcbuilder.backend import splash as splash_be
from tcbuilder.backend.kernel import \
    (find_kernel_in_sysroot, get_kernel_changes_dir)
from tcbuilder.backend.initramfs import UnpackedInitramfs
from tcbuilder.backend.common import \
    (images_unpack_executed, is_file_type_fit)

log = logging.getLogger("torizon." + __name__)  # use name hierarchy for "main" to be the parent


def splash(splash_image):
    """Prepare everything to call the "splash" backend service.

    :param splash_image: Path to the image splash filename.
    :raises:
        PathNotExistError: If could not find the splash image file.
    """

    splash_abspath = os.path.abspath(splash_image)
    if not os.path.isfile(splash_abspath):
        raise PathNotExistError(f"Unable to find splash image {splash_image}")

    with UnpackedInitramfs(source="auto") as rdm:
        splash_be.add_plymouth_splash_image(rdm.get_path(), splash_abspath)

    log.info("Initramfs splash screen updated")

    unpacked_kernel_path = find_kernel_in_sysroot()
    kernel_is_fit = is_file_type_fit(unpacked_kernel_path)
    log.debug(f"splash: kernel_is_fit={kernel_is_fit}")

    if kernel_is_fit:
        # FIT case: all changes go to the kernel-changes directory.
        changes_dir = get_kernel_changes_dir()
    else:
        # non-FIT case: changes go to the splash-changes directory.
        changes_dir = splash_be.get_splash_changes_dir()

    splash_be.add_plymouth_splash_image(changes_dir, splash_abspath)
    log.info("Sysroot splash screen updated")


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

    images_unpack_executed()
    splash(args.splash_image)


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
