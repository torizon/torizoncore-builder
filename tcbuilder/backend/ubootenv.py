"""
Backend handling for ubootenv subcommand
"""
import json
import os
import logging
import re
import shutil

from tcbuilder.backend.common import \
    (set_output_ownership, get_tezi_image_version)
from tcbuilder.backend.platform import \
    (validate_fuse_file, FUSE_HARDWAREIDS, restore_hex)
from tcbuilder.errors import \
    (FileContentMissing, TorizonCoreBuilderError, InvalidStateError,
     PathNotExistError)

log = logging.getLogger("torizon." + __name__)

FUSE_VARIABLES = [
    "fuse_prog_list=", "fuse_status=", "fuse_prog_close="
]

# pylint: disable-next=too-many-locals
def env_fuses(input_dir, output_dir, fuse_file, force=False):
    """Write fuse related u-boot variables to initial env file

    :param input_dir: Path to input Tezi image
    :param output_dir: Path to output Tezi image
    :param fuse_file: Path to fuse yaml file
    :param force: Whether to overwrite existing output
    """

    major, minor, _ = get_tezi_image_version(input_dir)
    if major is None or minor is None:
        log.warning("Warning: Unable to determine image version in input directory. "
                    "Proceeding anyways.")
    elif (major == 7 and minor < 2) or major < 7:
        log.warning("Warning: Provisioning secure fuse data is not supported on Torizon "
                    "OS before 7.2.0. Proceeding anyways, but this will most likely not "
                    "do anything.")

    initial_env_filename = get_env_filename(input_dir)
    initial_env = os.path.join(input_dir, initial_env_filename)

    with open(initial_env, "r", encoding="utf-8") as file:
        env = file.read()

    # Check to see if initial u-boot env already contains fuse variables
    if any(fuse_var in env for fuse_var in FUSE_VARIABLES):
        raise InvalidStateError(
            "Input image already contains fuse related u-boot variables")

    board = find_board(env)
    hwid = board + "-fuses"
    if hwid not in FUSE_HARDWAREIDS:
        raise InvalidStateError(
            f"Hardware type \"{board}\" is not supported by this command.")

    # Validate and check fuse file before proceeding
    fuse_file_data = validate_fuse_file(fuse_file, [hwid])

    var_list = get_fuse_vars(fuse_file_data)

    inplace = False
    if os.path.normpath(output_dir) == os.path.normpath(input_dir):
        log.debug("Updating Torizon OS image in place.")
        output_dir = input_dir
        output_env = initial_env
        inplace = True
    else:
        if os.path.exists(output_dir) and force:
            shutil.rmtree(output_dir)

        log.debug("Creating copy of Torizon OS input image.")
        shutil.copytree(input_dir, output_dir)
        output_env = os.path.join(output_dir, initial_env_filename)

    try:
        write_uboot_vars(output_env, var_list)
        set_output_ownership(output_dir)
        log.info("Fuse U-Boot variables successfully added to image.")
    except:
        if not inplace:
            log.debug("Removing output directory due to error.")
            shutil.rmtree(output_dir)
        # pylint: disable-next=raise-missing-from
        raise TorizonCoreBuilderError(
            f"Failed to update {output_env} file.")


def get_env_filename(tezi_dir):
    """Get the u-boot-initial-env* filename from a tezi directory

    :param tezi_dir: Path to tezi directory
    :returns: returns the filename of the u-boot-initial-env* file
    """

    image_json_path = os.path.join(tezi_dir, "image.json")
    if not os.path.exists(image_json_path):
        raise PathNotExistError(f"File {image_json_path} does not exist.")

    with open(image_json_path, "r", encoding="utf-8") as file:
        jsondata = json.load(file)

    env_file = jsondata.get("u_boot_env")
    if not env_file:
        raise FileContentMissing(
            f"Could not find u_boot_env field in {image_json_path}")

    if not os.path.exists(os.path.join(tezi_dir, env_file)):
        raise PathNotExistError(
            f"File {env_file} not found in {tezi_dir}")

    return env_file


def find_board(env):
    """Determine the hardware type via the u-boot-initial-env* file

    :param env: File contents of u-boot-initial-env*
    :returns: value of board u-boot variable
    """

    board_var = re.findall(r'^board=.*', env, re.MULTILINE)
    if not board_var:
        raise FileContentMissing(
            '"board=" variable not found in u-boot-initial-env* file')

    board = board_var[0].replace("board=", "").replace("_", "-")
    if board in ("colibri-imx6ull", "colibri-imx7"):
        board = board + "-emmc"

    return board


def get_fuse_vars(fuse_data):
    """Determine what u-boot variables to write based on fuse_file

    :param fuse_file: Fuse yaml file data
    :returns: List of u-boot variables and values
    """

    restore_hex(fuse_data)

    val_list = ""
    for key in sorted(fuse_data['fuses'].keys()):
        if "fuse-val" in key:
            num = fuse_data["fuses"].get(key)
            if not val_list:
                val_list = num
            else:
                val_list = val_list + " " + num

    fuse_close = fuse_data["fuses"].get("fuse-close")
    if fuse_close:
        close = "1"
    else:
        close = "0"

    var_list = [
        "fuse_prog_list=" + val_list, "fuse_prog_close=" + close, "fuse_status=pending"
    ]
    return var_list


def write_uboot_vars(env_file, var_list):
    """Write environment variables to U-Boot initial env file

    :params env_file: Path to u-boot-initial-env* file that will be modified
    :params var_list: List of U-boot variables and values to write to file
    """

    with open(env_file, "a", encoding="utf-8") as file:
        file.writelines(var + '\n' for var in var_list)
