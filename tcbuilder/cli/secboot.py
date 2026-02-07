"""
CLI handling for secboot subcommand
"""

import logging
import os

from tcbuilder.backend import secboot
from tcbuilder.backend import kernel
from tcbuilder.backend.common import images_unpack_executed, unpacked_image_type
from tcbuilder.errors import InvalidArgumentError, InvalidDataError

log = logging.getLogger("torizon." + __name__)

CST_CRYPTO_TYPES = ("rsa", "ecdsa")
CST_DIG_ALGO_TYPES = ["sha256"]
CST_DEFAULT_KEY_SIZE = "2048"
CST_DEAFULT_KEY_EXP = "65537"
CST_SRK_INDEXES = ("1", "2", "3", "4")
CST_SRK_DEFAULT_TABLE = "SRK_1_2_3_4_table.bin"
CST_SRK_DEFAULT_FUSE = "SRK_1_2_3_4_fuse.bin"

KERNEL_KEY_DEFAULT_ALGO = "sha256,rsa2048"

def validate_kernel_key_arg(kernel_key):
    """Parse and validate --kernel-key arg"""

    kernel_key_name = ""
    kernel_key_algo = ""
    for element in kernel_key.split(';'):
        argpair = element.split('=')

        if len(argpair) > 2:
            raise InvalidArgumentError("--kernel-key is not correctly formatted. Did you separate "
                                       "each field with a semicolon (;) ?")
        if len(argpair) == 1:
            argkey = argpair[0]
            argvalue = ""
        else:
            argkey, argvalue = argpair

        if argkey.strip() == 'name':
            kernel_key_name = argvalue.strip()
        elif argkey.strip() == 'algo':
            kernel_key_algo = argvalue.strip()

    if not kernel_key_name:
        raise InvalidArgumentError("Could not find value of 'name' in --kernel-key. Aborting.")

    if not kernel_key_algo:
        log.info("Could not find value of 'algo' in --kernel-key. "
                 f"Defaulting to {KERNEL_KEY_DEFAULT_ALGO}.")
        kernel_key_algo = KERNEL_KEY_DEFAULT_ALGO

    return kernel_key_name, kernel_key_algo


def do_sign_kernel(args):
    """Run 'secboot sign-kernel' subcommand"""

    if not os.path.isdir(args.kernel_key_dir):
        raise InvalidArgumentError(
            f"Directory \"{args.kernel_key_dir}\" does not exist: aborting.")

    kernel_key_name, kernel_key_algo = validate_kernel_key_arg(args.kernel_key)

    images_unpack_executed()
    if unpacked_image_type() == "raw":
        raise InvalidDataError("Secboot commands are not supported for WIC/raw images. "
                               "Aborting.")

    kernel_changes_dir = kernel.get_kernel_changes_dir()
    if not os.path.isdir(kernel_changes_dir):
        os.mkdir(kernel_changes_dir)

    secboot.sign_kernel(
        kernel_changes_dir=kernel_changes_dir,
        key_dir=args.kernel_key_dir,
        key_algo=kernel_key_algo,
        key_name=kernel_key_name
    )


def do_sign_bootloader_hab(args):
    """Run 'secboot sign-bootloader-hab' subcommand"""

    if not os.path.isdir(args.cst_dir):
        raise InvalidArgumentError(
            f"Directory \"{args.cst_dir}\" does not exist: aborting.")

    if args.kernel_key_dir:
        if not os.path.isdir(args.kernel_key_dir):
            raise InvalidArgumentError(
                f"Directory \"{args.kernel_key_dir}\" does not exist: aborting.")
        if not args.kernel_key:
            raise InvalidArgumentError(
                "--kernel-key-dir was passed but --kernel-key was not provided. Aborting.")

    kernel_key_name = None
    kernel_key_algo = None
    if args.kernel_key:
        if not args.kernel_key_dir:
            raise InvalidArgumentError(
                "--kernel-key was passed but --kernel-key-dir was not provided. Aborting.")
        kernel_key_name, kernel_key_algo = validate_kernel_key_arg(args.kernel_key)

    images_unpack_executed()
    if unpacked_image_type() == "raw":
        raise InvalidDataError("Secboot commands are not supported for WIC/raw images. "
                               "Aborting.")

    cst_args = {
        "crypto": args.cst_crypto,
        "key_size": args.cst_key_size,
        "key_exp": args.cst_key_exp,
        "dig_algo": args.cst_dig_algo,
        "srk_index": args.cst_srk_index,
        "srk_table": args.cst_srk_table,
        "srk_fuse": args.cst_srk_fuse,
        "srk_no_ca": args.cst_srk_no_ca
    }

    secboot.sign_bootloader_hab(
        kernel_key_dir=args.kernel_key_dir,
        kernel_key_name=kernel_key_name,
        kernel_key_algo=kernel_key_algo,
        cst_dir=args.cst_dir,
        cst_args=cst_args
    )

    if args.kernel_key_dir:
        log.info(f"Public key '{kernel_key_name}' in {args.kernel_key_dir} will be used by "
                 "the bootloader to verify the kernel signature.")
    else:
        log.warning("The bootloader DTBs were NOT updated with a new public key.")
        log.warning("If the kernel fitImage will be signed with a new key, please re-run the "
                    "command with --kernel-key-dir and --kernel-key so the new kernel signature "
                    "can be properly verified by the bootloader.")
        log.warning("Otherwise, this message can be ignored.")
    print()

    log.info("Bootloader in Torizon OS image signed successfully!")


def init_parser(subparsers):
    """Initialize argument parser"""

    parser = subparsers.add_parser(
        "secboot",
        help=("Sign different components of an unpacked Torizon OS image in "
              "Toradex Easy Installer format."),
        allow_abbrev=False)

    subparsers = parser.add_subparsers(title='Commands', required=True, dest='cmd')

    # secboot sign-kernel
    subparser = subparsers.add_parser(
        "sign-kernel",
        help=("Sign the kernel fitImage of an unpacked Torizon OS image."),
        description=("Currently supported machines: "
                     f"{', '.join(secboot.KERNEL_SIGNING_SUPPORTED_MACHINES)}"))

    subparser.add_argument(
        "--kernel-key-dir", dest="kernel_key_dir",
        default=".",
        metavar="KERNEL_KEY_DIR",
        help="Kernel fitImage key directory path. This directory must contain a private key in "
             "PEM format having the .key extension. (default: working directory)")

    subparser.add_argument(
        "--kernel-key", dest="kernel_key",
        help="Key information in the form 'name=<NAME>;algo=<ALGO>', where <NAME> is the "
             "key name and <ALGO> is a comma-separated pair of the hashing and crypto algorithms "
             "to be used for the signing process (e.g. 'name=prod;algo=sha256,rsa2048'). "
             f"If <ALGO> is not provided, it defaults to '{KERNEL_KEY_DEFAULT_ALGO}'.",
        required=True)

    subparser.set_defaults(func=do_sign_kernel)

    # secboot sign-bootloader-hab
    subparser = subparsers.add_parser(
        "sign-bootloader-hab",
        help=("Sign bootloader components (SPL, DDR Firmware, U-Boot fitImage) for i.MX-based "
              "modules compatible with HAB using the Code Signing Tool (CST) from NXP. The CST "
              "directory is specified with the --cst-dir argument. Keys and certificates "
              "(in .pem format), SRK table and e-fuse hash binaries have to be generated "
              "beforehand by following the NXP documentation."),
        description=("Currently supported machines: "
                     f"{', '.join(secboot.HAB_SIGNING_SUPPORTED_MACHINES)}"))

    subparser.add_argument(
        dest="cst_dir",
        metavar="CST_DIR",
        help="CST directory path.")

    subparser.add_argument(
        "--kernel-key-dir", dest="kernel_key_dir",
        help="Kernel fitImage key directory path. If specified the U-Boot DTB and Control DTBs "
             "will be updated with the public key before signing the bootloader. This directory "
             "must contain a private key (.key extension) and a certificate (.crt extension) with "
             "the public key, both in PEM format and with the same name.")

    subparser.add_argument(
        "--kernel-key", dest="kernel_key",
        help="Kernel key information in the form 'name=<NAME>;algo=<ALGO>' if updating the U-Boot "
             "DTBs, where <NAME> is the key name and <ALGO> is a comma-separated pair of the "
             "hashing and crypto algorithms used to sign the kernel "
             "(e.g. 'name=prod;algo=sha256,rsa2048'). If <ALGO> is not provided, "
             f"it defaults to '{KERNEL_KEY_DEFAULT_ALGO}'.")

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
        default=CST_DEAFULT_KEY_EXP,
        help=("Key exponent for RSA keys (only). "
              f"(default: {CST_DEAFULT_KEY_EXP})"))

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

    subparser.set_defaults(func=do_sign_bootloader_hab)
