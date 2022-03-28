"""Push sub-command CLI handling

The push sub-command makes use of aktualizr's SOTA tools (specifically
garage-push and garage-sign) to sign & push a new OSTree to be deployed over OTA
to the devices.
"""

import logging

import tcbuilder.cli.platform as platform_cli

log = logging.getLogger("torizon." + __name__)


def push_subcommand(args):
    """Run \"push\" subcommand"""

    platform_cli.do_platform_push(args)
    log.warning("Warning: The \"push\" command is deprecated "
                "and will be removed in an upcoming major release "
                "of TorizonCore Builder; please use \"platform push\" instead.")


def init_parser(subparsers):
    """Initialize argument parser"""

    subparser = subparsers.add_parser(
        "push",
        help="Push artifact to OTA server as a new update package.",
        description=("Warning: The \"push\" command is deprecated and will be "
                     "removed in an upcoming major release of TorizonCore Builder; "
                     "please use \"platform push\" instead."))

    platform_cli.add_common_push_arguments(subparser)

    subparser.set_defaults(func=push_subcommand)
