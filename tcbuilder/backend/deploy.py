"""
Backend handling for the deploy subcommand.
"""

import json
import logging
import os
import shutil
import subprocess
import threading

import paramiko

# pylint: disable=wrong-import-position
import gi
gi.require_version("OSTree", "1.0")
from gi.repository import Gio, OSTree

from tcbuilder.backend import ostree
from tcbuilder.backend.common import get_rootfs_tarball, resolve_remote_host
from tcbuilder.backend.rforward import reverse_forward_tunnel
from tcbuilder.errors import TorizonCoreBuilderError, InvalidDataError
from tezi.utils import find_rootfs_content
# pylint: enable=wrong-import-position

log = logging.getLogger("torizon." + __name__)

OSNAME = "torizon"

def create_sysroot(deploy_sysroot_dir):
    sysroot = OSTree.Sysroot.new(Gio.File.new_for_path(deploy_sysroot_dir))

    if not sysroot.ensure_initialized():
        raise TorizonCoreBuilderError("Error initializing OSTree sysroot.")

    if not sysroot.init_osname(OSNAME):
        raise TorizonCoreBuilderError("Error initializing OSTree osname.")

    if not sysroot.load():
        raise TorizonCoreBuilderError("Error loading OSTree sysroot.")

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
    if not sysroot.simple_write_deployment(
            OSNAME, deployment, None,
            OSTree.SysrootSimpleWriteDeploymentFlags.NO_CLEAN):
        raise TorizonCoreBuilderError("Error writing deployment.")


def update_uncompressed_image_size(image_filename):
    """
    Update the 'uncompressed_size' field of the 'image.json' file.

    :param image_filename: Compressed image filename.
    """

    # '.zst' is the default compression used, but it can also be '.xz'
    cmd = ["zstd", "-l", f"{image_filename}"]
    if image_filename.endswith(".xz"):
        cmd[0] = "xz"

    output = subprocess.check_output(cmd)
    uncompressed_image_size = output.split()[11] # Uncompressed field of zstd/xz -l

    image_json = os.path.join(os.path.dirname(image_filename), 'image.json')
    with open(image_json, "r", encoding="utf-8") as jsonfile:
        jsondata = json.load(jsonfile)
    content = find_rootfs_content(jsondata)
    if content is None:
        raise InvalidDataError(
            "No root file system content section found in Easy Installer image.")

    content["uncompressed_size"] = float(uncompressed_image_size)
    with open(image_json, "w", encoding="utf-8") as jsonfile:
        json.dump(jsondata, jsonfile, indent=4)


def create_installed_versions(path, ref, branch):
    with open(os.path.join(path, "installed_versions"), "w") as versionfile:
        versioninfo = {}
        versioninfo[ref] = branch + "-" + ref
        json.dump(versioninfo, versionfile)

def copy_tezi_image(src_tezi_dir, dst_tezi_dir):
    shutil.copytree(src_tezi_dir, dst_tezi_dir)

def pack_rootfs_for_tezi(dst_sysroot_dir, output_dir):
    image_filename = get_rootfs_tarball(output_dir)

    if image_filename.endswith(".xz"):
        uncompressed_file = image_filename.replace(".xz", "")
        compress_cmd = f"xz -z {uncompressed_file}"
    elif image_filename.endswith(".zst"):
        uncompressed_file = image_filename.replace(".zst", "")
        compress_cmd = f"zstd --rm {uncompressed_file}"

    # pylint: disable=line-too-long
    # This is a OSTree bare repository. Care must been taken to preserve all
    # file system attributes. Python tar does not support xattrs, so use GNU tar
    # here.
    # See: https://dev.gentoo.org/~mgorny/articles/portability-of-tar-features.html#extended-file-metadata
    # pylint: enable=line-too-long
    tar_cmd = "tar --xattrs --xattrs-include='*' -cf {0} -S -C {1} -p .".format(
        uncompressed_file, dst_sysroot_dir)
    log.debug(f"Running tar command: {tar_cmd}")
    subprocess.check_output(tar_cmd, shell=True, stderr=subprocess.STDOUT)

    log.debug(f"Running compress command: {compress_cmd}")
    subprocess.check_output(compress_cmd, shell=True, stderr=subprocess.STDOUT)

    update_uncompressed_image_size(image_filename)


def copy_files_from_old_sysroot(src_sysroot, dst_sysroot):
    # Call get_path twice to receive the local path instead of an
    # OSTree object
    src_path = src_sysroot.get_path().get_path()
    dst_path = dst_sysroot.get_path().get_path()
    var_path = os.path.join("ostree/deploy", OSNAME, "var")
    copy_list = [
        {"src": os.path.join(src_path, var_path, "rootdirs"),
         "dst": os.path.join(dst_path, var_path)},
        {"src": os.path.join(src_path, "boot.scr"), "dst": dst_path}
    ]

    for copy_file in copy_list:
        # shutil.copytree does not preserve ownership
        if subprocess.Popen(['cp', '-a', '-t', copy_file['dst'], copy_file['src']]).wait():
            raise TorizonCoreBuilderError("Cannot deploy home directories.")

# pylint: disable=too-many-locals
def deploy_tezi_image(tezi_dir, src_sysroot_dir, src_ostree_archive_dir,
                      output_dir, dst_sysroot_dir, ref=None):
    """Deploys a Toradex Easy Installer image with given OSTree reference

    Creates a new Toradex Easy Installer image with a OSTree deployment of the
    given OSTree reference.
    """
    # It seems the customer did not pass a reference, deploy the original commit
    # (probably not that useful in practice, but useful to test the workflow)
    if ref is None:
        ref = ostree.OSTREE_BASE_REF
    print(f"Deploying commit ref: {ref}")

    # Create a new sysroot for our deployment
    sysroot = create_sysroot(dst_sysroot_dir)
    repo = sysroot.repo()

    # We need to resolve the reference to a checksum again, otherwise
    # pull_local_ref complains with:
    # "Commit has no requested ref ‘base’ in ref binding metadata"
    srcrepo = ostree.open_ostree(src_ostree_archive_dir)
    ret, csumdeploy = srcrepo.resolve_rev(ref, False)
    if not ret:
        raise TorizonCoreBuilderError(f"Error resolving {ref}.")

    # Get metadata from the commit being requested.
    srcmeta, _subject, _body = ostree.get_metadata_from_ref(srcrepo, csumdeploy)
    srckargs = srcmeta['oe.kargs-default']

    log.info(f"Pulling OSTree with ref {ref} from local archive repository...")
    log.info(f"  Commit checksum: {csumdeploy}")
    log.info(f"  TorizonCore Version: {srcmeta['version']}")
    log.info(f"  Default kernel arguments: {srckargs}\n")

    ostree.pull_local_ref(repo, src_ostree_archive_dir, csumdeploy, remote="torizon")
    log.info("Pulling done.")

    log.info(f"Deploying OSTree with checksum {csumdeploy}")

    # Deploy commit with default kernel arguments.
    deploy_rootfs(sysroot, csumdeploy, "torizon", srckargs)
    log.info("Deploying done.")

    # Currently we use the sysroot from the unpacked Tezi rootfs as source for
    # /home directories
    log.info("Copy files not under OSTree control from original deployment.")
    src_sysroot = ostree.load_sysroot(src_sysroot_dir)
    copy_files_from_old_sysroot(src_sysroot, sysroot)

    log.info("Packing rootfs...")
    copy_tezi_image(tezi_dir, output_dir)
    pack_rootfs_for_tezi(dst_sysroot_dir, output_dir)
    log.info("Packing rootfs done.")
# pylint: enable=too-many-locals


def run_command_with_sudo(client, command, password):
    stdin, stdout, stderr = client.exec_command("sudo -S -- " + command)
    stdin.write(f"{password}\n")
    stdin.flush()
    status = stdout.channel.recv_exit_status()  # wait for exec_command to finish

    stdout_str = stdout.read().decode('utf-8').strip()
    stderr_str = stderr.read().decode('utf-8').strip()

    if status != 0:
        if len(stdout_str) > 0:
            log.info(stdout_str)
        if len(stderr_str) > 0:
            log.error(stderr_str)
        raise TorizonCoreBuilderError(f"Failed to run command on module: {command}")

    if len(stdout_str) > 0:
        log.debug(stdout_str)
    if len(stderr_str) > 0:
        log.debug(stderr_str)


def deploy_ostree_remote(remote_host, remote_username, remote_password, remote_port,
                         remote_mdns, src_ostree_archive_dir, ref, reboot=False):
    """Implementation to deploy OSTree on remote device"""

    # It seems the customer did not pass a reference, deploy the original commit
    # (probably not that useful in practise, but useful to test the workflow)
    if ref is None:
        ref = ostree.OSTREE_BASE_REF

    # We need to resolve the reference to a checksum again, otherwise we
    # pull_local_ref complains with:
    # "Commit has no requested ref ‘base’ in ref binding metadata"
    srcrepo = ostree.open_ostree(src_ostree_archive_dir)
    ret, csumdeploy = srcrepo.resolve_rev(ref, False)
    if not ret:
        raise TorizonCoreBuilderError(f"Error resolving {ref}.")

    log.info(f"Pulling OSTree with ref {ref} (checksum {csumdeploy}) "
             "from local archive repository...")

    # Start http server...
    http_server_thread = ostree.serve_ostree_start(src_ostree_archive_dir, "localhost")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    resolved_remote_host = resolve_remote_host(remote_host, remote_mdns)
    client.connect(hostname=resolved_remote_host,
                   username=remote_username,
                   password=remote_password,
                   port=remote_port)

    forwarding_thread = threading.Thread(target=reverse_forward_tunnel,
                                         args=(8080, "127.0.0.1", 8080, client.get_transport()))
    forwarding_thread.daemon = True
    forwarding_thread.start()

    run_command_with_sudo(
        client,
        "ostree remote add --no-gpg-verify --force tcbuilder http://localhost:8080/",
        remote_password)

    log.info("Starting OSTree pull on the device...")
    run_command_with_sudo(
        client, f"ostree pull tcbuilder:{csumdeploy}", remote_password)

    log.info("Deploying new OSTree on the device...")
    # Do the final staging after we set upgrade_available, therefore option --stage
    run_command_with_sudo(
        client, f"ostree admin deploy --stage tcbuilder:{csumdeploy}", remote_password)

    # Make sure we set bootcount to 0, it can be > 1 from previous runs
    run_command_with_sudo(
        client, "fw_setenv bootcount 0", remote_password)

    # Make sure we remove the rollback flag from previous runs
    run_command_with_sudo(
        client, "fw_setenv rollback 0", remote_password)

    # Set upgrade_available for U-Boot
    run_command_with_sudo(
        client, "fw_setenv upgrade_available 1", remote_password)

    # Finalize the update after we set upgrade_available for U-Boot
    run_command_with_sudo(
        client, "ostree admin finalize-staged", remote_password)

    log.info("Deploying successfully finished.")

    if reboot:
        # If reboot is started in foreground it leads to exit code <> 0 sometimes
        # which leads to a stack trace in torizoncore-builder. Start in background
        # to make the command run successfully always.
        run_command_with_sudo(client, "sh -c 'reboot &'", remote_password)
        log.info("Device reboot initiated...")
    else:
        log.info("Please reboot the device to boot into the new deployment.")

    client.close()

    ostree.serve_ostree_stop(http_server_thread)
