import os
import sys
import subprocess
import shutil
import paramiko
import logging
from subprocess import Popen
from subprocess import PIPE
from tcbuilder.backend import common
from tcbuilder.errors import FileNotFoundError

log = logging.getLogger("torizon." + __name__)


def combine_image(image_dir, output_dir_containers, output_directory, image_name,
                  image_description, licence_file, release_notes_file):
    try:
        additional_size = common.get_additional_size(output_dir_containers, common.DOCKER_FILES_TO_ADD)
        if additional_size is None:
            raise FileNotFoundError("Docker Container bundle missing, use bundle sub-command.")

        log.info("Creating copy of TorizonCore source image.")
        shutil.rmtree(output_directory)
        shutil.copytree(image_dir, output_directory)

        log.info("Combining TorizonCore image with Docker Container bundle.")
        common.combine_single_image(output_dir_containers, common.DOCKER_FILES_TO_ADD, additional_size,
                                    output_directory, image_name,
                                    image_description, licence_file,
                                    release_notes_file)
    except Exception as ex:
        if not hasattr(ex, "msg"):
            ex.msg = "issue occurred while combining image with docker bundle"
            ex.det = str(ex)

        raise
