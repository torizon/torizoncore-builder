import os
import sys
import glob
import logging
import json
import subprocess
import tezi.utils
from tcbuilder.backend.common import TorizonCoreBuilderError

def unpack_local_image(image_dir, ostree_dir):
    if not os.path.exists(image_dir):
        raise TorizonCoreBuilderError("Source image directory does not exist")

    image_files = glob.glob(os.path.join(image_dir, "image*.json"))

    if len(image_files) < 1:
        raise TorizonCoreBuilderError("No image.json file found in image directory")

    image_json_filepath = os.path.join(image_dir, image_files[0])
    with open(image_json_filepath, "r") as jsonfile:
        jsondata = json.load(jsonfile)

    # Find root file system content
    content = tezi.utils.find_rootfs_content(jsondata)
    if content is None:
        raise TorizonCoreBuilderError("No root file system content section found")

    # This is a OSTree bare repository. Care must been taken to preserve all
    # file system attributes. Python tar does not support xattrs, so use GNU tar
    # here
    # See: https://dev.gentoo.org/~mgorny/articles/portability-of-tar-features.html#extended-file-metadata
    tarcmd = "tar --xattrs --xattrs-include='*' -xhf {0} -C {1}".format(
                os.path.join(image_dir, content["filename"]), ostree_dir)
    logging.info("Running tar command: " + tarcmd)
    subprocess.check_output(tarcmd, shell=True, stderr=subprocess.STDOUT)

