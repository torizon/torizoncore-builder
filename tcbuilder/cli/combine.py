"""Combine CLI frontend

Create Toradex Easy Installer image of TorizonCore with bundled Docker
container(s) from the "bundle" command.
"""

import os
import logging
import argparse

from tcbuilder.backend.common import (add_common_image_arguments,
                                      add_bundle_directory_argument,
                                      check_valid_tezi_image,
                                      set_output_ownership)

from tcbuilder.backend import combine
from tcbuilder.errors import (PathNotExistError,
                              InvalidArgumentError)

log = logging.getLogger("torizon." + __name__)


def check_deprecated_parameters(args):
    """Check deprecated combine command line arguments.

    It checks for "DEPRECATED" switches or command line arguments and
    shows a message explaining what the user should do.

    :param args: Arguments provided to the "combine" command.
    :raises:
        InvalidArgumentError: if a deprecated switch was passed.
    """

    # Temporary solution to provide better messages (DEPRECATED since 2021-05-17).
    if args.image_directory_compat:
        raise InvalidArgumentError(
            "Error: "
            "the switch --image-directory has been removed; "
            "please provide the image directory without passing the switch.")

    # Temporary solution to provide better messages (DEPRECATED since 2021-05-17).
    if args.output_directory_compat:
        raise InvalidArgumentError(
            "Error: "
            "the switch --output-directory has been removed; "
            "please provide the output directory without passing the switch.")


def do_combine(args):
    """Run "combine" sub-command"""

    check_deprecated_parameters(args)

    dir_containers = os.path.abspath(args.bundle_directory)
    if not os.path.exists(dir_containers):
        raise PathNotExistError(f"bundle directory {dir_containers} does not exist")

    image_dir = check_valid_tezi_image(args.image_directory)

    output_dir = os.path.abspath(args.output_directory)

    tezi_props_args = {
        "name": args.image_name,
        "description": args.image_description,
        "accept_licence": args.image_accept_licence,
        "autoinstall": args.image_autoinstall,
        "autoreboot": args.image_autoreboot,
        "licence_file": args.licence_file,
        "release_notes_file": args.release_notes_file
    }

    combine.combine_image(image_dir, dir_containers, output_dir, tezi_props_args)
    set_output_ownership(output_dir)
    log.info("Successfully created a TorizonCore image with Docker Containers"
             f" preprovisioned in {args.output_directory}")


def init_parser(subparsers):
    """Initialize argument parser"""

    subparser = subparsers.add_parser(
        "combine",
        help=("Combines a container bundle with a specified Toradex Easy "
              "Installer image."),
        epilog=("NOTE: the switches --image-directory and --output_directory "
                "have been removed."))

    add_bundle_directory_argument(subparser)

    subparser.add_argument(
        dest="image_directory",
        metavar="IMAGE_DIRECTORY",
        help=("Path to TorizonCore Toradex Easy Installer source image, "
              "which needs to be updated with docker bundle."))

    subparser.add_argument(
        dest="output_directory",
        metavar="OUTPUT_DIRECTORY",
        help=("Path to combined TorizonCore Toradex Easy Installer image, "
              "which needs to be updated with docker bundle."))

    # Temporary solution to provide better messages (DEPRECATED since 2021-05-17).
    subparser.add_argument(
        "--image-directory",
        dest="image_directory_compat",
        action="store_true",
        default=False,
        help=argparse.SUPPRESS)

    # Temporary solution to provide better messages (DEPRECATED since 2021-05-17).
    subparser.add_argument(
        "--output-directory",
        dest="output_directory_compat",
        action="store_true",
        default=False,
        help=argparse.SUPPRESS)

    add_common_image_arguments(subparser, argparse)

    subparser.set_defaults(func=do_combine)
