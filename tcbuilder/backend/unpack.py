import os
import shutil
import logging
import subprocess
from tcbuilder.backend.common import get_rootfs_tarball, get_unpack_command
from tcbuilder.backend import ostree

log = logging.getLogger("torizon." + __name__)

def unpack_local_image(image_dir, sysroot_dir):
    tarfile = get_rootfs_tarball(image_dir)

    # This is a OSTree bare repository. Care must been taken to preserve all
    # file system attributes. Python tar does not support xattrs, so use GNU tar
    # here
    # See: https://dev.gentoo.org/~mgorny/articles/portability-of-tar-features.html#extended-file-metadata
    tarcmd = "cat '{0}' | {1} | tar --xattrs --xattrs-include='*' -xhf - -C {2}".format(
                tarfile, get_unpack_command(tarfile), sysroot_dir)
    log.debug(f"Running tar command: {tarcmd}")
    subprocess.check_output(tarcmd, shell=True, stderr=subprocess.STDOUT)

    # Remove the tarball since we have it unpacked now
    os.unlink(tarfile)

def import_local_image(image_dir, tezi_dir, src_sysroot_dir, src_ostree_archive_dir):
    """Import local Toradex Easy Installer image

    Import local Toradex Easy installer image to be customized. Assuming an
    empty/non-existing src_sysroot_dir as well as src_ostree_archive_dir.
    """
    os.mkdir(src_sysroot_dir)

    log.info("Copying Toradex Easy Installer image.")
    shutil.copytree(image_dir, tezi_dir)

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
