"""
Backend for the uEnv.txt (bootloader environment file) related operations.
"""

import logging
import os
import re
import subprocess

from tcbuilder.errors import InvalidStateError
from tcbuilder.backend.common import \
    (get_storage_dir, get_changes_dir, DT_CHANGES_SUBDIR, KERNEL_CHANGES_SUBDIR)

log = logging.getLogger("torizon." + __name__)

BACKSLASH_SPC_RE = re.compile(r"\\\s*$")


def get_current_uenv_txt_path():
    """Get the path to the currently applied uEnv.txt, the bootloader environment file."""

    # Look for the file in two changes directories; the former is used with
    # non-FIT whereas the latter with FIT images.
    storage_dir = get_storage_dir()
    dchangesdir = get_changes_dir(DT_CHANGES_SUBDIR)
    dpath = os.path.join(dchangesdir, "usr", "lib", "ostree-boot", "uEnv.txt")
    kchangesdir = get_changes_dir(KERNEL_CHANGES_SUBDIR)
    kpath = os.path.join(kchangesdir, "usr", "lib", "ostree-boot", "uEnv.txt")

    if os.path.exists(dpath) and os.path.exists(kpath):
        raise InvalidStateError(
            f"Bad storage state: uEnv.txt was found both in '{dpath}' and '{kpath}'")

    for _path in (dpath, kpath):
        if os.path.exists(_path):
            log.debug(f"Found uEnv.txt in changes dir: '{_path}'")
            return _path

    # Check for the ostree-managed version of the file in the deployment; this
    # finds the committed version of the file rather the modified copy produced
    # by libostree in the boot directory when a deployment is created.
    dpath = subprocess.check_output(
        ["find", f"{storage_dir}/sysroot/ostree/deploy",
         "-wholename", "*/usr/lib/ostree-boot/uEnv.txt",
         "-print", "-quit"],
        text=True).strip()
    assert dpath and os.path.exists(dpath), "panic: missing uEnv.txt in base image!"
    log.debug(f"Found uEnv.txt in deployment: '{dpath}'")

    return dpath


def set_uenv_txt_variable(var_name, var_value, *, changes_dir, append=False):
    """Set/clear a variable in uEnv.txt storing the modified file in the changes directory.

    :param var_name: Name of the variable.
    :param var_value: Value of the variable; if None is passed, the variable
        will be cleared (removed from the file).
    :param changes_dir: Path to changes directory.
    :param append: If False (default), the new variable assignment is added at
        the beginning of the uEnv.txt file; otherwise, it's added at its end.
    :returns: True if the variable existed in uEnv.txt; False, otherwise."""

    # Load original file:
    uenv_src_path = get_current_uenv_txt_path()
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


def get_uenv_txt_variable(var_name, *, drop_cont=False):
    """Get a variable from the current uEnv.txt.

    By default, if the variable setting in uEnv.txt was split into multiple-lines
    in the source file, the returned value will be a string with embedded new-line
    characters including the backslash at end of each line indicating the line
    continuation. This behavior can be changed by 'drop_cont'.

    :param var_name: Name of the variable.
    :param drop_cont: Drop the continuaton string at the end of the lines
        effectively joining all lines together.
    """

    # Load original file:
    uenv_src_path = get_current_uenv_txt_path()
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
