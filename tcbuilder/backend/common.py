import ipaddress
import json
import logging
import os
import re
import socket
import subprocess
import sys
import time
import threading
import binascii
import glob
import shutil
import tempfile

from typing import Optional
from contextlib import contextmanager
from datetime import datetime
from urllib.request import urlretrieve

import git
import dns.resolver
import ifaddr
import guestfs
import requests

from docker import DockerClient
from docker.errors import NotFound
from gi.repository import GLib

import tezi.utils

from tezi.image import ImageConfig
from tcbuilder.backend import ostree
from tcbuilder.errors import \
    (FileContentMissing, GitRepoError, ImageUnpackError, InvalidDataError, InvalidStateError,
     LicenceAcceptanceError, OperationFailureError, PathNotExistError, TorizonCoreBuilderError,
     IntegrityCheckFailed, ParseError)

log = logging.getLogger("torizon." + __name__)

DOCKER_BUNDLE_TARNAME = "docker-storage.tar"

# Mapping from architecture to a Docker platform.
ARCH_TO_DOCKER_PLAT = {
    "aarch64": "linux/arm64",
    "arm": "linux/arm/v7",
    "x86_64": "linux/amd64"
}

DEFAULT_DOCKER_PLATFORM = "linux/arm/v7"

DEFAULT_RAW_ROOTFS_LABEL = "otaroot"

TEZI_PROP_TO_ARGNAME = {
    "name": "--image-name",
    "description": "--image-description",
    "accept_licence": "--image-accept-licence",
    "autoinstall": "--image-autoinstall",
    "autoreboot": "--image-autoreboot",
    "licence_file": "--image-licence",
    "release_notes_file": "--image-release-notes"
}

RAW_PROP_TO_ARGNAME = {
    "raw_rootfs_label": "--raw-rootfs-label"
}

RAW_PROP_DEFAULTS = {
    "raw_rootfs_label" : DEFAULT_RAW_ROOTFS_LABEL
}

TAR_EXT_TO_PROGRAM = {
    ".gz": "gzip",
    ".gzip": "gzip",
    ".tgz": "gzip",
    ".xz": "xz",
    ".bz2": "bzip2",
    ".lzo": "lzop",
    ".tar": None
}

DEFAULT_SERVER_NAME = "frankfurt"

DEFAULT_SRC = "torizoncore-oe"

RELEASE_TO_PROD_MAP = {
    "nightly": "prerelease",
    "monthly": "prerelease",
    "quarterly": "prod"
}
RELEASE_TO_DEVEL_MAP = {
    "nightly": "-devel-",
    "monthly": "-devel-",
    "quarterly": ""
}
RELEASE_TO_BUILD_TYPE_MAP = {
    "nightly": "nightly",
    "monthly": "monthly",
    "quarterly": "release"
}
MAJOR_TO_YOCTO_MAP = {
    5: "dunfell-5.x.y",
    6: "kirkstone-6.x.y",
    7: "scarthgap-7.x.y"
}

SYNAIMG_MACHINES = ("luna-sl1680", "sl1680")

COMMON_TORIZON_TO_SRC = {
    "am62lxx-evm": "common-torizon-ti-oe",
    "am62pxx-evm": "common-torizon-ti-oe",
    "am62xx-evm": "common-torizon-ti-oe",
    "beagley-ai": "common-torizon-ti-oe",
    "intel-corei7-64": "common-torizon-x86-oe",
    "luna-sl1680": "common-torizon-syn-oe",
    "sl1680": "common-torizon-syn-oe"
}

LEGACY_VARIANT_PREFIX = "torizon-core-"
VARIANT_PREFIX = "torizon-"

DEFAULT_LEGACY_IMAGE_VARIANT = LEGACY_VARIANT_PREFIX + "docker"
DEFAULT_IMAGE_VARIANT = VARIANT_PREFIX + "docker"

#  Hex value taken from the Devicetree Specification available at:
#  https://devicetree-specification.readthedocs.io/en/stable/flattened-format.html
FDT_HEADER_MAGIC = "d00dfeed"

REMOTE_CMD_TIMEOUT = 90

SECBOOT_ARTIFACTS_DIR = "/storage/secboot_tracked_artifacts"

OSTREE_ROOT_DEPLOY_PATH = "ostree/deploy/torizon/deploy/{csum}"

OSTREE_SOTA_DIR_PATH = "/ostree/deploy/torizon/var/sota"


def get_storage_dir():
    """Get the absolute path of the "storage" directory."""
    return os.path.abspath(os.environ.get("TCB_STORAGE_DIR", "/storage"))


def set_storage_dir(storage_dir):
    """Set the path to the "storage" directory."""
    os.environ["TCB_STORAGE_DIR"] = storage_dir


def get_src_sysroot_dir():
    """Get the path to the source sysroot."""
    storage_dir = get_storage_dir()
    return os.path.join(storage_dir, "sysroot")


def get_src_ostree_dir():
    """Get the path to the ostree repository in the source sysroot."""
    src_sysroot = get_src_sysroot_dir()
    return os.path.join(src_sysroot, "ostree", "repo")


# TODO: Use this function everywhere instead of hardcoding "ostree-archive".
def get_int_ostree_dir():
    """Get the path to the internal (archive) ostree repository."""
    storage_dir = get_storage_dir()
    return os.path.join(storage_dir, "ostree-archive")


# Based on this solution: https://stackoverflow.com/a/50690347
# Usage of Event object to stop thread was based on:
# https://www.pythontutorial.net/python-concurrency/python-stop-thread/
# imports needed: sys, time, threading
def run_with_loading_animation(func=None, args=(), kwargs=None,
                               loading_msg="Loading...", end_msg="Done."):
    """
    Run given function func(*args, **kwargs) while displaying a loading animation
    on the terminal, and print an end message after the function finishes running.

    :param func: Function to be executed
    :param args: Tuple of arguments related to func
    :param kwargs: Dictionary of keyword arguments related to func
    :param loading_msg: String to be displayed when func is running
    :param end_msg: String to print after func finishes execution

    :return:
        What func returns, or 'None' if func doesn't return anything.
    """

    ret = None

    # kwargs has None as default value due to pylint
    # warning dangerous-default-value if the default
    # is an empty dictionary
    kwargs_ = kwargs if kwargs is not None else {}

    event = threading.Event()

    # Don't print spinner if stdout isn't a terminal
    if sys.stdout.isatty():
        run_target = print_spinner_animation
    else:
        run_target = None

    thread = threading.Thread(target=run_target, args=(event,))

    log.debug(loading_msg)
    print(loading_msg, end='')

    thread.start()
    try:
        ret = func(*args, **kwargs_)
    except Exception as exc:
        end_msg = "Error!"
        raise exc
    finally:
        event.set()
        thread.join()
        print(f" {end_msg}")

    return ret


def print_spinner_animation(event):
    """
    Print spinner animation indefinitely until event flag is set with event.set().
    This function was developed to be executed using the threading.Thread class.

    :param event: Event object
    """
    chars = "/—\\|"
    while True:
        for char in chars:
            sys.stdout.write(char + '  ')
            sys.stdout.flush()
            time.sleep(.1)
            sys.stdout.write('\b\b\b')
            sys.stdout.flush()
        if event.is_set():
            break


def get_rootfs_tarball(tezi_image_dir):
    if not os.path.exists(tezi_image_dir):
        raise PathNotExistError(f"Source image {tezi_image_dir} directory does not exist")

    image_json_filepath = os.path.join(tezi_image_dir, "image.json")

    with open(image_json_filepath, "r", encoding="utf-8") as jsonfile:
        jsondata = json.load(jsonfile)

    # Find root file system content
    content = tezi.utils.find_rootfs_content(jsondata)
    if content is None:
        raise FileContentMissing(f"No root file system content section found in {jsonfile}")

    return os.path.join(tezi_image_dir, content["filename"])


def add_bundle_directory_argument(parser):
    """
    Add the --bundle-directory argument to a parser of a command.

    :param parser: A parser of a command line.
    """
    parser.add_argument(
        "--bundle-directory",
        dest="bundle_directory",
        default="bundle",
        help="Container bundle directory")


def add_common_tezi_image_arguments(subparser, argparse):
    subparser.add_argument(TEZI_PROP_TO_ARGNAME["name"], dest="image_name",
                           help=("(Easy Installer images only) Image name to be used in Easy "
                                 "Installer image json."))
    subparser.add_argument(TEZI_PROP_TO_ARGNAME["description"], dest="image_description",
                           help=("(Easy Installer images only) Image description to be used in "
                                 "Easy Installer image json."))
    subparser.add_argument(TEZI_PROP_TO_ARGNAME["licence_file"], dest="licence_file",
                           help=("(Easy Installer images only) Licence file which will be "
                                 "shown on image installation."))
    subparser.add_argument(TEZI_PROP_TO_ARGNAME["accept_licence"], dest="image_accept_licence",
                           action=argparse.BooleanOptionalAction,
                           help=("(Easy Installer images only) Automatically accept the "
                                 "image licence present in the input image or set by "
                                 "--image-licence; Licence should be accepted every time an "
                                 "image is generated."))
    subparser.add_argument(TEZI_PROP_TO_ARGNAME["release_notes_file"], dest="release_notes_file",
                           help=("(Easy Installer images only) Release notes file which "
                                 "will be shown on image installation."))
    subparser.add_argument(TEZI_PROP_TO_ARGNAME["autoinstall"], dest="image_autoinstall",
                           action=argparse.BooleanOptionalAction,
                           help=("(Easy Installer images only) Automatically install "
                                 "image upon detection by Toradex Easy Installer."))
    subparser.add_argument(TEZI_PROP_TO_ARGNAME["autoreboot"], dest="image_autoreboot",
                           action=argparse.BooleanOptionalAction,
                           help=("(Easy Installer images only) Enable automatic reboot "
                                 "after image is flashed by Toradex Easy Installer."))


def add_common_raw_image_arguments(subparser):
    subparser.add_argument(RAW_PROP_TO_ARGNAME["raw_rootfs_label"], dest="raw_rootfs_label",
                           metavar="LABEL", help="(raw images only) rootfs filesystem label of "
                                                 "source WIC/raw image. "
                                                 f"(default: {DEFAULT_RAW_ROOTFS_LABEL})",
                           default=None) # Default is in RAW_PROP_DEFAULTS. Default should only be
                                         # set if arg is used in a raw image.
                                         # Arg value should remain None if a tezi image is used.


def add_ssh_arguments(subparser):
    """
    Add the ssh arguments: username, password and port.

    --remote-username (Default:torizon)
    --remote-password (Default:torizon)
    --remote-port (Default:22)
    """
    subparser.add_argument("--remote-username",
                           dest="remote_username",
                           help="Username of remote machine (default value "
                                "is torizon)",
                           default="torizon")
    subparser.add_argument("--remote-password",
                           dest="remote_password",
                           help="Password of remote machine (default value "
                                "is torizon)",
                           default="torizon")
    subparser.add_argument("--remote-port",
                           dest="remote_port",
                           help="SSH port (default value is 22)",
                           default=22,
                           type=int)


def add_common_registry_arguments(subparser):
    """
    Add the registry arguments: login, login-to and cacert-to.

    --login (USERNAME PASSWORD)
    --login-to (REGISTRY USERNAME PASSWORD)
    --cacert-to (REGISTRY CACERT)
    """
    subparser.add_argument(
        "--login", nargs=2, dest="main_login",
        metavar=('USERNAME', 'PASSWORD'),
        help=("Request that the tool logs in to the default [Docker Hub] "
              "registry using specified USERNAME and PASSWORD."))
    subparser.add_argument(
        "--login-to", nargs=3, action="append", dest="extra_logins", default=[],
        metavar=('REGISTRY', 'USERNAME', 'PASSWORD'),
        help=("Request that the tool logs in to registry REGISTRY using "
              "specified USERNAME and PASSWORD (can be employed multiple times)."))
    subparser.add_argument(
        "--cacert-to", nargs=2, action="append", dest="cacerts", default=[],
        metavar=('REGISTRY', 'CERTIFICATE'),
        help=("Define a root CA CERTIFICATE (path to file in PEM format) "
              "to be used for validating the certificate of the specified "
              "secure REGISTRY (when connecting to it)."))


def get_unpack_command(filename):
    """Get shell command to unpack a given file format"""
    cmd = "cat"
    if filename.endswith(".gz") or filename.endswith(".tgz"):
        cmd = "gzip -dc"
    elif filename.endswith(".xz"):
        cmd = "xz -dc"
    elif filename.endswith(".lzo"):
        cmd = "lzop -dc"
    elif filename.endswith(".zst"):
        cmd = "zstd -dc"
    elif filename.endswith(".lz4"):
        cmd = "lz4 -dc"
    elif filename.endswith(".bz2"):
        cmd = "bzip2 -dc"
    return cmd


def get_tar_compress_program_options(filename):
    """ Get array with options to pass to tar to decompress given file format. """
    cmd = get_unpack_command(filename)
    # Tar adds a -d option to the command passed, but cat does not
    # accept this, so omit the --use-compress-program entirely in this
    # case.
    if cmd == "cat":
        return []
    return ["--use-compress-program", cmd]


def get_all_local_ip_addresses():
    """
    Get all local IP addresses on this host except the ones assigned to the
    "lo" and "docker0" intefaces.

    Returns:
        list -- List of IP addresses.
    """

    local_ip_addresses = []
    for adapter in ifaddr.get_adapters():
        if not adapter.nice_name in ('lo', 'docker0'):
            for ipaddr in adapter.ips:
                if isinstance(ipaddr.ip, str):  # If it's an str it's an IPv4.
                    local_ip_addresses.append(ipaddr.ip)
                else:
                    local_ip_addresses.append(ipaddr.ip[0])
    return local_ip_addresses


def resolve_hostname(hostname: str, mdns_source: Optional[str] = None) -> (str, bool):
    """
    Convert a hostname to ip using operating system's name resolution service
    first and fallback to mDNS if the hostname is (or can be) a mDNS host name.
    If it does not resolve it, returns the original value (in
    case this may be parsed in some smarter ways down the line)

    Arguments:
        hostname {str} -- mnemonic name
        mdns_source {Optional[str]} -- source interface used for mDNS multicasts

    Returns:
        str -- IP address as string
        bool - true id mdns has been used
    """

    try:
        ip_addr = socket.gethostbyname(hostname)
        return ip_addr, False
    except socket.gaierror as sgex:
        # If its a mDNS compatible hostname, ignore regular resolve issues
        # and try mDNS next
        if not hostname.endswith(".local") and "." in hostname:
            raise TorizonCoreBuilderError(f'Resolving hostname "{hostname}" failed.') from sgex

    if hostname.endswith(".local"):
        mdns_hostname = hostname
    else:
        mdns_hostname = hostname + ".local"

    # Configure Resolver manually for mDNS operation
    resolver = dns.resolver.Resolver(configure=False)
    resolver.nameservers = ["224.0.0.251"]  # mDNS IPv4 link-local multicast address
    resolver.port = 5353  # mDNS port
    if mdns_source:
        try:
            addr = resolver.query(mdns_hostname, "A", lifetime=3, source=mdns_source)
            if addr is None or len(addr) == 0:
                raise TorizonCoreBuilderError("Resolving mDNS address failed with no answer")

            ip_addr = addr[0].to_text()
            return ip_addr, True
        except dns.exception.Timeout as dnsex:
            raise TorizonCoreBuilderError(
                f'Resolving hostname "{mdns_hostname}" using mDNS failed.') from dnsex
    else:
        mdns_addr = None
        for local_ip in get_all_local_ip_addresses():
            try:
                mdns_addr = resolver.query(mdns_hostname, "A", lifetime=3, source=local_ip)
            except dns.exception.Timeout:
                pass
            else:
                break
        if mdns_addr:
            return mdns_addr[0].to_text(), True

        raise TorizonCoreBuilderError(
            f'Resolving hostname "{mdns_hostname}" using mDNS on all interfaces failed.')


def resolve_remote_host(remote_host, mdns_source=None):
    """Resolve given host to IP address if host is not an IP address already"""
    try:
        _ip_obj = ipaddress.ip_address(remote_host)
        return remote_host
    except ValueError:
        # This seems to be a host name, let's try to resolve it
        ip_addr, _mdns = resolve_hostname(remote_host, mdns_source)
        return ip_addr


def get_branch_and_major_from_metadata():
    """Get the kernel branch and image major version from the OSTree metadata"""

    storage_dir = get_storage_dir()
    src_sysroot_dir = os.path.join(storage_dir, "sysroot")
    src_sysroot = ostree.load_sysroot(src_sysroot_dir)
    csum, _kargs = ostree.get_deployment_info_from_sysroot(src_sysroot)
    metadata, _subject, _body = ostree.get_metadata_from_checksum(src_sysroot.repo(), csum)

    if "oe.kernel-source" not in metadata or not isinstance(metadata["oe.kernel-source"], tuple):
        raise TorizonCoreBuilderError(
            "OSTree metadata are missing the kernel source branch name. Use "
            "--branch to manually specify the kernel branch used by this image.")

    _kernel_repo, kernel_branch, _kernel_revision = metadata["oe.kernel-source"]
    version_major = int(metadata['oe.tdx-major'])
    return kernel_branch, version_major


def get_tezi_image_version(input_dir):
    """Get the image version of a tezi image directory by looking at image.json

    :param input_dir: tezi image directory path

    :return:
        A tuple with the int values of the major, minor and patch number
        of the image, in this order. If unable to determine a number,
        the tuple entry will be 'None'.
    """
    image_json_path = os.path.join(input_dir, "image.json")

    with open(image_json_path, "r", encoding="utf-8") as image_json_file:
        image_json_str = image_json_file.read()

    try:
        image_json_obj = json.loads(image_json_str)
    except (binascii.Error, json.decoder.JSONDecodeError) as exc:
        raise TorizonCoreBuilderError(
            "Failure decoding image.json: aborting.") from exc

    # Auxiliary function
    def convert_to_int_else_none(string):
        try:
            int_value = int(string)
        except ValueError:
            return None
        return int_value

    major = convert_to_int_else_none(image_json_obj['version'].split('.')[0])
    minor = convert_to_int_else_none(image_json_obj['version'].split('.')[1])
    patch = convert_to_int_else_none(
        image_json_obj['version'].split('.')[2].split('-')[0].split('+')[0])

    return major, minor, patch


def update_dt_git_repo():
    """Update the device-trees Git repository"""
    try:
        repo_obj = git.Repo(os.path.abspath("device-trees"))
        sha = repo_obj.head.object.hexsha
        repo_obj.remotes["origin"].fetch()
        repo_obj.remotes["origin"].pull()
        set_output_ownership("device-trees")
        log.info("'device-trees' is already up to date"
                 if sha == repo_obj.head.object.hexsha
                 else "'device-trees' successfully updated")
    except git.GitError as error:
        raise GitRepoError(error) from error


def checkout_dt_git_repo(*, git_repo=None, git_branch=None):
    """Checkout the device-trees Git repository

    This function will clone a git_repo and checkout a chosen branch. If no
    git repo is given, the default device-trees repository will be used. If no branch
    is given, the branch name will be read from the OSTree metadata.

    :param git_repo: The git repository to clone from. If None, the default
    :param git_branch: The git branch to checkout.
    """

    if git_branch is None:
        git_branch, image_major_version = get_branch_and_major_from_metadata()

        if image_major_version >= 6:
            raise TorizonCoreBuilderError(
                "The dt checkout command is not supported on TorizonCore 6 and newer. "
                "Learn how to clone the device trees and overlays repositories on "
                "https://developer.toradex.com/torizon/os-customization/use-cases/"
                "device-tree-overlays-on-torizon/#"
                "clone-the-toradex-repositories-and-check-the-available-device-trees-and-overlays")

    if git_repo is None:
        repo_obj = git.Repo.clone_from("https://github.com/toradex/device-trees",
                                       "device-trees")
    elif git_repo.startswith("https://") or git_repo.startswith("git://"):
        directory_name = git_repo.rsplit('/', 1)[1].rsplit('.', 1)[0]
        repo_obj = git.Repo.clone_from(git_repo, directory_name)
    else:
        repo_obj = git.Repo(git_repo)

    if repo_obj.bare:
        raise GitRepoError("git repo seem to be empty.")

    # Checkout branch if necessary
    if git_branch not in repo_obj.refs:
        ref = next((rref for rref in repo_obj.remotes["origin"].refs
                    if rref.remote_head == git_branch), None)
        if ref is None:
            raise GitRepoError(f"Branch name {git_branch} does not exist in upstream repository.")
        ref.checkout(b=git_branch)

    repo_obj.close()


def _progress(blocknum, blocksiz, totsiz, totbarsiz=40):
    if not sys.stdout.isatty():
        return

    if totsiz in [0, -1]:
        totread = (blocknum * blocksiz) // (1024*1024)
        sys.stdout.write(f"\rDownloading file: {totread} MB...")
        sys.stdout.flush()
    else:
        barsiz = int(min((blocknum * blocksiz) / (totsiz), 1.0) * totbarsiz)
        sys.stdout.write("\r[" + ("=" * barsiz) + ("." * (totbarsiz - barsiz)) + "] ")
        sys.stdout.flush()


@contextmanager
def download_progress():
    """Context manager supplying a urlretrieve reporthook"""
    is_tty = sys.stdout.isatty()
    try:
        yield _progress if is_tty else None
    finally:
        if is_tty:
            try:
                sys.stdout.write("\n")
                sys.stdout.flush()
            # pylint: disable-next=broad-exception-caught
            except Exception:
                pass


def get_file_sha256sum(path):
    """Get SHA-256 checksum of a file"""
    # Run external program - output is like this:
    # c81be3dc13de2bd6e13da015e7822a4719aca3cc7434f24b564e40ff8c632a36 <fname>
    text = subprocess.check_output(
        ["sha256sum", path],
        text=True, stderr=subprocess.STDOUT)
    parts = re.split(r"\s+", text)
    # Sanity checks:
    assert (len(parts) >= 2) and (len(parts[0]) == 64)
    # Return the SHA-256 checksum
    return parts[0]


def get_own_container_id(
        docker_client, image_name="torizoncore-builder", env_var="TCB_CONTAINER_NAME"):
    """Determine ID of current container

    This function tries to find a container with the name specified by environment
    variable whose name is specified by `env_var` (if that variable is set) or with
    an image name containing the substring defined by `image_name`.
    """

    # Use environment variable if available.
    if env_var in os.environ:
        container_id = None
        container_name = os.environ[env_var]
        filters = {"name": container_name}
        for container in docker_client.containers.list(filters=filters):
            # Sanity check: this condition should never occur.
            assert container_id is None, \
                "Found more than one container with the same name"
            container_id = container.attrs["Id"]

        if container_id is not None:
            log.debug(f"Current container ID (found by container name): {container_id}")
            return container_id

        log.warning("couldn't determine ID of container (container name method)")

    # Try to find container with a certain image name:
    container_id = None
    for container in docker_client.containers.list():
        if image_name in container.attrs["Config"]["Image"]:
            assert container_id is None, \
                f"Found more than one *{image_name}* container"
            container_id = container.attrs["Id"]

    if container_id is not None:
        log.debug(f"Current container ID (found by image name): {container_id}")
        return container_id

    raise OperationFailureError("Can't determine current container ID.")


def get_host_workdir():
    """Get location of working directory w.r.t. the host"""

    docker_client = DockerClient.from_env()
    container_id = get_own_container_id(docker_client)

    try:
        container = docker_client.containers.get(container_id)
    except NotFound as exc:
        raise OperationFailureError(
            "Can't retrieve container information from docker.") from exc

    mounts = container.attrs["Mounts"]
    for mount in mounts:
        if mount["Destination"] == "/workdir":
            if "Name" in mount:
                # A Docker volume is mapped to the workdir.
                return (mount["Name"], mount["Type"], True)
            # A real directory is mapped to the workdir.
            return (mount["Source"], mount["Type"], False)

    return None, None


def get_arch_from_ostree(ref="base"):
    """Determine architecture from OSTree metadata"""

    storage_dir = get_storage_dir()
    src_ostree_archive_dir = os.path.join(storage_dir, "ostree-archive")
    if not os.path.isdir(src_ostree_archive_dir):
        raise InvalidStateError(
            f"Source OSTree archive ({src_ostree_archive_dir}) does not exist!")
    srcrepo = ostree.open_ostree(src_ostree_archive_dir)
    ret, csumdeploy = srcrepo.resolve_rev(ref, False)
    if not ret:
        raise TorizonCoreBuilderError(f"Error resolving {ref}.")
    srcmeta, _subject, _body = ostree.get_metadata_from_ref(srcrepo, csumdeploy)
    return srcmeta.get("oe.arch")


def get_docker_platform():
    """Determine platform for accessing a Docker registry

    The information is mapped from the architecture field in the OSTree
    metadata.
    """

    oe_arch = get_arch_from_ostree()
    if oe_arch not in ARCH_TO_DOCKER_PLAT:
        raise InvalidDataError(
            f"Unknown architecture {oe_arch} in OSTree metadata")
    return ARCH_TO_DOCKER_PLAT[oe_arch]


def check_valid_tezi_image(image_directory):
    """
    Check if the image directory has a valid TEZI image.

    :param image_directory: Directory with a TEZI image.
    :raises:
        PathNotExistError: if image_directory path does not exist.
        InvalidDataError: if image_directory has an invalid TEZI image.
    :return:
        The absolute image directory path
    """

    image_dir = os.path.abspath(image_directory)
    if not os.path.exists(image_dir):
        raise PathNotExistError(
            f"Source image directory {image_directory} does not exist")

    tarfile = ""
    try:
        tarfile = get_rootfs_tarball(image_dir)
    except (FileNotFoundError, FileContentMissing) as exc:
        raise InvalidDataError(
            f"Error: directory {image_directory}"
            " does not contain a valid TEZI image") from exc

    if not os.path.exists(tarfile):
        raise InvalidDataError(
            "Error: "
            f"directory {image_directory} does not contain a valid TEZI image")

    return image_dir


def apply_workdir_ownership(filename, workdir_uid, workdir_gid):
    """
    Apply working directory ownership to filename but only if it does belong
    to "root:root". Doing this we could be pretty confident that filename
    has been generated by TorizonCore Builder.

    :param filename: File or directory name to apply ownership to.
    :param workdir_uid: Working directory UID.
    :param workdir_gid: Working directory GID.
    """

    file_uid, file_gid = get_file_ownership(filename)

    if file_uid == 0 and file_gid == 0:
        os.chown(filename, workdir_uid, workdir_gid, follow_symlinks=False)


def get_file_ownership(filename):
    """
    Get filename UID and GID.

    :param filename: File or directory name to get ownership from.
    :return: File user and group IDs.
    """

    stat = os.stat(filename, follow_symlinks=False)
    return stat.st_uid, stat.st_gid


def set_output_ownership(output_file, set_parents=False):
    """
    Set ownership for any file and/or directory to the same ownership of
    TorizonCore Builder "working directory", but only if this ownership
    is equal to "root:root". This way all output files generated by the
    TorizonCore Builder container will be accessible by the user on the
    host machine.

    :param output_file: Output file or directory inside "/workdir"
    :param set_parents: If True, set also the ownership of all parent
                        directories in `output_file` (this is done only
                        if `output_file` is a relative path).
    """

    workdir_uid, workdir_gid = get_file_ownership('/workdir')

    if set_parents and not os.path.isabs(output_file):
        parts = os.path.normpath(output_file).split(os.sep)
        for num in range(len(parts) - 1):
            apply_workdir_ownership(
                os.sep.join(parts[:num + 1]), workdir_uid, workdir_gid)

    apply_workdir_ownership(output_file, workdir_uid, workdir_gid)

    for rootdir, directories, filenames in os.walk(output_file):
        for filename in directories + filenames:
            apply_workdir_ownership(os.path.join(rootdir, filename),
                                    workdir_uid, workdir_gid)


def images_unpack_executed():
    """
    Check both, if the storage directory exists and if a "torizoncore-builder
    images unpack command" was executed previously.

    :raises:
        PathNotExistError: if the storage directory does not exist.
        ImageUnpackError: if "images unpack" was not executed previously.
    """

    storage_dir = get_storage_dir()
    if not os.path.exists(storage_dir):
        raise PathNotExistError(
            f"Storage directory \"{storage_dir}\" does not exist.")

    image_dirs = ("ostree-archive", "sysroot")

    for image_dir in image_dirs:
        if not os.path.exists(os.path.join(storage_dir, image_dir)):
            raise ImageUnpackError()


def unpacked_image_type():
    """
    Check if unpacked image is of type 'tezi' or 'wic' by
    looking if the storage has a directory named tezi.
    This function should always run after images_unpack_executed()

    :raises:
        PathNotExistError: if the storage directory does not exist.
    :return: "tezi" or "wic", depending on the image
    """

    storage_dir = get_storage_dir()
    if not os.path.exists(storage_dir):
        raise PathNotExistError(
            f"Storage directory \"{storage_dir}\" does not exist.")

    if os.path.exists(os.path.join(storage_dir, "tezi")):
        return "tezi"

    return "raw"


def fail_on_raw_image(message):
    """Throw error if the unpacked image is of type WIC/raw.

    :param message: Message string for exception to be thrown.
    """
    if unpacked_image_type() == "raw":
        raise InvalidDataError(message)


def image_has_cfs_support(ostree_dir=None):
    """Determine if the image has composefs support.

    :param ostree_dir: If specified, defines the path to the OSTree repository
        whose configuration will be checked. When not specified, the check is
        performed on the repo belonging to the original sysroot in the image
        (source repository).
    """
    ostree_dir = ostree_dir or get_src_ostree_dir()
    repo = ostree.open_ostree(ostree_dir)
    conf = repo.get_config()

    res = False
    try:
        val = conf.get_string("ex-integrity", "composefs")
        val = val.lower()
        if val in ["true", "yes", "1"]:
            res = True
        elif val in ["false", "no", "0"]:
            res = False
        else:
            log.debug("ex-integrity.composefs='%s' will be assumed as False", val)
    except GLib.GError as _exc:
        pass

    return res


def get_own_network():
    """ Determine Network mode of current tcb container
    Given the host `docker_client`. This function returns
    the network mode of this instance of the tcb container.
    """
    host_client = DockerClient.from_env()
    tcb_id = get_own_container_id(host_client)
    try:
        tcb = host_client.containers.get(tcb_id)
    except NotFound as exc:
        raise OperationFailureError(
            "Can't retrieve container information from docker.") from exc

    network = tcb.attrs["HostConfig"]["NetworkMode"]
    if network == "default":
        network = "bridge"

    return network


def check_licence_acceptance(image_dir, tezi_props):
    if tezi_props.get("accept_licence"):
        return

    image_json_filepath = os.path.join(image_dir, "image.json")

    if not os.path.exists(image_json_filepath):
        log.warning("Missing \"image.json\" File")
        return

    image_json = ImageConfig(image_json_filepath)

    if image_json.get("license") is None and tezi_props.get("licence_file") is None:
        return

    licence_file = tezi_props.get("licence_file") or image_json.get("license")
    licence_file = os.path.basename(licence_file)

    if image_json.get("autoinstall") or tezi_props.get("autoinstall"):
        raise LicenceAcceptanceError(
            f"Error: To enable the auto-installation feature you must accept the licence "
            f"\"{licence_file}\".")


def validate_compose_file(compose_file_data):
    """
    Validate the Docker compose file and throw an exception if the file is invalid.

    :param compose_file_data: The Docker compose file data as a dictionary
    """

    if not (isinstance(compose_file_data, dict) and
            isinstance(compose_file_data.get('services'), dict)):
        raise InvalidDataError("Error: No 'services' section in compose file.")

    for svc_name, svc_spec in compose_file_data['services'].items():
        image_name = svc_spec.get('image')
        if not image_name:
            raise InvalidDataError(f"Error: No image specified for service '{svc_name}'.")


def is_tcb_container_64bit():
    return sys.maxsize > 2**32


def check_if_file_exists(filename, directory):
    """Check if file exists in a given directory. Raises an error if the file is not found.

    :param filename: Name of the file
    :param directory: Path of directory to search for the file
    :returns: The file path of the result
    """

    log.debug(f"Checking for {filename} in {directory}...")
    file_list = glob.glob(os.path.join(directory, filename))

    list_len = len(file_list)

    if list_len <= 0:
        raise FileContentMissing(f"Could not find '{filename}' in '{directory}'. Aborting.")
    if list_len >= 2:
        log.debug(f"Found more than one match for '{filename}' in '{directory}'. "
                  f"Choosing {file_list[0]}.")

    return file_list[0]


def is_file_type_dtb(file_path):
    """
    Check if the file located in file_path is in DTB format by looking at the first bytes
    of the file, which must be the value FDT_HEADER_MAGIC.
    This can be used to quickly check if a binary is a Device Tree Blob or a Flattened Image
    Tree (FIT) file.

    :param file_path: Path of the file to be checked.
    :returns: True if the first bytes of the file match FDT_HEADER_MAGIC, False otherwise.
    """

    expected_value = bytes.fromhex(FDT_HEADER_MAGIC)
    value_length = len(expected_value)

    with open(file_path, "rb") as _file:
        found_value = _file.read(value_length)

    return found_value == expected_value


def is_file_type_fit(file_path):
    """
    Check if the binary located in file_path is a valid Flattened Image Tree (FIT) file by looking
    if it has the required nodes and properties at the root node. Raises an error if the file is in
    FDT format but doesn't have the required FIT properties or nodes.

    :param file_path: Path of the file to be checked.
    :returns: True if the file has the required properties and nodes,
              False if the file is not in FDT format.
    """

    # Values taken from 'Flattened Image Tree (FIT) Format' in the U-Boot v2024.07 Documentation:
    # https://docs.u-boot.org/en/v2024.07/usage/fit/source_file_format.html
    required_props = ["timestamp"]
    required_nodes = ["images", "configurations"]

    if not is_file_type_dtb(file_path):
        return False

    try:
        output = subprocess.run(["fdtget", file_path, "/", "-p"],
                                text=True, check=True, stdout=subprocess.PIPE)

        # Check if file has the required properties in the root node
        if not all(prop in output.stdout for prop in required_props):
            raise InvalidDataError("File is in FDT format but doesn't have the required FIT "
                                   "properties. Aborting.")

        output = subprocess.run(["fdtget", file_path, "/", "-l"],
                                text=True, check=True, stdout=subprocess.PIPE)

        # Check if file has the required nodes in the root node
        if not all(node in output.stdout for node in required_nodes):
            raise InvalidDataError("File is in FDT format but doesn't have the required FIT "
                                   "nodes. Aborting.")

    except subprocess.CalledProcessError as exc:
        raise TorizonCoreBuilderError(
            f"Error running fdtget: {exc.output.strip()}") from exc

    return True


@contextmanager
def open_disk_image(image_path, *, delete_on_error=False, readonly=False, loading_msg=None):
    """Create a context manager to open and manipulate raw disk images."""

    try:
        gfs = guestfs.GuestFS(python_return_dict=True)
        gfs.add_drive_opts(image_path, format="raw", readonly=readonly)
        run_with_loading_animation(
            func=gfs.launch,
            loading_msg=loading_msg or "Initializing image...")
        if len(gfs.list_partitions()) < 1:
            raise TorizonCoreBuilderError(
                "Image doesn't have any partitions or it's not a valid raw image. Aborting.")
        yield gfs
    except RuntimeError as gfserr:
        if delete_on_error:
            log.info("Removing '%s'", image_path)
            os.remove(image_path)
        match = re.search(r"unable to resolve 'LABEL=(.*)'", str(gfserr), re.IGNORECASE)
        if match:
            # pylint: disable-next=raise-missing-from
            raise TorizonCoreBuilderError(
                f"Filesystem with label '{match.group(1)}' not found in image. Aborting.")
        # pylint: disable-next=raise-missing-from
        raise TorizonCoreBuilderError(f"guestfs: {gfserr.args[0]}")
    finally:
        if gfs:
            gfs.shutdown()
            gfs.close()


def checksum_match(fpath, cksum, error_on_mismatch=True):
    """Check if SHA256 checksum of a file matches the provided value."""

    file_cksum = get_file_sha256sum(fpath)
    log.info("Calculated SHA256 checksum: %s", file_cksum)
    if cksum != file_cksum:
        if error_on_mismatch:
            raise IntegrityCheckFailed(
                f"Calculated checksum of '{os.path.basename(fpath)}' does not match "
                "expected value. Aborting.")
        log.warning("Calculated checksum of '%s' does not match expected value.",
                    os.path.basename(fpath))
        return False

    log.info("Integrity check was successful!")
    return True


def checksum_match_with_remote(fpath, url, error_on_mismatch=True):
    """Check if existing file checksum matches the one referenced in url."""

    # Try to get checksum from response header
    res = requests.head(url, timeout=60)
    if res.status_code == requests.codes["ok"] and "X-Checksum-Sha256" in res.headers:
        cksum = res.headers["X-Checksum-Sha256"]
        log.info("Got SHA256 checksum from response header: %s", cksum)
    else:
        log.info("Could not get file checksum from response header.")
        return None

    return checksum_match(fpath, cksum, error_on_mismatch)


def sanitize_fname(fname, repl="_"):
    """Replace disallowed characters in file names"""
    return re.sub(r"[^\w\.\-\+]", repl, fname)


# From https://stackoverflow.com/questions/37060344/
# how-to-determine-the-filename-of-content-downloaded-with-http-in-python
#
def parse_disposition_header(header):
    """Simplified parser of Content-Disposition header (RFC 6266)"""
    # Review this if a full-blown parser is required (TODO).
    # See https://tools.ietf.org/html/rfc6266
    fname = re.findall(r"filename\*?=([^;]+)", header, flags=re.IGNORECASE)
    assert len(fname) == 1, "Failed parsing Content-Disposition header"
    return fname[0].strip().strip('"')


def fetch_remote(url, fname=None, cksum=None, download_dir=None):
    """Fetch a remote file

    :param url: Source URL for the file.
    :param fname: Base name of the file to download (currently required).
    :param cksum: Expected SHA-256 checksum of the file. If the downloaded
                  file checksum does not match it an `IntegrityCheckFailed`
                  exception will be raised.
    :param download_dir: Directory where file should be downloaded to or
                         obtained from if it already exists.
    """

    # No path allowed: paths should be passed through download_dir.
    if fname:
        assert os.path.basename(fname) == fname, \
            "fetch_remote: file name cannot contain a path"

    if None not in [fname, download_dir] and os.path.isfile(os.path.join(download_dir, fname)):
        fpath = os.path.join(download_dir, fname)
        log.info("'%s' already exists. Verifying checksum.", fname)
        if cksum is not None:
            log.info("Provided SHA256 checksum: %s", cksum)
            if checksum_match(fpath, cksum, error_on_mismatch=False):
                return fname, False
        elif checksum_match_with_remote(fpath, url, error_on_mismatch=False) in [None, True]:
            return fname, False
        # Checksum failed for local file, download image
        fname, ext = os.path.splitext(fname)
        fname = fname + datetime.now().strftime("_%Y%m%d%H%M%S") + ext
        log.warning("Downloading file as '%s'.", fname)

    # Inner helper function.
    def make_download_fname(fname):
        """Make full name of file to download"""
        des_fname = None
        is_temp = False
        if download_dir and fname:
            # Download directory and file name known: use them.
            des_fname = os.path.join(download_dir, fname)
        elif fname:
            # Only file name is known: place file into temp directory.
            des_fname = os.path.join(tempfile.gettempdir(), fname)
            is_temp = True
        return des_fname, is_temp

    in_fname, is_temp = make_download_fname(fname)

    try:
        log.info(f"Fetching URL '{url}' into '{in_fname}'")

        # Do actual download.
        with download_progress() as reporthook:
            out_fname, headers = urlretrieve(url, filename=in_fname, reporthook=reporthook)

        log.info("Download Complete!")
        # log.debug(f"Downloaded {out_fname}, headers: {headers}")

        # If we still haven't decided the name of the file, try to determine
        # one from the Content-Disposition header.
        if in_fname is None and "Content-Disposition" in headers:
            new_fname = parse_disposition_header(headers["Content-Disposition"])
            new_fname = sanitize_fname(new_fname)
            new_fname, is_temp = make_download_fname(new_fname)
            log.debug(f"Moving '{out_fname}' to '{new_fname}'")
            shutil.move(out_fname, new_fname)
            out_fname = new_fname

        elif in_fname is None:
            # Currently a temporary name is useless to the program because the
            # file name is used to determine its type. This should be reviewed
            # if the logic in 'images unpack' changes (TODO).
            os.unlink(out_fname)
            raise InvalidDataError(
                "Cannot determine appropriate file name after download!")
    except Exception as exc:
        raise OperationFailureError(f"Could not fetch URL '{url}'") from exc

    log.info(f"Downloaded file name: '{out_fname}'")
    if not is_temp:
        set_output_ownership(out_fname)

    # Ensure checksum matches expected one:
    if cksum is not None:
        checksum_match(out_fname, cksum, error_on_mismatch=True)
    elif checksum_match_with_remote(out_fname, url, error_on_mismatch=True) is None:
        log.info("No integrity check performed because reference checksum could not be obtained.")

    return out_fname, is_temp


def make_feed_url(feed_props):
    """Build URL to the input image based on Toradex feed properties"""

    # Update documentation with latest changes to the toradex-feed prop:
    # - major -> version (string, major.minor.patch)
    # - module -> machine
    # - release value 'stable' -> 'quarterly'
    # - build-number (number|string, required) added
    # - build-date (number|string, required except when quarterly) added

    # ---
    # Define each part of the URL - store in a dictionary:
    # ---
    params = {}

    # NOTE: We use assertions below for tests that should never fail
    #       since the schema validation should have caught them before
    #       and we raise exceptions in other cases.
    release_prop = feed_props.get("release")
    if release_prop not in RELEASE_TO_PROD_MAP:
        assert False, "Unhandled release property value"

    distro_prop = feed_props["distro"]
    rt_flag = "-rt" if distro_prop[-3:] == "-rt" else ""

    params["prod"] = RELEASE_TO_PROD_MAP[release_prop]
    params["server"] = DEFAULT_SERVER_NAME
    params["machine_name"] = feed_props["machine"]
    params["distro"] = distro_prop
    params["variant"] = feed_props.get("variant")
    params["rt_flag"] = rt_flag

    if params["machine_name"] in COMMON_TORIZON_TO_SRC:
        params["src"]  = COMMON_TORIZON_TO_SRC[params["machine_name"]]
        params["tezi_flag"] = ""
        params["ext"] = "wic"
    else:
        params["src"] = DEFAULT_SRC
        params["tezi_flag"] = "Tezi_"
        params["ext"] = "tar"

    version_prop = feed_props["version"]
    version_major = int(version_prop.split('.')[0])
    if version_major not in MAJOR_TO_YOCTO_MAP:
        # Raise a parse error instead to allow a better message (TODO)
        # Caller should capture parse error and set file name.
        raise InvalidDataError(
            f"Don't know how to handle a major version of {version_major}")

    if params["variant"] is None:
        if MAJOR_TO_YOCTO_MAP[version_major] in ("dunfell-5.x.y", "kirkstone-6.x.y"):
            params["variant"] = DEFAULT_LEGACY_IMAGE_VARIANT
        else:
            params["variant"] = DEFAULT_IMAGE_VARIANT

    params["version"] = feed_props["version"]
    params["yocto"] = MAJOR_TO_YOCTO_MAP[version_major]

    if release_prop not in RELEASE_TO_BUILD_TYPE_MAP:
        assert False, "Unhandled release property value"
    params["build_type"] = RELEASE_TO_BUILD_TYPE_MAP[release_prop]

    # Automatically detect build number and build date based on manifest (TODO)
    build_number_prop = feed_props["build-number"]
    params["build_number"] = build_number_prop

    if release_prop == "quarterly":
        params["build_date"] = ""
    else:
        build_date_prop = feed_props.get("build-date")
        if build_date_prop is None:
            raise ParseError("Monthly and nightly images require the 'build-date' field.")
        params["build_date"] = build_date_prop

    if release_prop not in RELEASE_TO_DEVEL_MAP:
        assert False, "Unhandled release property value"
    params["devel"] = RELEASE_TO_DEVEL_MAP[release_prop]

    url_format = (
        "https://artifacts.toradex.com/artifactory/{src}-{prod}-{server}/{yocto}/"
        "{build_type}/{build_number}/{machine_name}/{distro}/{variant}/oedeploy/"
    )
    name_format = (
        "{variant}{rt_flag}-{machine_name}-{tezi_flag}{version}"
        "{devel}{build_date}+build.{build_number}.{ext}"
    )

    if params["build_type"] == "nightly":
        log.warning("NOTE: Nightly images are only kept in our servers for a few weeks.")
        log.warning("The URL may no longer work.")

    if feed_props["machine"] in SYNAIMG_MACHINES:
        filename = "SYNAIMG-flash.tar.gz"
    else:
        filename = name_format.format(**params)

    url = url_format.format(**params) + filename

    log.debug(f"Feed URL: {url}")

    return url, filename
