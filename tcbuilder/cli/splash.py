import os
import sys
import shutil
import logging
import traceback
from tcbuilder.errors import OperationFailureError
from tcbuilder.errors import TorizonCoreBuilderError
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
        log.error("unable to find splash image")
        return

    if args.sysroot_directory is None:
        sysroot_dir = os.path.join(storage_dir, "sysroot")
    else:
        sysroot_dir = os.path.abspath(args.sysroot_directory)

    src_ostree_archive_dir = os.path.join(storage_dir, "ostree-archive")

    try:
        splash.create_splash_initramfs(work_dir, image, sysroot_dir, src_ostree_archive_dir)
        log.info("splash screen merged to initramfs")
    except TorizonCoreBuilderError as ex:
        log.error(ex.msg)  # msg from all kinds of Exceptions
        if ex.det is not None:
            log.info(ex.det)  # more elaborative message
        log.debug(traceback.format_exc())  # full traceback to be shown for debugging only


def init_parser(subparsers):
    subparser = subparsers.add_parser("splash",
                                      help="""change splash screen""")

    subparser.add_argument("--image", dest="image",
                           help="""Path and name of splash screen image""",
                           required=True)
    subparser.add_argument("--work-dir", dest="work_dir",
                           help="""Working directory""")
    subparser.add_argument("--sysroot-directory", dest="sysroot_directory",
                           help="""Path to source sysroot storage.""")

    subparser.set_defaults(func=splash_subcommand)
