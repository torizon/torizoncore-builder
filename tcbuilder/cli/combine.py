"""Combine CLI frontend

Create Toradex Easy Installer image of TorizonCore with bundled Docker
container(s) from the "bundle" command.
"""

import os
import logging
from tcbuilder.backend.common import (add_common_image_arguments,
                                      add_bundle_directory_argument)
from tcbuilder.backend import combine
from tcbuilder.errors import PathNotExistError


def combine_image(args):
    """combine sub-command"""

    log = logging.getLogger("torizon." + __name__)

    dir_containers = os.path.abspath(args.bundle_directory)
    if not os.path.exists(dir_containers):
        raise PathNotExistError(f"bundle directory {dir_containers} does not exist")

    image_dir = os.path.abspath(args.image_directory)
    if not os.path.exists(image_dir):
        raise PathNotExistError(f"Source image directory {image_dir} does not exist")

    output_dir = os.path.abspath(args.output_directory)

    combine.combine_image(image_dir, dir_containers, output_dir, args.image_name,
                          args.image_description, args.licence_file,
                          args.release_notes_file)
    log.info(f"Successfully created a TorizonCore image with Docker Containers"
             f" preprovisioned in {args.output_directory}")


def init_parser(subparsers):
    """Initialize argument parser"""

    subparser = subparsers.add_parser(
        "combine",
        help="Combines a container bundle with a specified Toradex Easy "
             "Installer image.")

    add_bundle_directory_argument(subparser)

    subparser.add_argument(
        "--image-directory",
        dest="image_directory",
        required=True,
        help="Path to TorizonCore Toradex Easy Installer source image, "
             "which needs to be updated with docker bundle.")

    subparser.add_argument(
        "--output-directory",
        dest="output_directory",
        required=True,
        help="Path to combined TorizonCore Toradex Easy Installer image, "
             "which needs to be updated with docker bundle.")

    add_common_image_arguments(subparser)

    subparser.set_defaults(func=combine_image)
