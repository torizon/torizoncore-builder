import os
import logging
from tcbuilder.backend.common import add_common_image_arguments
from tcbuilder.backend import combine
from tcbuilder.errors import PathNotExistError


def combine_image(args):
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
    log.info("Successfully created a TorizonCore image with Docker Containers "
                "preprovisioned in {}", args.output_directory)

def init_parser(subparsers):
    subparser = subparsers.add_parser("combine", help="""\
    Combines a container bundle with a specified Toradex Easy Installer image.
    """)
    subparser.add_argument("--image-directory", dest="image_directory",
                           help="""Path to TorizonCore Toradex Easy Installer source image, 
                        which needs to be updated with docker bundle.""",
                           required=True)
    subparser.add_argument("--output-directory", dest="output_directory",
                           help="""Path to combined TorizonCore Toradex Easy Installer image, 
                            which needs to be updated with docker bundle.""",
                           required=True)
    add_common_image_arguments(subparser)

    subparser.set_defaults(func=combine_image)
