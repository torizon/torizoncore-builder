import os
import shutil
import logging
from tcbuilder.errors import PathNotExistError
from tcbuilder.backend import splash


def splash_subcommand(args):
    log = logging.getLogger("torizon." + __name__)  # use name hierarchy for "main" to be the parent

    storage_dir = os.path.abspath(args.storage_directory)

    work_dir = ""
    if args.work_dir is not None:
        work_dir = args.work_dir
    else:
        work_dir = os.path.join(storage_dir, "splash")
        if os.path.exists(work_dir):
            shutil.rmtree(work_dir)
        os.mkdir(work_dir)

    image = os.path.abspath(args.image)
    if not os.path.exists(image):
        raise PathNotExistError(f"Unable to find splash image {image}")

    src_ostree_archive_dir = os.path.join(storage_dir, "ostree-archive")

    splash.create_splash_initramfs(work_dir, image, src_ostree_archive_dir)
    log.info("splash screen merged to initramfs")


def init_parser(subparsers):
    subparser = subparsers.add_parser("splash",
                                      help="""change splash screen""")

    subparser.add_argument("--image", dest="image",
                           help="""Path and name of splash screen image""",
                           required=True)
    subparser.add_argument("--work-dir", dest="work_dir",
                           help="""Working directory""")

    subparser.set_defaults(func=splash_subcommand)
