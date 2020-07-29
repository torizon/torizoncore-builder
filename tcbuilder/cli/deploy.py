import os
import sys
import glob
import logging
import json
import subprocess
import tezi.utils
import re
from tcbuilder.backend import deploy
from tcbuilder.backend import ostree

def progress_update(asyncprogress, user_data=None):
    """ Update progress status

        self:
            asyncprogress (OSTree.AsyncProgress) - object with progress information
            user_data - additional data (not used)
    """
    bytes_transferred = asyncprogress.get_uint64("bytes-transferred")

    print("Pull: %s bytes transferred.\r", str(bytes_transferred))


def deploy_image(args):
    output_dir = os.path.abspath(args.output_directory)
    storage_dir = os.path.abspath(args.storage_directory)
    tezi_dir = os.path.join(storage_dir, "tezi")
    if args.sysroot_directory is None:
        src_sysroot_dir = os.path.join(storage_dir, "sysroot")
    else:
        src_sysroot_dir = os.path.abspath(args.sysroot_directory)

    dst_sysroot_dir = os.path.abspath(args.deploy_sysroot_directory)

    if os.path.exists(output_dir):
        print("Output directory must not exist!", file=sys.stderr)
        return

    if not os.path.exists(dst_sysroot_dir):
        print("Deploy sysroot directory does not exist", file=sys.stderr)
        return

    # Currently we use the OSTree from the unpacked Tezi rootfs as source
    src_sysroot = ostree.load_sysroot(src_sysroot_dir)
    ref, kargs = ostree.get_ref_from_sysroot(src_sysroot)
    metadata, subject, body = ostree.get_metadata_from_ref(src_sysroot.repo(), ref)

    print("Using unpacked Toradex Easy Installer image as base:")
    print("  Commit ref: {}".format(ref))
    print("  TorizonCore Version: {}".format(metadata['version']))
    print("  Kernel arguments: {}".format(kargs))
    print()

    if args.ref is not None:
        ref = args.ref
    print("Deploying commit ref: {}".format(ref))

    # Create a new sysroot for our deployment
    sysroot = deploy.create_sysroot(dst_sysroot_dir)

    repo = sysroot.repo()

    print("Pulling OSTree with ref {0} from local repository...".format(ref))
    src_ostree_dir = os.path.join(src_sysroot_dir, "ostree/repo")
    ostree.pull_local_ref(repo, src_ostree_dir, ref, remote="torizon")
    print("Pulling done.")

    print("Deploying OSTree with ref {0}".format(ref))
    # Remove old ostree= kernel argument
    newkargs = re.sub("ostree=[^\s]*", "", kargs)
    deploy.deploy_rootfs(sysroot, ref, "torizon", newkargs)
    print("Deploying done.")

    print("Copy rootdirs such as /home from original deployment.")
    deploy.copy_home_from_old_sysroot(src_sysroot, sysroot)

    print("Packing rootfs...")
    deploy.copy_tezi_image(tezi_dir, output_dir)
    deploy.pack_rootfs_for_tezi(dst_sysroot_dir, output_dir)
    print("Packing rootfs done.")


def init_parser(subparsers):
    subparser = subparsers.add_parser("deploy", help="""\
    Deploy the current image as a Toradex Easy Installer image""")
    subparser.add_argument("--output-directory", dest="output_directory",
                        help="""Output path for TorizonCore Toradex Easy Installer image.""",
                        required=True)
    subparser.add_argument("--ref", dest="ref",
                        help="""OSTree reference to deploy.""")
    subparser.add_argument("--sysroot-directory", dest="sysroot_directory",
                        help="""Path to source sysroot storage.""")
    subparser.add_argument("--deploy-sysroot-directory", dest="deploy_sysroot_directory",
                        help="""Work directory to store the intermittent deployment sysroot.
                        NOTE: OSTree need to be able to write extended
                        attributes in this directory. This seems to only
                        reliably work when using a Docker volume!
                        """,
                        default="/deploy")

    subparser.set_defaults(func=deploy_image)


