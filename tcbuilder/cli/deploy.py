"""
CLI handling for deploy subcommand
"""
import argparse
import os

from tcbuilder.backend import deploy as dbe
from tcbuilder.backend import common
from tcbuilder.backend import combine as cbe
from tcbuilder.errors import (
    InvalidArgumentError,
    InvalidStateError,
    PathNotExistError,
    InvalidDataError,
)

DEFAULT_DEPLOY_DIR = "/deploy"
DEFAULT_OUTPUT_WIC_IMAGE = "tcb_common_torizon_os.wic"
DEFAULT_WIC_ROOTFS_LABEL = "otaroot"

def progress_update(asyncprogress, _user_data=None):
    """ Update progress status

        self:
            asyncprogress (OSTree.AsyncProgress) - object with progress information
            user_data - additional data (not used)
    """
    bytes_transferred = asyncprogress.get_uint64("bytes-transferred")

    print("Pull: %s bytes transferred.\r", str(bytes_transferred))


def deploy_tezi_image(ostree_ref, output_dir, storage_dir, deploy_sysroot_dir,
                      tezi_props=None):

    common.images_unpack_executed(storage_dir)
    if common.unpacked_image_type(storage_dir) == "wic":
        raise InvalidDataError("Current unpacked image is not a Toradex Easy Installer image. "
                               "Aborting.")

    output_dir_ = os.path.abspath(output_dir)

    storage_dir_ = os.path.abspath(storage_dir)
    tezi_dir = os.path.join(storage_dir_, "tezi")

    common.check_licence_acceptance(tezi_dir, tezi_props)

    src_sysroot_dir = os.path.join(storage_dir_, "sysroot")
    src_ostree_archive_dir = os.path.join(storage_dir_, "ostree-archive")

    dst_sysroot_dir_ = os.path.abspath(deploy_sysroot_dir)

    if os.path.exists(output_dir_):
        raise InvalidStateError(f"Output directory {output_dir_} must not exist.")

    if not os.path.exists(dst_sysroot_dir_):
        raise PathNotExistError(f"Deploy sysroot directory {dst_sysroot_dir_} does not exist.")

    dbe.deploy_tezi_image(tezi_dir, src_sysroot_dir, src_ostree_archive_dir,
                          output_dir_, dst_sysroot_dir_, ostree_ref)

    if tezi_props and any(prop is not None for prop in tezi_props):
        combine_params = {
            "image_dir": output_dir_,
            "bundle_dir": None,
            "output_directory": None,
            "tezi_props": tezi_props,
        }
        # Change output directory in place.
        # FIXME: This is not really combining an image - consider refactoring.
        cbe.combine_image(**combine_params)

    common.set_output_ownership(output_dir_)

def deploy_wic_image(ostree_ref, base_wic_img, output_wic_img, storage_dir,
                     deploy_sysroot_dir, rootfs_label):

    common.images_unpack_executed(storage_dir)
    if common.unpacked_image_type(storage_dir) == "tezi":
        raise InvalidDataError("Current unpacked image is not a WIC image. Aborting.")

    if os.path.isdir(output_wic_img):
        output_wic_img = os.path.join(output_wic_img, DEFAULT_OUTPUT_WIC_IMAGE)

    output_wic_img_ = os.path.abspath(output_wic_img)
    storage_dir_ = os.path.abspath(storage_dir)

    src_sysroot_dir = os.path.join(storage_dir_, "sysroot")
    src_ostree_archive_dir = os.path.join(storage_dir_, "ostree-archive")

    dst_sysroot_dir_ = os.path.abspath(deploy_sysroot_dir)

    if os.path.exists(output_wic_img_):
        raise InvalidStateError(f"{output_wic_img} already exists. Aborting.")

    if not os.path.exists(dst_sysroot_dir_):
        raise PathNotExistError(f"Deploy sysroot directory {dst_sysroot_dir_} does not exist.")

    dbe.deploy_wic_image(base_wic_img, src_sysroot_dir, src_ostree_archive_dir,
                         output_wic_img_, dst_sysroot_dir_, rootfs_label, ostree_ref)


def do_deploy_tezi_image(args):

    tezi_props_args = {
        "name": args.image_name,
        "description": args.image_description,
        "accept_licence": args.image_accept_licence,
        "autoinstall": args.image_autoinstall,
        "autoreboot": args.image_autoreboot,
        "licence_file": args.licence_file,
        "release_notes_file": args.release_notes_file
    }

    deploy_tezi_image(ostree_ref=args.ref,
                      output_dir=args.output_directory,
                      storage_dir=args.storage_directory,
                      deploy_sysroot_dir=args.deploy_sysroot_directory,
                      tezi_props=tezi_props_args)


def do_deploy_wic_image(args):

    deploy_wic_image(ostree_ref=args.ref,
                     base_wic_img=args.base_wic_image,
                     output_wic_img=args.output_wic_image,
                     storage_dir=args.storage_directory,
                     deploy_sysroot_dir=args.deploy_sysroot_directory,
                     rootfs_label=args.wic_rootfs_label)


def deploy_ostree_remote(storage_dir, remote_host, remote_username,
                         remote_password, remote_port, mdns_source, ref, reboot):

    storage_dir_ = os.path.abspath(storage_dir)
    common.images_unpack_executed(storage_dir_)

    src_ostree_archive_dir = os.path.join(storage_dir_, "ostree-archive")

    dbe.deploy_ostree_remote(remote_host, remote_username, remote_password,
                             remote_port, mdns_source, src_ostree_archive_dir,
                             ref, reboot)


def do_deploy_ostree_remote(args):

    deploy_ostree_remote(storage_dir=args.storage_directory,
                         remote_host=args.remote_host,
                         remote_username=args.remote_username,
                         remote_password=args.remote_password,
                         remote_port=args.remote_port,
                         mdns_source=args.mdns_source,
                         ref=args.ref,
                         reboot=args.reboot)


def do_deploy(args):

    if (args.output_directory and args.base_wic_image and args.remote_host):
        raise InvalidArgumentError(
            "--output-directory, --base-wic and --remote-host are "
            "mutually exclusive. Aborting.")

    if (args.output_directory and args.base_wic_image):
        raise InvalidArgumentError(
            "--output-directory and --base-wic are "
            "mutually exclusive. Aborting.")

    if (args.output_directory and args.remote_host):
        raise InvalidArgumentError(
            "--output-directory and --remote-host are "
            "mutually exclusive. Aborting.")

    if (args.base_wic_image and args.remote_host):
        raise InvalidArgumentError(
            "--base-wic and --remote-host are "
            "mutually exclusive. Aborting.")

    if args.output_directory is not None:
        do_deploy_tezi_image(args)
    elif args.base_wic_image is not None:
        do_deploy_wic_image(args)
    elif args.remote_host is not None:
        do_deploy_ostree_remote(args)
    else:
        raise InvalidArgumentError(
            "One of the following arguments is required: --output-directory, "
            "--base-wic, --remote-host")


def init_parser(subparsers):
    subparser = subparsers.add_parser(
        "deploy",
        help="Deploy the current image as a Toradex Easy Installer image.",
        allow_abbrev=False)

    subparser.add_argument("--output-directory", dest="output_directory",
                           help="Output path for TorizonCore Toradex Easy Installer image.")

    subparser.add_argument("--remote-host", dest="remote_host",
                           help="Remote host machine to deploy to.")

    common.add_ssh_arguments(subparser)

    subparser.add_argument("--mdns-source", dest="mdns_source",
                           help=("Use the given IP address as mDNS source. "
                                 "This is useful when multiple interfaces are used, and "
                                 "mDNS multicast requests are sent out the wrong "
                                 "network interface."))

    subparser.add_argument("--reboot", dest="reboot", action='store_true',
                           help="Reboot machine after deploying",
                           default=False)

    subparser.add_argument(metavar="REF", nargs="?", dest="ref",
                           help="OSTree reference to deploy.")

    subparser.add_argument("--deploy-sysroot-directory", dest="deploy_sysroot_directory",
                           help=("Work directory to store the intermittent deployment sysroot. "
                                 "NOTE: OSTree need to be able to write extended "
                                 "attributes in this directory. This seems to only "
                                 "reliably work when using a Docker volume!"),
                           default=DEFAULT_DEPLOY_DIR)

    subparser.add_argument("--base-wic", dest="base_wic_image", metavar="BASE",
                           help="Base image that the deployment will be based on i.e. "
                                "the .wic file used in the \'images unpack\' command.")

    subparser.add_argument("--wic-rootfs-label", dest="wic_rootfs_label", metavar="LABEL",
                           help="rootfs filesystem label of base WIC image. "
                                f"(default: {DEFAULT_WIC_ROOTFS_LABEL}) ",
                           default=DEFAULT_WIC_ROOTFS_LABEL)

    subparser.add_argument("--output-wic", dest="output_wic_image", metavar="OUT",
                           help="Output path for the image to be deployed.",
                           default=DEFAULT_OUTPUT_WIC_IMAGE)

    common.add_common_image_arguments(subparser, argparse)

    subparser.set_defaults(func=do_deploy)
