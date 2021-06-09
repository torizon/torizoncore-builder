import os

from tcbuilder.backend import deploy as dbe
from tcbuilder.backend import common
from tcbuilder.backend import combine as cbe
from tcbuilder.errors import InvalidArgumentError, InvalidStateError, PathNotExistError

DEFAULT_DEPLOY_DIR = "/deploy"


def progress_update(asyncprogress, _user_data=None):
    """ Update progress status

        self:
            asyncprogress (OSTree.AsyncProgress) - object with progress information
            user_data - additional data (not used)
    """
    bytes_transferred = asyncprogress.get_uint64("bytes-transferred")

    print("Pull: %s bytes transferred.\r", str(bytes_transferred))


def deploy_tezi_image(ostree_ref, output_dir, storage_dir, deploy_sysroot_dir,
                      image_name=None, image_description=None,
                      licence_file=None, release_notes_file=None):

    output_dir_ = os.path.abspath(output_dir)

    storage_dir_ = os.path.abspath(storage_dir)
    tezi_dir = os.path.join(storage_dir_, "tezi")
    src_sysroot_dir = os.path.join(storage_dir_, "sysroot")
    src_ostree_archive_dir = os.path.join(storage_dir_, "ostree-archive")

    dst_sysroot_dir_ = os.path.abspath(deploy_sysroot_dir)

    if os.path.exists(output_dir_):
        raise InvalidStateError(f"Output directory {output_dir_} must not exist.")

    if not os.path.exists(dst_sysroot_dir_):
        raise PathNotExistError(f"Deploy sysroot directory {dst_sysroot_dir_} does not exist.")

    dbe.deploy_tezi_image(tezi_dir, src_sysroot_dir, src_ostree_archive_dir,
                          output_dir_, dst_sysroot_dir_, ostree_ref)

    comb_args = [image_name, image_description, licence_file, release_notes_file]

    if any(arg is not None for arg in comb_args):
        # Change output directory in place.
        cbe.combine_image(image_dir=output_dir_,
                          bundle_dir=None,
                          output_directory=None,
                          image_name=image_name,
                          image_description=image_description,
                          licence_file=licence_file,
                          release_notes_file=release_notes_file)


def do_deploy_tezi_image(args):

    deploy_tezi_image(ostree_ref=args.ref,
                      output_dir=args.output_directory,
                      storage_dir=args.storage_directory,
                      deploy_sysroot_dir=args.deploy_sysroot_directory,
                      image_name=args.image_name,
                      image_description=args.image_description,
                      licence_file=args.licence_file,
                      release_notes_file=args.release_notes_file)


def do_deploy_ostree_remote(args):
    storage_dir = os.path.abspath(args.storage_directory)
    src_ostree_archive_dir = os.path.join(storage_dir, "ostree-archive")

    dbe.deploy_ostree_remote(args.remote_host, args.remote_username,
                             args.remote_password, args.mdns_source,
                             src_ostree_archive_dir, args.ref, args.reboot)

def do_deploy(args):
    if args.output_directory is not None:
        do_deploy_tezi_image(args)
    elif args.remote_host is not None:
        do_deploy_ostree_remote(args)
    else:
        raise InvalidArgumentError(
            "One of the following arguments is required: --output-directory, --remote-host")


def init_parser(subparsers):
    subparser = subparsers.add_parser("deploy", help="""\
    Deploy the current image as a Toradex Easy Installer image""")
    subparser.add_argument("--output-directory", dest="output_directory",
                           help="""Output path for TorizonCore Toradex Easy Installer image.""")

    subparser.add_argument("--remote-host", dest="remote_host",
                           help="""Remote host machine to deploy to.""")
    common.add_username_password_arguments(subparser)
    subparser.add_argument("--mdns-source", dest="mdns_source",
                           help="""Use the given IP address as mDNS source.
                           This is useful when multiple interfaces are used, and
                           mDNS multicast requests are sent out the wrong
                           network interface.""")
    subparser.add_argument("--reboot", dest="reboot", action='store_true',
                           help="""Reboot machine after deploying""",
                           default=False)

    subparser.add_argument(metavar="REF", nargs="?", dest="ref",
                           help="""OSTree reference to deploy.""")
    subparser.add_argument("--deploy-sysroot-directory", dest="deploy_sysroot_directory",
                           help="""Work directory to store the intermittent deployment sysroot.
                           NOTE: OSTree need to be able to write extended
                           attributes in this directory. This seems to only
                           reliably work when using a Docker volume!
                           """,
                           default=DEFAULT_DEPLOY_DIR)
    common.add_common_image_arguments(subparser)

    subparser.set_defaults(func=do_deploy)
