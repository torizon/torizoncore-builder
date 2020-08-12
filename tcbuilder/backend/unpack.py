import os
import logging
import subprocess
from tcbuilder.backend.common import get_rootfs_tarball


def unpack_local_image(image_dir, sysroot_dir):
    tarfile = get_rootfs_tarball(image_dir)

    # This is a OSTree bare repository. Care must been taken to preserve all
    # file system attributes. Python tar does not support xattrs, so use GNU tar
    # here
    # See: https://dev.gentoo.org/~mgorny/articles/portability-of-tar-features.html#extended-file-metadata
    tarcmd = "tar --xattrs --xattrs-include='*' -xhf {0} -C {1}".format(
                tarfile, sysroot_dir)
    logging.info(f"Running tar command: {tarcmd}")
    subprocess.check_output(tarcmd, shell=True, stderr=subprocess.STDOUT)

    # Remove the tarball since we have it unpacked now
    os.unlink(tarfile)
