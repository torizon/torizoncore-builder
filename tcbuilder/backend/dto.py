"""Backend implementation of dto subcommand."""

import logging
import os
import subprocess

from tcbuilder.backend import dt, kernel
from tcbuilder.backend.common import get_storage_dir, is_file_type_dtb

from tcbuilder.errors import InvalidStateError

log = logging.getLogger("torizon." + __name__)

OVERLAYS_TXT_FILE = "overlays.txt"


def get_active_overlays_txt_path():
    """Query the path to the currently applied overlays.txt.

    The overlays.txt file is the overlays definition file for
    the boot loader that may or may not exist.
    """

    # Look for the file in two changes directories; the former is used with
    # non-FIT whereas the latter with FIT images.
    dtbsubdir = dt.get_dtb_kernel_subdir()
    dchangesdir = dt.get_dt_changes_dir()
    dpath = os.path.join(dchangesdir, dtbsubdir, OVERLAYS_TXT_FILE)
    kchangesdir = kernel.get_kernel_changes_dir()
    kpath = os.path.join(kchangesdir, dtbsubdir, OVERLAYS_TXT_FILE)

    if os.path.exists(dpath) and os.path.exists(kpath):
        raise InvalidStateError(
            f"Bad storage state: {OVERLAYS_TXT_FILE} was found both in "
            f"'{dpath}' and '{kpath}'")

    for _path in (dpath, kpath):
        if os.path.exists(_path):
            log.debug(f"Found {OVERLAYS_TXT_FILE} in changes dir: '{_path}'")
            return _path

    # Check for the ostree-managed version of the file in the deployment.
    storage_dir = get_storage_dir()
    dpath = subprocess.check_output(
        ["find", os.path.join(storage_dir, 'sysroot', 'ostree', 'deploy'),
         "-type", "f", "-wholename", f"*/usr/lib/modules/*/dtb/{OVERLAYS_TXT_FILE}",
         "-print", "-quit"],
        text=True).strip()
    assert dpath and os.path.exists(dpath), \
        f"panic: missing {OVERLAYS_TXT_FILE} in base image!"
    log.debug(f"Found {OVERLAYS_TXT_FILE} in deployment: '{dpath}'")

    return dpath


def get_applied_overlay_names():
    """Query the base names of the currently applied overlay blobs."""

    overlays_txt_path = get_active_overlays_txt_path()
    if not overlays_txt_path:
        return []
    return dt.query_variable_in_config_file(
        "fdt_overlays", overlays_txt_path).split()


def set_applied_overlay_names(overlay_names, changes_dir):
    """Deploy an overlays.txt with the specified overlay names.

    :param overlay_names: List of overlays base names to deploy into
        overlays.txt; example of a base name: "my-overlay.dtbo".
    :param changes_dir: Path of a changes directory where the overlays
        file will be created or modified.
    """

    log.debug("Setting overlay list in '%s' to %s",
              OVERLAYS_TXT_FILE, str(overlay_names))
    overlays_txt_dir = os.path.join(changes_dir, dt.get_dtb_kernel_subdir())
    overlays_txt_path = os.path.join(overlays_txt_dir, OVERLAYS_TXT_FILE)
    os.makedirs(overlays_txt_dir, exist_ok=True)
    with open(overlays_txt_path, "w", encoding="utf-8") as ovlf:
        ovlf.write("fdt_overlays=" + " ".join(overlay_names) + "\n")


def find_path_to_overlay(basename):
    """Get the full path of the overlay blob file.

    Given the base name of an overlay blob file, return the full path to it
    (or die trying).
    """

    path = os.path.join(dt.get_dt_changes_dir(),
                        dt.get_dtb_kernel_subdir(),
                        "overlays", basename)
    if os.path.exists(path):
        # There is a recently applied (but not yet deployed) overlay blob with
        # this base name.
        return path
    # Resort to the overlay blobs of the base image.
    storage_dir = get_storage_dir()
    path = subprocess.check_output(
        ["find",
         os.path.join(storage_dir, "sysroot/ostree/deploy"),
         "-type", "f", "-wholename",
         os.path.join("*/usr/lib/modules/*/dtb/overlays", basename),
         "-print", "-quit"], text=True).strip()
    assert path, f"panic: no blob found for overlay {basename}!"
    return path


def get_applied_overlay_paths(base_names=None):
    """Query the paths to the currently applied overlays."""
    if base_names is None:
        base_names = get_applied_overlay_names()
    return [find_path_to_overlay(basename) for basename in base_names]


def modify_dtb_by_overlays(source_dtb_path, source_dtob_paths, target_dtb_path):
    """Apply overlay blobs over device tree blob.

    Apply the device tree overlay blobs 'dtob_paths' over the device tree blob
    'source_dtb_path', producing the device tree blob 'target_dtb_path'.

    Returns True on successful application, False otherwise.
    """

    source_dtob_names = [os.path.basename(_name) for _name in source_dtob_paths]

    assert source_dtob_paths, "panic: empty list of overlays!"
    res = subprocess.run(
        ["fdtoverlay", "-i", source_dtb_path, "-o",
         target_dtb_path] + source_dtob_paths,
        check=False, capture_output=True, text=True)

    if res.returncode != 0:
        log.error(res.stderr)
        log.error(
            f"error: cannot apply device tree overlays {source_dtob_names} "
            f"against device tree {os.path.basename(source_dtb_path)}.")
        return False

    if not is_file_type_dtb(target_dtb_path):
        log.error(
            f"error: application of overlays {source_dtob_names} against "
            f"device tree {os.path.basename(source_dtb_path)} did not produce"
            " a Device Tree Blob.")
        return False

    return True
