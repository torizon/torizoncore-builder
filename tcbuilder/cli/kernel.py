from tcbuilder.backend import kernel

def do_kernel_build_module(args):
    """"Run 'kernel build_module' subcommand"""

    kernel.build_module()

def do_kernel_set_custom_args(args):
    """Run 'kernel set_custom_args" subcommand"""

    kernel.set_custom_args()


def init_parser(subparsers):
    """Initialize 'kernel' subcommands command line interface."""

    parser = subparsers.add_parser("kernel", help="Manage and modify TorizonCore Linux Kernel.")
    subparsers = parser.add_subparsers(title='Commands', required=True, dest='cmd')

    # kernel build_module
    subparser = subparsers.add_parser("build_module",
                                      help="""Build the kernel module at the provided
                                      source directory.""")
    subparser.add_argument(metavar="SRC_DIR", dest="source_directory", nargs='?',
                           help="Path to directory with kernel module source code.")
    subparser.add_argument("--autoload", dest="autoload", action="store_true",
                           help="Configure kernel module to be loaded on startup.")

    # kernel set_custom_args
    subparser = subparsers.add_parser("set_custom_args",
                                      help="Modify the TorizonCore kernel arguments.")
    subparser.add_argument(metavar="KERNEL_ARGS", dest="kernel_args", nargs='?',
                           help="Kernel arguments to be added.")
