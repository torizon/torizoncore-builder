"""Serve CLI frontend
"""
import os

from tcbuilder.backend import serve


def serving_ostree_callback():
    """Callback executed when HTTP Server has been started"""


def serve_ostree(args):
    """Run \"serve\" subcommand"""
    if args.ostree_repo_directory is None:
        storage_dir = os.path.abspath(args.storage_directory)
        src_ostree_archive_dir = os.path.join(storage_dir, "ostree-archive")
    else:
        src_ostree_archive_dir = os.path.abspath(args.ostree_repo_directory)

    http_server_thread = serve.serve_ostree_start(src_ostree_archive_dir)

    print("==> OSTree available on http://localhost:8080/")
    print()

    print("Press 'ENTER'' to stop OSTree http server.")
    input()

    print("Stopping server.")
    serve.serve_ostree_stop(http_server_thread)

def init_parser(subparsers):
    """Initialize argument parser"""
    subparser = subparsers.add_parser("serve", help="""\
    Serve OSTree on the local network using http""")
    subparser.add_argument("--ostree-repo-directory", dest="ostree_repo_directory",
                           help="""Path to the OSTree repository to serve
                           (defaults to internal archive repository).""")

    subparser.set_defaults(func=serve_ostree)
