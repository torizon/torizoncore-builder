"""
CLI handling for build subcommand
"""

import re
import logging

from tcbuilder.errors import InvalidAssignmentError

log = logging.getLogger("torizon." + __name__)

DEFAULT_BUILD_FILE = "tcbuild.yaml"


def _parse_assignments(assignments):
    """Parse a list of assignment strings in the form KEY=VALUE

    :param assignments: List of strings to be parsed.
    :return: Dictionary with the resulting key-value mapping.
    """

    # print("_parse_assignments:", assignments)
    ASSGN_REGEX = r"^([a-zA-Z_][a-zA-Z_0-9]*)=(.*)$";
    assgn_regex = re.compile(ASSGN_REGEX)

    var_mapping = {}
    for assgn in assignments:
        matches = assgn_regex.match(assgn)
        if not matches:
            raise InvalidAssignmentError(
                "Variable assignment must follow the format KEY=VALUE "
                f"(in assignment '{assgn}').")
        # log.debug(f"_parse_assignments: '{matches.group(1)}' <= '{matches.group(2)}'")
        
        var_key, var_val = matches.group(1), matches.group(2)
        var_mapping[var_key] = var_val

    return var_mapping


def create_template(config_fname):
    print(f"Generating '{config_fname}' (not yet implemented)")


def build(config_fname, substs=None, enable_subst=True):
    print(f"Building image as per configuration file '{config_fname}' (not yet implemented).")
    print(f"Substitutions ({['disabled', 'enabled'][enable_subst]}):", substs)


def do_build(args):
    print(args)

    if args.create_template:
        # Just create the template and nothing else.
        create_template(args.config_fname)
    else:
        build(args.config_fname,
              substs=_parse_assignments(args.assignments),
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
