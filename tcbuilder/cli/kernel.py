"""
CLI handling for kernel subcommand
"""

import os
import re
import sys
import logging
import tempfile
import subprocess

import libfdt
from tcbuilder.errors import \
    (FileContentMissing, InvalidDataError, PathNotExistError, UnsupportedImageFeature)
from tcbuilder.backend.common import \
    (is_file_type_fit, get_branch_and_major_from_metadata, get_storage_dir,
     get_tar_compress_program_options, images_unpack_executed,
     get_arch_from_ostree, get_src_sysroot_dir)
from tcbuilder.backend.deploy import get_image_bootloader

from tcbuilder.backend import kernel, dt, dto
from tcbuilder.backend.kernelfit import KernelFit
from tcbuilder.cli import dto as dto_cli

log = logging.getLogger("torizon." + __name__)

# Name of the custom args overlay file (this should match the name used by the
# boot script uEnv.txt.
# XXX: Always keep in sync with uEnv.txt.in in recipe `u-boot-distro-boot`.
KERNEL_SET_CUSTOM_ARGS_DTS_NAME = 'custom-kargs_overlay.dts'

# Contents of the custom args overlay source file.
KERNEL_SET_CUSTOM_ARGS_DTS = """
/dts-v1/;
/plugin/;

&{{/chosen}} {{
    bootargs_custom = "{kernel_args}";
}};
"""

# Name of the property defining the kernel args.
# XXX: Always keep in sync with `KERNEL_SET_CUSTOM_ARGS_DTS`.
# XXX: Always keep in sync with uEnv.txt.in in recipe `u-boot-distro-boot`.
KERNEL_SET_CUSTOM_ARGS_PROPERTY = 'bootargs_custom'

# Name of the variables in uEnv.txt defining the kernel args; one variable
# is added to the left (prepended) and the other to the right (appended) of
# the original bootargs string.
# XXX: Always keep in sync with uEnv.txt.in in recipe `u-boot-distro-boot`.
UENV_CUSTOM_BOOTARGS_L_VAR = "torizon_bootargs_l"
UENV_CUSTOM_BOOTARGS_R_VAR = "torizon_bootargs_r"

# Error messages:
MSG_CUSTOMIZATION_NOT_SUPPORTED_FOR_WIC = \
    "Kernel customization is not supported for WIC/raw images. Aborting."
MSG_COMMAND_NOT_SUPPORTED_FOR_WIC = \
    "Command not supported for WIC/raw images. Aborting."

# Regexp to match the name of the secure boot kernel bootargs overlay.
SECBOOT_KARGS_OVL_RE = re.compile(r"^conf-.*secboot-kargs_overlay\.dtbo$")

SECBOOT_NODE_PATH = "/fragment@0/__overlay__/chosen/toradex,secure-boot"
SECBOOT_REQ_BOOTARGS_PROPNAME = "required-bootargs"
SECBOOT_REQ_BOOTARGS_ORG_PROPNAME = "required-bootargs-org"


def _on_custom_kargs_not_supported():
    raise UnsupportedImageFeature(
        "Error: the Torizon OS image you are customizing does not support "
        "custom kernel arguments; please upgrade to a newer OS image version.")


def _check_makefile(source_dir):
    """Ensure the Makefile in the module source dir has the required variables."""

    makefile = os.path.join(source_dir, "Makefile")
    if not os.path.exists(makefile):
        raise PathNotExistError(f'Makefile "{makefile}" does not exist')

    log.debug("Checking presence of KERNEL_SRC/KDIR in '%s'.", makefile)
    with open(makefile, "r", encoding="utf-8") as mkfile:
        lines = mkfile.readlines()
        kernel_check = None
        for line in lines:
            if kernel_check is None:
                kernel_check = re.search("KERNEL_SRC", line)
            if kernel_check is None:
                kernel_check = re.search("KDIR", line)
            if kernel_check is not None:
                break
    if kernel_check is None:
        raise FileContentMissing(f'KERNEL_SRC not found in "{makefile}"')


def _extract_kernel_source():
    """Find the kernel source tarball in the present image and unpack it.

    The tarball will be unpacked into the storage directory whose path will be
    returned by the function.
    """

    # Determine location of linux source tarball.
    storage_dir = get_storage_dir()
    linux_src = subprocess.check_output(
        ["find", os.path.join(storage_dir, "sysroot/ostree/deploy"),
         "-type", "f", "-name", "linux.tar.bz2", "-print", "-quit"], text=True)
    assert linux_src, "panic: missing Linux kernel source!"
    linux_src = linux_src.rstrip()

    # Unpack the linux source tarball into the storage.
    log.debug("Unpacking '%s' into storage '%s'", linux_src, storage_dir)
    tarcmd = [
        "tar",
        "-xf", linux_src,
        "-C", storage_dir,
    ] + get_tar_compress_program_options(linux_src)
    subprocess.check_output(tarcmd, stderr=subprocess.STDOUT)
    extracted_src = os.path.join(storage_dir, "linux")
    assert os.path.isdir(extracted_src), \
        "panic: linux source tarball does not contain 'linux/' directory"

    return extracted_src


def kernel_build_module(source_dir, autoload):
    """"Main handler of the 'kernel build_module' subcommand"""

    images_unpack_executed()
    img_arch = get_arch_from_ostree()
    if img_arch not in ("arm", "aarch64"):
        raise UnsupportedImageFeature(
            "Building kernel modules are not supported for Torizon OS images that target "
            f"{img_arch} devices. Aborting.")

    # Check for valid Makefile
    if not os.path.isdir(source_dir):
        raise PathNotExistError(f'Source directory "{source_dir}" does not exist')
    _check_makefile(source_dir)

    # Find and unpack linux source
    extracted_src = _extract_kernel_source()

    # Build and install Kernel module
    storage_dir = get_storage_dir()
    changes_dir = kernel.get_kernel_changes_dir()
    kernel_subdir = kernel.get_kernel_subdir()
    mod_path = os.path.join(changes_dir, kernel_subdir)
    os.makedirs(mod_path, exist_ok=True)
    usr_dir = subprocess.check_output(
        ["find", os.path.join(storage_dir, "sysroot/ostree/deploy"),
         "-type", "d", "-name", "usr", "-print", "-quit"],
        text=True).rstrip()
    src_mod_dir = os.path.join(os.path.dirname(usr_dir), kernel_subdir)
    src_ostree_archive_dir = os.path.join(storage_dir, "ostree-archive")
    _, image_major_version = get_branch_and_major_from_metadata()

    src_dir = os.path.abspath(source_dir)
    kernel.build_module(
        src_dir=src_dir,
        linux_src=extracted_src,
        src_mod_dir=src_mod_dir,
        image_major_version=image_major_version,
        src_ostree_archive_dir=src_ostree_archive_dir,
        mod_path=mod_path,
        kernel_changes_dir=changes_dir)

    log.info("Kernel module(s) successfully built and ready to deploy.")

    # Set built kernel modules to be autoloaded on boot
    if autoload:
        built_modules = subprocess.check_output(
            ["find", source_dir, "-name", "*.ko", "-print"],
            text=True).splitlines()
        for module in built_modules:
            kernel.autoload_module(module, changes_dir)
            log.info(f"{module} is set to be autoloaded on boot.")

    log.info("All kernel module(s) have been built and prepared.")


def do_kernel_build_module(args):
    """"Run 'kernel build_module' subcommand"""
    kernel_build_module(source_dir=args.source_directory, autoload=args.autoload)


def _set_custom_kargs_ovl(kargs):
    """Set the custom bootargs using the (old) overlay method."""

    log.debug("Setting bootargs (overlay method).")

    # Format string to become file contents.
    dts_contents = KERNEL_SET_CUSTOM_ARGS_DTS.format(kernel_args=kargs)

    # Generate the DTS file with desired contents inside a temporary directory.
    with tempfile.TemporaryDirectory() as tmpdirname:
        dtos_path = os.path.join(tmpdirname, KERNEL_SET_CUSTOM_ARGS_DTS_NAME)
        with open(dtos_path, "w", encoding="utf-8") as file:
            file.write(dts_contents)

        # The present command is simply a wrapper around `dto apply` - since we are
        # setting test_apply as False the parameters `dtb_path` is not required as
        # the function being invoked will not try to apply the overlay for assurance
        # purposes. Also, the include directory is not needed either because we know
        # the file being compiled includes no other files.
        dto_cli.dto_apply(
            dtos_path=dtos_path, dtb_path=None, include_dirs=[],
            allow_reapply=True, test_apply=False)


def _set_custom_kargs_uenv(kargs, changes_dir, *, prepend=False):
    """Set the custom bootargs using the (new) uenv method."""

    log.debug("Setting bootargs (uenv method).")
    if prepend:
        log.debug("Passed string will be prepended to the original bootargs.")
        dt.set_uenv_txt_variable(
            UENV_CUSTOM_BOOTARGS_L_VAR, kargs, changes_dir=changes_dir)
        dt.set_uenv_txt_variable(
            UENV_CUSTOM_BOOTARGS_R_VAR, None, changes_dir=changes_dir)
    else:
        log.debug("Passed string will be appended to the original bootargs.")
        dt.set_uenv_txt_variable(
            UENV_CUSTOM_BOOTARGS_L_VAR, None, changes_dir=changes_dir)
        dt.set_uenv_txt_variable(
            UENV_CUSTOM_BOOTARGS_R_VAR, kargs, changes_dir=changes_dir)


def _secboot_kargs_ovl_present():
    """Check if the base image kernel has a secboot kargs overlay.

    :returns: A pair where first element is a boolean indicating the presence of
        overlay, and the second element is the corresponding file name inside the
        kernel FIT image.
    """

    kernel_path = kernel.find_kernel_in_sysroot()
    dtb_prefix = dt.get_kernelfit_dtb_prefix()
    with open(kernel_path, "rb") as fhandle:
        fit = KernelFit(fhandle, dtb_prefix=dtb_prefix)

    # Find the configuration node corresponding to the secboot kargs overlay
    # and determine its related file name.
    dtbo_list = fit.get_dtb_list(overlay=True)
    dtbo_fname = None
    for _dtbo in dtbo_list:
        if SECBOOT_KARGS_OVL_RE.match(_dtbo["conf_name"]):
            dtbo_fname = _dtbo["file_name"]
            break

    if not dtbo_fname:
        log.debug("Overlay with secboot required-bootargs is not present in the kernel.")
        return False, None

    log.debug("Overlay with secboot required-bootargs found in the kernel.")
    return True, dtbo_fname


def _get_secboot_required_bootargs_fdt(ovl):
    """Get the required-bootargs string from the given overlay libfdt.Fdt."""

    # Determine current value of required-bootargs:
    try:
        nodoff = ovl.path_offset(SECBOOT_NODE_PATH)
        req_bootargs_cur = ovl.getprop(nodoff, SECBOOT_REQ_BOOTARGS_PROPNAME)
        req_bootargs_cur = req_bootargs_cur.as_str()
    except libfdt.FdtException as exc:
        raise InvalidDataError(
            f"Required property {SECBOOT_NODE_PATH}/{SECBOOT_REQ_BOOTARGS_PROPNAME}"
            " not found in secboot overlay.") \
            from exc
    log.debug("req_bootargs_cur='%s'", req_bootargs_cur)

    # Determine original value of required-bootargs:
    try:
        nodoff = ovl.path_offset(SECBOOT_NODE_PATH)
        req_bootargs_org = ovl.getprop(nodoff, SECBOOT_REQ_BOOTARGS_ORG_PROPNAME)
        req_bootargs_org = req_bootargs_org.as_str()
    except libfdt.FdtException as _exc:
        req_bootargs_org = None
        log.debug(
            f"Property {SECBOOT_NODE_PATH}/{SECBOOT_REQ_BOOTARGS_ORG_PROPNAME}"
            " not found in secboot overlay.")
    log.debug("req_bootargs_org='%s'", req_bootargs_org)

    return req_bootargs_cur, req_bootargs_org


def _set_secboot_required_bootargs(kargs, changes_dir):
    """Set/clear the required-bootargs data inside the kernel FIT image.

    The passed kernel bootargs will be prepended to the existing required-bootargs
    in the secboot overlay.
    """

    log.debug("Trying to %s secboot required-bootargs.",
              ["clear", "set"][kargs is None])
    dtbo_pres, dtbo_fname = _secboot_kargs_ovl_present()
    if not dtbo_pres:
        return

    # Copy kernel to changes directory and load it.
    kernel_path = kernel.copy_kernel_to_changes_dir(changes_dir)
    with open(kernel_path, "rb") as fhandle:
        fit = KernelFit(
            fhandle, dtb_prefix=dt.get_kernelfit_dtb_prefix())

    # Extract/parse the overlay from the kernel.
    ovl = libfdt.Fdt(fit.extract_dtb(dtbo_fname, overlay=True))

    # Determine current and original required-bootargs strings.
    req_bootargs_cur, req_bootargs_org = _get_secboot_required_bootargs_fdt(ovl)

    if kargs is None:
        # Handle the "clear" operation:
        if req_bootargs_org is None:
            # Original was not set; by setting the new value to None we avoid
            # updating the overlay inside the FIT (as an optimization).
            req_bootargs_new = None
        else:
            # Clear original bootargs:
            log.debug("Clearing original required-bootargs in the overlay.")
            nodoff = ovl.path_offset(SECBOOT_NODE_PATH)
            ovl.delprop(nodoff, SECBOOT_REQ_BOOTARGS_ORG_PROPNAME)
            # Copy original value into new (undoing the set operation).
            req_bootargs_new = req_bootargs_org
    else:
        # Handle the "set" operation:
        if req_bootargs_org is None:
            # Save original bootargs:
            log.debug("Storing original required-bootargs into the overlay.")
            nodoff = ovl.path_offset(SECBOOT_NODE_PATH)
            ovl.resize(ovl.totalsize() + len(req_bootargs_cur) + 128)
            ovl.setprop_str(nodoff, SECBOOT_REQ_BOOTARGS_ORG_PROPNAME, req_bootargs_cur)
            # Define new value (string):
            req_bootargs_new = kargs + " " + req_bootargs_cur
        else:
            # Define new value (string) based on the original bootargs:
            req_bootargs_new = kargs + " " + req_bootargs_org

    log.debug("req_bootargs_new='%s'", req_bootargs_new)

    if req_bootargs_new is None:
        log.debug("Overlay with required-bootargs needs no update.")
        return

    # Save new bootargs:
    log.debug("Storing updated required-bootargs into the overlay.")
    nodoff = ovl.path_offset(SECBOOT_NODE_PATH)
    ovl.resize(ovl.totalsize() + len(req_bootargs_new) + 128)
    ovl.setprop_str(nodoff, SECBOOT_REQ_BOOTARGS_PROPNAME, req_bootargs_new)
    ovl.pack()

    # Update the DTBO inside the kernel.
    log.debug("Storing updated overlay into the kernel FIT.")
    fit.add_dtb(dtbo_fname, bytes(ovl.as_bytearray()), overlay=True, overwrite=True)

    # Update kernel FIT image on disk.
    with open(kernel_path, "wb") as fhandle:
        fit.write(fhandle)


def kernel_set_custom_args(kernel_args):
    """Main handler of the 'kernel set_custom_args" subcommand

    :param kernel_args: List of strings with the kernel arguments.
    """

    images_unpack_executed()
    img_bootld = get_image_bootloader(get_src_sysroot_dir())
    if img_bootld not in kernel.KARGS_SUPPORTED_BOOTLOADERS:
        log.warning(f"Detected bootloader in unpacked image: {img_bootld}")
        raise UnsupportedImageFeature(
            f"Kernel argument customization is not supported for {img_bootld} "
            "bootloader. Aborting.")

    kernel_path = kernel.find_kernel_in_sysroot()
    kernel_is_fit = is_file_type_fit(kernel_path)
    log.debug(f"kernel_set_custom_args: kernel_is_fit={kernel_is_fit}")

    # Ensure a non-empty string arguments string is being passed (to clear the
    # string users should use the "clear" sub-command).
    kargs = " ".join(kernel_args)
    if not kargs.rstrip():
        log.error('Error: please pass a valid string for the custom kernel arguments.')
        sys.exit(1)

    kargs_methods = kernel.get_supported_bootargs_methods()

    # Check image requirements:
    if kernel_is_fit and "uenv" not in kargs_methods:
        raise UnsupportedImageFeature(
            "Error: the Torizon OS image you are customizing has a kernel in FIT "
            "format but it does not support the uEnv method for passing kernel "
            "arguments; please upgrade to Torizon OS version 7.5.0 or newer.")

    # Determine the target changes directory.
    if kernel_is_fit:
        changes_dir = kernel.get_kernel_changes_dir()
    else:
        changes_dir = dt.get_dt_changes_dir()

    # Determine if the *secboot* kargs overlay is present (not to be confused with
    # the "custom kargs overlay" which is the old method for passing bootargs). We
    # use the presence of the overlay to decide whether the passed bootargs should
    # be prepended or appended to the original secboot bootargs string.
    sb_kargs_ovl_pres = False
    if kernel_is_fit:
        sb_kargs_ovl_pres, _ = _secboot_kargs_ovl_present()

    if "uenv" in kargs_methods:
        if sb_kargs_ovl_pres:
            log.info(
                "Warning: because you are customizing a Secure Boot image, the custom "
                "kernel arguments will be prepended rather than appended to the "
                "original ones from the base image.")
        _set_custom_kargs_uenv(kargs, changes_dir, prepend=sb_kargs_ovl_pres)
        _clr_custom_kargs_ovl()
    elif "overlay" in kargs_methods:
        _set_custom_kargs_ovl(kargs)
    else:
        _on_custom_kargs_not_supported()

    # Secure boot images also keep a "required-bootargs" string inside the kernel
    # which need to be updated; handle this case here.
    if kernel_is_fit and sb_kargs_ovl_pres:
        _set_secboot_required_bootargs(kargs, changes_dir)

    # Confirm application of arguments.
    print(f'Kernel custom arguments successfully configured with "{kargs}".')


def do_kernel_set_custom_args(args):
    """Run 'kernel set_custom_args" subcommand"""
    kernel_set_custom_args(kernel_args=args.kernel_args)


def _get_custom_kargs_ovl():
    # Check if the custom kernel args overlays is being applied.
    overlay_basenames = dto.get_applied_overlay_names()
    dtob_basename = os.path.splitext(KERNEL_SET_CUSTOM_ARGS_DTS_NAME)[0] + ".dtbo"
    if dtob_basename not in overlay_basenames:
        # No arguments set: nothing wrong with that.
        return None

    # Determine full path of the overlay of interest only.
    overlay_paths = dto.get_applied_overlay_paths(base_names=[dtob_basename])
    dtob_path = overlay_paths[0]
    log.debug(f"Custom arguments overlay is applied: path='{dtob_path}'")

    # Read overlay property holding custom bootargs.
    fdtget_output = \
        subprocess.check_output(
            ["fdtget", dtob_path, "/fragment@0/__overlay__/",
             KERNEL_SET_CUSTOM_ARGS_PROPERTY], text=True).rstrip()

    return fdtget_output


def _get_custom_kargs_uenv():
    """Get the custom bootargs using the (new) uenv method."""

    log.debug("Getting bootargs (uenv method).")
    kargs_l = dt.get_uenv_txt_variable(UENV_CUSTOM_BOOTARGS_L_VAR)
    kargs_r = dt.get_uenv_txt_variable(UENV_CUSTOM_BOOTARGS_R_VAR)
    if kargs_l and kargs_r:
        raise InvalidDataError(
            "Error: the Torizon OS image you are customizing has both "
            "'%s' and '%s' set in uEnv.txt which is a case currently not "
            "supported by TorizonCore Builder." %
            (UENV_CUSTOM_BOOTARGS_L_VAR, UENV_CUSTOM_BOOTARGS_R_VAR))

    return kargs_l or kargs_r


def _get_secboot_required_bootargs(changes_dir):
    """Get the (current, original) required-bootargs strings from the kernel FIT."""

    log.debug("Trying to get secboot required-bootargs.")
    dtbo_pres, dtbo_fname = _secboot_kargs_ovl_present()
    if not dtbo_pres:
        return None, None

    # Load customized or original kernel.
    kernel_path = \
        (kernel.find_kernel_in_changes_dir(changes_dir) or
         kernel.find_kernel_in_sysroot())
    with open(kernel_path, "rb") as fhandle:
        fit = KernelFit(
            fhandle, dtb_prefix=dt.get_kernelfit_dtb_prefix())

    # Extract/parse the overlay from the kernel.
    ovl = libfdt.Fdt(fit.extract_dtb(dtbo_fname, overlay=True))

    return _get_secboot_required_bootargs_fdt(ovl)


def kernel_get_custom_args():
    """Run 'kernel get_custom_args" subcommand"""

    images_unpack_executed()
    img_bootld = get_image_bootloader(get_src_sysroot_dir())
    if img_bootld not in kernel.KARGS_SUPPORTED_BOOTLOADERS:
        log.warning(f"Detected bootloader in unpacked image: {img_bootld}")
        raise UnsupportedImageFeature(
            f"Kernel argument customization is not supported for {img_bootld} "
            "bootloader. Aborting.")

    kernel_path = kernel.find_kernel_in_sysroot()
    kernel_is_fit = is_file_type_fit(kernel_path)
    log.debug(f"kernel_get_custom_args: kernel_is_fit={kernel_is_fit}")

    kargs_methods = kernel.get_supported_bootargs_methods()

    # Supported cases are shown in the table below:
    #            +-----------------+
    #            |   Kernel type   |
    # +----------+-----------------+
    # | Method   | non-FIT  | FIT  |
    # +----------+----------+------+
    # | Overlay  | Yes      | No   |
    # +----------+----------+------+
    # | uEnv.txt | Yes      | Yes  |
    # +----------+----------+------+
    #
    if kernel_is_fit and "uenv" not in kargs_methods:
        log.warning(
            "Notice: this image has a kernel in FIT format but it does not support "
            "the uEnv method for passing kernel arguments; this means you will not "
            "be able to set its custom kernel arguments. This can be solved by "
            "upgrading to Torizon OS version 7.5.0 or newer.")

    kargs = None
    if "uenv" in kargs_methods:
        kargs = _get_custom_kargs_uenv()
    elif "overlay" in kargs_methods:
        kargs = _get_custom_kargs_ovl()
    else:
        _on_custom_kargs_not_supported()

    if kargs is None:
        print("No custom kernel arguments configured.")
    else:
        # Send output to stdout always.
        print(f'Currently configured custom kernel arguments: "{kargs}".')

    if kernel_is_fit:
        # Show a debug message with the final secure boot kernel arguments (which
        # include the custom arguments set by the user and the original "required"
        # arguments set when the image was built).
        changes_dir = kernel.get_kernel_changes_dir()
        # At the moment, we don't handle the output of the below function because
        # we are only showing the required-bootargs string as debug messages.
        _get_secboot_required_bootargs(changes_dir)


def do_kernel_get_custom_args(_args):
    """Run 'kernel get_custom_args" subcommand"""
    kernel_get_custom_args()


def _clr_custom_kargs_ovl():
    """Clear the custom bootargs set using the old method (overlay)."""

    log.debug("Clearing bootargs (overlay method).")
    dtob_basename = os.path.splitext(KERNEL_SET_CUSTOM_ARGS_DTS_NAME)[0] + ".dtbo"
    res = dto_cli.dto_remove_single(dtob_basename, presence_required=False)
    return res


def _clr_custom_kargs_uenv(changes_dir):
    """Clear the custom bootargs set using the new method (variables in uEnv.txt)."""

    log.debug("Clearing bootargs (uenv method).")
    status_l = dt.set_uenv_txt_variable(
        UENV_CUSTOM_BOOTARGS_L_VAR, None, changes_dir=changes_dir)
    status_r = dt.set_uenv_txt_variable(
        UENV_CUSTOM_BOOTARGS_R_VAR, None, changes_dir=changes_dir)
    return status_l or status_r


def kernel_clear_custom_args():
    """Run 'kernel clear_custom_args" subcommand"""

    images_unpack_executed()
    img_bootld = get_image_bootloader(get_src_sysroot_dir())
    if img_bootld not in kernel.KARGS_SUPPORTED_BOOTLOADERS:
        log.warning(f"Detected bootloader in unpacked image: {img_bootld}")
        raise UnsupportedImageFeature(
            f"Kernel argument customization is not supported for {img_bootld} "
            "bootloader. Aborting.")

    kernel_path = kernel.find_kernel_in_sysroot()
    kernel_is_fit = is_file_type_fit(kernel_path)
    log.debug(f"kernel_clear_custom_args: kernel_is_fit={kernel_is_fit}")

    kargs_methods = kernel.get_supported_bootargs_methods()

    # Check image requirements:
    if kernel_is_fit and "uenv" not in kargs_methods:
        raise UnsupportedImageFeature(
            "Error: the Torizon OS image you are customizing has a kernel in FIT "
            "format but it does not support the uEnv method for passing kernel "
            "arguments; please upgrade to Torizon OS version 7.5.0 or newer.")

    # Determine the target changes directory.
    if kernel_is_fit:
        changes_dir = kernel.get_kernel_changes_dir()
    else:
        changes_dir = dt.get_dt_changes_dir()

    status = False
    if "uenv" in kargs_methods:
        status = _clr_custom_kargs_uenv(changes_dir)
    elif "overlay" in kargs_methods:
        status = _clr_custom_kargs_ovl()
    else:
        _on_custom_kargs_not_supported()

    # Secure boot images also keep a "required-bootargs" string inside the kernel
    # which need to be updated; handle this case here.
    if kernel_is_fit:
        _set_secboot_required_bootargs(None, changes_dir)

    if status:
        print("Custom kernel arguments successfully cleared.")
    else:
        # No arguments set: nothing wrong with that.
        log.info("No custom kernel arguments configured.")


def do_kernel_clear_custom_args(_args):
    """Run 'kernel clear_custom_args" subcommand"""
    kernel_clear_custom_args()


def init_parser(subparsers):
    """Initialize 'kernel' subcommands command line interface."""

    parser = subparsers.add_parser(
        "kernel",
        help="Manage and modify TorizonCore Linux Kernel.",
        allow_abbrev=False)
    subparsers = parser.add_subparsers(title='Commands', required=True, dest='cmd')

    # kernel build_module
    subparser = subparsers.add_parser(
        "build_module",
        help="Build the kernel module at the provided source directory.",
        allow_abbrev=False)
    subparser.add_argument(metavar="SRC_DIR", dest="source_directory",
                           help="Path to directory with kernel module source code.")
    subparser.add_argument("--autoload", dest="autoload", action="store_true",
                           help="Configure kernel module to be loaded on startup.")
    subparser.set_defaults(func=do_kernel_build_module)

    # kernel set_custom_args
    subparser = subparsers.add_parser(
        "set_custom_args",
        help="Set the TorizonCore kernel arguments.",
        allow_abbrev=False)
    subparser.add_argument(metavar="KERNEL_ARGS", dest="kernel_args", nargs='+',
                           help="Kernel arguments to be added.")
    subparser.set_defaults(func=do_kernel_set_custom_args)

    # kernel get_custom_args
    subparser = subparsers.add_parser(
        "get_custom_args",
        help="Get the TorizonCore kernel arguments.",
        allow_abbrev=False)
    subparser.set_defaults(func=do_kernel_get_custom_args)

    # kernel clear_custom_args
    subparser = subparsers.add_parser(
        "clear_custom_args",
        help="Clear the TorizonCore kernel arguments.",
        allow_abbrev=False)
    subparser.set_defaults(func=do_kernel_clear_custom_args)
