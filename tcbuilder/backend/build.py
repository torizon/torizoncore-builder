"""
Backend handling for build subcommand
"""

import os
import copy
import logging
import re

from urllib.parse import urlparse, unquote

import jsonschema
import yaml

from tcbuilder.backend.common import sanitize_fname
from tcbuilder.backend.expandvars import expand
from tcbuilder.errors import (PathNotExistError, InvalidDataError, InvalidAssignmentError,
                              ParseError, ParseErrors)

DEFAULT_SCHEMA_FILE = "tcbuild.schema.yaml"

# Assignment regex pre-compiled.
ASSGN_REGEX = re.compile(r"^([a-zA-Z_][a-zA-Z_0-9]*)=(.*)$")

# Possible file name extensions for which parse_remote() will consider the
# inferred file name valid.
ALLOWED_SLUG_EXTS = [".tar", ".zip"]

# Minimum base file name length for which parse_remote() will consider the
# inferred file name valid.
MIN_INFER_FNAME = 8


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


def parse_remote(remote_str, infer_fname=True):
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
    if fname is None and infer_fname:
        fname = unquote(os.path.basename(parts.path))
        fname = sanitize_fname(fname) or None
        fparts = os.path.splitext(fname)
        if (len(fparts[0]) >= MIN_INFER_FNAME and fparts[1] in ALLOWED_SLUG_EXTS):
            log.debug(f"Remote file name inferred from slug: {fname}")
        else:
            log.debug("Remote file name could not be inferred from slug")
            fname = None

    return url, fname, cksum


def parse_config_file(config_path, schema_path=DEFAULT_SCHEMA_FILE, substs=None):
    """Parse a configuration file against the expected schema

    :param config_path: Configuration file (full-path).
    :param schema_path: Schema file.
    :param substs: Dictionary with variables to substitute.
    :return: The contents of the configuration file as a dictionary.
    """

    if not os.path.exists(config_path):
        raise PathNotExistError(
            f"Build configuration file '{config_path}' does not exist.")

    # Load the YAML configuration file (user-supplied):
    with open(config_path, "r", encoding="utf-8") as file:
        try:
            config = yaml.safe_load(file)

        except yaml.YAMLError as ex:
            error_exc = ParseError(getattr(ex, "problem", "parsing error"))
            error_exc.set_source(file=config_path)
            if hasattr(ex, "problem_mark"):
                mark = getattr(ex, "problem_mark")
                error_exc.set_source(line=mark.line, column=mark.column)
            # pylint: disable-next=raise-missing-from
            raise error_exc

    # Make variable substitutions.
    if substs is not None:
        config = subst_variables(config, substs)

    # Load the YAML schema file (supplied with the tool):
    schemapath = os.path.join(os.path.dirname(__file__), schema_path)
    with open(schemapath, "r", encoding="utf-8") as file:
        schema = yaml.safe_load(file)

    # Do the actual validation of configuration against the schema.
    validator = jsonschema.Draft7Validator(schema)
    errors = []
    for error in validator.iter_errors(config):
        error_exc = ParseError(error.message)
        error_exc.set_source(file=config_path, prop=error.path)
        errors.append(error_exc)
    if errors:
        raise ParseErrors("Parsing errors found in configuration file!", payload=errors)

    return config


def transform_leaves(dct, handler, max_depth=10):
    """Traverse a dictionary invoking 'handler' on all leaf nodes"""

    def _traverse(dct_or_lst, depth=0):
        assert depth < max_depth, "Dictionary is too deeply nested"
        if isinstance(dct_or_lst, dict):
            for key, value in dct_or_lst.items():
                if isinstance(value, (list, tuple, dict)):
                    _traverse(value, depth+1)
                else:
                    dct_or_lst[key] = handler(value)
                    # log.debug(f"Property {key}: '{value}' -> '{dct_or_lst[key]}'")

        elif isinstance(dct_or_lst, (list, tuple)):
            for index, value in enumerate(dct_or_lst):
                if isinstance(value, (list, tuple, dict)):
                    _traverse(value, depth+1)
                else:
                    dct_or_lst[index] = handler(value)
                    # log.debug(f"Property [{index}]: '{value}' -> '{dct_or_lst[index]}'")
        else:
            assert False, "_traverse() error"

    _traverse(dct)


def subst_variables(config, variables):
    """Perform variable substitution on all string-type values

    This function will go over all string-type values contained in the
    dictionary 'config' expanding variables via the expand() function.
    """

    def _replacer(value):
        if isinstance(value, str):
            return expand(value, variables)
        # No change except for string.
        return value

    config = copy.deepcopy(config)
    transform_leaves(config, _replacer)
    return config
