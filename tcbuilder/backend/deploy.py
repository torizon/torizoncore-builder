import json
import logging
import os
import shutil
import subprocess

import gi
gi.require_version("OSTree", "1.0")
from gi.repository import Gio, OSTree

from tcbuilder.backend.common import get_rootfs_tarball
from tcbuilder.errors import TorizonCoreBuilderError

log = logging.getLogger("torizon." + __name__)

OSNAME = "torizon"

def create_sysroot(deploy_sysroot_dir):
    sysroot = OSTree.Sysroot.new(Gio.File.new_for_path(deploy_sysroot_dir))

    if not sysroot.ensure_initialized():
        raise TorizonCoreBuilderError("Error initializing sysroot.")

    if not sysroot.init_osname(OSNAME):
        raise TorizonCoreBuilderError("Error initializing osname.")

    if not sysroot.load():
        raise TorizonCoreBuilderError("Error loading sysroot.")

    return sysroot

def deploy_rootfs(sysroot, ref, refspec, kargs):
    """ deploy OSTree commit given by ref in sysroot with kernel arguments

        args:

            sysroot(OSTree.Sysroot) - sysroot object
            ref(str) - reference to deploy
            kargs(str) = kernel arguments

        raises:
            Exception - for failure to perform operations
    """
    result, revision = sysroot.repo().resolve_rev(ref, False)
    if not result:
        raise TorizonCoreBuilderError(f"Error getting revision of reference {ref}.")

    keyfile = sysroot.origin_new_from_refspec(refspec)

    # ostree admin --sysroot=${OTA_SYSROOT} deploy ${kargs_list} --os=${OSTREE_OSNAME} ${revision}
    log.debug(f"Deploying revision {revision}")
    result, deployment = sysroot.deploy_tree(
        OSNAME, revision, keyfile, None, kargs.split())
    if not result:
        raise TorizonCoreBuilderError("Error creating deployment.")

    # Create boot file to trigger U-Boot detection
    bootdir = os.path.join(sysroot.get_path().get_path(), "boot")

    os.makedirs(bootdir)
    os.makedirs(os.path.join(bootdir, "loader.1"))
    os.symlink("loader.1", os.path.join(bootdir, "loader"))

    file = open(os.path.join(bootdir, "loader/uEnv.txt"), "w")
    file.close()

    log.debug(f"Write deployment for revision {revision}")
    if not sysroot.simple_write_deployment(OSNAME, deployment, None,
            OSTree.SysrootSimpleWriteDeploymentFlags.NO_CLEAN):
        raise TorizonCoreBuilderError("Error writing deployment.")

def get_var_path(sysroot):
    return os.path.join(sysroot.get_path().get_path(), "ostree/deploy", OSNAME, "var")

def create_installed_versions(path, ref, branch):
    with open(os.path.join(path, "installed_versions"), "w") as versionfile:
        versioninfo = {}
        versioninfo[ref] = branch + "-" + ref
        json.dump(versioninfo, versionfile)

def copy_tezi_image(src_tezi_dir, dst_tezi_dir):
    shutil.copytree(src_tezi_dir, dst_tezi_dir)

def pack_rootfs_for_tezi(dst_sysroot_dir, output_dir):
    tarfile = get_rootfs_tarball(output_dir)

    compression = ""
    if tarfile.endswith(".xz"):
        compression = "--xz"
    elif tarfile.endswith(".zst"):
        compression = "--zstd"

    # This is a OSTree bare repository. Care must been taken to preserve all
    # file system attributes. Python tar does not support xattrs, so use GNU tar
    # here
    # See: https://dev.gentoo.org/~mgorny/articles/portability-of-tar-features.html#extended-file-metadata
    tarcmd = "tar --xattrs --xattrs-include='*' -cf {0} {1} -S -C {2} -p .".format(
                tarfile, compression, dst_sysroot_dir)
    log.debug(f"Running tar command: {tarcmd}")
    subprocess.check_output(tarcmd, shell=True, stderr=subprocess.STDOUT,
                            env={ "XZ_OPT": "-1" })

def copy_home_from_old_sysroot(src_sysroot, dst_sysroot):
    src_var = get_var_path(src_sysroot)
    dst_var = get_var_path(dst_sysroot)
    shutil.copytree(os.path.join(src_var, "rootdirs"),
        os.path.join(dst_var, "rootdirs"), symlinks=True)
