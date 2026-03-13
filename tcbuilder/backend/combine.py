"""
Backend handling for the combine subcommand
"""

import os
import shutil
import logging
import re
import datetime

import fnmatch
import subprocess

from tezi.image import ImageConfig
from tcbuilder.backend.common import \
    (set_output_ownership, check_licence_acceptance, run_with_loading_animation,
     open_disk_image, get_tar_compress_program_options, DOCKER_BUNDLE_TARNAME)
from tcbuilder.errors import InvalidStateError, InvalidDataError, TorizonCoreBuilderError

log = logging.getLogger("torizon." + __name__)

TARGET_NAME_FILENAME = "target_name"
DOCKER_FILES_TO_ADD = [
    "docker-compose.yml:/ostree/deploy/torizon/var/sota/storage/docker-compose/",
    TARGET_NAME_FILENAME + ":/ostree/deploy/torizon/var/sota/storage/docker-compose/"
]
DOCKER_STORAGE_DESTINATION = "/ostree/deploy/torizon/var/lib/docker/"
DOCKER_STORAGE_DIRNAME = "docker-storage"

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

# Disk size increase factor on top of filesystem size increase
DISK_INCREASE_FACTOR = 1.20
# Fixed disk size increase
DISK_FIXED_INCREASE_KB = 200*1024 # 200 MiB
# Maximum allowed ratio between required and available root filesystem space.
# If higher than that, the disk size will be increased.
MAX_REQ_AVAIL_RATIO = 0.98


def check_docker_storage_file(bundle_dir):
    """
    Search in bundle_dir if there is a file named DOCKER_BUNDLE_TARNAME*
    e.g. DOCKER_BUNDLE_TARNAME, DOCKER_BUNDLE_TARNAME.xz, DOCKER_BUNDLE_TARNAME.gz, etc.
    """
    for filename in os.listdir(bundle_dir):
        if fnmatch.fnmatch(filename, f"{DOCKER_BUNDLE_TARNAME}*"):
            return filename
    return None


def set_autoreboot(output_dir, include):
    """Set autoreboot feature in TEZI image."""

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


def add_files_to_tezi(tezidir, image_json_filename, filelist, tezi_props):
    """Add files in filelist to a Toradex Easy Installer image directory."""

    config_fname = os.path.join(tezidir, image_json_filename)
    config = ImageConfig(config_fname)

    if config.search_filelist(src=DOCKER_BUNDLE_TARNAME):
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
    """Update Toradex Easy Installer metadata present in image.json."""

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
    version = add_files_to_tezi(**add_files_params)

    return version


def combine_single_tezi_image(bundle_dir, files_to_add, output_dir, tezi_props):
    """Add files in bundle_dir to TEZI image according to files_to_add list."""

    for prop in tezi_props:
        assert prop in TEZI_PROPS, f"Unknown property {prop} to combine_single_image"

    for filename in files_to_add:
        filename = filename.split(":")[0]
        shutil.copy(os.path.join(bundle_dir, filename),
                    os.path.join(output_dir, filename))

    return update_tezi_files(output_dir, tezi_props, files_to_add)


def check_combine_files(bundle_dir, *, untar_storage=False):
    """
    Verify if the bundle directory has the required files, and optionally unpack the docker
    storage tarfile.
    """

    files_to_add = []
    if bundle_dir is not None:
        files_to_add = DOCKER_FILES_TO_ADD.copy()
        target_name_file = os.path.join(bundle_dir, TARGET_NAME_FILENAME)

        if not os.path.exists(target_name_file):
            with open(target_name_file, "w", encoding="utf-8") as target_name_fd:
                target_name_fd.write("docker-compose.yml")
            set_output_ownership(bundle_dir)

        for filename in files_to_add:
            filename = filename.split(":", maxsplit=1)[0]
            filename_path = os.path.join(bundle_dir, filename)
            if not os.path.exists(filename_path):
                log.error("Error: %s not found in bundle directory.", filename)
                return None

        docker_storage_filename = check_docker_storage_file(bundle_dir)
        if docker_storage_filename is not None:
            if untar_storage:
                unpack_docker_storage(docker_storage_filename, files_to_add, bundle_dir)
            else:
                files_to_add.append(f"{docker_storage_filename}:{DOCKER_STORAGE_DESTINATION}:true")
        else:
            log.error("Error: %s not found in bundle directory.", DOCKER_BUNDLE_TARNAME)
            return None

    return files_to_add


def combine_tezi_image(image_dir, bundle_dir, output_directory, tezi_props, force):
    """
    Combine a container bundle to a Toradex Easy Installer image by copying its contents to the
    image directory and add instructions in image.json to copy them to the device during
    installation.

    :param image_path: Path of the Toradex Easy Installer image.
    :param bundle_dir: Path of the container bundle directory.
    :param output_path: Path where the resulting image directory will be created.
    :param tezi_props: TEZI-specific metadata dictionary to be added in the output image.
    :param force: Overwrite output directory if it already exists.
    """

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
    """
    Combine a container bundle to a raw disk image by copying its contents to the image root
    filesystem. If the size of the container bundle exceeds the available space in root,
    then the disk image will be resized beforehand.

    :param image_path: Path of the input raw disk image.
    :param bundle_dir: Path of the container bundle directory.
    :param output_path: Path where the resulting raw disk image will be created.
    :param rootfs_label: Filesystem label of the root partition.
    :param force: Overwrite output file if it already exists.
    """

    delete_on_error = True
    if (output_path is None or output_path == image_path) and force:
        log.info("Updating Torizon OS raw image in place.")
        delete_on_error = False
        output_path = image_path
    else:
        if os.path.isfile(output_path):
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

    files_to_add = check_combine_files(bundle_dir, untar_storage=True)

    if not files_to_add:
        if delete_on_error and os.path.isfile(output_path):
            log.info("Removing '%s'", output_path)
            os.remove(output_path)
        raise TorizonCoreBuilderError("Some required bundle files were not found. Aborting.")

    req_space_kb = get_bundle_size_kb(files_to_add, bundle_dir)

    with open_disk_image(output_path, delete_on_error=delete_on_error) as gfs:
        root_partition = gfs.findfs_label(rootfs_label)
        gfs.mount(root_partition, "/")
        statvfs_dict = gfs.statvfs("/")
        root_avail_kb = statvfs_dict['bsize'] * statvfs_dict['bavail'] / 1024

        log.info(f"Required free space in root filesystem: {req_space_kb/1024:.2f} MiB")
        log.info(f"Available space in root filesystem: {root_avail_kb/1024:.2f} MiB")

        req_avail_ratio = req_space_kb / root_avail_kb
        if req_avail_ratio <= MAX_REQ_AVAIL_RATIO:
            # Contents fit in root filesystem, add them and return
            copy_to_mounted_root(gfs, files_to_add, bundle_dir)
            return

    # Contents don't fit (or barely fit) in root filesystem, disk needs to be increased.
    extra_disk_size_kb = DISK_FIXED_INCREASE_KB
    if req_avail_ratio > 1:
        extra_disk_size_kb += int((req_space_kb - root_avail_kb) * DISK_INCREASE_FACTOR)

    log.info(f"Output disk will be increased by {extra_disk_size_kb/1024:.2f} MiB")
    subprocess.check_output(["truncate", "-s", f"+{extra_disk_size_kb}K", output_path])

    tmp_image = None
    if output_path == image_path:
        # The build command uses in-place modification.
        # virt-resize doesn't support that, so we need to create a temporary copy.
        tmp_image = output_path + ".not_bundled"
        log.debug("Copying '%s' -> '%s' for virt-resize.", output_path, tmp_image)
        shutil.copyfile(output_path, tmp_image)
        image_path = tmp_image

    try:
        expand_disk_partition(image_path, root_partition, output_path)
    finally:
        if tmp_image and os.path.isfile(tmp_image):
            log.debug("Deleting '%s'", tmp_image)
            os.remove(tmp_image)

    with open_disk_image(output_path, delete_on_error=delete_on_error) as gfs:
        gfs.mount(root_partition, "/")
        copy_to_mounted_root(gfs, files_to_add, bundle_dir)


def expand_disk_partition(src_image, src_partition, dst_image):
    """
    Using virt-resize, expand a given partition on src_image and copy the end result into
    dst_image. The expanded partition will fill any extra disk space in dst_image.

    virt-resize will automatically resize ext4 filesystems after expanding the partition.
    """

    log.info("Starting virt-resize...")
    print("------------------------------------------------------------")
    expandcmd = ["virt-resize", "--format", "raw", "--expand"]
    expandcmd.extend([src_partition, src_image, dst_image])
    subprocess.run(expandcmd, check=True)
    print("------------------------------------------------------------")


def get_bundle_size_kb(files_to_add, src_dir):
    """Get total size of files/directories in a files_to_add list from a source directory."""

    size_kb = 0
    for src_dest_untar in files_to_add:
        src_dest_untar = src_dest_untar.split(":")
        filename = src_dest_untar[0]
        file_path = os.path.join(src_dir , filename)

        if not os.path.exists(file_path):
            raise InvalidDataError(f'Error: "{filename}" not found in "{src_dir}". Aborting.')

        if os.path.isdir(file_path):
            filesize_kb = subprocess.check_output(["du", "-s", file_path], text=True)
            filesize_kb = int(filesize_kb.split('\t', maxsplit=1)[0])
        else:
            filesize_kb = os.path.getsize(file_path) / 1024

        size_kb += filesize_kb

    return size_kb


def copy_to_mounted_root(gfs, files_to_add, contents_dir):
    """Copy list of files inside a directory to a mounted filesystem in '/'."""

    log.info("Adding files to disk root.")
    for src_dest_untar in files_to_add:

        src_dest_untar = src_dest_untar.split(":")
        list_len = len(src_dest_untar)
        untar = False

        if list_len < 2:
            raise TorizonCoreBuilderError(
                "Internal error: DOCKER_FILES_TO_ADD not properly formatted. Aborting.")

        if list_len >= 3:
            untar = src_dest_untar[2]
            untar = untar.lower() == 'true'

        src, dest = src_dest_untar[0:2]

        # Create destination path in root if it doesn't exist already
        if not gfs.is_dir(dest):
            gfs.mkdir_p(dest)

        if untar:
            run_with_loading_animation(
                func=gfs.tar_in,
                args=(os.path.join(contents_dir, src), dest),
                kwargs={'compress': TAR_EXT_TO_COMPRESSION_TYPE[os.path.splitext(src)[1]]},
                loading_msg=f"  Unpacking {src} to {dest} ...")
        else:
            run_with_loading_animation(
                func=gfs.copy_in,
                args=(os.path.join(contents_dir, src), dest),
                loading_msg=f"  Copying {src} to {dest} ...")


def unpack_docker_storage(docker_storage_filename, files_to_add, bundle_dir):
    """Unpack the docker storage tarfile and add its contents to the files_to_add list."""

    docker_storage_path = os.path.join(bundle_dir, docker_storage_filename)
    extracted_path = os.path.join(bundle_dir, DOCKER_STORAGE_DIRNAME)

    if os.path.isdir(extracted_path):
        shutil.rmtree(extracted_path)
    os.mkdir(extracted_path)

    log.info("Unpacking '%s'", docker_storage_filename)
    tar_compress_options = get_tar_compress_program_options(docker_storage_path)
    tarcmd = [
        "tar",
        "-xf", docker_storage_path,
        "-C", extracted_path,
    ] + tar_compress_options
    subprocess.check_output(tarcmd, stderr=subprocess.STDOUT)

    for content in os.listdir(extracted_path):
        files_to_add.append(
            f"{os.path.join(DOCKER_STORAGE_DIRNAME, content)}:{DOCKER_STORAGE_DESTINATION}")
