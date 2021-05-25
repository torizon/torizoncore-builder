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

DEFAULT_COMPOSE_FILE = "docker-compose.yml"


def bundle(bundle_dir, compose_file, storage_dir,
           force=False, platform=None,
           reg_username=None, reg_password=None, registry=None):

    if not platform:
        try:
            platform = common.get_docker_platform(storage_dir)
            log.debug(f"Platform not specified: default set to '{platform}' "
                      "based on current image on storage")

        except InvalidStateError as _exc:
            platform = common.DEFAULT_DOCKER_PLATFORM
            log.info("Could not determine platform from current image: "
                     f"using default of '{platform}'")

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

    logging.info("Creating Docker Container bundle.")

    bundle_be.download_containers_by_compose_file(
        bundle_dir, compose_file, host_workdir,
        docker_username=reg_username,
        docker_password=reg_password,
        registry=registry,
        platform=platform,
        output_filename=common.DOCKER_BUNDLE_FILENAME)

    logging.info(
        f"Successfully created Docker Container bundle in \"{bundle_dir}\".")


def do_bundle(args):
    """\"bundle\" sub-command"""

    # Temporary solution to provide better messages (DEPRECATED since 2021-05-25).
    if args.host_workdir_compat:
        raise InvalidArgumentError(
            "Error: the switch --host-workdir has been removed; "
            "please run the tool without passing that switch (and its argument).")

    bundle(bundle_dir=args.bundle_directory,
           compose_file=args.compose_file,
           storage_dir=args.storage_directory,
           force=args.force,
           platform=args.platform,
           reg_username=args.docker_username,
           reg_password=args.docker_password,
           registry=args.registry)


def init_parser(subparsers):
    """Initialize argument parser"""

    subparser = subparsers.add_parser(
        "bundle",
        help=("Create container bundle from a Docker Compose file. Can be "
              "used to combine with a TorizonCore base image."))
    subparser.add_argument(
        "-f", "--file", dest="compose_file",
        help=f"Compose file to be processed (default: {DEFAULT_COMPOSE_FILE}).",
        default=DEFAULT_COMPOSE_FILE)
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

    subparser.set_defaults(func=do_bundle)
