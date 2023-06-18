"""OSTree CLI frontend
"""

import os
import logging
import signal
import subprocess

from tcbuilder.backend import ostree
from tcbuilder.backend.common import images_unpack_executed

log = logging.getLogger("torizon." + __name__)


def serving_ostree_callback():
    """Callback executed when HTTP Server has been started"""


def serve_ostree(storage_dir, repo_dir=None):
    """Main handler of the ostree serve command (CLI layer)"""

    if repo_dir is None:
        storage_dir_ = os.path.abspath(storage_dir)
        src_ostree_archive_dir = os.path.join(storage_dir_, "ostree-archive")
        images_unpack_executed(storage_dir_)
        summary_cmd = ['ostree', 'summary', '--repo', src_ostree_archive_dir, '-u']
        subprocess.check_output(summary_cmd, stderr=subprocess.STDOUT)
    else:
        src_ostree_archive_dir = os.path.abspath(repo_dir)

    http_server_thread = None

    # Allow stopping via SIGTERM so that a `docker stop` will stop the container
    # quick and cleanly.
    def stop_by_sigterm(_signum, _frame):
        if http_server_thread is not None:
            http_server_thread.shutdown()

    prev_handler = signal.signal(signal.SIGTERM, stop_by_sigterm)

    try:
        http_server_thread = ostree.serve_ostree_start(src_ostree_archive_dir)
        http_server_addr = http_server_thread.server_address
        log.info(f"Server running at http://{http_server_addr[0]}:{http_server_addr[1]}/. "
                 "Press 'Ctrl+C' to quit.")
        http_server_thread.join()

    except KeyboardInterrupt:
        pass

    finally:
        signal.signal(signal.SIGTERM, prev_handler)
        if http_server_thread is not None:
            log.info("Stopping server.")
            ostree.serve_ostree_stop(http_server_thread)


def do_serve_ostree(args):
    """Run "serve" subcommand"""
    serve_ostree(args.storage_directory, args.ostree_repo_directory)


def init_parser(subparsers):
    """Initialize argument parser"""

    parser = subparsers.add_parser(
        "ostree",
        help="OSTree operational commands",
        allow_abbrev=False)

    subparsers = parser.add_subparsers(
        title='Commands',
        required=True,
        dest='cmd')

    # serve command
    subparser = subparsers.add_parser(
        "serve",
        help="Serve OSTree on the local network using http",
        allow_abbrev=False)

    subparser.add_argument(
        "--ostree-repo-directory",
        dest="ostree_repo_directory",
        help="Path to the OSTree repository to serve (defaults to internal "
             "archive repository)")

    subparser.set_defaults(func=do_serve_ostree)
