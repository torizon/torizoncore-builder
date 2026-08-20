"""
Backend handling for build subcommand
"""

import base64
import binascii
import http.server
import json
import logging
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import uuid

from zipfile import ZipFile
from tempfile import TemporaryDirectory

import fabric

from tcbuilder.backend.common import (get_rootfs_tarball, get_tar_compress_program_options,
                                      set_output_ownership, run_with_loading_animation,
                                      get_tezi_image_version, open_disk_image, make_feed_url,
                                      fetch_remote, RAW_PROP_TO_ARGNAME, DEFAULT_RAW_ROOTFS_LABEL,
                                      DEFAULT_RAW_SECTOR_SIZE,
                                      SECBOOT_ARTIFACTS_DIR, REMOTE_CMD_TIMEOUT, TAR_EXT_TO_PROGRAM,
                                      OSTREE_SOTA_DIR_PATH, LEGACY_VARIANT_PREFIX, VARIANT_PREFIX,
                                      SYNAIMG_MACHINES)

from tcbuilder.backend import ostree
from tcbuilder.backend.secboot import DEFAULT_TCB_SIGNING_FILES_TARNAME, BOOTLOADER_CONTAINER_NAME
from tcbuilder.errors import (TorizonCoreBuilderError, InvalidArgumentError, FileContentMissing,
                              InvalidStateError, OperationFailureError, PathNotExistError,
                              UnsupportedImageFeature)
from tezi.image import ImageConfig, DEFAULT_IMAGE_JSON_FILENAME
from tezi.errors import TeziError

log = logging.getLogger("torizon." + __name__)

PROV_IMPORT_DIRNAME = "import"
PROV_ONLINE_DATA_FILENAME = "auto-provisioning.json"
PROV_DATA_FILENAME = "provisioning-data.tar.gz"

VERSION_TO_YOCTO_MAP = {
    "dunfell": "dunfell-5.x.y",
    "kirkstone": "kirkstone-6.x.y",
    "scarthgap": "scarthgap-7.x.y"
}

LAST_DEPRECATED_IMAGE_MAJOR = 5
LAST_DEPRECATED_IMAGE_NAME = "TorizonCore"
LAST_DEPRECATED_IMAGE_VERSION = "5.7.2"
LAST_TCB_VERSION_SUPPORTING_DEPRECATED = "3.10.0"

HIBERNATION_MODE_URL = (
    "https://developer.toradex.com/"
    "torizon/torizon-platform/devices-fleet-management"
    "#hibernation-mode"
)

def serve(images_directory):
    """
    Serve TorizonCore TEZI images via HTTP so they can be installed directly
    from TorizonCore Builder to any SoC using zeroconf technologies.

    :param images_directory: TorizonCore TEZI images directory.
    """

    image_list_file = os.path.join(images_directory, "image_list.json")
    if not os.path.exists(image_list_file):
        logging.error(f"Error: The Toradex Easy Installer '{image_list_file}' "
                      f"does not exist inside '{images_directory}' directory.")
        sys.exit(1)

    class Handler(http.server.SimpleHTTPRequestHandler):
        """Handler for the HTTP server."""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=images_directory, **kwargs)

        def log_message(self, *args):
            path = args[1]
            code = "OK" if args[2] == "200" else "Error"
            log.debug(f"{path} {code}")

        def do_GET(self):
            """
            Insert a 'Cache-Control' HTTP header in each response for
            every '*.json' file requested previously so Toradex Easy
            Installer will ask again for JSON files which it could
            had already been asked in the pass because of multiple
            executions of the TorizonCore Builder 'serve' command.
            """
            if self.path.endswith('.json'):
                # TODO: Review this implementation (use "with").
                # pylint: disable-next=unspecified-encoding,consider-using-with
                fd_json = open(os.path.join(images_directory, self.path[1:])).read()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(fd_json)))
                self.send_header("Cache-Control", "no-store,max-age=0")
                self.end_headers()
                self.wfile.write(fd_json.encode("utf-8"))
            else:
                super().do_GET()

    avahi = None
    try:
        # The Avahi daemon should respond for zeroconf TEZI services
        # pylint: disable-next=consider-using-with
        avahi = subprocess.Popen(["avahi-daemon"],
                                 stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)

        # Serve TEZI images directory via HTTP
        log.info("Currently serving Toradex Easy Installer images from "
                 f"'{images_directory}'. You may now run Toradex Easy Installer "
                 "on your Toradex Device and install these images. Press "
                 "'Ctrl+C' to quit and stop serving these images.\n")
        with http.server.ThreadingHTTPServer(("", 80), Handler) as httpd:
            httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if avahi is not None:
            avahi.terminate()
            avahi.wait()

def get_device_img_info(r_host, r_username, r_password, r_port):
    """
    Access a "live" Torizon OS device and get some information about it.

    :param r_host: Torizon OS machine name.
    :param r_username: Torizon OS remote username.
    :param r_password: Torizon OS remote password.
    :returns: Dictionary with information about its installed image (version, variant, etc.).
    """

    connection_args = {
        "host": r_host,
        "user": r_username,
        "port": r_port,
        "connect_kwargs": {"password": r_password}
    }
    with fabric.Connection(**connection_args) as conn:
        # Check if OSTree is present on the device
        result = conn.run(
            r"ostree admin status | sed -ne 's/^ *\* .* \([0-9a-f]\+\)\.[0-9]\+/\1/p'",
            hide=True, timeout=REMOTE_CMD_TIMEOUT
        )
        hash_stdout = result.stdout.strip()
        if result.failed or not hash_stdout:
            raise InvalidStateError("OSTree not present on host device. Aborting.")

        result = conn.run(
            f"ostree show {hash_stdout} --print-metadata-key oe.machine",
            hide=True, timeout=REMOTE_CMD_TIMEOUT
        )
        machine = result.stdout.strip("\"'\n ")

        result = conn.run("test -f /etc/os-release",
                          warn=True, hide=True, timeout=REMOTE_CMD_TIMEOUT)
        if result.failed:
            raise PathNotExistError("/etc/os-release not found in remote device. Aborting.")
        # Gather information from device /etc/os-release.
        sftp = conn.sftp()
        if sftp is None:
            raise OperationFailureError("Unable to create SSH connection.")
        release_file = sftp.file("/etc/os-release")
        file_contents = release_file.read().decode("utf-8")

    img_info = {
        "version": None,
        "release": None,
        "machine": machine,
        "distro": None,
        "variant": None,
        "build-number": None,
        "build-date": None
    }
    result = re.search(r'^VARIANT="?(\w.*)$', file_contents, re.MULTILINE)
    if result is not None:
        img_info["variant"] = result.group(1).strip("\"' ").lower()
    else:
        raise FileContentMissing("Unable to parse image variant from /etc/os-release. Aborting.")

    # Yocto builds based on Poky store the distro on the os-release ID field
    result = re.search(r'^ID="?(\w.*)$', file_contents, re.MULTILINE)
    if result is not None:
        img_info["distro"] = result.group(1).strip("\"' ")
    else:
        raise FileContentMissing("Unable to parse image distro from /etc/os-release. Aborting.")

    result = re.search(
        r'^VERSION_ID="?(\d+\.\d+\.\d+)(-devel-\d+)?-build\.(\d+)', file_contents, re.MULTILINE)
    if result is not None:
        img_info["version"] = result.group(1)
        major = int(img_info["version"].split(".")[0])
        if major < 7:
            img_info["variant"] = LEGACY_VARIANT_PREFIX + img_info["variant"]
        else:
            img_info["variant"] = VARIANT_PREFIX + img_info["variant"]

        img_info["build-number"] = result.group(3)
        if result.group(2) is None:
            # No -devel-* field, quarterly release
            img_info["release"] = "quarterly"
        else:
            img_info["build-date"] = result.group(2)[7:]
            if len(img_info["build-date"]) == 6:
                # Monthly has date in yyyymm format (6 digits)
                img_info["release"] = "monthly"
            else:
                # Nightly has date in yyyymmdd format (8 digits)
                img_info["release"] = "nightly"
    else:
        raise FileContentMissing("Unable to parse image version from /etc/os-release. Aborting.")

    return img_info


def download_tos_image(r_host, r_username, r_password, r_port, *,
                       download_dir, tezi_dir, src_sysroot_dir, src_ostree_archive_dir):
    """
    Download appropriate Torizon OS image based on target device.
    """

    img_info = get_device_img_info(r_host, r_username, r_password, r_port)
    url, filename = make_feed_url(img_info)

    if img_info["machine"] in SYNAIMG_MACHINES:
        log.warning("Image for %s is in SYNAIMG format.", img_info["machine"])
        log.warning("TorizonCore Builder cannot handle SYNAIMG directly.")
        log.warning("URL: %s", url)
        raise UnsupportedImageFeature(
            "Please manually download the image then convert it to a .img file with the included "
            "syna2img.pyz program. Pass the result to the 'images unpack' command.")

    if download_dir is not None and not os.path.isdir(download_dir):
        os.makedirs(download_dir)
        set_output_ownership(download_dir, set_parents=True)

    # Download and unpack image
    log.info(f"Downloading image from: {url}\n")
    log.info("The download may take some time. Please wait...")
    filename, _ = fetch_remote(url, filename, download_dir=download_dir)
    set_output_ownership(filename)
    import_local_image(filename, tezi_dir, src_sysroot_dir, src_ostree_archive_dir)


def unpack_tezi_rootfs_tarball(image_dir, sysroot_dir):
    """Extract the root fs tarball from the image into the sysroot directory"""

    tarfile = get_rootfs_tarball(image_dir)

    # pylint: disable=line-too-long
    # This is a OSTree bare repository. Care must been taken to preserve all
    # file system attributes. Python tar does not support xattrs, so use GNU tar
    # here
    # See: https://dev.gentoo.org/~mgorny/articles/portability-of-tar-features.html#extended-file-metadata
    # pylint: enable=line-too-long
    tarcmd = [
        "tar",
        "--xattrs", "--xattrs-include=*",
        "-xhf", tarfile,
        "-C", sysroot_dir,
    ] + get_tar_compress_program_options(tarfile)
    log.debug(f"Running tar command: {shlex.join(tarcmd)}")
    subprocess.check_output(tarcmd, stderr=subprocess.STDOUT)

    # Remove the tarball since we have it unpacked now
    os.unlink(tarfile)


def unpack_local_tezi_image(image_dir_or_file, tezi_dir):
    """Handle the unpacking or copying of a Toradex Easy Installer image."""

    if os.path.isfile(image_dir_or_file):
        # This creates tempdir next to tezi_dir to ensure moving files
        # can be efficiently done with a single rename syscall by
        # shutil.move later.
        with tempfile.TemporaryDirectory(dir=os.path.dirname(tezi_dir)) as tempdir:
            tar_compress_options = get_tar_compress_program_options(image_dir_or_file)

            if image_dir_or_file.endswith(".tar") or tar_compress_options:
                log.info("Unpacking Toradex Easy Installer image.")
                tarcmd = [
                    "tar",
                    "-xf", image_dir_or_file,
                    "-C", tempdir,
                ] + tar_compress_options
                log.debug(f"Running tar command: {shlex.join(tarcmd)}")
                subprocess.check_output(tarcmd, stderr=subprocess.STDOUT)
            elif image_dir_or_file.endswith(".zip"):
                log.info("Unzipping Toradex Easy Installer image.")
                with ZipFile(image_dir_or_file, "r") as file:
                    file.extractall(tempdir)
            else:
                raise TorizonCoreBuilderError(
                    f"Unsupported image file type: {image_dir_or_file}")

            contents = os.listdir(tempdir)
            if len(contents) == 1 and os.path.isdir(os.path.join(tempdir, contents[0])):
                shutil.move(os.path.join(tempdir, contents[0]), tezi_dir)
            else:
                shutil.move(tempdir, tezi_dir)

    elif os.path.isdir(image_dir_or_file):
        log.info("Copying Toradex Easy Installer image.")
        log.debug(f"Copy directory {image_dir_or_file} -> {tezi_dir}.")
        shutil.copytree(image_dir_or_file, tezi_dir)
    elif os.path.exists(image_dir_or_file):
        raise TorizonCoreBuilderError(f"Image is not a file or directory: {image_dir_or_file}")
    else:
        raise TorizonCoreBuilderError(f"Image does not exist: {image_dir_or_file}")


def unpack_local_raw_image(image_dir, sysroot_dir, raw_rootfs_label,
                           sector_size=DEFAULT_RAW_SECTOR_SIZE):
    """Extract the root fs from the image into the sysroot directory"""

    if raw_rootfs_label is None:
        raw_rootfs_label = DEFAULT_RAW_ROOTFS_LABEL

    with open_disk_image(image_dir, readonly=True, sector_size=sector_size) as gfs:
        # Get partition number from ext4 fs called raw_rootfs_label in disk image (.wic/.img)
        rootfs_partition = gfs.findfs_label(raw_rootfs_label)
        log.info(f"'{raw_rootfs_label}' partition found: {rootfs_partition}")
        gfs.mount_ro(rootfs_partition, "/")
        run_with_loading_animation(
            func=gfs.copy_out,
            args=("/", sysroot_dir),
            loading_msg="Unpacking image. This may take a few minutes...")


def _make_tezi_extract_dir(tezi_dir):
    """Create target directory where to extract the tezi image"""
    extract_dir = tezi_dir + '.tmp'
    if os.path.exists(extract_dir):
        shutil.rmtree(extract_dir)
    os.mkdir(extract_dir)
    return extract_dir


# pylint: disable-next=too-many-positional-arguments,too-many-locals
def import_local_image(image_dir_or_file, tezi_dir, src_sysroot_dir, src_ostree_archive_dir,
                       raw_rootfs_label=None, raw_sector_size=None):
    """Import local raw/WIC or Toradex Easy Installer image.

    Import local raw/WIC or Toradex Easy installer image (archive file or unpacked
    dir) to be customized. Assuming an empty/non-existing src_sysroot_dir as well
    as src_ostree_archive_dir.
    """
    os.mkdir(src_sysroot_dir)

    if ((image_dir_or_file.lower().endswith(".wic") or
         image_dir_or_file.lower().endswith(".img")) and os.path.isfile(image_dir_or_file)):
        unpack_local_raw_image(image_dir_or_file, src_sysroot_dir, raw_rootfs_label,
                               raw_sector_size or DEFAULT_RAW_SECTOR_SIZE)
    else:
        unpack_local_tezi_image(image_dir_or_file, tezi_dir)

        common_raw_props_args = {
            "raw_rootfs_label": raw_rootfs_label,
            "raw_sector_size": raw_sector_size
        }
        # pylint: disable-next=consider-using-dict-items
        for prop in common_raw_props_args:
            if common_raw_props_args[prop] is not None:
                log.warning(f"Warning: {RAW_PROP_TO_ARGNAME[prop]} "
                            "is specific to raw images. Ignoring.")

        log.info("Unpacking TorizonCore Toradex Easy Installer image.")
        unpack_tezi_rootfs_tarball(tezi_dir, src_sysroot_dir)

    src_sysroot = ostree.load_sysroot(src_sysroot_dir)
    csum, _ = ostree.get_deployment_info_from_sysroot(src_sysroot)

    log.info(f"Importing OSTree revision {csum} from local repository...")
    repo = ostree.create_ostree(src_ostree_archive_dir)
    src_ostree_dir = os.path.join(src_sysroot_dir, "ostree/repo")

    # Copy the original OSTree repo configuration (essential for composefs).
    src_repo = ostree.open_ostree(src_ostree_dir)
    ostree.copy_repo_config(src_repo, repo, keep_core=True)
    ostree.dump_repo_config(repo)

    target_refs = ostree.get_reference_dict(src_ostree_dir, base_csum=csum)
    ostree.pull_local_refs(repo, src_ostree_dir, refs=target_refs, remote="torizon")
    metadata, _, _ = ostree.get_metadata_from_checksum(src_sysroot.repo(), csum)

    if os.path.exists(tezi_dir):
        track_tezi_signed_files(tezi_dir, csum, metadata.get("oe.machine"))
        log.info("Unpacked OSTree from Toradex Easy Installer image:")
    else:
        log.info("Unpacked OSTree from WIC/raw image:")

    log.info("  Commit checksum: %s", csum)
    log.info("  TorizonCore Version: %s", metadata["version"])

    image_major = int(metadata["oe.tdx-major"])

    if image_major <= LAST_DEPRECATED_IMAGE_MAJOR:
        if image_major == LAST_DEPRECATED_IMAGE_MAJOR:
            log.warning("Warning: The last officially supported version of TCB for the "
                        f"{LAST_DEPRECATED_IMAGE_NAME} {LAST_DEPRECATED_IMAGE_MAJOR} series "
                        f"(up to and including {LAST_DEPRECATED_IMAGE_VERSION}) is "
                        f"{LAST_TCB_VERSION_SUPPORTING_DEPRECATED}.")
            log.warning("Newer versions of TCB may work with them, but we don't guarantee support "
                        "for this use case. Proceed at your own risk.")
        else:
            log.warning("Warning: Unsupported image version detected. Proceed at your own risk.")


def check_provdata_presence_in_tezi(input_dir):
    """Determine if input TEZI image already has provisioning data"""

    config_fname = os.path.join(input_dir, DEFAULT_IMAGE_JSON_FILENAME)
    config = ImageConfig(config_fname)
    return config.search_filelist(src=PROV_DATA_FILENAME) is not None


def check_provdata_presence_in_raw_image(gfs):
    """Determine if mounted disk image already has provisioning data."""

    sota_import_dir = OSTREE_SOTA_DIR_PATH + "/import/"
    import_dirs = ["director/", "repo/"]
    for import_dir in import_dirs:
        if not gfs.is_file(sota_import_dir + import_dir + "root.json"):
            return False

    return True


def _prov_get_image_version_raw_image(disk_img, rootfs_label,
                                      sector_size=DEFAULT_RAW_SECTOR_SIZE):
    """Check disk image for any existing provisioning data, also returning the img version.

    :param disk_img: path to disk image.
    :param rootfs_label: Filesystem label of the root partition.

    :return:
        A tuple with the int values of the major, minor and patch number
        of the image, in this order. If unable to determine a number,
        the tuple entry will be 'None'.
    """

    with open_disk_image(disk_img, readonly=True, sector_size=sector_size) as gfs:
        rootfs_partition = gfs.findfs_label(rootfs_label)
        log.info(f"'{rootfs_label}' partition found: {rootfs_partition}")
        gfs.mount_ro(rootfs_partition, "/")
        if check_provdata_presence_in_raw_image(gfs):
            # Currently we do not support inputting an image with provisioning data
            # already present.
            raise InvalidStateError("Input image already contains provisioning data. Aborting.")
        return get_mounted_raw_image_version(gfs)


def get_mounted_raw_image_version(gfs):
    """Get image version of a mounted raw disk image from /etc/os-release of the default deployment

    :param gfs: guestfs object with mounted root filesystem in "/".

    :return:
        A tuple with the int values of the major, minor and patch number
        of the image, in this order. If unable to determine a number,
        the tuple entry will be 'None'.
    """

    result = gfs.glob_expand_opts("/ostree/deploy/torizon/deploy/*.0/etc/os-release")
    if not result:
        log.warning("Warning: Could not find /etc/os-release in deployed OSTree sysroot.")
        return None, None, None

    os_release_txt = gfs.cat(result[0])
    match = re.search(r'^VERSION="?(\d+)\.(\d+)\.(\d+)[-+]', os_release_txt, re.MULTILINE)
    if match is None:
        match = re.search(r'^VERSION_ID="?(\d+)\.(\d+)\.(\d+)[-+]', os_release_txt, re.MULTILINE)
        if match is None:
            return None, None, None

    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def prov_gen_provdata_tarball(output_dir, shared_data, online_data, *,
                              hibernated=False, fleets=None):
    """Generate tarball containing all provisioning data

    The tarball will be stored into the output directory; then it should be
    added to image.json in order to be actually installed on the device by TEZI.

    Throwing errors here will cause output directory to be removed (if the
    operation is not in-place).
    """

    # Let us create the contents of the /var/sota/ directory:
    # - auto-provisioning.json
    # - import/
    #   - directory contents taken from the shared data tarball
    #
    with TemporaryDirectory() as tmpdir:
        toplvl_entries = []
        log.debug(f"Writing provisioning files to directory: {tmpdir}")

        # Create import directory and extract original shared data into it. This
        # will keep the numeric IDs and attributes of files since we are running
        # inside a container (i.e. as root from the perspective of "tar").
        import_dir = os.path.join(tmpdir, PROV_IMPORT_DIRNAME)
        os.mkdir(import_dir, 0o511)
        subprocess.check_output(["tar", "-xvf", shared_data, "-C", import_dir])
        toplvl_entries.append(PROV_IMPORT_DIRNAME)

        # Create the file holding online provisioning data:
        if online_data:
            online_prov_file = os.path.join(tmpdir, PROV_ONLINE_DATA_FILENAME)
            with open(online_prov_file, "wb") as outfile:
                # Try to decode it just to be sure it is actually valid JSON.
                try:
                    online_data_padded = online_data
                    online_data_padded += "=" * ((4 - len(online_data) % 4) %4)
                    online_data_json = base64.b64decode(online_data_padded)
                    online_data_obj = json.loads(online_data_json)

                    # Add 'hibernated' key if user enabled hibernated mode
                    if hibernated and isinstance(online_data_obj, dict):
                        log.info("Adding hibernated mode flag.")
                        online_data_obj['hibernated'] = True
                        online_data_json = json.dumps(online_data_obj).encode("utf-8")

                    # Add fleet UUIDs if present
                    if fleets and isinstance(online_data_obj, dict):
                        log.info("Adding fleet UUID(s).")
                        online_data_obj['fleetids'] = fleets
                        online_data_json = json.dumps(online_data_obj).encode("utf-8")

                except (binascii.Error, json.decoder.JSONDecodeError) as exc:
                    raise TorizonCoreBuilderError(
                        "Failure decoding online data. Aborting.") from exc
                outfile.write(online_data_json)

            # Make file contents only visible to root user (assumed UID=0, GID=0).
            os.chmod(online_prov_file, 0o640)
            os.chown(online_prov_file, uid=0, gid=0)

            toplvl_entries.append(PROV_ONLINE_DATA_FILENAME)

        # Create final tarball:
        subprocess.check_output(
            ["tar", "--numeric-owner", "--preserve-permissions",
             "-czvf", os.path.join(output_dir, PROV_DATA_FILENAME),
             "-C", tmpdir, *toplvl_entries])


def prov_add_provdata_tarball_to_tezi(output_dir):
    """Add the provisioning tarball to the files copied to the device by TEZI."""

    config_fname = os.path.join(output_dir, DEFAULT_IMAGE_JSON_FILENAME)
    config = ImageConfig(config_fname)
    config.add_files(
        [(PROV_DATA_FILENAME, OSTREE_SOTA_DIR_PATH + "/", True)],
        image_dir=output_dir, update_size=True, fail_src_present=True)
    config.save()


def prov_check_supported_img_features(img_version, online_data, hibernated, fleets):
    """Check supported provisioning features according to image version."""

    img_major, img_minor, _ = img_version
    if img_major is None or img_minor is None:
        log.warning("Warning: Unable to determine image version in input image. "
                    "Proceeding anyway.")
    elif online_data:
        if hibernated and ((img_major == 6 and img_minor <= 7) or img_major < 6):
            # Torizon OS 6.7 or below doesn't support hibernated auto-provisioning
            # without changes to the auto-provisioning script.
            log.warning("Warning: Hibernated auto-provisioning is not supported on Torizon "
                        "OS 6.7 or older. Proceeding anyway.")
        if fleets:
            if (img_major == 7 and img_minor <= 6) or img_major < 7:
                # Torizon OS 7.6 or below doesn't support fleet auto-provisioning
                log.warning("Warning: Fleet auto-provisioning is not supported on Torizon "
                            "OS 7.6 or older. Proceeding anyway.")

            _validate_fleets(fleets)
    log.debug("Found image version: %d.%d", img_major, img_minor)


def prov_check_input(input_path, output_path, rootfs_label,
                     sector_size=DEFAULT_RAW_SECTOR_SIZE):
    """Check provisioning inputs passed by the user."""

    is_tezi_img = False
    # If disk image
    if os.path.isfile(input_path):
        if (not input_path.lower().endswith(".wic") and
            not input_path.lower().endswith(".img")):
            log.warning("Unknown image format. If you are trying to pass an Easy Installer image, "
                        "please provide it as a directory.")
            raise InvalidStateError("Unknown image format. Aborting.")

        if output_path and os.path.isdir(output_path):
            raise InvalidStateError("For raw images the output can't be a directory. Aborting.")
        if rootfs_label is None:
            rootfs_label = DEFAULT_RAW_ROOTFS_LABEL

        img_version = _prov_get_image_version_raw_image(input_path, rootfs_label, sector_size)

    # If TEZI image
    else:
        if (input_path and output_path and
                os.path.realpath(input_path) == os.path.realpath(output_path)):
            # For in-place updates caller should not pass an output directory.
            raise InvalidArgumentError("Input and output directories must be different. Aborting.")

        if check_provdata_presence_in_tezi(input_path):
            # Currently we do not support inputting an image with provisioning data
            # already present.
            raise InvalidStateError("Input image already contains provisioning data. Aborting.")

        # Check unpacked version of Torizon OS
        img_version = get_tezi_image_version(input_path)
        is_tezi_img = True

    return img_version, is_tezi_img, rootfs_label


def provision(input_path, output_path, rootfs_label, prov_data, *,
              hibernated=False, fleets=None, force=False,
              sector_size=DEFAULT_RAW_SECTOR_SIZE):
    """Generate OS image with added provisioning data

    :param input_path: Path containing Easy Installer directory or disk image.
    :param output_path: Path which will hold the output image.
    :param rootfs_label: Filesystem label of the root partition. Only applies for raw disk images.
    :param prov_data: dictionary with provisioning data. It contains the following keys:
           - 'shared': Path to tarball containing shared (i.e. related to both
                            offline and online cases) provisioning data.
           - 'online': Base-64 string containing online provisioning data.
    :param hibernated: Boolean that indicates to whether or not provision in hibernated mode
    :param fleets: List of fleet UUID(s) to provision to
    :param force: Boolean indicating whether to remove output directory if it
                  already exists.
    """

    if hibernated:
        log.warning("Warning: Hibernation Mode is deprecated and may be removed in a "
                    "future release; please do not use it in new projects.\n"
                    f"See: {HIBERNATION_MODE_URL}")

    # Basic validations:
    img_version, is_tezi_img, rootfs_label = prov_check_input(
        input_path, output_path, rootfs_label, sector_size)

    prov_check_supported_img_features(img_version, prov_data['online'], hibernated, fleets)

    # Handle normal or in-place modifications:
    inplace = False

    if output_path is None:
        log.debug("Updating Torizon OS image in place.")
        output_path = input_path
        inplace = True
    else:
        # Fail when output directory already exists.
        if os.path.exists(output_path):
            if not force:
                raise InvalidStateError(f"\"{output_path}\" already exists. Aborting.")
            if os.path.isdir(output_path):
                shutil.rmtree(output_path)
            else:
                os.remove(output_path)

        log.debug("Creating copy of Torizon OS input image.")
        if os.path.isdir(input_path):
            shutil.copytree(input_path, output_path)
        else:
            shutil.copy2(input_path, output_path)

    # Actual provisioning:
    try:
        if is_tezi_img:
            prov_tezi_img(output_path, prov_data, hibernated, fleets)
        else:
            prov_raw_img(rootfs_label, output_path, prov_data, hibernated, fleets, sector_size)

        log.info("Image successfully provisioned.")

    except (TorizonCoreBuilderError, TeziError, RuntimeError) as _exc:
        if not inplace:
            log.debug("Removing output due to error.")
            if os.path.isdir(output_path):
                shutil.rmtree(output_path)
            else:
                os.remove(output_path)
        raise


def prov_tezi_img(output_path, prov_data, hibernated, fleets):
    """Create provisioning data and add it to TEZI image."""

    prov_gen_provdata_tarball(
        output_dir=output_path,
        shared_data=prov_data['shared'],
        online_data=prov_data['online'],
        hibernated=hibernated,
        fleets=fleets)
    prov_add_provdata_tarball_to_tezi(output_path)
    set_output_ownership(output_path)


# pylint: disable-next=too-many-positional-arguments
def prov_raw_img(rootfs_label, output_path, prov_data, hibernated, fleets,
                 sector_size=DEFAULT_RAW_SECTOR_SIZE):
    """Create provisioning data and add it to the root filesystem of the disk image."""

    msg = f"Initializing {output_path}..."
    with (open_disk_image(output_path, loading_msg=msg, sector_size=sector_size) as gfs,
          tempfile.TemporaryDirectory() as tmpdir):
        rootfs_partition = gfs.findfs_label(rootfs_label)
        gfs.mount(rootfs_partition, "/")
        prov_gen_provdata_tarball(
            output_dir=tmpdir,
            shared_data=prov_data['shared'],
            online_data=prov_data['online'],
            hibernated=hibernated,
            fleets=fleets)
        ext = os.path.splitext(PROV_DATA_FILENAME)[1]
        log.info("Copying provisioning data to '%s'.", rootfs_label)
        gfs.mkdir_p(OSTREE_SOTA_DIR_PATH)
        gfs.tar_in(os.path.join(tmpdir, PROV_DATA_FILENAME),
                   OSTREE_SOTA_DIR_PATH,
                   compress=TAR_EXT_TO_PROGRAM[ext])


def _validate_fleets(fleets):
    """
    Check if provided list of fleet UUIDs are in the form of UUIDs

    :param fleets: List of potential UUIDs
    """

    bad_uuids = []
    for uuids in fleets:
        try:
            # Torizon Cloud uses version 4 UUIDs
            uuid.UUID(uuids, version=4)
        except ValueError:
            bad_uuids.append(uuids)

    if bad_uuids:
        raise InvalidArgumentError(
            f"The following UUID(s) do not appear to be a UUID: {bad_uuids}")


def track_tezi_signed_files(tezi_dir, commit_hash, machine):
    """
    Check if input TEZI image has a tarfile with signing files and if so,
    associate it and the bootloader container with the current OSTree commit of the image.
    Otherwise, do nothing.

    :param tezi_dir: Path of directory containing input TEZI image.
    :param commit_hash: Current OSTree commit hash of the TEZI image.
    :machine: Machine name compatible with the TEZI image
    """

    if not machine:
        log.warning("Warning: Could not determine compatible machine for the image.")
        log.warning("Secboot commands will not be usable with this image.")
        log.warning("Proceeding anyway.")
        return

    tcb_signing_files_tar = os.path.join(tezi_dir, DEFAULT_TCB_SIGNING_FILES_TARNAME)
    if os.path.isfile(tcb_signing_files_tar):

        # Assume the signing feature for the machine is not supported if TCB doesn't have its
        # entry in BOOTLOADER_CONTAINER_NAME
        if machine not in BOOTLOADER_CONTAINER_NAME:
            log.warning("Warning: secboot commands are not supported for this machine.")
            return

        log.info(f"Found {DEFAULT_TCB_SIGNING_FILES_TARNAME}.")
        commit_dir = os.path.join(SECBOOT_ARTIFACTS_DIR, commit_hash)
        os.makedirs(commit_dir, exist_ok=True)
        shutil.copy2(tcb_signing_files_tar, commit_dir)

        log.info(f"Linking bootloader container to {commit_hash}.")
        shutil.copy2(os.path.join(tezi_dir, BOOTLOADER_CONTAINER_NAME[machine]),
                     commit_dir)
# EOF
