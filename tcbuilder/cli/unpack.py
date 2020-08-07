"""Unpack sub-command CLI handling

The unpack sub-command take a (unzipped!) TorizonCore Toradex Easy
Installer image and unpacks the rootfs so the TorizonCore Builder
can customize the image. This gives access to the rootfs' OSTree
sysroot (deployment) and OSTree repository.
"""

import logging
import os
import shutil
import traceback

from tcbuilder.backend import ostree, unpack
from tcbuilder.errors import TorizonCoreBuilderError


def unpack_subcommand(args):
    """Run \"unpack\" subcommand"""
    log = logging.getLogger("torizon." + __name__)  # use name hierarchy for "main" to be the parent

    image_dir = os.path.abspath(args.image_directory)
    storage_dir = os.path.abspath(args.storage_directory)
    tezi_dir = os.path.join(storage_dir, "tezi")

    if args.sysroot_directory is None:
        src_sysroot_dir = os.path.join(storage_dir, "sysroot")
    else:
        src_sysroot_dir = os.path.abspath(args.sysroot_directory)

    src_ostree_archive_dir = os.path.join(storage_dir, "ostree-archive")

    try:
        if not os.path.exists(storage_dir):
            os.mkdir(storage_dir)

        if os.path.exists(tezi_dir) or os.path.exists(src_sysroot_dir):
            ans = input("Storage not empty. Delete current image before continuing? [y/N] ")
            if ans.lower() != "y":
                return
            if os.path.exists(tezi_dir):
                shutil.rmtree(tezi_dir)

            if os.path.exists(src_sysroot_dir):
                shutil.rmtree(src_sysroot_dir)

        os.mkdir(src_sysroot_dir)

        print("Copying Toradex Easy Installer image.")
        shutil.copytree(image_dir, tezi_dir)

        print("Unpacking TorizonCore Toradex Easy Installer image.")
        unpack.unpack_local_image(tezi_dir, src_sysroot_dir)

        src_sysroot = ostree.load_sysroot(src_sysroot_dir)
        csum, _ = ostree.get_deployment_info_from_sysroot(src_sysroot)

        print("Importing OSTree revision {0} from local repository...".format(csum))
        repo = ostree.create_ostree(src_ostree_archive_dir)
        src_ostree_dir = os.path.join(src_sysroot_dir, "ostree/repo")
        ostree.pull_local_ref(repo, src_ostree_dir, csum, remote="torizon")
        metadata, _, _ = ostree.get_metadata_from_ref(src_sysroot.repo(), csum)

        print("Unpacked OSTree from Toradex Easy Installer image:")
        print("  Commit checksum: {}".format(csum))
        print("  TorizonCore Version: {}".format(metadata['version']))
        print()

    except TorizonCoreBuilderError as ex:
        log.error(ex.msg)  # msg from all kinds of Exceptions
        if ex.det is not None:
            log.info(ex.det)  # more elaborative message
        log.debug(traceback.format_exc())  # full traceback to be shown for debugging only

def init_parser(subparsers):
    """Initialize argument parser"""
    subparser = subparsers.add_parser("unpack", help="""\
    Unpack a specified Toradex Easy Installer image so it can be modified with
    union subcommand.
    """)
    subparser.add_argument("--image-directory", dest="image_directory",
                           help="""Path to TorizonCore Toradex Easy Installer source image.""",
                           required=True)
    subparser.add_argument("--sysroot-directory", dest="sysroot_directory",
                           help="""Path to source sysroot storage.""")

    subparser.set_defaults(func=unpack_subcommand)
