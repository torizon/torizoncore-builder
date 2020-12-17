import logging
import json
import os
import subprocess
import sys

log = logging.getLogger("torizon." + __name__)


def get_dt_changes_dir(storage_dir):
    '''Returns the directory that contains external device tree related changes.'''
    return os.path.join(storage_dir, "dt")


def get_current_uenv_txt_path(storage_dir):
    '''Get the path to the currently applied uEnv.txt, the bootloader environment file.'''
    path = os.path.join(get_dt_changes_dir(storage_dir), "usr", "lib", "ostree-boot", "uEnv.txt")
    if os.path.exists(path):
        # Found a recently applied (but not yet deployed) uEnv.txt.
        return path
    # Fallback to uEnv.txt from the base image.
    path = os.path.join(storage_dir, "sysroot", "boot", "loader", "uEnv.txt")
    assert os.path.exists(path), "panic: missing uEnv.txt in base image!"
    return path


def get_uboot_initial_env_path(storage_dir):
    '''Get the path to u-boot-initial-env-sd, the initial bootloader environment provided by Tezi.'''
    image_json_path = os.path.join(storage_dir, "tezi", "image.json")
    assert os.path.exists(image_json_path), "panic: missing image.json in Tezi directory!"
    with open(image_json_path, "r") as f:
        image_json = json.load(f)
    try:
        initial_env_basename = image_json["u_boot_env"]
    except KeyError:
        initial_env_basename = None
    assert initial_env_basename, "panic: missing 'u_boot-env' key in image.json in Tezi directory!"
    initial_env_path = os.path.join(storage_dir, "tezi", initial_env_basename)
    assert os.path.exists(initial_env_path), f"panic: missing {initial_env_basename} in Tezi directory!"
    return initial_env_path


def query_variable_in_config_file(name, path):
    '''Query the value of variable 'name' in configuration file 'path'.
       Returns an empty string if the variable does not exist in the file.'''
    p = subprocess.run(["sed", "-e", f"/^{name}=/!d", "-e", "s/^[^=]*=//", "-e", "q", path], check=False, capture_output=True, text=True)
    if p.returncode != 0:
        # This Should Never Happen (TM)
        log.error(p.stderr)
        log.error(f"error: cannot search file '{os.path.basename(path)}'! -- missing 'unpack'?")
        sys.exit(1)
    return p.stdout.strip()


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

    answer = subprocess.check_output(f"set -o pipefail && find {storage_dir}/sysroot/ostree/deploy -type d -name dtb -print -quit | sed -r -e 's|.*/(usr/lib/modules/)|\\1|'", shell=True, text=True).strip()
    assert answer, "panic: missing kernel device tree directory!"
    return answer


def get_current_dtb_path(storage_dir):
    '''Query the path to the currently applied device tree blob.
    Returns a tuple (path, ensured) where:
        - 'path' is the path to a device tree blob in the filesystem (ensured to exist).
        - 'ensured' is True if 'path' was detected as the current device tree in the boot loader configuration.
          False means that the current device tree cannot be retrieved from configs (e.g. decided at runtime),
          and an arbitrary device tree blob of the base image was chosen instead.
    '''
    dtb_basename = get_current_dtb_basename(storage_dir)
    if dtb_basename:
        # Found a real definition of the device tree in boot loader configuration.
        # Find the path to this device tree, or die trying.
        answer = os.path.join(get_dt_changes_dir(storage_dir), get_dtb_kernel_subdir(storage_dir), dtb_basename)
        if os.path.exists(answer):
            # This is a recently applied device tree.
            return (answer, True)
        # This is a device tree from the base image.
        answer = subprocess.check_output(f"find {storage_dir}/sysroot/ostree/deploy -type f -name {dtb_basename} -print -quit", shell=True, text=True).strip()
        assert os.path.exists(answer), f"panic: missing device tree blob file for {dtb_basename}!"
        return (answer, True)

    # Cannot identify the device tree by peeking the boot loader configuration.
    # Hint by returning the first device tree blob found in the base image.
    answer = subprocess.check_output(f"find {storage_dir}/sysroot/ostree/deploy -type f -name '*.dtb' -print -quit", shell=True, text=True).strip()
    assert os.path.exists(answer), "panic: missing device tree blobs in base image!"
    return (answer, False)


def build_dts(source_dts_path, include_dirs, target_dtb_path):
    '''Compile the device tree source file 'source_dts_path' to 'target_dtb_path'.
       Returns True on successful compilation, False otherwise.
   '''
    opt_includes = []
    for include_dir in include_dirs:
        opt_includes.append("-I")
        opt_includes.append(include_dir)
    opt_includes = " ".join(opt_includes)
    try:
        subprocess.check_output(f"set -o pipefail && cpp -nostdinc -undef -x assembler-with-cpp {opt_includes} {source_dts_path} | dtc -I dts -O dtb -@ -o {target_dtb_path}", shell=True, text=True, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        log.error(e.output.strip())
        return False
    dtb_check = subprocess.check_output(f"file {target_dtb_path}", shell=True, text=True).strip()
    log.info(dtb_check)
    if not "Device Tree Blob" in dtb_check:
        log.error(f"error: compilation of '{source_dts_path}' did not produce a Device Tree Blob.")
        return False
    log.info(f"'{os.path.basename(source_dts_path)}' compiles successfully.")
    return True
