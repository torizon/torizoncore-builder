"""
Backend functions and functionality for all kernel commands
"""

import subprocess
import os
import re
import shutil
import logging
import traceback
import urllib.request

from tcbuilder.backend import ostree
from tcbuilder.backend.common import get_unpack_command, progress
from tcbuilder.errors import TorizonCoreBuilderError

log = logging.getLogger("torizon." + __name__)

MAJOR_TO_GCC_MAP = {
    5: "gcc-arm-9.2-2019.12",
    6: "arm-gnu-toolchain-11.3.rel1"
}


def get_kernel_changes_dir(storage_dir):
    """Return directory containing kernel related changes"""

    return os.path.join(storage_dir, "kernel")


# pylint: disable=too-many-locals
def build_module(src_dir, linux_src, src_mod_dir,
                 src_ostree_archive_dir, mod_path, kernel_changes_dir):
    """Build kernel module from source"""

    # Figure out ARCH based on linux source
    config = os.path.join(linux_src, ".config")
    with open(config, 'r') as file:
        lines = file.read()

    if re.search("CONFIG_ARM=y", lines, re.MULTILINE):
        arch = "arm"
    elif re.search("CONFIG_ARM64=y", lines, re.MULTILINE):
        arch = "arm64"
    else:
        assert False, "Achitecture could not be determined from .config"

    version_gcc = None
    version_major = re.search(r"CONFIG_LOCALVERSION=\"-(\d+)\.\d+\.\d+", lines,
                              re.MULTILINE)
    if version_major:
        version_major = int(version_major.group(1))
        version_gcc = MAJOR_TO_GCC_MAP[version_major]

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

    # Run modules_prepare on kernel source
    subprocess.check_output(f"""PATH=$PATH:{toolchain} make -C {linux_src} ARCH={arch} \
        CROSS_COMPILE={c_c} modules_prepare""", shell=True, stderr=subprocess.STDOUT)

    # Build kernel module source
    try:
        subprocess.run(f"""PATH=$PATH:{toolchain} KERNEL_SRC={linux_src} KDIR={linux_src} \
            CROSS_COMPILE={c_c} ARCH={arch} make -C {src_dir}""",
                       shell=True, stderr=subprocess.STDOUT, check=True)
        print()
    except:
        logging.error(traceback.format_exc())
        raise TorizonCoreBuilderError("Error building kernel module(s)!")

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
    subprocess.check_output(f"cp -r {src_mod_dir}/* {mod_path}",
                            shell=True, stderr=subprocess.STDOUT)
    shutil.rmtree(os.path.join(mod_path, "dtb"))

    # Install modules with modules_install
    subprocess.check_output(f"""PATH=$PATH:{toolchain} make -C {linux_src} ARCH={arch} \
        CROSS_COMPILE={c_c} M={src_dir} INSTALL_MOD_PATH={install_path} modules_install""",
                            shell=True, stderr=subprocess.STDOUT)

    # Cleanup kernel source
    shutil.rmtree(linux_src)

# pylint: enable=too-many-locals


def autoload_module(module, kernel_changes_dir):
    """Write module name to /etc/modules-load.d to be autloaded on boot"""

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
    tarcmd = "cat '{0}' | {1} | tar -xf - -C {2}".format(
                tarball, get_unpack_command(tarball), toolchain_path)
    subprocess.check_output(tarcmd, shell=True, stderr=subprocess.STDOUT)
    os.remove(tarball)
    log.info("Toolchain successfully unpacked.\n")
