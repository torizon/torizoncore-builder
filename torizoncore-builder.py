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



def bundle_containers(args):
    output_dir_containers = os.path.abspath(args.bundle_directory)

    logging.info("Creating Docker Container bundle.")
    dockerbundle.download_containers_by_compose_file(output_dir_containers,
                args.compose_file, platform=args.platform)

def check_containers_bundle(output_dir_containers):
    # Download only if not yet downloaded
    if (os.path.exists(os.path.join(output_dir_containers, "docker-storage.tar"))
        and
        os.path.exists(os.path.join(output_dir_containers, "docker-compose.yml"))):
        return True
    else:
        return False

def combine_single_image(source_dir_containers, output_dir):
    files_to_add = [
            "docker-compose.yml:/ostree/deploy/torizon/var/sota/storage/docker-compose/",
            "docker-storage.tar:/ostree/deploy/torizon/var/lib/docker/:true"
            ]

    # Copy container
    for filename in files_to_add:
        filename = filename.split(":")[0]
        shutil.copy(os.path.join(source_dir_containers, filename),
                    os.path.join(output_dir, filename))

    for image_file in glob.glob(os.path.join(output_dir, "image*.json")):
        add_files(output_dir, image_file, files_to_add)

def combine_local_image(args):
    output_dir_containers = os.path.abspath(args.bundle_directory)
    if not check_containers_bundle(output_dir_containers):
        logging.error("Docker Container bundle missing, use bundle sub-command.")
        return

    output_image_dir = os.path.abspath(args.output_directory)

    if not os.path.exists(output_image_dir):
        os.mkdir(output_image_dir)

    image_dir = os.path.abspath(args.image_directory)

    if not os.path.exists(image_dir):
        logging.error("Source image directory does not exist")
        return

    shutil.copytree(image_dir, output_image_dir, dirs_exist_ok=True)

    combine_single_image(output_dir_containers, output_image_dir)

def batch_process(args):
    output_dir_containers = os.path.abspath(args.bundle_directory)
    if not check_containers_bundle(output_dir_containers):
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
            output_dir = os.path.join(image_dir, machine, distro, args.image_name)
            os.makedirs(output_dir, exist_ok=True)

            for url in image_urls:
                logging.info("Downloading from {0}".format(url))
                downloader.download(url, output_dir)

            combine_single_image(output_dir_containers, output_dir)

            # Start Artifactory upload with a empty environment
            if args.post_script is not None:
                logging.info("Executing post image generation script {0}.".format(args.post_script))

                cp = subprocess.run(
                    [ args.post_script,
                      machine, distro, args.image_name ],
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

parser.add_argument("--bundle-directory", dest="bundle_directory",
                    help="Container bundle directory",
                    default="bundle")

subparsers = parser.add_subparsers(title='Commands:')

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
subparser.add_argument("--image-name", dest="image_name",
                    help="""New image name""",
                    default="torizon-core-docker-with-containers")
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
subparser.set_defaults(func=combine_local_image)

if __name__== "__main__":
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    args = parser.parse_args()
    args.func(args)
