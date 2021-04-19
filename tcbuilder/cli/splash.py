import os
import shutil
import logging

from tcbuilder.errors import PathNotExistError
from tcbuilder.backend import splash as sbe

log = logging.getLogger("torizon." + __name__)  # use name hierarchy for "main" to be the parent

def splash(image, storage_dir, work_dir=None):
    storage_dir_ = os.path.abspath(storage_dir)

    work_dir_ = work_dir
    if work_dir_ is None:
        work_dir_ = os.path.join(storage_dir_, "splash")
        if os.path.exists(work_dir_):
            shutil.rmtree(work_dir_)
        os.mkdir(work_dir_)

    image_ = os.path.abspath(image)
    if not os.path.exists(image_):
        raise PathNotExistError(f"Unable to find splash image {image_}")

    src_ostree_archive_dir = os.path.join(storage_dir_, "ostree-archive")

    sbe.create_splash_initramfs(work_dir_, image_, src_ostree_archive_dir)
    log.info("splash screen merged to initramfs")


def do_splash(args):
    splash(args.image, args.storage_directory, work_dir=args.work_dir)


def init_parser(subparsers):
    subparser = subparsers.add_parser("splash",
                                      help="""change splash screen""")

    subparser.add_argument("--image", dest="image",
                           help="""Path and name of splash screen image""",
                           required=True)
    subparser.add_argument("--work-dir", dest="work_dir",
                           help="""Working directory""")

    subparser.set_defaults(func=do_splash)
