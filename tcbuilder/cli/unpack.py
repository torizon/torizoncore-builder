"""Unpack sub-command CLI handling

The unpack sub-command take a (unzipped!) TorizonCore Toradex Easy
Installer image and unpacks the rootfs so the TorizonCore Builder
can customize the image. This gives access to the rootfs' OSTree
sysroot (deployment) and OSTree repository.
"""

import os
import shutil

from tcbuilder.backend import unpack
from tcbuilder.errors import UserAbortError




def unpack_subcommand(args):
    """Run \"unpack\" subcommand"""

    image_dir = os.path.abspath(args.image_directory)
    storage_dir = os.path.abspath(args.storage_directory)
    tezi_dir = os.path.join(storage_dir, "tezi")
    src_sysroot_dir = os.path.join(storage_dir, "sysroot")
    src_ostree_archive_dir = os.path.join(storage_dir, "ostree-archive")

    if not os.path.exists(storage_dir):
        os.mkdir(storage_dir)

    if os.path.exists(tezi_dir) or os.path.exists(src_sysroot_dir):
        ans = input("Storage not empty. Delete current image before continuing? [y/N] ")
        if ans.lower() != "y":
            raise UserAbortError()
        if os.path.exists(tezi_dir):
            shutil.rmtree(tezi_dir)

        if os.path.exists(src_sysroot_dir):
            shutil.rmtree(src_sysroot_dir)

    unpack.import_local_image(image_dir, tezi_dir, src_sysroot_dir, src_ostree_archive_dir)



def init_parser(subparsers):
    """Initialize argument parser"""
    subparser = subparsers.add_parser("unpack", help="""\
    Unpack a specified Toradex Easy Installer image so it can be modified with
    union subcommand.
    """)
    subparser.add_argument("--image-directory", dest="image_directory",
                           help="""Path to TorizonCore Toradex Easy Installer source image.""",
                           required=True)

    subparser.set_defaults(func=unpack_subcommand)
