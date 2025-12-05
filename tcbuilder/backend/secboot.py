"""
Backend handling for secboot subcommand
"""

import logging
import os
import re
import shutil
import shlex
import subprocess

from tcbuilder.backend import kernel
from tcbuilder.backend.common import \
    (set_output_ownership, get_tar_compress_program_options, is_tcb_container_64bit,
     check_if_file_exists, get_tezi_image_version, is_file_type_fit)
from tcbuilder.backend.ubootenv import (get_env_filename, find_board)
from tcbuilder.backend.platform import (FUSE_HARDWAREIDS)

from tcbuilder.errors import \
    (TorizonCoreBuilderError, InvalidArgumentError,
     FileContentMissing, InvalidStateError, InvalidDataError)

log = logging.getLogger("torizon." + __name__)

DEFAULT_TCB_SIGNING_FILES_TARNAME = "tcb_signing_files.tar.gz"

UBOOT_TOOLS_DIR = "/u-boot/tools"
SECURE_BOOT_WORKDIR = "/storage/secure_boot_workdir"
UBOOT_DTB = "u-boot.dtb"
KERNEL_FIT_FILENAME = kernel.OSTREE_KERNEL_FILENAME

UBOOT_CONFIG_FILE = "uboot_config"
UBOOT_DTBS_DIR = "u-boot-dtbs"

BINMAN_OUTPUT_DIR = f"{SECURE_BOOT_WORKDIR}/binman_output"
FLASH_BIN_SIGNING_DIR = "/storage/flash_bin_signing"
SIGNED_BOOTLOADER_ARTIFACTS_DIR = "/storage/signed_bootloader_artifacts"

MKIMAGE_DTC_OPT = "-I dts -O dtb -p 2000"

FLASH_BIN = "flash.bin"
ATF_BIN = "bl31*.bin"

UBOOT_SPL_DDR_BINARY = "u-boot-spl-ddr.bin"
UBOOT_DTB_BINARY = "u-boot.dtb.out"
BOOTLOADER_CONTAINER_NAME = {"verdin-imx8mp": "imx-boot"}

KERNEL_SIGNING_SUPPORTED_MACHINES = {"verdin-imx8mp": "imx8m"}
HAB_SIGNING_SUPPORTED_MACHINES = {"verdin-imx8mp": "imx8m"}

SECURE_BOOT_FILES_DIR = "/builder/tcbuilder/secure_boot_files"
COPY_SIG_NODE_SCRIPT = "copy_signature_node_to_fdts.sh"
UPDATE_FIT_CONFIGS_KEYNAME_SCRIPT = "update_fit_configs_keyname.sh"

FUSE_CMD_TXT_NAME = "fuse-cmds.txt"

def update_fit_configs_keyname(fit_path, key_name):
    """Update the 'key-name-hint' property of all config nodes in /configurations with a new value

    :param fit_path: Path to signed fitImage
    :param key_name: New value of key-name-hint
    """

    fit_dir, fit_filename = os.path.split(fit_path)

    update_keyname_script = os.path.join(SECURE_BOOT_FILES_DIR, UPDATE_FIT_CONFIGS_KEYNAME_SCRIPT)
    script_extra_env = {"PREFIX": fit_dir}

    log.info(f"Updating fitImage configurations to be signed with key name: {key_name}")
    try:
        subprocess.check_output(["bash", update_keyname_script, fit_filename, key_name],
                                text=True, env=(os.environ | script_extra_env),
                                stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError:
        raise TorizonCoreBuilderError(f"Error when running {update_keyname_script}")


def copy_sig_node_to_config_of_list(input_binaries_dir, board):
    """Copy signature node in u-boot.dtb to DTBs listed in CONFIG_OF_LIST

    :param input_binaries_dir: Path to directory that has the U-Boot DTB, U-Boot config file, and
                               the CONFIG_OF_LIST DTBs
    :param board: Name of the board compatible with the OS image
    """

    machine_prefix = KERNEL_SIGNING_SUPPORTED_MACHINES[board]
    copy_sig_script = f"{machine_prefix}_{COPY_SIG_NODE_SCRIPT}"
    copy_sig_script = os.path.join(SECURE_BOOT_FILES_DIR, copy_sig_script)

    copy_sig_extra_env = {
        "PREFIX": input_binaries_dir,
        "UBOOT_CONFIG_FILE": UBOOT_CONFIG_FILE
    }

    print()
    log.info(f"Copying signature node in {UBOOT_DTB} to DTBs listed in CONFIG_OF_LIST")

    try:
        subprocess.check_output(["bash", copy_sig_script, UBOOT_DTB],
                                text=True, env=(os.environ | copy_sig_extra_env),
                                stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError:
        raise TorizonCoreBuilderError(f"Error when running {copy_sig_script}")


def remove_dtb_node(dtb_file, node_path):
    """Remove a node in the provided DTB file, if it exists.

    :param dtb_file: Path to DTB file
    :param node_path: Absolute path of the node to be removed
    :returns: If the node exists, return node_path.
              Otherwise, return string 'FDT_ERR_NOTFOUND'
    """

    # Check if node path exists in DTB
    output = subprocess.run(["fdtget", dtb_file, node_path, "-p"],
                            text=True, check=False, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT)

    if output.returncode == 0:
        # Node exists, remove it
        output = subprocess.run(["fdtput", "-r", dtb_file, node_path],
                                text=True, check=False, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT)
        if output.returncode == 0:
            # Node removed successfully
            return node_path
        # Error when removing node
        log.error(output.stdout)
        raise InvalidStateError(f"Error when removing {node_path} in {dtb_file}. Aborting.")

    if "FDT_ERR_NOTFOUND" in output.stdout:
        # Node does not exist in DTB
        return "FDT_ERR_NOTFOUND"

    # Other error occurred when trying to read node in DTB file
    log.error(output.stdout)
    raise InvalidDataError(f"Error when trying to read {node_path} in {dtb_file}. Aborting.")


def update_dtb_public_key(dtbs_dir, dt_of_list, kernel_key_dir,
                          kernel_key_name, kernel_key_algo, board):
    """
    Update U-Boot DTB with a new public key (in certificate format). Also remove any previous
    signature nodes in them.

    If applicable for the board, also update the DTBs listed in CONFIG_OF_LIST.

    :param dtbs_dir: Path to directory with the the U-Boot DTB, U-Boot config file, and
                     CONFIG_OF_LIST DTBs
    :param dt_of_list: List of DTBs in CONFIG_OF_LIST
    :param kernel_key_dir: Path to directory with the key/certificate used to sign the kernel
    :param kernel_key_name: Name of the provided kernel key
    :param kernel_key_algo: Pair of hashing and crypto algorithms used to sign the kernel
    :param board: Name of the board compatible with the OS image
    """

    uboot_dtb_path = check_if_file_exists(UBOOT_DTB, dtbs_dir)

    # If a signature node is already present in U-Boot DTB, delete it
    # before adding the public key
    sig_removal_status = remove_dtb_node(uboot_dtb_path, "/signature")

    if sig_removal_status == "FDT_ERR_NOTFOUND":
        log.info("No previous signature node found in U-Boot DTB.")
    else:
        log.info("Removed previous signature node in U-Boot DTB.")

    # Same for all CONFIG_OF_LIST DTBs (assumed to be in UBOOT_DTBS_DIR)
    for dtb in dt_of_list:
        dtb += ".dtb"
        sig_removal_status = remove_dtb_node(
            check_if_file_exists(dtb, os.path.join(dtbs_dir, UBOOT_DTBS_DIR)), "/signature")
        if sig_removal_status == "FDT_ERR_NOTFOUND":
            log.info(f"No previous signature node found in {dtb}.")
        else:
            log.info(f"Removed previous signature node in {dtb}.")

    try:
        # Check if mkimage is present in the environment
        mkimage_cmd = subprocess.check_output(
            [f"{UBOOT_TOOLS_DIR}/mkimage", "--version"],
            text=True, stderr=subprocess.STDOUT)
        log.info(f"Adding public key '{kernel_key_name}' in {kernel_key_dir} to U-Boot DTB "
                 f"using {mkimage_cmd}")

        # Add public key to U-Boot DTB
        mkimage_cmd = [f"{UBOOT_TOOLS_DIR}/mkimage", "-D", MKIMAGE_DTC_OPT, "-f", "auto-conf",
                       "-d", "/dev/null", "-g", kernel_key_name, "-k", kernel_key_dir,
                       "-K", uboot_dtb_path, "-o", kernel_key_algo, "-r", "unused.itb"]

        log.info(shlex.join(mkimage_cmd))
        print()
        mkimage_output = subprocess.check_output(mkimage_cmd, text=True, stderr=subprocess.STDOUT)

        # Remove useless FIT generated by mkimage
        if os.path.isfile("unused.itb"):
            os.remove("unused.itb")

    except subprocess.CalledProcessError as exc:
        raise TorizonCoreBuilderError(exc.output.strip())

    log.debug("---------- OUTPUT FROM MKIMAGE ----------")
    log.debug(mkimage_output)
    log.debug("--------- END OF MKIMAGE OUTPUT ---------")

    pub_match = re.search(r"Public key written to '(.*)'", mkimage_output, re.IGNORECASE)

    if pub_match:
        log.info(f"Public key written to '{pub_match.group(1)}'")

        if KERNEL_SIGNING_SUPPORTED_MACHINES[board] == "imx8m":
            copy_sig_node_to_config_of_list(dtbs_dir, board)

    else:
        raise InvalidStateError("Could not confirm if mkimage correctly wrote the public key. "
                                "of the kernel fitImage. Aborting.")


def sign_with_mkimage(kernel_fitimage_path, kernel_key_dir, kernel_key_algo):
    """Sign the kernel fitImage with mkimage.

    :param kernel_fitimage_path: Path to the fitImage
    :param kernel_key_dir: Path to directory with the key to sign the kernel
    :param kernel_key_algo: Pair of hashing and crypto algorithms used to sign the kernel
    """

    try:
        # Check if mkimage is present in the environment
        mkimage_version = subprocess.check_output(
            [f"{UBOOT_TOOLS_DIR}/mkimage", "--version"],
            text=True, stderr=subprocess.STDOUT)
        log.info(f"Using {kernel_key_algo} for the signing process.")
        log.info(f"Signing kernel fitImage with {mkimage_version}")

        mkimage_env = {"SOURCE_DATE_EPOCH": "0"}
        mkimage_cmd = [f"{UBOOT_TOOLS_DIR}/mkimage", "-D", MKIMAGE_DTC_OPT, "-F",
                       "-o", kernel_key_algo, "-k", kernel_key_dir, "-r", kernel_fitimage_path]

        mkimage_print = (" ".join([f"{key}={val}" for key, val in mkimage_env.items()]) + " " +
                         shlex.join(mkimage_cmd))
        log.info(mkimage_print)
        print()
        mkimage_output = subprocess.check_output(mkimage_cmd, text=True, env=mkimage_env,
                                                 stderr=subprocess.STDOUT)

    except subprocess.CalledProcessError as exc:
        raise TorizonCoreBuilderError(exc.output.strip())

    log.debug("---------- OUTPUT FROM MKIMAGE ----------")
    log.debug(mkimage_output)
    log.debug("--------- END OF MKIMAGE OUTPUT ---------")

    sig_match = re.search(r"Signature written to '(.*)'", mkimage_output, re.IGNORECASE)

    if sig_match:
        log.info(f"Signature written to '{sig_match.group(1)}'")
        print()
        log.info(f"Kernel fitImage signed successfully with key in {kernel_key_dir}.")
        print()
    else:
        raise InvalidStateError("Could not confirm if mkimage correctly signed "
                                "the kernel fitImage. Aborting.")


def assemble_flash_bin_with_binman(input_binaries_dir, dt_of_list, binman_output_dir):
    """Assemble flash.bin (bootloader container) using binman

    :param input_binaries_dir: Path to directory with all binman input binaries
    :param dt_of_list: List of DTBs in CONFIG_OF_LIST
    :param binman_output_dir: Path to directory where binman will output its results
    """

    try:
        uboot_dtb_path = check_if_file_exists(UBOOT_DTB, input_binaries_dir)
        atf_bin_path = check_if_file_exists(ATF_BIN, input_binaries_dir)
        log.info("Assembling bootloader container with binman")

        binman_extra_env = {"SOURCE_DATE_EPOCH": "0"}
        # Running binman with the same args found when running via U-Boot Makefile
        # (based on the U-Boot Yocto Scarthgap recipe execution for the verdin-imx8mp machine)
        binman_cmd = [f"{UBOOT_TOOLS_DIR}/binman/binman", "--toolpath", UBOOT_TOOLS_DIR, "build",
                      "-u", "-d", uboot_dtb_path, "-O", binman_output_dir, "-m", "--allow-missing",
                      "-I", input_binaries_dir,
                      "-I", os.path.join(input_binaries_dir, UBOOT_DTBS_DIR),
                      "-a", f"of-list={' '.join(dt_of_list)}",
                      "-a", f"atf-bl31-path={atf_bin_path}",
                      "-a", "tee-os-path=", "-a", "ti-dm-path=", "-a", "opensbi-path=",
                      "-a", f"default-dt={dt_of_list[0]}", "-a", "scp-path=",
                      "-a", "rockchip-tpl-path=", "-a", "spl-bss-pad=", "-a", "tpl-bss-pad=1",
                      "-a", "spl-dtb=y", "-a", "tpl-dtb=", "-a", "pre-load-key-path="]

        binman_print = (" ".join([f"{key}={val}" for key, val in binman_extra_env.items()]) + " " +
                        shlex.join(binman_cmd))
        print()
        log.info(binman_print)
        print()
        binman_output = subprocess.check_output(binman_cmd, text=True,
                                                env=(os.environ | binman_extra_env),
                                                stderr=subprocess.STDOUT)

        # Check if binman generated the tools directory, then change ownership if it exists
        tools_dir = os.path.join(os.getcwd(), "tools")
        if os.path.isdir(tools_dir):
            set_output_ownership(tools_dir)

        if binman_output.rstrip() != '':
            log.debug(binman_cmd)

    except subprocess.CalledProcessError as exc:
        raise TorizonCoreBuilderError(exc.output.strip())

    if os.path.isfile(os.path.join(binman_output_dir, FLASH_BIN)):
        log.info(f"{FLASH_BIN} created successfully.")
        print()
    else:
        raise InvalidStateError(f"Binman did not generate {FLASH_BIN}.\n"
                                "Run again with debug logs enabled.")


# Based on function with the same name in imx-hab.bbclass in meta-toradex-security:
# https://github.com/toradex/meta-toradex-security/blob/83493978ad6e5b4ffde529e929afec7f31a83364/classes/imx-hab.bbclass
def make_srk_cert_name(crypto, key_size, key_exp, dig_algo, srk_index, srk_no_ca):
    """Generate certificate name related to a Super Root Key

    :param crypto: Type of cryptographic key being used
    :param key_size: Key length for RSA; String from the generated certificate name for ECDSA
    :param key_exp: Key exponent for RSA
    :param dig_algo: Digest algorithm used in CST
    :param srk_index: Index of SRK to be used for signing
    :param src_no_ca: Whether 'fast authentication' was enabled in CST when generating the PKI tree
    """

    res = ""
    srk_index = int(srk_index)
    castr = "ca" if srk_no_ca is False else "usr"

    if srk_index < 1 or srk_index > 4:
        raise InvalidArgumentError("The SRK index must be in the range [1,4]. Aborting")
    if crypto == "rsa":
        res = f"SRK{srk_index}_{dig_algo}_{key_size}_{key_exp}_v3_{castr}_crt.pem"
    elif crypto == "ecdsa":
        if key_size.isdigit():
            log.warning("--cst-key-size is likely not set up correctly; "
                        "check --help to understand how to set this argument for ECDSA.")
        res = f"SRK{srk_index}_{dig_algo}_{key_size}_v3_{castr}_crt.pem"
    else:
        raise InvalidArgumentError('--cst-crypto is not properly set. Aborting.')

    return res


# Based on function with the same name in imx-hab.bbclass in meta-toradex-security:
# https://github.com/toradex/meta-toradex-security/blob/83493978ad6e5b4ffde529e929afec7f31a83364/classes/imx-hab.bbclass
def make_sub_cert_name(prefix, crypto, key_size, key_exp, dig_algo, srk_index, srk_no_ca):
    """Generate certificate name related to a subordinate key

    :param prefix: Name of the SRK subordinate key ('CSF' or 'IMG')
    :param crypto: Type of cryptographic key being used
    :param key_size: Key length for RSA; String from the generated certificate name for ECDSA
    :param key_exp: Key exponent for RSA
    :param dig_algo: Digest algorithm used in CST
    :param srk_index: Index of SRK to be used for signing
    :param src_no_ca: Whether 'fast authentication' was enabled in CST when generating the PKI tree
    """

    res = ""
    srk_index = int(srk_index)
    if srk_index < 1 or srk_index > 4:
        raise InvalidArgumentError("The SRK index must be in the range [1,4]. Aborting")
    if srk_no_ca:
        pass
    elif crypto == "rsa":
        res = f"{prefix}{srk_index}_1_{dig_algo}_{key_size}_{key_exp}_v3_usr_crt.pem"
    elif crypto == "ecdsa":
        if key_size.isdigit():
            log.warning("--cst-key-size is likely not set up correctly; "
                        "check --help to understand how to set this argument for ECDSA.")
        res = f"{prefix}{srk_index}_1_{dig_algo}_{key_size}_v3_usr_crt.pem"
    else:
        raise InvalidArgumentError('--cst-crypto is not properly set. Aborting.')

    return res


def get_cst_bin(cst_dir):
    """
    Get path of the CST binary to be used. The binary inside the CST directory will be tested first.
    If it can be executed without issues, the function will return its path. If the binary cannot be
    found in the CST directory, or if there are any errors when checking for its version, return the
    path of the CST binary installed in the TCB container as a fallback option.

    :param cst_dir: Path to CST directory tree
    :returns: String with the path to the chosen CST binary
    """

    if is_tcb_container_64bit():
        bin_rel_path = "linux64/bin/cst"
    else:
        bin_rel_path = "linux32/bin/cst"

    cst_path = os.path.join(cst_dir, bin_rel_path)
    cst_rel_path = cst_path.replace("/workdir", ".")

    if not os.path.isfile(cst_path):
        log.warning(f"CST binary not found in {cst_rel_path}. Using the built-in CST binary.")
        cst_version = subprocess.run(
            ["/usr/bin/cst", "--version"],
            text=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        log.info(cst_version.stdout)
        return "/usr/bin/cst"

    # Check if TCB can run the CST binary in the provided CST directory
    cst_version = subprocess.run(
        [cst_path, "--version"],
        text=True, check=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    if cst_version.returncode != 0:
        log.warning(cst_version.stdout)
        log.warning(f"Error when testing {cst_rel_path}. Using the built-in CST binary.")
        cst_version = subprocess.run(
            ["/usr/bin/cst", "--version"],
            text=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        log.info(cst_version.stdout)
        return "/usr/bin/cst"

    log.info(f"Running CST found in {cst_rel_path}.")
    log.info(cst_version.stdout)
    return cst_path


def run_hab_signing_script(signing_dir, uboot_config_path, binman_output_dir,
                           board, cst_dir, cst_args):
    """Run the signing script for HAB-compatible modules

    :param signing_dir: Path where the signing script will be executed
    :param uboot_config_path: Path to U-Boot config file (.config)
    :param binman_output_dir: Path to directory with the binman output files
    :param board: Name of the board compatible with the OS image
    :param cst_dir: Path to CST directory tree
    :param cst_args: Dictionary with CST parameters
    """

    if os.path.isdir(signing_dir):
        shutil.rmtree(signing_dir)

    # Create signing directory with the necessary secure boot files/scripts
    shutil.copytree(SECURE_BOOT_FILES_DIR, signing_dir)
    shutil.copy(uboot_config_path, signing_dir)
    # Copy required binman output files to the signing directory
    shutil.copy(check_if_file_exists(FLASH_BIN, binman_output_dir), signing_dir)
    shutil.copy(check_if_file_exists(UBOOT_SPL_DDR_BINARY, binman_output_dir), signing_dir)
    shutil.copy(check_if_file_exists(UBOOT_DTB_BINARY, binman_output_dir), signing_dir)

    # Change to the signing directory as the script generates some files
    # in the current working directory
    os.chdir(signing_dir)
    try:
        sign_extra_env = {
            "LIBFAKETIME_PATH": "/usr/lib/x86_64-linux-gnu/faketime/libfaketime.so.1",
            "UBOOT_CONFIG_FILE": UBOOT_CONFIG_FILE,
            "TDX_IMX_HAB_CST_BIN": get_cst_bin(cst_dir),
            "TDX_IMX_HAB_CST_SRK": cst_args["srk_table"],
            "TDX_IMX_HAB_CST_SRK_CERT": cst_args["srk_crt"],
            "TDX_IMX_HAB_CST_CSF_CERT": cst_args["csf_crt"],
            "TDX_IMX_HAB_CST_IMG_CERT": cst_args["img_crt"]
        }
        sign_cmd = ["bash", f"{HAB_SIGNING_SUPPORTED_MACHINES[board]}_sign.sh"]

        log.info("Signing bootloader container with CST")

        sign_print = (" ".join([f"{key}={val}" for key, val in sign_extra_env.items()]) + " " +
                      shlex.join(sign_cmd))
        print()
        log.info(sign_print)
        print()
        sign_output = subprocess.check_output(sign_cmd, text=True,
                                              env=(os.environ | sign_extra_env),
                                              stderr=subprocess.STDOUT)
        log.info(sign_output)

    except subprocess.CalledProcessError as exc:
        raise TorizonCoreBuilderError(exc.output.strip())

    log.info("Bootloader container signed successfully.")

    subprocess.check_output(["bash", "create_fuse_cmds.sh",
                             HAB_SIGNING_SUPPORTED_MACHINES[board].upper(),
                             cst_args["srk_fuse"],
                             FUSE_CMD_TXT_NAME],
                            text=True, stderr=subprocess.STDOUT)
    # Change working directory back to the default one before leaving the function
    os.chdir("/workdir")


def check_basic_signing_prerequisites(storage_dir):
    """
    Check if the unpacked Torizon OS image in Toradex Easy Installer format has the minimum
    requirements necessary for the signing feature

    :param storage_dir: Path to storage directory, where the image was unpacked
    """

    img_major, _, _ = get_tezi_image_version(os.path.join(storage_dir, "tezi"))
    if img_major is None:
        raise InvalidArgumentError("Unable to determine unpacked image version. Aborting.")

    if img_major < 7:
        raise InvalidArgumentError("Feature only supported on Torizon OS 7 images. Aborting.")

    log.debug("Checking if the unpacked image has the kernel in FIT format...")

    unpacked_kernel_path = kernel.find_kernel_in_sysroot(storage_dir)
    if not is_file_type_fit(unpacked_kernel_path):
        raise InvalidArgumentError(
            "Unpacked image does not have the kernel in FIT format. Aborting.")

    log.info("Found kernel in FIT format.")


def check_unpacked_tezi_kernel_signing_support(storage_dir):
    """Check if TorizonCore Builder can sign the kernel of the unpacked TEZI image

    :param storage_dir: Path to storage directory, where the image was unpacked
    """

    tezi_dir = os.path.join(storage_dir, "tezi")

    initial_env_filename = get_env_filename(tezi_dir)
    initial_env = os.path.join(tezi_dir, initial_env_filename)

    with open(initial_env, 'r') as file:
        env = file.read()

    board = find_board(env)
    log.info(f"Detected image for {board}")

    if board not in KERNEL_SIGNING_SUPPORTED_MACHINES:
        raise InvalidStateError(
            f"TorizonCore Builder doesn't support signing the kernel of images for \"{board}\". "
            "Aborting.\n"
            f"Currently supported machines: {', '.join(KERNEL_SIGNING_SUPPORTED_MACHINES)}")

    check_basic_signing_prerequisites(storage_dir)


def check_unpacked_tezi_hab_signing_support(storage_dir):
    """
    Check if TorizonCore Builder can sign the HAB-compatible bootloader of the given
    Toradex Easy Installer image

    :param storage_dir: Path to storage directory, where the image was unpacked
    :returns: The name of the machine compatible with the image
    """
    tezi_dir = os.path.join(storage_dir, "tezi")

    initial_env_filename = get_env_filename(tezi_dir)
    initial_env = os.path.join(tezi_dir, initial_env_filename)

    with open(initial_env, 'r') as file:
        env = file.read()

    board = find_board(env)
    log.info(f"Detected image for {board}")

    hwid = board + "-fuses"

    if hwid not in FUSE_HARDWAREIDS or FUSE_HARDWAREIDS[hwid] != "hab":
        raise InvalidStateError(
            f"Hardware type \"{board}\" is not compatible with HAB. Aborting.")

    if board not in HAB_SIGNING_SUPPORTED_MACHINES:
        raise InvalidStateError(
            "TorizonCore Builder doesn't support signing the bootloader of images for "
            f"\"{board}\". Aborting.\n"
            f"Currently supported machines: {', '.join(HAB_SIGNING_SUPPORTED_MACHINES)}")

    check_basic_signing_prerequisites(storage_dir)

    return board


def check_cst_dir(abs_cst_dir, cst_args):
    """Check if the user-provided CST directory tree has the expected key/certificate files

    :param abs_cst_dir: Absolute path to CST directory tree
    :param cst_args: Dictionary with CST parameters
    """

    cst_crts_dir = os.path.join(abs_cst_dir, "crts")
    if not os.path.isdir(cst_crts_dir):
        raise FileContentMissing("Directory 'crts' not found in provided CST directory. Aborting.")

    srk_crt = make_srk_cert_name(cst_args["crypto"], cst_args["key_size"],
                                 cst_args["key_exp"], cst_args["dig_algo"],
                                 cst_args["srk_index"], cst_args["srk_no_ca"])

    csf_crt = make_sub_cert_name("CSF",
                                 cst_args["crypto"], cst_args["key_size"],
                                 cst_args["key_exp"], cst_args["dig_algo"],
                                 cst_args["srk_index"], cst_args["srk_no_ca"])

    img_crt = make_sub_cert_name("IMG",
                                 cst_args["crypto"], cst_args["key_size"],
                                 cst_args["key_exp"], cst_args["dig_algo"],
                                 cst_args["srk_index"], cst_args["srk_no_ca"])

    # Add srk, csf and img filenames to cst_args dictionary after checking if they exist
    cst_args["srk_crt"] = check_if_file_exists(srk_crt, cst_crts_dir)
    cst_args["csf_crt"] = check_if_file_exists(csf_crt, cst_crts_dir)
    cst_args["img_crt"] = check_if_file_exists(img_crt, cst_crts_dir)

    cst_args["srk_table"] = check_if_file_exists(cst_args["srk_table"], cst_crts_dir)
    cst_args["srk_fuse"] = check_if_file_exists(cst_args["srk_fuse"], cst_crts_dir)


def sign_kernel(storage_dir, kernel_changes_dir, key_dir, key_algo, key_name):
    """Sign kernel fitImage of unpacked Easy Installer image in storage_dir

    :param storage_dir: Path to storage directory, where the image was unpacked
    :param kernel_changes_dir: Path to directory with all kernel changes to be commited
    :param key_dir: Path to directory with the key to sign the kernel fitImage
    :param key_algo: Pair of hashing and crypto algorithms used to sign the kernel
    :param key_name: Name of the provided key
    """

    check_if_file_exists(f"{key_name}.key", key_dir)

    check_unpacked_tezi_kernel_signing_support(storage_dir)

    # Ensure we have a clean secure boot work directory.
    if os.path.isdir(SECURE_BOOT_WORKDIR):
        shutil.rmtree(SECURE_BOOT_WORKDIR)
    os.mkdir(SECURE_BOOT_WORKDIR)

    # Determine final destination of kernel binary.
    kernel_subdir = kernel.get_kernel_subdir(storage_dir)
    kernel_dst_dir = os.path.join(kernel_changes_dir, kernel_subdir)
    kernel_dst_path = os.path.join(kernel_dst_dir, KERNEL_FIT_FILENAME)

    # Select kernel and copy it to the work directory.
    kernel_workdir_path = os.path.join(SECURE_BOOT_WORKDIR, KERNEL_FIT_FILENAME)
    if os.path.exists(kernel_dst_path):
        kernel_src_path = kernel_dst_path
        log.debug("Taking customized kernel from '%s' for signing.", kernel_src_path)
    else:
        kernel_src_path = kernel.find_kernel_in_sysroot(storage_dir)
        log.debug("Taking original kernel from '%s' for signing.", kernel_src_path)
    shutil.copy2(kernel_src_path, kernel_workdir_path)

    # Update key names and re-sign the kernel in the work directory.
    update_fit_configs_keyname(kernel_workdir_path, key_name)
    sign_with_mkimage(kernel_workdir_path, key_dir, key_algo)

    # Store finalized kernel into the "changes" directory.
    os.makedirs(kernel_dst_dir, exist_ok=True)
    shutil.copy2(kernel_workdir_path, kernel_dst_path)

    log.info("Kernel in unpacked Torizon OS image signed successfully!")


def sign_bootloader_hab(storage_dir, kernel_key_dir,
                        kernel_key_name, kernel_key_algo, cst_dir, cst_args):
    """Sign bootloader container of a HAB-compatible image in input_dir

    :param storage_dir: Path to storage directory, where the image was unpacked
    :param kernel_key_dir: Path to directory with the key to sign the kernel fitImage
    :param kernel_key_name: Name of the provided kernel key
    :param kernel_key_algo: Pair of hashing and crypto algorithms used to sign the kernel
    :param cst_dir: Path to CST directory tree
    :param cst_args: Dictionary with CST parameters
    """

    if kernel_key_dir:
        check_if_file_exists(f"{kernel_key_name}.key", kernel_key_dir)
        check_if_file_exists(f"{kernel_key_name}.crt", kernel_key_dir)

    board = check_unpacked_tezi_hab_signing_support(storage_dir)

    # Using absolute path as the signing script will be executed relative from its own directory
    cst_dir = os.path.abspath(cst_dir)

    log.info("Attempting to sign the bootloader container with the following options:")
    log.info(f"- Key type: {cst_args['crypto']}")
    log.info(f"- Key length: {cst_args['key_size']}")
    if cst_args['crypto'] == "rsa":
        log.info(f"- Key exponent: {cst_args['key_exp']}")
    log.info(f"- Digest algorithm: {cst_args['dig_algo']}")
    log.info(f"- SRK index: {cst_args['srk_index']}")
    log.info(f"- SRK table filename: {os.path.basename(cst_args['srk_table'])}")
    log.info(f"- SRK fuse filename: {os.path.basename(cst_args['srk_fuse'])}")
    log.info(f"- SRK CA flag disabled: {'YES' if cst_args['srk_no_ca'] else 'NO'}")

    check_cst_dir(cst_dir, cst_args)

    tezi_dir = os.path.join(storage_dir, "tezi")

    signing_binaries_file = check_if_file_exists(DEFAULT_TCB_SIGNING_FILES_TARNAME, tezi_dir)

    # Check if secure boot work directory exists, and if so, remove it
    # so we have a clean work directory
    if os.path.isdir(SECURE_BOOT_WORKDIR):
        shutil.rmtree(SECURE_BOOT_WORKDIR)

    os.mkdir(SECURE_BOOT_WORKDIR)

    tar_compress_options = get_tar_compress_program_options(signing_binaries_file)
    if signing_binaries_file.endswith(".tar") or tar_compress_options:
        tarcmd = [
            "tar",
            "-xf", signing_binaries_file,
            "-C", SECURE_BOOT_WORKDIR,
        ] + tar_compress_options
        log.debug(f"Running tar command: {shlex.join(tarcmd)}")
        subprocess.check_output(tarcmd, stderr=subprocess.STDOUT)

    uboot_config_path = check_if_file_exists(UBOOT_CONFIG_FILE, SECURE_BOOT_WORKDIR)
    with open(uboot_config_path, 'r') as uboot_config_file:
        dt_of_list = re.search(r'CONFIG_OF_LIST="(.*)"', uboot_config_file.read())

    if dt_of_list is not None:
        dt_of_list = dt_of_list.group(1).split()
    else:
        raise InvalidStateError("U-Boot config file does not contain CONFIG_OF_LIST. Aborting.")

    if kernel_key_dir:
        update_dtb_public_key(SECURE_BOOT_WORKDIR, dt_of_list,
                              kernel_key_dir, kernel_key_name, kernel_key_algo, board)

    assemble_flash_bin_with_binman(SECURE_BOOT_WORKDIR, dt_of_list, BINMAN_OUTPUT_DIR)

    run_hab_signing_script(FLASH_BIN_SIGNING_DIR, uboot_config_path, BINMAN_OUTPUT_DIR, board,
                           cst_dir, cst_args)

    # Copy resulting bootloader container binary with the correct filename and fusing instructions
    # text file to SIGNED_BOOTLOADER_ARTIFACTS_DIR
    if os.path.isdir(SIGNED_BOOTLOADER_ARTIFACTS_DIR):
        shutil.rmtree(SIGNED_BOOTLOADER_ARTIFACTS_DIR)

    os.mkdir(SIGNED_BOOTLOADER_ARTIFACTS_DIR)

    shutil.copy2(os.path.join(FLASH_BIN_SIGNING_DIR, FLASH_BIN),
                 os.path.join(SIGNED_BOOTLOADER_ARTIFACTS_DIR, BOOTLOADER_CONTAINER_NAME[board]))
    shutil.copy2(os.path.join(FLASH_BIN_SIGNING_DIR, FUSE_CMD_TXT_NAME),
                 SIGNED_BOOTLOADER_ARTIFACTS_DIR)

    # Tar the updated contents of the signing binaries to SIGNED_BOOTLOADER_ARTIFACTS_DIR,
    # excluding work directories
    tarcmd = [
        "tar", "--xattrs", "--xattrs-include=*", "--owner=0", "--group=0",
        "-C", SECURE_BOOT_WORKDIR,
        "--exclude", os.path.basename(BINMAN_OUTPUT_DIR),
        "-czf", os.path.join(SIGNED_BOOTLOADER_ARTIFACTS_DIR, DEFAULT_TCB_SIGNING_FILES_TARNAME),
        "."
    ]
    subprocess.check_output(tarcmd, stderr=subprocess.STDOUT)
