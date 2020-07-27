#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
MIN_PYTHON = (3, 7)
if sys.version_info < MIN_PYTHON:
        sys.exit("Python %s.%s or later is required.\n" % MIN_PYTHON)

import argparse
import os
import urllib.request
import urllib.parse
import logging
from tezi import downloader
from tezi import utils
import subprocess
import dockerbundle
import json
from tcbuilder.cli import unpack
from tcbuilder.cli import isolate
from tcbuilder.cli import deploy
from tcbuilder.cli import union
from tcbuilder.cli import combine
from tcbuilder.backend import common
TEZI_FEED_URL = "https://tezi.int.toradex.com:8443/tezifeed"


def get_images(feed_url, artifactory_repo, branch, release_type, matrix_build_number, machine, distro, image):
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
    logging.info("Requestion from \"{}\"".format(feed_url))
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
    # If no Docker host workdir is given, we assume that Docker uses the same
    # path as we do to access the current working directory.
    host_workdir = args.host_workdir
    if host_workdir is None:
        host_workdir = os.getcwd()

    logging.info("Creating Docker Container bundle.")
    dockerbundle.download_containers_by_compose_file(
                args.bundle_directory, args.compose_file, host_workdir,
                platform=args.platform, output_filename=common.DOCKER_BUNDLE_FILENAME)
    logging.info("Successfully created Docker Container bundle in {}."
            .format(args.bundle_directory))

def batch_process(args):
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
                args.release_type, args.matrix_build_number, machine, distro, 'torizon-core-docker'))

            if len(image_urls) == 0:
                continue

            # Create image dir for image and add containers there...
            output_dir = os.path.join(image_dir, machine, distro, args.image_directory)
            os.makedirs(output_dir, exist_ok=True)

            for url in image_urls:
                logging.info("Downloading from {0}".format(url))
                downloader.download(url, output_dir)

            common.combine_single_image(output_dir_containers, common.DOCKER_FILES_TO_ADD,
                                 additional_size, output_dir, args.image_name,
                                 args.image_description, args.licence_file,
                                 args.release_notes_file)

            # Start Artifactory upload with a empty environment
            if args.post_script is not None:
                logging.info("Executing post image generation script {0}.".format(args.post_script))

                cp = subprocess.run(
                    [ args.post_script,
                      machine, distro, args.image_directory ],
                    cwd=output_dir)

                if cp.returncode != 0:
                    logging.error(
                            "Executing post image generation script was unsuccessful. Exit code {0}."
                            .format(cp.returncode))
                    sys.exit(1)

    logging.info("Finished")


parser = argparse.ArgumentParser(description="""\
Utility to create TorizonCore images with containers pre-provisioned. Requires a
TorizonCore base image and a Docker Compose YAML file as input and creates a
Toradex Easy Installer image with TorizonCore and the containers combined.
""")


def setup_logging(level, verbose, file):
    logger = logging.getLogger("torizon")  # use name hierarchy
    lhandler = None
    if file is None:
        lhandler = logging.StreamHandler()
    else:
        file = os.path.abspath(file)
        lhandler = logging.FileHandler(file)

    set_level = None
    if level is not None:
        levels = {
             'DEBUG': logging.DEBUG,
             'INFO': logging.INFO,
             'WARNING': logging.WARNING,
             'ERROR': logging.ERROR,
             'CRITICAL': logging.CRITICAL,
        }
        set_level = levels.get(level.upper())

    if set_level is None:
        print('Invalid value for --log-level. Expected one of DEBUG, INFO, WARNING, ERROR, CRITICAL.')
        sys.exit(-1)

    if verbose:
        logger.setLevel(logging.INFO)
        lformat = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        lhandler.setFormatter(lformat)

    if set_level == logging.DEBUG:
        logger.setLevel(logging.DEBUG)
        lformat = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        lhandler.setFormatter(lformat)
    else:
        logger.setLevel(set_level)

    logger.addHandler(lhandler)


parser.add_argument("--verbose", dest="verbose",
                    action='store_true',
                    help="Show more output")

parser.add_argument("--log-level", dest="log_level",
                    help="--log-level Set log level (debug, info, warning, error, critical)",
                    default="info")

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
                    default=[ "torizon" ])
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


if __name__ == "__main__":
    args = parser.parse_args()
    setup_logging(args.log_level, args.verbose, args.log_file)

    if hasattr(args, 'func'):
        args.func(args)
    else:
        print(f"Try --help for options")

