"""
Backend handling for the secboot subcommand on TI K3 based machines
"""

import glob
import json
import logging
import os
import re
import shutil
import shlex
import subprocess

from tcbuilder.backend.common import \
    (check_if_file_exists, get_storage_dir, get_tar_compress_program_options)
from tcbuilder.backend.secboot import \
    (check_basic_signing_prerequisites, DEFAULT_TCB_SIGNING_FILES_TARNAME, MKIMAGE_DTC_OPT,
     SECURE_BOOT_FILES_DIR, SECURE_BOOT_WORKDIR, SIGNED_BOOTLOADER_ARTIFACTS_DIR, UBOOT_DTB,
     UBOOT_TOOLS_DIR)
from tcbuilder.backend.ubootenv import get_env_filename, find_board

from tcbuilder.errors import \
    (TorizonCoreBuilderError, InvalidArgumentError,
     FileContentMissing, InvalidStateError, InvalidDataError)

from tezi.image import ImageConfig, DEFAULT_IMAGE_JSON_FILENAME

log = logging.getLogger("torizon." + __name__)


# Machines whose bootloader can be signed with the K3 scheme, mapped to the SoC family they
# are based on. Only the keys are ever read: the family is recorded for the next machine to be
# added rather than consulted, because everything the signing needs is derived from the signing
# files the image itself carries.
K3_SIGNING_SUPPORTED_MACHINES = {
    "verdin-am62": "am62x",
}

# Top-level directory inside the signing files tarball.
K3_SIGNING_FILES_SUBDIR = "tcb-signing"

K3_MANIFEST_NAME = "manifest.json"
K3_MANIFEST_FORMAT_VERSION = 1

# Directory, relative to a signing root, where binman resolves the signing keys. It holds no
# files in the tarball, so it cannot be carried in it and is created at signing time.
K3_KEYS_SUBDIR = "arch/arm/mach-k3/keys"
K3_CUSTMPK_NAME = "custMpk.pem"
K3_DEGENERATE_KEY_NAME = "ti-degenerate-key.pem"
K3_DEGENERATE_KEY = os.path.join(SECURE_BOOT_FILES_DIR, K3_DEGENERATE_KEY_NAME)

# binman descriptor shipped without a /signature node; the public key that the bootloader
# verifies the kernel with is embedded into a copy of it named UBOOT_DTB.
UBOOT_DTB_NOKEYS = "u-boot.dtb-nokeys"

# Written by the container build with the U-Boot revision the signing tools come from.
UBOOT_RELEASE_FILE = "/u-boot/uboot-release"

# Set to "1" by a developer who wants the signing work directory left behind to inspect what
# binman did. It is not a supported setting: the directory holds copies of the private key the
# bootloader is signed with, which is why it is removed on every other run.
K3_KEEP_WORKDIR_ENV = "K3_KEEP_WORKDIR"

# Device states an image can target, and the tiboot3 variant each one boots: a module with the
# customer keys fused (HS-SE) runs the 'hs' container, an unfused one (HS-FS) the 'hs-fs'.
K3_TARGET_DEVICE_VARIANTS = {
    "hs-fs": "hs-fs",
    "hs-se": "hs",
}

# Request left beside the signed artifacts by --target-device, applied when the image is
# deployed and never installed on the device.
K3_TARGET_DEVICE_FILENAME = "tcb_k3_target_device.json"

# Extension of the boot binaries whose name carries the device variant. Only these are
# rewritten when an image is retargeted; anything else it installs keeps its name, whatever
# the name happens to contain.
K3_CONTAINER_EXT = ".bin"

# Matches the variant infix of a boot container filename, the '-hs-fs-' in
# tiboot3-am62x-hs-fs-verdin.bin for instance. Names without it, the GP container and the
# binaries common to every variant, are the same whatever the image targets.
K3_HS_VARIANT_RE = re.compile(r"-(hs(?:-fs)?)-")


def _detect_unpacked_image_board():
    """Read the machine name out of the U-Boot environment of the unpacked image."""

    # TODO: Hoist this into secboot.py and have the two older callers use it. The same lines sit
    # inlined in check_unpacked_tezi_hab_signing_support() and in
    # check_unpacked_tezi_kernel_signing_support(), identical down to the log message, so there
    # are three copies of the machine detection and this is the only one that is a function of
    # its own. Left as it is here because converging them means editing two functions that the
    # K3 signing work does not otherwise touch, which belongs in a change of its own.

    tezi_dir = os.path.join(get_storage_dir(), "tezi")
    initial_env = os.path.join(tezi_dir, get_env_filename(tezi_dir))

    with open(initial_env, "r", encoding="utf-8") as file:
        env = file.read()

    board = find_board(env)
    log.info(f"Detected image for machine \"{board}\".")

    return board


def check_unpacked_tezi_k3_signing_support():
    """Check if TorizonCore Builder can sign the bootloader of the unpacked TEZI image with
    the TI K3 signing scheme

    :returns: The name of the machine compatible with the image
    """

    board = _detect_unpacked_image_board()

    if board not in K3_SIGNING_SUPPORTED_MACHINES:
        raise InvalidStateError(
            "TorizonCore Builder doesn't support signing the TI K3 bootloader of images for "
            f"\"{board}\". Aborting.\n"
            f"Currently supported machines: {', '.join(K3_SIGNING_SUPPORTED_MACHINES)}")

    check_basic_signing_prerequisites()

    return board


def extract_k3_signing_files(tezi_dir):
    """Extract the signing files shipped by the image into a clean work directory

    :param tezi_dir: Path to the unpacked Toradex Easy Installer image
    :returns: Path to the directory holding the extracted signing files
    """

    tarball = os.path.join(tezi_dir, DEFAULT_TCB_SIGNING_FILES_TARNAME)
    if not os.path.isfile(tarball):
        raise InvalidArgumentError(
            f"The unpacked image does not contain \"{DEFAULT_TCB_SIGNING_FILES_TARNAME}\", "
            "which holds the binaries its bootloader is assembled from, so the bootloader "
            "cannot be signed. Aborting.\n"
            # TODO: name the first Torizon OS version shipping it once that version is known.
            "Please use an image built by a Torizon OS version that ships the bootloader "
            "signing files for this machine.")

    if os.path.isdir(SECURE_BOOT_WORKDIR):
        shutil.rmtree(SECURE_BOOT_WORKDIR)

    os.mkdir(SECURE_BOOT_WORKDIR)

    tarcmd = ["tar", "-xf", tarball, "-C", SECURE_BOOT_WORKDIR] + \
        get_tar_compress_program_options(tarball)
    log.debug(f"Running tar command: {shlex.join(tarcmd)}")
    subprocess.check_output(tarcmd, stderr=subprocess.STDOUT)

    signing_dir = os.path.join(SECURE_BOOT_WORKDIR, K3_SIGNING_FILES_SUBDIR)
    if not os.path.isdir(signing_dir):
        raise InvalidDataError(
            f"\"{DEFAULT_TCB_SIGNING_FILES_TARNAME}\" does not have the expected layout: it "
            f"has no \"{K3_SIGNING_FILES_SUBDIR}\" directory. Aborting.")

    return signing_dir


def _log_k3_uboot_revisions(manifest):
    """Log which U-Boot produced the image and which one built the signing tools.

    These normally differ, since the image is built from Toradex's U-Boot while the tools in
    this container come from upstream, and a difference is not by itself a problem: it is
    recorded for bug reports, not checked.
    """

    image_release = (manifest.get("uboot") or {}).get("release")

    tools_release = None
    if os.path.isfile(UBOOT_RELEASE_FILE):
        with open(UBOOT_RELEASE_FILE, "r", encoding="utf-8") as release_file:
            tools_release = release_file.read().strip()

    log.debug(f"U-Boot revision of the image: {image_release}; "
              f"of the signing tools in this container: {tools_release}.")


def remove_k3_signing_workdir():
    """Remove the signing work directory

    Signing leaves copies of the key passed with --k3-key in it: one staged into each signing
    root, and one more that binman writes into each root's output directory as it resolves the
    key by plain filename. That is the key whose hash the module fuses irreversibly, so the
    directory goes on every run, successful or not, rather than sitting in the storage volume
    until something else happens to clear it.

    A developer debugging a signing problem can keep it with K3_KEEP_WORKDIR=1, accepting that
    the keys stay with it.
    """

    if os.environ.get(K3_KEEP_WORKDIR_ENV) == "1":
        log.warning(f"Warning: {K3_KEEP_WORKDIR_ENV} is set, so \"{SECURE_BOOT_WORKDIR}\" is "
                    "being left behind; it holds copies of the key passed with --k3-key.")
        return

    if os.path.isdir(SECURE_BOOT_WORKDIR):
        shutil.rmtree(SECURE_BOOT_WORKDIR)


def remove_k3_signed_artifacts():
    """Remove the signed artifacts of a run that did not finish

    The directory is filled before the last steps of signing, and nothing downstream can tell a
    half-filled one from a finished one: `union.track_signed_bootloader()` copies it into the
    commit on nothing more than it existing and being non-empty. Left behind by a failed run it
    would put freshly signed binaries into an image beside the tarball that image came with,
    whose own copies of those binaries are the ones being replaced, and deploying would report
    success.

    Removing it whenever the run does not reach the end also clears what an earlier successful
    run left, which a failure before the directory is recreated would otherwise keep. Nothing
    worth inspecting goes with it: the binaries in it are copies of files in the work directory,
    which K3_KEEP_WORKDIR keeps.
    """

    if os.path.isdir(SIGNED_BOOTLOADER_ARTIFACTS_DIR):
        shutil.rmtree(SIGNED_BOOTLOADER_ARTIFACTS_DIR)


def read_k3_signing_manifest(signing_dir, board):
    """Read and check the manifest of the extracted signing files

    :param signing_dir: Path to the directory holding the extracted signing files
    :param board: Name of the machine the unpacked image is for
    :returns: Tuple with the list of signing roots and the SOURCE_DATE_EPOCH to sign with
    """

    manifest_path = os.path.join(signing_dir, K3_MANIFEST_NAME)
    if not os.path.isfile(manifest_path):
        raise FileContentMissing(
            f"The signing files of this image have no \"{K3_MANIFEST_NAME}\", so their layout "
            "cannot be determined. Aborting.")

    with open(manifest_path, "r", encoding="utf-8") as manifest_file:
        try:
            manifest = json.load(manifest_file)
        except json.JSONDecodeError as exc:
            raise InvalidDataError(
                f"Could not parse \"{K3_MANIFEST_NAME}\" of the signing files: {exc}. "
                "Aborting.") from exc

    format_version = manifest.get("format_version")
    if format_version != K3_MANIFEST_FORMAT_VERSION:
        raise InvalidDataError(
            f"The signing files of this image are in format version \"{format_version}\", "
            f"while this version of TorizonCore Builder handles version "
            f"{K3_MANIFEST_FORMAT_VERSION}. Please update TorizonCore Builder. Aborting.")

    machine = manifest.get("machine")
    if machine != board:
        raise InvalidDataError(
            f"The signing files were produced for machine \"{machine}\" while the unpacked "
            f"image is for \"{board}\": they do not belong to this image. Aborting.")

    roots = manifest.get("roots")
    if not roots:
        raise FileContentMissing(
            f"The signing files declare no directories to build from in \"{K3_MANIFEST_NAME}\". "
            "Aborting.")

    for root in roots:
        if not os.path.isdir(os.path.join(signing_dir, root)):
            raise FileContentMissing(
                f"The signing files declare a \"{root}\" directory which is not there: the "
                "tarball is truncated. Aborting.")

    signing = manifest.get("signing") or {}

    if not signing.get("certificates_pinned"):
        log.info("Note: the certificates of this image were not generated reproducibly, so "
                 "its signed binaries cannot be compared byte-for-byte with the original "
                 "ones. The signing itself is not affected.")

    source_date_epoch = signing.get("source_date_epoch")
    if source_date_epoch is None:
        source_date_epoch = 0
        log.info("The signing files do not state which SOURCE_DATE_EPOCH the image was built "
                 f"with; assuming {source_date_epoch}.")

    _log_k3_uboot_revisions(manifest)

    return roots, source_date_epoch


def _k3_root_relpath(root_dir, pattern, *, required=True):
    """Find a single file or directory inside a signing root

    Paths are derived from what a root actually holds, so that the machines supported by this
    command are a list of names rather than a list of layouts.

    :param root_dir: Path to the signing root
    :param pattern: Glob pattern, relative to the root
    :param required: Whether having no match is an error
    :returns: The match as a path relative to the root, or "" if nothing matched
    """

    matches = sorted(glob.glob(os.path.join(root_dir, pattern)))

    if len(matches) > 1:
        raise InvalidDataError(
            f"Expected a single match for \"{pattern}\" in the signing files, but found "
            f"{len(matches)}. Aborting.")

    if not matches:
        if required:
            raise FileContentMissing(
                f"Could not find \"{pattern}\" in the signing files. Aborting.")
        return ""

    return os.path.relpath(matches[0], root_dir)


def _k3_root_device_tree(root_dir):
    """Name of the device tree binman builds a signing root for."""

    device_tree = _k3_root_relpath(root_dir, "arch/arm/dts/*.dtb")

    return os.path.splitext(os.path.basename(device_tree))[0]


def stage_k3_signing_keys(root_dir, k3_key, degenerate_key):
    """Put the signing keys where binman resolves them from

    :param root_dir: Path to the signing root
    :param k3_key: Path to the customer key every boot container is signed with
    :param degenerate_key: Path to TI's degenerate key, which signs the GP artifacts
    """

    keys_dir = os.path.join(root_dir, K3_KEYS_SUBDIR)
    os.makedirs(keys_dir, exist_ok=True)

    shutil.copy2(k3_key, os.path.join(keys_dir, K3_CUSTMPK_NAME))
    shutil.copy2(degenerate_key, os.path.join(keys_dir, K3_DEGENERATE_KEY_NAME))


def add_kernel_pubkey_to_dtb(uboot_dtb_path, key_dir, key_name, key_algo):
    """Embed the public half of the kernel signing key into a U-Boot DTB

    :param uboot_dtb_path: Path to the DTB to be updated
    :param key_dir: Path to the directory holding the kernel key
    :param key_name: Name of the kernel key
    :param key_algo: Pair of hashing and crypto algorithms used to sign the kernel
    """

    # TODO: Drop the private key requirement by using fdt_add_pubkey here, as the recovery path
    # in add_recovered_pubkey_to_dtb already does. mkimage is handed a key pair only because it
    # refuses to run without one, while the public half is all that goes into the device tree;
    # requiring the private half means a user cannot embed a kernel key whose secret half stays
    # in an HSM or on another machine. Measured equivalent: fdt_add_pubkey -a <algo> -k <dir>
    # -n <name> -r conf writes a DTB byte-identical to the one mkimage -f auto-conf produces,
    # "conf" being the value mkimage picks for that mode. What would be lost is the "Public key
    # written to" line checked below, so the swap should confirm the node another way, by reading
    # the device tree back. sign_bootloader_hab takes the same detour through mkimage in
    # update_dtb_public_key (backend/secboot.py) and would gain the same thing; doing both at once
    # is what keeps the two commands behaving alike.
    check_if_file_exists(f"{key_name}.key", key_dir)
    check_if_file_exists(f"{key_name}.crt", key_dir)

    # mkimage insists on writing a FIT image; it is of no use here and is removed below.
    unused_fit = os.path.join(SECURE_BOOT_WORKDIR, "unused.itb")

    mkimage_cmd = [f"{UBOOT_TOOLS_DIR}/mkimage", "-D", MKIMAGE_DTC_OPT, "-f", "auto-conf",
                   "-d", "/dev/null", "-g", key_name, "-k", key_dir,
                   "-K", uboot_dtb_path, "-o", key_algo, "-r", unused_fit]

    log.info(f"Adding public key '{key_name}' in {key_dir} to "
             f"{os.path.basename(uboot_dtb_path)}")
    log.info(shlex.join(mkimage_cmd))

    try:
        mkimage_output = subprocess.check_output(mkimage_cmd, text=True,
                                                 stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as exc:
        raise TorizonCoreBuilderError(exc.output.strip()) from exc
    finally:
        if os.path.isfile(unused_fit):
            os.remove(unused_fit)

    log.debug("---------- OUTPUT FROM MKIMAGE ----------")
    log.debug(mkimage_output)
    log.debug("--------- END OF MKIMAGE OUTPUT ---------")

    if not re.search(r"Public key written to", mkimage_output, re.IGNORECASE):
        raise InvalidStateError(
            "Could not confirm if mkimage correctly wrote the public key of the kernel FIT "
            f"image into {os.path.basename(uboot_dtb_path)}. Aborting.")


def prepare_k3_uboot_dtb(root_dir, key_dir, key_name, key_algo):
    """Build the binman descriptor of a root from the pristine one shipped by the image

    Only the root producing the binaries that verify the kernel has a descriptor to prepare:
    it ships without a /signature node, and the public key goes into a copy of it. The copy is
    made on every run, so that signing twice does not stack one key on top of another.

    :param root_dir: Path to the signing root
    :param key_dir: Path to the directory holding the kernel key
    :param key_name: Name of the kernel key
    :param key_algo: Pair of hashing and crypto algorithms used to sign the kernel
    :returns: Whether this root had a descriptor to prepare
    """

    nokeys_dtb = os.path.join(root_dir, UBOOT_DTB_NOKEYS)
    if not os.path.isfile(nokeys_dtb):
        return False

    uboot_dtb = os.path.join(root_dir, UBOOT_DTB)
    shutil.copy2(nokeys_dtb, uboot_dtb)

    add_kernel_pubkey_to_dtb(uboot_dtb, key_dir, key_name, key_algo)

    return True


def run_binman_for_k3_root(root_dir, source_date_epoch):
    """Assemble the boot binaries of one signing root with binman

    binman runs with the root as both its working directory and its output directory, the way
    the U-Boot build runs it in the build directory. Both matter: the descriptor reaches its
    inputs through paths relative to the working directory, and it stages the signing keys
    into the output directory, where the openssl calls that sign the containers then look for
    them by plain filename.

    :param root_dir: Path to the signing root
    :param source_date_epoch: Value of SOURCE_DATE_EPOCH to sign with
    """

    device_tree = _k3_root_device_tree(root_dir)

    include_dirs = [".", "arch/arm/dts", K3_KEYS_SUBDIR,
                    _k3_root_relpath(root_dir, "board/*/*")]

    firmware_dir = _k3_root_relpath(root_dir, "usr/lib/firmware", required=False)
    if firmware_dir:
        include_dirs.append(firmware_dir)

    # The firmware blobs are only in the root that builds the binaries running on the main
    # cores; the other root gets empty values for them, as the U-Boot build does.
    atf_path = _k3_root_relpath(root_dir, "firmware/bl31.bin", required=False)
    tee_path = _k3_root_relpath(root_dir, "usr/lib/firmware/bl32.bin", required=False)
    ti_dm_path = _k3_root_relpath(root_dir, "usr/lib/firmware/ti-dm/*/*", required=False)

    binman_cmd = [f"{UBOOT_TOOLS_DIR}/binman/binman", "--toolpath", UBOOT_TOOLS_DIR, "build",
                  "-u", "-d", UBOOT_DTB, "-O", ".", "-m", "--allow-missing"]

    for include_dir in include_dirs:
        binman_cmd += ["-I", include_dir]

    binman_cmd += ["-a", f"of-list={device_tree}", "-a", f"default-dt={device_tree}",
                   "-a", f"atf-bl31-path={atf_path}", "-a", f"tee-os-path={tee_path}",
                   "-a", f"ti-dm-path={ti_dm_path}",
                   "-a", "opensbi-path=", "-a", "scp-path=", "-a", "rockchip-tpl-path=",
                   "-a", "spl-bss-pad=", "-a", "tpl-bss-pad=1", "-a", "spl-dtb=y",
                   "-a", "tpl-dtb=", "-a", "pre-load-key-path="]

    binman_extra_env = {"SOURCE_DATE_EPOCH": str(source_date_epoch)}

    log.info(f"Assembling the boot binaries of \"{os.path.basename(root_dir)}\" with binman")
    binman_print = (" ".join([f"{key}={val}" for key, val in binman_extra_env.items()]) + " " +
                    shlex.join(binman_cmd))
    print()
    log.info(binman_print)
    print()

    try:
        binman_output = subprocess.check_output(binman_cmd, cwd=root_dir, text=True,
                                                env=(os.environ | binman_extra_env),
                                                stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as exc:
        raise TorizonCoreBuilderError(exc.output.strip()) from exc

    if binman_output.rstrip() != '':
        log.debug("---------- OUTPUT FROM BINMAN ----------")
        log.debug(binman_output)
        log.debug("--------- END OF BINMAN OUTPUT ---------")


def _iter_image_rawfiles(image_config):
    """Iterate over the raw file entries of a Toradex Easy Installer configuration

    :param image_config: `ImageConfig` object of the image
    :returns: Generator over the entries, which can be modified in place
    """

    def walk(node):
        if isinstance(node, dict):
            for rawfile in node.get("rawfiles") or []:
                if isinstance(rawfile, dict) and rawfile.get("filename"):
                    yield rawfile
            for value in node.values():
                yield from walk(value)
        elif isinstance(node, list):
            for value in node:
                yield from walk(value)

    yield from walk(image_config.json_data)


def _k3_hs_variant(filename):
    """The device variant a boot binary is built for, or None if its name does not say

    :param filename: Name of the file, as the image installs it
    :returns: The variant as it appears in the filename, or None
    """

    if not filename.endswith(K3_CONTAINER_EXT):
        return None

    match = K3_HS_VARIANT_RE.search(filename)

    return match.group(1) if match else None


def _k3_retarget_filename(filename, variant):
    """The name the same boot binary has when built for another kind of device

    :param filename: Name of the file, as the image installs it
    :param variant: Variant to name it for
    :returns: The rewritten name, or the name unchanged if it carries no variant
    """

    current = _k3_hs_variant(filename)
    if current is None or current == variant:
        return filename

    return filename.replace(f"-{current}-", f"-{variant}-", 1)


def _k3_variant_siblings(filename):
    """Names the same bootloader binary has when built for the other device states."""

    return {_k3_retarget_filename(filename, variant)
            for variant in K3_TARGET_DEVICE_VARIANTS.values()}


def _list_signing_files(signing_dir):
    """List everything under the extracted signing files, relative to their parent directory.

    :param signing_dir: Path to the directory holding the extracted signing files
    :returns: Set of paths, directories included, as stored in the tarball
    """

    workdir = os.path.dirname(signing_dir)

    entries = {os.path.relpath(signing_dir, workdir)}
    for dirpath, dirnames, filenames in os.walk(signing_dir):
        for name in dirnames + filenames:
            entries.add(os.path.relpath(os.path.join(dirpath, name), workdir))

    return entries


def _generated_signing_files(signing_dir, original_entries):
    """Find the files produced while signing, as opposed to those that came with the image.

    binman builds inside the directory it reads from, which is what the U-Boot build does, so
    telling its output apart from its input is a matter of knowing what was there first.

    Each root builds into its own directory, so the same name can come out of both. Every path
    a name resolves to is kept rather than the last one seen, which leaves the ambiguity for the
    caller to reject for the names it actually ships. It is not rare: with the two roots of a
    verdin-am62, around 180 names are produced by both, the staged keys and the bytecode binman
    writes under tools/ among them. None of those is a bootloader binary.

    :param signing_dir: Path to the directory holding the extracted signing files
    :param original_entries: Entries present before signing, from `_list_signing_files`
    :returns: Mapping of filename to the list of paths with that name that were not there before
    """

    workdir = os.path.dirname(signing_dir)

    generated = {}
    for entry in sorted(_list_signing_files(signing_dir) - original_entries):
        path = os.path.join(workdir, entry)
        if os.path.isfile(path):
            generated.setdefault(os.path.basename(path), []).append(path)

    return generated


def collect_k3_signed_artifacts(generated, image_config, artifacts_dir):
    """Copy the binaries binman produced to the signed artifacts directory

    Everything the image installs is copied, plus the container of the device state the image
    does not currently target: shipping that one signed with the user's key as well is what
    makes retargeting the image safe, and it costs a few hundred kilobytes.

    :param generated: Mapping of filename to path for the files binman generated
    :param image_config: `ImageConfig` object of the unpacked image
    :param artifacts_dir: Path to the directory to copy the binaries to
    :returns: Sorted list of the names copied
    """

    produced = {name: paths for name, paths in generated.items() if not name.endswith(".map")}

    installed = {rawfile["filename"] for rawfile in _iter_image_rawfiles(image_config)}

    missing = sorted(installed - produced.keys())
    if missing:
        raise InvalidStateError(
            "binman did not produce these bootloader binaries that the image installs: "
            f"{', '.join(missing)}. Aborting.\n"
            "Run the command again with --verbose to see the output of binman.")

    siblings = set()
    for filename in installed:
        siblings |= _k3_variant_siblings(filename) & produced.keys()

    copied = sorted(installed | siblings)

    ambiguous = [
        f"{name} ("
        f"{', '.join(os.path.relpath(path, SECURE_BOOT_WORKDIR) for path in produced[name])})"
        for name in copied if len(produced[name]) > 1]
    if ambiguous:
        raise InvalidStateError(
            "More than one signing root produced these bootloader binaries, so there is no "
            f"telling which one the image should install: {'; '.join(ambiguous)}. Aborting.")

    for filename in copied:
        shutil.copy2(produced[filename][0], os.path.join(artifacts_dir, filename))

    log.info(f"Signed bootloader binaries: {', '.join(copied)}.")

    return copied


def refresh_k3_signing_files_binaries(signing_dir, artifacts_dir, artifacts):
    """Replace the boot binaries carried by the signing files with the freshly signed ones

    One of the roots ships copies of binaries built by the other, for the bootloader update
    containers it assembles. Left alone they would keep the signatures of the image this one
    was made from.

    :param signing_dir: Path to the directory holding the extracted signing files
    :param artifacts_dir: Path to the directory holding the signed binaries
    :param artifacts: Names of the signed binaries
    """

    for dirpath, _, filenames in os.walk(signing_dir):
        for name in filenames:
            if name in artifacts:
                shutil.copy2(os.path.join(artifacts_dir, name), os.path.join(dirpath, name))


def repack_k3_signing_files(signing_dir, original_entries, artifacts_dir, source_date_epoch):
    """Re-create the signing files tarball from the work directory

    Only what the image shipped goes back in, so the tarball travelling in the signed image
    has the same shape as the one that came with it: no signing keys, and none of the files
    binman built along the way.

    The tar options are the ones the recipe that produced the tarball uses, rather than a set
    picked here: tcb-signing-files.bb in meta-toradex-torizon. Matching them is what makes a
    re-signed image comparable with the one it was made from. Without pinning the timestamps,
    the binaries replaced just above carry the wall clock of the signing run while every other
    member carries the build's epoch, so two signings of the same image with the same key
    produce two different tarballs and therefore two different images, even though every
    binary inside them is identical. The member order comes from the sorted list handed to
    --files-from rather than from --sort=name, since --no-recursion means tar never reads a
    directory to sort.

    :param signing_dir: Path to the directory holding the extracted signing files
    :param original_entries: Entries present before signing, from `_list_signing_files`
    :param artifacts_dir: Path to the directory to write the tarball to
    :param source_date_epoch: Value of SOURCE_DATE_EPOCH the image was built with
    """

    workdir = os.path.dirname(signing_dir)
    entries_file = os.path.join(SECURE_BOOT_WORKDIR, "signing_files.list")

    with open(entries_file, "w", encoding="utf-8") as entries:
        entries.write("\n".join(sorted(original_entries)) + "\n")

    tarcmd = ["tar", "--dereference", "--hard-dereference", "--sort=name", "--format=gnu",
              f"--mtime=@{source_date_epoch}", "--clamp-mtime",
              "--owner=0", "--group=0", "--numeric-owner",
              "-C", workdir, "--no-recursion", "--files-from", entries_file,
              "-czf", os.path.join(artifacts_dir, DEFAULT_TCB_SIGNING_FILES_TARNAME)]

    log.debug(f"Running tar command: {shlex.join(tarcmd)}")
    subprocess.check_output(tarcmd, stderr=subprocess.STDOUT)

    os.remove(entries_file)


def _image_target_variant(image_config):
    """The container variant the image currently installs, or None if it installs none."""

    for rawfile in _iter_image_rawfiles(image_config):
        variant = _k3_hs_variant(rawfile["filename"])
        if variant:
            return variant

    return None


def _warn_about_k3_target_device(target_device):
    """Say what the requested device state means for the module the image is installed on."""

    if K3_TARGET_DEVICE_VARIANTS[target_device] == K3_TARGET_DEVICE_VARIANTS["hs-se"]:
        log.warning("Warning: the image will boot only on a module whose keys have been "
                    "fused; make sure the module is properly fused, otherwise the image will "
                    "hang at boot.")
    else:
        log.warning("Warning: the image will boot only on a module that is not fused; this "
                    "setup is normally used during development and evaluation only.")

    log.warning("Note: the Toradex Easy Installer recovery files are not affected by this "
                "setting. Recovering a module over USB requires a recovery image built for "
                "the kind of device being recovered.")


def set_k3_target_device(artifacts_dir, image_config, target_device, artifacts):
    """Record that the deployed image should target another device state

    The rewrite itself happens at deploy time: deploying recomputes fields of image.json that
    signing cannot know, so the file is edited there rather than replaced from here. What can
    be decided now is whether the rewrite will have anything to work with, and that is decided
    now: a request recorded here and found impossible at the end of a deploy is a long way to
    walk for something knowable before the signed artifacts are even written.

    :param artifacts_dir: Path to the directory holding the signed artifacts
    :param image_config: `ImageConfig` object of the unpacked image
    :param target_device: Device state the deployed image should target
    :param artifacts: Names of the signed binaries, from `collect_k3_signed_artifacts`
    """

    variant = K3_TARGET_DEVICE_VARIANTS[target_device]

    if _image_target_variant(image_config) == variant:
        log.info(f"The image already targets a {target_device.upper()} device; its "
                 "configuration will be left as it is.")
        return

    retargeted = set()
    for rawfile in _iter_image_rawfiles(image_config):
        filename = _k3_retarget_filename(rawfile["filename"], variant)
        if filename != rawfile["filename"]:
            retargeted.add(filename)

    if not retargeted:
        raise InvalidArgumentError(
            f"Cannot make the image target a {target_device.upper()} device: none of the "
            "bootloader binaries it installs is built for one kind of device rather than "
            "another, so there is no name to rewrite. Aborting.")

    missing = sorted(retargeted - set(artifacts))
    if missing:
        raise InvalidStateError(
            f"Cannot make the image target a {target_device.upper()} device: the signing did "
            f"not produce {', '.join(missing)}, which the image would have to install. "
            "Aborting.\n"
            "Run the command again with --verbose to see the output of binman.")

    request_path = os.path.join(artifacts_dir, K3_TARGET_DEVICE_FILENAME)
    with open(request_path, "w", encoding="utf-8") as request_file:
        json.dump({"target_device": target_device, "variant": variant}, request_file, indent=4)

    log.info(f"The deployed image will be set to target a {target_device.upper()} device.")
    _warn_about_k3_target_device(target_device)


def apply_k3_target_device(tezi_dir):
    """Apply a device state requested at signing time to a deployed image

    Called after the signed artifacts have been copied over the output image. The request
    travels with those artifacts as a file, which is consumed here so that it never reaches
    the device.

    :param tezi_dir: Path to the Toradex Easy Installer image to update
    """

    request_path = os.path.join(tezi_dir, K3_TARGET_DEVICE_FILENAME)
    if not os.path.isfile(request_path):
        return

    with open(request_path, "r", encoding="utf-8") as request_file:
        request = json.load(request_file)
    os.remove(request_path)

    variant = request["variant"]
    target_device = request["target_device"]

    image_config = ImageConfig(os.path.join(tezi_dir, DEFAULT_IMAGE_JSON_FILENAME))

    retargeted = set()
    for rawfile in _iter_image_rawfiles(image_config):
        filename = _k3_retarget_filename(rawfile["filename"], variant)
        if filename == rawfile["filename"]:
            continue
        if not os.path.isfile(os.path.join(tezi_dir, filename)):
            raise InvalidStateError(
                f"Cannot make the image target a {target_device.upper()} device: it does not "
                f"contain \"{filename}\". Aborting.")
        rawfile["filename"] = filename
        retargeted.add(filename)

    if not retargeted:
        raise InvalidStateError(
            f"The image was signed to target a {target_device.upper()} device, but none of the "
            "bootloader binaries it installs carries a name that can be rewritten for one. "
            "Aborting.")

    image_config.save()
    log.info(f"Image set to target a {target_device.upper()} device, installing "
             f"{', '.join(sorted(retargeted))}.")


# pylint: disable-next=too-many-locals
def sign_bootloader_k3(*, k3_key, degenerate_key, kernel_key_dir, kernel_key_name,
                       kernel_key_algo, target_device=None):
    """Sign the bootloader binaries of an unpacked image for a TI K3 based machine

    :param k3_key: Path to the customer key that every boot container is signed with
    :param degenerate_key: Path to TI's degenerate key, which signs the GP artifacts
    :param kernel_key_dir: Path to the directory holding the kernel key
    :param kernel_key_name: Name of the kernel key
    :param kernel_key_algo: Pair of hashing and crypto algorithms used to sign the kernel
    :param target_device: Device state the deployed image should target, or None to leave the
                          image targeting what it already targets
    """

    completed = False
    try:
        # Inside the try, so that refusing an unsupported machine still clears the artifacts an
        # earlier run left: union copies that directory on nothing more than it being non-empty.
        board = check_unpacked_tezi_k3_signing_support()

        tezi_dir = os.path.join(get_storage_dir(), "tezi")
        image_config = ImageConfig(os.path.join(tezi_dir, DEFAULT_IMAGE_JSON_FILENAME))

        signing_dir = extract_k3_signing_files(tezi_dir)
        roots, source_date_epoch = read_k3_signing_manifest(signing_dir, board)

        log.info(f"Signing the bootloader binaries of a \"{board}\" image with "
                 f"\"{os.path.basename(k3_key)}\".")

        original_entries = _list_signing_files(signing_dir)

        # Preparing every root first means the check below is reached before any assembly
        # rather than after all of it, and the user gets this message instead of whatever
        # binman says about a descriptor that was never written.
        prepared = False
        for root in roots:
            root_dir = os.path.join(signing_dir, root)

            stage_k3_signing_keys(root_dir, k3_key, degenerate_key)
            prepared |= prepare_k3_uboot_dtb(root_dir, kernel_key_dir, kernel_key_name,
                                             kernel_key_algo)

        if not prepared:
            raise InvalidDataError(
                f"None of the signing files directories has a \"{UBOOT_DTB_NOKEYS}\" to add the "
                "kernel public key to, so the signed bootloader would not be able to verify the "
                "kernel. Aborting.")

        for root in roots:
            run_binman_for_k3_root(os.path.join(signing_dir, root), source_date_epoch)

        if os.path.isdir(SIGNED_BOOTLOADER_ARTIFACTS_DIR):
            shutil.rmtree(SIGNED_BOOTLOADER_ARTIFACTS_DIR)

        os.mkdir(SIGNED_BOOTLOADER_ARTIFACTS_DIR)

        generated = _generated_signing_files(signing_dir, original_entries)
        artifacts = collect_k3_signed_artifacts(generated, image_config,
                                                SIGNED_BOOTLOADER_ARTIFACTS_DIR)

        if target_device:
            set_k3_target_device(SIGNED_BOOTLOADER_ARTIFACTS_DIR, image_config,
                                 target_device, artifacts)

        refresh_k3_signing_files_binaries(signing_dir, SIGNED_BOOTLOADER_ARTIFACTS_DIR, artifacts)
        repack_k3_signing_files(signing_dir, original_entries, SIGNED_BOOTLOADER_ARTIFACTS_DIR,
                                source_date_epoch)

        completed = True
    finally:
        # The keys go first: removing them is the cleanup with a consequence, and it should not
        # be reachable only through one that has none.
        remove_k3_signing_workdir()

        if not completed:
            remove_k3_signed_artifacts()
