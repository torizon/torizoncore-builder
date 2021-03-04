"""
Backend functions and functionality for all kernel commands
"""

import subprocess
import os
import re
import shutil
import logging
import traceback

from tcbuilder.backend import ostree
from tcbuilder.errors import TorizonCoreBuilderError

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
    if arch == "arm":
        c_c = "arm-none-linux-gnueabihf-"
        toolchain = "/builder/gcc-arm-9.2-2019.12-x86_64-arm-none-linux-gnueabihf/bin"
    if arch == "arm64":
        c_c = "aarch64-none-linux-gnu-"
        toolchain = "/builder/gcc-arm-9.2-2019.12-x86_64-aarch64-none-linux-gnu/bin"

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


def set_custom_args():
    """Apply new kernel arguments"""

    pass
