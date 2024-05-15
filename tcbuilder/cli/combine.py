"""Combine CLI frontend

Create Toradex Easy Installer image of TorizonCore with bundled Docker
container(s) from the "bundle" command.
"""

import os
import logging
import argparse

from tcbuilder.backend.common import (add_common_tezi_image_arguments,
                                      add_common_raw_image_arguments,
                                      add_bundle_directory_argument,
                                      check_valid_tezi_image,
                                      set_output_ownership,
                                      TEZI_PROP_TO_ARGNAME,
                                      RAW_PROP_TO_ARGNAME,
                                      RAW_PROP_DEFAULTS)

from tcbuilder.backend import combine
from tcbuilder.errors import (PathNotExistError,
                              InvalidArgumentError,
                              InvalidStateError)

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
        raise PathNotExistError(f"Bundle directory {args.bundle_directory} does not exist.")

    output_path = os.path.abspath(args.output_path)

    image_path = os.path.abspath(args.image_path)

    tezi_props_args = {
        "name": args.image_name,
        "description": args.image_description,
        "accept_licence": args.image_accept_licence,
        "autoinstall": args.image_autoinstall,
        "autoreboot": args.image_autoreboot,
        "licence_file": args.licence_file,
        "release_notes_file": args.release_notes_file
    }

    raw_props_args = {
        "raw_rootfs_label" : args.raw_rootfs_label
    }

    # If raw image:
    if (not os.path.isdir(image_path) and
            (args.image_path.lower().endswith(".wic") or
             args.image_path.lower().endswith(".img"))):

        if os.path.isdir(output_path):
            raise InvalidStateError(
                "Error: For raw images the output can't be a directory. Aborting.")

        # Check for tezi-specific args being set:
        for prop in tezi_props_args:
            if tezi_props_args[prop] is not None:
                log.warning(f"Warning: {TEZI_PROP_TO_ARGNAME[prop]} "
                            "is specific to Easy Installer images. Ignoring.")

        # Set default raw-specific args if they're not already set:
        for prop in raw_props_args:
            if raw_props_args[prop] is None:
                raw_props_args[prop] = RAW_PROP_DEFAULTS[prop]

        combine.combine_raw_image(image_path, dir_containers, output_path,
                                  raw_props_args["raw_rootfs_label"], args.force)

    # If TEZI image:
    else:

        if os.path.exists(output_path) and not os.path.isdir(output_path):
            raise InvalidStateError(
                "Error: For Easy Installer images the output can't be an "
                "existing file. Aborting.")

        # Check for raw-specific args being set:
        for prop in raw_props_args:
            if raw_props_args[prop] is not None:
                log.warning(f"Warning: {RAW_PROP_TO_ARGNAME[prop]} "
                            "is specific to raw images. Ignoring.")

        tezi_image_dir = check_valid_tezi_image(args.image_path)

        combine.combine_tezi_image(tezi_image_dir, dir_containers, output_path,
                                   tezi_props_args, args.force)

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

    subparser.add_argument(
        "--force", dest="force",
        default=False, action="store_true",
        help=("Force program output, overwriting any existing file/directory."))

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

    add_common_raw_image_arguments(subparser)

    add_common_tezi_image_arguments(subparser, argparse)

    subparser.set_defaults(func=do_combine)
