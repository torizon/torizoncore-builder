"""
CLI for the DT (device-tree) command.
"""

import logging
import os
import re
import shutil
import sys
import tempfile
import traceback

from tcbuilder.backend import dt as dt_be
from tcbuilder.backend import dto as dto_be
from tcbuilder.backend import kernel as kernel_be
from tcbuilder.backend.common import \
    (checkout_dt_git_repo, set_output_ownership, images_unpack_executed, update_dt_git_repo,
     unpacked_image_type, is_file_type_fit)
from tcbuilder.backend.kernelfit import KernelFit
from tcbuilder.errors import \
    (InvalidArgumentError, InvalidStateError, InvalidDataError, FeatureNotImplementedError,
     TorizonCoreBuilderError)

log = logging.getLogger("torizon." + __name__)

MAX_DTB_FILE_SIZE = 1*1024*1024


def do_dt_status(args):
    '''Perform the 'dt status' command.'''

    images_unpack_executed(args.storage_directory)
    if unpacked_image_type(args.storage_directory) == "raw":
        raise InvalidDataError("Command not supported for WIC/raw images. Aborting.")

    dtb_basename = dt_be.get_current_dtb_basename(args.storage_directory)
    if not dtb_basename:
        log.error("error: cannot identify the enabled device tree in the image "
                  "because it is dynamically selected at runtime.")
        sys.exit(1)

    log.info(f"Current device tree is: {dtb_basename}")


def do_dt_checkout(args):
    '''Perform the 'dt checkout' command.'''
    storage_dir = os.path.abspath(args.storage_directory)

    images_unpack_executed(storage_dir)

    unpacked_kernel_path = kernel_be.find_kernel_in_sysroot(storage_dir)
    if is_file_type_fit(unpacked_kernel_path):
        raise FeatureNotImplementedError(
            "Error: Command not supported for images with kernel in the FIT format.")

    # Retrieve the Toradex device-tree repository, if not already retrieved.
    try:
        if os.path.exists(os.path.abspath("device-trees")):
            if not args.update:
                raise InvalidStateError("'device-trees' directory already exists")
            update_dt_git_repo()
        else:
            checkout_dt_git_repo(storage_dir, None, None)
    except TorizonCoreBuilderError as ex:
        log.error(ex.msg)  # msg from all kinds of Exceptions
        if ex.det is not None:
            log.info(ex.det)  # more elaborative message
        log.debug(traceback.format_exc())  # full traceback to be shown for debugging only
        sys.exit(1)
    finally:
        if os.path.exists(os.path.abspath("device-trees")):
            set_output_ownership("device-trees")


def _abort_if_overlay(dts_path):
    '''Abort operation if given device-tree source is an overlay'''
    with open(dts_path, "r", encoding="utf-8") as fhandle:
        file_string = fhandle.read()
    match = re.search(r'^\s*/plugin/\s*;', file_string, re.MULTILINE)
    if match:
        raise InvalidArgumentError(
            f"error: {dts_path} is a device tree overlay and cannot be applied")


def _deploy_dtb_nonfit(*, dtb_src_path, dtb_name, changes_dir, storage_dir):
    '''Deploy the given DTB into a changes directory (non-FIT kernel case)'''

    dtb_target_dir = os.path.join(
        changes_dir, dt_be.get_dtb_kernel_subdir(storage_dir))
    os.makedirs(dtb_target_dir, exist_ok=True)
    dtb_tgt_path = os.path.join(dtb_target_dir, dtb_name)
    shutil.move(dtb_src_path, dtb_tgt_path)


def _deploy_dtb_fit(*, dtb_src_path, dtb_name, changes_dir, storage_dir):
    '''Deploy the given DTB into a changes directory (FIT kernel case)'''

    kernel_path = kernel_be.copy_kernel_to_changes_dir(changes_dir, storage_dir)

    # Load kernel FIT into memory:
    dtb_prefix = dt_be.get_kernelfit_dtb_prefix(storage_dir)
    with open(kernel_path, "rb") as fhandle:
        fit = KernelFit(fhandle, dtb_prefix=dtb_prefix)

    # Load DTB into memory:
    with open(dtb_src_path, "rb") as fhandle:
        dtb_data = fhandle.read(MAX_DTB_FILE_SIZE+1)
        if len(dtb_data) > MAX_DTB_FILE_SIZE:
            raise InvalidDataError(
                f"DTB file size exceeds limit of {MAX_DTB_FILE_SIZE} bytes.")

    # Store into FIT.
    log.debug("Storing DTB with %d bytes in size into FIT image.", len(dtb_data))
    fit.add_dtb(dtb_name, dtb_data)

    # Update kernel FIT image on disk.
    with open(kernel_path, "wb") as fhandle:
        fit.write(fhandle)


def _deploy_updated_uenv_txt(*, fdtfile, changes_dir, storage_dir):
    # Load original file:
    uenv_src_path = dt_be.get_current_uenv_txt_path(storage_dir)
    with open(uenv_src_path, "r", encoding="utf-8") as fhandle:
        lines = fhandle.readlines()
    # Drop lines assigning to the desired variable:
    var_name = "fdtfile"
    new_lines = []
    for line in lines:
        if not line.startswith(f"{var_name}="):
            new_lines.append(line)
    # Add assignment as the first line.
    new_lines.insert(0, f"{var_name}={fdtfile}\n")
    # Save modified version of the file:
    uenv_target_dir = os.path.join(changes_dir, "usr", "lib", "ostree-boot")
    uenv_target_path = os.path.join(uenv_target_dir, "uEnv.txt")
    os.makedirs(uenv_target_dir, exist_ok=True)
    with open(uenv_target_path, "w", encoding="utf-8") as fhandle:
        fhandle.writelines(new_lines)


def _deploy_empty_overlays_txt(*, changes_dir, storage_dir):
    # Deploy an empty overlays config file, so any overlays from the base image are disabled.
    log.info("warning: removing currently applied device tree overlays.")
    dto_be.set_applied_overlay_names([], changes_dir, storage_dir)


def dt_apply(dts_path, storage_dir, include_dirs=None):
    '''Perform the work of the 'dt apply' command.'''

    images_unpack_executed(storage_dir)
    if unpacked_image_type(storage_dir) == "raw":
        raise InvalidDataError(
            "Device tree customization is not supported for WIC/raw images. "
            "Aborting.")

    unpacked_kernel_path = kernel_be.find_kernel_in_sysroot(storage_dir)
    kernel_is_fit = is_file_type_fit(unpacked_kernel_path)
    log.debug(f"dt_apply: kernel_is_fit={kernel_is_fit}")

    # Sanity check parameters.
    assert dts_path, "panic: missing device tree source parameter"
    if include_dirs is None:
        include_dirs = ["device-trees/include"]

    log.debug(f"dt_apply: include directories: {','.join(include_dirs)}")

    # Ensure user is not trying to compile an overlay.
    _abort_if_overlay(dts_path)

    # Compile the device tree into a temporary dtb.
    dtb_tmp_path = tempfile.mktemp(suffix=".dtb")
    if not dt_be.build_dts(dts_path, include_dirs, dtb_tmp_path):
        log.error(f"error: cannot apply {dts_path}.")
        sys.exit(1)

    # Compute the final/deployed name of the DTB.
    dtb_name = os.path.splitext(os.path.basename(dts_path))[0] + ".dtb"

    if kernel_is_fit:
        # FIT case: all changes go to the kernel-changes directory.
        changes_dir = kernel_be.get_kernel_changes_dir(storage_dir)
        # Deploy the DTB into the kernel FIT container:
        _deploy_dtb_fit(
            dtb_src_path=dtb_tmp_path, dtb_name=dtb_name,
            changes_dir=changes_dir, storage_dir=storage_dir)
    else:
        # non-FIT case: changes go to the DT-changes directory.
        changes_dir = dt_be.get_dt_changes_dir(storage_dir)
        # Erase device tree and overlays of the current session.
        shutil.rmtree(changes_dir, ignore_errors=True)
        # Deploy the DTB into the appropriate changes directory:
        _deploy_dtb_nonfit(
            dtb_src_path=dtb_tmp_path, dtb_name=dtb_name,
            changes_dir=changes_dir, storage_dir=storage_dir)

    _deploy_updated_uenv_txt(
        fdtfile=dtb_name,
        changes_dir=changes_dir, storage_dir=storage_dir)

    _deploy_empty_overlays_txt(
        changes_dir=changes_dir, storage_dir=storage_dir)

    # All set.
    log.info(f"Device tree {dtb_name} successfully applied.")


def do_dt_apply(args):
    '''Perform the 'dt apply' command.'''
    dt_apply(args.dts_path, args.storage_directory, include_dirs=args.include_dirs)


def init_parser(subparsers):
    '''Initializes the 'dt' subcommands command line interface.'''

    parser = subparsers.add_parser(
        "dt",
        description="Manage device trees",
        help="Manage device trees",
        allow_abbrev=False)
    subparsers = parser.add_subparsers(title='Commands', required=True, dest='cmd')

    # dt status
    subparser = subparsers.add_parser(
        "status",
        description="Show the currently enabled device tree",
        help="Show the currently enabled device tree",
        allow_abbrev=False)
    subparser.set_defaults(func=do_dt_status)

    # dt checkout
    subparser = subparsers.add_parser(
        "checkout",
        description="Checkout Toradex device tree and overlays repository",
        help="Checkout Toradex device tree and overlays repository",
        allow_abbrev=False)
    subparser.add_argument(
        "--update", dest="update", action="store_true",
        help="Update device-trees repository (if existing)",
        default=False)
    subparser.set_defaults(func=do_dt_checkout)

    # dt apply DEVICE_TREE
    subparser = subparsers.add_parser(
        "apply",
        description="Compile and enable a device tree",
        help="Compile and enable a device tree",
        allow_abbrev=False)
    subparser.add_argument(
        metavar="DEVICE_TREE", dest="dts_path", help="Path to the device tree source file")
    subparser.add_argument(
        "--include-dir", metavar="DIR", dest="include_dirs", action='append',
        help=("Search directory for include files during device tree compilation. "
              "Can be passed multiple times. If absent, defaults to 'device-trees/include'."))
    subparser.set_defaults(func=do_dt_apply)
