import logging
import os
import subprocess

from tcbuilder.backend import dt

log = logging.getLogger("torizon." + __name__)


def get_active_overlays_txt_path(storage_dir):
    '''Query the path to the currently applied overlays.txt, the overlays definition file for the boot loader, if any.'''

    path = os.path.join(dt.get_dt_changes_dir(storage_dir), dt.get_dtb_kernel_subdir(storage_dir), "overlays.txt")
    if os.path.exists(path):
        # There is a recently applied (but not yet deployed) overlays.txt.
        return path
    path = subprocess.check_output(f"find {storage_dir}/sysroot/ostree/deploy -type f -wholename '*/usr/lib/modules/*/dtb/overlays.txt' -print -quit", shell=True, text=True).strip()
    if path:
        # The base image has an overlay definition.
        return path
    # No overlay definitions found.
    return None


def get_applied_overlays_base_names(storage_dir):
    '''Query the base names of the currently applied overlay blobs.'''

    overlays_txt_path = get_active_overlays_txt_path(storage_dir)
    if not overlays_txt_path:
        return []
    return dt.query_variable_in_config_file("fdt_overlays", overlays_txt_path).split()


def find_path_to_overlay(storage_dir, basename):
    '''Given the base name of an overlay blob file, return the full path to it (or die trying).'''

    path = os.path.join(dt.get_dt_changes_dir(storage_dir), dt.get_dtb_kernel_subdir(storage_dir), "overlays", basename)
    if os.path.exists(path):
        # There is a recently applied (but not yet deployed) overlay blob with this base name.
        return path
    # Resort to the overlay blobs of the base image.
    path = subprocess.check_output(f"find {storage_dir}/sysroot/ostree/deploy -type f -wholename '*/usr/lib/modules/*/dtb/overlays/{basename}' -print -quit", shell=True, text=True).strip()
    assert path, f"panic: no blob found for overlay {basename}!"
    return path


def get_applied_overlay_paths(storage_dir):
    '''Query the paths to the currently applied overlays.'''
    return [ find_path_to_overlay(storage_dir, basename) for basename in get_applied_overlays_base_names(storage_dir) ]


def modify_dtb_by_overlays(source_dtb_path, source_dtob_paths, target_dtb_path):
    '''Apply the device tree overlay blobs 'dtob_paths' over the device tree blob 'source_dtb_path',
       producing the device tree blob 'target_dtb_path'.
       Returns True on successful application, False otherwise.
    '''
    assert source_dtob_paths, "panic: empty list of overlays!"
    p = subprocess.run(["fdtoverlay", "-i", source_dtb_path, "-o", target_dtb_path] + source_dtob_paths, check=False, capture_output=True, text=True)
    if p.returncode != 0:
        log.error(p.stderr)
        log.error(f"error: cannot apply device tree overlays {source_dtob_paths} against device tree {source_dtb_path}.")
        return False
    dtb_check = subprocess.check_output(f"file {target_dtb_path}", shell=True, text=True).strip()
    log.info(dtb_check)
    if not "Device Tree Blob" in dtb_check:
        log.error(f"error: application of overlays {source_dtob_paths} against device tree {source_dtb_path} did not produce a device tree blob.")
        return False
    return True

