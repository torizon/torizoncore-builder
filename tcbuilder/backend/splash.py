"""
Backend for the splash command
"""

import logging
import os
import shutil
import subprocess

from gi.repository import Gio

from tcbuilder.backend import ostree
from tcbuilder.errors import TorizonCoreBuilderError

log = logging.getLogger("torizon." + __name__)


def create_splash_initramfs(work_dir, image, src_ostree_archive_dir):
    """Create a initramfs with a splash screen and append it to the current initramfs"""

    splash_initramfs = "initramfs.splash"
    splash_initramfs_dir = "usr/share/plymouth/themes/spinner/"
    rel_splash_initramfs_dir = os.path.join(work_dir, splash_initramfs_dir)  # relative to work_dir

    if os.path.exists(rel_splash_initramfs_dir):
        shutil.rmtree(rel_splash_initramfs_dir)

    os.makedirs(rel_splash_initramfs_dir)
    shutil.copy(image, os.path.join(rel_splash_initramfs_dir, "watermark.png"))

    # Currently there is no official library for python 3+ to create
    # cpio archive. So bash commands are to be used

    # create splash image only initramfs
    create_initramfs_cmd = "echo {0} | cpio -H newc -D {1} -o | gzip > {2}".format(
        os.path.join(splash_initramfs_dir, "watermark.png"), work_dir, \
                            os.path.join(work_dir, splash_initramfs))
    subprocess.check_output(create_initramfs_cmd, shell=True, stderr=subprocess.STDOUT)
    shutil.rmtree(os.path.join(work_dir, "usr/share"))

    # get path of initramfs of current deployment inside sysroot
    repo = ostree.open_ostree(src_ostree_archive_dir)
    kernel_version = ostree.get_kernel_version(repo, ostree.OSTREE_BASE_REF)

    # implement cat `ostree cat ref /usr/lib/modules/${kver}/initramfs.img`
    # /storage/splash/initrmafs.splash > /storage/splash/usr/lib/modules/${kver}/initramfs.img
    ret, root, _commit = repo.read_commit(ostree.OSTREE_BASE_REF)
    if not ret:
        raise TorizonCoreBuilderError(f"Error couldn't reat commit: {ostree.OSTREE_BASE_REF}")

    sub_path = root.resolve_relative_path(os.path.join("usr/lib/modules",
                                                       kernel_version, "initramfs.img"))

    # create directory for storing finalized initramfs
    os.makedirs(os.path.join(work_dir, "usr/lib/modules", kernel_version))

    initramfs = Gio.File.new_for_path(
        os.path.join(work_dir, "usr/lib/modules", kernel_version, "initramfs.img")
        ).create(Gio.FileCreateFlags.NONE, None)

    initramfs.splice(sub_path.read(None), Gio.OutputStreamSpliceFlags.CLOSE_SOURCE, None)
    initramfs.splice(Gio.File.new_for_path(os.path.join(work_dir, splash_initramfs)).read(None),
                     Gio.OutputStreamSpliceFlags.CLOSE_SOURCE |
                     Gio.OutputStreamSpliceFlags.CLOSE_TARGET, None)

    os.remove(os.path.join(work_dir, splash_initramfs))
