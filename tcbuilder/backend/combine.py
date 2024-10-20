import os
import shutil
import logging
import re
import datetime

import guestfs

from tezi.image import ImageConfig
from tcbuilder.backend.common import \
    (set_output_ownership, check_licence_acceptance,
     run_with_loading_animation, DOCKER_BUNDLE_FILENAME, DOCKER_BUNDLE_FILENAME_UNCOMPRESSED)
from tcbuilder.errors import InvalidStateError, InvalidDataError, TorizonCoreBuilderError

log = logging.getLogger("torizon." + __name__)

TARGET_NAME_FILENAME = "target_name"
DOCKER_FILES_TO_ADD = [
    "docker-compose.yml:/ostree/deploy/torizon/var/sota/storage/docker-compose/",
    DOCKER_BUNDLE_FILENAME + ":/ostree/deploy/torizon/var/lib/docker/:true",
    TARGET_NAME_FILENAME + ":/ostree/deploy/torizon/var/sota/storage/docker-compose/"
]

DOCKER_FILES_TO_ADD_TO_RAW = [
    "docker-compose.yml:/ostree/deploy/torizon/var/sota/storage/docker-compose/",
    DOCKER_BUNDLE_FILENAME_UNCOMPRESSED + ":/ostree/deploy/torizon/var/lib/docker/:true",
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

TAR_EXT_TO_COMPRESSION_TYPE = {
    ".gz": "gzip",
    ".gzip": "gzip",
    ".tgz": "gzip",
    ".xz": "xz",
    ".bz2": "bzip2",
    ".lzo": "lzop",
    ".tar": None
}


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


def update_tezi_files(image_dir, tezi_props, files_to_add=None):
    licence_file_bn = None
    if tezi_props.get("licence_file") is not None:
        licence_file = tezi_props.get("licence_file")
        licence_file_bn = os.path.basename(licence_file)
        shutil.copy(licence_file, os.path.join(image_dir, licence_file_bn))
        tezi_props["licence_file"] = licence_file_bn

    release_notes_file_bn = None
    if tezi_props.get("release_notes_file") is not None:
        release_notes_file = tezi_props.get("release_notes_file")
        release_notes_file_bn = os.path.basename(release_notes_file)
        shutil.copy(release_notes_file,
                    os.path.join(image_dir, release_notes_file_bn))
        tezi_props["release_notes_file"] = release_notes_file_bn

    version = None

    image_json_filepath = os.path.join(image_dir, "image.json")

    add_files_params = {
        "tezidir": image_dir,
        "image_json_filename": image_json_filepath,
        "filelist": files_to_add,
        "tezi_props": tezi_props
    }
    version = add_files(**add_files_params)

    return version


def combine_single_tezi_image(bundle_dir, files_to_add, output_dir, tezi_props):
    for prop in tezi_props:
        assert prop in TEZI_PROPS, f"Unknown property {prop} to combine_single_image"

    for filename in files_to_add:
        filename = filename.split(":")[0]
        shutil.copy(os.path.join(bundle_dir, filename),
                    os.path.join(output_dir, filename))

    return update_tezi_files(output_dir, tezi_props, files_to_add)


def check_combine_files(bundle_dir, is_for_raw_image=False):

    files_to_add = []
    if bundle_dir is not None:
        if not is_for_raw_image:
            files_to_add = DOCKER_FILES_TO_ADD
        else:
            files_to_add = DOCKER_FILES_TO_ADD_TO_RAW

        target_name_file = os.path.join(bundle_dir, TARGET_NAME_FILENAME)
        if not os.path.exists(target_name_file):
            with open(target_name_file, 'w') as target_name_fd:
                target_name_fd.write("docker-compose.yml")
            set_output_ownership(bundle_dir)

        for filename in files_to_add:
            filename = filename.split(":")[0]
            filename_path = os.path.join(bundle_dir, filename)
            if not os.path.exists(filename_path):
                log.error(f"Error: {filename} not found in bundle directory.")
                return None

    return files_to_add


def combine_tezi_image(image_dir, bundle_dir, output_directory, tezi_props, force):

    check_licence_acceptance(image_dir, tezi_props)

    files_to_add = check_combine_files(bundle_dir)

    if (output_directory is None or output_directory == image_dir) and force:
        log.info("Updating Torizon OS image in place.")
        output_directory = image_dir
    else:
        if os.path.exists(output_directory):
            if force:
                log.info(f"Removing existing directory '{output_directory}'")
                shutil.rmtree(output_directory)
            else:
                raise InvalidStateError(
                    f"Directory {output_directory} already exists. "
                    "Rename output or use --force to overwrite.")

        log.info("Creating copy of source image.")
        shutil.copytree(image_dir, output_directory)

    # Notice that the present function can be used simply for updating the
    # metadata and not necessarily to add containers (so the function name
    # may not fit very well anymore).
    if files_to_add:
        log.info("Combining Torizon OS image with Docker Container bundle.")
    else:
        if output_directory != image_dir:
            log.info("Removing copy of source image.")
            shutil.rmtree(output_directory)
        raise TorizonCoreBuilderError("Some required bundle files were not found. Aborting.")

    combine_params = {
        "bundle_dir": bundle_dir,
        "files_to_add": files_to_add,
        "output_dir": output_directory,
        "tezi_props": tezi_props
    }
    combine_single_tezi_image(**combine_params)


def combine_raw_image(image_path, bundle_dir, output_path, rootfs_label, force):

    files_to_add = check_combine_files(bundle_dir, True)

    if files_to_add:

        if (output_path is None or output_path == image_path) and force:
            log.info("Updating Torizon OS raw image in place.")
            output_path = image_path
        else:
            if os.path.exists(output_path):
                if force:
                    log.info(f"Removing existing file '{output_path}'")
                    os.remove(output_path)
                else:
                    raise InvalidStateError(
                        f"File {output_path} already exists. "
                        "Rename output or use --force to overwrite.")

            run_with_loading_animation(
                func=shutil.copyfile,
                args=(image_path, output_path),
                loading_msg="Creating copy of source image...")

        log.info("Combining Torizon OS image with Docker Container bundle.")

        try:
            gfs = guestfs.GuestFS(python_return_dict=True)
            gfs.add_drive_opts(output_path, format="raw")
            run_with_loading_animation(
                func=gfs.launch,
                loading_msg="Initializing image...")
            if len(gfs.list_partitions()) < 1:
                raise TorizonCoreBuilderError(
                    "Image doesn't have any partitions or it's not a valid raw image. Aborting.")

            # Get partition number from ext4 fs called rootfs_label in disk image (.wic/.img)
            rootfs_partition = gfs.findfs_label(rootfs_label)
            log.info(f"  rootfs partition found: {rootfs_partition} "
                     f"(filesystem label: {rootfs_label})")
            gfs.mount(rootfs_partition, "/")

            log.info("Adding files to rootfs.")
            for src_dest_untar in files_to_add:

                src_dest_untar = src_dest_untar.split(":")
                list_len = len(src_dest_untar)
                untar = False

                if list_len < 2:
                    raise TorizonCoreBuilderError(
                        "Internal error: DOCKER_FILES_TO_ADD not properly formatted. Aborting.")

                if list_len >= 3:
                    untar = src_dest_untar[2]
                    untar = (untar.lower() == 'true')

                src, dest = src_dest_untar[0:2]

                # Create destination path in rootfs if it doesn't exist
                if not gfs.is_dir(dest):
                    gfs.mkdir_p(dest)

                if untar:
                    run_with_loading_animation(
                        func=gfs.tar_in,
                        args=(os.path.join(bundle_dir, src), dest),
                        kwargs={'compress': TAR_EXT_TO_COMPRESSION_TYPE[os.path.splitext(src)[1]]},
                        loading_msg=f"  Unpacking {src} to {dest} ...")

                else:
                    run_with_loading_animation(
                        func=gfs.copy_in,
                        args=(os.path.join(bundle_dir, src), dest),
                        loading_msg=f"  Copying {src} to {dest} ...")

            gfs.shutdown()
            gfs.close()
        except RuntimeError as gfserr:
            if output_path != image_path:
                log.info("Removing copy of source image.")
                os.remove(output_path)
            if gfs:
                gfs.close()
            if f"unable to resolve 'LABEL={rootfs_label}'" in str(gfserr):
                raise TorizonCoreBuilderError(
                    f"Filesystem with label '{rootfs_label}' not found in image. Aborting.")
            raise TorizonCoreBuilderError(f"guestfs: {gfserr.args[0]}")
    else:
        raise TorizonCoreBuilderError("Some required bundle files were not found. Aborting.")
