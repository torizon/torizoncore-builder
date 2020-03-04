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

parser = argparse.ArgumentParser(description="""\
Utility to create TorizonCore images with containers pre-provisioned. Requires a
TorizonCore base image (downloaded from Toradex Easy Installer feed) and a
Docker Compose YAML file as input and creates a Toradex Easy Installer image
with TorizonCore and the containers combined.
""")
parser.add_argument("--output-directory", dest="output_directory",
                    help="Specify an alternate output directory")
parser.add_argument("-f", "--file", dest="compose_file",
                    help="Specify an alternate compose file",
                    default="docker-compose.yml")
parser.add_argument("--platform", dest="platform",
                    help="""Specify platform to make sure fetching the correct
                    container image when multi-platform container images are
                    specified (e.g. linux/arm/v7 or linux/arm64)""",
                    default="linux/arm/v7")
parser.add_argument("--repo", dest="repo",
                    help="""Toradex Easy Installer source repository""",
                    default="torizoncore-oe-nightly-horw")
parser.add_argument("--branch", dest="branch",
                    help="""ToroizonCore OpenEmbedded branch""",
                    default="zeus")
parser.add_argument("--distro", dest="distro", nargs='+',
                    help="""ToroizonCore OpenEmbedded distro""",
                    default=[ "torizon" ])
parser.add_argument("--release-type", dest="release_type",
                    help="""TorizonCore release type (nightly/monthly/release)""",
                    default="nightly")
parser.add_argument("--matrix-build-number", dest="matrix_build_number",
                    help="""Matrix build number to processes.""")
parser.add_argument("--image-name", dest="image_name",
                    help="""New image name""",
                    default="torizon-core-docker-with-containers")
parser.add_argument("--post-script", dest="post_script",
                    help="""Executes this script in every image generated.""")
parser.add_argument('machines', metavar='MACHINE', type=str, nargs='+',
                    help='Machine names to process.')
args = parser.parse_args()

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

def add_files(tezidir, image_json_filename, filelist):
    image_json_filepath = os.path.join(tezidir, image_json_filename)
    with open(image_json_filepath, "r") as jsonfile:
        jsondata = json.load(jsonfile)

    jsondata["name"] = jsondata["name"] + " with Containers"
    jsondata["version"] = jsondata["version"] + ".container"
    jsondata["release_date"] = datetime.datetime.today().strftime("%Y-%m-%d")

    # Find root file system content
    content = utils.find_rootfs_content(jsondata)
    if content is None:
        raise Exception("No root file system content section found")

    # Asuming those files are uncompressed/copied as is
    additional_size = 0
    for filename in filelist:
        filename = filename.split(":")[0]
        st = os.stat(os.path.join(tezidir, filename))
        additional_size = additional_size + st.st_size

    content["filelist"] = filelist
    content["uncompressed_size"] += float(additional_size) / 1024 / 1024

    with open(image_json_filepath, "w") as jsonfile:
        json.dump(jsondata, jsonfile, indent=4)


if __name__== "__main__":
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)


    output_dir_containers = os.path.join(os.getcwd(), "output")

    # Download only if not yet downloaded
    if (os.path.exists(os.path.join(output_dir_containers, "docker-storage.tar"))
        and
        os.path.exists(os.path.join(output_dir_containers, "docker-compose.yml"))):
        logging.info("Docker bundle present, reusing...")
    else:
        logging.info("Downloading containers using Docker...")
        dockerbundle.download_containers_by_compose_file(output_dir_containers,
                args.compose_file, platform=args.platform)

    if args.output_directory is None:
        image_dir = os.path.abspath("images")
    else:
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
            output_dir = os.path.join(image_dir, machine, distro, args.image_name)
            os.makedirs(output_dir, exist_ok=True)

            files_to_add = [
                    "docker-compose.yml:/ostree/deploy/torizon/var/sota/storage/docker-compose/",
                    "docker-storage.tar:/ostree/deploy/torizon/var/lib/docker/:true"
                    ]

            # Copy container
            for filename in files_to_add:
                filename = filename.split(":")[0]
                shutil.copy(os.path.join(output_dir_containers, filename),
                            os.path.join(output_dir, filename))

            for url in image_urls:
                logging.info("Downloading from {0}".format(url))
                downloader.download(url, output_dir)

                logging.info("Adding container tarball to downloaded image")
                add_files(output_dir, os.path.basename(url), files_to_add)

                # Start Artifactory upload with a empty environment
                if args.post_script is not None:
                    logging.info("Executing post image generation script {0}.".format(args.post_script))

                    cp = subprocess.run(
                        [ args.post_script,
                          machine, distro, image_name ],
                        cwd=output_dir)

                    if cp.returncode != 0:
                        logging.error(
                                "Executing post image generation script was unsuccessful. Exit code {0}."
                                .format(cp.returncode))
                        sys.exit(1)


    logging.info("Finished")

