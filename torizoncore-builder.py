#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TorizonCore Builder main python script

This module is the entry point of TorizonCore Builder. TorizonCore Builder allows
to create customized TorizonCore OSTree commits and Toradex Easy Installer images
without rebuilding the complete operating system.
"""

# Version information (as per PEP-8, it should be set before imports):
__version_info__ = ('3', '10', '0')
__version__ = '.'.join(__version_info__)

import sys

MIN_PYTHON = (3, 7)
if sys.version_info < MIN_PYTHON:
    sys.exit("Python %s.%s or later is required.\n" % MIN_PYTHON)

# pylint: disable=wrong-import-position
import argparse
import logging
import os
import subprocess
import traceback

from tcbuilder.cli import (bundle, build, combine, deploy, dt, dto, images, isolate,
                           kernel, ostree, platform, push, splash, union)

from tcbuilder.errors import TorizonCoreBuilderError, InvalidArgumentError
# pylint: enable=wrong-import-position

# IMPORTANT: This line may be edited by the build system.
VERSION_SUFFIX = ''

parser = argparse.ArgumentParser(
    description="TorizonCore Builder is an utility that allows to create "
                "customized TorizonCore OSTree commits and Toradex Easy "
                "Installer images without rebuilding the complete operating "
                "system.",
    epilog="Learn more on "
           "https://developer.toradex.com/knowledge-base/torizoncore-builder-tool",
    allow_abbrev=False)


def setup_logging(arg_level, verbose, file):
    """Setup logging levels and print handler for torizoncore-builder"""

    # Configure the root logger for our needs
    logger = logging.getLogger()
    lhandler = None
    if file is None:
        lhandler = logging.StreamHandler()
    else:
        file = os.path.abspath(file)
        lhandler = logging.FileHandler(file)

    set_level = None

    if verbose:
        set_level = logging.DEBUG

    if arg_level is not None:
        levels = {
            'DEBUG': logging.DEBUG,
            'INFO': logging.INFO,
            'WARNING': logging.WARNING,
            'ERROR': logging.ERROR,
            'CRITICAL': logging.CRITICAL,
        }
        set_level = levels.get(arg_level.upper())

        if set_level is None:
            print("Invalid value for --log-level. Expected one of {levels}",
                  levels=", ".join(levels.keys()))
            sys.exit(-1)

    # Show/store time if any of the following is used:
    # --verbose
    # --log-level DEBUG
    # --log-file FILE
    if verbose or file is not None or (set_level is not None and set_level <= logging.DEBUG):
        lformat = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        lhandler.setFormatter(lformat)

    if set_level is None:
        # By default, use INFO for TorizonCore itself, and WARNING for libraries
        torizoncore_logger = logging.getLogger("torizon")
        torizoncore_logger.setLevel(logging.INFO)
        logger.setLevel(logging.WARNING)
    else:
        logger.setLevel(set_level)

    logger.addHandler(lhandler)


parser.add_argument("--verbose", dest="verbose",
                    action='store_true',
                    help="show more output")

parser.add_argument("--log-level", dest="log_level",
                    help="set global log level (debug, info, warning, error, critical)")

parser.add_argument("--log-file", dest="log_file",
                    help="write logs to a file instead of console",
                    default=None)

# This parameter should be hidden and its functionality should be
# defined by setting the "-s" switch of the "tcb-env-setup" script.
parser.add_argument("--storage-directory",
                    dest="storage_directory",
                    help=argparse.SUPPRESS,
                    default=argparse.SUPPRESS)

parser.add_argument('-v', '--version',
                    action='version',
                    version='%(prog)s ' + __version__ + VERSION_SUFFIX)

# Temporary solution to provide better messages (DEPRECATED since 2021-05-17).
parser.add_argument(
    "--bundle-directory",
    dest="bundle_directory_compat",
    type=str,
    default="",
    help=argparse.SUPPRESS)

subparsers = parser.add_subparsers(title='Commands', required=True, dest='cmd')

# Commands in ALPHABETICAL order.
build.init_parser(subparsers)
bundle.init_parser(subparsers)
combine.init_parser(subparsers)
deploy.init_parser(subparsers)
dt.init_parser(subparsers)
dto.init_parser(subparsers)
images.init_parser(subparsers)
isolate.init_parser(subparsers)
kernel.init_parser(subparsers)
ostree.init_parser(subparsers)
platform.init_parser(subparsers)
push.init_parser(subparsers)
splash.init_parser(subparsers)
union.init_parser(subparsers)

# pylint: disable=broad-except

def am_i_under_docker():
    """Tells whether the OS is inside the Matrix."""
    # Detect if the init process has Docker control groups; see
    # https://stackoverflow.com/questions/20010199/how-to-determine-if-a-process-runs-inside-lxc-docker
    with open('/proc/1/cgroup', 'rt') as fd_cgroup:
        return 'docker' in fd_cgroup.read()


def assert_operational_directory(path):
    """Assert that a given directory looks ok to be used as a data storage
       between executions of torizoncore-builder.

    :param path: Diretory path to be used as data storage.
    """

    if not os.path.isabs(path):
        logging.error(f"error: storage directory '{path}' is not absolute.")
        sys.exit(1)
    if not os.path.exists(path):
        logging.error(f"error: storage directory '{path}' does not exist.")
        sys.exit(1)
    if not os.path.isdir(path):
        logging.error(f"error: storage directory '{path}' is not a directory.")
        sys.exit(1)
    if not am_i_under_docker():
        return
    if os.stat(path).st_dev == os.stat('/').st_dev:
        # We're under Docker and the directory is part of the container's root mount.
        # When the container vanishes, so will the contents of the directory.
        # This is probably not what the user desires.
        logging.warning(f"WARNING: storage directory '{path}' is local to "
                        "a Docker container, and its contents will be lost "
                        "if the container vanishes.")


def check_deprecated_parameters(args):
    """Check deprecated base TorizonCore Builder command line arguments.

    It checks for "DEPRECATED" switches or command line arguments and
    shows a message explaining what the user should do.

    :param args: Base arguments provided to "torizoncore-builder" command.
    :raises:
        InvalidArgumentError: if a deprecated switch was passed.
    """

    # Temporary solution to provide better messages (DEPRECATED since 2021-05-17).
    if args.bundle_directory_compat:
        raise InvalidArgumentError(
            "Error: the switch --bundle-directory has been removed from the "
            "base torizoncore-builder command; it should be used only with "
            "the \"bundle\" and \"combine\" subcommands")


if __name__ == "__main__":
    mainargs = parser.parse_args()

    setup_logging(mainargs.log_level, mainargs.verbose, mainargs.log_file)

    if VERSION_SUFFIX == '+early-access':
        sys.stderr.write("You are running an early access version of TorizonCore Builder.\n")

    # Check if "--storage-directory" was provided in the command line.
    if "storage_directory" in mainargs:
        logging.warning("WARNING: The parameter --storage-directory is being "
                        "deprecated and might be removed from TorizonCore "
                        "Builder soon. For the same functionality, please "
                        "use the -s flag from the tcb-env-setup.sh script.")
        assert_operational_directory(mainargs.storage_directory)
    else:
        mainargs.storage_directory = "/storage"

    try:
        check_deprecated_parameters(mainargs)
        if hasattr(mainargs, 'func'):
            mainargs.func(mainargs)
        else:
            print("Try --help for options")
    except TorizonCoreBuilderError as ex:
        logging.error(ex.msg)  # msg from all kinds of Exceptions
        if ex.det is not None:
            logging.info(ex.det)  # more elaborative message
        logging.debug(traceback.format_exc())  # full traceback to be shown for debugging only
        sys.exit(-1)
    except subprocess.CalledProcessError as ex:
        logging.error(f"{ex}")
        if b"\n" in ex.output:
            outxt = "\n  ".join(ex.output.decode().split("\n")) # pylint: disable=invalid-name
            logging.error(f"Output:\n  {outxt}")
        elif ex.output:
            logging.error(f"Output: {ex.output.decode()}")
        logging.debug(traceback.format_exc())  # full traceback to be shown for debugging only
        sys.exit(4)
    except Exception as ex:
        logging.fatal(
            "An unexpected Exception occurred. Please provide the following stack trace to\n"
            "the Toradex TorizonCore support team:\n\n")
        logging.error(traceback.format_exc())
        sys.exit(-2)
