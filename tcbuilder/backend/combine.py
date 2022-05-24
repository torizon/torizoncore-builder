import os
import shutil
import logging
import re
import datetime

from tezi.image import ImageConfig
from tcbuilder.backend.common import \
    (set_output_ownership, check_licence_acceptance,
     DOCKER_BUNDLE_FILENAME)
from tcbuilder.errors import InvalidStateError, InvalidDataError

log = logging.getLogger("torizon." + __name__)

TARGET_NAME_FILENAME = "target_name"
DOCKER_FILES_TO_ADD = [
    "docker-compose.yml:/ostree/deploy/torizon/var/sota/storage/docker-compose/",
    DOCKER_BUNDLE_FILENAME + ":/ostree/deploy/torizon/var/lib/docker/:true",
    TARGET_NAME_FILENAME + ":/ostree/deploy/torizon/var/sota/storage/docker-compose/"
]

TEZI_PROPS = [
    "name",
    "description",
    "accept_licence",
    "autoinstall",
    "autoreboot",
    "licence_file",
    "release_notes_file"
]


def set_autoreboot(output_dir, include):
    wrapup_sh = os.path.join(os.path.abspath(output_dir), 'wrapup.sh')

    with open(wrapup_sh, "r", encoding="utf-8") as infile:
        lines = infile.readlines()

    exit_occurrences = [
        (lineidx, line) for (lineidx, line) in enumerate(lines)
        if re.match(r"^\s*exit\s+0\s*", line)
    ]

    if not exit_occurrences:
        log.warning("no 'exit 0' found")
        return

    # Check if autoreboot is already set
    autoreboot_occurrences = [
        (lineidx, line) for (lineidx, line) in enumerate(lines)
        if re.match(r"^\s*reboot\s+-f\s+#\s+torizoncore-builder\s+generated\s*", line)
    ]

    if include:
        if autoreboot_occurrences:
            log.debug("autoreboot is already set")
            return
        last_exit_occurrence = exit_occurrences[-1]

        if last_exit_occurrence[0] < len(lines) - 2:
            log.warning("'exit 0' not at the end of the file")
            return

        # Add extra line(s) before last exit:
        lines.insert(last_exit_occurrence[0], "reboot -f  # torizoncore-builder generated\n")
    else:
        if not autoreboot_occurrences:
            log.debug("autoreboot is already unset")
            return
        lines.pop(autoreboot_occurrences[0][0])

    with open(wrapup_sh, "w", encoding="utf-8") as output:
        output.writelines(lines)


def add_files(tezidir, image_json_filename, filelist, tezi_props):

    config_fname = os.path.join(tezidir, image_json_filename)
    config = ImageConfig(config_fname)

    if config.search_filelist(src=DOCKER_BUNDLE_FILENAME):
        raise InvalidDataError(
            "Currently it is not possible to customize the containers of a base "
            "image already containing container images")

    if filelist:
        config.add_files(
            filelist, image_dir=tezidir, update_size=True, fail_src_present=True)

    # ---
    # FIXME: The code below should be factored out (separate adding files from setting props):
    # ---
    if tezi_props.get("name") is None:
        name_extra = ["", " with Containers"][bool(filelist)]
        config["name"] = config["name"] + name_extra
    else:
        config["name"] = tezi_props["name"]

    if tezi_props.get("description") is not None:
        config["description"] = tezi_props["description"]

    # Rather ad-hoc for now, we probably want to give the user more control
    # FIXME: Here we assume that a filelist is always adding containers to the image.
    version_extra = [".modified", ".container"][bool(filelist)]
    config["version"] = config["version"] + version_extra
    config["release_date"] = datetime.datetime.today().strftime("%Y-%m-%d")

    if tezi_props.get("licence_file") is not None:
        config["license"] = tezi_props["licence_file"]

    if tezi_props.get("release_notes_file") is not None:
        config["releasenotes"] = tezi_props["release_notes_file"]

    if tezi_props.get("autoinstall") is not None:
        config["autoinstall"] = tezi_props["autoinstall"]

    config.save()

    # Properties that are not in "image.json":
    if tezi_props.get("autoreboot") is not None:
        set_autoreboot(tezidir, tezi_props["autoreboot"])

    return config["version"]


def combine_single_image(bundle_dir, files_to_add, output_dir, tezi_props):
    for prop in tezi_props:
        assert prop in TEZI_PROPS, f"Unknown property {prop} to combine_single_image"

    for filename in files_to_add:
        filename = filename.split(":")[0]
        shutil.copy(os.path.join(bundle_dir, filename),
                    os.path.join(output_dir, filename))

    licence_file_bn = None
    if tezi_props.get("licence_file") is not None:
        licence_file = tezi_props.get("licence_file")
        licence_file_bn = os.path.basename(licence_file)
        shutil.copy(licence_file, os.path.join(output_dir, licence_file_bn))
        tezi_props["licence_file"] = licence_file_bn

    release_notes_file_bn = None
    if tezi_props.get("release_notes_file") is not None:
        release_notes_file = tezi_props.get("release_notes_file")
        release_notes_file_bn = os.path.basename(release_notes_file)
        shutil.copy(release_notes_file,
                    os.path.join(output_dir, release_notes_file_bn))
        tezi_props["release_notes_file"] = release_notes_file_bn

    version = None

    image_json_filepath = os.path.join(output_dir, "image.json")

    add_files_params = {
        "tezidir": output_dir,
        "image_json_filename": image_json_filepath,
        "filelist": files_to_add,
        "tezi_props": tezi_props
    }
    version = add_files(**add_files_params)

    return version


def combine_image(image_dir, bundle_dir, output_directory, tezi_props):

    check_licence_acceptance(image_dir, tezi_props)

    files_to_add = []
    if bundle_dir is not None:
        files_to_add = DOCKER_FILES_TO_ADD
        target_name_file = os.path.join(bundle_dir, TARGET_NAME_FILENAME)
        if not os.path.exists(target_name_file):
            with open(target_name_file, 'w') as target_name_fd:
                target_name_fd.write("docker-compose.yml")
            set_output_ownership(bundle_dir)

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

    combine_params = {
        "bundle_dir": bundle_dir,
        "files_to_add": files_to_add,
        "output_dir": output_directory,
        "tezi_props": tezi_props
    }
    combine_single_image(**combine_params)
