"""
Backend functions and functionality for all splash-config commands
"""

import os
import subprocess

from tcbuilder.backend.common import get_storage_dir
from tcbuilder.backend.splash import add_plymouth_theme_file
from tcbuilder.errors import PathNotExistError

PLYMOUTH_CONFIG = "spinner.plymouth"


def get_default_config():
    """Returns path to the default spinner.plymouth file
       found in the unpacked image.
    """

    storage_dir = get_storage_dir()

    default_config = subprocess.check_output(
        ["find", os.path.join(storage_dir, "sysroot/ostree/deploy"),
         "-type", "f", "-name", PLYMOUTH_CONFIG, "-print", "-quit"], text=True)

    if not default_config:
        raise PathNotExistError("Could not find default Plymouth configuration file.")

    return default_config.rstrip()


def add_plymouth_splash_config(root_dir, config):
    """Add splash config in the Plymouth theme directory tree relative to root_dir"""

    add_plymouth_theme_file(root_dir, config, PLYMOUTH_CONFIG)
