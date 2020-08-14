import os
import sys

from tcbuilder.backend import deploy


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
    src_sysroot_dir = os.path.join(storage_dir, "sysroot")
    src_ostree_archive_dir = os.path.join(storage_dir, "ostree-archive")

    dst_sysroot_dir = os.path.abspath(args.deploy_sysroot_directory)

    if os.path.exists(output_dir):
        print("Output directory must not exist!", file=sys.stderr)
        return

    if not os.path.exists(dst_sysroot_dir):
        print("Deploy sysroot directory does not exist", file=sys.stderr)
        return

    deploy.deploy_tezi_image(tezi_dir, src_sysroot_dir, src_ostree_archive_dir,
                             output_dir, dst_sysroot_dir, args.ref)


def init_parser(subparsers):
    subparser = subparsers.add_parser("deploy", help="""\
    Deploy the current image as a Toradex Easy Installer image""")
    subparser.add_argument("--output-directory", dest="output_directory",
                        help="""Output path for TorizonCore Toradex Easy Installer image.""",
                        required=True)
    subparser.add_argument(metavar="REF", nargs="?", dest="ref",
                        help="""OSTree reference to deploy.""")
    subparser.add_argument("--deploy-sysroot-directory", dest="deploy_sysroot_directory",
                        help="""Work directory to store the intermittent deployment sysroot.
                        NOTE: OSTree need to be able to write extended
                        attributes in this directory. This seems to only
                        reliably work when using a Docker volume!
                        """,
                        default="/deploy")

    subparser.set_defaults(func=deploy_image)

