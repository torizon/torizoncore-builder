"""
CLI for the splash-config command
"""

import logging
import os
import shutil

from tcbuilder.backend import splashconfig as splashconfig_be

from tcbuilder.backend.common import \
    (images_unpack_executed, set_output_ownership,
     is_file_type_fit)
from tcbuilder.errors import \
    (InvalidStateError, PathNotExistError)
from tcbuilder.backend.initramfs import UnpackedInitramfs
from tcbuilder.backend.kernel import \
    (find_kernel_in_sysroot, get_kernel_changes_dir)
from tcbuilder.backend.splash import \
    (get_splash_changes_dir, PLYMOUTH_THEME_PATH)
from tcbuilder.backend.splashconfig import PLYMOUTH_CONFIG

log = logging.getLogger("torizon." + __name__)


def splash_config_set(config):
    """Main handler for 'splash-config set' command.

    :param config: Path to provided configuration file.
    """

    config_file = os.path.abspath(config)
    if not os.path.exists(config_file):
        raise PathNotExistError(f"Unable to find configuration file {config}.")

    with UnpackedInitramfs(source="auto") as rdm:
        splashconfig_be.add_plymouth_splash_config(rdm.get_path(), config_file)

    unpacked_kernel_path = find_kernel_in_sysroot()
    kernel_is_fit = is_file_type_fit(unpacked_kernel_path)
    log.debug(f"splash: kernel_is_fit={kernel_is_fit}")

    if kernel_is_fit:
        # FIT case: all changes go to the kernel-changes directory.
        changes_dir = get_kernel_changes_dir()
    else:
        # non-FIT case: changes go to the splash-changes directory.
        changes_dir = get_splash_changes_dir()

    splashconfig_be.add_plymouth_splash_config(changes_dir, config_file)

    log.info("Splash screen configuration updated")


def do_splash_config_set(args):
    """Run 'splash-config set' command."""

    images_unpack_executed()

    splash_config_set(args.splash_config)


def create_config(output_file, config, force):
    """Prints or writes the current active Plymouth Configuration file.

    :param output_file: Filename for where to write the content. If 'None'
                        then prints the content to console instead.
    :param config: Path to currently active config file.
    :param force: Whether to overwrite output_file if it already exists.
    """

    # Dump to stdout
    if not output_file:
        print()
        with open(config, "r", encoding="utf-8") as file:
            for line in file:
                print(line, end='')
    else:
        if os.path.exists(output_file) and not force:
            raise InvalidStateError(f"File '{output_file}' already exists; aborting.")

        log.info(f"Creating configuration file '{output_file}'")
        shutil.copy(config, output_file)
        set_output_ownership(output_file)


def splash_config_dump(output_file, force):
    """Main handler for splash-config dump.

    :param output_file: Filename to write splash config content to.
    :param force: Whether to overwrite output_file if it already exists.
    """

    unpacked_kernel_path = find_kernel_in_sysroot()
    kernel_is_fit = is_file_type_fit(unpacked_kernel_path)
    log.debug(f"splash: kernel_is_fit={kernel_is_fit}")

    if kernel_is_fit:
        # FIT case: all changes go to the kernel-changes directory.
        changes_dir = get_kernel_changes_dir()
    else:
        # non-FIT case: changes go to the splash-changes directory.
        changes_dir = get_splash_changes_dir()

    config_custom = os.path.join(changes_dir, PLYMOUTH_THEME_PATH, PLYMOUTH_CONFIG)

    # First determine whether a customized config is present,
    # otherwise we use the one from the unpacked image.
    if os.path.exists(config_custom):
        config_current = config_custom
        log.info("Found customized configuration file.")
    else:
        config_current = splashconfig_be.get_default_config()
        log.info("Found default configuration file.")

    create_config(output_file, config_current, force)


def do_splash_config_dump(args):
    """Run 'splash-config dump' command."""

    images_unpack_executed()

    splash_config_dump(args.output_file, args.force)


def init_parser(subparsers):
    """Initialize 'splash-config' subcommands command line interface."""

    parser = subparsers.add_parser(
        "splash-config",
        help=("Perform customizations that affect the configuration of the splash "
              "screen."),
        allow_abbrev=False)
    subparsers = parser.add_subparsers(title='Commands', required=True, dest='cmd')

    # splash-config set
    subparser = subparsers.add_parser(
        "set",
        help="Sets a new Plymouth configuration file as the new configuration.",
        allow_abbrev=False)
    subparser.add_argument(
        dest="splash_config",
        metavar="SPLASH_CONFIG",
        help="File path to the new configuration file.")
    subparser.set_defaults(func=do_splash_config_set)

    # splash-config dump
    subparser = subparsers.add_parser(
        "dump",
        help="Prints the current Plymouth configuration.",
        allow_abbrev=False)
    subparser.add_argument(
        "--file",
        dest="output_file",
        help="Writes current Plymouth configuration to the provided file name.",
        required=False,
        default=None)
    subparser.add_argument(
        "--force",
        dest="force",
        default=False, action="store_true",
        help="Overwrite file designated by '--file' (if it exists).")
    subparser.set_defaults(func=do_splash_config_dump)
