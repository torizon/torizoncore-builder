import os
import shutil
import logging
from tcbuilder.backend.common import \
    (get_additional_size, combine_single_image, DOCKER_FILES_TO_ADD, \
     TARGET_NAME_FILENAME, set_output_ownership)
from tcbuilder.errors import TorizonCoreBuilderError, InvalidStateError

log = logging.getLogger("torizon." + __name__)


def combine_image(image_dir, bundle_dir, output_directory,
                  tezi_props):

    files_to_add = []
    additional_size = 0
    if bundle_dir is not None:
        files_to_add = DOCKER_FILES_TO_ADD
        target_name_file = os.path.join(bundle_dir, TARGET_NAME_FILENAME)
        if not os.path.exists(target_name_file):
            with open(target_name_file, 'w') as target_name_fd:
                target_name_fd.write("docker-compose.yml")
            set_output_ownership(bundle_dir)
        additional_size = get_additional_size(bundle_dir, files_to_add)
        if additional_size is None:
            raise TorizonCoreBuilderError(
                "Docker Container bundle missing, use bundle sub-command.")

    if output_directory is None:
        log.info("Updating TorizonCore image in place.")
        output_directory = image_dir
    else:
        # Fail when output directory exists like deploy does.
        if os.path.exists(output_directory):
            raise InvalidStateError(
                f"Output directory {output_directory} must not exist.")
        log.info("Creating copy of TorizonCore source image.")
        shutil.copytree(image_dir, output_directory)

    # Notice that the present function can be used simply for updating the
    # metadata and not necessarily to add containers (so the function name
    # may not fit very well anymore).
    if files_to_add:
        log.info("Combining TorizonCore image with Docker Container bundle.")

    # log.debug(
    #     f"combine: bundledir={bundle_dir}, "
    #     f"outdir={output_directory}, imgname={image_name}, "
    #     f"imgdesc={image_description}, licfile={licence_file}, "
    #     f"relnotes={release_notes_file}, addsize={additional_size}")
    combine_params = {
        "bundle_dir": bundle_dir,
        "files_to_add": files_to_add,
        "additional_size": additional_size,
        "output_dir": output_directory,
        "tezi_props": tezi_props
    }

    combine_single_image(**combine_params)
