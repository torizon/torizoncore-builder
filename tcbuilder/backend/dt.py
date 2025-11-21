"""
Backend for the DT (device-tree) related operations.
"""

import logging
import json
import os
import shlex
import subprocess
import sys
import re

from tcbuilder.errors import (InvalidDataError, InvalidStateError)
from tcbuilder.backend.kernel import get_kernel_changes_dir
from tcbuilder.backend.common import is_file_type_dtb

log = logging.getLogger("torizon." + __name__)

DTB_PREFIX_RE = re.compile(r'bootm[^#]*#conf-([^$]*)\$')


def get_dt_changes_dir(storage_dir):
    '''Returns the directory that contains external device tree related changes.'''
    return os.path.join(storage_dir, "dt")


def get_current_uenv_txt_path(storage_dir):
    '''Get the path to the currently applied uEnv.txt, the bootloader environment file.'''

    # Look for the file in two changes directories; the former is used with
    # non-FIT whereas the latter with FIT images.
    dchangesdir = get_dt_changes_dir(storage_dir)
    dpath = os.path.join(dchangesdir, "usr", "lib", "ostree-boot", "uEnv.txt")
    kchangesdir = get_kernel_changes_dir(storage_dir)
    kpath = os.path.join(kchangesdir, "usr", "lib", "ostree-boot", "uEnv.txt")

    if os.path.exists(dpath) and os.path.exists(kpath):
        raise InvalidStateError(
            f"Bad storage state: uEnv.txt was found both in '{dpath}' and '{kpath}'")

    for _path in (dpath, kpath):
        if os.path.exists(_path):
            log.debug(f"Found uEnv.txt in changes dir: '{_path}'")
            return _path

    # Check for the ostree-managed version of the file in the deployment; this
    # finds the commited version of the file rather the modified copy produced
    # by libostree in the boot directory when a deployment is created.
    dpath = subprocess.check_output(
        ["find", f"{storage_dir}/sysroot/ostree/deploy",
         "-wholename", "*/usr/lib/ostree-boot/uEnv.txt",
         "-print", "-quit"],
        shell=False, text=True).strip()
    assert dpath and os.path.exists(dpath), "panic: missing uEnv.txt in base image!"
    log.debug(f"Found uEnv.txt in deployment: '{dpath}'")

    return dpath


def get_uboot_initial_env_path(storage_dir):
    '''Get the path to u-boot-initial-env-sd, the initial bootloader environment set by Tezi.'''
    image_json_path = os.path.join(storage_dir, "tezi", "image.json")
    assert os.path.exists(image_json_path), "panic: missing image.json in Tezi directory!"
    with open(image_json_path, "r", encoding="utf-8") as jsonf:
        image_json = json.load(jsonf)
    try:
        initial_env_basename = image_json["u_boot_env"]
    except KeyError:
        initial_env_basename = None
    assert initial_env_basename, \
        "panic: missing 'u_boot_env' key in image.json in Tezi directory!"
    initial_env_path = os.path.join(storage_dir, "tezi", initial_env_basename)
    assert os.path.exists(initial_env_path), \
        f"panic: missing {initial_env_basename} in Tezi directory!"
    return initial_env_path


def query_variable_in_config_file(name, path):
    '''Query the value of variable 'name' in configuration file 'path'.
       Returns an empty string if the variable does not exist in the file.'''
    proc = subprocess.run(
        ["sed", "-e", f"/^{name}=/!d", "-e", "s/^[^=]*=//", "-e", "q", path],
        check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        # This Should Never Happen (TM)
        log.error(proc.stderr)
        log.error(f"error: cannot search file '{os.path.basename(path)}'! -- missing 'unpack'?")
        sys.exit(1)
    return proc.stdout.strip()


def get_current_dtb_basename(storage_dir):
    '''Query the base name of the currently applied device tree blob.'''

    # Find the value of fdtfile in uEnv.txt
    dtb_basename = query_variable_in_config_file("fdtfile", get_current_uenv_txt_path(storage_dir))
    if dtb_basename:
        return dtb_basename

    # fdtfile is not defined in uEnv.txt.
    # Find the value of fdtfile in u-boot-initial-env-sd instead.
    dtb_basename = query_variable_in_config_file("fdtfile", get_uboot_initial_env_path(storage_dir))
    if dtb_basename:
        return dtb_basename

    # Cannot identify the applied device tree.
    return None


def get_dtb_kernel_subdir(storage_dir):
    '''Returns "usr/lib/modules/<kernel_version/dtb".'''

    answer = subprocess.check_output(
        ("set -o pipefail && "
         f"find {storage_dir}/sysroot/ostree/deploy -type d -name dtb -print -quit |"
         " sed -r -e 's|.*/(usr/lib/modules/)|\\1|'"),
        shell=True, text=True).strip()
    assert answer, "panic: missing kernel device tree directory!"
    return answer


def get_current_dtb_path(storage_dir):
    '''Query the path to the currently applied device tree blob.

    Returns a tuple (path, ensured) where:
        - 'path' is the path to a device tree blob in the filesystem (ensured to exist).
        - 'ensured' is True if 'path' was detected as the current device tree in the
          boot loader configuration. False means that the current device tree cannot
          be retrieved from configs (e.g. decided at runtime), and an arbitrary device
          tree blob of the base image was chosen instead.
    '''
    dtb_basename = get_current_dtb_basename(storage_dir)
    if dtb_basename:
        # Found a real definition of the device tree in boot loader configuration.
        # Find the path to this device tree, or die trying.
        answer = os.path.join(get_dt_changes_dir(storage_dir),
                              get_dtb_kernel_subdir(storage_dir), dtb_basename)
        if os.path.exists(answer):
            # This is a recently applied device tree.
            return (answer, True)
        # This is a device tree from the base image.
        answer = subprocess.check_output(
            ["find", f"{storage_dir}/sysroot/ostree/deploy", "-type", "f",
             "-name", dtb_basename, "-print", "-quit"],
            text=True).strip()
        assert os.path.exists(answer), f"panic: missing device tree blob file for {dtb_basename}!"
        return (answer, True)

    # Cannot identify the device tree by peeking the boot loader configuration.
    # Hint by returning the first device tree blob found in the base image.
    answer = subprocess.check_output(
        ["find", f"{storage_dir}/sysroot/ostree/deploy", "-type", "f",
         "-name", "*.dtb", "-print", "-quit"],
        text=True).strip()
    assert os.path.exists(answer), "panic: missing device tree blobs in base image!"
    return (answer, False)


def build_dts(source_dts_path, include_dirs, target_dtb_path):
    '''Compile the device tree source file 'source_dts_path' to 'target_dtb_path'.
       Returns True on successful compilation, False otherwise.
   '''
    opt_includes = []
    for include_dir in include_dirs:
        opt_includes.append("-I")
        opt_includes.append(shlex.quote(include_dir))
    opt_includes = " ".join(opt_includes)
    try:
        # Check if dtc is present in the environment
        dtc_version = subprocess.check_output(
            "dtc --version",
            shell=True, text=True, stderr=subprocess.STDOUT)
        dtc_version = dtc_version.rstrip().split(': ')[1]
        log.info(f"Compiling Device Tree with {dtc_version}...")

        dtc_output = subprocess.check_output(
            ("set -o pipefail && "
             f"cpp -nostdinc -undef -x assembler-with-cpp {opt_includes} "
             f"{shlex.quote(source_dts_path)} "
             f"| dtc -I dts -O dtb -@ -o {shlex.quote(target_dtb_path)}"),
            shell=True, text=True, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as exc:
        log.error(exc.output.strip())
        return False

    dtc_warning_match = re.search('warning', dtc_output, re.IGNORECASE)

    if logging.root.level > logging.DEBUG and dtc_warning_match:
        log.info("The device tree was compiled with warnings. To view them, run the command again "
                 "with debug log level enabled (torizoncore-builder --log-level debug <command>).")
        log.info("Please note that some warnings can come from .dtsi files included in the device "
                 "tree source e.g. from the SoC vendor.")
        log.info("The warnings don't necessarily indicate a breaking issue with the device tree.")

    log.debug("OUTPUT FROM DEVICE TREE COMPILER")
    log.debug(dtc_output)
    log.debug("END OF DEVICE TREE COMPILER OUTPUT")

    if not is_file_type_dtb(target_dtb_path):
        log.error(f"error: compilation of '{source_dts_path}' did not produce"
                  " a Device Tree Blob.")
        return False

    log.info(f"File '{os.path.basename(source_dts_path)}' compiles successfully.")
    return True


def get_kernelfit_dtb_prefix(storage_dir, defval=None):
    """Get the configuration name prefix used with kernel FIT images.

    The configuration name prefix is a string added to the name of a DTB when
    referencing that DTB inside a FIT image in the "bootm" command. For example,
    with NXP the prefix could be "freescale_" and when booting with a DTB file
    named "my-device-tree.dtb" the "bootm" command would be something like this:

    bootm KERNEL_ADDR#conf-freescale_my-device-tree.dtb

    The prefix is determined from uEnv.txt which is supposed to have the "bootm"
    invocation.
    """

    uenv_path = get_current_uenv_txt_path(storage_dir)
    with open(uenv_path, "r", encoding="utf-8") as fhandle:
        lines = fhandle.readlines()
    res = None
    for line in lines:
        match = DTB_PREFIX_RE.search(line)
        if match:
            res = match.group(1)
            break
    if res is None and defval is None:
        raise InvalidDataError(
            "Cannot determine DTB prefix used inside FIT image from uEnv.txt")
    if res is None:
        res = defval
    log.debug("Determined DTB prefix from uEnv.txt: '%s'", res)
    return res
