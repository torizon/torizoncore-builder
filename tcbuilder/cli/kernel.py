"""
CLI handling for kernel subcommand
"""

import os
import re
import sys
import subprocess
import logging
import tempfile

from tcbuilder.errors import PathNotExistError
from tcbuilder.errors import FileContentMissing
from tcbuilder.backend.common import get_unpack_command
from tcbuilder.backend import kernel, dt
from tcbuilder.cli import dto as dto_cli

log = logging.getLogger("torizon." + __name__)

# Name of the custom args overlay file (this should match the name used by the
# boot script uEnv.txt.
KERNEL_SET_CUSTOM_ARGS_DTS_NAME = 'custom-kargs_overlay.dts'

KERNEL_SET_CUSTOM_ARGS_DTS = """
/dts-v1/;
/plugin/;

&{{/chosen}} {{
    bootargs_custom = "{kernel_args}";
}};
"""


def do_kernel_build_module(args):
    """"Run 'kernel build_module' subcommand"""

    # Check for valid Makefile
    if not os.path.exists(args.source_directory):
        raise PathNotExistError(f'Source directory "{args.source_directory}" does not exist')

    makefile = os.path.join(args.source_directory, "Makefile")
    if not os.path.exists(makefile):
        raise PathNotExistError(f'Makefile "{makefile}" does not exist')
    file = open(makefile, 'r')
    lines = file.readlines()
    kernel_check = None
    for line in lines:
        if kernel_check is None:
            kernel_check = re.search("KERNEL_SRC", line)
        if kernel_check is None:
            kernel_check = re.search("KDIR", line)
    if kernel_check is None:
        raise FileContentMissing(f'KERNEL_SRC not found in "{makefile}"')

    # Find and unpack linux source
    linux_src = subprocess.check_output(f"""find {args.storage_directory}/sysroot/ostree/deploy \
        -type f -name 'linux.tar.bz2' -print -quit""", shell=True, text=True)
    assert linux_src, "panic: missing Linux kernel source!"
    linux_src = linux_src.rstrip()
    tarcmd = "cat '{0}' | {1} | tar -xf - -C {2}".format(
                linux_src, get_unpack_command(linux_src), args.storage_directory)
    subprocess.check_output(tarcmd, shell=True, stderr=subprocess.STDOUT)
    extracted_src = os.path.join(args.storage_directory, "linux")

    # Build and install Kernel module
    kernel_changes_dir = kernel.get_kernel_changes_dir(args.storage_directory)
    kernel_subdir = os.path.dirname(dt.get_dtb_kernel_subdir(args.storage_directory))
    mod_path = os.path.join(kernel_changes_dir, kernel_subdir)
    os.makedirs(mod_path, exist_ok=True)
    usr_dir = subprocess.check_output(f"""find {args.storage_directory}/sysroot/ostree/deploy \
        -type d -name 'usr' -print -quit""", shell=True, text=True).rstrip()
    src_mod_dir = os.path.join(os.path.dirname(usr_dir), kernel_subdir)
    src_ostree_archive_dir = os.path.join(args.storage_directory, "ostree-archive")
    src_dir = os.path.abspath(args.source_directory)
    kernel.build_module(src_dir, extracted_src,
                        src_mod_dir, src_ostree_archive_dir, mod_path, kernel_changes_dir)
    log.info("Kernel module(s) successfully built and ready to deploy.")

    # Set built kernel modules to be autoloaded on boot
    if args.autoload:
        built_modules = subprocess.check_output(f"""find {args.source_directory} -name \
            '*.ko' -print""", shell=True, text=True).splitlines()
        for module in built_modules:
            kernel.autoload_module(module, kernel_changes_dir)
            log.info(f"{module} is set to be autoloaded on boot.")

    log.info("All kernel module(s) have been built and prepared.")


def do_kernel_set_custom_args(args):
    """Run 'kernel set_custom_args" subcommand"""

    kargs = " ".join(args.kernel_args)
    if not kargs.rstrip():
        log.error('error: please pass a valid string for the custom kernel arguments.')
        sys.exit(1)

    # Format string to become file contents.
    dts_contents = KERNEL_SET_CUSTOM_ARGS_DTS.format(kernel_args=kargs)

    # Generate the DTS file with desired contents inside a temporary directory.
    with tempfile.TemporaryDirectory() as tmpdirname:
        dtos_path = os.path.join(tmpdirname, KERNEL_SET_CUSTOM_ARGS_DTS_NAME)
        with open(dtos_path, 'w') as f:
            f.write(dts_contents)

        # The present command is simply a wrapper around `dto apply` - since we are setting
        # test_apply as False the parameters `dtb_path` is not required as the function being
        # invoked will not try to apply the overlay for assurance purposes. Also, the include
        # directory is not needed either because we know the file being compiled includes no
        # other files.
        dto_cli.dto_apply_cmd(dtos_path=dtos_path,
                              dtb_path=None, include_dirs=[],
                              storage_dir=args.storage_directory,
                              allow_reapply=True, test_apply=False)


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
    subparser.set_defaults(func=do_kernel_build_module)

    # kernel set_custom_args
    subparser = subparsers.add_parser("set_custom_args",
                                      help="Modify the TorizonCore kernel arguments.")
    subparser.add_argument(metavar="KERNEL_ARGS", dest="kernel_args", nargs='+',
                           help="Kernel arguments to be added.")
    subparser.set_defaults(func=do_kernel_set_custom_args)
