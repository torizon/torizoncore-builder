import os
import json
import glob
import tezi.utils

class TorizonCoreBuilderError(Exception):
    pass

def get_rootfs_tarball(tezi_image_dir):
    if not os.path.exists(tezi_image_dir):
        raise TorizonCoreBuilderError("Source image directory does not exist")

    image_files = glob.glob(os.path.join(tezi_image_dir, "image*.json"))

    if len(image_files) < 1:
        raise TorizonCoreBuilderError("No image.json file found in image directory")

    image_json_filepath = os.path.join(tezi_image_dir, image_files[0])
    with open(image_json_filepath, "r") as jsonfile:
        jsondata = json.load(jsonfile)

    # Find root file system content
    content = tezi.utils.find_rootfs_content(jsondata)
    if content is None:
        raise TorizonCoreBuilderError("No root file system content section found")

    return os.path.join(tezi_image_dir, content["filename"])
