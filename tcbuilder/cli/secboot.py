"""
CLI handling for secboot subcommand
"""

import logging
import os

from tcbuilder.backend import secboot
from tcbuilder.backend import kernel
from tcbuilder.backend.common import \
    (fail_on_raw_image, image_has_cfs_support, images_unpack_executed)
from tcbuilder.backend.ostree import OSTreeKey
from tcbuilder.cli.common import parse_ostree_key
from tcbuilder.errors import InvalidArgumentError, PathNotExistError

log = logging.getLogger("torizon." + __name__)

# Constants related to HAB signing:
CST_CRYPTO_TYPES = ("rsa", "ecdsa")
CST_DIG_ALGO_TYPES = ["sha256"]
CST_DEFAULT_KEY_SIZE = "2048"
CST_DEFAULT_KEY_EXP = "65537"
CST_SRK_INDEXES = ("1", "2", "3", "4")
CST_SRK_DEFAULT_TABLE = "SRK_1_2_3_4_table.bin"
CST_SRK_DEFAULT_FUSE = "SRK_1_2_3_4_fuse.bin"

# Constants related to kernel signing:
KERNEL_KEY_DEFAULT_ALGO = "sha256,rsa2048"


# pylint: disable-next=too-many-arguments
def sign_bootloader_hab(
        *,
        cst_dir, cst_crypto, cst_key_size, cst_key_exp, cst_dig_algo,
        cst_srk_index, cst_srk_table, cst_srk_fuse, cst_srk_no_ca,
        kernel_key, kernel_key_dir=None):
    """Execute the work of the "sign-bootloader-hab" command."""

    images_unpack_executed()
    fail_on_raw_image("Secboot commands are not supported for WIC/raw images. Aborting.")

    if not os.path.isdir(cst_dir):
        raise InvalidArgumentError(
            f"Directory \"{cst_dir}\" does not exist: aborting.")

    if kernel_key_dir and not kernel_key:
        raise InvalidArgumentError(
            "Error: --kernel-key-dir was passed but --kernel-key was not provided. Aborting.")

    kernel_key_name = None
    kernel_key_algo = None
    if kernel_key is not None:
        if kernel_key_dir is not None and not os.path.isdir(kernel_key_dir):
            raise InvalidArgumentError(
                f"Directory \"{kernel_key_dir}\" does not exist. Aborting.")
        kernel_key_dir = kernel_key_dir or "."
        kernel_key_name, kernel_key_algo = _parse_kernel_key_arg(kernel_key)

    cst_args = {
        "crypto": cst_crypto,
        "key_size": cst_key_size,
        "key_exp": cst_key_exp,
        "dig_algo": cst_dig_algo,
        "srk_index": cst_srk_index,
        "srk_table": cst_srk_table,
        "srk_fuse": cst_srk_fuse,
        "srk_no_ca": cst_srk_no_ca
    }

    secboot.sign_bootloader_hab(
        kernel_key_dir=kernel_key_dir,
        kernel_key_name=kernel_key_name,
        kernel_key_algo=kernel_key_algo,
        cst_dir=cst_dir,
        cst_args=cst_args
    )

    if kernel_key_dir:
        log.info(f"Public key '{kernel_key_name}' in {kernel_key_dir} will be used by "
                 "the bootloader to verify the kernel signature.\n")
    else:
        log.warning("The bootloader DTBs were NOT updated with a new public key.")
        log.warning("If the kernel FIT image will be signed with a new key, please re-run the "
                    "command with --kernel-key-dir and --kernel-key so the new kernel signature "
                    "can be properly verified by the bootloader.")
        log.warning("Otherwise, this message can be ignored.\n")

    log.info("Bootloader in Torizon OS image signed successfully!")


def do_sign_bootloader_hab(args):
    """Get the arguments of the sign-bootloader-hab command from the CLI parser."""

    sign_bootloader_hab(
        cst_dir=args.cst_dir,
        cst_crypto=args.cst_crypto,
        cst_key_size=args.cst_key_size,
        cst_key_exp=args.cst_key_exp,
        cst_dig_algo=args.cst_dig_algo,
        cst_srk_index=args.cst_srk_index,
        cst_srk_table=args.cst_srk_table,
        cst_srk_fuse=args.cst_srk_fuse,
        cst_srk_no_ca=args.cst_srk_no_ca,
        kernel_key=args.kernel_key,
        kernel_key_dir=args.kernel_key_dir)


def _parse_kernel_key_arg(kernel_key):
    """Parse and validate --kernel-key arg."""

    kernel_key_name = ""
    kernel_key_algo = ""
    for element in kernel_key.split(';'):
        argpair = element.split('=')

        if len(argpair) > 2:
            raise InvalidArgumentError(
                "--kernel-key is not correctly formatted. Did you separate "
                "each field with a semicolon (;) ?")
        if len(argpair) == 1:
            argkey = argpair[0]
            argvalue = ""
        else:
            argkey, argvalue = argpair

        argkey = argkey.strip()
        if argkey == 'name':
            kernel_key_name = argvalue.strip()
        elif argkey == 'algo':
            kernel_key_algo = argvalue.strip()
        else:
            log.warning("Unknown key '%s' in kernel-key parameter was ignored.", argkey)

    if not kernel_key_name:
        raise InvalidArgumentError("Could not find value of 'name' in --kernel-key. Aborting.")

    if not kernel_key_algo:
        log.info("Could not find value of 'algo' in --kernel-key; "
                 f"defaulting to {KERNEL_KEY_DEFAULT_ALGO}.")
        kernel_key_algo = KERNEL_KEY_DEFAULT_ALGO

    return kernel_key_name, kernel_key_algo


def _check_parse_ostree_key_args(ostree_key_dir, ostree_key, *, check_pubk=True):
    """Parse and validate arguments to --ostree-key/--ostree-key-dir.

    :param ostree_key_dir: OSTree keys directory; if None, the working directory is
        taken as default.
    :param ostree_key: Key specification string; if None, it means no signing keys
        update is being requested.
    :returns: `OSTreeKey` object or None if signing was not requested.
    """

    if ostree_key_dir and not ostree_key:
        raise InvalidArgumentError(
            "Error: ostree-key-dir was passed but ostree-key was not provided. Aborting.")

    if not image_has_cfs_support():
        if ostree_key is not None:
            raise InvalidArgumentError(
                "Error: The ostree-key parameter has been passed for an image that has no "
                "support for the root filesystem protection. Aborting.")

    if ostree_key is None:
        return None

    if ostree_key_dir is not None and not os.path.isdir(ostree_key_dir):
        raise PathNotExistError(
            f"Error: OSTree keys directory '{ostree_key_dir}' does not exist. Aborting.")

    ostree_key_dir = ostree_key_dir or "."
    ostree_key_obj = parse_ostree_key(ostree_key, ostree_key_dir=ostree_key_dir)

    if check_pubk:
        pubk_file = ostree_key_obj.get_pub_key_path()
        if not os.path.isfile(pubk_file):
            raise PathNotExistError(
                f"Error: Cannot read public key file '{pubk_file}'.")

    return ostree_key_obj


def sign_kernel(kernel_key, *, kernel_key_dir,
                ostree_key_dir=None, ostree_key=None):
    """Execute the work of the "sign-kernel" command."""

    images_unpack_executed()
    fail_on_raw_image("Secboot commands are not supported for WIC/raw images. Aborting.")

    if not os.path.isdir(kernel_key_dir):
        raise InvalidArgumentError(
            f"Directory \"{kernel_key_dir}\" does not exist. Aborting.")

    kernel_key_name, kernel_key_algo = _parse_kernel_key_arg(kernel_key)

    ostree_key_obj = _check_parse_ostree_key_args(ostree_key_dir, ostree_key)

    kernel_changes_dir = kernel.get_kernel_changes_dir()
    if not os.path.isdir(kernel_changes_dir):
        os.mkdir(kernel_changes_dir)

    secboot.sign_kernel(
        kernel_changes_dir=kernel_changes_dir,
        key_dir=kernel_key_dir,
        key_algo=kernel_key_algo,
        key_name=kernel_key_name,
        ostree_key=ostree_key_obj)


def do_sign_kernel(args):
    """Get the arguments of the sign-kernel command from the CLI parser."""

    sign_kernel(
        kernel_key=args.kernel_key,
        kernel_key_dir=args.kernel_key_dir,
        ostree_key=args.ostree_key,
        ostree_key_dir=args.ostree_key_dir)


def init_parser(subparsers):
    """Initialize argument parser."""

    parser = subparsers.add_parser(
        "secboot",
        help=("Sign different components of an unpacked Torizon OS image in "
              "Toradex Easy Installer format."),
        allow_abbrev=False)

    subparsers = parser.add_subparsers(title='Commands', required=True, dest='cmd')

    # secboot sign-bootloader-hab
    subparser = subparsers.add_parser(
        "sign-bootloader-hab",
        help="Sign bootloader components for images targeting devices based on NXP HAB.",
        description=(
            "Sign bootloader components (SPL, DDR Firmware, U-Boot FIT image) for i.MX-based "
            "modules compatible with HAB. The signing is performed using the Code Signing Tool "
            "(CST) from NXP. The CST directory is specified with the --cst-dir argument. Keys "
            "and certificates (in PEM format, with the .pem extension), SRK table and E-fuse "
            "hash binaries have to be generated beforehand by following the NXP documentation."
        ),
        epilog=("Currently supported machines: "
                f"{', '.join(secboot.HAB_SIGNING_SUPPORTED_MACHINES)}"))

    subparser.add_argument(
        "--cst-dir", dest="cst_dir",
        metavar="CST_DIR",
        help="CST directory path.",
        required=True)

    subparser.add_argument(
        "--cst-crypto", dest="cst_crypto", choices=CST_CRYPTO_TYPES,
        default=CST_CRYPTO_TYPES[0],
        help=("Type of cryptographic keys being used. "
              f"Allowed values: {', '.join(CST_CRYPTO_TYPES)}. "
              f"(default: {CST_CRYPTO_TYPES[0]})"))

    subparser.add_argument(
        "--cst-key-size", dest="cst_key_size",
        default=CST_DEFAULT_KEY_SIZE,
        help=("Key length in bits if using RSA; for ECDSA this would be a string from the "
              "generated certificate file name e.g. secp384r1 for "
              f"SRK1_sha256_secp384r1_v3_ca_crt.pem. (default: {CST_DEFAULT_KEY_SIZE})"))

    subparser.add_argument(
        "--cst-key-exp", dest="cst_key_exp",
        default=CST_DEFAULT_KEY_EXP,
        help=("Key exponent for RSA keys (only). "
              f"(default: {CST_DEFAULT_KEY_EXP})"))

    subparser.add_argument(
        "--cst-dig-algo", dest="cst_dig_algo", choices=CST_DIG_ALGO_TYPES,
        default=CST_DIG_ALGO_TYPES[0],
        help=("Digest algorithm as entered into the CST tool. "
              f"(default: {CST_DIG_ALGO_TYPES[0]})"))

    subparser.add_argument(
        "--cst-srk-index", dest="cst_srk_index",
        default=CST_SRK_INDEXES[0], choices=CST_SRK_INDEXES,
        help=("Index of the SRK table to be used for signing. "
              f"Allowed values: {', '.join(CST_SRK_INDEXES)}. "
              f"(default: {CST_SRK_INDEXES[0]})"))

    subparser.add_argument(
        "--cst-srk-table", dest="cst_srk_table",
        default=CST_SRK_DEFAULT_TABLE,
        help=("SRK table binary filename in 'crts' inside the CST directory. "
              f"(default: {CST_SRK_DEFAULT_TABLE})"))

    subparser.add_argument(
        "--cst-srk-fuse", dest="cst_srk_fuse",
        default=CST_SRK_DEFAULT_FUSE,
        help=("SRK fuse binary filename in 'crts' inside the CST directory. "
              f"(default: {CST_SRK_DEFAULT_FUSE})"))

    subparser.add_argument(
        "--cst-srk-no-ca", dest="cst_srk_no_ca",
        default=False, action="store_true",
        help="Enable this if the CA flag was *not* set when generating the SRK certificates.")

    subparser.add_argument(
        "--kernel-key", dest="kernel_key",
        help=("If specified, this switch causes the U-Boot DTB and its Control DTBs to be "
              "updated with the specified (PUBLIC) key before signing the bootloader. The "
              "string passed to the switch should have the form 'name=<NAME>;algo=<ALGO>' "
              "where <NAME> is the key name and <ALGO> is a comma-separated pair of the "
              "hashing and crypto algorithms used to sign the kernel (e.g. "
              "'name=prod;algo=sha256,rsa2048'). If <ALGO> is not provided, it defaults to "
              f"'{KERNEL_KEY_DEFAULT_ALGO}'. "))

    subparser.add_argument(
        "--kernel-key-dir", dest="kernel_key_dir",
        help=("Kernel key directory path. This directory must contain a certificate key file named "
              "<NAME>.crt holding the PUBLIC key, and a PRIVATE key file named <NAME>.key (both "
              "in PEM format), where <NAME> is specified through the --kernel-key switch. "
              "(default: working directory)"))

    subparser.set_defaults(func=do_sign_bootloader_hab)

    # secboot sign-kernel
    subparser = subparsers.add_parser(
        "sign-kernel",
        help="Sign the kernel FIT image of an unpacked Torizon OS image.",
        description="Sign the kernel FIT image of an unpacked Torizon OS image.",
        epilog=("Currently supported machines: "
                f"{', '.join(secboot.KERNEL_SIGNING_SUPPORTED_MACHINES)}"))

    subparser.add_argument(
        "--kernel-key", dest="kernel_key",
        help=("Kernel key information in the form 'name=<NAME>;algo=<ALGO>', where <NAME> is "
              "the key name and <ALGO> is a comma-separated pair of the hashing and crypto "
              "algorithms to be used for the signing process (e.g. 'name=prod;algo=sha256,"
              "rsa2048'). If <ALGO> is not provided, it defaults to "
              f"'{KERNEL_KEY_DEFAULT_ALGO}'."),
        required=True)

    subparser.add_argument(
        "--kernel-key-dir", dest="kernel_key_dir",
        default=".",
        metavar="KERNEL_KEY_DIR",
        help=("Kernel key directory path. This directory must contain a PRIVATE key file named "
              "<NAME>.key in PEM format, where <NAME> is specified through the --kernel-key "
              "switch. (default: working directory)"))

    subparser.add_argument(
        "--ostree-key",
        dest="ostree_key",
        metavar="OSTREE_KEY",
        help=("If specified, this switch causes the ramdisk embedded in the kernel FIT image "
              "to be updated with the PUBLIC key used for signing the root filesystem (OSTree "
              "commit); this is done before the FIT image is signed. The string passed to the "
              "switch should have the form 'name=<NAME>;algo=<ALGO>' where <NAME> is the key "
              "name and <ALGO> corresponds to the signing algorithm (e.g. "
              "'name=prod;algo=ed25519'); <ALGO> defaults to "
              f"'{OSTreeKey.OSTREE_KEY_DEFAULT_ALGO}' if not provided."))

    subparser.add_argument(
        "--ostree-key-dir",
        dest="ostree_key_dir",
        metavar="OSTREE_KEY_DIR",
        help=("OSTree key directory path. This directory must contain a PUBLIC key file named "
              "<NAME>.pub, where <NAME> is specified through the --ostree-key switch. "
              "(default: working directory)"))

    subparser.set_defaults(func=do_sign_kernel)
