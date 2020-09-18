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

from tcbuilder.cli import batch, bundle, combine, deploy, dt, isolate, push, \
                          serve, splash, union, unpack

#pylint: enable=wrong-import-position

parser = argparse.ArgumentParser(description="""\
Utility to create TorizonCore images with containers pre-provisioned. Requires a
TorizonCore base image and a Docker Compose YAML file as input and creates a
Toradex Easy Installer image with TorizonCore and the containers combined.
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
                    help="Show more output")

parser.add_argument("--log-level", dest="log_level",
                    help="--log-level Set global log level (debug, info, warning, error, critical)")

parser.add_argument("--log-file", dest="log_file",
                    help="write logs to a file instead of console",
                    default=None)


parser.add_argument("--bundle-directory", dest="bundle_directory",
                    help="Container bundle directory",
                    default="bundle")
parser.add_argument("--storage-directory", dest="storage_directory",
                    help="""Path to internal storage. Must be a file system
                    capable of carrying Linux file system metadata (Unix
                    file permissions and xattr).""",
                    default="/storage")

subparsers = parser.add_subparsers(title='Commands:', required=True, dest='cmd')

batch.init_parser(subparsers)
bundle.init_parser(subparsers)
unpack.init_parser(subparsers)
isolate.init_parser(subparsers)
deploy.init_parser(subparsers)
union.init_parser(subparsers)
combine.init_parser(subparsers)
dt.init_parser(subparsers)
push.init_parser(subparsers)
splash.init_parser(subparsers)
serve.init_parser(subparsers)

if __name__ == "__main__":
    mainargs = parser.parse_args()
    setup_logging(mainargs.log_level, mainargs.verbose, mainargs.log_file)

    try:
        if hasattr(mainargs, 'func'):
            mainargs.func(mainargs)
        else:
            print("Try --help for options")
    except Exception as ex:
        logging.fatal(
            "An unexpected Exception occured. Please provide the following stack trace to\n"
            "the Toradex TorizonCore support team:\n\n")
        raise ex
