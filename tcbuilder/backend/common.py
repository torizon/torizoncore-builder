import datetime
import glob
import ipaddress
import json
import os
import shutil
import socket
import subprocess
import git
from tcbuilder.backend import ostree
from typing import Optional

import dns.resolver
import ifaddr

import tezi.utils
from tcbuilder.errors import (FileContentMissing, OperationFailureError,
                              PathNotExistError, TorizonCoreBuilderError, GitRepoError,
                              InvalidDataError)

DOCKER_BUNDLE_FILENAME = "docker-storage.tar.xz"
DOCKER_FILES_TO_ADD = [
    "docker-compose.yml:/ostree/deploy/torizon/var/sota/storage/docker-compose/",
    DOCKER_BUNDLE_FILENAME + ":/ostree/deploy/torizon/var/lib/docker/:true"
]

def get_rootfs_tarball(tezi_image_dir):
    if not os.path.exists(tezi_image_dir):
        raise PathNotExistError(f"Source image {tezi_image_dir} directory does not exist","")

    image_files = glob.glob(os.path.join(tezi_image_dir, "image*.json"))

    if len(image_files) < 1:
        raise FileNotFoundError("No image.json file found in image directory","")

    image_json_filepath = os.path.join(tezi_image_dir, image_files[0])
    with open(image_json_filepath, "r") as jsonfile:
        jsondata = json.load(jsonfile)

    # Find root file system content
    content = tezi.utils.find_rootfs_content(jsondata)
    if content is None:
        raise FileContentMissing(f"No root file system content section found in {jsonfile}","")

    return os.path.join(tezi_image_dir, content["filename"])


def add_common_image_arguments(subparser):
    subparser.add_argument("--image-name", dest="image_name",
                           help="""Image name to be used in Easy Installer image json""")
    subparser.add_argument("--image-description", dest="image_description",
                           help="""Image description to be used in Easy Installer image json""")
    subparser.add_argument("--image-licence", dest="licence_file",
                           help="""Licence file which will be shown on image installation""")
    subparser.add_argument("--image-release-notes", dest="release_notes_file",
                           help="""Release notes file which will be shown on image installation""")


def add_files(tezidir, image_json_filename, filelist, additional_size,
              image_name, image_description, licence_file, release_notes_file):
    image_json_filepath = os.path.join(tezidir, image_json_filename)
    with open(image_json_filepath, "r") as jsonfile:
        jsondata = json.load(jsonfile)

    # Version 3 image format is required for the advanced filelist syntax.
    jsondata["config_format"] = 3

    if image_name is None:
        jsondata["name"] = jsondata["name"] + " with Containers"
    else:
        jsondata["name"] = image_name

    if image_description is not None:
        jsondata["description"] = image_description

    if licence_file is not None:
        jsondata["license"] = licence_file

    if release_notes_file is not None:
        jsondata["releasenotes"] = release_notes_file

    # Rather ad-hoc for now, we probably want to give the user more control
    jsondata["version"] = jsondata["version"] + ".container"
    jsondata["release_date"] = datetime.datetime.today().strftime("%Y-%m-%d")

    # Find root file system content
    content = tezi.utils.find_rootfs_content(jsondata)
    if content is None:
        raise InvalidDataError("No root file system content section found in Easy Installer image.")

    content["filelist"] = filelist
    content["uncompressed_size"] += float(additional_size) / 1024 / 1024

    with open(image_json_filepath, "w") as jsonfile:
        json.dump(jsondata, jsonfile, indent=4)

    return jsondata["version"]


def combine_single_image(source_dir_containers, files_to_add, additional_size,
                         output_dir, image_name, image_description,
                         licence_file, release_notes_file):
    # Copy container to sysroot deployment
    for filename in files_to_add:
        filename = filename.split(":")[0]
        shutil.copy(os.path.join(source_dir_containers, filename),
                    os.path.join(output_dir, filename))

    if licence_file is not None:
        shutil.copy(licence_file, os.path.join(output_dir, licence_file))

    if release_notes_file is not None:
        shutil.copy(release_notes_file, os.path.join(output_dir, release_notes_file))

    version = None
    for image_file in glob.glob(os.path.join(output_dir, "image*.json")):
        version = add_files(output_dir, image_file, files_to_add, additional_size,
                            image_name, image_description, licence_file,
                            release_notes_file)

    return version

def get_unpack_command(filename):
    """Get shell command to unpack a given file format"""
    if filename.endswith(".gz"):
        return "gzip -dc"
    elif filename.endswith(".xz"):
        return "xz -dc"
    elif filename.endswith(".lzo"):
        return "lzop -dc"
    elif filename.endswith(".zst"):
        return "zstd -dc"
    elif filename.endswith(".lz4"):
        return "lz4 -dc"
    else:
        return "cat"

def get_additional_size(output_dir_containers, files_to_add):
    additional_size = 0

    # Check size of files to add to theimage
    for fileentry in files_to_add:
        filename, _destination, *rest = fileentry.split(":")
        filepath = os.path.join(output_dir_containers, filename)
        if not os.path.exists(filepath):
            raise PathNotExistError(f"File {filepath} to be added to image.json does not exist")

        # Check third parameter, if unpack is set to true we need to get size
        # of unpacked tarball...
        unpack = False
        if len(rest) > 0:
            unpack = rest[0].lower() == "true"

        if unpack:
            command = get_unpack_command(filename)

            # Unpack similar to how Tezi does the size check
            size_proc = subprocess.run(
                    "cat '{0}' | {1} | wc -c".format(filename, command),
                    shell=True, capture_output=True, cwd=output_dir_containers,
                    check=False)

            if size_proc.returncode != 0:
                raise OperationFailureError("Size estimation failed. Exit code {0}."
                              .format(size_proc.returncode),"")

            additional_size += int(size_proc.stdout.decode('utf-8'))
        else:
            st = os.stat(filepath)
            additional_size += st.st_size

    return additional_size

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
            for ip in adapter.ips:
                if type(ip.ip) == str: # If it's an str it's an IPv4.
                    local_ip_addresses.append(ip.ip)
                else:
                    local_ip_addresses.append(ip.ip[0])
    return local_ip_addresses

def resolve_hostname(hostname: str, mdns_source: Optional[str] = None) -> (str, bool):  # pylint: disable=E1136
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
        else:
            raise TorizonCoreBuilderError(
                f'Resolving hostname "{mdns_hostname}" using mDNS on all interfaces failed.')


def resolve_remote_host(remote_host, mdns_source = None):
    """Resolve given host to IP address if host is not an IP address already"""
    try:
        _ip_obj = ipaddress.ip_address(remote_host)
        return remote_host
    except ValueError:
        # This seems to be a host name, let's try to resolve it
        ip_addr, _mdns = resolve_hostname(remote_host, mdns_source)
        return ip_addr

def get_branch_from_metadata(storage_dir):
    src_sysroot_dir = os.path.join(storage_dir, "sysroot")
    src_sysroot = ostree.load_sysroot(src_sysroot_dir)
    csum, _kargs = ostree.get_deployment_info_from_sysroot(src_sysroot)
    metadata, _subject, _body = ostree.get_metadata_from_checksum(src_sysroot.repo(), csum)

    if "oe.kernel-source" not in metadata or not isinstance(metadata["oe.kernel-source"], tuple):
        raise TorizonCoreBuilderError(
            "OSTree metadata are missing the kernel source branch name. Use " \
            "--branch to manually specify the kernel branch used by this image.")

    _kernel_repo, kernel_branch, _kernel_revision = metadata["oe.kernel-source"]
    return kernel_branch

def checkout_git_repo(storage_dir, git_repo = None, git_branch = None):

    if git_branch is None:
        git_branch = get_branch_from_metadata(storage_dir)

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
        ref = next((rref for rref in repo_obj.remotes["origin"].refs if rref.remote_head == git_branch),
                None)
        if ref is None:
            raise GitRepoError(f"Branch name {git_branch} does not exist in upstream repository.")
        ref.checkout(b=git_branch)

    repo_obj.close()
