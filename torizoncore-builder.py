#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TorizonCore Builder main python script

This module is the entry point of TorizonCore Builder. TorizonCore Builder allows
to create customized TorizonCore OSTree commits and Toradex Easy Installer images
without rebuilding the complete operating system.
"""

import sys

MIN_PYTHON = (3, 7)
if sys.version_info < MIN_PYTHON:
    sys.exit("Python %s.%s or later is required.\n" % MIN_PYTHON)

TEZI_FEED_URL = "https://tezi.int.toradex.com:8443/tezifeed"

#pylint: disable=wrong-import-position

import argparse
import json
import logging
import os
import subprocess
import urllib.parse
import urllib.request

import dockerbundle
from tcbuilder.backend import common
from tcbuilder.cli import combine, deploy, isolate, union, unpack, dt, push, splash, serve
from tezi import downloader

#pylint: enable=wrong-import-position

def get_images(feed_url, artifactory_repo, branch, release_type, matrix_build_number, machine,
               distro, image):
    """Get list of Toradex Easy Installer images from feed URL"""

    filter_params = {'repo': artifactory_repo,
                     'BUILD_MANIFEST_BRANCH': branch,
                     'BUILD_PIPELINETYPE': release_type,
                     'BUILD_MACHINE': machine,
                     'BUILD_DISTRO': distro,
                     'BUILD_RECIPE': image}

    if matrix_build_number is not None:
        filter_params['MATRIX_BUILD_NUMBER'] = matrix_build_number

    params = urllib.parse.urlencode(filter_params)

    feed_url = "{}?{}".format(feed_url, params)
    logging.info(f"Requestion from \"{feed_url}\"")
    req = urllib.request.urlopen(feed_url)
    content = req.read().decode(req.headers.get_content_charset() or "utf-8")

    # This gets the actual location of the images also considering HTTP 301/302
    # redirects...
    image_base_url = os.path.dirname(req.url)

    imagelist = json.loads(content)
    for image in imagelist['images']:
        if not bool(urllib.parse.urlparse(image).netloc):
            yield os.path.join(image_base_url, image)
        else:
            yield image

def bundle_containers(args):
    """\"bundle\" sub-command"""
    # If no Docker host workdir is given, we assume that Docker uses the same
    # path as we do to access the current working directory.
    host_workdir = args.host_workdir
    if host_workdir is None:
        host_workdir = os.getcwd()

    logging.info("Creating Docker Container bundle.")
    dockerbundle.download_containers_by_compose_file(
                args.bundle_directory, args.compose_file, host_workdir,
                platform=args.platform, output_filename=common.DOCKER_BUNDLE_FILENAME)
    logging.info(f"Successfully created Docker Container bundle in {args.bundle_directory}.")

def batch_process(args):
    """\"batch\" sub-command"""
    output_dir_containers = os.path.abspath(args.bundle_directory)
    additional_size = common.get_additional_size(output_dir_containers, common.DOCKER_FILES_TO_ADD)
    if additional_size is None:
        logging.error("Docker Container bundle missing, use bundle sub-command.")
        return

    image_dir = os.path.abspath(args.output_directory)

    if not os.path.exists(image_dir):
        os.mkdir(image_dir)

    for machine in args.machines:
        for distro in args.distro:
            # Get TorizonCore Toradex Easy Installer images for
            # machine/distro/image combination...
            image_urls = list(get_images(TEZI_FEED_URL, args.repo, args.branch,
                                         args.release_type, args.matrix_build_number,
                                         machine, distro, 'torizon-core-docker'))

            if len(image_urls) == 0:
                continue

            # Create image dir for image and add containers there...
            output_dir = os.path.join(image_dir, machine, distro, args.image_directory)
            os.makedirs(output_dir, exist_ok=True)

            for url in image_urls:
                logging.info(f"Downloading from {url}")
                downloader.download(url, output_dir)

            common.combine_single_image(output_dir_containers, common.DOCKER_FILES_TO_ADD,
                                        additional_size, output_dir, args.image_name,
                                        args.image_description, args.licence_file,
                                        args.release_notes_file)

            # Start Artifactory upload with a empty environment
            if args.post_script is not None:
                logging.info(f"Executing post image generation script {args.post_script}.")

                cp_process = subprocess.run([args.post_script, machine, distro,
                                             args.image_directory],
                                            cwd=output_dir,
                                            check=False)

                if cp_process.returncode != 0:
                    logging.error(
                        f"""Executing post image generation script was unsuccessful.
                        Exit code {cp_process.returncode}.""")
                    sys.exit(1)

    logging.info("Finished")

parser = argparse.ArgumentParser(description="""\
Utility to create TorizonCore images with containers pre-provisioned. Requires a
TorizonCore base image and a Docker Compose YAML file as input and creates a
Toradex Easy Installer image with TorizonCore and the containers combined.
""")


def setup_logging(arg_level, verbose, file):
    """Setup logging levels and print handler for torizoncore-builder"""

    # Configure the root logger for our needs
    logger = logging.getLogger()
    lhandler = None
    if file is None:
        lhandler = logging.StreamHandler()
    else:
        file = os.path.abspath(file)
        lhandler = logging.FileHandler(file)

    set_level = None

    if verbose:
        set_level = logging.DEBUG

    if arg_level is not None:
        levels = {
            'DEBUG': logging.DEBUG,
            'INFO': logging.INFO,
            'WARNING': logging.WARNING,
            'ERROR': logging.ERROR,
            'CRITICAL': logging.CRITICAL,
        }
        set_level = levels.get(arg_level.upper())

        if set_level is None:
            print("Invalid value for --log-level. Expected one of {levels}",
                  levels=", ".join(levels.keys()))
            sys.exit(-1)

    # Show/store time if any of the following is used:
    # --verbose
    # --log-level DEBUG
    # --log-file FILE
    if verbose or file is not None or (set_level is not None and set_level <= logging.DEBUG):
        lformat = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        lhandler.setFormatter(lformat)

    if set_level is None:
        # By default, use INFO for TorizonCore itself, and WARNING for libraries
        torizoncore_logger = logging.getLogger("torizon")
        torizoncore_logger.setLevel(logging.INFO)
        logger.setLevel(logging.WARNING)
    else:
        logger.setLevel(set_level)

    logger.addHandler(lhandler)


parser.add_argument("--verbose", dest="verbose",
                    action='store_true',
                    help="Show more output")

parser.add_argument("--log-level", dest="log_level",
                    help="--log-level Set global log level (debug, info, warning, error, critical)")

parser.add_argument("--log-file", dest="log_file",
                    help="write logs to a file instead of console",
                    default=None)


parser.add_argument("--bundle-directory", dest="bundle_directory",
                    help="Container bundle directory",
                    default="bundle")
parser.add_argument("--storage-directory", dest="storage_directory",
                    help="""Path to internal storage. Must be a file system
                    capable of carrying Linux file system metadata (Unix
                    file permissions and xattr).""",
                    default="/storage")

subparsers = parser.add_subparsers(title='Commands:', required=True, dest='cmd')

subparser = subparsers.add_parser("batch", help="""\
Automatically downloads a set of Toradex Easy Installer images and adds the
specified containers to it.
""")

subparser.add_argument("--output-directory", dest="output_directory",
                       help="Specify the output directory",
                       default="output")
subparser.add_argument("--repo", dest="repo",
                       help="""Toradex Easy Installer source repository""",
                       default="torizoncore-oe-nightly-horw")
subparser.add_argument("--branch", dest="branch",
                       help="""ToroizonCore OpenEmbedded branch""",
                       default="zeus")
subparser.add_argument("--distro", dest="distro", nargs='+',
                       help="""ToroizonCore OpenEmbedded distro""",
                       default=["torizon"])
subparser.add_argument("--release-type", dest="release_type",
                       help="""TorizonCore release type (nightly/monthly/release)""",
                       default="nightly")
subparser.add_argument("--matrix-build-number", dest="matrix_build_number",
                       help="""Matrix build number to processes.""")
subparser.add_argument("--image-directory", dest="image_directory",
                       help="""Image directory name""",
                       default="torizon-core-docker-with-containers")
common.add_common_image_arguments(subparser)
subparser.add_argument("--post-script", dest="post_script",
                       help="""Executes this script in every image generated.""")
subparser.add_argument('machines', metavar='MACHINE', type=str, nargs='+',
                       help='Machine names to process.')
subparser.set_defaults(func=batch_process)

subparser = subparsers.add_parser("bundle", help="""\
Create container bundle from a Docker Compose file. Can be used to combine with
a TorizonCore base image.
""")
subparser.add_argument("-f", "--file", dest="compose_file",
                       help="Specify an alternate compose file",
                       default="docker-compose.yml")
subparser.add_argument("--platform", dest="platform",
                       help="""Specify platform to make sure fetching the correct
                       container image when multi-platform container images are
                       specified (e.g. linux/arm/v7 or linux/arm64)""",
                       default="linux/arm/v7")
subparser.add_argument("--host-workdir", dest="host_workdir",
                       help="""Location where Docker needs to bind mount to to
                       share data between this script and the DIND instance.""")
subparser.set_defaults(func=bundle_containers)

unpack.init_parser(subparsers)
isolate.init_parser(subparsers)
deploy.init_parser(subparsers)
union.init_parser(subparsers)
combine.init_parser(subparsers)
dt.init_parser(subparsers)
push.init_parser(subparsers)
splash.init_parser(subparsers)
serve.init_parser(subparsers)

if __name__ == "__main__":
    mainargs = parser.parse_args()
    setup_logging(mainargs.log_level, mainargs.verbose, mainargs.log_file)

    try:
        if hasattr(mainargs, 'func'):
            mainargs.func(mainargs)
        else:
            print("Try --help for options")
    except Exception as ex:
        logging.fatal(
            "An unexpected Exception occured. Please provide the following stack trace to\n"
            "the Toradex TorizonCore support team:\n\n")
        raise ex
