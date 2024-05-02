"""
CLI handling for images subcommand
"""

import logging
import os
import shutil
import sys

from tcbuilder.backend import images, common
from tcbuilder.errors import UserAbortError, TorizonCoreBuilderError
from tezi.errors import TeziError

log = logging.getLogger("torizon." + __name__)

PROV_MODE_OFFLINE = "offline"
PROV_MODE_ONLINE = "online"
PROV_MODES = (PROV_MODE_OFFLINE, PROV_MODE_ONLINE)


def get_extra_dirs(storage_dir, main_dirs):
    """
    Get all directories names inside "storage" that should be removed when
    unpacking a new TEZI image but that are not included in the list of
    "keep directories" and the list of "main directories". At this time,
    only the "toolchain directory" should be kept between images unpack.

    :param storage_dir: Storage directory.
    :param main_dirs: List of main directories for the unpacking.
    :returns: A list of extra directories that should be removed.
    """

    # Directories that should be kept between images "unpacks"
    keep_dirs = [os.path.join(storage_dir, "toolchain")]

    extra_dirs = []

    for dirname in os.listdir(storage_dir):
        abs_dirname = os.path.join(storage_dir, dirname)
        if abs_dirname not in keep_dirs + main_dirs:
            extra_dirs.append(abs_dirname)

    return extra_dirs


def prepare_storage(storage_directory, remove_storage):
    """ Prepare Storage directory for unpacking"""

    storage_dir = os.path.abspath(storage_directory)

    if not os.path.exists(storage_dir):
        os.mkdir(storage_dir)

    # Main directories: will be cleared and returned by this function.
    main_dirs = [os.path.join(storage_dir, dirname)
                 for dirname in ("tezi", "sysroot", "ostree-archive")]

    # Extra directories: will be cleared but not returned.
    extra_dirs = get_extra_dirs(storage_dir, main_dirs)

    all_dirs = main_dirs + extra_dirs
    need_clearing = False
    for src_dir in all_dirs:
        if os.path.exists(src_dir):
            need_clearing = True
            break

    if need_clearing and not remove_storage:
        # Let's ask the user about that:
        ans = input("Storage not empty. Delete current image before continuing? [y/N] ")
        if ans.lower() != "y":
            raise UserAbortError()

    for src_dir in all_dirs:
        if os.path.exists(src_dir):
            shutil.rmtree(src_dir)

    return main_dirs


def do_images_download(args):
    """Run 'images download' subcommand"""

    r_ip = common.resolve_remote_host(args.remote_host, args.mdns_source)
    dir_list = prepare_storage(args.storage_directory, args.remove_storage)
    images.download_tezi(r_ip, args.remote_username, args.remote_password,
                         args.remote_port,
                         dir_list[0], dir_list[1], dir_list[2])


def do_images_provision(args):
    """Run 'images provision' subcommand"""

    # ---
    # Validate arguments:
    # ---
    if args.mode == PROV_MODE_OFFLINE:
        if not args.shared_data_file:
            log.error("Error: With offline provisioning, switch --shared-data must be passed.")
            sys.exit(1)
        if args.online_data:
            log.error("Error: With offline provisioning, switch --online-data cannot be passed.")
            sys.exit(1)

    elif args.mode == PROV_MODE_ONLINE:
        if not (args.shared_data_file and args.online_data):
            log.error("Error: With online provisioning, switches --shared-data "
                      "and --online-data must be passed.")
            sys.exit(1)

    else:
        assert False, "Unhandled provisioning mode"

    try:
        images.provision(
            input_dir=args.input_directory,
            output_dir=args.output_directory,
            shared_data=args.shared_data_file,
            online_data=args.online_data,
            force=args.force)

    except (TorizonCoreBuilderError, TeziError) as exc:
        log.error(f"Error: {str(exc)}")
        sys.exit(2)


def do_images_serve(args):
    """
    Wrapper for 'images serve' subcommand.
    """
    images.serve(args.images_directory)


def images_unpack(image_dir, storage_dir, raw_rootfs_label="",
                  remove_storage=False):
    """Main handler for the 'images unpack' subcommand"""

    image_dir = os.path.abspath(image_dir)
    dir_list = prepare_storage(storage_dir, remove_storage)
    images.import_local_image(image_dir, dir_list[0], dir_list[1],
                              dir_list[2], raw_rootfs_label)


def do_images_unpack(args):
    """Wrapper for 'images unpack' subcommand"""

    images_unpack(args.image_directory,
                  args.storage_directory,
                  args.raw_rootfs_label,
                  args.remove_storage)


def init_parser(subparsers):
    """Initialize 'images' subcommands command line interface."""

    parser = subparsers.add_parser(
        "images",
        help="Manage Toradex Easy Installer Images.",
        allow_abbrev=False)
    # FIXME: This should be moved to "images unpack" and "images download"
    parser.add_argument("--remove-storage", dest="remove_storage", action="store_true",
                        help="""Automatically clear storage prior to unpacking a new Easy
                        Installer image.""")
    subparsers = parser.add_subparsers(title='Commands', required=True, dest='cmd')

    # images download
    subparser = subparsers.add_parser(
        "download",
        help="Download image from Toradex Artifactory and unpack it.",
        allow_abbrev=False)
    subparser.add_argument(
        "--remote-host", dest="remote_host",
        help="Hostname/IP address to target device.", required=True)
    common.add_ssh_arguments(subparser)
    subparser.add_argument(
        "--mdns-source", dest="mdns_source",
        help=("Use the given IP address as mDNS source. This is useful when "
              "multiple interfaces are used, and mDNS multicast requests are "
              "sent out the wrong network interface."))
    subparser.set_defaults(func=do_images_download)

    # images provision
    subparser = subparsers.add_parser(
        "provision",
        help=("Generate a Toradex Easy Installer image with provisioning data "
              "for secure updates."),
        allow_abbrev=False)
    subparser.add_argument(
        metavar="INPUT_DIRECTORY",
        dest="input_directory",
        help="Path to input TorizonCore Toradex Easy Installer image.")
    subparser.add_argument(
        metavar="OUTPUT_DIRECTORY",
        dest="output_directory",
        help=("Path to output TorizonCore Toradex Easy Installer image, which "
              "will hold provisioning data."))
    subparser.add_argument(
        "--mode", dest="mode", choices=PROV_MODES,
        help="Select type of provisioning; online mode encompasses offline mode.",
        required=True)
    subparser.add_argument(
        "--force", dest="force",
        default=False, action="store_true",
        help=("Force program output (remove output directory before "
              "starting process)."))
    subparser.add_argument(
        "--shared-data", dest="shared_data_file",
        help="Archive containing shared provisioning data.")
    subparser.add_argument(
        "--online-data", dest="online_data",
        help=("String containing sensitive data required for online "
              "provisioning (base64-encoded)."))
    subparser.set_defaults(func=do_images_provision)

    # images serve
    subparser = subparsers.add_parser(
        "serve",
        help="Serve TorizonCore Toradex Easy Installer images via HTTP.",
        allow_abbrev=False)

    subparser.add_argument(
        metavar="IMAGES_DIRECTORY",
        dest="images_directory",
        help="Path to directory holding Toradex Easy Installer images.")
    subparser.set_defaults(func=do_images_serve)

    # images unpack
    subparser = subparsers.add_parser(
        "unpack",
        help=("Unpack a specified Toradex Easy Installer or WIC/raw image so it can be "
              "modified with the union subcommand."),
        allow_abbrev=False)
    subparser.add_argument(
        metavar="IMAGE", dest="image_directory",
        help="Path to .wic/.img file, Easy Installer .tar file or directory.")
    subparser.add_argument(
        "--raw-rootfs-label", dest="raw_rootfs_label", metavar="LABEL",
        help="rootfs filesystem label of WIC/raw image. "
             f"(default: {common.DEFAULT_RAW_ROOTFS_LABEL})",
        default=common.DEFAULT_RAW_ROOTFS_LABEL)

    subparser.set_defaults(func=do_images_unpack)
