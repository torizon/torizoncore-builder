"""
Backend functions and functionality for all kernel commands
"""

import logging
import os
import re
import shutil
import subprocess
import urllib.request

from tcbuilder.backend import ostree, dt
from tcbuilder.backend.common import \
    (download_progress, get_tar_compress_program_options, get_storage_dir,
     set_output_ownership, OSTREE_ROOT_DEPLOY_PATH)
from tcbuilder.errors import \
    (TorizonCoreBuilderError, PathNotExistError)

log = logging.getLogger("torizon." + __name__)

IMAGE_MAJOR_TO_GCC_MAP = {
    5: "gcc-arm-9.2-2019.12",
    6: "arm-gnu-toolchain-11.3.rel1",
    7: "arm-gnu-toolchain-13.3.rel1"
}

OSTREE_KERNEL_SUBDIR_PATH = "usr/lib/modules/{kver}/"
OSTREE_KERNEL_FILENAME = "vmlinuz"
KERNEL_FIT_FILENAME = OSTREE_KERNEL_FILENAME

KARGS_SUPPORTED_BOOTLOADERS = ["U-Boot"]

# Name of the "function" in uEnv.txt responsible for handling boot arguments
# passed by means of an overlay.
SET_BOOTARGS_CUSTOM_RE = r'^\s*set_bootargs_custom='

# Name of the "function" in uEnv.txt responsible for handling boot arguments
# passed as variables in uEnv.txt.
SET_BOOTARGS_CUSTOM2_RE = r'^\s*set_bootargs_custom2='

# List of files/directories under usr/lib/modules/<kver>/ which should not be
# copied from sysroot to the changes directory when preparing the latter for
# building modules.
MOD_DIR_COPY_EXCLUDE_SET = {"dtb"}


def get_kernel_changes_dir():
    """Return directory containing kernel related changes."""
    storage_dir = get_storage_dir()
    return os.path.join(storage_dir, "kernel")


def _kernel_version_from_source(linux_src):
    """Return dictionary with kernel major, minor and revision from source."""

    kernel_release_file = os.path.join(linux_src, "include/config/kernel.release")
    with open(kernel_release_file, "r", encoding="utf-8") as file:
        kernel_release_line = file.read()

    kernel_version = re.match(r"(\d+)\.(\d+)\.(\d+)", kernel_release_line)
    if kernel_version:
        major, minor, rev = kernel_version.group(1, 2, 3)
        return {'major': int(major), 'minor': int(minor), 'rev': int(rev)}

    return None


def _kernel_arch_from_source(linux_src):
    """Determine ARCH based on linux source."""

    config = os.path.join(linux_src, ".config")
    with open(config, "r", encoding="utf-8") as file:
        config_lines = file.read()

    if re.search("CONFIG_ARM=y", config_lines, re.MULTILINE):
        arch = "arm"
    elif re.search("CONFIG_ARM64=y", config_lines, re.MULTILINE):
        arch = "arm64"
    else:
        assert False, "Architecture could not be determined from .config"

    return arch


def _amend_makefile(linux_src):
    """Amend the Linux kernel Makefile to allow building out-of-tree."""

    kversion = _kernel_version_from_source(linux_src)
    if kversion is None:
        raise TorizonCoreBuilderError(
            "Could not determine kernel version of unpacked image. Aborting.")

    # Makefile Hotfix needed to build modules for kernel v6.1:
    if (kversion['major'] == 6 and kversion['minor'] == 1):
        _pattern = r"s/\$(build)=\. prepare/$(build)=./g"
        subprocess.check_output(
            ["sed", "-i", _pattern, f"{linux_src}/Makefile"],
            stderr=subprocess.STDOUT)


def _get_toolchain(image_major_version, linux_src):
    arch = _kernel_arch_from_source(linux_src)
    version_gcc = IMAGE_MAJOR_TO_GCC_MAP.get(image_major_version)
    assert version_gcc, "Unable to determine the GCC toolchain version"

    # Set CROSS_COMPILE and toolchain based on ARCH
    toolchain_path = os.path.join(os.path.dirname(linux_src), "toolchain")
    if arch == "arm":
        c_c = "arm-none-linux-gnueabihf-"
        toolchain = os.path.join(
            toolchain_path, f"{version_gcc}-x86_64-arm-none-linux-gnueabihf/bin")
    elif arch == "arm64":
        c_c = "aarch64-none-linux-gnu-"
        toolchain = os.path.join(
            toolchain_path, f"{version_gcc}-x86_64-aarch64-none-linux-gnu/bin")
    else:
        assert False, "build_module: Unhandled architecture"

    # Download toolchain if needed
    if not os.path.exists(toolchain):
        download_toolchain(c_c, toolchain_path, version_gcc)

    return (toolchain, arch, c_c)


def _prep_linux_src_for_modules_install(src_ostree_archive_dir, linux_src):
    """Prepare linux source for modules_install."""

    # TODO: Consider not relying on OSTree / get the version from the map file itself.
    # Get kernel version for future operations
    repo = ostree.open_ostree(src_ostree_archive_dir)
    kernel_version = ostree.get_kernel_version(repo, ostree.OSTREE_BASE_REF)
    shutil.copyfile(
        os.path.join(linux_src, f"System.map-{kernel_version}"),
        os.path.join(linux_src, "System.map"))
    release_file = os.path.join(linux_src, "include/config/kernel.release")
    with open(release_file, "w", encoding="utf-8") as file:
        file.write(kernel_version)


def _copy_mod_dir_to_mod_path(src_mod_dir, mod_path):
    """Copy modules directory to modules path.

    The source directory is supposed to be in the sysroot and, the target, in a
    "changes" directory. The entries listed in MOD_DIR_COPY_EXCLUDE_SET will be
    excluded from the copy. Also, files already in the destination, will not be
    replaced.
    """

    all_entries = os.listdir(src_mod_dir)
    flt_entries = [
        _entry for _entry in all_entries if _entry not in MOD_DIR_COPY_EXCLUDE_SET
    ]
    flt_entries_with_path = [
        os.path.join(src_mod_dir, _entry) for _entry in flt_entries
    ]

    # Copy files to MOD_PATH; notice the "-n" flag that prevents the overwriting of
    # files; this is important to keep any other files that might be present at the
    # destination due to previous customizations.
    subprocess.check_output(
        ["cp", "-r", "-n", *flt_entries_with_path, mod_path],
        stderr=subprocess.STDOUT)


def build_module(*,
                 src_dir, linux_src, src_mod_dir, image_major_version,
                 src_ostree_archive_dir, mod_path, kernel_changes_dir):
    """Build kernel module from source."""

    (toolchain, arch, c_c) = _get_toolchain(image_major_version, linux_src)
    _amend_makefile(linux_src)

    env_vars = {
        **os.environ.copy(),
        "PATH": f"{os.environ['PATH']}:{toolchain}",
        "KERNEL_SRC": linux_src,
        "KDIR": linux_src
    }

    # Run modules_prepare on kernel source
    subprocess.check_output(
        ["make", "-C", linux_src, f"ARCH={arch}", f"CROSS_COMPILE={c_c}", "modules_prepare"],
        env=env_vars, stdin=subprocess.DEVNULL, stderr=subprocess.STDOUT)

    # Build kernel module in the source directory
    try:
        subprocess.run(
            ["make", "-C", src_dir, f"CROSS_COMPILE={c_c}", f"ARCH={arch}"],
            env=env_vars, stderr=subprocess.STDOUT, check=True)
        print()
    except subprocess.CalledProcessError as exc:
        raise TorizonCoreBuilderError(f"Error building kernel module(s): {exc}") from exc
    finally:
        set_output_ownership(src_dir)

    # Amend some files to allow proper installation
    _prep_linux_src_for_modules_install(src_ostree_archive_dir, linux_src)

    # Copy source module directory to changes directory
    _copy_mod_dir_to_mod_path(src_mod_dir, mod_path)

    # Install modules with modules_install
    install_path = os.path.join(kernel_changes_dir, "usr")
    subprocess.check_output(
        ["make", "-C", linux_src,
         f"ARCH={arch}", f"CROSS_COMPILE={c_c}",
         f"M={src_dir}", f"INSTALL_MOD_PATH={install_path}",
         "INSTALL_MOD_DIR=updates", "modules_install"],
        env=env_vars, stderr=subprocess.STDOUT)

    # Cleanup kernel source
    shutil.rmtree(linux_src)


def autoload_module(module, kernel_changes_dir):
    """Write module name to /etc/modules-load.d to be autoloaded on boot"""

    conf_dir = os.path.join(kernel_changes_dir, "usr/etc/modules-load.d")
    os.makedirs(conf_dir, exist_ok=True)
    module_name = os.path.splitext(os.path.basename(os.path.normpath(module)))[0]

    # Load the modules-load configuration file if one already exists and drop
    # lines listing the module being added.
    conf_file = os.path.join(conf_dir, "tcb.conf")
    conf_lines = []
    if os.path.isfile(conf_file):
        with open(conf_file, "r", encoding="utf-8") as cnfh:
            conf_lines_ = cnfh.readlines()
            conf_lines = [
                _line for _line in conf_lines_ if _line.strip() != module_name
            ]

    # Add the new module line at the end:
    conf_lines.append(f"{module_name}\n")
    with open(conf_file, "w", encoding="utf-8") as cnfh:
        cnfh.writelines(conf_lines)


def download_toolchain(toolchain, toolchain_path, version_gcc):
    """Download toolchain from online if it doesn't already exist"""

    url_prefix = "https://sources.toradex.com/tcb/toolchains/"
    if toolchain == "arm-none-linux-gnueabihf-":
        tarball = f"{version_gcc}-x86_64-arm-none-linux-gnueabihf.tar.xz"
    elif toolchain == "aarch64-none-linux-gnu-":
        tarball = f"{version_gcc}-x86_64-aarch64-none-linux-gnu.tar.xz"
    else:
        assert False, f"download_toolchain: unhandled toolchain {toolchain}"
    url = url_prefix + tarball

    log.info("A toolchain is required to build the module.")
    log.info(f"Downloading toolchain from {url}.")
    log.info("Please wait this could take a while...")

    try:
        with download_progress() as reporthook:
            urllib.request.urlretrieve(url, filename=tarball, reporthook=reporthook)
    except Exception as exc:
        raise TorizonCoreBuilderError(
            "The requested toolchain could not be downloaded") from exc

    log.info("Download Complete!")

    log.info("Unpacking downloaded toolchain into storage.")
    os.makedirs(toolchain_path, exist_ok=True)
    tarcmd = [
        "tar",
        "-xf", tarball,
        "-C", toolchain_path,
    ] + get_tar_compress_program_options(tarball)
    subprocess.check_output(tarcmd, stderr=subprocess.STDOUT)
    os.remove(tarball)
    log.info("Toolchain successfully unpacked.\n")


def find_kernel_in_sysroot():
    """
    Find kernel binary path in the unpacked image sysroot. Raises an error if
    it cannot find it.

    :returns: String with absolute path of the kernel binary inside sysroot.
    """

    storage_dir = get_storage_dir()
    sysroot_path = os.path.join(storage_dir, "sysroot")

    # As the kernel path is composed of directories named after the deployment commit and the
    # kernel version, get them via OSTree metadata.

    sysroot_obj = ostree.load_sysroot(sysroot_path)

    csum, _ = ostree.get_deployment_info_from_sysroot(sysroot_obj)
    kernel_version = ostree.get_kernel_version(sysroot_obj.repo(), csum)

    # Add deployment index part to checksum string, which is 0 for a new deployment
    csum += ".0"

    kernel_path = os.path.join(
        OSTREE_ROOT_DEPLOY_PATH.format(csum=csum),
        OSTREE_KERNEL_SUBDIR_PATH.format(kver=kernel_version)
    )
    kernel_path = os.path.join(sysroot_path, kernel_path, OSTREE_KERNEL_FILENAME)

    if os.path.isfile(kernel_path):
        log.debug("Kernel found at '%s'", kernel_path)
    else:
        raise PathNotExistError("Kernel not found in unpacked rootfs. Aborting.")

    return kernel_path


def get_kernel_subdir():
    """Get the versioned kernel directory.

    Returns "usr/lib/modules/<kver>" where <kver> is determined
    automatically. This is where the kernel binary is supposed to live.
    """

    storage_dir = get_storage_dir()
    src_sysroot_dir = os.path.join(storage_dir, "sysroot")
    src_sysroot = ostree.load_sysroot(src_sysroot_dir)
    csum, _ = ostree.get_deployment_info_from_sysroot(src_sysroot)
    kernel_version = ostree.get_kernel_version(src_sysroot.repo(), csum)
    return OSTREE_KERNEL_SUBDIR_PATH.format(kver=kernel_version)


def find_kernel_in_changes_dir(changes_dir, basename=None):
    """Find path of kernel binary in the given changes directory."""

    kernel_subdir = get_kernel_subdir()
    kernel_src_dir = os.path.join(changes_dir, kernel_subdir)
    kernel_src_path = os.path.join(kernel_src_dir, basename or OSTREE_KERNEL_FILENAME)
    if os.path.isfile(kernel_src_path):
        log.debug("Kernel found at '%s'", kernel_src_path)
    else:
        log.debug("Kernel not found at '%s'", kernel_src_path)
        return None

    return kernel_src_path


def copy_kernel_to_changes_dir(changes_dir, *, basename=None):
    """Copy kernel FIT image from sysroot to changes directory.

    Find kernel in sysroot and copy it to the appropriate subdirectory in the
    specified changes directory. The copy is done only if the kernel binary
    does not yet exist in the destination.
    """

    kernel_subdir = get_kernel_subdir()
    kernel_tgt_dir = os.path.join(changes_dir, kernel_subdir)
    kernel_tgt_path = os.path.join(kernel_tgt_dir, basename or OSTREE_KERNEL_FILENAME)
    if not os.path.isfile(kernel_tgt_path):
        log.debug("Kernel does not exist in '%s'", kernel_tgt_path)
        os.makedirs(kernel_tgt_dir, exist_ok=True)
        kernel_src_path = find_kernel_in_sysroot()
        log.debug("Copying '%s' -> '%s'", kernel_src_path, kernel_tgt_path)
        shutil.copy2(kernel_src_path, kernel_tgt_path)
    else:
        log.debug("Kernel already exists in '%s'", kernel_tgt_path)

    return kernel_tgt_path


def get_supported_bootargs_methods():
    """Determine the set of bootargs passing methods supported by the current image."""

    uenv_txt_path = dt.get_current_uenv_txt_path()
    method_re = {
        "overlay": re.compile(SET_BOOTARGS_CUSTOM_RE),
        "uenv": re.compile(SET_BOOTARGS_CUSTOM2_RE)
    }
    found_methods = set()
    with open(uenv_txt_path, "r", encoding="utf-8") as fhandle:
        for line in fhandle:
            for meth, regex in method_re.items():
                if regex.match(line):
                    found_methods.add(meth)
    log.debug("Supported bootargs passing methods: %s", str(found_methods))
    return found_methods
