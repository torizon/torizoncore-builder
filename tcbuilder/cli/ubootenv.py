"""
CLI handling for ubootenv subcommand
"""
import logging
import os
import sys

from tcbuilder.cli.build import l2_pref
from tcbuilder.backend import ubootenv
from tcbuilder.errors import \
    (InvalidArgumentError, InvalidStateError, ParseError, ParseErrors)

log = logging.getLogger("torizon." + __name__)

def do_ubootenv_fuses(args):
    """Run 'ubootenv fuses' subcommand"""

    if not os.path.isdir(args.input_dir):
        raise InvalidArgumentError(
            f"Input directory \"{args.input_dir}\" does not exist: aborting.")

    if args.output_dir and os.path.isdir(args.output_dir) and not args.force:
        raise InvalidStateError(
            f"Output directory \"{args.output_dir}\" already exists; aborting.")

    if not os.path.isfile(args.fuse_file):
        raise InvalidArgumentError(
            f"Fuse file \"{args.fuse_file}\" does not exist; aborting.")

    try:
        ubootenv.env_fuses(
            input_dir=args.input_dir,
            output_dir=args.output_dir,
            fuse_file=args.fuse_file,
            force=args.force)
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
    except Exception as exc:
        exc.msg = "Error: " + exc.msg
        raise exc


def init_parser(subparsers):
    """Initialize argument parser"""

    parser = subparsers.add_parser(
        "ubootenv",
        help="Manage U-Boot environment for Torizon OS images.",
        allow_abbrev=False)
    subparsers = parser.add_subparsers(title='Commands', required=True, dest='cmd')

    # ubootenv fuses
    subparser = subparsers.add_parser(
        "fuses",
        help=("Generate a Toradex Easy Installer image with fuse data, "
              "for secure boot purposes."),
        allow_abbrev=False)
    subparser.add_argument(
        metavar="INPUT_DIRECTORY",
        dest="input_dir",
        help="Path to input TorizonCore Toradex Easy Installer image.")
    subparser.add_argument(
        metavar="OUTPUT_DIRECTORY",
        dest="output_dir",
        help=("Path to output TorizonCore Toradex Easy Installer image, which "
              "will hold the fuse data."))
    subparser.add_argument(
        "--fuse-file", dest="fuse_file",
        help="Input yaml file containing fusing information",
        required=True)
    subparser.add_argument(
        "--force", dest="force",
        default=False, action="store_true",
        help="Remove output directory before starting (if it exists).")
    subparser.set_defaults(func=do_ubootenv_fuses)
