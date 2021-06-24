"""
CLI handling for kernel subcommand
"""

import os
import re
import sys
import logging
import tempfile
import subprocess

from tcbuilder.errors import PathNotExistError
from tcbuilder.errors import FileContentMissing
from tcbuilder.backend.common import (get_unpack_command,
                                      set_output_ownership)
from tcbuilder.backend import kernel, dt, dto
from tcbuilder.cli import dto as dto_cli

log = logging.getLogger("torizon." + __name__)

# pylint: disable=fixme

# Name of the custom args overlay file (this should match the name used by the
# boot script uEnv.txt.
# XXX: Always keep in sync with uEnv.txt.in in recipe `u-boot-distro-boot`.
KERNEL_SET_CUSTOM_ARGS_DTS_NAME = 'custom-kargs_overlay.dts'

# Contents of the custom args overlay source file.
KERNEL_SET_CUSTOM_ARGS_DTS = """
/dts-v1/;
/plugin/;

&{{/chosen}} {{
    bootargs_custom = "{kernel_args}";
}};
"""

# Name of the property defining the kernel args.
# XXX: Always keep in sync with `KERNEL_SET_CUSTOM_ARGS_DTS`.
# XXX: Always keep in sync with uEnv.txt.in in recipe `u-boot-distro-boot`.
KERNEL_SET_CUSTOM_ARGS_PROPERTY = 'bootargs_custom'

# Regex to find the "function" responsible for handling the bootargs in uEnv.txt.
# XXX: Always keep in sync with uEnv.txt.in in recipe `u-boot-distro-boot`.
UENV_SET_CUSTOM_ARGS_FUNCTION_RE = r'^\s*set_bootargs_custom='


# pylint: disable=too-many-locals
def kernel_build_module(source_dir, storage_dir, autoload):
    """"Main handler of the 'kernel build_module' subcommand"""

    # Check for valid Makefile
    if not os.path.exists(source_dir):
        raise PathNotExistError(f'Source directory "{source_dir}" does not exist')

    makefile = os.path.join(source_dir, "Makefile")
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
    linux_src = subprocess.check_output(
        ["find", os.path.join(storage_dir, "sysroot/ostree/deploy"),
         "-type", "f", "-name", "linux.tar.bz2", "-print", "-quit"], text=True)
    assert linux_src, "panic: missing Linux kernel source!"
    linux_src = linux_src.rstrip()
    tarcmd = "cat '{0}' | {1} | tar -xf - -C {2}".format(
        linux_src, get_unpack_command(linux_src), storage_dir)
    subprocess.check_output(tarcmd, shell=True, stderr=subprocess.STDOUT)
    extracted_src = os.path.join(storage_dir, "linux")

    # Build and install Kernel module
    kernel_changes_dir = kernel.get_kernel_changes_dir(storage_dir)
    kernel_subdir = os.path.dirname(dt.get_dtb_kernel_subdir(storage_dir))
    mod_path = os.path.join(kernel_changes_dir, kernel_subdir)
    os.makedirs(mod_path, exist_ok=True)
    usr_dir = subprocess.check_output(
        ["find", os.path.join(storage_dir, "sysroot/ostree/deploy"),
         "-type", "d", "-name", "usr", "-print", "-quit"],
        text=True).rstrip()
    src_mod_dir = os.path.join(os.path.dirname(usr_dir), kernel_subdir)
    src_ostree_archive_dir = os.path.join(storage_dir, "ostree-archive")
    src_dir = os.path.abspath(source_dir)
    kernel.build_module(
        src_dir, extracted_src, src_mod_dir, src_ostree_archive_dir, mod_path,
        kernel_changes_dir)
    set_output_ownership(src_dir)
    log.info("Kernel module(s) successfully built and ready to deploy.")

    # Set built kernel modules to be autoloaded on boot
    if autoload:
        built_modules = subprocess.check_output(
            ["find", source_dir, "-name", "*.ko", "-print"],
            text=True).splitlines()
        for module in built_modules:
            kernel.autoload_module(module, kernel_changes_dir)
            log.info(f"{module} is set to be autoloaded on boot.")

    log.info("All kernel module(s) have been built and prepared.")

# pylint: enable=too-many-locals


def do_kernel_build_module(args):
    """"Run 'kernel build_module' subcommand"""
    kernel_build_module(source_dir=args.source_directory,
                        storage_dir=args.storage_directory,
                        autoload=args.autoload)


def kernel_set_custom_args(kernel_args, storage_dir):
    """Main handler of the 'kernel set_custom_args" subcommand

    :param kernel_args: List of strings with the kernel arguments.
    :param storage_dir: Path of the storage directory to be used on the
                        operations.
    """

    kargs = " ".join(kernel_args)
    if not kargs.rstrip():
        log.error('error: please pass a valid string for the custom kernel arguments.')
        sys.exit(1)

    # Make sure image can handle kernel arguments.
    assert_custom_kargs_compat_image(storage_dir)

    # Format string to become file contents.
    dts_contents = KERNEL_SET_CUSTOM_ARGS_DTS.format(kernel_args=kargs)

    # Generate the DTS file with desired contents inside a temporary directory.
    with tempfile.TemporaryDirectory() as tmpdirname:
        dtos_path = os.path.join(tmpdirname, KERNEL_SET_CUSTOM_ARGS_DTS_NAME)
        with open(dtos_path, 'w') as file:
            file.write(dts_contents)

        # The present command is simply a wrapper around `dto apply` - since we are setting
        # test_apply as False the parameters `dtb_path` is not required as the function being
        # invoked will not try to apply the overlay for assurance purposes. Also, the include
        # directory is not needed either because we know the file being compiled includes no
        # other files.
        dto_cli.dto_apply(dtos_path=dtos_path,
                          dtb_path=None, include_dirs=[],
                          storage_dir=storage_dir,
                          allow_reapply=True, test_apply=False)

    # Confirm application of arguments.
    print(f"Kernel custom arguments successfully configured with \"{kargs}\".")


def do_kernel_set_custom_args(args):
    """Run 'kernel set_custom_args" subcommand"""

    kernel_set_custom_args(kernel_args=args.kernel_args,
                           storage_dir=args.storage_directory)


def do_kernel_get_custom_args(args):
    """Run 'kernel get_custom_args" subcommand"""

    # Make sure image can handle kernel arguments.
    assert_custom_kargs_compat_image(args.storage_directory)

    # Check if the custom kernel args overlays is being applied.
    applied_overlay_basenames = dto.get_applied_overlays_base_names(args.storage_directory)
    dtob_basename = os.path.splitext(KERNEL_SET_CUSTOM_ARGS_DTS_NAME)[0] + ".dtbo"
    if dtob_basename not in applied_overlay_basenames:
        # No arguments set: nothing wrong with that.
        log.info("No custom kernel arguments configured.")
        return

    # Determine full path of the overlay of interest only.
    applied_overlay_paths = \
        dto.get_applied_overlay_paths(args.storage_directory, base_names=[dtob_basename])

    log.debug(f"Custom arguments overlay is applied: path='{applied_overlay_paths[0]}'")

    dtob_path = applied_overlay_paths[0]

    # XXX: Following command might break if DTC command changes in the future.
    # Run external program from 'device-tree-compiler' package.
    fdtget_output = \
        subprocess.check_output(
            ["fdtget", dtob_path, "/fragment@0/__overlay__/",
             KERNEL_SET_CUSTOM_ARGS_PROPERTY], text=True).rstrip()

    # Send output to stdout always.
    print(f"Currently configured custom kernel arguments: \"{fdtget_output}\".")


def do_kernel_clear_custom_args(args):
    """Run 'kernel clear_custom_args" subcommand"""

    # Make sure image can handle kernel arguments.
    assert_custom_kargs_compat_image(args.storage_directory)

    dtob_basename = os.path.splitext(KERNEL_SET_CUSTOM_ARGS_DTS_NAME)[0] + ".dtbo"

    res = dto_cli.dto_remove_single(
        dtob_basename, args.storage_directory, presence_required=False)
    if res:
        print("Custom kernel arguments successfully cleared.")
    else:
        # No arguments set: nothing wrong with that.
        log.info("No custom kernel arguments configured.")
        return


def assert_custom_kargs_compat_image(storage_dir):
    """Ensure image is capable of handling custom kernel argument.

    On return, caller can assume reference image does contain the code to handle
    custom kernel argument. If it does not, the program will exit.
    """

    uenv_txt_path = dt.get_current_uenv_txt_path(storage_dir)
    handling_code_found = False

    re_searched = re.compile(UENV_SET_CUSTOM_ARGS_FUNCTION_RE)

    with open(uenv_txt_path, 'r') as file:
        for line in file:
            if re_searched.match(line):
                handling_code_found = True
                break

    if not handling_code_found:
        log.error("The TorizonCore image you are customizing doesn't support "
                  "custom kernel arguments. Please update it to the latest "
                  "TorizonCore version.")
        sys.exit(1)


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
                                      help="Set the TorizonCore kernel arguments.")
    subparser.add_argument(metavar="KERNEL_ARGS", dest="kernel_args", nargs='+',
                           help="Kernel arguments to be added.")
    subparser.set_defaults(func=do_kernel_set_custom_args)

    # kernel get_custom_args
    subparser = subparsers.add_parser("get_custom_args",
                                      help="Get the TorizonCore kernel arguments.")
    subparser.set_defaults(func=do_kernel_get_custom_args)

    # kernel clear_custom_args
    subparser = subparsers.add_parser("clear_custom_args",
                                      help="Clear the TorizonCore kernel arguments.")
    subparser.set_defaults(func=do_kernel_clear_custom_args)
