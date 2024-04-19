"""
Backend handling for the deploy subcommand.
"""

import json
import logging
import os
import shutil
import subprocess
import threading
import shlex

import guestfs
import paramiko

# pylint: disable=wrong-import-position
import gi
gi.require_version("OSTree", "1.0")
from gi.repository import Gio, OSTree

from tcbuilder.backend import ostree
from tcbuilder.backend.common import (get_rootfs_tarball, resolve_remote_host,
                                      run_with_loading_animation)
from tcbuilder.backend.rforward import reverse_forward_tunnel, request_port_forward
from tcbuilder.errors import TorizonCoreBuilderError, InvalidDataError
from tezi.utils import find_rootfs_content
# pylint: enable=wrong-import-position

log = logging.getLogger("torizon." + __name__)

OSNAME = "torizon"
EXTRA_ROOTFS_SIZE_KB = 0
# Value based on
# https://github.com/torizon/meta-toradex-torizon/blob/953aacb8b3241ea26f98e853d1a1d4c8463636a4/recipes-images/images/torizon-core-common.inc#L11
IMAGE_OVERHEAD_FACTOR = 2.3

def create_sysroot(deploy_sysroot_dir):
    sysroot = OSTree.Sysroot.new(Gio.File.new_for_path(deploy_sysroot_dir))

    if not sysroot.ensure_initialized():
        raise TorizonCoreBuilderError("Error initializing OSTree sysroot.")

    if not sysroot.init_osname(OSNAME):
        raise TorizonCoreBuilderError("Error initializing OSTree osname.")

    if not sysroot.load():
        raise TorizonCoreBuilderError("Error loading OSTree sysroot.")

    return sysroot


def get_image_bootloader(sysroot_dir):
    """
    Get bootloader being used in a given unpacked sysroot

    :param sysroot_dir: sysroot path

    Based on:
    - https://github.com/ostreedev/ostree/blob/v2024.4/src/libostree/ostree-bootloader-uboot.c#L47
    - https://github.com/ostreedev/ostree/blob/v2024.4/src/libostree/ostree-bootloader-grub2.c#L73
    """
    tentative_uenv_path = os.path.join(sysroot_dir, "boot/loader/uEnv.txt")

    if os.path.exists(tentative_uenv_path):
        return "U-Boot"

    tentative_grubcfg_path1 = os.path.join(sysroot_dir, "boot/grub/grub.cfg")
    tentative_grubcfg_path2 = os.path.join(sysroot_dir, "boot/grub2/grub.cfg")

    if (os.path.exists(tentative_grubcfg_path1) or
            os.path.exists(tentative_grubcfg_path2)):
        return "GRUB2"

    tentative_efi_dir_path = os.path.join(sysroot_dir, "boot/efi/EFI")
    if (os.path.exists(tentative_efi_dir_path) and
            os.path.isdir(tentative_efi_dir_path)):
        for _, _, files in os.walk(tentative_efi_dir_path):
            if "grub.cfg" in files:
                return "GRUB2"

    return "UNSUPPORTED"


def deploy_rootfs(sysroot, src_sysroot_dir, ref, refspec, kargs):
    """ deploy OSTree commit given by ref in sysroot with kernel arguments

        args:

            sysroot(OSTree.Sysroot) - sysroot object
            src_sysroot_dir(str) - path to src sysroot
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
        OSNAME, revision, keyfile, None, shlex.split(kargs))
    if not result:
        raise TorizonCoreBuilderError("Error creating deployment.")

    # Create boot file to trigger U-Boot detection
    bootdir = os.path.join(sysroot.get_path().get_path(), "boot")

    os.makedirs(bootdir)
    os.makedirs(os.path.join(bootdir, "loader.1"))
    os.symlink("loader.1", os.path.join(bootdir, "loader"))

    bootloader_found = get_image_bootloader(src_sysroot_dir)

    if bootloader_found == "GRUB2":
        log.info("Bootloader found in unpacked image: GRUB2")
        os.environ["OSTREE_BOOT_PARTITION"] = "/boot"
        os.environ["OSTREE_GRUB2_EXEC"] = \
            "/builder/tcbuilder/ostree-grub-generator"
        os.makedirs(os.path.join(bootdir, "grub2"))
        os.symlink("../loader/grub.cfg", os.path.join(bootdir, "grub2/grub.cfg"))
    elif bootloader_found == "U-Boot":
        log.info("Bootloader found in unpacked image: U-Boot")
        file = open(os.path.join(bootdir, "loader/uEnv.txt"), "w")
        file.close()
    else:
        raise TorizonCoreBuilderError(
            "Aborting: Couldn't determine bootloader in unpacked image or "
            "bootloader isn't supported."
            "\nSupported bootloaders: U-Boot, GRUB2.")

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
        compress_cmd = ["xz", "-z", uncompressed_file]
    elif image_filename.endswith(".zst"):
        uncompressed_file = image_filename.replace(".zst", "")
        compress_cmd = ["zstd", "--rm", uncompressed_file]

    # pylint: disable=line-too-long
    # This is a OSTree bare repository. Care must been taken to preserve all
    # file system attributes. Python tar does not support xattrs, so use GNU tar
    # here.
    # See: https://dev.gentoo.org/~mgorny/articles/portability-of-tar-features.html#extended-file-metadata
    # pylint: enable=line-too-long
    tar_cmd = [
        "tar",
        "--xattrs", "--xattrs-include=*",
        "-cf", uncompressed_file,
        "-S", "-C", dst_sysroot_dir,
        "-p", "."
    ]
    log.debug(f"Running tar command: {shlex.join(tar_cmd)}")
    subprocess.check_output(tar_cmd, stderr=subprocess.STDOUT)

    log.debug(f"Running compress command: {shlex.join(compress_cmd)}")
    subprocess.check_output(compress_cmd, stderr=subprocess.STDOUT)

    update_uncompressed_image_size(image_filename)


def copy_files_from_old_sysroot(src_sysroot, dst_sysroot):
    # Call get_path twice to receive the local path instead of an
    # OSTree object
    src_path = src_sysroot.get_path().get_path()
    dst_path = dst_sysroot.get_path().get_path()
    var_path = os.path.join("ostree/deploy", OSNAME, "var")
    copy_list = [
        {"src": os.path.join(src_path, var_path, "rootdirs"),
         "dst": os.path.join(dst_path, var_path)}
    ]

    if os.path.exists(os.path.join(src_path, "boot.scr")):
        copy_list.append({"src": os.path.join(src_path, "boot.scr"), "dst": dst_path})

    for copy_file in copy_list:
        # shutil.copytree does not preserve ownership
        if subprocess.Popen(['cp', '-a', '-t', copy_file['dst'], copy_file['src']]).wait():
            raise TorizonCoreBuilderError("Cannot deploy home directories.")

# pylint: disable=too-many-locals
def deploy_ostree_local(src_sysroot_dir, src_ostree_archive_dir,
                        dst_sysroot_dir, ref):
    """Deploys a local OSTree ref in a given directory"""

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

    target_refs = {ref: csumdeploy}
    ostree.pull_local_refs(repo, src_ostree_archive_dir, refs=target_refs,
                           remote="torizon")
    log.info("Pulling done.")

    log.info(f"Deploying OSTree with checksum {csumdeploy}")

    # Deploy commit with default kernel arguments.
    deploy_rootfs(sysroot, src_sysroot_dir, csumdeploy, "torizon", srckargs)
    log.info("Deploying done.")

    # Currently we use the sysroot from the unpacked Tezi rootfs as source for
    # /home directories
    log.info("Copy files not under OSTree control from original deployment.")
    src_sysroot = ostree.load_sysroot(src_sysroot_dir)
    copy_files_from_old_sysroot(src_sysroot, sysroot)
# pylint: enable=too-many-locals


def deploy_tezi_image(tezi_dir, src_sysroot_dir, src_ostree_archive_dir,
                      output_dir, dst_sysroot_dir, ref=None):
    """Deploys a Toradex Easy Installer image with given OSTree reference

    Creates a new Toradex Easy Installer image with a OSTree deployment of the
    given OSTree reference.
    """
    deploy_ostree_local(src_sysroot_dir, src_ostree_archive_dir, dst_sysroot_dir, ref)

    log.info("Packing rootfs...")
    copy_tezi_image(tezi_dir, output_dir)
    pack_rootfs_for_tezi(dst_sysroot_dir, output_dir)
    log.info("Packing rootfs done.")


def write_rootfs_to_raw_image(base_raw_img, output_raw_img, base_rootfs_partition, rootfs_label,
                              base_rootfs_partition_size_kb, other_partitions_size_kb,
                              rootfs_size_kb, dst_sysroot_dir):
    """Writes unpacked rootfs contents to an output raw image

    Writes the current unpacked rootfs to a raw image that is based on
    an input image. If the unpacked rootfs has a larger size than the base
    rootfs partition the output image is increased accordingly.
    """
    out_size_kb = max(base_rootfs_partition_size_kb, rootfs_size_kb * IMAGE_OVERHEAD_FACTOR)
    out_size_kb += EXTRA_ROOTFS_SIZE_KB
    out_size_kb += other_partitions_size_kb

    # Create new image file:
    subprocess.check_output(["truncate", "-s", f"+{int(out_size_kb)}K", output_raw_img])
    log.debug(f"Created empty output image: {output_raw_img}")
    log.debug(f"Image overhead factor: {IMAGE_OVERHEAD_FACTOR}")
    log.debug(f"Extra rootfs size added: {EXTRA_ROOTFS_SIZE_KB/1024} MiB")

    log.info(f"Size of output image will be: {out_size_kb/1024/1024:.2f} GiB")

    # With virt-resize, copy base image to output image, except base_rootfs_partition:
    log.info("Copying other partitions from base to output image. Starting virt-resize...")
    log.info("------------------------------------------------------------")
    resizecmd = ["virt-resize", "--format", "raw", "--delete"]
    resizecmd.extend([base_rootfs_partition, base_raw_img, output_raw_img])
    subprocess.run(resizecmd, check=True)
    log.info("------------------------------------------------------------")

    try:
        gfs = guestfs.GuestFS(python_return_dict=True)
        gfs.add_drive_opts(output_raw_img, format="raw")
        run_with_loading_animation(
            func=gfs.launch,
            loading_msg="Initializing output image...")

        # virt-resize rearranged all existing partitions and generated a new empty partition at the
        # end of the disk. We will format it to ext4 and put the unpacked rootfs contents in it.

        # Its partition number (/dev/sda1, /dev/sda2, etc.) is equal to the number of partitions
        # in the image, given that it is the last one.

        output_rootfs_partition = f"/dev/sda{len(gfs.list_partitions())}"
        log.info(f"Creating new '{rootfs_label}' rootfs partition at {output_rootfs_partition}.")

        gfs.mkfs("ext4", output_rootfs_partition)
        gfs.set_label(output_rootfs_partition, rootfs_label)
        gfs.mount(output_rootfs_partition, "/")

        dst_sysroot_dir_ls = os.listdir(dst_sysroot_dir)
        if 'lost+found' in dst_sysroot_dir_ls:
            dst_sysroot_dir_ls.remove('lost+found')

        log.info("Copying unpacked rootfs contents to output image. This may take a few minutes...")
        for content in dst_sysroot_dir_ls:
            run_with_loading_animation(
                func=gfs.copy_in,
                args=(f"{dst_sysroot_dir}/{content}", "/"),
                loading_msg=f"  Copying /{content}...")

        gfs.shutdown()
        gfs.close()
    except RuntimeError as gfserr:
        if gfs:
            gfs.close()
        raise TorizonCoreBuilderError(f"guestfs: {gfserr.args[0]}")


def deploy_raw_image(base_raw_img, src_sysroot_dir, src_ostree_archive_dir,
                     output_raw_img, dst_sysroot_dir, rootfs_label, ref=None):
    """Deploys a WIC image with given OSTree reference

    Creates a new WIC image with an OSTree deployment of the
    given OSTree reference.
    """
    deploy_ostree_local(src_sysroot_dir, src_ostree_archive_dir, dst_sysroot_dir, ref)

    try:
        gfs = guestfs.GuestFS(python_return_dict=True)
        gfs.add_drive_opts(base_raw_img, format="raw", readonly=1)
        run_with_loading_animation(
            func=gfs.launch,
            loading_msg="Initializing base WIC/raw image...")
        if len(gfs.list_partitions()) < 1:
            raise TorizonCoreBuilderError(
                "Image doesn't have any partitions or it's not a valid WIC/raw image. Aborting.")
        # Get partition number from ext4 fs called rootfs_label in disk image (.wic/.img)
        rootfs_partition = gfs.findfs_label(rootfs_label)
        log.info(f"  '{rootfs_label}' partition found: {rootfs_partition}")

        base_rootfs_partition_size_kb = gfs.blockdev_getsize64(rootfs_partition) / 1024

        other_partitions_size_kb = 0
        partitions = gfs.list_partitions()
        partitions.remove(rootfs_partition)
        for part in partitions:
            other_partitions_size_kb += gfs.blockdev_getsize64(part) / 1024

        # Close read-only handle
        gfs.shutdown()
        gfs.close()
    except RuntimeError as gfserr:
        if gfs:
            gfs.close()
        if f"unable to resolve 'LABEL={rootfs_label}'" in str(gfserr):
            raise TorizonCoreBuilderError(
                f"Filesystem with label '{rootfs_label}' not found in image. Aborting.")

        raise TorizonCoreBuilderError(f"guestfs: {str(gfserr)}")

    log.info(f"  rootfs partition size: {base_rootfs_partition_size_kb/1024/1024:.2f} GiB")
    log.info(f"  Size of other partitions combined: {other_partitions_size_kb/1024/1024:.2f} GiB")

    rootfs_size_kb = subprocess.check_output(["du", "-s", dst_sysroot_dir], text=True)
    rootfs_size_kb = int(rootfs_size_kb.split('\t')[0])
    log.info(f"Unpacked rootfs size: {rootfs_size_kb/1024/1024:.2f} GiB")

    write_rootfs_to_raw_image(base_raw_img, output_raw_img, rootfs_partition, rootfs_label,
                              base_rootfs_partition_size_kb, other_partitions_size_kb,
                              rootfs_size_kb, dst_sysroot_dir)
    log.info(f"Image {os.path.basename(output_raw_img)} created successfully!")

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


# pylint: disable=too-many-locals
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

    # Get metadata from the commit being requested.
    srcmeta, _subject, _body = ostree.get_metadata_from_ref(srcrepo, csumdeploy)
    srckargs = srcmeta['oe.kargs-default']

    # Create kargs arguments based on metadata
    args_list = ['--karg-none']
    for arg in shlex.split(srckargs):
        arg = f"--karg-append={arg}"
        args_list.append(arg)

    args_cli = shlex.join(args_list)

    log.info(f"Pulling OSTree with ref {ref} (checksum {csumdeploy}) "
             "from local archive repository...")

    # Start http server...
    http_server_thread = ostree.serve_ostree_start(src_ostree_archive_dir,
                                                   "localhost", port=0)

    # Get the dynamic port the HTTP server is listening on
    local_ostree_server_port = http_server_thread.server_port
    log.info(f'OSTree server listening on "localhost:{local_ostree_server_port}".')

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    resolved_remote_host = resolve_remote_host(remote_host, remote_mdns)
    client.connect(hostname=resolved_remote_host,
                   username=remote_username,
                   password=remote_password,
                   port=remote_port)

    # Get the reverse TCP port that was chosen by the remote SSH
    reverse_ostree_server_port = request_port_forward(client.get_transport())

    forwarding_thread = threading.Thread(target=reverse_forward_tunnel,
                                         args=("localhost",
                                               local_ostree_server_port,
                                               client.get_transport()))
    forwarding_thread.daemon = True
    forwarding_thread.start()

    run_command_with_sudo(
        client,
        "ostree remote add --no-gpg-verify --force tcbuilder "
        f"http://localhost:{reverse_ostree_server_port}/",
        remote_password)

    log.info("Starting OSTree pull on the device...")
    run_command_with_sudo(
        client, f"ostree pull tcbuilder:{csumdeploy}", remote_password)

    log.info("Deploying new OSTree on the device...")
    # Do the final staging after we set upgrade_available, therefore option --stage
    run_command_with_sudo(
        client, f"ostree admin deploy --stage {args_cli} tcbuilder:{csumdeploy}", remote_password)

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
# pylint: enable=too-many-locals
