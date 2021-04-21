#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TorizonCore Builder main python script

This module is the entry point of TorizonCore Builder. TorizonCore Builder allows
to create customized TorizonCore OSTree commits and Toradex Easy Installer images
without rebuilding the complete operating system.
"""

import sys

MIN_PYTHON = (3, 7)
if sys.version_info < MIN_PYTHON:
    sys.exit("Python %s.%s or later is required.\n" % MIN_PYTHON)

#pylint: disable=wrong-import-position

import argparse
import logging
import os
import traceback

from tcbuilder.cli import batch, bundle, combine, deploy, dt, dto, isolate, push, \
        serve, splash, union, images, kernel

from tcbuilder.errors import TorizonCoreBuilderError

#pylint: enable=wrong-import-position

__version_info__ = ('2', '5', '4')
__version__ = '.'.join(__version_info__)

parser = argparse.ArgumentParser(description="""\
TorizonCore Builder is an utility that allows to create customized TorizonCore
OSTree commits and Toradex Easy Installer images without rebuilding the complete
operating system.""",
epilog="""\
Learn more on
https://developer.toradex.com/knowledge-base/torizoncore-builder-tool
""")


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

parser.add_argument("--bundle-directory", dest="bundle_directory",
                    help="container bundle directory",
                    default="bundle")

parser.add_argument("--storage-directory", dest="storage_directory",
                    help="""path to internal storage. Must be a file system
                    capable of carrying Linux file system metadata (Unix
                    file permissions and xattr)""",
                    default="/storage")

parser.add_argument('-v', '--version', action='version', version='%(prog)s ' + __version__)

subparsers = parser.add_subparsers(title='Commands', required=True, dest='cmd')

batch.init_parser(subparsers)
bundle.init_parser(subparsers)
images.init_parser(subparsers)
isolate.init_parser(subparsers)
deploy.init_parser(subparsers)
union.init_parser(subparsers)
combine.init_parser(subparsers)
dt.init_parser(subparsers)
dto.init_parser(subparsers)
push.init_parser(subparsers)
splash.init_parser(subparsers)
serve.init_parser(subparsers)
kernel.init_parser(subparsers)

#pylint: disable=broad-except

def am_i_under_docker():
    '''Tells whether the OS is inside the Matrix.
    '''
    # Detect if the init process has Docker control groups; see
    # https://stackoverflow.com/questions/20010199/how-to-determine-if-a-process-runs-inside-lxc-docker
    with open('/proc/1/cgroup', 'rt') as f:
        return 'docker' in f.read()

def assert_operational_directory(path, label):
    '''Assert that a given directory looks ok to be used as a data storage
       between executions of torizoncore-builder.
    '''
    if not os.path.isabs(path):
        logging.error(f"error: {label} directory '{path}' is not absolute.")
        sys.exit(1)
    if not os.path.exists(path):
        logging.error(f"error: {label} directory '{path}' does not exist.")
        sys.exit(1)
    if not os.path.isdir(path):
        logging.error(f"error: {label} directory '{path}' is not a directory.")
        sys.exit(1)
    if not am_i_under_docker():
        return
    if os.stat(path).st_dev == os.stat('/').st_dev:
        # We're under Docker and the directory is part of the container's root mount.
        # When the container vanishes, so will the contents of the directory.
        # This is probably not what the user desires.
        logging.warning(f"warning: {label} directory '{path}' is local to a Docker container, and its contents will be lost if the container vanishes.")
        logging.warning(f"You may want to bind '{path}' to a host directory with Docker's --volume option.")
    return

if __name__ == "__main__":
    mainargs = parser.parse_args()
    setup_logging(mainargs.log_level, mainargs.verbose, mainargs.log_file)
    assert_operational_directory(mainargs.storage_directory, 'storage')

    try:
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
    except Exception as ex:
        logging.fatal(
            "An unexpected Exception occured. Please provide the following stack trace to\n"
            "the Toradex TorizonCore support team:\n\n")
        logging.error(traceback.format_exc())     
        sys.exit(-2)

