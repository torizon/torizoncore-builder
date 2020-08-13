import os
import re
import sys

from tcbuilder.backend import deploy, ostree


def progress_update(asyncprogress, _user_data=None):
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

    src_ostree_archive_dir = os.path.join(storage_dir, "ostree-archive")

    if os.path.exists(output_dir):
        print("Output directory must not exist!", file=sys.stderr)
        return

    if not os.path.exists(dst_sysroot_dir):
        print("Deploy sysroot directory does not exist", file=sys.stderr)
        return

    # Currently we use the sysroot from the unpacked Tezi rootfs as source
    # for kargs, /home directories
    src_sysroot = ostree.load_sysroot(src_sysroot_dir)
    csum, kargs = ostree.get_deployment_info_from_sysroot(src_sysroot)
    metadata, _subject, _body = ostree.get_metadata_from_ref(src_sysroot.repo(), csum)

    print("Using unpacked Toradex Easy Installer image as base:")
    print("  Commit checksum: {}".format(csum))
    print("  TorizonCore Version: {}".format(metadata['version']))
    print("  Kernel arguments: {}".format(kargs))
    print()

    ref = args.ref
    # It seems the customer did not pass a reference, deploy the original commit
    # (probably not that useful in practise, but useful to test the workflow)
    if ref is None:
        ref = ostree.OSTREE_BASE_REF
    print("Deploying commit ref: {}".format(ref))

    # Create a new sysroot for our deployment
    sysroot = deploy.create_sysroot(dst_sysroot_dir)

    repo = sysroot.repo()

    print("Pulling OSTree with ref {0} from local archive repository...".format(ref))
    ostree.pull_local_ref(repo, src_ostree_archive_dir, ref, remote="torizon")
    print("Pulling done.")

    print("Deploying OSTree with ref {0}".format(ref))
    # Remove old ostree= kernel argument
    newkargs = re.sub(r"ostree=[^\s]*", "", kargs)
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
    subparser.add_argument(metavar="REF", nargs="?", dest="ref",
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

