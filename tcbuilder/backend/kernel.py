"""
Backend functions and functionality for all kernel commands
"""

import glob
import subprocess
import os
import re
import shutil
import logging
import urllib.request

from tcbuilder.backend import ostree
from tcbuilder.backend.common import (get_tar_compress_program_options, progress,
                                      set_output_ownership)
from tcbuilder.errors import TorizonCoreBuilderError

log = logging.getLogger("torizon." + __name__)

IMAGE_MAJOR_TO_GCC_MAP = {
    5: "gcc-arm-9.2-2019.12",
    6: "arm-gnu-toolchain-11.3.rel1",
    7: "arm-gnu-toolchain-13.3.rel1"
}


def get_kernel_changes_dir(storage_dir):
    """Return directory containing kernel related changes"""

    return os.path.join(storage_dir, "kernel")


def get_kernel_version(linux_src):
    """Return dictionary with kernel major, minor and revision from source."""

    kernel_release_file = os.path.join(linux_src, "include/config/kernel.release")
    with open(kernel_release_file, 'r') as file:
        kernel_release_line = file.read()

    kernel_version = re.match(r"(\d+)\.(\d+)\.(\d+)", kernel_release_line)
    if kernel_version:
        major, minor, rev = kernel_version.group(1, 2, 3)
        return {'major': int(major), 'minor': int(minor), 'rev': int(rev)}

    return None


# pylint: disable=too-many-locals
def build_module(src_dir, linux_src, src_mod_dir, image_major_version,
                 src_ostree_archive_dir, mod_path, kernel_changes_dir):
    """Build kernel module from source"""

    # Figure out ARCH based on linux source
    config = os.path.join(linux_src, ".config")
    with open(config, 'r') as file:
        config_lines = file.read()

    if re.search("CONFIG_ARM=y", config_lines, re.MULTILINE):
        arch = "arm"
    elif re.search("CONFIG_ARM64=y", config_lines, re.MULTILINE):
        arch = "arm64"
    else:
        assert False, "Architecture could not be determined from .config"

    version_gcc = IMAGE_MAJOR_TO_GCC_MAP.get(image_major_version)

    assert version_gcc, "Unable to determine the GCC toolchain version"

    # Set CROSS_COMPILE and toolchain based on ARCH
    toolchain_path = os.path.join(os.path.dirname(linux_src), "toolchain")
    if arch == "arm":
        c_c = "arm-none-linux-gnueabihf-"
        toolchain = os.path.join(toolchain_path,
                                 f"{version_gcc}-x86_64-arm-none-linux-gnueabihf/bin")
    if arch == "arm64":
        c_c = "aarch64-none-linux-gnu-"
        toolchain = os.path.join(toolchain_path,
                                 f"{version_gcc}-x86_64-aarch64-none-linux-gnu/bin")

    # Download toolchain if needed
    if not os.path.exists(toolchain):
        download_toolchain(c_c, toolchain_path, version_gcc)

    kversion = get_kernel_version(linux_src)

    if kversion is None:
        raise TorizonCoreBuilderError(
            "Could not determine kernel version of unpacked image. Aborting.")

    # Makefile Hotfix needed to build modules for kernel v6.1:
    if (kversion['major'] == 6 and kversion['minor'] == 1):
        _pattern = r"s/\$(build)=\. prepare/$(build)=./g"
        subprocess.check_output(
            ["sed", "-i", _pattern, f"{linux_src}/Makefile"],
            stderr=subprocess.STDOUT)

    env_path = {
        **os.environ.copy(),
        "PATH": f"{os.environ['PATH']}:{toolchain}",
    }

    # Run modules_prepare on kernel source
    cmd = [
        "make", "-C", linux_src,
        f"ARCH={arch}",
        f"CROSS_COMPILE={c_c}",
        "modules_prepare",
    ]
    subprocess.check_output(cmd, stdin=subprocess.DEVNULL, stderr=subprocess.STDOUT, env=env_path)

    # Build kernel module source
    try:
        extra_env = {
            **env_path,
            "KERNEL_SRC": linux_src,
            "KDIR": linux_src,
        }
        cmd = [
            "make", "-C", src_dir,
            f"CROSS_COMPILE={c_c}",
            f"ARCH={arch}",
        ]
        subprocess.run(cmd, stderr=subprocess.STDOUT, check=True, env=extra_env)
        print()
    except subprocess.CalledProcessError as exc:
        raise TorizonCoreBuilderError(f"Error building kernel module(s): {exc}") from exc
    finally:
        set_output_ownership(src_dir)

    # Get kernel version for future operations
    repo = ostree.open_ostree(src_ostree_archive_dir)
    kernel_version = ostree.get_kernel_version(repo, ostree.OSTREE_BASE_REF)

    # Prepare linux source for modules_install
    map_file = os.path.join(linux_src, f"System.map-{kernel_version}")
    dest = os.path.join(linux_src, "System.map")
    shutil.copyfile(map_file, dest)
    release_file = os.path.join(linux_src, "include/config/kernel.release")
    with open(release_file, 'w') as file:
        file.write(kernel_version)

    # Copy source module directory to changes directory
    install_path = os.path.join(kernel_changes_dir, "usr")
    subprocess.check_output(["cp", "-r", *glob.glob(f"{src_mod_dir}/*"), mod_path],
                            stderr=subprocess.STDOUT)
    shutil.rmtree(os.path.join(mod_path, "dtb"))

    # Install modules with modules_install
    cmd = [
        "make", "-C", linux_src,
        f"ARCH={arch}",
        f"CROSS_COMPILE={c_c}",
        f"M={src_dir}",
        f"INSTALL_MOD_PATH={install_path}",
        "INSTALL_MOD_DIR=updates",
        "modules_install",
    ]
    subprocess.check_output(cmd, stderr=subprocess.STDOUT, env=env_path)

    # Cleanup kernel source
    shutil.rmtree(linux_src)

# pylint: enable=too-many-locals


def autoload_module(module, kernel_changes_dir):
    """Write module name to /etc/modules-load.d to be autoloaded on boot"""

    conf_dir = os.path.join(kernel_changes_dir, "usr/etc/modules-load.d")
    os.makedirs(conf_dir, exist_ok=True)
    module_name = os.path.splitext(os.path.basename(os.path.normpath(module)))[0]

    conf_file = os.path.join(conf_dir, "tcb.conf")
    with open(conf_file, 'a') as file:
        file.write(f"{module_name} \n")


def download_toolchain(toolchain, toolchain_path, version_gcc):
    """Download toolchain from online if it doesn't already exist"""

    url_prefix = "http://sources.toradex.com/tcb/toolchains/"
    if toolchain == "arm-none-linux-gnueabihf-":
        tarball = f"{version_gcc}-x86_64-arm-none-linux-gnueabihf.tar.xz"
    if toolchain == "aarch64-none-linux-gnu-":
        tarball = f"{version_gcc}-x86_64-aarch64-none-linux-gnu.tar.xz"
    url = url_prefix + tarball

    log.info("A toolchain is required to build the module.\n"
             f"Downloading toolchain from {url}.\n"
             "Please wait this could take a while...")

    try:
        urllib.request.urlretrieve(url, filename=tarball, reporthook=progress)
        log.info("\nDownload Complete!\n")
    except:
        raise TorizonCoreBuilderError("The requested toolchain could not be downloaded")

    log.info("Unpacking downloaded toolchain into storage")
    os.makedirs(toolchain_path, exist_ok=True)
    tarcmd = [
        "tar",
        "-xf", tarball,
        "-C", toolchain_path,
    ] + get_tar_compress_program_options(tarball)
    subprocess.check_output(tarcmd, stderr=subprocess.STDOUT)
    os.remove(tarball)
    log.info("Toolchain successfully unpacked.\n")
