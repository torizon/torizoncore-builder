"""
Backend handling for the deploy subcommand.
"""

import json
import logging
import os
import shutil
import struct
import subprocess
import tempfile
import threading
import shlex

import fabric

# pylint: disable=wrong-import-position
import gi
gi.require_version("OSTree", "1.0")
from gi.repository import Gio, OSTree

from tcbuilder.backend import ostree
from tcbuilder.backend.common import (get_rootfs_tarball, resolve_remote_host,
                                      run_with_loading_animation, open_disk_image,
                                      REMOTE_CMD_TIMEOUT, SECBOOT_ARTIFACTS_DIR,
                                      DEFAULT_RAW_SECTOR_SIZE, FUSE_CMD_TXT_NAME,
                                      get_image_bootloader)
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
    log.debug("Creating OSTree sysroot at '%s'", deploy_sysroot_dir)
    sysroot = OSTree.Sysroot.new(Gio.File.new_for_path(deploy_sysroot_dir))

    if not sysroot.ensure_initialized():
        raise TorizonCoreBuilderError("Error initializing OSTree sysroot.")

    if not sysroot.init_osname(OSNAME):
        raise TorizonCoreBuilderError("Error initializing OSTree osname.")

    if not sysroot.load():
        raise TorizonCoreBuilderError("Error loading OSTree sysroot.")

    return sysroot


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
        with open(os.path.join(bootdir, "loader/uEnv.txt"),
                  "w", encoding="utf-8") as _file:
            pass
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
    with open(os.path.join(path, "installed_versions"),
              "w", encoding="utf-8") as versionfile:
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
    else:
        assert False, \
            f"pack_rootfs_for_tezi: unhandled filename extension ({image_filename})."

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
        try:
            # shutil.copytree does not preserve ownership
            subprocess.check_output(
                ["cp", "-a", "-t", copy_file["dst"], copy_file["src"]])
        except subprocess.CalledProcessError as exc:
            raise TorizonCoreBuilderError(
                "Cannot deploy home directories.") from exc


# pylint: disable-next=too-many-locals
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

    # Copy the original OSTree repo configuration (essential for composefs).
    src_ostree_dir = os.path.join(src_sysroot_dir, "ostree/repo")
    src_repo = ostree.open_ostree(src_ostree_dir)
    ostree.copy_repo_config(src_repo, repo, keep_core=True)
    ostree.dump_repo_config(repo)

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

    return csumdeploy


# pylint: disable-next=too-many-positional-arguments
def deploy_tezi_image(tezi_dir, src_sysroot_dir, src_ostree_archive_dir,
                      output_dir, dst_sysroot_dir, *, ref=None):
    """Deploys a Toradex Easy Installer image with given OSTree reference

    Creates a new Toradex Easy Installer image with a OSTree deployment of the
    given OSTree reference.
    """

    commit = deploy_ostree_local(src_sysroot_dir, src_ostree_archive_dir, dst_sysroot_dir, ref)

    log.info("Packing rootfs...")
    copy_tezi_image(tezi_dir, output_dir)
    pack_rootfs_for_tezi(dst_sysroot_dir, output_dir)
    log.info("Packing rootfs done.")

    # Check if there is a signed bootloader to be copied for this ref
    commit_dir = os.path.join(SECBOOT_ARTIFACTS_DIR, commit)
    if os.path.isdir(commit_dir):
        log.info(f"Copying signed artifacts linked with {commit} to output image.")
        copy_signed_artifacts(commit_dir, output_dir)


# pylint: disable-next=too-many-locals
def grow_last_partition(raw_img, added_size_kb, sector_size, rootfs_partition, *,
                        delete_on_error=False):
    """Enlarge a raw image and extend its last partition to fill the new space.

    For 4Kn images, where virt-resize cannot operate. delete_on_error=True
    mutates raw_img directly and deletes it on failure; otherwise raw_img is
    the caller's only copy, so every mutation runs against a temporary
    sibling copy instead, swapped into place only on full success.
    """
    work_img = raw_img
    tmp_img = None

    try:
        if not delete_on_error:
            tmp_fd, tmp_img = tempfile.mkstemp(
                prefix=f"{os.path.basename(raw_img)}.",
                suffix=".grow.tmp",
                dir=os.path.dirname(os.path.abspath(raw_img)))
            os.close(tmp_fd)
            shutil.copy2(raw_img, tmp_img)
            work_img = tmp_img

        orig_size = os.path.getsize(work_img)
        # Round up to a whole sector; a non-sector-multiple size can be rejected at 4Kn.
        new_size = orig_size + int(added_size_kb) * 1024
        new_size = (new_size + sector_size - 1) // sector_size * sector_size
        subprocess.check_output(["truncate", "-s", str(new_size), work_img])

        with open_disk_image(work_img, delete_on_error=True,
                             sector_size=sector_size) as gfs:
            dev = "/dev/sda"
            last_partition = max(
                gfs.part_list(dev), key=lambda partition: partition["part_start"])
            partnum = last_partition["part_num"]
            if gfs.part_to_partnum(rootfs_partition) != partnum:
                raise TorizonCoreBuilderError(
                    "the rootfs must be the last partition to grow a 4Kn raw image.")
            start_sector = last_partition["part_start"] // sector_size

            gfs.part_expand_gpt(dev)  # relocate the GPT backup header to the new end

            # LastUsableLBA (offset 48, 8-byte LE) already reflects the real
            # backup reservation post-expand; read it instead of re-deriving it.
            header = gfs.pread_device(dev, 56, sector_size)
            if len(header) != 56 or header[:8] != b"EFI PART":
                raise TorizonCoreBuilderError(
                    f"could not read the GPT header at LBA 1 for a "
                    f"{sector_size}-byte sector size after expanding the "
                    "partition table.")
            end_sector = struct.unpack("<Q", header[48:56])[0]
            if end_sector <= start_sector:
                raise TorizonCoreBuilderError(
                    "not enough room to grow the last partition of a 4Kn raw image.")

            name = gfs.part_get_name(dev, partnum)
            gpt_type = gfs.part_get_gpt_type(dev, partnum)
            gpt_guid = gfs.part_get_gpt_guid(dev, partnum)
            gpt_attributes = gfs.part_get_gpt_attributes(dev, partnum)

            gfs.part_del(dev, partnum)
            gfs.part_add(dev, "primary", start_sector, end_sector)

            # part_add() may reuse a different free slot than the one just deleted
            # if a lower gap exists; re-derive the number from the start sector.
            try:
                new_partnum = next(p["part_num"] for p in gfs.part_list(dev)
                                   if p["part_start"] // sector_size == start_sector)
            except StopIteration:
                raise TorizonCoreBuilderError(
                    "could not locate the regrown partition after part_add().") from None
            new_rootfs_partition = f"{dev}{new_partnum}"
            gfs.part_set_name(dev, new_partnum, name)
            gfs.part_set_gpt_type(dev, new_partnum, gpt_type)
            gfs.part_set_gpt_guid(dev, new_partnum, gpt_guid)
            gfs.part_set_gpt_attributes(dev, new_partnum, gpt_attributes)

            # Growing only the partition would leave the fs at its old size; the
            # original rootfs_partition may no longer exist if renumbered above.
            gfs.resize2fs(new_rootfs_partition)

        if tmp_img:
            os.replace(tmp_img, raw_img)
    except BaseException:  # always re-raises; must also clean up on KeyboardInterrupt/SystemExit
        # Clean up the disposable file only: tmp_img if it exists (even a
        # failed copy or swap can leave one), else raw_img when
        # delete_on_error.
        cleanup_target = tmp_img if tmp_img else (raw_img if delete_on_error else None)
        try:
            # open_disk_image may have removed it already.
            if cleanup_target and os.path.isfile(cleanup_target):
                os.remove(cleanup_target)
        except OSError as cleanup_exc:
            log.error("Failed to clean up '%s' after a grow failure: %s",
                     cleanup_target, cleanup_exc)
        raise


# pylint: disable-next=too-many-positional-arguments
def create_output_raw_image(base_raw_img, output_raw_img, base_rootfs_partition,
                            other_partitions_size_kb, rootfs_size_kb,
                            sector_size=DEFAULT_RAW_SECTOR_SIZE):
    """Create a new raw disk image based on an existing one.

    The result is a copy of the base disk image with all partitions except
    the rootfs one, replaced by an empty partition at the end of the disk.
    """

    base_img_size_kb = os.path.getsize(base_raw_img)/1024
    out_size_kb = max(base_img_size_kb,
                      IMAGE_OVERHEAD_FACTOR*(rootfs_size_kb + other_partitions_size_kb))
    out_size_kb += EXTRA_ROOTFS_SIZE_KB

    if sector_size != DEFAULT_RAW_SECTOR_SIZE:
        # virt-resize drives libguestfs at the default 512-byte sector size and
        # cannot open a 4Kn disk, so grow the image with libguestfs directly and
        # let write_rootfs_to_raw_image() reformat the enlarged last partition.
        shutil.copy2(base_raw_img, output_raw_img)
        if out_size_kb > base_img_size_kb:
            added_size_kb = out_size_kb - base_img_size_kb
            log.info(f"Adding {added_size_kb/1024:.2f} MiB to output image.")
            log.info(f"Size of output image will be: {out_size_kb/1024/1024:.2f} GiB")
            grow_last_partition(output_raw_img, added_size_kb, sector_size,
                                base_rootfs_partition, delete_on_error=True)
        else:
            log.info("Output image will have the same size as the base one.")
        return

    # Copy of the base disk will be the starting point of the output disk
    shutil.copy2(base_raw_img, output_raw_img)
    log.debug(f"Created output image: {output_raw_img}")

    if out_size_kb > base_img_size_kb:
        added_size_kb = out_size_kb - base_img_size_kb
        log.debug(f"Image overhead factor: {IMAGE_OVERHEAD_FACTOR}")
        log.debug(f"Extra rootfs size added: {EXTRA_ROOTFS_SIZE_KB/1024} MiB")
        log.info(f"Adding {added_size_kb/1024:.2f} MiB to output image.")
        log.info(f"Size of output image will be: {out_size_kb/1024/1024:.2f} GiB")
        subprocess.check_output(["truncate", "-s", f"+{int(added_size_kb)}K", output_raw_img])
    else:
        log.info("Output image will have the same size as the base one.")

    # Using virt-resize, copy all base image partitions to output image,
    # except base_rootfs_partition:
    log.info("Starting virt-resize...")
    print("------------------------------------------------------------")
    resizecmd = ["virt-resize", "--format", "raw", "--expand"]
    resizecmd.extend([base_rootfs_partition, base_raw_img, output_raw_img])
    subprocess.run(resizecmd, check=True)
    print("------------------------------------------------------------")


def write_rootfs_to_raw_image(raw_disk_img, rootfs_label, rootfs_partition, rootfs_dir,
                              sector_size=DEFAULT_RAW_SECTOR_SIZE):
    """Writes unpacked rootfs contents to a raw disk image

    Creates a new rootfs ext4 partition with a given label on the last partition
    of a raw disk and writes the contents of the provided rootfs directory.
    """

    loading_msg="Initializing output image..."
    with open_disk_image(raw_disk_img, loading_msg=loading_msg, sector_size=sector_size) as gfs:
        # virt-resize expanded the root partition without moving any of the others, so
        # the partition numbering of the input disk should be valid for the output one.
        log.info("Formatting '%s' at %s.", rootfs_label, rootfs_partition)

        gfs.mkfs("ext4", rootfs_partition)
        gfs.set_label(rootfs_partition, rootfs_label)
        gfs.mount(rootfs_partition, "/")

        rootfs_dir_ls = os.listdir(rootfs_dir)
        if 'lost+found' in rootfs_dir_ls:
            rootfs_dir_ls.remove('lost+found')

        log.info("Copying unpacked rootfs contents to output image. This may take a few minutes...")
        for content in rootfs_dir_ls:
            run_with_loading_animation(
                func=gfs.copy_in,
                args=(f"{rootfs_dir}/{content}", "/"),
                loading_msg=f"  Copying /{content}...")


# pylint: disable-next=too-many-positional-arguments
def deploy_raw_image(base_raw_img, src_sysroot_dir, src_ostree_archive_dir,
                     output_raw_img, dst_sysroot_dir, rootfs_label, *, ref=None,
                     sector_size=DEFAULT_RAW_SECTOR_SIZE):
    """Deploys a WIC image with given OSTree reference

    Creates a new WIC image with an OSTree deployment of the
    given OSTree reference.
    """
    deploy_ostree_local(src_sysroot_dir, src_ostree_archive_dir, dst_sysroot_dir, ref)

    loading_msg="Initializing base WIC/raw image..."
    with open_disk_image(base_raw_img, readonly=True, loading_msg=loading_msg,
                         sector_size=sector_size) as gfs:
        # Get partition number from ext4 fs called rootfs_label in disk image (.wic/.img)
        rootfs_partition = gfs.findfs_label(rootfs_label)
        log.info(f"  '{rootfs_label}' partition found: {rootfs_partition}")

        other_partitions_size_kb = 0
        partitions = gfs.list_partitions()
        partitions.remove(rootfs_partition)
        for part in partitions:
            other_partitions_size_kb += gfs.blockdev_getsize64(part) / 1024

    if other_partitions_size_kb > 0:
        log.info("  Combined size of all partitions except rootfs: "
                 f"{other_partitions_size_kb/1024/1024:.2f} GiB")

    rootfs_size_kb = subprocess.check_output(["du", "-s", dst_sysroot_dir], text=True)
    rootfs_size_kb = int(rootfs_size_kb.split('\t', maxsplit=1)[0])
    log.info(f"Unpacked rootfs size: {rootfs_size_kb/1024/1024:.2f} GiB")

    create_output_raw_image(base_raw_img, output_raw_img, rootfs_partition,
                            other_partitions_size_kb, rootfs_size_kb, sector_size)

    write_rootfs_to_raw_image(output_raw_img, rootfs_label, rootfs_partition, dst_sysroot_dir,
                              sector_size)

    log.info(f"Image {os.path.basename(output_raw_img)} created successfully!")


def run_command_with_sudo(ssh_connection, command) -> dict:

    result = ssh_connection.sudo(command, pty=True, hide=True, timeout=REMOTE_CMD_TIMEOUT)

    # Check exit status
    if result.failed:
        log.error(result.stdout.strip())
        ssh_connection.close()
        raise TorizonCoreBuilderError(f"Failed to run command on module: {command}")

    stdout_str = result.stdout.strip()

    if len(stdout_str) > 0:
        log.debug(stdout_str)

    return {"status": result.exited, "stdout": stdout_str}


def is_ostree_compatible(srcmeta, ssh_conn):
    # Check if OSTree is present on the device
    hash_result = ssh_conn.run(
        r"ostree admin status | sed -ne 's/^ *\* .* \([0-9a-f]\+\)\.[0-9]\+/\1/p'"
    )
    hash_stdout = hash_result.stdout.strip()

    if hash_result.failed or not hash_stdout:
        log.warning("OSTree not present on host device.")
        return False

    machine_result = ssh_conn.run(
        f"ostree show {hash_stdout} --print-metadata-key oe.machine",
    )
    machine_stdout = machine_result.stdout.strip()

    if machine_result.failed or not machine_stdout:
        log.warning("Machine is not set in device OSTree metadata.")
        return False

    # The output machine is wrapped in quotes, and python duplicates them
    # We must remove the duplicated quotes before comparing
    host_machine = machine_stdout.strip("\"'")

    image_machine = srcmeta["oe.machine"]
    compatibility = image_machine == host_machine
    if not compatibility:
        log.warning(
            f"Image for device '{image_machine}' is NOT compatible with machine '{host_machine}'"
        )

    return compatibility


# pylint: disable-next=too-many-locals,too-many-positional-arguments
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

    resolved_remote_host = resolve_remote_host(remote_host, remote_mdns)
    connection_args = {
        "host": resolved_remote_host,
        "user": remote_username,
        "port": remote_port,
        "connect_kwargs": {'password': remote_password},
        "config": fabric.Config(overrides={'sudo': {'password': remote_password}})
    }
    with fabric.Connection(**connection_args) as conn:

        conn.open()
        # Get the reverse TCP port that was chosen by the remote SSH
        reverse_ostree_server_port = request_port_forward(conn.transport)

        forwarding_thread = threading.Thread(target=reverse_forward_tunnel,
                                             args=("localhost",
                                                   local_ostree_server_port,
                                                   conn.transport))
        forwarding_thread.daemon = True
        forwarding_thread.start()

        is_compatible = is_ostree_compatible(srcmeta, conn)

        if not is_compatible:
            raise TorizonCoreBuilderError("Device is NOT compatible. Operation aborted.")

        log.debug("Device compatible with image.")

        run_command_with_sudo(
            conn,
            "ostree remote add --no-gpg-verify --force tcbuilder "
            f"http://localhost:{reverse_ostree_server_port}/")

        log.info("Starting OSTree pull on the device...")
        run_command_with_sudo(
            conn, f"ostree pull tcbuilder:{csumdeploy}")

        log.info("Deploying new OSTree on the device...")
        # Do the final staging after we set upgrade_available, therefore option --stage
        run_command_with_sudo(
            conn, f"ostree admin deploy --stage {args_cli} tcbuilder:{csumdeploy}")

        # Make sure we set bootcount to 0, it can be > 1 from previous runs
        run_command_with_sudo(
            conn, "fw_setenv bootcount 0")

        # Make sure we remove the rollback flag from previous runs
        run_command_with_sudo(
            conn, "fw_setenv rollback 0")

        # Set upgrade_available for U-Boot
        run_command_with_sudo(
            conn, "fw_setenv upgrade_available 1")

        # Finalize the update after we set upgrade_available for U-Boot
        run_command_with_sudo(
            conn, "ostree admin finalize-staged")

        log.info("Deploying successfully finished.")

        if reboot:
            # If reboot is started in foreground it leads to exit code <> 0 sometimes
            # which leads to a stack trace in torizoncore-builder. Start in background
            # to make the command run successfully always.
            run_command_with_sudo(conn, "sh -c 'reboot &'")
            log.info("Device reboot initiated...")
        else:
            log.info("Please reboot the device to boot into the new deployment.")

    ostree.serve_ostree_stop(http_server_thread)


def copy_signed_artifacts(src_commit_dir, tezi_dir):
    """
    Copy artifacts signed by TCB to the Torizon OS image in tezi_dir, overwriting
    existing content. These include the bootloader container, the text file with
    fusing instructions, and the tarball with the signing files.

    :param src_commit_dir: Commit directory where the artifacts are located
    :param tezi_dir: Path of Torizon OS image in Toradex Easy Installer format (directory)
    """

    # Add the signed artifacts to the tezi image, overwriting existing files
    shutil.copytree(src_commit_dir, tezi_dir, dirs_exist_ok=True)

    fuse_cmd_txt = os.path.join(tezi_dir, FUSE_CMD_TXT_NAME)
    if os.path.isfile(fuse_cmd_txt):
        with open(fuse_cmd_txt, "r", encoding="utf-8") as fuse_file:
            print()
            print("# Fusing instructions to be executed in U-Boot:")
            print()
            print(fuse_file.read())
            print(f"# You can recheck the instructions given above in {FUSE_CMD_TXT_NAME} "
                  f"created in directory '{os.path.basename(tezi_dir)}'.")
            print()
