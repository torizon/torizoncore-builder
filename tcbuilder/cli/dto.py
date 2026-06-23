"""CLI handling for dto subcommand."""

import logging
import os
import shlex
import shutil
import subprocess
import sys
import tempfile

from tcbuilder.backend import dt, dto, common, kernel
from tcbuilder.backend.common import \
    (images_unpack_executed, unpacked_image_type, is_file_type_fit)
from tcbuilder.backend.kernelfit import KernelFit, KernelFitException

from tcbuilder.cli import images as images_cli
from tcbuilder.cli import dt as dt_cli
from tcbuilder.cli import union as union_cli
from tcbuilder.cli import deploy as deploy_cli

from tcbuilder.errors import InvalidDataError

log = logging.getLogger("torizon." + __name__)

MAX_DTBO_FILE_SIZE = 1*1024*1024

BUILD_COMMAND_URL = (
    "https://developer.toradex.com/"
    "torizon/os-customization/torizoncore-builder-tool-commands-manual"
    "#the-build-command"
)


def _test_apply_overlay_nonfit(*, dtob_path, dtob_name, dtb_name, overlay_names):
    """Try to apply an overlay on top of a device-tree (non-FIT case).

    :param dtob_path: Path to new overlay file to apply.
    :param dtob_name: Name of the overlay for displaying purposes.
    :param dtb_name: Basename of device-tree blob on top of which the overlay will
        be applied; if empty, the current DTB will be used.
    :param overlay_names: List of other overlays to be applied before applying
        the new one.
    """

    if dtb_name and "/" in dtb_name:
        # The dtb_name must specify only a DTB basename; in the future the presence
        # of slashes may be used to allow passing a DTB path outside the storage.
        log.error("error: the device tree name (%s) must not contain slashes.", dtb_name)
        sys.exit(1)

    # Determine the full path of the base device-tree.
    if dtb_name:
        # User has provided the basename of a device tree blob of the base image.
        log.debug("Using the specified base DTB '%s' for applying overlay.", dtb_name)
        (any_dtb_path, _) = dt.get_current_dtb_path()
        dtb_path = os.path.join(os.path.dirname(any_dtb_path), dtb_name)
    else:
        # Use the current device tree blob.
        log.debug("No base DTB specified; picking the currently applied one.")
        (dtb_path, is_dtb_exact) = dt.get_current_dtb_path()
        if not is_dtb_exact:
            log.error("error: could not find the device tree to check the overlay against.")
            log.error("Please use --device-tree to pass one of the device trees below or use "
                      "--force to bypass checking:")
            dtb_list = subprocess.check_output(
                ["find", os.path.dirname(dtb_path), "-maxdepth", "1", "-type", "f",
                 "-name", "*.dtb", "-printf", "- %f\\n"],
                text=True).rstrip()
            log.error(dtb_list)
            sys.exit(1)

    cur_overlay_paths = dto.get_applied_overlay_paths(base_names=overlay_names)
    new_overlay_paths = cur_overlay_paths + [dtob_path]

    dtb_tmp_path = tempfile.mktemp(suffix=".dtb")
    if not dto.modify_dtb_by_overlays(dtb_path, new_overlay_paths, dtb_tmp_path):
        return False

    log.info(f"Overlay {dtob_name} can successfully modify the device tree "
             f"{os.path.basename(dtb_path)}.")

    return True


def _test_apply_overlay_fit(*, dtob_path, dtob_name, dtb_name, overlay_names, changes_dir):
    """Try to apply an overlay on top of a device-tree (FIT case).

    :param dtob_path: Path to new overlay file to apply.
    :param dtob_name: Name of the overlay for displaying purposes.
    :param dtb_name: Path to device-tree blob file on top of which the overlay will
        be applied; if empty, the current DTB will be used.
    :param overlay_names: List of other overlays to be applied before applying
        the new one.
    """

    # Select base DTB:
    dtb_path = _resolve_dtb_fit(dtb_name, changes_dir)

    # Determine DTBs to apply:
    cur_overlay_paths = _resolve_dtob_fit(overlay_names, changes_dir)
    new_overlay_paths = cur_overlay_paths + [dtob_path]

    dtb_tmp_path = tempfile.mktemp(suffix=".dtb")
    if not dto.modify_dtb_by_overlays(dtb_path, new_overlay_paths, dtb_tmp_path):
        return False

    log.info(f"Overlay {dtob_name} can successfully modify the device tree "
             f"{os.path.basename(dtb_path)}.")

    return True


def _deploy_dtob_nonfit(*, dtob_src_path, dtob_name, changes_dir):
    """Deploy the given DTBO into a changes directory (non-FIT kernel case)."""

    krnl_subdir = dt.get_dtb_kernel_subdir()
    dtob_tgt_dir = os.path.join(changes_dir, krnl_subdir, "overlays")
    os.makedirs(dtob_tgt_dir, exist_ok=True)
    dtob_tgt_path = os.path.join(dtob_tgt_dir, dtob_name)
    shutil.move(dtob_src_path, dtob_tgt_path)


def _deploy_dtob_fit(*, dtob_src_path, dtob_name, changes_dir):
    """Deploy the given DTBO into a changes directory (FIT kernel case)."""

    kernel_path = kernel.copy_kernel_to_changes_dir(changes_dir)

    # Load kernel FIT into memory:
    dtb_prefix = dt.get_kernelfit_dtb_prefix()
    with open(kernel_path, "rb") as fhandle:
        fit = KernelFit(fhandle, dtb_prefix=dtb_prefix)

    # Load DTBO into memory:
    with open(dtob_src_path, "rb") as fhandle:
        dtob_data = fhandle.read(MAX_DTBO_FILE_SIZE+1)
        if len(dtob_data) > MAX_DTBO_FILE_SIZE:
            raise InvalidDataError(
                f"DTBO file size exceeds limit of {MAX_DTBO_FILE_SIZE} bytes.")

    # Store into FIT.
    log.debug("Storing DTBO with %d bytes in size into FIT image.", len(dtob_data))
    fit.add_dtb(dtob_name, dtob_data, overlay=True)

    # Update kernel FIT image on disk.
    with open(kernel_path, "wb") as fhandle:
        fit.write(fhandle)


def dto_apply(dtos_path, dtb_path, include_dirs,
              *, allow_reapply=False, test_apply=True):
    """Execute most of the work of 'dto apply' command.

    :param dtos_path: the full path to the source device-tree overlay file to be applied.
    :param dtb_path: the name of the device-tree blob where to test apply the overlay
        (required only if `test_apply` is True).
    :param include_dirs: list of directories where to search include files when building
        the overlay file.
    :param allow_reapply: whether or not to allow an overlay to be applied another time.
    :param test_apply: whether or not to apply the overlay over the device tree to check
        for errors.
    """

    images_unpack_executed()
    if unpacked_image_type() == "raw":
        raise InvalidDataError("Device tree overlay customization is not supported for WIC/raw "
                               "images. Aborting.")

    kernel_path = kernel.find_kernel_in_sysroot()
    kernel_is_fit = is_file_type_fit(kernel_path)
    log.debug(f"dto_apply: kernel_is_fit={kernel_is_fit}")

    cur_overlay_basenames = dto.get_applied_overlay_names()
    dtob_target_basename = os.path.splitext(os.path.basename(dtos_path))[0] + ".dtbo"

    # Detect a redundant overlay application.
    if not allow_reapply:
        if dtob_target_basename in cur_overlay_basenames:
            log.error(f"error: overlay {dtob_target_basename} is already applied.")
            sys.exit(1)

    # When reapplying an overlay, remove it from the current list to ensure only the last
    # application will take effect.
    if dtob_target_basename in cur_overlay_basenames:
        cur_overlay_basenames.remove(dtob_target_basename)

    # Compile the overlay.
    dtob_tmp_path = tempfile.mktemp(suffix=".dtbo")
    if not dt.build_dts(dtos_path, include_dirs, dtob_tmp_path):
        log.error(f"error: cannot apply {dtos_path}.")
        sys.exit(1)

    if kernel_is_fit:
        # FIT case: all changes go to the kernel-changes directory.
        changes_dir = kernel.get_kernel_changes_dir()
    else:
        # non-FIT case: changes go to the DT-changes directory.
        changes_dir = dt.get_dt_changes_dir()

    # Test apply the overlay against the device-tree and already applied overlays.
    if test_apply:
        _apply_res = None
        if kernel_is_fit:
            _apply_res = _test_apply_overlay_fit(
                dtob_path=dtob_tmp_path, dtob_name=dtob_target_basename,
                dtb_name=dtb_path, overlay_names=cur_overlay_basenames,
                changes_dir=changes_dir)
        else:
            _apply_res = _test_apply_overlay_nonfit(
                dtob_path=dtob_tmp_path, dtob_name=dtob_target_basename,
                dtb_name=dtb_path, overlay_names=cur_overlay_basenames)
        if not _apply_res:
            log.error(f"error: overlay '{dtos_path}' is not applicable.")
            sys.exit(1)

    # Deploy the device tree overlay blob.
    if kernel_is_fit:
        _deploy_dtob_fit(
            dtob_src_path=dtob_tmp_path, dtob_name=dtob_target_basename,
            changes_dir=changes_dir)
    else:
        _deploy_dtob_nonfit(
            dtob_src_path=dtob_tmp_path, dtob_name=dtob_target_basename,
            changes_dir=changes_dir)

    # Deploy the enablement of the device tree overlay blob.
    new_overlay_basenames = cur_overlay_basenames + [dtob_target_basename]
    dto.set_applied_overlay_names(new_overlay_basenames, changes_dir)

    # All set :-)
    log.info(f"Overlay {dtob_target_basename} successfully applied.")


def do_dto_apply(args):
    """Perform the 'dto apply' command."""

    # Sanity check parameters.
    if not args.include_dirs:
        args.include_dirs = ["device-trees/include"]
    assert args.dtos_path, "panic: missing overlay source parameter"

    if args.force:
        log.info("warning: --force was used, bypassing checking overlays against the device tree.")

    # TODO: Review --force behavior and the fixed `allow_reapply` parameter.
    dto_apply(
        dtos_path=args.dtos_path,
        dtb_path=args.device_tree,
        include_dirs=args.include_dirs,
        allow_reapply=False,
        test_apply=not args.force)


def _dto_list_check_args(device_tree, overlays_subdir):
    """Check the arguments passed to the "dto list" command."""

    # Sanity check for overlay sources to scan.
    log.debug("Checking existence of '%s' directory.", overlays_subdir)
    if not os.path.isdir(overlays_subdir):
        log.error("error: missing device tree overlays directory '%s'; "
                  "please check the developer website documentation on "
                  "the \"Device Tree Overlays\" topic.",
                  overlays_subdir)
        sys.exit(1)

    # Sanity check for --device-tree
    if device_tree and not (device_tree.endswith(".dtb") or
                            device_tree.endswith(".dts")):
        log.error("error: the argument to --device-tree must be either "
                  "a device tree source (.dts) or binary/blob (.dtb).")
        sys.exit(1)

    if device_tree and device_tree.endswith(".dts") and not os.path.isfile(device_tree):
        # The user has passed a wrong device tree blob file with --device-tree
        log.error("error: cannot read device tree source '%s'.", device_tree)
        sys.exit(1)


def _resolve_dtb_nonfit(dtb_name):
    """Get the path of the named DTB (if passed) or of the default DTB."""

    if dtb_name and "/" in dtb_name:
        # In the future the presence of slashes may be used to allow passing a
        # DTB path outside the storage.
        log.error("error: the device tree name (%s) must not contain slashes.", dtb_name)
        sys.exit(1)

    (dtb_path, is_dtb_exact) = dt.get_current_dtb_path()
    if not dtb_name and not is_dtb_exact:
        # No device-tree specified and the default one could not be determined.
        dtb_dir = os.path.dirname(dtb_path)
        log.warning("Could not determine default device tree.")
        log.debug("Looking for available device-trees under '%s'.", dtb_dir)
        # Show available device-trees to the user.
        dtb_list = subprocess.check_output(
            ["find", dtb_dir, "-maxdepth", "1", "-type", "f",
             "-name", "*.dtb", "-printf", "- %f\\n"],
            text=True).rstrip()
        if dtb_list.count('\n') > 0:
            log.error("Please use --device-tree to pass one of the device "
                      "trees below as the assumed default:")
            log.error(dtb_list)
            sys.exit(1)
        # Go ahead if there is only one available device-tree.
        log.info("Proceeding with the following device tree as the assumed default:")
        log.info(os.path.basename(dtb_path))

    if dtb_name:
        dtb_path = os.path.join(os.path.dirname(dtb_path), os.path.basename(dtb_name))

    return dtb_path


def _resolve_dtb_fit(dtb_name, changes_dir):
    """Get a path for the named DTB (if passed) or for the default DTB.

    This handles the FIT case where the DTB would reside inside the kernel
    FIT image. To be able to return a path, this function will extract the
    DTB into a temporary directory.
    """

    if dtb_name and "/" in dtb_name:
        # In the future the presence of slashes may be used to allow passing a
        # DTB path outside the storage.
        log.error("error: the device tree name (%s) must not contain slashes.", dtb_name)
        sys.exit(1)

    list_dtbs = False
    if not dtb_name:
        # No device-tree specified: use default one from the image (if set).
        dtb_name = dt.get_current_dtb_basename()
        if not dtb_name:
            log.warning("Could not determine default device tree.")
            list_dtbs = True

    # Load kernel FIT into memory:
    kernel_path = \
        (kernel.find_kernel_in_changes_dir(changes_dir) or
         kernel.find_kernel_in_sysroot())
    dtb_prefix = dt.get_kernelfit_dtb_prefix()
    with open(kernel_path, "rb") as fhandle:
        fit = KernelFit(fhandle, dtb_prefix=dtb_prefix)

    if list_dtbs:
        # List dtbs available within the kernel image.
        dtb_list = fit.get_dtb_list()
        if len(dtb_list) == 1:
            # If there's only one dtb available, select it.
            log.info("Proceeding with the following device tree as the assumed default:")
            dtb_name = dtb_list[0]["file_name"]
        elif len(dtb_list) > 1:
            log.error("Please use --device-tree to pass one of the device "
                      "trees below as the assumed default:")
            for _dtb in dtb_list:
                log.error("- %s", _dtb["file_name"])
            sys.exit(1)
        else:
            log.error("No device tree blobs available inside the kernel FIT image; aborting.")
            sys.exit(1)

    # Extract the DTB from the kernel FIT into a temporary file.
    dtb_data = fit.extract_dtb(dtb_name)
    dtb_tmp_dir = tempfile.mkdtemp()
    dtb_path = os.path.join(dtb_tmp_dir, dtb_name)
    log.debug("Extracting '%s' data into '%s'.", dtb_name, dtb_path)
    with open(dtb_path, "wb") as dtbh:
        dtbh.write(dtb_data)

    return dtb_path


def _resolve_dtob_fit(dtob_names, changes_dir):
    """Get a path for the specified device-tree overlays.

    This handles the FIT case where the overlays would reside inside the
    kernel FIT image. To be able to return a path, this function will extract
    the overlays into a temporary directory.
    """

    assert isinstance(dtob_names, list)
    # Load kernel FIT into memory:
    kernel_path = \
        (kernel.find_kernel_in_changes_dir(changes_dir) or
         kernel.find_kernel_in_sysroot())
    dtb_prefix = dt.get_kernelfit_dtb_prefix()
    with open(kernel_path, "rb") as fhandle:
        fit = KernelFit(fhandle, dtb_prefix=dtb_prefix)

    # Extract all DTBOs into the same temporary directory.
    dtob_tmp_dir = tempfile.mkdtemp()

    dtob_paths = []
    for dtob_name in dtob_names:
        # Extract the DTBO from the kernel FIT into a temporary file.
        dtob_data = fit.extract_dtb(dtob_name, overlay=True)
        dtob_path = os.path.join(dtob_tmp_dir, dtob_name)
        log.debug("Extracting '%s' data into '%s'.", dtob_name, dtob_path)
        with open(dtob_path, "wb") as dtobh:
            dtobh.write(dtob_data)
        dtob_paths.append(dtob_path)

    return dtob_paths


def dto_list(device_tree, overlays_subdir):
    """Perform the 'dto list' command."""

    images_unpack_executed()
    if unpacked_image_type() == "raw":
        raise InvalidDataError("Command not supported for WIC/raw images. Aborting.")

    _dto_list_check_args(device_tree, overlays_subdir)

    kernel_path = kernel.find_kernel_in_sysroot()
    kernel_is_fit = is_file_type_fit(kernel_path)
    log.debug(f"dto_list: kernel_is_fit={kernel_is_fit}")

    # Temporary file that will hold the extracted compatibility regexps.
    compat_regexps_tmp_path = tempfile.mktemp()

    # Extract compatibility labels from the device tree blob,
    # and use them for building regexp patterns for matching with compatible
    # device tree source files.
    #
    # Samples of such patterns:
    # ^[[:blank:]]*compatible *= *"toradex,colibri-imx8x-aster"
    # ^[[:blank:]]*compatible *= *"toradex,colibri-imx8x"
    # ^[[:blank:]]*compatible *= *"fsl,imx8qxp"
    if device_tree and device_tree.endswith(".dts"):
        # The user passed a device tree source file to check compatibility against;
        # parse the textual content of the file.
        try:
            # About the 'sed' invocations below:
            # 1. The first 'sed' scans the device tree source file and extracts
            #    the first block from "compatible =" to the semicolon.
            # 2. The second sed filters out the "source noise" of the
            #    compatibility values;
            # 3. The final 'sed' prepends '^[[:blank:]]*compatible *= *'
            #    to the compatibility values.
            subprocess.check_output(
                "set -o pipefail && "
                "sed -r -e '/^[[:blank:]]*compatible *=/,/;/!d' "
                f"-e '/;/q' {shlex.quote(device_tree)} | tr -d '\n' | "
                "sed -r -e 's/.*\\<compatible *= *//' "
                "-e 's/[[:blank:]]*//g' -e 's/\";.*/\"\\n/' -e 's/\",\"/\"\\n\"/g'"
                f">{shlex.quote(compat_regexps_tmp_path)}",
                shell=True, executable="/bin/bash",
                text=True, stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as exc:
            log.error(exc.output.strip())
            log.error("error: cannot extract compatibility labels from device "
                      f"tree source '{device_tree}'")
            sys.exit(1)
    else:
        # The device tree is a binary blob (either inside the kernel or as a separate file).
        if kernel_is_fit:
            # FIT case: all changes go to the kernel-changes directory.
            changes_dir = kernel.get_kernel_changes_dir()
            dtb_path = _resolve_dtb_fit(device_tree, changes_dir)
        else:
            dtb_path = _resolve_dtb_nonfit(device_tree)

        # Use the resolved path as the new device-tree name.
        device_tree = dtb_path

        try:
            # About the 'sed' programs below:
            #  -e 's/$/\"/' appends '"' to each line
            subprocess.check_output(
                f"set -o pipefail && fdtget {shlex.quote(dtb_path)} / compatible | tr ' ' '\n' "
                f"| sed -e 's/$/\"/' >{shlex.quote(compat_regexps_tmp_path)}",
                shell=True, executable="/bin/bash",
                text=True, stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as exc:
            log.error(exc.output.strip())
            if "FDT_ERR_BADMAGIC" in exc.output:
                log.error(f"error: bad file format -- is '{dtb_path}' a device tree blob?")
            else:
                log.error("error: cannot extract compatibility labels from "
                          f"device tree blob '{dtb_path}'")
            sys.exit(1)

    # Show all device tree overlay source files that are compatible with the device tree blob.
    # Given the regexp patterns mentioned above, 'grep' can easily scan for all compatible
    # files under a given subdirectory.
    try:
        compat_list = subprocess.check_output(
            f"set -o pipefail && grep -rlHEf {shlex.quote(compat_regexps_tmp_path)} "
            f"{shlex.quote(overlays_subdir)} "
            "| sort -u | sed -e 's/^/- /'",
            shell=True, executable="/bin/bash", text=True).strip()
        log.info(f"Overlays compatible with device tree {os.path.basename(device_tree)}:")
        log.info(f"{compat_list}")
    except subprocess.CalledProcessError as _exc:
        log.info("No overlays compatible with device tree "
                 f"{os.path.basename(device_tree)} were found.")


def do_dto_list(args):
    """Perform the 'dto list' command."""
    dto_list(device_tree=args.device_tree,
             overlays_subdir="device-trees/overlays")


def dto_status():
    """Perform the 'dto status' command."""

    images_unpack_executed()
    if unpacked_image_type() == "raw":
        raise InvalidDataError("Command not supported for WIC/raw images. Aborting.")

    # Show the enabled device tree.
    dtb_basename = dt.get_current_dtb_basename()
    if dtb_basename:
        log.info(f"Enabled overlays over device tree {dtb_basename}:")
    else:
        log.info("Enabled overlays over unknown device tree:")

    # Show the enabled overlays.
    for overlay_basename in dto.get_applied_overlay_names():
        log.info(f"- {overlay_basename}")


def do_dto_status(_args):
    """Perform the 'dto status' command."""
    dto_status()


def _dto_remove_single_nonfit(dtob_basename, changes_dir):
    """Withdraw the application of an overlay (not-FIT case).

    Remove the specified overlay from the list of overlays being "applied"
    and delete the overlay file from the changes directory (if present).

    :param dtob_basename: Basename of the overlay file.
    :param changes_dir: Path to the changes directory.
    """

    log.debug("Removing overlay '%s'.", dtob_basename)
    # Update overlays.txt:
    dtob_basenames = dto.get_applied_overlay_names()
    dtob_basenames.remove(dtob_basename)
    dto.set_applied_overlay_names(dtob_basenames, changes_dir)
    # Remove the overlay blob if it's not deployed.
    dtob_path = dto.find_path_to_overlay(dtob_basename)
    if dtob_path.startswith(changes_dir):
        os.remove(dtob_path)


def _dto_remove_single_fit(dtob_basename, changes_dir, restore=True):
    """Withdraw the application of an overlay (FIT case).

    Remove the specified overlay from the list of overlays being "applied"
    and delete the overlay blob from within the kernel FIT image. In case the
    overlay being deleted was replacing/overwriting an overlay with the same
    name from the base image, this function can restore/copy the original
    blob from the base image (this mimics the behavior of the non-FIT case).

    :param dtob_basename: Basename of the overlay file (which will be mapped to
        node names inside the kernel FIT image).
    :param changes_dir: Path to the changes directory.
    :param restore: Whether or not to restore an overlay from the base image.
    """

    log.debug("Removing overlay '%s'.", dtob_basename)
    # Update overlays.txt:
    dtob_basenames = dto.get_applied_overlay_names()
    dtob_basenames.remove(dtob_basename)
    dto.set_applied_overlay_names(dtob_basenames, changes_dir)

    # If the kernel has not undergone any changes yet, for sure there are no user set
    # overlays in it; nothing needs to be done in that case.
    kernel_path_sysroot = kernel.find_kernel_in_sysroot()
    kernel_path_chgsdir = kernel.find_kernel_in_changes_dir(changes_dir)
    if not kernel_path_chgsdir:
        log.debug("Not removing overlay from kernel FIT (kernel has no custom changes).")
        return

    # ---
    # Remove the overlay from the kernel being customized.
    # ---

    # Load kernel FIT into memory:
    dtb_prefix = dt.get_kernelfit_dtb_prefix()
    with open(kernel_path_chgsdir, "rb") as fhandle:
        fitcustom = KernelFit(fhandle, dtb_prefix=dtb_prefix)
    # Delete the overlay:
    fitcustom.del_dtb(dtob_basename, overlay=True)

    # ---
    # Restore overlay from the base image by copying it from the original kernel.
    # ---

    # This mirrors the non-FIT behavior: new overlays may be added and existing
    # ones from the base image may be replaced, but deletion is not possible.
    if restore:
        with open(kernel_path_sysroot, "rb") as fhandle:
            fitbase = KernelFit(fhandle, dtb_prefix=dtb_prefix)
        try:
            dtob_data = fitbase.extract_dtb(dtob_basename, overlay=True)
            fitcustom.add_dtb(dtob_basename, dtob_data, overlay=True)
            log.debug("Overlay '%s' was restored from base image.", dtob_basename)
        except KernelFitException:
            log.debug("Overlay '%s' is not present in base image.", dtob_basename)

    # Update kernel FIT image on disk.
    with open(kernel_path_chgsdir, "wb") as fhandle:
        fitcustom.write(fhandle)


def dto_remove_single(dtob_basename, presence_required=True):
    """Remove a single overlay."""

    images_unpack_executed()
    if unpacked_image_type() == "raw":
        raise InvalidDataError("Device tree overlay customization is not supported for WIC/raw "
                               "images. Aborting.")

    dtob_basenames = dto.get_applied_overlay_names()
    if not dtob_basename in dtob_basenames:
        if presence_required:
            log.error(f"error: overlay '{dtob_basename}' is already not applied.")
            sys.exit(1)
        else:
            log.debug(f"Overlay '{dtob_basename}' is already not applied.")
            return False

    kernel_path = kernel.find_kernel_in_sysroot()
    kernel_is_fit = is_file_type_fit(kernel_path)
    log.debug(f"dto_remove_single: kernel_is_fit={kernel_is_fit}")

    if kernel_is_fit:
        changes_dir = kernel.get_kernel_changes_dir()
        # TODO: Consider allowing users to set restore=False.
        _dto_remove_single_fit(dtob_basename, changes_dir)
    else:
        changes_dir = dt.get_dt_changes_dir()
        _dto_remove_single_nonfit(dtob_basename, changes_dir)

    return True


def _dto_remove_all_nonfit(changes_dir):
    # Deploy an empty overlays config file.
    log.debug("Removing all overlays.")
    dto.set_applied_overlay_names([], changes_dir)
    # Wipe out all overlay blobs as external changes.
    dtob_target_dir = os.path.join(
        changes_dir, dt.get_dtb_kernel_subdir(), "overlays")
    shutil.rmtree(dtob_target_dir, ignore_errors=True)


def _dto_remove_all_fit(changes_dir):
    log.debug("Removing all overlays (FIT case).")
    dtob_basenames = dto.get_applied_overlay_names()
    for dtob_basename in dtob_basenames:
        _dto_remove_single_fit(dtob_basename, changes_dir)


def dto_remove_all():
    """Remove all overlays currently applied."""

    images_unpack_executed()
    if unpacked_image_type() == "raw":
        raise InvalidDataError("Device tree overlay customization is not supported for WIC/raw "
                               "images. Aborting.")

    kernel_path = kernel.find_kernel_in_sysroot()
    kernel_is_fit = is_file_type_fit(kernel_path)
    log.debug(f"dto_remove_all: kernel_is_fit={kernel_is_fit}")

    if kernel_is_fit:
        changes_dir = kernel.get_kernel_changes_dir()
        _dto_remove_all_fit(changes_dir)
    else:
        changes_dir = dt.get_dt_changes_dir()
        _dto_remove_all_nonfit(changes_dir)

    # Sanity check.
    assert not dto.get_applied_overlay_names(), \
        "panic: all overlays removal failed; please contact the maintainers of this tool."


def do_dto_remove(args):
    """Perform the 'dto status' command."""

    if args.all and args.dtob_basename:
        log.error("error: both --all and an overlay were specified in the command line.")
        sys.exit(1)

    if args.all:
        # The user wants to remove all overlays.
        dto_remove_all()
    else:
        # The user wants to remove a single overlay.
        if not args.dtob_basename:
            log.error("error: no overlay was specified in the command line.")
            sys.exit(1)
        dto_remove_single(args.dtob_basename, presence_required=True)


def do_dto_deploy(args):
    """
    Run just one command to deploy an overlay in the device, so it is easier
    and less error-prone to the user.
    """

    log.warning("\n\n[DEPRECATED] Use the 'build' command instead.\n"
                f"See: {BUILD_COMMAND_URL}\n\n")

    # Download TEZI image and checkout Device Tree files.
    args.remove_storage = True
    setattr(args, 'update', False)
    images_cli.do_images_download(args)
    dt_cli.do_dt_checkout(args)

    # Remove all applied overlays
    if args.clear:
        args.all = True
        args.dtob_basename = None
        do_dto_remove(args)

    # Apply all Device Tree overlay file(s) passed in the command line.
    for dtos_path in args.dtos_paths:
        args.dtos_path = dtos_path
        do_dto_apply(args)

    # Create an ostree overlay.
    union_branch = "dto_deploy"
    union_cli.union(
        changes_dirs=None,
        union_branch=union_branch,
        commit_subject="dto_deploy_subject",
        commit_body="dto_deploy_body")

    # Deploy an ostree overlay in the device.
    args.ref = union_branch
    deploy_cli.do_deploy_ostree_remote(args)


def init_parser(subparsers):
    """Initializes the 'dto' subcommands command line interface."""

    parser = subparsers.add_parser(
        "dto",
        description="Manage device tree overlays",
        help="Manage device tree overlays",
        allow_abbrev=False)

    subparsers = parser.add_subparsers(title='Commands', required=True, dest='cmd')

    # dto apply
    subparser = subparsers.add_parser(
        "apply",
        description="Apply a device tree overlay",
        help="Apply a device tree overlay",
        allow_abbrev=False)
    subparser.add_argument(
        metavar="OVERLAY", dest="dtos_path",
        help="Path to the device tree overlay source file")
    subparser.add_argument(
        "--include-dir",
        metavar="DIR", dest="include_dirs", action='append',
        help=("Search directory for include files during overlay compilation. "
              "Can be passed multiple times. If absent, defaults to 'device-trees/include'"))
    subparser.add_argument(
        "--device-tree",
        metavar="FILE", dest="device_tree",
        help="Test the overlay against an specific device tree.")
    subparser.add_argument(
        "--force",
        action="store_true",
        help="Apply the overlay even on failure checking it against a device tree.")
    subparser.set_defaults(func=do_dto_apply)

    # dto list
    subparser = subparsers.add_parser(
        "list",
        description="List the device tree overlays compatible with the current device tree",
        help="List the device tree overlays compatible with the current device tree",
        allow_abbrev=False)
    subparser.add_argument(
        "--device-tree",
        metavar="FILE", dest="device_tree",
        help=("Check for overlay compatibility against this device tree source or binary "
              "file instead."))
    subparser.set_defaults(func=do_dto_list)

    # dto status
    subparser = subparsers.add_parser(
        "status",
        description="List the applied device tree overlays",
        help="List the applied device tree overlays",
        allow_abbrev=False)
    subparser.set_defaults(func=do_dto_status)

    # dto remove
    subparser = subparsers.add_parser(
        "remove",
        description="Remove a device tree overlay",
        help="Remove a device tree overlay",
        allow_abbrev=False)
    subparser.add_argument(
        metavar="OVERLAY", dest="dtob_basename", nargs='?',
        help="Name of the device tree overlay")
    subparser.add_argument(
        "--all",
        action="store_true",
        help="Remove all device tree overlays")
    subparser.set_defaults(func=do_dto_remove)

    # dto deploy
    subparser = subparsers.add_parser(
        "deploy",
        description="Deploy a device tree overlay in the device",
        help="Deploy a device tree overlay in the device",
        allow_abbrev=False)
    subparser.add_argument(
        "--remote-host",
        dest="remote_host",
        help="Name/IP of remote machine", required=True)
    common.add_ssh_arguments(subparser)
    subparser.add_argument(
        "--reboot",
        dest="reboot", action='store_true',
        help="Reboot device after deploying device tree overlay(s)",
        default=False)
    subparser.add_argument(
        "--mdns-source",
        dest="mdns_source",
        help=("Use the given IP address as mDNS source. This is useful when "
              "multiple interfaces are used, and mDNS multicast requests are "
              "sent out the wrong network interface."))
    subparser.add_argument(
        "--include-dir",
        metavar="DIR", dest="include_dirs", action='append',
        help=("Search directory for include files during overlay compilation. "
              "Can be passed multiple times. If absent, defaults to "
              "'device-trees/include'"))
    subparser.add_argument(
        "--force",
        action="store_true",
        help="Apply the overlay even on failure checking it against a device tree.")
    subparser.add_argument(
        "--device-tree",
        metavar="FILE", dest="device_tree",
        help="Test the overlay against an specific device tree.")
    subparser.add_argument(
        "--clear",
        dest="clear", action="store_true",
        help="Remove all currently applied device tree overlays.", default=False)
    subparser.add_argument(
        metavar="OVERLAY", dest="dtos_paths",
        help="Path to the device tree overlay source file(s)", nargs='+')
    subparser.set_defaults(func=do_dto_deploy)
