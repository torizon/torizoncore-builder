#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import datetime
import os
import sys
import json
import shutil
import urllib.request
import urllib.parse
import logging
import glob
from tezi import downloader
from tezi import utils
import subprocess
import dockerbundle

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

def add_files(tezidir, image_json_filename, filelist, additional_size,
              image_name, image_description):
    image_json_filepath = os.path.join(tezidir, image_json_filename)
    with open(image_json_filepath, "r") as jsonfile:
        jsondata = json.load(jsonfile)

    # Version 3 image format is required for the advanced filelist syntax.
    jsondata["config_format"] = 3

    if image_name is None:
        jsondata["name"] = jsondata["name"] + " with Containers"
    else:
        jsondata["name"] = image_name
    if image_description is not None:
        jsondata["description"] = image_description

    jsondata["version"] = jsondata["version"] + ".container"
    jsondata["release_date"] = datetime.datetime.today().strftime("%Y-%m-%d")

    # Find root file system content
    content = utils.find_rootfs_content(jsondata)
    if content is None:
        raise Exception("No root file system content section found")

    content["filelist"] = filelist
    content["uncompressed_size"] += float(additional_size) / 1024 / 1024

    with open(image_json_filepath, "w") as jsonfile:
        json.dump(jsondata, jsonfile, indent=4)


DOCKER_BUNDLE_FILENAME = "docker-storage.tar.xz"
DOCKER_FILES_TO_ADD = [
    "docker-compose.yml:/ostree/deploy/torizon/var/sota/storage/docker-compose/",
    DOCKER_BUNDLE_FILENAME + ":/ostree/deploy/torizon/var/lib/docker/:true"
]

def bundle_containers(args):
    # If no Docker host workdir is given, we assume that Docker uses the same
    # path as we do to access the current working directory.
    host_workdir = args.host_workdir
    if host_workdir is None:
        host_workdir = os.getcwd()

    logging.info("Creating Docker Container bundle.")
    dockerbundle.download_containers_by_compose_file(
                args.bundle_directory, args.compose_file, host_workdir,
                platform=args.platform, output_filename=DOCKER_BUNDLE_FILENAME)
    logging.info("Successfully created Docker Container bundle in {}."
            .format(args.bundle_directory))

def get_additional_size(output_dir_containers, files_to_add):
    additional_size = 0

    # Check size of files to add to theimage
    for fileentry in files_to_add:
        filename, destination, *rest = fileentry.split(":")
        filepath = os.path.join(output_dir_containers, filename)
        if not os.path.exists(filepath):
            return None

        # Check third parameter, if unpack is set to true we need to get size
        # of unpacked tarball...
        unpack = False
        if len(rest) > 0:
            unpack = rest[0].lower() == "true"

        if unpack:
            if filename.endswith(".gz"):
                command = "gzip -dc"
            elif filename.endswith(".xz"):
                command = "xz -dc"
            elif filename.endswith(".lzo"):
                command = "lzop -dc"
            elif filename.endswith(".zst"):
                command = "zstd -dc"

            # Unpack similar to how Tezi does the size check
            size_proc = subprocess.run(
                    "cat '{0}' | {1} | wc -c".format(filename, command),
                    shell=True, capture_output=True, cwd=output_dir_containers)

            if size_proc.returncode != 0:
                logging.error("Size estimation failed. Exit code {0}."
                              .format(size_proc.returncode))
                sys.exit(1)

            additional_size += int(size_proc.stdout.decode('utf-8'))

        else:
            st = os.stat(filepath)
            additional_size += st.st_size

    return additional_size

def combine_single_image(source_dir_containers, files_to_add, additional_size,
                         output_dir, image_name, image_description):
    # Copy container
    for filename in files_to_add:
        filename = filename.split(":")[0]
        shutil.copy(os.path.join(source_dir_containers, filename),
                    os.path.join(output_dir, filename))

    for image_file in glob.glob(os.path.join(output_dir, "image*.json")):
        add_files(output_dir, image_file, files_to_add, additional_size,
                  image_name, image_description)

def combine_local_image(args):
    output_dir_containers = os.path.abspath(args.bundle_directory)

    additional_size = get_additional_size(output_dir_containers, DOCKER_FILES_TO_ADD)
    if additional_size is None:
        logging.error("Docker Container bundle missing, use bundle sub-command.")
        return

    output_image_dir = os.path.abspath(args.output_directory)

    if not os.path.exists(output_image_dir):
        os.mkdir(output_image_dir)

    image_dir = os.path.abspath(args.image_directory)

    if not os.path.exists(image_dir):
        logging.error("Source image directory does not exist")
        return

    logging.info("Creating copy of TorizonCore source image.")
    shutil.rmtree(output_image_dir)
    shutil.copytree(image_dir, output_image_dir)

    logging.info("Combining TorizonCore image with Docker Container bundle.")
    combine_single_image(output_dir_containers, DOCKER_FILES_TO_ADD, additional_size,
                         output_image_dir, args.image_name, args.image_description)
    logging.info("Successfully created a TorizonCore image with Docker Containers preprovisioned in {}"
            .format(args.output_directory))

def batch_process(args):
    output_dir_containers = os.path.abspath(args.bundle_directory)
    additional_size = get_additional_size(output_dir_containers, DOCKER_FILES_TO_ADD)
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

            combine_single_image(output_dir_containers, DOCKER_FILES_TO_ADD, additional_size,
                                 output_dir, args.image_name, args.image_description)

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


def add_common_image_arguments(subparser):
    subparser.add_argument("--image-name", dest="image_name",
                        help="""Image name used in Easy Installer image json""")
    subparser.add_argument("--image-description", dest="image_description",
                        help="""Image description used in Easy Installer image json""")


parser = argparse.ArgumentParser(description="""\
Utility to create TorizonCore images with containers pre-provisioned. Requires a
TorizonCore base image and a Docker Compose YAML file as input and creates a
Toradex Easy Installer image with TorizonCore and the containers combined.
""")

parser.add_argument("--bundle-directory", dest="bundle_directory",
                    help="Container bundle directory",
                    default="bundle")

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
add_common_image_arguments(subparser)
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

subparser = subparsers.add_parser("combine", help="""\
Combines a container bundle with a specified Toradex Easy Installer image.
""")
subparser.add_argument("--output-directory", dest="output_directory",
                    help="""\
Output directory where the combined Toradex Easy Installer images will be stored.
""",
                    default="output")
subparser.add_argument("--image-directory", dest="image_directory",
                    help="""Path to TorizonCore Toradex Easy Installer source image.""",
                    required=True)
add_common_image_arguments(subparser)

subparser.set_defaults(func=combine_local_image)

if __name__== "__main__":
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    args = parser.parse_args()
    args.func(args)
