"""
CLI handling for build subcommand
"""

import logging
import os
from datetime import datetime

# import dockerbundle

from tcbuilder.errors import (FileContentMissing,
                              FeatureNotImplementedError, InvalidDataError)

from tcbuilder.backend import build as bb
from tcbuilder.backend import combine as comb_be
from tcbuilder.cli import images as images_cli
from tcbuilder.cli import union as union_cli
from tcbuilder.cli import deploy as deploy_cli

DEFAULT_BUILD_FILE = "tcbuild.yaml"

log = logging.getLogger("torizon." + __name__)


def create_template(config_fname):
    """Main handler for the create-template mode of the build subcommand"""

    print(f"Generating '{config_fname}' (not yet implemented)")


def handle_input_section(props, **kwargs):
    """Handle the input section of the configuration file

    :param props: Dictionary holding the data of the section.
    :param kwargs: Keyword arguments that are forwarded to the handling
                   functions of the subsections.
    """

    if "easy-installer" in props:
        handle_easy_installer_input(props["easy-installer"], **kwargs)
    elif "ostree" in props:
        handle_ostree_input(props["ostree"], **kwargs)
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

    log.debug(f"Handling easy-installer section: {str(props)}")

    assert storage_dir is not None, "Parameter `storage_dir` must be passed"

    if "local" in props:
        images_cli.images_unpack(
            props["local"], storage_dir, remove_storage=True)

    elif ("remote" in props) or ("toradex-feed" in props):
        # Review the `toradex-feed` docs (TODO)
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


def handle_ostree_input(props, **kwargs):
    """Handle the input/easy-installer subsection of the configuration file"""
    raise FeatureNotImplementedError(
        "Processing of ostree archive inputs is not implemented yet.")


def handle_output_section(props, storage_dir, extra_changes_dirs=None):
    """Handle the output section of the configuration file

    :param props: Dictionary holding the data of the section.
    :param storage_dir: Absolute path of storage directory. This is a required
                        keyword argument.
    """

    # ostree data is currently optional.
    ostree_props = props.get("ostree", {})

    # Parameters to pass to union()
    union_params = {
        "changes_dirs": None,
        "storage_dir": storage_dir,
        "extra_changes_dirs": extra_changes_dirs
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

    # Handle the "ostree.local" property (TODO).
    # Handle the "ostree.remote" property (TODO).

    tezi_props = props.get("easy-installer", {})

    # Note that the following test should never fail (due to schema validation).
    assert "local" in tezi_props, "'local' property is required"

    output_dir = tezi_props["local"]
    if os.path.isabs(output_dir):
        raise InvalidDataError(
            f"Image output directory '{output_dir}' is not relative")
    output_dir = os.path.abspath(output_dir)

    deploy_cli.deploy_tezi_image(
        ostree_ref=union_params["union_branch"],
        output_dir=output_dir,
        storage_dir=storage_dir, deploy_sysroot_dir=deploy_cli.DEFAULT_DEPLOY_DIR,
        image_name=tezi_props.get("name"),
        image_description=tezi_props.get("description"),
        licence_file=tezi_props.get("licence"),
        release_notes_file=tezi_props.get("release-notes"))

    bundle_props = tezi_props.get("bundle", {})

    if "dir" in bundle_props:
        # Do a combine "in place" to avoid creating another directory.
        comb_be.combine_image(
            image_dir=output_dir,
            bundle_dir=bundle_props["dir"],
            output_directory=None,
            image_name=tezi_props.get("name"),
            image_description=tezi_props.get("description"),
            licence_file=tezi_props.get("licence"),
            release_notes_file=tezi_props.get("release-notes"))

    # Implement this (TODO)
    # elif "compose-file" in bundle_props:
    #     #####
    #     dockerbundle.download_containers_by_compose_file(
    #         output_dir, compose_file, host_workdir,
    #         docker_username, docker_password, registry,
    #         use_host_docker, platform, output_filename)


def build(config_fname, storage_dir, substs=None, enable_subst=True):
    """Main handler for the normal operating mode of the build subcommand"""

    log.info(f"Building image as per configuration file '{config_fname}'...")
    log.debug(f"Substitutions ({['disabled', 'enabled'][enable_subst]}): "
              f"{substs}")

    config = bb.parse_config_file(config_fname)

    # ---
    # Handle each section.
    # ---

    if "input" in config:
        handle_input_section(config["input"], storage_dir=storage_dir)
    else:
        # Raise a parse error instead to allow a better message (TODO)
        raise FileContentMissing("No input specified in configuration file")

    # Customization section is currently optional.
    customization_props = config.get("customization", {})
    # fs_changes = handle_customization_section(customization_props)
    fs_changes = customization_props.get("filesystem")

    # Output section is currently optional.
    handle_output_section(config.get("output", {}),
                          storage_dir=storage_dir,
                          extra_changes_dirs=fs_changes)

    # print(config)


def do_build(args):
    """Wrapper of the build command that unpacks argparse arguments"""

    print(args)

    if args.create_template:
        # Template creating mode.
        create_template(args.config_fname)
    else:
        # Normal build mode.
        build(args.config_fname, args.storage_directory,
              substs=bb.parse_assignments(args.assignments),
              enable_subst=args.enable_substitutions)


def init_parser(subparsers):
    """Initialize "build" subcommands command line interface."""

    parser = subparsers.add_parser(
        "build",
        help=("Customize a Toradex Easy Installer image based on settings "
              "specified via a configuration file."))

    parser.add_argument(
        "-c", "--create-template", dest="create_template",
        default=False, action="store_true",
        help=("Request that a template file be generated (with the name "
              "defined by --file)."))

    parser.add_argument(
        "-f", "--file", metavar="CONFIG", dest="config_fname",
        default=DEFAULT_BUILD_FILE,
        help=("Specify location of the build configuration file "
              f"(default: {DEFAULT_BUILD_FILE})."))

    parser.add_argument(
        "-s", "--set", metavar="ASSIGNMENT", dest="assignments",
        default=[], action="append",
        help=("Assign values to variables (e.g. VER=\"1.2.3\"). This can "
              "be used multiple times."))

    parser.add_argument(
        "-n", "--no-subst", dest="enable_substitutions",
        default=True, action="store_false",
        help="Disable the variable substitution feature.")

    parser.set_defaults(func=do_build)
