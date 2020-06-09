import os
import sys
import logging
import shutil
import tezi.utils
from tcbuilder.backend import unpack
from tcbuilder.backend import ostree

def unpack_subcommand(args):
    image_dir = os.path.abspath(args.image_directory)
    storage_dir = os.path.abspath(args.storage_directory)
    tezi_dir = os.path.join(storage_dir, "tezi")
    src_sysroot_dir = os.path.join(storage_dir, "sysroot")

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
        ref, kargs = ostree.get_ref_from_sysroot(src_sysroot)
        metadata, subject, body = ostree.get_metadata_from_ref(src_sysroot.repo(), ref)

        print("Unpacked OSTree from oradex Easy Installer image:")
        print("Commit ref: {}".format(ref))
        print("TorizonCore Version: {}".format(metadata['version']))
        print()

    except Exception as ex:
        print("Failed to unpack: " + str(ex), file=sys.stderr)

def init_parser(subparsers):
    subparser = subparsers.add_parser("unpack", help="""\
    Unpack a specified Toradex Easy Installer image so it can be modified with
    union subcommand.
    """)
    subparser.add_argument("--image-directory", dest="image_directory",
                        help="""Path to TorizonCore Toradex Easy Installer source image.""",
                        required=True)
    subparser.add_argument("--storage-directory", dest="storage_directory",
                        help="""Path to internal storage. Must be a file system
                        capable of carring Linux file system metadata (Unnix
                        file permissions and xattr).""",
                        default="/storage")

    subparser.set_defaults(func=unpack_subcommand)


