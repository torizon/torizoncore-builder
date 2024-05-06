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
                                      set_output_ownership,
                                      DEFAULT_RAW_ROOTFS_LABEL)

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
        raise PathNotExistError(f"bundle directory {args.bundle_directory} does not exist")


    if args.output_path is not None:
        output_path = os.path.abspath(args.output_path)
    else:
        output_path = None

    image_path = os.path.abspath(args.image_path)

    # If raw image:
    if (not os.path.isdir(image_path) and
            (args.image_path.lower().endswith(".wic") or
             args.image_path.lower().endswith(".img"))):

        combine.combine_raw_image(image_path, dir_containers, output_path, args.raw_rootfs_label)

    # If TEZI image:
    else:
        tezi_image_dir = check_valid_tezi_image(args.image_path)


        tezi_props_args = {
            "name": args.image_name,
            "description": args.image_description,
            "accept_licence": args.image_accept_licence,
            "autoinstall": args.image_autoinstall,
            "autoreboot": args.image_autoreboot,
            "licence_file": args.licence_file,
            "release_notes_file": args.release_notes_file
        }

        combine.combine_tezi_image(tezi_image_dir, dir_containers, output_path, tezi_props_args)

    if output_path is not None:
        set_output_ownership(output_path)
        log.info("Successfully created a Torizon OS image with "
                 "Docker Containers preprovisioned")
    else:
        set_output_ownership(image_path)
        log.info("Successfully updated source Torizon OS image with "
                 "Docker Containers preprovisioned.")


def init_parser(subparsers):
    """Initialize argument parser"""

    subparser = subparsers.add_parser(
        "combine",
        help=("Combines a container bundle with a specified Torizon OS image "
              "(Toradex Easy Installer or raw/WIC)"),
        epilog=("NOTE: the switches --image-directory and --output_directory "
                "have been removed."),
        allow_abbrev=False)

    add_bundle_directory_argument(subparser)

    subparser.add_argument(
        dest="image_path",
        metavar="IMAGE_PATH",
        help="Path of Torizon OS image to be updated with docker bundle.")

    subparser.add_argument(
        dest="output_path",
        metavar="OUTPUT_PATH",
        help="Path of resulting Torizon OS image updated with docker bundle.")

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

    subparser.add_argument(
        "--raw-rootfs-label", dest="raw_rootfs_label", metavar="LABEL",
        help="rootfs filesystem label of source WIC/raw image. "
             f"(default: {DEFAULT_RAW_ROOTFS_LABEL})",
        default=DEFAULT_RAW_ROOTFS_LABEL)

    add_common_image_arguments(subparser, argparse)

    subparser.set_defaults(func=do_combine)
