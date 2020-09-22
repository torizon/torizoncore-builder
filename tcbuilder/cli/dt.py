import logging
import os
import gi
gi.require_version("OSTree", "1.0")
import traceback
from tcbuilder.errors import TorizonCoreBuilderError
from tcbuilder.backend import dt
from tcbuilder.backend.common import checkout_git_repo
from tcbuilder.errors import PathNotExistError, InvalidStateError
from tcbuilder.backend.overlay_parser import CompatibleOverlayParser

def dt_overlay_subcommand(args):
    log = logging.getLogger("torizon." + __name__)  # use name hierarchy for "main" to be the parent

    if args.overlays is None:
        log.error("no overlay is provided")
        return

    devicetree_bin = ""
    if args.devicetree_bin is None:
        # create list of available device trees in OSTree
        storage_dir = os.path.abspath(args.storage_directory)
        src_ostree_archive_dir = os.path.join(storage_dir, "ostree-archive")

        dt_list = dt.get_ostree_dtb_list(src_ostree_archive_dir)

        # check volume storage for devicetree
        storage_dt = dt.get_dt_changes_dir(None, storage_dir)
        if os.path.exists(storage_dt):
            dt_list.append({'path': storage_dt.rsplit("/", 1)[0],
                            'name': storage_dt.rsplit("/", 1)[1]})

        # ask user to select one
        print("Which one of the above available device tree is to be overlaid? [Number]:", end=" ")
        for item in enumerate(dt_list):
            if item[1]['name'] == storage_dt.rsplit("/", 1)[1]:
                log.info(f"{item[0]}. Volume: {item[1]['name']}")
            else:
                log.info(f"{item[0]}. OSTree: {item[1]['name']}")

        selection = int(input())
        selected_dt = os.path.join(dt_list[selection]['path'], dt_list[selection]['name'])

        log.info(f"Device tree {dt_list[selection]['name']} is to be overlaid")

        devicetree_bin = dt.create_copy_devicetree_bin(storage_dir, selected_dt)
    else:
        devicetree_bin = os.path.abspath(args.devicetree_bin)

    devicetree_out = ""
    if args.devicetree_out is not None:
        dt_out = os.path.abspath(args.devicetree_out)
        if not os.path.exists(dt_out):
            log.error(f"{args.devicetree_out} does not exist")
            return
        if os.path.exists(os.path.join(dt_out, "usr")):
            log.error(f"{args.devicetree_out} is not empty")
            return

    devicetree_out = dt.create_dt_changes_dir(args.devicetree_out, args.storage_directory)

    dt.build_and_apply(devicetree_bin, args.overlays, devicetree_out,
                       args.include_dir)

    if os.path.exists(os.path.join(storage_dir, "tmp_devicetree.dtb")):
        os.remove(os.path.join(storage_dir, "tmp_devicetree.dtb"))

    log.info(f"Overlays {args.overlays} successfully applied")

def dt_custom_subcommand(args):
    log = logging.getLogger("torizon." + __name__)  # use name hierarchy for "main" to be the parent

    devicetree_out = ""
    if args.devicetree_out is not None:
        devicetree_out = os.path.abspath(args.devicetree_out)
        if not os.path.exists(devicetree_out):
            raise PathNotExistError(f"{args.devicetree_out} does not exist")
        if os.path.exists(os.path.join(devicetree_out, "usr")):
            raise InvalidStateError(f"{args.devicetree_out} is not empty")

    devicetree_out = dt.create_dt_changes_dir(args.devicetree_out, args.storage_directory)

    dt.build_and_apply(args.devicetree, None, devicetree_out,
                       args.include_dir)

    log.info(f"Device tree {args.devicetree} built successfully")

def dt_checkout_subcommand(args):
    log = logging.getLogger("torizon." + __name__)  # use name hierarchy for "main" to be the parent

    storage_dir = os.path.abspath(args.storage_directory)

    if args.git_repo is None:
        if os.path.exists(os.path.abspath("device-trees")):
            log.error("'device-trees' directory already exists")
            return
    elif args.git_repo is not None:
        if args.git_branch is None:
            log.error("git branch is not provided")
            return
        elif (args.git_repo.startswith("https://") or
            args.git_repo.startswith("git://")):
            repo_name = args.git_repo.rsplit('/', 1)[1].rsplit('.', 1)[0]
            if os.path.exists(os.path.abspath(repo_name)):
                log.error(f"directory '{repo_name}' named as repo name should not exist")
                return
        elif not os.path.exists(os.path.abspath(args.git_repo)):
            log.error(f"{args.git_repo} directory does not exist")
            return

    try:
        checkout_git_repo(storage_dir, args.git_repo, args.git_branch)
        log.info("dt checkout completed successfully")
    except TorizonCoreBuilderError as ex:
        log.error(ex.msg)  # msg from all kinds of Exceptions
        if ex.det is not None:
            log.info(ex.det)  # more elaborative message
        log.debug(traceback.format_exc())  # full traceback to be shown for debugging only

def dt_list_overlays_subcommand(args):
    log = logging.getLogger("torizon." + __name__)  # use name hierarchy for "main" to be the parent

    if not os.path.exists(os.path.abspath(args.overlays_dir)):
        log.error(f"{args.overlays_dir} does not exist")
        return

    if args.devicetree is None and args.devicetree_bin is None:
        log.error("no devicetree file is provided")
        return

    if args.devicetree is not None and args.devicetree_bin is not None:
        log.error("provide either device tree source file or binary file")
        return

    if args.devicetree is not None and \
            not os.path.exists(os.path.abspath(args.devicetree)):
        log.error(f"{args.devicetree} does not exist")
        return

    if args.devicetree_bin is not None and \
        not os.path.exists(os.path.abspath(args.devicetree_bin)):
        log.error(f"{args.devicetree_bin} does not exist")
        return

    overlays_path = os.path.abspath(args.overlays_dir)

    parser = CompatibleOverlayParser()
    compatibilities = []
    if args.devicetree_bin is not None:
        compatibilities = parser.get_compatibilities_binary(args.devicetree_bin)
    else:
        compatibilities = parser.get_compatibilities_source(args.devicetree)

    compatible_overlays = []
    for path in sorted(os.listdir(overlays_path)):
        if path.endswith(".dts"):
            overlay_path = os.path.join(overlays_path, path)
            if os.path.isfile(overlay_path):
                if parser.check_compatibility(compatibilities, overlay_path):
                    compatible_overlays.append(path)

    if compatible_overlays:
        log.info("Available overlays are:")
        for compatible_overlay in compatible_overlays:
            log.info(f"\t {compatible_overlay}")

        log.info(parser.parse(overlay_path))
    else:
        log.info("no compatible overlay found")

def add_overlay_parser(parser):
    subparsers = parser.add_subparsers(title='Commands:', required=True, dest='cmd')
    subparser = subparsers.add_parser("overlay", help="Apply an overlay")
    subparser.add_argument("--devicetree", dest="devicetree_bin",
                           help="Path to the devicetree binary")
    subparser.add_argument("--devicetree-out", dest="devicetree_out",
                           help="""Path to the devicetree output directory. 
                           Device tree file is stored with name 'devicetree'.""")
    subparser.add_argument("--include-dir", dest="include_dir", action='append',
                           help="""Directory with device tree include (.dtsi) or
                           header files. Can be passed multiple times.""",
                           required=True)
    subparser.add_argument(metavar="overlays", dest="overlays", nargs="+",
                           help="The overlay(s) to apply")

    subparser.set_defaults(func=dt_overlay_subcommand)

    subparser = subparsers.add_parser("custom", help="Compile device tree")
    subparser.add_argument("--devicetree", dest="devicetree",
                           help="Path to the devicetree file",
                           required=True)
    subparser.add_argument("--devicetree-out", dest="devicetree_out",
                           help="""Path to the devicetree output directory.
                           Device tree file is stored with name 'devicetree'.""")
    subparser.add_argument("--include-dir", dest="include_dir", action='append',
                           help="""Directory with device tree include (.dtsi) or
                           header files. Can be passed multiple times.""",
                           required=True)

    subparser.set_defaults(func=dt_custom_subcommand)

    subparser = subparsers.add_parser("checkout", help="checkout a git branch from remote repository")
    subparser.add_argument("--repository", dest="git_repo",
                           help="""Remote repository URL. Default repo is
                           https://github.com/toradex/device-trees""")
    subparser.add_argument("--branch", dest="git_branch",
                           help="""Branch to be checked out. Default branch with default repo is
                           toradex_<kmajor>.<kminor>.<x>""")

    subparser.set_defaults(func=dt_checkout_subcommand)

    subparser = subparsers.add_parser("list-overlays", help="list overlays")
    subparser.add_argument("--devicetree", dest="devicetree",
                           help="Device tree source file")
    subparser.add_argument("--devicetree-bin", dest="devicetree_bin",
                           help="Device tree binary file")
    subparser.add_argument("--overlays-dir", dest="overlays_dir",
                           help="Path to overlays directory",
                           required=True)

    subparser.set_defaults(func=dt_list_overlays_subcommand)

def init_parser(subparsers):
    subparser = subparsers.add_parser("dt", help="""\
    Compile and apply device trees and device tree overlays.
    """)

    add_overlay_parser(subparser)
