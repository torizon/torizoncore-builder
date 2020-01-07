#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import datetime
import os
import json
import shutil
import urllib.request
import logging
import glob
from tezi import downloader
from tezi import utils
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
parser.add_argument('machines', metavar='MACHINE', type=str, nargs='+',
                    help='Machine names to process')
parser.add_argument("--platform", dest="platform",
                    help="""Specify platform to make sure fetching the correct
                    image when multi-platform images are specified""",
                    default="linux/arm/v7")
args = parser.parse_args()

TEZI_FEED_URL = "http://tezi.toradex.com/image_list.json"
TEZI_CI_FEED_URL = "http://tezi.toradex.com/image_list_ci.json"

def get_images(feed_url, machines):
    req = urllib.request.urlopen(feed_url)
    content = req.read().decode(req.headers.get_content_charset() or "utf-8")

    # This gets the actual location of the images also considering HTTP 301/302
    # redirects...
    image_base_url = os.path.dirname(req.url)

    imagelist = json.loads(content)
    for image in imagelist['images']:
        # We can only work with TorizonCore Docker images...
        if "torizon-core-docker" not in image:
            continue

        # Find machine in image name. Add - to avoid matching imx6ull with imx6
        if not any(machine + "-" in image for machine in machines):
            continue

        image_url = os.path.join(image_base_url, image)
        yield image_url

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

    logging.info("Downloading containers using Docker...")
    output_dir_containers = os.path.join(os.getcwd(), "output")
    dockerbundle.download_containers_by_compose_file(output_dir_containers,
            args.compose_file, platform=args.platform)

    if args.output_directory is None:
        image_dir = os.path.abspath("images")
    else:
        image_dir = os.path.abspath(args.output_directory)

    if not os.path.exists(image_dir):
        os.mkdir(image_dir)

    # TODO: get list of all images we have to process using build number or
    # similar...
    image_urls = list(get_images(TEZI_FEED_URL, args.machines))

    for url in image_urls:
        image_name = os.path.basename(os.path.dirname(url))
        output_dir = os.path.join(image_dir, image_name)
        if not os.path.exists(output_dir):
            os.mkdir(output_dir)

        files_to_add = [
                "docker-compose.yml:/ostree/deploy/torizon/var/sota/storage/docker-compose/",
                "docker-storage.tar:/ostree/deploy/torizon/var/lib/docker/:true"
                ]

        # Copy container
        for filename in files_to_add:
            filename = filename.split(":")[0]
            shutil.copy(os.path.join(output_dir_containers, filename),
                        os.path.join(output_dir, filename))

        logging.info("Downloading from {0}".format(url))
        downloader.download(url, output_dir)

        logging.info("Adding container tarball to downloaded image")
        for image_file in glob.glob(os.path.join(output_dir, "image*.json")):
            add_files(output_dir, image_file, files_to_add)
        # TODO: tar up and Artifactory upload...

    logging.info("Finished")

