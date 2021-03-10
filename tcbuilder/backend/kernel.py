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

def get_kernel_changes_dir(storage_dir):
    """Return directory containing kernel related changes"""

    return os.path.join(storage_dir, "kernel")

def build_module(src_dir, linux_src, src_mod_dir,
                 src_ostree_archive_dir, mod_path, kernel_changes_dir):
    """Build kernel module from source"""

    # Figure out ARCH based on linux source
    config = os.path.join(linux_src, ".config")
    file = open(config, 'r')
    lines = file.readlines()
    for line in lines:
        if re.search("CONFIG_ARM=y", line):
            arch = "arm"
            break
        if re.search("CONFIG_ARM64=y", line):
            arch = "arm64"
            break

    # Set CROSS_COMPILE and toolchain based on ARCH
    toolchain_path = os.path.join(os.path.dirname(linux_src), "toolchain")
    if arch == "arm":
        c_c = "arm-none-linux-gnueabihf-"
        toolchain = os.path.join(toolchain_path,
                                 "gcc-arm-9.2-2019.12-x86_64-arm-none-linux-gnueabihf/bin")
    if arch == "arm64":
        c_c = "aarch64-none-linux-gnu-"
        toolchain = os.path.join(toolchain_path,
                                 "gcc-arm-9.2-2019.12-x86_64-aarch64-none-linux-gnu/bin")

    # Download toolchain if needed
    if not os.path.exists(toolchain):
        download_toolchain(c_c, toolchain_path)

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

    # Install modules with modules_install
    subprocess.check_output(f"""PATH=$PATH:{toolchain} make -C {linux_src} ARCH={arch} \
        CROSS_COMPILE={c_c} M={src_dir} INSTALL_MOD_PATH={install_path} modules_install""",
                            shell=True, stderr=subprocess.STDOUT)

    # Cleanup kernel source
    shutil.rmtree(linux_src)

def autoload_module(module, kernel_changes_dir):
    """Write module name to /etc/modules-load.d to be autloaded on boot"""

    conf_dir = os.path.join(kernel_changes_dir, "usr/etc/modules-load.d")
    os.makedirs(conf_dir, exist_ok=True)
    module_name = os.path.splitext(os.path.basename(os.path.normpath(module)))[0]

    conf_file = os.path.join(conf_dir, "tcb.conf")
    with open(conf_file, 'a') as file:
        file.write(f"{module_name} \n")

def download_toolchain(toolchain, toolchain_path):
    """Download toolchain from online if it doesn't already exist"""

    url_prefix = "http://sources.toradex.com/tcb/toolchains/"
    if toolchain == "arm-none-linux-gnueabihf-":
        tarball = "gcc-arm-9.2-2019.12-x86_64-arm-none-linux-gnueabihf.tar.xz"
    if toolchain == "aarch64-none-linux-gnu-":
        tarball = "gcc-arm-9.2-2019.12-x86_64-aarch64-none-linux-gnu.tar.xz"
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
