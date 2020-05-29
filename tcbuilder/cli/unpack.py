import os
import sys
import glob
import logging
import json
import subprocess
import tezi.utils
from tcbuilder.backend import unpack

def unpack_subcommand(args):
    image_dir = os.path.abspath(args.image_directory)
    ostree_dir = os.path.abspath(args.ostree_directory)

    try:
        if not os.path.exists(ostree_dir):
            os.mkdir(ostree_dir)

        elif len(os.listdir(ostree_dir)) > 0:
            ans = input("Target directory not empty. Delete before continuing? [y/N] ")
            if ans.lower() != "y":
                return

        print("Unpacking TorizonCore Toradex Easy Installer image.")
        unpack.unpack_local_image(image_dir, ostree_dir)

    except Exception as ex:
        print("Faild to unpack: " + str(ex), file=sys.stderr)

def init_parser(subparsers):
    subparser = subparsers.add_parser("unpack", help="""\
    Unpack a specified Toradex Easy Installer image so it can be modified with
    union subcommand.
    """)
    subparser.add_argument("--image-directory", dest="image_directory",
                        help="""Path to TorizonCore Toradex Easy Installer source image.""",
                        required=True)
    subparser.add_argument("--ostree-directory", dest="ostree_directory",
                        help="""Path to OSTree storage.""",
                        default="/storage")

    subparser.set_defaults(func=unpack_subcommand)


