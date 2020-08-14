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
from tcbuilder.backend import ostree
import re

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

def deploy_tezi_image(tezi_dir, src_sysroot_dir, src_ostree_archive_dir,
                      output_dir, dst_sysroot_dir, ref=None):
    """Deploys a Toradex Easy Installer image with given OSTree reference

    Creates a new Toradex Easy Installer image with a OSTree deployment of the
    given OSTree reference.
    """
    # Currently we use the sysroot from the unpacked Tezi rootfs as source
    # for kargs, /home directories
    src_sysroot = ostree.load_sysroot(src_sysroot_dir)
    csum, kargs = ostree.get_deployment_info_from_sysroot(src_sysroot)
    metadata, _subject, _body = ostree.get_metadata_from_ref(src_sysroot.repo(), csum)

    log.info("Using unpacked Toradex Easy Installer image as base:")
    log.info(f"  Commit checksum: {csum}")
    log.info(f"  TorizonCore Version: {metadata['version']}")
    log.info(f"  Kernel arguments: {kargs}\n")

    # It seems the customer did not pass a reference, deploy the original commit
    # (probably not that useful in practise, but useful to test the workflow)
    if ref is None:
        ref = ostree.OSTREE_BASE_REF
    print(f"Deploying commit ref: {ref}")

    # Create a new sysroot for our deployment
    sysroot = create_sysroot(dst_sysroot_dir)

    repo = sysroot.repo()

    log.info(f"Pulling OSTree with ref {ref} from local archive repository...")
    ostree.pull_local_ref(repo, src_ostree_archive_dir, ref, remote="torizon")
    log.info("Pulling done.")

    log.info(f"Deploying OSTree with ref {ref}")

    # Remove old ostree= kernel argument
    newkargs = re.sub(r"ostree=[^\s]*", "", kargs)
    deploy_rootfs(sysroot, ref, "torizon", newkargs)
    log.info("Deploying done.")

    log.info("Copy rootdirs such as /home from original deployment.")
    copy_home_from_old_sysroot(src_sysroot, sysroot)

    log.info("Packing rootfs...")
    copy_tezi_image(tezi_dir, output_dir)
    pack_rootfs_for_tezi(dst_sysroot_dir, output_dir)
    log.info("Packing rootfs done.")