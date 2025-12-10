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

BACKSLASH_SPC_RE = re.compile(r"\\\s*$")


def get_dt_changes_dir(storage_dir):
    """Returns the directory that contains external device tree related changes."""
    return os.path.join(storage_dir, "dt")


# TODO: Consider moving the various "uenv" functions to a separate module (other than common).
def get_current_uenv_txt_path(storage_dir):
    """Get the path to the currently applied uEnv.txt, the bootloader environment file."""

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


def set_uenv_txt_variable(var_name, var_value, *,
                          changes_dir, storage_dir, append=False):
    """Set/clear a variable in uEnv.txt storing the modified file in the changes directory.

    :param var_name: Name of the variable.
    :param var_value: Value of the variable; if None is passed, the variable
        will be cleared (removed from the file).
    :param changes_dir: Path to changes directory.
    :param storage_dir: Path to storage directory.
    :param append: If False (default), the new variable assignment is added at
        the beginning of the uEnv.txt file; otherwise, it's added at its end.
    :returns: True if the variable existed in uEnv.txt; False, otherwise."""

    # Load original file:
    uenv_src_path = get_current_uenv_txt_path(storage_dir)
    with open(uenv_src_path, "r", encoding="utf-8") as fhandle:
        lines = fhandle.readlines()

    # Status indicates that the variable was set before.
    status = False

    # Drop lines assigning to the desired variable (lines may be continued by
    # a backslash at the end):
    ign_cont = False
    new_lines = []
    for line in lines:
        if ign_cont:
            if not BACKSLASH_SPC_RE.search(line):
                ign_cont = False
        elif line.startswith(f"{var_name}="):
            status = True
            if BACKSLASH_SPC_RE.search(line):
                ign_cont = True
        else:
            new_lines.append(line)

    if var_value is None:
        # Variable is being deleted.
        pass
    elif append:
        # Add assignment as the last line.
        assgn_str = f"{var_name}={var_value}\n"
        new_lines.append(assgn_str)
    else:
        # Add assignment as the first line.
        assgn_str = f"{var_name}={var_value}\n"
        new_lines.insert(0, assgn_str)

    # Save modified version of the file:
    uenv_target_dir = os.path.join(changes_dir, "usr", "lib", "ostree-boot")
    uenv_target_path = os.path.join(uenv_target_dir, "uEnv.txt")
    os.makedirs(uenv_target_dir, exist_ok=True)
    with open(uenv_target_path, "w", encoding="utf-8") as fhandle:
        fhandle.writelines(new_lines)

    return status


def get_uenv_txt_variable(var_name, *, storage_dir, drop_cont=False):
    """Get a variable from the current uEnv.txt.

    By default, if the variable setting in uEnv.txt was split into multiple-lines
    in the source file, the returned value will be a string with embedded new-line
    characters including the backslash at end of each line indicating the line
    continuation. This behavior can be changed by 'drop_cont'.

    :param var_name: Name of the variable.
    :param storage_dir: Path to the storage directory.
    :param drop_cont: Drop the continuaton string at the end of the lines
        effectively joining all lines together.

    """

    # Load original file:
    uenv_src_path = get_current_uenv_txt_path(storage_dir)
    with open(uenv_src_path, "r", encoding="utf-8") as fhandle:
        lines = fhandle.readlines()

    assgn_str = f"{var_name}="
    var_value = None

    # Find the assignment (handling the multi-line case); in case of multiple
    # assignments get the value of the last one:
    cont = False
    for line in lines:
        if cont:
            var_value.append(line)
            if not BACKSLASH_SPC_RE.search(line):
                cont = False
        elif line.startswith(assgn_str):
            var_value = []
            var_value.append(line[len(assgn_str):])
            if BACKSLASH_SPC_RE.search(line):
                cont = True

    # Drop the continuation string from all intermediate lines:
    if var_value and drop_cont:
        for _idx, _val in enumerate(var_value[:-1]):
            var_value[_idx] = _val[:_val.rindex("\\")]

    # Drop the newline character of the last line:
    if var_value:
        if "\n" in var_value[-1]:
            _val = var_value[-1]
            var_value[-1] = _val[:_val.rindex("\n")]

    if var_value is not None:
        var_value = "".join(var_value)

    return var_value


def get_uboot_initial_env_path(storage_dir):
    """Get the path to u-boot-initial-env-sd, the initial bootloader environment set by Tezi."""
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
    """Query the value of variable 'name' in configuration file 'path'.
       Returns an empty string if the variable does not exist in the file."""
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
    """Query the base name of the currently applied device tree blob."""

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
    """Returns "usr/lib/modules/<kernel_version/dtb"."""

    answer = subprocess.check_output(
        ("set -o pipefail && "
         f"find {storage_dir}/sysroot/ostree/deploy -type d -name dtb -print -quit |"
         " sed -r -e 's|.*/(usr/lib/modules/)|\\1|'"),
        shell=True, text=True).strip()
    assert answer, "panic: missing kernel device tree directory!"
    return answer


def get_current_dtb_path(storage_dir):
    """Query the path to the currently applied device tree blob.

    This works with non-FIT kernel images only. With FIT, the DTBs do not have a path
    since they are just nodes inside the kernel image.

    Returns a tuple (path, ensured) where:
        - 'path' is the path to a device tree blob in the filesystem (ensured to exist).
        - 'ensured' is True if 'path' was detected as the current device tree in the
          boot loader configuration. False means that the current device tree cannot
          be retrieved from configs (e.g. decided at runtime), and an arbitrary device
          tree blob of the base image was chosen instead.
    """

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
    """Compile a device tree source file.

    Compile the device tree source file 'source_dts_path' to 'target_dtb_path'.
    Returns True on successful compilation, False otherwise.
    """
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
