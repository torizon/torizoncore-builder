"""
Backend handling for build subcommand
"""

import os
import logging
import re
import sys
import tempfile

from urllib.parse import urlparse, unquote
from urllib.request import urlretrieve

import jsonschema
import yaml

from tcbuilder.backend.common import progress, get_file_sha256sum
from tcbuilder.errors import (PathNotExistError, InvalidDataError,
                              InvalidAssignmentError, OperationFailureError,
                              IntegrityCheckFailed)

DEFAULT_SCHEMA_FILE = "tcbuild.schema.yaml"

RELEASE_TO_PROD_MAP = {
    "nightly": "torizoncore-oe-prerelease-frankfurt",
    "monthly": "torizoncore-oe-prerelease-frankfurt",
    "quarterly": "torizoncore-oe-prod-frankfurt"
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
    5: "dunfell-5.x.y"
}

# Assigment regex pre-compiled.
ASSGN_REGEX = re.compile(r"^([a-zA-Z_][a-zA-Z_0-9]*)=(.*)$")

log = logging.getLogger("torizon." + __name__)


def parse_assignments(assignments):
    """Parse a list of assignment strings in the form KEY=VALUE

    :param assignments: List of strings to be parsed.
    :return: Dictionary with the resulting key-value mapping.
    """

    var_mapping = {}
    for assgn in assignments:
        matches = ASSGN_REGEX.match(assgn)
        if not matches:
            raise InvalidAssignmentError(
                "Variable assignment must follow the format KEY=VALUE "
                f"(in assignment '{assgn}').")
        # log.debug(f"parse_assignments: '{matches.group(1)}' <= '{matches.group(2)}'")
        var_key, var_val = matches.group(1), matches.group(2)
        var_mapping[var_key] = var_val

    return var_mapping


def sanitize_fname(fname, repl="_"):
    """Replace disallowed characters in file names"""
    return re.sub(r"[^\w\.\-\+]", repl, fname)


def parse_remote(remote_str):
    """Parse the 'remote' property in the configuration file

    The remote property provides the remote file URL but it may additionally
    indicate the expected SHA-256 checksum of the file.
    """

    parts = urlparse(remote_str)
    if parts.scheme.lower() not in ["ftp", "http", "https"]:
        raise InvalidDataError("Remote must be provided as an FTP or HTTP URL")

    fname = None
    cksum = None
    params_in = parts.params.split(";")
    params_out = []
    for param in params_in:
        # Handle some special parameters.
        matches = re.match(r"sha256sum=([a-fA-F0-9]+)", param)
        if matches:
            cksum = matches.group(1)
            continue
        matches = re.match(r"filename=(.*)", param)
        if matches:
            fname = matches.group(1)
            continue
        params_out.append(param)

    # Rebuild URL without consumed parameters.
    url = parts._replace(params=";".join(params_out)).geturl()

    # If user did not specify a file name, try to determine one from the URL.
    # Note that this is not expected to work always but we need a stable file
    # name in order to be able to find out if the file has already been
    # downloaded. Here we also sanitize the file name just in case.
    if fname is None:
        fname = unquote(os.path.basename(parts.path))
        fname = sanitize_fname(fname) or None

    # Document sha256sum parameter (TODO).
    # Document filename parameter (TODO).

    return url, fname, cksum


def fetch_remote(url, fname=None, cksum=None, download_dir=None):
    """Fetch a remote file

    :param url: Source URL for the file.
    :param fname: Base name of the file to download (currently required).
    :param cksum: Expected SHA-256 checksum of the file. If the downloaded
                  file checksum does not match it an `IntegrityCheckFailed`
                  exception will be raised.
    :param download_dir: Directory where file should be downloaded to or
                         obtained from if it already exists (TODO).
    """

    if fname is None:
        # Try to determine file name from server (TODO).
        raise InvalidDataError("Do not know the name of the file to download!")

    # No path allowed: paths should be passed through download_dir.
    assert os.path.basename(fname) == fname, \
        "fetch_remote: fname cannot contain a path"

    # Optimization (TODO).
    if None not in [fname, cksum, download_dir]:
        # If a file in the download directory with correct checksum exists then
        # do not download it again.
        pass

    # Optimization (TODO).
    elif None not in [fname, download_dir]:
        # If a file in the download directory exists and its checksum matches
        # the one provided by the server then do not download it again.
        # Note that Artifactory provides a header named X-Checksum-Sha256
        # that we could use for that.
        pass

    is_temp = False
    if download_dir:
        in_fname = os.path.join(download_dir, fname)
    else:
        in_fname = os.path.join(tempfile.gettempdir(), fname)
        is_temp = True

    try:
        # Show progress bar only when outputting to a terminal.
        progress_hook = None
        if sys.stdout.isatty():
            print(f"Fetching URL '{url}' into '{in_fname}'")
            progress_hook = progress
        else:
            log.info(f"Fetching URL '{url}' into '{in_fname}'")
        # Do actual download.
        out_fname, _headers = urlretrieve(
            url, filename=in_fname, reporthook=progress_hook)
        log.info("\nDownload Complete!")
        log.debug(f"Target file name: {out_fname}")
        # log.debug(f"Downloaded {out_fname}, headers: {headers}")
    except:
        raise OperationFailureError(f"Could not fetch URL '{url}'")

    # Ensure checksum matches expected one:
    if cksum is not None:
        file_cksum = get_file_sha256sum(out_fname)
        if cksum != file_cksum:
            raise IntegrityCheckFailed(
                f"Downloaded file sha256sum of '{file_cksum}' does not match "
                f"expected checksum of '{cksum}'")
        log.info("Integrity check was successful!")
    else:
        log.info("No integrity check performed because checksum was not specified.")

    return out_fname, is_temp


def parse_config_file(config_path, schema_path=DEFAULT_SCHEMA_FILE):
    """Parse a configuration file against the expected schema

    :param config_path: Configuration file (full-path).
    :param schema_path: Schema file.
    :return: The contents of the configuration file as a dictionary.
    """

    if not os.path.exists(config_path):
        raise PathNotExistError(f"Build configuration file '{config_path}' does not exist.")

    # Load the YAML configuration file (user-supplied):
    with open(config_path) as file:
        try:
            config = yaml.load(file, Loader=yaml.FullLoader)

        except yaml.YAMLError as ex:
            parts = []
            parts.append(f"{config_path}:")
            if hasattr(ex, "problem_mark"):
                mark = getattr(ex, "problem_mark")
                parts.append(f"{mark.line}:{mark.column}: ")
            if hasattr(ex, "problem"):
                parts.append(getattr(ex, "problem"))
            else:
                parts.append("parsing error")

            raise InvalidDataError("".join(parts))

    # Load the YAML schema file (supplied with the tool):
    schemapath = os.path.join(os.path.dirname(__file__), schema_path)
    with open(schemapath) as file:
        schema = yaml.load(file, Loader=yaml.FullLoader)

    # Do the actual validation of configuration against the schema.
    try:
        jsonschema.validate(config, schema)
    except jsonschema.ValidationError as ex:
        # print("Config file:", json.dumps(config))
        raise InvalidDataError(f"{config_path}: {ex.message}")

    return config


def make_feed_url(feed_props):
    """Build URL to the input image based on Toradex feed properties"""

    # Update documentation with latest changes to the toradex-feed prop:
    # - major -> version (string, major.minor.patch)
    # - module -> machine
    # - release value 'stable' -> 'quarterly'
    # - build-number (string, required) added
    # - build-date (string, required except when quarterly) added

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
    params["machine_name"] = feed_props["machine"]
    params["distro"] = distro_prop
    params["variant"] = feed_props["variant"]
    params["rt_flag"] = rt_flag

    version_prop = feed_props["version"]
    version_major = int(version_prop.split('.')[0])
    if version_major not in MAJOR_TO_YOCTO_MAP:
        # Raise a parse error instead to allow a better message (TODO)
        raise InvalidDataError(
            f"Don't know how to handle a major version of {version_major}")

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
            # Raise a parse error instead to allow a better message (TODO)
            raise InvalidDataError("'build-date' must be specified")
        params["build_date"] = build_date_prop

    if release_prop not in RELEASE_TO_DEVEL_MAP:
        assert False, "Unhandled release property value"
    params["devel"] = RELEASE_TO_DEVEL_MAP[release_prop]

    url_format = (
        "https://artifacts.toradex.com/artifactory/{prod}/{yocto}/"
        "{build_type}/{build_number}/{machine_name}/{distro}/{variant}/"
        "oedeploy/{variant}{rt_flag}-{machine_name}-Tezi_{version}"
        "{devel}{build_date}+build.{build_number}.tar"
    )
    name_format = (
        "{variant}{rt_flag}-{machine_name}-Tezi_{version}"
        "{devel}{build_date}+build.{build_number}.tar"
    )

    url = url_format.format(**params)
    filename = name_format.format(**params)

    log.debug(f"Feed URL: {url}")

    return url, filename
