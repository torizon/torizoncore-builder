"""
Backend for the splash command
"""

import logging
import os
import shutil

from tcbuilder.backend.common import get_storage_dir

log = logging.getLogger("torizon." + __name__)

PLYMOUTH_THEME_PATH = "usr/share/plymouth/themes/spinner/"
PLYMOUTH_SPLASH_FILENAME = "watermark.png"

def get_splash_changes_dir():
    """Returns the directory that contains external splash screen related changes."""

    storage_dir = get_storage_dir()
    return os.path.join(storage_dir, "splash")


def add_plymouth_theme_file(root_dir, src_file, dst_filename=None):
    """Add file in the Plymouth spinner theme directory tree relative to root_dir"""

    plymouth_theme_abspath = os.path.join(root_dir, PLYMOUTH_THEME_PATH)
    os.makedirs(plymouth_theme_abspath, exist_ok=True)

    if dst_filename:
        plymouth_theme_abspath = os.path.join(plymouth_theme_abspath, dst_filename)

    log.debug(f"Splash: copying {src_file} -> {plymouth_theme_abspath}")
    shutil.copy2(src_file, plymouth_theme_abspath)


def add_plymouth_splash_image(root_dir, splash_img):
    """Add splash image in the Plymouth theme directory tree relative to root_dir"""

    add_plymouth_theme_file(root_dir, splash_img, PLYMOUTH_SPLASH_FILENAME)
