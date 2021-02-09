import os
import shutil

from tcbuilder.backend import images
from tcbuilder.backend.common import resolve_remote_host
from tcbuilder.errors import UserAbortError

def prepare_storage(storage_directory, remove_storage):
    """ Prepare Storage directory for unpacking"""

    storage_dir = os.path.abspath(storage_directory)
    tezi_dir = os.path.join(storage_dir, "tezi")
    src_sysroot_dir = os.path.join(storage_dir, "sysroot")
    src_ostree_archive_dir = os.path.join(storage_dir, "ostree-archive")
    src_dt_dir = os.path.join(storage_dir, "dt")

    if not os.path.exists(storage_dir):
        os.mkdir(storage_dir)

    if os.path.exists(tezi_dir) or os.path.exists(src_sysroot_dir) or os.path.exists(src_dt_dir):
        if not remove_storage:
            ans = input("Storage not empty. Delete current image before continuing? [y/N] ")
        else:
            ans = "n"
        if ans.lower() != "y" and not remove_storage:
            raise UserAbortError()

        for src_dir in tezi_dir, src_sysroot_dir, src_dt_dir:
            if os.path.exists(src_dir):
                shutil.rmtree(src_dir)

    return [tezi_dir, src_sysroot_dir, src_ostree_archive_dir]

def do_images_download(args):
    """Run 'images download' subcommand"""

    r_ip = resolve_remote_host(args.remote_host, args.mdns_source)
    dir_list = prepare_storage(args.storage_directory, args.remove_storage)
    images.download_tezi(r_ip, args.remote_username, args.remote_password,
                         dir_list[0], dir_list[1], dir_list[2])

def do_images_unpack(args):
    """Run 'images unpack' subcommand"""

    image_dir = os.path.abspath(args.image_directory)
    dir_list = prepare_storage(args.storage_directory, args.remove_storage)
    images.import_local_image(image_dir, dir_list[0], dir_list[1], dir_list[2])


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
    subparser.add_argument("--remote-username", dest="remote_username",
                           help="Username login to target device.", required=True)
    subparser.add_argument("--remote-password", dest="remote_password",
                           help="Password login to target device.", required=True)
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
