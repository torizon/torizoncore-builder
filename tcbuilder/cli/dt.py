import logging
from tcbuilder.backend import dt

def dt_overlay_subcommand(args):
    log = logging.getLogger("torizon." + __name__)  # use name hierarchy for "main" to be the parent

    dt.build_and_apply(args.devicetree, args.overlays, args.devicetree_out,
                       args.include_dir)

    log.info(f"Overlays {args.overlays} successfully applied to {args.devicetree}")

def dt_custom_subcommand(args):
    log = logging.getLogger("torizon." + __name__)  # use name hierarchy for "main" to be the parent

    dt.build_and_apply(args.devicetree, None, args.devicetree_out,
                       args.include_dir)

    log.info(f"Device tree {args.devicetree} built successfully")


def add_overlay_parser(parser):
    subparsers = parser.add_subparsers(title='Commands:', required=True, dest='cmd')
    subparser = subparsers.add_parser("overlay", help="Apply an overlay")
    subparser.add_argument("--devicetree", dest="devicetree",
                           help="Path to the devicetree",
                           required=True)
    subparser.add_argument("--devicetree-out", dest="devicetree_out",
                           help="Path to the devicetree output",
                           required=True)
    subparser.add_argument("--include-dir", dest="include_dir", action='append',
                           help="""Directory with device tree include (.dtsi) or
                           header files. Can be passed multiple times.""",
                           required=True)
    subparser.add_argument(metavar="overlays", dest="overlays", nargs="+",
                           help="The overlay to apply")

    subparser.set_defaults(func=dt_overlay_subcommand)

    subparser = subparsers.add_parser("custom", help="Compile device tree")
    subparser.add_argument("--devicetree", dest="devicetree",
                           help="Path to the devicetree",
                           required=True)
    subparser.add_argument("--devicetree-out", dest="devicetree_out",
                           help="Path to the devicetree output",
                           required=True)
    subparser.add_argument("--include-dir", dest="include_dir", action='append',
                           help="""Directory with device tree include (.dtsi) or
                           header files. Can be passed multiple times.""",
                           required=True)
    
    subparser.set_defaults(func=dt_custom_subcommand)

def init_parser(subparsers):
    subparser = subparsers.add_parser("dt", help="""\
    Compile and apply device trees and device tree overlays.
    """)

    add_overlay_parser(subparser)
