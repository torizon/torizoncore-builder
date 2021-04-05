"""
Backend handling for build subcommand
"""

import json
import os
import logging
import re

import jsonschema
import yaml

from tcbuilder.errors import (PathNotExistError, InvalidDataError,
                              InvalidAssignmentError)

DEFAULT_SCHEMA_FILE = "tcbuild.schema.yaml"

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
        print("Config file:", json.dumps(config))
        raise InvalidDataError(f"{config_path}: {ex.message}")

    return config
