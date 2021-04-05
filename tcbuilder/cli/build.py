"""
CLI handling for build subcommand
"""

import logging

from tcbuilder.backend import build as bb
# from tcbuilder.errors import InvalidAssignmentError

DEFAULT_BUILD_FILE = "tcbuild.yaml"

log = logging.getLogger("torizon." + __name__)


def create_template(config_fname):
    """Main handler for the create-template mode of the build subcommand"""

    print(f"Generating '{config_fname}' (not yet implemented)")


def build(config_fname, substs=None, enable_subst=True):
    """Main handler for the normal operating mode of the build subcommand"""

    print(f"Building image as per configuration file '{config_fname}'"
          " (not yet implemented).")
    print(f"Substitutions ({['disabled', 'enabled'][enable_subst]}):", substs)

    config = bb.parse_config_file(config_fname)
    print(config)


def do_build(args):
    """Wrapper of the build command that unpacks argparse arguments"""

    print(args)

    if args.create_template:
        # Template creating mode.
        create_template(args.config_fname)
    else:
        # Normal build mode.
        build(args.config_fname,
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
