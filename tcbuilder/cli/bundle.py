"""Bundle CLI frontend

Allows to bundle a Toradex Easy Installer images with a set of containers.
"""

import argparse
import logging
import os
import shutil

from tcbuilder.backend import common
from tcbuilder.backend import bundle as bundle_be
from tcbuilder.errors import InvalidArgumentError, InvalidStateError

log = logging.getLogger("torizon." + __name__)


# pylint: disable=too-many-arguments
def bundle(bundle_dir, compose_file, force=False, platform=None,
           reg_username=None, reg_password=None, registry=None):
    """Main handler of the bundle command (CLI layer)

    :param bundle_dir: Name of bundle directory (that will be created in the
                       working directory).
    :param compose_file: Relative path to the input compose file.
    :param force: Whether or not to overwrite the (output) bundle directory
                  if it already exists.
    :param platform: Default platform to use when fetching multi-platform
                     container images.
    :param reg_username: Username to access a registry.
    :param reg_password: Password to access a registry.
    :param registry: Registry from where images should be fetched from.
    """

    if os.path.exists(bundle_dir):
        if force:
            log.debug(f"Removing existing bundle directory '{bundle_dir}'")
            shutil.rmtree(bundle_dir)
        else:
            raise InvalidStateError(
                f"Bundle directory '{bundle_dir}' already exists; please remove "
                "it or pass a different output directory name.")

    # Determine mapping between volume and working directory.
    host_workdir = common.get_host_workdir()

    log.info("Creating Docker Container bundle...")

    bundle_be.download_containers_by_compose_file(
        bundle_dir, compose_file, host_workdir,
        docker_username=reg_username,
        docker_password=reg_password,
        registry=registry,
        platform=platform,
        output_filename=common.DOCKER_BUNDLE_FILENAME)

    log.info(f"Successfully created Docker Container bundle in \"{bundle_dir}\"!")

# pylint: enable=too-many-arguments


def do_bundle(args):
    """\"bundle\" sub-command"""

    # Temporary solution to provide better messages (DEPRECATED since 2021-05-25).
    if args.host_workdir_compat:
        raise InvalidArgumentError(
            "Error: the switch --host-workdir has been removed; "
            "please run the tool without passing that switch (and its argument).")

    # Temporary solution to provide better messages (DEPRECATED since 2021-05-17).
    if args.compose_file_compat:
        raise InvalidArgumentError(
            "Error: the switch --file (-f) has been removed; "
            "please provide the file name without passing the switch.")

    # Temporary solution to provide better messages (DEPRECATED since 2021-05-17).
    if not args.compose_file:
        raise InvalidArgumentError(
            "Error: the COMPOSE_FILE positional argument is required.")

    bundle(bundle_dir=args.bundle_directory,
           compose_file=args.compose_file,
           force=args.force,
           platform=args.platform,
           reg_username=args.docker_username,
           reg_password=args.docker_password,
           registry=args.registry)


def init_parser(subparsers):
    """Initialize argument parser"""

    # Temporary solution to provide better messages (DEPRECATED since 2021-05-25).
    subparser = subparsers.add_parser(
        "bundle",
        help=("Create container bundle from a Docker Compose file. Can be "
              "used to combine with a TorizonCore base image."),
        epilog=("NOTE: the switches --host-workdir and --file (-f) have been "
                "removed; please don't use them."))

    common.add_bundle_directory_argument(subparser)

    # The nargs='?' argument below can be removed together with the
    # --host-workdir and --file switches that currently exist just to allow
    # for better messages (DEPRECATED since 2021-05-17).
    subparser.add_argument(
        nargs='?',
        dest="compose_file",
        help=("Compose file to be processed (REQUIRED); "
              "commonly named 'docker-compose.yml'."))
    subparser.add_argument(
        "--force", dest="force",
        default=False, action="store_true",
        help=("Force program output (remove output directory before starting "
              "the bundle generation process)."))
    subparser.add_argument(
        "--platform", dest="platform",
        help=("Default platform for fetching container images when multi-"
              "platform images are specified in the compose file (e.g. "
              "linux/arm/v7 or linux/arm64)."))
    subparser.add_argument(
        "--docker-username", dest="docker_username",
        help="Optional username to be used to access a container registry.")
    subparser.add_argument(
        "--docker-password", dest="docker_password",
        help="Password to be used to access a container registry.")
    subparser.add_argument(
        "--registry", dest="registry",
        help="Alternative container registry used to access container images.")

    # Temporary solution to provide better messages (DEPRECATED since 2021-05-25).
    subparser.add_argument(
        "--host-workdir", dest="host_workdir_compat", help=argparse.SUPPRESS)
    subparser.add_argument(
        "-f", "--file", dest="compose_file_compat", help=argparse.SUPPRESS)

    subparser.set_defaults(func=do_bundle)
