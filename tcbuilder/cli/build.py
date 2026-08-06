"""
CLI handling for build subcommand
"""

import os
import logging
import shutil
import sys
from datetime import datetime

from tezi.errors import TeziError
from tcbuilder.cli.bundle import parse_env_assignments
from tcbuilder.backend.bundle import download_containers_by_compose_file
from tcbuilder.backend.expandvars import UserFailureException
from tcbuilder.backend.registryops import RegistryOperations
from tcbuilder.errors import \
    (FeatureNotImplementedError, FileContentMissing, InvalidArgumentError, InvalidDataError,
     InvalidStateError, LicenceAcceptanceError, ParseError, ParseErrors, PathNotExistError,
     UnsupportedImageFeature, TorizonCoreBuilderError)

from tcbuilder.backend import common
from tcbuilder.backend import build as bb
from tcbuilder.backend import combine as comb_be
from tcbuilder.backend import dt as dt_be
from tcbuilder.backend import images as images_be
from tcbuilder.backend import kernel as kernel_be
from tcbuilder.backend import ostree as ostree_be
from tcbuilder.backend import secboot as secboot_be
from tcbuilder.backend import ubootenv as ubootenv_be
from tcbuilder.cli import deploy as deploy_cli
from tcbuilder.cli import dt as dt_cli
from tcbuilder.cli import dto as dto_cli
from tcbuilder.cli import kernel as kernel_cli
from tcbuilder.cli import images as images_cli
from tcbuilder.cli import splash as splash_cli
from tcbuilder.cli import splashconfig as splashconfig_cli
from tcbuilder.cli import union as union_cli
from tcbuilder.cli import secboot as secboot_cli

DEFAULT_BUILD_FILE = "tcbuild.yaml"
TEMPLATE_BUILD_FILE = "tcbuild.template.yaml"

L1_PREF = "\n=>> "
L2_PREF = "\n=> "

log = logging.getLogger("torizon." + __name__)


def l1_pref(orgstr):
    """Add L1_PREF prefix to orgstr"""
    return L1_PREF + orgstr


def l2_pref(orgstr):
    """Add L2_PREF prefix to orgstr"""
    return L2_PREF + orgstr


def create_template(config_fname, force=False):
    """Main handler for the create-template mode of the build subcommand"""

    src_file = os.path.join(os.path.dirname(__file__), TEMPLATE_BUILD_FILE)

    # Dump the file directly to stdout (avoid creating root owned files):
    if config_fname == '-':
        with open(src_file, "r", encoding="utf-8") as file:
            for line in file:
                print(line, end='')
        return

    if os.path.exists(config_fname) and not force:
        raise InvalidStateError(f"File '{config_fname}' already exists: aborting.")

    log.info(f"Creating template file '{config_fname}'")
    shutil.copy(src_file, config_fname)
    common.set_output_ownership(config_fname)


def translate_tezi_props(tezi_props):
    """Translate the tcbuild.yaml's output.easyinstaler settings"""

    return {
        "name": tezi_props.get("name"),
        "description": tezi_props.get("description"),
        "accept_licence": tezi_props.get("accept-licence"),
        "autoinstall": tezi_props.get("autoinstall"),
        "autoreboot": tezi_props.get("autoreboot"),
        "licence_file": tezi_props.get("licence"),
        "release_notes_file": tezi_props.get("release-notes")
    }


def handle_input_section(props, **kwargs):
    """Handle the input section of the configuration file

    :param props: Dictionary holding the data of the section.
    :param kwargs: Keyword arguments that are forwarded to the handling
                   functions of the subsections.
    :returns: Input image path in case of a disk image, None if TEZI image
    """

    base_raw_image = None
    if props:
        log.info(l1_pref("Handling input section"))

    download_dir = None
    if "image-download-dir" in props:
        if not os.path.isdir(props["image-download-dir"]):
            os.makedirs(props["image-download-dir"])
            common.set_output_ownership(props["image-download-dir"], set_parents=True)
        download_dir = props["image-download-dir"]

    if "easy-installer" in props:
        handle_easy_installer_input(props["easy-installer"], download_dir, **kwargs)
    elif "ostree" in props:
        handle_ostree_input(props["ostree"], **kwargs)
    elif "raw-image" in props:
        base_raw_image = handle_raw_image_input(props["raw-image"], download_dir, **kwargs)
    else:
        raise FileContentMissing(
            "No kind of input specified in configuration file")
    return base_raw_image


def handle_easy_installer_input(props, download_dir=None):
    """Handle the input/easy-installer subsection of the configuration file

    :param props: Dictionary holding the data of the subsection.
    :param download_dir: Directory where files should be downloaded to or
                         obtained from if they already exist.
    """

    if "local" in props:
        images_cli.images_unpack(props["local"], remove_storage=True)

    elif ("remote" in props) or ("toradex-feed" in props):
        if "toradex-feed" in props:
            # Evaluate if it makes sense to supply a checksum here too (TODO).
            remote_url, remote_fname = common.make_feed_url(props["toradex-feed"])
            cksum = None
        else:
            # Parse remote which may contain integrity checking information.
            remote_url, remote_fname, cksum = bb.parse_remote(props["remote"])
            log.debug(f"Remote URL: {remote_url}, name: {remote_fname}, "
                      f"expected sha256: {cksum}")

        # Next call will download the file if necessary.
        local_file, is_temp = \
            common.fetch_remote(remote_url, remote_fname, cksum, download_dir)

        try:
            images_cli.images_unpack(local_file, remove_storage=True)
        finally:
            # Avoid leaving files in the temporary directory (if it was used).
            if is_temp:
                os.unlink(local_file)

    else:
        raise FileContentMissing(
            "No known input type specified in configuration file")

def handle_raw_image_input(props, download_dir=None):
    """Handle the input/raw-image subsection of the configuration file

    :param props: Dictionary holding the data of the subsection.
    :param download_dir: Directory where files should be downloaded to or
                         obtained from if they already exist.
    """

    if "local" in props:
        images_cli.images_unpack(
            props["local"],
            raw_rootfs_label=props.get("rootfs-label", common.DEFAULT_RAW_ROOTFS_LABEL),
            raw_sector_size=props.get("sector-size", common.DEFAULT_RAW_SECTOR_SIZE),
            remove_storage=True)
        base_raw_image = props["local"]

    elif ("remote" in props) or ("toradex-feed" in props):
        if "toradex-feed" in props:
            # Evaluate if it makes sense to supply a checksum here too (TODO).
            remote_url, remote_fname = common.make_feed_url(props["toradex-feed"])
            cksum = None
            if props["toradex-feed"]["machine"] in common.SYNAIMG_MACHINES:
                log.warning("Image for %s is in SYNAIMG format.", props["toradex-feed"]["machine"])
                log.warning("TorizonCore Builder cannot handle SYNAIMG directly.")
                log.warning("URL: %s", remote_url)
                raise UnsupportedImageFeature(
                    "Please manually download the image then convert it to a .img file with "
                    "the included syna2img.pyz program. Pass the result to TorizonCore Builder in "
                    "the 'local' field in the input section.")

        else:
            # Parse remote which may contain integrity checking information.
            remote_url, remote_fname, cksum = bb.parse_remote(props["remote"])
            log.debug(f"Remote URL: {remote_url}, name: {remote_fname}, "
                      f"expected sha256: {cksum}")

        # Next call will download the file if necessary.
        local_file, _ = common.fetch_remote(
            remote_url, fname=remote_fname, cksum=cksum, download_dir=download_dir)

        images_cli.images_unpack(
            local_file,
            raw_rootfs_label=props.get("rootfs-label", common.DEFAULT_RAW_ROOTFS_LABEL),
            raw_sector_size=props.get("sector-size", common.DEFAULT_RAW_SECTOR_SIZE),
            remove_storage=True)
        base_raw_image = local_file

    else:
        raise FileContentMissing(
            "No known input type specified in configuration file")
    return base_raw_image

def handle_ostree_input(props, **kwargs):
    """Handle the input/easy-installer subsection of the configuration file"""
    raise FeatureNotImplementedError(
        "Processing of ostree archive inputs is not implemented yet.")


def handle_customization_section(props):
    """Handle the customization section of the configuration file

    :param props: Dictionary holding the data of the section.
    """

    if props:
        log.info(l1_pref("Handling customization section"))

    if "splash-screen" in props:
        log.info(l2_pref("Setting splash screen image"))
        splash_cli.splash(props["splash-screen"])

    if "splash-config" in props:
        log.info(l2_pref("Setting splash screen configuration"))
        splashconfig_cli.splash_config_set(props["splash-config"])

    if "device-tree" in props:
        handle_dt_customization(props["device-tree"])

    if "kernel" in props:
        handle_kernel_customization(props["kernel"])

    if "secboot" in props:
        handle_secboot_customization(props["secboot"])

    # Filesystem changes are actually handled as part of the output processing.
    fs_changes = props.get("filesystem")

    return fs_changes


def handle_dt_customization(props):
    """Handle the device-tree customization section."""

    if props:
        log.info(l2_pref("Handling device-tree subsection"))

    if "custom" in props:
        log.info(l2_pref(f"Selecting custom device-tree '{props['custom']}'"))
        dt_cli.dt_apply(dts_path=props["custom"],
                        include_dirs=props.get("include-dirs", []))

    overlay_props = props.get("overlays", {})
    if overlay_props.get("clear", False):
        dto_cli.dto_remove_all()

        if "remove" in overlay_props:
            log.info("Individual overlay removal ignored because they've all been "
                     "removed due to the 'clear' property")

    elif "remove" in overlay_props:
        for overl in overlay_props["remove"]:
            dto_cli.dto_remove_single(overl, presence_required=False)

    if "add" in overlay_props:
        # We enable the overlay apply test only if it is possible to do it.
        test_apply = bool(dt_be.get_current_dtb_basename())
        if not test_apply:
            log.info("Not testing overlay because base image does not have a "
                     "device-tree set!")
        for overl in overlay_props["add"]:
            log.info(l2_pref(f"Adding device-tree overlay '{overl}'"))
            dto_cli.dto_apply(
                dtos_path=overl,
                dtb_path=None,
                include_dirs=props.get("include-dirs", []),
                allow_reapply=False,
                test_apply=test_apply)


def handle_kernel_customization(props):
    """Handle the kernel customization section."""

    if "modules" in props:
        for mod_props in props["modules"]:
            mod_source = mod_props["source-dir"]
            log.info(l2_pref(f"Building module located at '{mod_source}'"))
            kernel_cli.kernel_build_module(
                source_dir=mod_source,
                autoload=mod_props.get("autoload", False))

    if "arguments" in props:
        log.info(l2_pref("Setting kernel arguments"))
        kernel_cli.kernel_set_custom_args(kernel_args=props["arguments"])


def _handle_secboot_sign_bootloader_hab(sign_hab_props):
    """Handle the secboot.sign-bootloader-hab section."""

    cst_dir = sign_hab_props["cst-dir"]
    cst_dict = sign_hab_props.get("cst-args", {})
    kernel_key_dir = sign_hab_props.get("kernel-key-dir", None)
    kernel_key_list = sign_hab_props.get("kernel-key", [])
    kernel_key = {}

    if not os.path.isdir(cst_dir):
        raise InvalidArgumentError(
            f"Directory \"{cst_dir}\" does not exist: aborting.")

    if kernel_key_dir:
        if not os.path.isdir(kernel_key_dir):
            raise InvalidArgumentError(
                f"Directory \"{kernel_key_dir}\" does not exist: aborting.")
        if not kernel_key_list:
            raise InvalidArgumentError(
                "sign-bootloader-hab: 'kernel-key-dir' was passed but 'kernel-key' was "
                "not provided. Aborting.")

    if kernel_key_list:
        if len(kernel_key_list) > 1:
            raise InvalidArgumentError(
                "TorizonCore Builder only supports updating one public key. Aborting.")
        kernel_key = kernel_key_list[0]
        kernel_key_dir = kernel_key_dir or "."

        assert "name" in kernel_key, "'kernel-key' requires 'name' property"
        if "algo" not in kernel_key:
            log.info(f"Could not find value of 'algo' for key '{kernel_key['name']}'; "
                     f"defaulting to {secboot_cli.KERNEL_KEY_DEFAULT_ALGO}.")

    cst_args = {
        "crypto": cst_dict.get("crypto", secboot_cli.CST_CRYPTO_TYPES[0]),
        "key_size": cst_dict.get("key-size", secboot_cli.CST_DEFAULT_KEY_SIZE),
        "key_exp": cst_dict.get("key-exp", secboot_cli.CST_DEFAULT_KEY_EXP),
        "dig_algo": cst_dict.get("dig-algo", secboot_cli.CST_DIG_ALGO_TYPES[0]),
        "srk_index": cst_dict.get("srk-index", secboot_cli.CST_SRK_INDEXES[0]),
        "srk_table": cst_dict.get("srk-table", secboot_cli.CST_SRK_DEFAULT_TABLE),
        "srk_fuse": cst_dict.get("srk-fuse", secboot_cli.CST_SRK_DEFAULT_FUSE),
        "srk_no_ca": cst_dict.get("srk-no-ca-flag", False)
    }

    secboot_be.sign_bootloader_hab(
        kernel_key_dir=kernel_key_dir,
        kernel_key_name=kernel_key.get("name"),
        kernel_key_algo=kernel_key.get("algo", secboot_cli.KERNEL_KEY_DEFAULT_ALGO),
        cst_dir=cst_dir,
        cst_args=cst_args)

    if kernel_key:
        log.info(f"Public key '{kernel_key['name']}' in {kernel_key_dir} will be used by "
                 "the bootloader to verify the kernel signature.")
    else:
        log.warning("The bootloader DTBs were NOT updated with a new public key.")
        log.warning("If the kernel FIT image will be signed with a new key, please set "
                    "'kernel-key-dir' and 'kernel-key' and re-run the command so the new "
                    "kernel signature can be properly verified by the bootloader.")
        log.warning("Otherwise, this message can be ignored.")
    print()

    log.info("Bootloader in Torizon OS image signed successfully!")


def _parse_ostree_key(ostree_key_props, *, ostree_key_dir=None):
    """Parse the secboot.sign-kernel.ostree-key section."""

    assert "name" in ostree_key_props, "'ostree-key' requires 'name' property"
    key_name = ostree_key_props["name"]

    if "algo" not in ostree_key_props:
        log.info("Property 'algo' for ostree key '%s' has not been set; defaulting to '%s'.",
                 key_name, ostree_be.OSTreeKey.OSTREE_KEY_DEFAULT_ALGO)
    key_algo = ostree_key_props.get("algo", ostree_be.OSTreeKey.OSTREE_KEY_DEFAULT_ALGO)

    # Wrap key information into appropriate object:
    ostree_key_obj = ostree_be.OSTreeKey(
        key_dir=ostree_key_dir, key_name=key_name, key_algo=key_algo)

    return ostree_key_obj


def _sign_kernel_parse_ostree_key(ostree_key_dir, ostree_key_props, *, check_pubk=True):
    """Parse and validate the secboot.sign-kernel.ostree-key section.

    :param ostree_key_dir: OSTree keys directory; if None, the working directory is
        taken as default.
    :param ostree_key: Dict with contents of the section; None indicates the section
        was not provided as input.
    :param check_pubk: Whether or not to check the existence of the public key file.
    :returns: `OSTreeKey` object representing the key or None.
    """

    if ostree_key_dir and ostree_key_props is None:
        raise InvalidArgumentError(
            "Error: Property 'sign-kernel.ostree-key-dir' was set, but 'sign-kernel.ostree-key' "
            "was not provided. Aborting.")

    if not common.image_has_cfs_support():
        if ostree_key_props is not None:
            raise InvalidArgumentError(
                "Error: Property 'sign-kernel.ostree-key' has been set for an image that has "
                "no support for the root filesystem protection. Aborting.")

    if ostree_key_props is None:
        return None

    if ostree_key_dir is not None and not os.path.isdir(ostree_key_dir):
        raise PathNotExistError(
            f"Error: OSTree keys directory '{ostree_key_dir}' does not exist. Aborting.")

    ostree_key_dir = ostree_key_dir or "."
    ostree_key_obj = _parse_ostree_key(ostree_key_props, ostree_key_dir=ostree_key_dir)

    if check_pubk:
        pubk_file = ostree_key_obj.get_pub_key_path()
        if not os.path.isfile(pubk_file):
            raise PathNotExistError(
                f"Error: Cannot read public key file '{pubk_file}'.")

    return ostree_key_obj


def _handle_secboot_sign_kernel(sign_kernel_props):
    """Handle the secboot.sign-kernel section."""

    # ---
    # Collect/check the kernel-key related properties:
    # ---
    if len(sign_kernel_props["kernel-key"]) > 1:
        raise InvalidArgumentError(
            "TorizonCore Builder only supports signing the kernel FIT with one key. Aborting.")
    kernel_key = sign_kernel_props["kernel-key"][0]

    kernel_key_dir = sign_kernel_props.get("kernel-key-dir")
    if kernel_key_dir and not os.path.isdir(kernel_key_dir):
        raise InvalidArgumentError(
            f"Directory \"{kernel_key_dir}\" does not exist: aborting.")
    kernel_key_dir = kernel_key_dir or "."

    assert "name" in kernel_key, "'kernel-key' requires 'name' property"

    if "algo" not in kernel_key:
        log.info(f"Could not find value of 'algo' for key '{kernel_key['name']}'; "
                 f"defaulting to {secboot_cli.KERNEL_KEY_DEFAULT_ALGO}.")
    kernel_key_algo = kernel_key.get("algo", secboot_cli.KERNEL_KEY_DEFAULT_ALGO)

    # ---
    # Collect/check the ostree-key related properties:
    # ---
    ostree_key_ = sign_kernel_props.get("ostree-key")
    ostree_key_dir = sign_kernel_props.get("ostree-key-dir")
    ostree_key_obj = None

    if ostree_key_:
        if len(ostree_key_) > 1:
            raise InvalidArgumentError(
                "Error: Currently only one OSTree (public) key can be specified under the "
                "'sign-kernel.ostree-key' property.")

    ostree_key_obj = _sign_kernel_parse_ostree_key(
        ostree_key_dir, None if ostree_key_ is None else ostree_key_[0])

    kernel_changes_dir = kernel_be.get_kernel_changes_dir()
    if not os.path.isdir(kernel_changes_dir):
        os.mkdir(kernel_changes_dir)

    secboot_be.sign_kernel(
        kernel_changes_dir=kernel_changes_dir,
        key_dir=kernel_key_dir,
        key_algo=kernel_key_algo,
        key_name=kernel_key["name"],
        ostree_key=ostree_key_obj)


def handle_secboot_customization(props):
    """Handle the secure boot customization section."""

    common.images_unpack_executed()
    if common.unpacked_image_type() == "raw":
        raise InvalidDataError("TorizonCore Builder does not support signing components for "
                               "WIC/raw images. Aborting.")

    if "sign-bootloader-hab" in props:
        _handle_secboot_sign_bootloader_hab(props["sign-bootloader-hab"])

    if "sign-kernel" in props:
        _handle_secboot_sign_kernel(props["sign-kernel"])

    # NOTE: The "sign-ostree" section is not actually handled with the rest of the
    #       customization section but rather together with the output section.


def _union_parse_ostree_key(ostree_key_dir, ostree_key_props, *,
                            check_seck=True, check_pubk=True):
    """Parse and validate the secboot.sign-ostree.ostree-key section.

    :param ostree_key_dir: OSTree keys directory; if None, the working directory is
        taken as default.
    :param ostree_key: Dict with contents of the section; None indicates the section
        was not provided as input.
    :param check_seck: Whether or not to check the existence of the private key file.
    :param check_pubk: Whether or not to check the existence of the public key file.
    :returns: `OSTreeKey` object representing the key or None.
    """

    if ostree_key_dir and ostree_key_props is None:
        raise InvalidArgumentError(
            "Error: Property 'sign-ostree.ostree-key-dir' was set but 'sign-ostree.ostree-key' "
            "was not provided. Aborting.")

    if common.image_has_cfs_support():
        if ostree_key_props is None:
            # Abort the operation to avoid producing non-bootable images.
            raise InvalidArgumentError(
                "Error: The image has support for the root filesystem protection, but the "
                "'sign-ostree.ostree-key' property has not been set; the property is required "
                "for signing the commit.")
    else:
        if ostree_key_props is not None:
            raise InvalidArgumentError(
                "Error: Property 'sign-ostree.ostree-key' has been set for an image that has "
                "no support for the root filesystem protection. Aborting.")

    if ostree_key_props is None:
        return None

    if ostree_key_dir is not None and not os.path.isdir(ostree_key_dir):
        raise PathNotExistError(
            f"Error: OSTree keys directory '{ostree_key_dir}' does not exist. Aborting.")

    ostree_key_dir = ostree_key_dir or "."
    ostree_key_obj = _parse_ostree_key(ostree_key_props, ostree_key_dir=ostree_key_dir)

    if check_seck:
        seck_file = ostree_key_obj.get_sec_key_path()
        if not os.path.isfile(seck_file):
            raise PathNotExistError(
                f"Error: Cannot read secret key file '{seck_file}'.")

    if check_pubk:
        pubk_file = ostree_key_obj.get_pub_key_path()
        if not os.path.isfile(pubk_file):
            raise PathNotExistError(
                f"Error: Cannot read public key file '{pubk_file}'.")

    return ostree_key_obj


def handle_output_section(props, changes_dirs=None, default_base_raw_image=None,
                          sign_type=None):
    """Handle the output section of the configuration file

    :param props: Dictionary holding the data of the section.
    :param changes_dirs: Directories containing filesystem changes to apply.
    :param default_base_raw_image: Default base raw image. Should always be the
                                   input raw image. If dealing with tezi images,
                                   this value is equal to 'None'.
    :param sign_type: Secure-boot signing technology being used.
    """

    if props:
        log.info(l1_pref("Handling output section"))

    # ostree data is currently optional.
    ostree_props = props.get("ostree", {})

    # Parameters to pass to union()
    union_params = {
        "changes_dirs": changes_dirs
    }

    if "branch" in ostree_props:
        union_params["union_branch"] = ostree_props["branch"]
    else:
        # Create a default branch name based on date/time.
        nowstr = datetime.now().strftime("%Y%m%d%H%M%S")
        union_params["union_branch"] = f"tcbuilder-{nowstr}"

    if "commit-subject" in ostree_props:
        union_params["commit_subject"] = ostree_props["commit-subject"]
    if "commit-body" in ostree_props:
        union_params["commit_body"] = ostree_props["commit-body"]

    # NB: "sign-ostree" is entered by the user as a "customization" property, but
    #     it is copied to "output.ostree".
    if "sign-ostree" in ostree_props:
        sign_ostree_props = ostree_props["sign-ostree"]
    else:
        sign_ostree_props = {}

    # Collect/check the ostree-key related properties:
    ostree_key_ = sign_ostree_props.get("ostree-key")
    ostree_key_dir = sign_ostree_props.get("ostree-key-dir")
    ostree_key_obj = None
    if ostree_key_:
        if len(ostree_key_) > 1:
            raise InvalidArgumentError(
                "Error: Currently only one OSTree (private) key can be specified under "
                "the 'sign-ostree.ostree-key' property.")
    ostree_key_obj = _union_parse_ostree_key(
        ostree_key_dir, None if ostree_key_ is None else ostree_key_[0])

    union_params["ostree_key_obj"] = ostree_key_obj

    # TODO: Refactor union() by moving all non-CLI code to backend; then the API from the backend.
    union_cli.union(**union_params)

    # Handle the "output.ostree.local" property (TODO).
    # Handle the "output.ostree.remote" property (TODO).

    if common.unpacked_image_type() == "tezi":
        tezi_props = props.get("easy-installer", {})
        handle_easy_installer_output(tezi_props, union_params, sign_type)
    else:
        raw_props = props.get("raw-image", {})
        handle_raw_image_output(raw_props, union_params, default_base_raw_image)


def handle_raw_image_output(props, union_params, default_base_raw_image):
    """Handle the output/raw-image section of the configuration file

    :param props: Dictionary holding the data of the section.
    :param union_params: Parameters related to union(). This is a required arg.
    :param default_base_raw_image: Path of default base raw image. Should always
                                   be the input image.
    """

    # Note that the following test should never fail (due to schema validation).
    assert "local" in props, "'local' property is required"

    # Ensure that this test never fails.
    assert default_base_raw_image is not None, "Base raw image has no default value."

    output_raw_img = props["local"]
    if os.path.isabs(output_raw_img):
        raise InvalidDataError(
            f"Image output file '{output_raw_img}' is not relative")
    output_raw_img = os.path.abspath(output_raw_img)

    base_raw_img = props.get("base-image", default_base_raw_image)
    base_rootfs_label = props.get("base-rootfs-label", common.DEFAULT_RAW_ROOTFS_LABEL)
    base_sector_size = props.get("base-sector-size", common.DEFAULT_RAW_SECTOR_SIZE)

    deploy_raw_image_params = {
        "ostree_ref": union_params["union_branch"],
        "base_raw_img": base_raw_img,
        "output_raw_img": output_raw_img,
        "deploy_sysroot_dir": deploy_cli.DEFAULT_DEPLOY_DIR,
        "rootfs_label": base_rootfs_label,
        "sector_size": base_sector_size,
    }

    deploy_cli.deploy_raw_image(**deploy_raw_image_params)

    handle_raw_image_bundle_output(
        output_raw_img, output_raw_img, props.get("bundle", {}), props)
    common.set_output_ownership(output_raw_img)

    if "provisioning" in props:
        handle_provisioning(output_raw_img, props.get("provisioning"), base_rootfs_label,
                             base_sector_size)


def handle_easy_installer_output(props, union_params, sign_type=None):
    """Handle the output/easy-installer section of the configuration file

    :param props: Dictionary holding the data of the section.
    :param union_params: Parameters related to union(). This is a required arg.
    :param sign_type: Secure-boot technology being used.
    """

    # Note that the following test should never fail (due to schema validation).
    assert "local" in props, "'local' property is required"

    output_dir = props["local"]
    if os.path.isabs(output_dir):
        raise InvalidDataError(
            f"Image output directory '{output_dir}' is not relative")
    output_dir = os.path.abspath(output_dir)

    deploy_tezi_image_params = {
        "ostree_ref": union_params["union_branch"],
        "output_dir": output_dir,
        "deploy_sysroot_dir": deploy_cli.DEFAULT_DEPLOY_DIR,
        "tezi_props": translate_tezi_props(props),
    }

    deploy_cli.deploy_tezi_image(**deploy_tezi_image_params)

    handle_bundle_output(output_dir, props.get("bundle", {}), props)

    if "provisioning" in props:
        handle_provisioning(output_dir, props.get("provisioning"))

    if "fusing" in props:
        handle_fusing(output_dir, props.get("fusing"), sign_type)


def handle_bundle_common(bundle_props, compress_tar=True):
    """Handle the common steps of the bundle and combine for output generation.

    :param bundle_props: Dictionary holding the data of the bundle section.
    :param compress_tar: Optional argument that specifies if the docker bundle
                         tarfile should be compressed or not. Only applies if
                         using 'compose-file'. It is ignored when using 'dir'.
    :returns:
        bundle_dir: Bundle directory path as a string, or None if bundling fails.
        is_tmp_dir: Boolean that indicates if bundle_dir is a temporary directory or not.
    """

    if "dir" in bundle_props:
        bundle_dir = bundle_props["dir"]
        if os.path.exists(bundle_dir):
            return bundle_dir, False
        raise TorizonCoreBuilderError(f"No such directory: {bundle_dir}")

    if "compose-file" in bundle_props:
        # Download bundle to user's directory - review (TODO).
        # Avoid polluting user's directory with certificate stuff (TODO).
        # Complain if variant is not "torizon-core-docker" (TODO)?

        if "platform" in bundle_props:
            platform = bundle_props["platform"]
        else:
            # Detect platform based on OSTree data.
            platform = common.get_docker_platform()

        bundle_dir = datetime.now().strftime("bundle_%Y%m%d%H%M%S_%f.tmp")
        log.info(f"Bundling images to directory {bundle_dir}")
        try:
            # Download bundle to temporary directory - currently that directory
            # must be relative to the work directory.
            logins = []
            if bundle_props.get("registry") and bundle_props.get("username"):
                logins = [(bundle_props.get("registry"),
                           bundle_props.get("username"),
                           bundle_props.get("password", ""))]
            elif bundle_props.get("username"):
                logins = [(bundle_props.get("username"),
                           bundle_props.get("password", ""))]

            RegistryOperations.set_logins(logins)

            # CA Certificate of registry
            if bundle_props.get("registry") and bundle_props.get("ca-certificate"):
                cacerts = [[bundle_props.get("registry"),
                            bundle_props.get("ca-certificate")]]
                RegistryOperations.set_cacerts(cacerts)

            download_params = {
                "output_dir": bundle_dir,
                "compose_file": bundle_props["compose-file"],
                "host_workdir": common.get_host_workdir()[0],
                "use_host_docker": False,
                "output_filename": f"{common.DOCKER_BUNDLE_TARNAME}.xz" if compress_tar
                                   else common.DOCKER_BUNDLE_TARNAME,
                "keep_double_dollar_sign": bundle_props.get("keep-double-dollar-sign", False),
                "platform": platform,
                "dind_params": bundle_props.get("dind-params"),
                "dind_env": parse_env_assignments(bundle_props.get("dind-env")),
            }
            download_containers_by_compose_file(**download_params)

            return bundle_dir, True

        except:
            # pylint: disable-next=raise-missing-from
            raise TorizonCoreBuilderError("Error trying to bundle Docker containers")

    return None, False


def handle_bundle_output(image_dir, bundle_props, tezi_props):
    """Handle the bundle and combine steps of the output generation."""

    bundle_dir = None
    is_tmp_dir = None
    try:
        bundle_dir, is_tmp_dir = handle_bundle_common(bundle_props)

        if bundle_dir is None:
            return

        # Do a combine "in place" to avoid creating another directory.
        combine_params = {
            "image_dir": image_dir,
            "bundle_dir": bundle_dir,
            "output_directory": None,
            "tezi_props": translate_tezi_props(tezi_props),
            "force": True
        }
        comb_be.combine_tezi_image(**combine_params)

    finally:
        if bundle_dir is not None and is_tmp_dir:
            log.debug(f"Removing temporary bundle directory {bundle_dir}")
            shutil.rmtree(bundle_dir)


def handle_raw_image_bundle_output(image_dir, raw_image_path, bundle_props, raw_props):
    """Handle the bundle and combine steps of the output generation."""

    bundle_dir = None
    is_tmp_dir = None
    try:
        bundle_dir, is_tmp_dir = handle_bundle_common(bundle_props, compress_tar=False)
        if bundle_dir is None:
            return

        # do the combine
        combine_params = {
            "image_path": raw_image_path,
            "bundle_dir": bundle_dir,
            "output_path": image_dir,
            "rootfs_label": raw_props.get(
                "rootfs-label",
                common.DEFAULT_RAW_ROOTFS_LABEL
            ),
            "force": True,
            "sector_size": raw_props.get(
                "base-sector-size",
                common.DEFAULT_RAW_SECTOR_SIZE
            )
        }
        comb_be.combine_raw_image(**combine_params)

    finally:
        if bundle_dir is not None:
            if is_tmp_dir:
                log.debug(f"Removing temporary bundle directory {bundle_dir}")
                shutil.rmtree(bundle_dir)
            else:
                docker_storage_dir_path = os.path.join(bundle_dir, comb_be.DOCKER_STORAGE_DIRNAME)
                if os.path.isdir(docker_storage_dir_path):
                    log.debug("Deleting '%s'", docker_storage_dir_path)
                    shutil.rmtree(docker_storage_dir_path)


def handle_provisioning(output_dir, prov_props, rootfs_label=None, sector_size=None):
    """Handle the provisioning step of the output generation."""

    prov_data = {
        "shared": prov_props.get("shared-data"),
        "online": prov_props.get("online-data")
    }

    prov_params = {
        "input_path": output_dir,
        "output_path": None,
        "prov_data": prov_data,
        "rootfs_label": rootfs_label,
        "sector_size": sector_size or common.DEFAULT_RAW_SECTOR_SIZE,
        "hibernated": prov_props.get("hibernated", False),
        "fleets": prov_props.get("fleets")
    }

    if prov_props.get("mode") == images_cli.PROV_MODE_OFFLINE:
        if not prov_data["shared"]:
            raise InvalidDataError(
                "With offline provisioning, property 'shared-data' must be set.")
        if prov_data["online"]:
            raise InvalidDataError(
                "With offline provisioning, property 'online-data' cannot be set.")
    elif prov_props.get("mode") == images_cli.PROV_MODE_ONLINE:
        if not (prov_data["shared"] and prov_data["online"]):
            raise InvalidDataError(
                "With online provisioning, properties 'shared-data' "
                "and 'online-data' must be set.")
    elif prov_props.get("mode") == "disabled":
        # Provide a "disabled" mode so people can disable provisioning without having to
        # remove the properties (comment them out) from the file.
        return
    else:
        raise InvalidDataError("Provisioning 'mode' not correctly set")

    images_be.provision(**prov_params)


def handle_fusing(output_dir, fuse_props, sign_type=None):
    """Handle the fusing step of the output generation."""

    # Check to make sure re-signing of bootloader was done earlier
    if sign_type is None:
        raise InvalidStateError("To do 'fusing', 'sign-bootloader-hab' must be defined "
                                "at the same time.")

    _do_fuse = fuse_props.get("auto-programming", False)
    _do_file = fuse_props.get("fuse-file")

    if not _do_fuse and not _do_file:
        log.info(l2_pref("Neither 'auto-programming' or 'fuse-file' specified "
                         "skipping 'fusing' section"))
        return

    fuse_file = None
    try:
        fuse_file = ubootenv_be.generate_fuse_file(fuse_props.get("close-device"), output_dir)

        if _do_fuse:
            log.info(l2_pref("Adding automatic secure fuse programming to image."))
            ubootenv_params = {
                "input_dir": output_dir,
                "output_dir": output_dir,
                "fuse_file": fuse_file,
                "force": True,
            }
            ubootenv_be.env_fuses(**ubootenv_params)

        if _do_file:
            log.info(l2_pref(f"Creating fuse-file '{fuse_props['fuse-file']}'."))
            output_root = os.path.realpath(output_dir)
            fuse_output = os.path.realpath(os.path.join(output_root, _do_file))
            if (fuse_output == output_root or
                    os.path.commonpath((output_root, fuse_output)) != output_root):
                raise InvalidDataError("'fuse-file' must be inside the output directory.")
            shutil.copy(fuse_file, fuse_output)
            os.chmod(fuse_output, 0o644)
            common.set_output_ownership(fuse_output)
    finally:
        if fuse_file and os.path.exists(fuse_file):
            os.remove(fuse_file)


def _build_setup(config, force):
    """Do some sanity checks and prepare for handling the build operations."""

    output_dir = None
    output_image = None

    if "input" not in config:
        # Note that is also checked by the schema.
        raise FileContentMissing("No input specified in configuration file")

    if "output" not in config:
        # Note that is also checked by the schema.
        raise FileContentMissing("No output specified in configuration file")

    if "easy-installer" in config["input"]:
        if "easy-installer" not in config["output"]:
            raise InvalidStateError(
                "Input is 'easy-installer', but couldn't find 'easy-installer' in output "
                "section. Aborting.")

        # Check if output directory already exists and fail if it does.
        output_dir = config["output"]["easy-installer"]["local"]
        if os.path.exists(output_dir):
            if force:
                log.debug("Removing existing output directory '%s'.", output_dir)
                shutil.rmtree(output_dir)
            else:
                raise InvalidStateError(
                    f"Output directory '{output_dir}' already exists; please remove it or "
                    "select another output directory.")

    elif "raw-image" in config["input"]:
        if "raw-image" not in config["output"]:
            raise InvalidStateError(
                "Input is 'raw-image', but couldn't find 'raw-image' in output section. "
                "Aborting.")

        # Check if output file already exists and fail if it does.
        output_image = config["output"]["raw-image"]["local"]
        if os.path.exists(output_image):
            if force:
                if os.path.isfile(output_image):
                    log.debug("Removing existing file '%s'.", output_image)
                    os.remove(output_image)
                else:
                    raise InvalidStateError(
                        f"'{output_image}' is not a valid path to a file. Aborting.")
            else:
                raise InvalidStateError(
                    f"File '{output_image}' already exists; please remove it or give a "
                    "different filename for the output.")

    return output_dir, output_image


def build(config_fname, *, substs=None, enable_subst=True, force=False):
    """Main handler for the normal operating mode of the build subcommand"""

    log.info(f"Building image as per configuration file '{config_fname}'...")
    log.debug(f"Substitutions ({['disabled', 'enabled'][enable_subst]}): "
              f"{substs}")

    config = bb.parse_config_file(config_fname, substs=(substs if enable_subst else None))

    # Do some sanity checks and select output.
    output_dir, output_image = _build_setup(config, force)

    # Special handling for OSTree signing:
    # Copy "customization.secboot.sign-ostree" as a child of "output.ostree".
    try:
        _sign_ostree = config["customization"]["secboot"]["sign-ostree"]
        if "ostree" not in config["output"]:
            config["output"]["ostree"] = {}
        config["output"]["ostree"]["sign-ostree"] = _sign_ostree
    except KeyError as _exc:
        pass

    # Track whether bootloader re-signing is being done for auto-fusing
    _sign_type = None
    try:
        if "sign-bootloader-hab" in config["customization"]["secboot"]:
            _sign_type = "hab"
        # TODO: Once ahab devices are supported with re-signing
        #elif "sign-bootloader-ahab" in config["customization"]["secboot"]:
        #    _sign_type = "ahab"
    except KeyError as _exc:
        pass

    # ---
    # Handle each section.
    # ---

    # Input section (required):
    base_raw_image = handle_input_section(config["input"])

    # Customization section (currently optional).
    fs_changes = handle_customization_section(config.get("customization", {}))

    # Output section (required):
    try:
        handle_output_section(
            config["output"],
            changes_dirs=fs_changes,
            default_base_raw_image=base_raw_image,
            sign_type=_sign_type)

    except Exception as exc:
        # Avoid leaving a damaged output around:
        # TODO: Maybe it would be best to catch BaseException here so even
        #       keyboard interrupts are handled.
        if "easy-installer" in config["output"] and os.path.exists(output_dir):
            log.info(f"Removing output directory '{output_dir}' due to build errors")
            shutil.rmtree(output_dir)
        elif "raw-image" in config["output"] and os.path.exists(output_image):
            log.info(f"Removing output file '{output_image}' due to build errors")
            os.remove(output_image)
        raise exc

    log.info(l1_pref("Build command successfully executed!"))


def do_build(args):
    """Wrapper of the build command that unpacks argparse arguments"""

    try:
        if args.create_template:
            # Template creating mode.
            create_template(args.config_fname, force=args.force)
        else:
            # Normal build mode.
            build(args.config_fname,
                  substs=bb.parse_assignments(args.assignments),
                  enable_subst=args.enable_substitutions,
                  force=args.force)

    except UserFailureException as exc:
        log.warning(f"\n** Exiting due to user-defined error: {str(exc)}")
        sys.exit(1)

    except ParseError as exc:
        log.warning(l2_pref("Parsing errors found:"))
        log.warning(f"{str(exc)}")
        sys.exit(2)

    except ParseErrors as exc:
        log.warning(l2_pref("Parsing errors found:"))
        assert isinstance(exc.payload, list)
        for error in exc.payload:
            log.warning(str(error))
        sys.exit(2)

    except LicenceAcceptanceError as exc:
        log.warning(f"{str(exc)}")
        sys.exit(3)

    except (TorizonCoreBuilderError, TeziError) as exc:
        if exc.msg and not exc.msg.lower().startswith("error:"):
            exc.msg = "Error: " + exc.msg
        raise exc


def init_parser(subparsers):
    """Initialize "build" subcommands command line interface."""

    parser = subparsers.add_parser(
        "build",
        help=("Customize a Toradex Easy Installer image based on settings "
              "specified via a configuration file."),
        allow_abbrev=False)

    parser.add_argument(
        "--create-template", dest="create_template",
        default=False, action="store_true",
        help=("Request that a template file be generated with the name "
              "defined by --file; dump to standard output if file name is set "
              "to '-'."))

    parser.add_argument(
        "--file", metavar="CONFIG", dest="config_fname",
        default=DEFAULT_BUILD_FILE,
        help=("Specify location of the build configuration file "
              f"(default: {DEFAULT_BUILD_FILE})."))

    parser.add_argument(
        "--force", dest="force",
        default=False, action="store_true",
        help=("Force program output (remove output directory before "
              "starting the build process)."))

    parser.add_argument(
        "--set", metavar="ASSIGNMENT", dest="assignments",
        default=[], action="append",
        help=("Assign values to variables (e.g. VER=\"1.2.3\"). This can "
              "be used multiple times."))

    parser.add_argument(
        "--no-subst", dest="enable_substitutions",
        default=True, action="store_false",
        help="Disable the variable substitution feature.")

    parser.set_defaults(func=do_build)
