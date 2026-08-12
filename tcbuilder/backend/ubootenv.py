"""
Backend handling for ubootenv subcommand
"""
import json
import os
import logging
import re
import shutil
import tempfile

from tcbuilder.backend.common import \
    (set_output_ownership, get_tezi_image_version, FUSE_CMD_TXT_NAME)
from tcbuilder.backend.platform import \
    (validate_fuse_file, FUSE_HARDWAREIDS, restore_hex,
     SECBOOT_TECH_PER_MACHINE, fuse_count_for_tech)
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

    hwid, _ = _detect_fuse_hwid(input_dir)

    # Validate and check fuse file before proceeding
    fuse_file_data = validate_fuse_file(fuse_file, [hwid])

    var_list = get_fuse_vars(fuse_file_data)

    inplace = False
    initial_env_filename = get_env_filename(input_dir)
    if os.path.normpath(output_dir) == os.path.normpath(input_dir):
        log.debug("Updating Torizon OS image in place.")
        output_dir = input_dir
        output_env = os.path.join(input_dir, initial_env_filename)
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
        log.info("WARNING: Any device flashed with this image will perform "
                 "automatic fusing for secure-boot. This is an irreversible "
                 "operation. Take care to check before flashing this image.")
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
    # Subtract one to account for 'fuse-close'
    fuse_num = len(fuse_data['fuses']) - 1
    # Parse fuse values in order
    for index in range(fuse_num):
        # Add 1 cause range starts at 0
        num = fuse_data["fuses"].get(f"fuse-val{index + 1}")
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


def _detect_fuse_hwid(image_dir):
    """Determine the hardware-id based on the input image

    :param image_dir: Path to directory containing input image
    :returns: A tuple containing the detected hardware-id and board
    """

    initial_env_filename = get_env_filename(image_dir)
    initial_env = os.path.join(image_dir, initial_env_filename)

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

    return hwid, board


# pylint: disable-next=too-many-locals
def generate_fuse_file(close, image_dir):
    """Generate valid fuse.yaml file based on re-signing information

    :params close: Boolean on whether closing should be set in the yaml
    :params image_dir: Path to image directory containing the signed image
    :returns: Path to generated yaml file
    """

    fuse_instructions = os.path.join(image_dir, FUSE_CMD_TXT_NAME)
    if not os.path.isfile(fuse_instructions):
        raise PathNotExistError("Unable to find fusing instructions file: "
                                f"{FUSE_CMD_TXT_NAME}. Is the image signed?")

    # Figure out what machine this is for
    hwid, board = _detect_fuse_hwid(image_dir)

    _tech = SECBOOT_TECH_PER_MACHINE.get(board)
    fuse_num = fuse_count_for_tech(_tech)

    # Parse fusing values from fusing instruction file created by re-signing
    hex_regex = re.compile(r"\b(?:0[xX])[0-9a-fA-F]+\b")

    fuse_values = []
    with open(fuse_instructions, 'r', encoding="utf-8") as file:
        for line in file:
            fuse_value = hex_regex.findall(line)
            if fuse_value:
                fuse_values.append(fuse_value[0])

            if len(fuse_values) == fuse_num:
                break

    # Create temporary fuse yaml file to be used later
    with tempfile.NamedTemporaryFile(mode='w+', delete=False) as tmp_fuse_file:
        tmp_fuse_file.write("fuses:\n")
        _index = 1
        for value in fuse_values:
            tmp_fuse_file.write(f"  fuse-val{_index}: {value}\n")
            _index += 1

        tmp_fuse_file.write(f"  fuse-close: {close}\n")

    tmp_fuse_path = tmp_fuse_file.name

    # Quick sanity check on generated file
    validate_fuse_file(tmp_fuse_path, [hwid])

    return tmp_fuse_path
