"""
CLI handling for images subcommand
"""

import os
import shutil

from tcbuilder.backend import images, common
from tcbuilder.errors import UserAbortError


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
                         dir_list[0], dir_list[1], dir_list[2])

def images_unpack(image_dir, storage_dir, remove_storage=False):
    """Main handler for the 'images unpack' subcommand"""

    image_dir = os.path.abspath(image_dir)
    dir_list = prepare_storage(storage_dir, remove_storage)
    images.import_local_image(image_dir, dir_list[0], dir_list[1], dir_list[2])


def do_images_unpack(args):
    """Wrapper for 'images unpack' subcommand"""

    images_unpack(args.image_directory,
                  args.storage_directory,
                  args.remove_storage)


def init_parser(subparsers):
    '''Initialize 'images' subcommands command line interface.'''

    parser = subparsers.add_parser("images", help="Manage Toradex Easy Installer Images.")
    parser.add_argument("--remove-storage", dest="remove_storage", action="store_true",
                        help="""Automatically clear storage prior to unpacking a new Easy
                        Installer image.""")
    subparsers = parser.add_subparsers(title='Commands', required=True, dest='cmd')

    # images download
    subparser = subparsers.add_parser("download",
                                      help="""Download image from Toradex Artifactory
                                      and unpack it.""")
    subparser.add_argument("--remote-host", dest="remote_host",
                           help="Hostname/IP address to target device.", required=True)
    common.add_username_password_arguments(subparser)
    subparser.add_argument("--mdns-source", dest="mdns_source",
                           help="""Use the given IP address as mDNS source.
                           This is useful when multiple interfaces are used, and
                           mDNS multicast requests are sent out the wrong
                           network interface.""")
    subparser.set_defaults(func=do_images_download)

    #images unpack
    subparser = subparsers.add_parser("unpack", help="""\
    Unpack a specified Toradex Easy Installer image so it can be modified with
    union subcommand.""")
    subparser.add_argument(metavar="IMAGE", dest="image_directory", nargs='?',
                           help="Path to Easy Installer file or directory.")

    subparser.set_defaults(func=do_images_unpack)
