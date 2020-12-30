import logging
import os
import shutil
import subprocess
import sys
import tempfile
import traceback

from tcbuilder.backend import dt
from tcbuilder.backend.common import checkout_git_repo
from tcbuilder.errors import TorizonCoreBuilderError

log = logging.getLogger("torizon." + __name__)


def do_dt_status(args):
    '''Perform the 'dt status' command.'''

    dtb_basename = dt.get_current_dtb_basename(args.storage_directory)
    if not dtb_basename:
        log.error("error: cannot identify the enabled device tree in the image because it is dynamically selected at runtime.")
        sys.exit(1)

    log.info(f"Current device tree is: {dtb_basename}")


def do_dt_checkout(args):
    '''Perform the 'dt checkout' command.'''
    storage_dir = os.path.abspath(args.storage_directory)

    # Retrieve the Toradex device-tree repository, if not already retrieved.
    if os.path.exists(os.path.abspath("device-trees")):
        log.error("'device-trees' directory already exists")
        return
    try:
        checkout_git_repo(storage_dir, None, None)
    except TorizonCoreBuilderError as ex:
        log.error(ex.msg)  # msg from all kinds of Exceptions
        if ex.det is not None:
            log.info(ex.det)  # more elaborative message
        log.debug(traceback.format_exc())  # full traceback to be shown for debugging only


def do_dt_apply(args):
    '''Perform the 'dt apply' command.'''

    # Sanity check parameters.
    assert args.dts_path, "panic: missing device tree source parameter"
    if not args.include_dirs:
        args.include_dirs = ["device-trees/include"]

    # Compile the device tree.
    with tempfile.NamedTemporaryFile(delete=False) as f:
        dtb_tmp_path = f.name
    if not dt.build_dts(args.dts_path, args.include_dirs, dtb_tmp_path):
        log.error(f"error: cannot apply {args.dts_path}.")
        sys.exit(1)

    # Deploy the device tree blob.
    dt_changes_dir = dt.get_dt_changes_dir(args.storage_directory)
    subprocess.check_call(f"rm -rf {dt_changes_dir}", shell=True)  # Erase device tree and overlays of the current session
    dtb_target_dir = os.path.join(dt_changes_dir, dt.get_dtb_kernel_subdir(args.storage_directory))
    os.makedirs(dtb_target_dir, exist_ok=True)
    dtb_target_basename = os.path.splitext(os.path.basename(args.dts_path))[0] + ".dtb"
    dtb_target_path = os.path.join(dtb_target_dir, dtb_target_basename)
    shutil.move(dtb_tmp_path, dtb_target_path)

    # Deploy the enablement of the device tree blob.
    uenv_target_dir = os.path.join(dt_changes_dir, "usr", "lib", "ostree-boot")
    os.makedirs(uenv_target_dir, exist_ok=True)
    uenv_target_path = os.path.join(uenv_target_dir, "uEnv.txt")
    with open(uenv_target_path, "w") as f:
        f.write(f"fdtfile={dtb_target_basename}\n")
    subprocess.check_call(f"set -o pipefail && ostree --repo={args.storage_directory}/ostree-archive cat base /usr/lib/ostree-boot/uEnv.txt | sed /^fdtfile=/d >>{uenv_target_path}", shell=True)

    # Deploy an empty overlays config file, so any overlays from the base image are disabled.
    with open(os.path.join(dtb_target_dir, "overlays.txt"), "w") as f:
        f.write("fdt_overlays=\n")

    # All set.
    log.info(f"Device tree {dtb_target_basename} successfully applied.")


def init_parser(subparsers):
    '''Initializes the 'dt' subcommands command line interface.'''

    parser = subparsers.add_parser("dt", description="Manage device trees", help="Manage device trees")
    subparsers = parser.add_subparsers(title='Commands', required=True, dest='cmd')

    # dt status
    subparser = subparsers.add_parser("status", description="Show the currently enabled device tree", help="Show the currently enabled device tree")
    subparser.set_defaults(func=do_dt_status)

    # dt checkout
    subparser = subparsers.add_parser("checkout", description="Checkout Toradex device tree and overlays repository", help="Checkout Toradex device tree and overlays repository")
    subparser.set_defaults(func=do_dt_checkout)

    # dt apply DEVICE_TREE
    subparser = subparsers.add_parser("apply", description="Compile and enable a device tree", help="Compile and enable a device tree")
    subparser.add_argument(metavar="DEVICE_TREE", dest="dts_path", help="Path to the device tree source file")
    subparser.add_argument("--include-dir", metavar="DIR", dest="include_dirs", action='append', help="Search directory for include files during device tree compilation. Can be passed multiple times. If absent, defaults to 'device-trees/include'.")
    subparser.set_defaults(func=do_dt_apply)

