import os
import shutil
import logging
import subprocess
import re
import urllib.request
from zipfile import ZipFile
import paramiko

from tcbuilder.backend.common import get_rootfs_tarball, get_unpack_command
from tcbuilder.backend import ostree
from tcbuilder.errors import TorizonCoreBuilderError

log = logging.getLogger("torizon." + __name__)

def download_tezi(r_host, r_username, r_password,
                  tezi_dir, src_sysroot_dir, src_ostree_archive_dir):
    """
    Download appropriate Tezi Image based on target device.
    """

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    client.connect(hostname=r_host,
                   username=r_username,
                   password=r_password)

    # Gather module and version information remotely from device
    sftp = client.open_sftp()
    if sftp is not None:
        release_file = sftp.file("/etc/os-release")
        for line in release_file:
            if "PRETTY_NAME" in line:
                version = line
        host_file = sftp.file("/etc/hostname")
        hostname = host_file.readline()
        try:
            sftp.stat("/usr/bin/podman")
            container = "podman"
        except IOError:
            container = "docker"
        sftp.close()
    else:
        client.close()
        raise TorizonCoreBuilderError("Unable to create SSH connection")

    client.close()

    # Create correct artifactory link based on device information
    if "devel" in version:
        prod = "torizoncore-oe-prerelease-frankfurt"
        devel = "-devel-"
    else:
        prod = "torizoncore-oe-prod-frankfurt"
        devel = ""

    if "dunfell" in version:
        yocto = "dunfell-5.x.y"

    date = re.findall(r'.*-(.*?)\+', version)
    if not date:
        build_type = "release"
        date = ""
    elif len(date[0]) == 6:
        build_type = "monthly"
        date = date[0]
    elif len(date[0]) == 8:
        build_type = "nightly"
        date = date[0]

    build_number = re.findall(r'.*build.(.*?)\ ', version)[0]

    if "Upstream" in version:
        kernel_type = "-upstream"
    else:
        kernel_type = ""

    if "PREEMPT" in version:
        rt = "-rt"
    else:
        rt = ""

    sem_ver = re.findall(r'.*([0-9]+\.[0-9]+\.[0-9]+)\.*', version)[0]

    module_name = hostname[:-10]

    url = "https://artifacts.toradex.com/artifactory/{0}/{1}/{2}/{3}/{4}/" \
          "torizon{5}{6}/torizon-core-{7}/oedeploy/" \
          "torizon-core-{7}{6}-{4}-Tezi_{8}{9}{10}+build.{3}.tar".format(
              prod, yocto, build_type, build_number, module_name, kernel_type, rt,
              container, sem_ver, devel, date)

    # Download and unpack tezi image
    log.info(f"Downloading image from: {url}\n")
    log.info("The download may take some time. Please wait...")
    download_file = os.path.basename(url)
    try:
        urllib.request.urlretrieve(url, os.getcwd() + "/" + download_file)
        log.info("Download Complete!\n")
    except:
        raise TorizonCoreBuilderError("The requested image could not be found "
                                      "in the Toradex Artifactory.")
    import_local_image(download_file, tezi_dir,
                       src_sysroot_dir, src_ostree_archive_dir)

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

    # If provided image_dir is archived, extract it first
    if image_dir.endswith(".tar") or image_dir.endswith(".tar.gz") or image_dir.endswith(".tgz"):
        log.info("Unpacking Toradex Easy Installer image.")
        if "Tezi" in image_dir:
            extract_dir = os.getcwd()
            final_dir = os.path.splitext(image_dir)[0]
        elif "teziimage" in image_dir:
            extract_dir = "teziimage"
            if not os.path.exists(extract_dir):
                os.mkdir(extract_dir)
            final_dir = extract_dir
        tarcmd = "cat {0} | {1} | tar -xf - -C {2}".format(
            image_dir, get_unpack_command(image_dir), extract_dir)
        log.debug(f"Running tar command: {tarcmd}")
        subprocess.check_output(tarcmd, shell=True, stderr=subprocess.STDOUT)
        image_dir = final_dir
    elif image_dir.endswith(".zip"):
        log.info("Unzipping Toradex Easy Installer image.")
        with ZipFile(image_dir, 'r') as file:
            extract_dir = "teziimage"
            if not os.path.exists(extract_dir):
                os.mkdir(extract_dir)
            file.extractall(extract_dir)
            image_dir = extract_dir

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