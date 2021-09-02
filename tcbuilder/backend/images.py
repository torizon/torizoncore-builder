"""
Backend handling for build subcommand
"""

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import urllib.request

from io import BytesIO, TextIOWrapper
from urllib.parse import urljoin
from zipfile import ZipFile

import docker.errors
import requests
import paramiko
import yaml

from tcbuilder.backend.common import (get_rootfs_tarball, get_unpack_command,
                                      get_host_workdir, set_output_ownership)
from tcbuilder.backend import ostree
from tcbuilder.errors import \
    (TorizonCoreBuilderError, InvalidArgumentError, InvalidDataError, OperationFailureError)
from tcbuilder.backend.bundle import \
    (DindManager, login_to_registries, show_pull_progress_xterm)
from tcbuilder.backend.registryops import \
    (RegistryOperations, SHA256_PREFIX, parse_image_name, platform_matches)

log = logging.getLogger("torizon." + __name__)

SNAPSHOT_META_FILE = "snapshot.json"
TARGETS_META_FILE = "targets.json"
ROOT_META_FILE = "root.json"

DEFAULT_METADATA_MAXLEN = 4 * 1024 * 1024
OSTREE_PUBLIC_FEED = "https://feeds.toradex.com/ostree"
UNSAFE_FILENAME_CHARS = r'\/:*?"<>|'


def get_device_info(r_host, r_username, r_password):
    """
    Access a "live" TorizonCore device and get some information about it.

    :param r_host: TorizonCore hostname.
    :param r_username: TorizonCore remote username.
    :param r_password: TorizonCore remote password.
    :returns:
        version: TorizonCore version.
        hostname: TorizonCore hostname
        container: Container runtime engine.
    """

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    client.connect(hostname=r_host,
                   username=r_username,
                   password=r_password)

    # Gather module and version information remotely from device
    sftp = client.open_sftp()
    if sftp is not None:
        release_file = sftp.file("/etc/os-release")
        for line in release_file:
            if "PRETTY_NAME" in line:
                version = line
        host_file = sftp.file("/etc/hostname")
        hostname = host_file.readline()
        try:
            sftp.stat("/usr/bin/podman")
            container = "podman"
        except IOError:
            container = "docker"
        sftp.close()
    else:
        client.close()
        raise TorizonCoreBuilderError("Unable to create SSH connection")

    client.close()

    return version, hostname, container


# pylint: disable=too-many-locals
def download_tezi(r_host, r_username, r_password,
                  tezi_dir, src_sysroot_dir, src_ostree_archive_dir):
    """
    Download appropriate Tezi Image based on target device.
    """

    version, hostname, container = get_device_info(r_host,
                                                   r_username,
                                                   r_password)

    # Create correct artifactory link based on device information
    if "devel" in version:
        prod = "torizoncore-oe-prerelease-frankfurt"
        devel = "-devel-"
    else:
        prod = "torizoncore-oe-prod-frankfurt"
        devel = ""

    if "dunfell" in version:
        yocto = "dunfell-5.x.y"

    date = re.findall(r'.*-(.*?)\+', version)
    if not date:
        build_type = "release"
        date = ""
    elif len(date[0]) == 6:
        build_type = "monthly"
        date = date[0]
    elif len(date[0]) == 8:
        build_type = "nightly"
        date = date[0]

    build_number = re.findall(r'.*build.(.*?)\ ', version)[0]

    if "Upstream" in version:
        kernel_type = "-upstream"
    else:
        kernel_type = ""

    if "PREEMPT" in version:
        rt_flag = "-rt"
    else:
        rt_flag = ""

    sem_ver = re.findall(r'.*([0-9]+\.[0-9]+\.[0-9]+)\.*', version)[0]

    module_name = hostname[:-10]

    url = "https://artifacts.toradex.com/artifactory/{0}/{1}/{2}/{3}/{4}/" \
          "torizon{5}{6}/torizon-core-{7}/oedeploy/" \
          "torizon-core-{7}{6}-{4}-Tezi_{8}{9}{10}+build.{3}.tar".format(
              prod, yocto, build_type, build_number, module_name, kernel_type,
              rt_flag, container, sem_ver, devel, date)

    # Download and unpack tezi image
    log.info(f"Downloading image from: {url}\n")
    log.info("The download may take some time. Please wait...")
    download_file = os.path.basename(url)
    download_file_cwd = os.path.abspath(download_file)
    try:
        urllib.request.urlretrieve(url, download_file_cwd)
        log.info("Download Complete!\n")
    except:
        raise TorizonCoreBuilderError("The requested image could not be found "
                                      "in the Toradex Artifactory.")
    set_output_ownership(download_file_cwd)
    import_local_image(download_file, tezi_dir,
                       src_sysroot_dir, src_ostree_archive_dir)
# pylint: enable=too-many-locals


def unpack_local_image(image_dir, sysroot_dir):
    """Extract the root fs tarball from the image into the sysroot directory"""
    tarfile = get_rootfs_tarball(image_dir)

    # pylint: disable=line-too-long
    # This is a OSTree bare repository. Care must been taken to preserve all
    # file system attributes. Python tar does not support xattrs, so use GNU tar
    # here
    # See: https://dev.gentoo.org/~mgorny/articles/portability-of-tar-features.html#extended-file-metadata
    # pylint: enable=line-too-long
    tarcmd = "cat '{0}' | {1} | tar --xattrs --xattrs-include='*' -xhf - -C {2}".format(
                tarfile, get_unpack_command(tarfile), sysroot_dir)
    log.debug(f"Running tar command: {tarcmd}")
    subprocess.check_output(tarcmd, shell=True, stderr=subprocess.STDOUT)

    # Remove the tarball since we have it unpacked now
    os.unlink(tarfile)


def _make_tezi_extract_dir(tezi_dir):
    """Create target directory where to extract the tezi image"""
    extract_dir = tezi_dir + '.tmp'
    if os.path.exists(extract_dir):
        shutil.rmtree(extract_dir)
    os.mkdir(extract_dir)
    return extract_dir


def import_local_image(image_dir, tezi_dir, src_sysroot_dir, src_ostree_archive_dir):
    """Import local Toradex Easy Installer image

    Import local Toradex Easy installer image to be customized. Assuming an
    empty/non-existing src_sysroot_dir as well as src_ostree_archive_dir.
    """
    os.mkdir(src_sysroot_dir)

    # If provided image_dir is archived, extract it first
    # pylint: disable=C0330
    extract_dir = None
    if (image_dir.endswith(".tar") or image_dir.endswith(".tar.gz") or
        image_dir.endswith(".tgz")):
        log.info("Unpacking Toradex Easy Installer image.")
        if "Tezi" in image_dir:
            extract_dir = _make_tezi_extract_dir(tezi_dir)
            final_dir = os.path.join(
                extract_dir, os.path.splitext(os.path.basename(image_dir))[0])
        elif "teziimage" in image_dir:
            extract_dir = _make_tezi_extract_dir(tezi_dir)
            final_dir = extract_dir
        else:
            raise InvalidArgumentError(
                f"Unknown naming pattern for file {image_dir}")
        tarcmd = "cat {0} | {1} | tar -xf - -C {2}".format(
            image_dir, get_unpack_command(image_dir), extract_dir)
        log.debug(f"Running tar command: {tarcmd}")
        subprocess.check_output(tarcmd, shell=True, stderr=subprocess.STDOUT)
        image_dir = final_dir

    elif image_dir.endswith(".zip"):
        log.info("Unzipping Toradex Easy Installer image.")
        with ZipFile(image_dir, 'r') as file:
            extract_dir = _make_tezi_extract_dir(tezi_dir)
            file.extractall(extract_dir)
            image_dir = extract_dir

    log.info("Copying Toradex Easy Installer image.")
    log.debug(f"Copy directory {image_dir} -> {tezi_dir}.")
    shutil.copytree(image_dir, tezi_dir)

    # Get rid of the extraction directory (if we created one).
    if extract_dir is not None:
        shutil.rmtree(extract_dir)

    log.info("Unpacking TorizonCore Toradex Easy Installer image.")
    unpack_local_image(tezi_dir, src_sysroot_dir)

    src_sysroot = ostree.load_sysroot(src_sysroot_dir)
    csum, _ = ostree.get_deployment_info_from_sysroot(src_sysroot)

    log.info(f"Importing OSTree revision {csum} from local repository...")
    repo = ostree.create_ostree(src_ostree_archive_dir)
    src_ostree_dir = os.path.join(src_sysroot_dir, "ostree/repo")
    ostree.pull_local_ref(repo, src_ostree_dir, csum, remote="torizon")
    metadata, _, _ = ostree.get_metadata_from_checksum(src_sysroot.repo(), csum)

    log.info("Unpacked OSTree from Toradex Easy Installer image:")
    log.info(f"  Commit checksum: {csum}".format(csum))
    log.info(f"  TorizonCore Version: {metadata['version']}")


def load_metadata(fname, ftype=None, maxlen=DEFAULT_METADATA_MAXLEN):
    """Load metadata file and determine some of its attributes (size, sha256).

    :param fname: Name of the file to load.
    :param ftype: Type of the file for parsing purposes ("json" or "yaml"). If
                  not specified, this will default to "json" unless the file
                  name extension is ".yml" or ".yaml".
    :param maxlen: Maximum length of the file; raise exception if length is
                   exceeded.
    """

    # Load all file into memory.
    with open(fname, "rb") as fileh:
        data = fileh.read(maxlen + 1)
        assert len(data) <= maxlen, \
            f"File {fname} is larger than {maxlen} bytes (giving up)"

    # Wrap data into a text stream for loading.
    data_as_stream = BytesIO(data)
    data_as_text = TextIOWrapper(data_as_stream, encoding="utf-8")

    data_sha256_ = hashlib.sha256()
    data_sha256_.update(data)
    data_sha256 = data_sha256_.hexdigest()

    log.debug(f"File {fname}: sha256sum: {data_sha256}")

    # Determine parser to be used:
    if ftype is None:
        if os.path.splitext(fname)[1].lower() in [".yml", ".yaml"]:
            ftype = "yaml"
        else:
            ftype = "json"

    # Parse file.
    if ftype == "json":
        parsed = json.load(data_as_text)
    else:
        parsed = yaml.safe_load(data_as_text)

    return {
        "file": fname, "size": len(data), "sha256": data_sha256, "parsed": parsed
    }


def check_commit_present(ostree_url, commit_sha256, access_token=None):
    """Determine if the given commit is present at an OSTree repo

    :param ostree_url: Base URL to OSTree repo.
    :param commit_sha256: Hex digest of the commit (must be lower-case).
    :param access_token: If specified, the bearer token to access the resource
                         at the server.
    """

    # Build URL of OSTree commit:
    url = urljoin(
        ostree_url + "/",
        f"objects/{commit_sha256[:2]}/{commit_sha256[2:]}.commit")

    # Try to access resource using the HEAD method.
    if access_token:
        assert url.lower().startswith("https://")
        res = requests.head(
            url, allow_redirects=True,
            headers={"Authorization": f"Bearer {access_token}"})
    else:
        res = requests.head(url, allow_redirects=True)

    if res.status_code == requests.codes["ok"]:
        return True

    if res.status_code == requests.codes["not_found"]:
        return False

    raise InvalidDataError(
        "Unexpected status code when looking for commit: "
        f"code={res.status_code}, url={url}")


def do_fetch_ostree_target(_target, sha256, ostree_url, images_dir, access_token=None):
    """Helper to fetch a given commit from a specified OSTree repo"""

    # Evaluate using libostree for the work done by this function (FUTURE).
    # Create a local repo.
    repo_dir = os.path.join(images_dir, sha256 + ".ostree")
    os.mkdir(repo_dir)
    subprocess.run(
        ["ostree", "init", "--repo", repo_dir, "--mode=archive"],
        check=True)

    # Add a temporary remote.
    remote_name = "tmpremote"
    subprocess.run(
        ["ostree", "remote", "add", remote_name,
         "--repo", repo_dir, ostree_url, "--no-gpg-verify"],
        check=True)

    # Pull our hashref.
    pull_cmd = ["ostree", "pull", "--repo", repo_dir, remote_name, sha256]
    if access_token:
        # Add authorization header (that is supposed to be valid for hours) (FIXME):
        pull_cmd.extend([
            "--http-header", f'Authorization=Bearer {access_token}'
        ])
    log.debug(f"Running {' '.join(pull_cmd)}")
    subprocess.run(pull_cmd, check=True)

    # Remove remote.
    subprocess.run(
        ["ostree", "remote", "delete", remote_name, "--repo", repo_dir],
        check=True)


def fetch_ostree_target(target, sha256, ostree_url, images_dir,
                        access_token=None, name=None, version=None):
    """Fetch commit from the specified OSTree repo falling back to a public one

    :param target: Target as it appears in the Uptane metadata.
    :param sha256: ID of the commit.
    :param ostree_url: Base URL of the OSTree repository.
    :param images_dir: Directory where images should be stored. This function
                       will create a sub-directory to hold the OSTree repo.
    :param access_token: OAuth2 access token giving access to the OSTree repo.
    :param name: Name of target visible to the user as it appears in the Uptane
                 metadata.
    :param version: Version of the target visible to the user as it appears in
                    the Uptane metadata.
    """

    log.info(f"Handling OSTree target '{target}'")

    # Try to find commit on the user's repo first and then on the public feed.
    log.debug(f"Looking for commit {sha256} on the user's repo")
    server_url, server_token = None, None
    commit_present = check_commit_present(
        ostree_url, commit_sha256=sha256, access_token=access_token)
    if commit_present:
        log.info(f"Commit {sha256} found on the user's repo")
        server_url = ostree_url
        server_token = access_token
    else:
        log.debug(f"Looking for commit {sha256} on public feed")
        # For security reasons, we must not use the access-token with the public feed:
        commit_present = check_commit_present(
            OSTREE_PUBLIC_FEED, commit_sha256=sha256)
        if commit_present:
            server_url = OSTREE_PUBLIC_FEED
            server_token = None

    if not commit_present:
        raise TorizonCoreBuilderError(
            f"Could not find commit {sha256} on user's repo or on public feed")

    log.info(f"Fetching OSTree commit {sha256} from {server_url}...")
    log.info(f"Uptane info: target '{name}', version: '{version}'")
    return do_fetch_ostree_target(
        target, sha256, server_url, images_dir, access_token=server_token)


def fetch_validate(url, fname, dest_dir,
                   sha256=None, length=None, access_token=None, parse=None):
    """Fetch and possibly validate a given resource (file)

    :param url: Full URL to the resource (file).
    :param fname: Local name of the file (without a path).
    :param dest_dir: Destination directory for the local file.
    :param sha256: If specified, the required sha256 of the file.
    :param length: If specified, the required length in bytes of the file.
    :param access_token: If specified, the bearer token to access the resource
                         at the server.
    :param parse: If set to "json" the file will be parsed as JSON and the
                  result returned by the function (in case of success).
    """

    # Make sure there are no unsafe characters in the filename:
    # https://superuser.com/questions/358855/
    # what-characters-are-safe-in-cross-platform-file-names-for-linux-windows-and-os
    assert all(ch not in UNSAFE_FILENAME_CHARS for ch in fname), \
        f"Target '{fname}' contains unsafe characters"

    # Fetch the file:
    if access_token:
        assert url.lower().startswith("https://")
        res = requests.get(
            url, headers={"Authorization": f"Bearer {access_token}"})
    else:
        res = requests.get(url)

    if res.status_code != requests.codes["ok"]:
        raise TorizonCoreBuilderError(
            f"Could not fetch fname '{fname}' from '{url}'")

    if length is not None and len(res.content) != length:
        raise InvalidDataError(
            f"Downloaded file '{fname}' has wrong length "
            f"(actual={len(res.content)}, expected={length} bytes)")

    # Determine the sha256 of the data:
    content_sha256_ = hashlib.sha256()
    content_sha256_.update(res.content)
    content_sha256 = content_sha256_.hexdigest()

    if sha256 is not None and content_sha256 != sha256:
        raise InvalidDataError(
            f"Downloaded file '{fname}' has wrong sha256 checksum "
            f"(actual='{content_sha256}', expected='{sha256}')")

    # Write file into destination:
    fname = os.path.join(dest_dir, fname)
    with open(fname, "wb") as cmph:
        cmph.write(res.content)
    log.debug(f"Written file '{fname}' with {length} bytes, sha256='{sha256}'")

    ret = None
    if parse is None:
        pass
    elif parse == "json":
        ret = json.loads(res.text)
    elif parse == "yaml":
        ret = yaml.safe_load(res.text)
    else:
        assert False, f"Bad argument to fetch_validate(): parse={parse}"

    return ret


# pylint: disable=too-many-arguments
def fetch_file_target(target, repo_url, images_dir,
                      sha256=None, length=None, access_token=None, parse=None,
                      name=None, version=None):
    """Fetch a generic file target from the TUF repo

    :param target: Target as it appears in the Uptane metadata.
    :param repo_url: Base URL of the TUF repository as it appears in the
                     credentials file.
    :param images_dir: Directory where images would be stored.
    :param sha256: SHA256 checksum of the target.
    :param length: Length of the target in bytes.
    :param access_token: OAuth2 access token giving access to the TUF repo at
                         the OTA server.
    :param parse: How to parse the file (if not None): "json" or "yaml".
    :param name: Name of target visible to the user as it appears in the Uptane
                 metadata.
    :param version: Version of the target visible to the user as it appears in
                    the Uptane metadata.
    """

    # Build URL to file at OTA server:
    url = urljoin(repo_url + "/", f"api/v1/user_repo/targets/{target}")

    log.info(f"Fetching target '{target}' from '{url}'...")
    log.info(f"Uptane info: target '{name}', version: '{version}'")

    return fetch_validate(
        url, target, images_dir,
        sha256=sha256, length=length, access_token=access_token, parse=parse)
# pylint: enable=too-many-arguments


def get_referenced_images(compose):
    """Determine all the images being referenced by a docker-compose file.

    :param compose: Parsed docker-compose file as a dictionary.
    :return: A dictionary where the key is the service name and the value is a tuple
             (image, platform); image is the image name as referenced in the
             docker-compose file; platform may be None if no platform was explicitly
             defined in the compose file.
    """
    assert "services" in compose, \
        "Section 'services' not found in docker-compose file"
    services = compose["services"]

    image_per_service = {}
    for svc_name, svc_spec in services.items():
        assert "image" in svc_spec, \
            f"No 'image' specified for service {svc_name}"
        image = svc_spec["image"]
        image_platform = svc_spec.get("platform")
        parsed_name = parse_image_name(image)
        assert parsed_name.tag.startswith(SHA256_PREFIX), \
            f"Image '{image}' not specified by digest"
        image_per_service[svc_name] = (image, image_platform)

    log.debug(f"Images being used in docker-compose: {image_per_service}")

    return image_per_service


def fetch_manifests(images, manifests_dir,
                    req_platforms=None, validate=True, verbose=True):
    """Fetch all manifests for the given images.

    :param images: list of image/repo names to fetch (as used in a `docker pull`).
    :param manifests_dir: Directory where to store the manifests.
    :param req_platforms: List of platforms for fetching Docker images (used when
                          not specified in the docker-compose file).
    :param validate: Whether or not to check if each manifest file has a sha256
                     checksum matching the expected one.
    :param verbose: Show verbose output.
    :return: Dictionary where the key is the image name as provided in `images`
             and the value is a list where each object is another dictionary
             with fields:
             - "type": "manifest" or "manifest-list"
             - "name": name of image such as "ubuntu" or "fedora/httpd"
             - "digest": digest of the manifest such as "sha256:123..."
             - "platform": platform as a slash separated string in the form
                           "<os>[/<architecture>[/<variant>]]"
             - "manifest-file": name of the manifest file where data is stored
    """

    digests_cache = set()
    manifests_per_image = {}
    for image in images:
        if verbose:
            log.info(f"\nFetching manifests for {image}...")
        image_parsed = parse_image_name(image)
        assert image_parsed.registry is None, \
            f"{image}: Specifying a registry is not currently supported"

        ops = RegistryOperations()
        digests_saved, manifests_info = ops.save_all_manifests(
            image_parsed.get_name_with_tag(), manifests_dir,
            platforms=req_platforms,
            val_digest=validate)
        digests_cache.update(digests_saved)

        # Use cache to avoid fetching manifest multiple times (FUTURE).
        # This would be relevant only if the digest is referenced by the
        # manifest-list and also directly: this is expected to be rare.

        manifests_per_image[image] = manifests_info

    # log.debug(f"manifests_per_image: {json.dumps(manifests_per_image)}")
    if verbose:
        log.debug("\n=> Manifests per image:")
        for image, manifests_info in manifests_per_image.items():
            log.debug(f"{image}:")
            for man_info in manifests_info:
                log.debug(f" * {man_info['digest']} [{man_info['type']}]")
                log.debug(f"   in {man_info['manifest-file']}")

    return manifests_per_image


def get_compatible_images(manifests, platform, sort=True):
    """Select compatible images in a manifest list.

    The returned list has the same form as in the input but contains
    only the compatible manifests (possibly sorted).

    :param manifests: A list like this: [{"manifest":., "digest":., "platform"}, ...]
    :param platform: Desired platform.
    :param sort: Whether or not to list the manifest list in descending order
                 of specificity.
    """
    # log.debug(f"get_compatible_images() manifests: {json.dumps(manifests)}")
    manifests_with_grade = []
    for man in manifests:
        ret, grade = platform_matches(platform, man["platform"], ret_grade=True)
        if ret:
            manifests_with_grade.append((grade, man))

    if sort:
        manifests_with_grade.sort(key=lambda elem: elem[0], reverse=True)
        if len(manifests_with_grade) >= 2:
            log.debug(f"manifests_with_grade: {manifests_with_grade}")
            assert manifests_with_grade[0][0] < manifests_with_grade[1][0], \
                "There are multiple images equally appropriate for platform"

    return list(mwg[1] for mwg in manifests_with_grade)


# pylint: disable=too-many-locals
def select_images(image_platform_pairs, manifests_per_image, req_platforms=None, verbose=True):
    """Determine all single-platform/platform-independent image references."""

    images_selection = []
    images_selection_per_image = []
    for req_image, req_platform in image_platform_pairs:
        if req_image not in manifests_per_image:
            assert False, \
                f"Requested image {req_image} not in the fetched manifests!"

        # Get manifests available for requested image (exclude manifest lists):
        manifests_all = manifests_per_image[req_image]
        manifests = [man for man in manifests_all if man["type"] == "manifest"]
        multi_platform = len(manifests_all) > len(manifests)
        assert manifests, f"No manifest for image {req_image}"

        cur_selection = []
        if req_platform is None:
            # ---
            # No specific platform requested in docker-compose:
            # ---
            if multi_platform and req_platforms is None:
                # Multi-platform image and no default platform defined (select all):
                for child in manifests:
                    cur_selection.append(
                        ((req_image, req_platform), child["digest"], child["platform"]))

            elif multi_platform and req_platforms is not None:
                # Multi-platform image and default platforms defined (select only them):
                # Note: this should be the usual case with multi-platform images.
                for _plat in req_platforms:
                    _avail = get_compatible_images(manifests, _plat)
                    assert _avail, \
                        (f"There are no images matching platform '{_plat}' "
                         f"for '{req_image}'")
                    # The first one is the "most compatible" one.
                    _sel = _avail[0]
                    cur_selection.append(
                        ((req_image, req_platform), _sel["digest"], _sel["platform"]))

            else:
                # Not a multi-platform image (select the one available):
                # Note: this should be the usual case with single-platform /
                #       platform-independent images.
                _sel = manifests[0]
                cur_selection.append(
                    ((req_image, req_platform), _sel["digest"], _sel["platform"]))
        else:
            # ---
            # Specific platform requested in docker-compose (it must be available).
            # ---
            if multi_platform:
                # Multi-platform image (select best match):
                _avail = get_compatible_images(manifests, req_platform)
                assert _avail, \
                    (f"There are no images matching platform '{req_platform}' "
                     f"for '{req_image}'")
                # The first one is the "most compatible" one.
                _sel = _avail[0]
                cur_selection.append(
                    ((req_image, req_platform), _sel["digest"], _sel["platform"]))
            else:
                # Not a multi-platform image (select the one available):
                _sel = manifests[0]
                cur_selection.append(
                    ((req_image, req_platform), _sel["digest"], _sel["platform"]))

        images_selection_per_image.append(((req_image, req_platform), cur_selection))
        images_selection.extend(cur_selection)

    if verbose:
        log.info("\n=> Digests selected per image:")
        for (req_image, req_platform), cur_selection in images_selection_per_image:
            log.info(f"{req_image}, platform '{req_platform}':")
            for sel in cur_selection:
                log.info(f" * {sel[1]} [{sel[2]}]")

    # At this point `images_selection` is a list like this:
    # [((image, platform), <selected-digest>), ...]
    log.debug(f"images_selection: {images_selection}")

    return images_selection
# pylint: enable=too-many-locals


def select_unique_images(image_platform_pairs, manifests_per_image,
                         req_platforms=None, verbose=True):
    """Determine all single-platform/platform-independent image references."""

    images_selection = select_images(
        image_platform_pairs, manifests_per_image, req_platforms=req_platforms)

    # Determine unique images:
    images_selection_unique = set()
    for (sel_image, _sel_plat), sel_digest, _sel_plat in images_selection:
        image_spec = "{0}@{1}".format(sel_image.split("@")[0], sel_digest)
        images_selection_unique.add((image_spec, sel_digest))

    if verbose:
        log.info("\n=> Unique images selected:")
        for sel in sorted(images_selection_unique):
            log.info(f" * {sel[0]}")

    return images_selection_unique


# pylint:disable=too-many-locals
def build_docker_tarballs(unique_images, target_dir, host_workdir,
                          verbose=True, logins=None, dind_params=None):
    """Build the docker tarballs of a takeout image

    :param unique_images: Iterable giving the pairs (image, digest) for which
                          to generate the tarballs; `image` should be the image
                          name referencing the desired image locally.
    :param target_dir: Directory where to write the tarballs.
    :param host_workdir: Working directory location on the Docker Host (the
                         system where dockerd we are accessing is running).
    :param verbose: Whether to show verbose output/progress information.
    :param logins: List of logins to perform: each element of the list must
                   be either a 2-tuple: (USERNAME, PASSWORD) or a 3-tuple:
                   (REGISTRY, USERNAME, PASSWORD) or equivalent iterable.
    :param dind_params: Parameters to pass to Docker-in-Docker (list).
    """

    show_progress = True
    if verbose:
        _term = os.environ.get('TERM')
        if not sys.stdout.isatty():
            show_progress = False
        elif not (_term.startswith('xterm') or _term.startswith('rxvt')):
            show_progress = False

    log.info("\nStarting DIND container")
    manager = DindManager(target_dir, host_workdir)
    tarballs = None

    try:
        # Start DinD container on host.
        manager.start("host", dind_params=dind_params)
        # Get DinD client to be used on the pulling operations.
        dind_client = manager.get_client()
        if dind_client is None:
            return None
        # Login to all registries before trying to fetch anything.
        if logins:
            login_to_registries(dind_client, logins)

        # Fetch the containers:
        tarballs = []
        for image_spec, image_digest in unique_images:
            assert image_digest.startswith(SHA256_PREFIX)

            # Fetch image:
            log.info(f"Fetching container image {image_spec}")
            if show_progress:
                # Use low-level API to get progress information.
                res_stream = dind_client.api.pull(image_spec, stream=True, decode=True)
                show_pull_progress_xterm(res_stream)
                image_obj = dind_client.images.get(image_spec)
            else:
                # Use high-level API (no progress info).
                image_obj = dind_client.images.pull(image_spec)

            # Set appropriate tag that will be saved in the `docker save` tarball.
            image_spec_parts = image_spec.split("@")
            assert len(image_spec_parts) == 2, \
                f"Image name {image_spec} does not conform with format name@digest"
            image_spec_tag = "digest_" + image_digest.replace(":", "_")
            image_obj.tag(image_spec_parts[0], image_spec_tag)

            # Re-get the image with the new tag.
            image_spec_new = f"{image_spec_parts[0]}:{image_spec_tag}"
            image_obj = dind_client.images.get(image_spec_new)

            # Build tarball via `docker image save image:tag > output.tar`:
            image_fname = image_digest[len(SHA256_PREFIX):] + ".tar"
            image_fname = os.path.join(target_dir, image_fname)
            log.info(f"Saving {image_spec}\n"
                     f"  into {image_fname}")
            with open(image_fname, "wb") as outf:
                for image_data in image_obj.save(named=True):
                    outf.write(image_data)

            tarballs.append({
                "image_spec": image_spec,
                "image_spec_tag": image_spec_tag,
                "image_fname": image_fname
            })

        # Done fetching the containers.
        log.debug("Done fetching and saving images!")

    except docker.errors.APIError as exc:
        raise OperationFailureError(
            f"Error: container images download failed: {str(exc)}") from exc

    finally:
        log.info("Stopping DIND container")
        manager.stop()

    if tarballs and verbose:
        log.info("\n=> Tarball summary:")
        for tarball in tarballs:
            log.info(f"{tarball['image_fname']}:")
            log.info(f" * tagged: {tarball['image_spec_tag']}")
            log.info(f" * image:  {tarball['image_spec']}")

    return tarballs
# pylint:enable=too-many-locals


# pylint: disable=too-many-arguments,too-many-locals
def fetch_compose_target(target, repo_url, images_dir, metadata_dir,
                         sha256=None, length=None, req_platforms=None,
                         access_token=None, name=None, version=None):
    """Fetch compose file target from the TUF repo along with referenced artifacts

    Parameter `req_platforms` should be a list of the platforms to select
    by default for the Docker images. For the other parameters, see
    :func:`fetch_file_target`.
    """

    # Fetch the docker-compose file.
    log.info(f"Fetching docker-compose target '{target}'")
    compose = fetch_file_target(
        target, repo_url, images_dir,
        sha256=sha256, length=length, access_token=access_token, parse="yaml",
        name=name, version=version)

    # Get the list of images being referenced by the compose-file with their
    # requested platforms.
    image_per_service = get_referenced_images(compose)
    images = {img for img, _plat in image_per_service.values()}

    # Fetch the manifests of all images.
    manifests_dir = os.path.join(metadata_dir, sha256 + ".manifests")
    os.mkdir(manifests_dir)
    manifests_per_image = fetch_manifests(images, manifests_dir)

    # Determine (image, platform) pairs referenced in the compose file.
    image_platform_pairs = set(image_per_service.values())
    log.debug(f"image_platform_pairs: {image_platform_pairs}")

    # Determine which images will be needed at `docker-compose up` time.
    images_selection = select_unique_images(
        image_platform_pairs, manifests_per_image, req_platforms=req_platforms)

    # Build tarball with the images.
    docker_dir = os.path.join(images_dir, sha256 + ".images")
    os.mkdir(docker_dir)
    build_docker_tarballs(
        images_selection, docker_dir, host_workdir=get_host_workdir())
# pylint: enable=too-many-arguments,too-many-locals


def fetch_binary_target(target, repo_url, images_dir,
                        sha256=None, length=None,
                        access_token=None, name=None, version=None):
    """Fetch a binary file target from the TUF repo

    For details on the parameters, see :func:`fetch_file_target`.
    """

    log.info(f"Fetching binary target '{target}'")
    fetch_file_target(target, repo_url, images_dir,
                      sha256=sha256, length=length,
                      access_token=access_token, name=name, version=version)


def fetch_imgrepo_metadata(repo_url, dest_dir, access_token=None):
    """Fetch all the required metadata from an Uptane image repo

    :param repo_url: Base URL of the TUF repository as it appears in the
                     credentials file.
    :param dest_dir: Destination directory of the metadata files.
    :param access_token: OAuth2 access token giving access to the TUF repo at
                         the OTA server.
    """

    # 1st: Fetch the snapshot metadata from where we learn about all
    # the other metadata files that should be fetched. With this approach
    # we will fetch more than the minimal needed but the advantage is that
    # we do not have to parse and understand the delegations.

    # NOTE: We do no validations in the snapshot metadata ATM (the device
    #       will do all required validations in the end).
    log.info(f"Fetching '{SNAPSHOT_META_FILE}'")

    url = urljoin(repo_url + "/", f"api/v1/user_repo/{SNAPSHOT_META_FILE}")
    snapshot_meta = fetch_validate(
        url, SNAPSHOT_META_FILE, dest_dir,
        sha256=None, length=None, access_token=access_token, parse="json")

    # Fetch the various metadata files (except "root.json")
    known_metadata_files = [TARGETS_META_FILE]
    for fname, fmeta in snapshot_meta["signed"]["meta"].items():
        url = None
        if fname == ROOT_META_FILE:
            # The root.json file will be handled specially later.
            continue

        if fname in known_metadata_files:
            # Known metadata files are assumed to be at the root of the repo.
            url = urljoin(repo_url + "/", f"api/v1/user_repo/{fname}")

        else:
            # All the rest is assumed to be a delegation.
            # NOTE: Toradex delegation files start with 'tdx-', so we issue a
            #       warning here to help us know if the pattern changes; this
            #       should probably be removed in the future.
            if not fname.startswith("tdx-"):
                log.warning(f"Assuming file {fname} to be a delegation")
            url = urljoin(repo_url + "/", f"api/v1/user_repo/delegations/{fname}")

        log.info(f"Fetching '{fname}'")
        # NOTE: The sha256 in the metadata does not seem to match the actual files.
        fetch_validate(
            url, fname, dest_dir,
            # sha256=fmeta["hashes"].get("sha256"),
            length=fmeta["length"],
            access_token=access_token)

    # Fetch the various versions of the "root.json" file:
    last_root_version = snapshot_meta["signed"]["meta"]["root.json"]["version"]
    for version in range(1, last_root_version + 1):
        fname = f"{version}.root.json"
        url = urljoin(repo_url + "/", f"api/v1/user_repo/{fname}")
        log.info(f"Fetching '{fname}'")
        # It seems we cannot check the SHA and length of previous root data.
        fetch_validate(url, fname, dest_dir, access_token=access_token)


def fetch_director_metadata():
    """Fetch all the required metadata from an Uptane director repo"""
    # TODO: Implement this.


# EOF
