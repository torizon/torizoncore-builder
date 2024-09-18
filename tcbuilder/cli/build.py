"""
CLI handling for build subcommand
"""

import os
import logging
import shutil
import sys
from datetime import datetime

from tezi.errors import TeziError
from tcbuilder.backend.bundle import download_containers_by_compose_file
from tcbuilder.backend.expandvars import UserFailureException
from tcbuilder.backend.registryops import RegistryOperations
from tcbuilder.errors import (
    FileContentMissing, FeatureNotImplementedError, InvalidDataError,
    InvalidStateError, LicenceAcceptanceError, TorizonCoreBuilderError,
    ParseError, ParseErrors)

from tcbuilder.backend import common
from tcbuilder.backend import build as bb
from tcbuilder.backend import combine as comb_be
from tcbuilder.backend import dt as dt_be
from tcbuilder.backend import images as images_be
from tcbuilder.cli import deploy as deploy_cli
from tcbuilder.cli import dt as dt_cli
from tcbuilder.cli import dto as dto_cli
from tcbuilder.cli import kernel as kernel_cli
from tcbuilder.cli import images as images_cli
from tcbuilder.cli import splash as splash_cli
from tcbuilder.cli import union as union_cli

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
        with open(src_file, 'r') as file:
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
    """

    if props:
        log.info(l1_pref("Handling input section"))

    if "easy-installer" in props:
        handle_easy_installer_input(props["easy-installer"], **kwargs)
    elif "ostree" in props:
        handle_ostree_input(props["ostree"], **kwargs)
    elif "raw-image" in props:
        handle_raw_image_input(props["raw-image"], **kwargs)
    else:
        raise FileContentMissing(
            "No kind of input specified in configuration file")


def handle_easy_installer_input(props, storage_dir=None, download_dir=None):
    """Handle the input/easy-installer subsection of the configuration file

    :param props: Dictionary holding the data of the subsection.
    :param storage_dir: Absolute path of storage directory. This is a required
                        keyword argument.
    :param download_dir: Directory where files should be downloaded to or
                         obtained from if they already exist (TODO).
    """

    assert storage_dir is not None, "Parameter `storage_dir` must be passed"

    if "local" in props:
        images_cli.images_unpack(
            props["local"], storage_dir, remove_storage=True)

    elif ("remote" in props) or ("toradex-feed" in props):
        if "toradex-feed" in props:
            # Evaluate if it makes sense to supply a checksum here too (TODO).
            remote_url, remote_fname = bb.make_feed_url(props["toradex-feed"])
            cksum = None
        else:
            # Parse remote which may contain integrity checking information.
            remote_url, remote_fname, cksum = bb.parse_remote(props["remote"])
            log.debug(f"Remote URL: {remote_url}, name: {remote_fname}, "
                      f"expected sha256: {cksum}")

        # Next call will download the file if necessary (TODO).
        local_file, is_temp = \
            bb.fetch_remote(remote_url, remote_fname, cksum, download_dir)

        try:
            images_cli.images_unpack(local_file, storage_dir, remove_storage=True)
        finally:
            # Avoid leaving files in the temporary directory (if it was used).
            if is_temp:
                os.unlink(local_file)

    else:
        raise FileContentMissing(
            "No known input type specified in configuration file")

def handle_raw_image_input(props, storage_dir=None):
    """Handle the input/raw-image subsection of the configuration file

    :param props: Dictionary holding the data of the subsection.
    :param storage_dir: Absolute path of storage directory. This is a required
                        keyword argument.
    """

    assert storage_dir is not None, "Parameter `storage_dir` must be passed"

    if "local" in props:
        images_cli.images_unpack(
            props["local"],
            storage_dir,
            raw_rootfs_label=props.get("rootfs-label", common.DEFAULT_RAW_ROOTFS_LABEL),
            remove_storage=True)
    else:
        raise FileContentMissing(
            "No known input type specified in configuration file")

def handle_ostree_input(props, **kwargs):
    """Handle the input/easy-installer subsection of the configuration file"""
    raise FeatureNotImplementedError(
        "Processing of ostree archive inputs is not implemented yet.")


def handle_customization_section(props, storage_dir=None):
    """Handle the customization section of the configuration file

    :param props: Dictionary holding the data of the section.
    :param storage_dir: Absolute path of storage directory. This is a required
                        keyword argument.
    """

    if props:
        log.info(l1_pref("Handling customization section"))

    assert storage_dir is not None, "Parameter `storage_dir` must be passed"

    if "splash-screen" in props:
        log.info(l2_pref("Setting splash screen"))
        splash_cli.splash(props["splash-screen"], storage_dir=storage_dir)

    if "device-tree" in props:
        handle_dt_customization(props["device-tree"], storage_dir=storage_dir)

    if "kernel" in props:
        handle_kernel_customization(props["kernel"], storage_dir=storage_dir)

    # Filesystem changes are actually handled as part of the output processing.
    fs_changes = props.get("filesystem")

    return fs_changes


def handle_dt_customization(props, storage_dir=None):
    """Handle the device-tree customization section."""

    if props:
        log.info(l2_pref("Handling device-tree subsection"))

    if "custom" in props:
        log.info(l2_pref(f"Selecting custom device-tree '{props['custom']}'"))
        dt_cli.dt_apply(dts_path=props["custom"],
                        storage_dir=storage_dir,
                        include_dirs=props.get("include-dirs", []))

    overlay_props = props.get("overlays", {})
    if overlay_props.get("clear", False):
        dto_cli.dto_remove_all(storage_dir)

        if "remove" in overlay_props:
            log.info("Individual overlay removal ignored because they've all been "
                     "removed due to the 'clear' property")

    elif "remove" in overlay_props:
        for overl in overlay_props["remove"]:
            dto_cli.dto_remove_single(overl, storage_dir, presence_required=False)

    if "add" in overlay_props:
        # We enable the overlay apply test only if it is possible to do it.
        test_apply = bool(dt_be.get_current_dtb_basename(storage_dir))
        if not test_apply:
            log.info("Not testing overlay because base image does not have a "
                     "device-tree set!")
        for overl in overlay_props["add"]:
            log.info(l2_pref(f"Adding device-tree overlay '{overl}'"))
            dto_cli.dto_apply(
                dtos_path=overl,
                dtb_path=None,
                include_dirs=props.get("include-dirs", []),
                storage_dir=storage_dir,
                allow_reapply=False,
                test_apply=test_apply)


def handle_kernel_customization(props, storage_dir=None):
    """Handle the kernel customization section."""

    if "modules" in props:
        for mod_props in props["modules"]:
            mod_source = mod_props["source-dir"]
            log.info(l2_pref(f"Building module located at '{mod_source}'"))
            kernel_cli.kernel_build_module(
                source_dir=mod_source,
                storage_dir=storage_dir,
                autoload=mod_props.get("autoload", False))

    if "arguments" in props:
        log.info(l2_pref("Setting kernel arguments"))
        kernel_cli.kernel_set_custom_args(
            kernel_args=props["arguments"],
            storage_dir=storage_dir)


def handle_output_section(props, storage_dir, changes_dirs=None, default_base_raw_image=None):
    """Handle the output section of the configuration file

    :param props: Dictionary holding the data of the section.
    :param storage_dir: Absolute path of storage directory. This is a required
                        keyword argument.
    :param changes_dirs: Directories containing filesystem changes to apply.
    :param default_base_raw_image: Default base raw image. Should always be the
                                   input raw image. If dealing with tezi images,
                                   this value is equal to 'None'.
    """

    if props:
        log.info(l1_pref("Handling output section"))

    # ostree data is currently optional.
    ostree_props = props.get("ostree", {})

    # Parameters to pass to union()
    union_params = {
        "storage_dir": storage_dir,
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

    union_cli.union(**union_params)

    # Handle the "output.ostree.local" property (TODO).
    # Handle the "output.ostree.remote" property (TODO).

    if common.unpacked_image_type(storage_dir) == "tezi":
        tezi_props = props.get("easy-installer", {})
        handle_easy_installer_output(tezi_props, storage_dir, union_params)
    else:
        raw_props = props.get("raw-image", {})
        handle_raw_image_output(raw_props, storage_dir, union_params, default_base_raw_image)


def handle_raw_image_output(props, storage_dir, union_params, default_base_raw_image):
    """Handle the output/raw-image section of the configuration file

    :param props: Dictionary holding the data of the section.
    :param storage_dir: Absolute path of storage directory. This is a required
                        keyword argument.
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

    deploy_raw_image_params = {
        "ostree_ref": union_params["union_branch"],
        "base_raw_img": base_raw_img,
        "output_raw_img": output_raw_img,
        "storage_dir": storage_dir,
        "deploy_sysroot_dir": deploy_cli.DEFAULT_DEPLOY_DIR,
        "rootfs_label": base_rootfs_label,
    }

    deploy_cli.deploy_raw_image(**deploy_raw_image_params)


def handle_easy_installer_output(props, storage_dir, union_params):
    """Handle the output/easy-installer section of the configuration file

    :param props: Dictionary holding the data of the section.
    :param storage_dir: Absolute path of storage directory. This is a required
                        keyword argument.
    :param union_params: Parameters related to union(). This is a required arg.
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
        "storage_dir": storage_dir,
        "deploy_sysroot_dir": deploy_cli.DEFAULT_DEPLOY_DIR,
        "tezi_props": translate_tezi_props(props),
    }

    deploy_cli.deploy_tezi_image(**deploy_tezi_image_params)

    handle_bundle_output(
        output_dir, storage_dir, props.get("bundle", {}), props)

    if "provisioning" in props:
        handle_provisioning(output_dir, props.get("provisioning"))


def handle_bundle_output(image_dir, storage_dir, bundle_props, tezi_props):
    """Handle the bundle and combine steps of the output generation."""

    if "dir" in bundle_props:
        # Do a combine "in place" to avoid creating another directory.
        combine_params = {
            "image_dir": image_dir,
            "bundle_dir": bundle_props["dir"],
            "output_directory": None,
            "tezi_props": translate_tezi_props(tezi_props),
            "force": True
        }
        comb_be.combine_tezi_image(**combine_params)

    elif "compose-file" in bundle_props:
        # Download bundle to user's directory - review (TODO).
        # Avoid polluting user's directory with certificate stuff (TODO).
        # Complain if variant is not "torizon-core-docker" (TODO)?

        if "platform" in bundle_props:
            platform = bundle_props["platform"]
        else:
            # Detect platform based on OSTree data.
            platform = common.get_docker_platform(storage_dir)

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
                "output_filename": common.DOCKER_BUNDLE_FILENAME,
                "keep_double_dollar_sign": bundle_props.get("keep-double-dollar-sign", False),
                "platform": platform
            }
            download_containers_by_compose_file(**download_params)

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
            log.debug(f"Removing temporary bundle directory {bundle_dir}")
            if os.path.exists(bundle_dir):
                shutil.rmtree(bundle_dir)


def handle_provisioning(output_dir, prov_props):
    """Handle the provisioning step of the output generation."""

    prov_params = {
        "input_dir": output_dir,
        "output_dir": None,
        "shared_data": prov_props.get("shared-data"),
        "online_data": prov_props.get("online-data"),
        "hibernated": prov_props.get("hibernated", False)
    }

    if prov_props.get("mode") == images_cli.PROV_MODE_OFFLINE:
        if not prov_params["shared_data"]:
            raise InvalidDataError(
                "With offline provisioning, property 'shared-data' must be set.")
        if prov_params["online_data"]:
            raise InvalidDataError(
                "With offline provisioning, property 'online-data' cannot be set.")
    elif prov_props.get("mode") == images_cli.PROV_MODE_ONLINE:
        if not (prov_params["shared_data"] and prov_params["online_data"]):
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


def build(config_fname, storage_dir,
          substs=None, enable_subst=True, force=False):
    """Main handler for the normal operating mode of the build subcommand"""

    log.info(f"Building image as per configuration file '{config_fname}'...")
    log.debug(f"Substitutions ({['disabled', 'enabled'][enable_subst]}): "
              f"{substs}")

    config = bb.parse_config_file(config_fname, substs=(substs if enable_subst else None))

    # ---
    # Handle each section.
    # ---
    if "input" not in config:
        # Note that is also checked by the schema.
        raise FileContentMissing("No input specified in configuration file")

    if "output" not in config:
        # Note that is also checked by the schema.
        raise FileContentMissing("No output specified in configuration file")

    if "easy-installer" in config["input"]:

        if "easy-installer" not in config["output"]:
            raise InvalidStateError(
                "Input is 'easy-installer', but couldn't find"
                " 'easy-installer' in output section. Aborting.")

        # Check if output directory already exists and fail if it does.
        output_dir = config["output"]["easy-installer"]["local"]
        if os.path.exists(output_dir):
            if force:
                log.debug(f"Removing existing output directory '{output_dir}'")
                shutil.rmtree(output_dir)
            else:
                raise InvalidStateError(
                    f"Output directory '{output_dir}' already exists; please remove"
                    " it or select another output directory.")

    elif "raw-image" in config["input"]:

        if "raw-image" not in config["output"]:
            raise InvalidStateError(
                "Input is 'raw-image', but couldn't find"
                " 'raw-image' in output section. Aborting.")

        # Check if output file already exists and fail if it does.
        output_image = config["output"]["raw-image"]["local"]
        if os.path.exists(output_image):
            if force:
                if os.path.isfile(output_image):
                    log.debug(f"Removing existing file '{output_image}'")
                    os.remove(output_image)
                else:
                    raise InvalidStateError(
                        f"'{output_image}' is not a valid path to a file. Aborting.")
            else:
                raise InvalidStateError(
                    f"File '{output_image}' already exists; please remove"
                    " it or give a different filename for the output.")

    # Input section (required):
    handle_input_section(config["input"], storage_dir=storage_dir)

    # Customization section (currently optional).
    fs_changes = handle_customization_section(
        config.get("customization", {}), storage_dir=storage_dir)


    default_base_raw_image = (
        config["input"]["raw-image"]["local"] if "raw-image" in config["input"] else None)
    # Output section (required):
    try:
        handle_output_section(
            config["output"],
            storage_dir=storage_dir, changes_dirs=fs_changes,
            default_base_raw_image=default_base_raw_image)

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
            build(args.config_fname, args.storage_directory,
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
