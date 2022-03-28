"""
Backend handling for build subcommand
"""

import logging
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import http.server

from zipfile import ZipFile

import paramiko

from tcbuilder.backend.common import (get_rootfs_tarball, get_unpack_command,
                                      set_output_ownership)
from tcbuilder.backend import ostree
from tcbuilder.errors import (TorizonCoreBuilderError, InvalidArgumentError)

log = logging.getLogger("torizon." + __name__)


def serve(images_directory):
    """
    Serve TorizonCore TEZI images via HTTP so they can be installed directly
    from TorizonCore Builder to any SoC using zeroconf technologies.

    :param images_directory: TorizonCore TEZI images directory.
    """

    image_list_file = os.path.join(images_directory, "image_list.json")
    if not os.path.exists(image_list_file):
        logging.error(f"Error: The Toradex Easy Installer '{image_list_file}' "
                      f"does not exist inside '{images_directory}' directory.")
        sys.exit(1)

    class Handler(http.server.SimpleHTTPRequestHandler):
        """Handler for the HTTP server."""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=images_directory, **kwargs)

        def log_message(self, *args):
            path = args[1]
            code = "OK" if args[2] == "200" else "Error"
            log.debug(f"{path} {code}")

        def do_GET(self):
            """
            Insert a 'Cache-Control' HTTP header in each response for
            every '*.json' file requested previously so Toradex Easy
            Installer will ask again for JSON files which it could
            had already been asked in the pass because of multiple
            executions of the TorizonCore Builder 'serve' command.
            """
            if self.path.endswith('.json'):
                fd_json = open(os.path.join(images_directory, self.path[1:])).read()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(fd_json)))
                self.send_header("Cache-Control", "no-store,max-age=0")
                self.end_headers()
                self.wfile.write(fd_json.encode("utf-8"))
            else:
                super().do_GET()

    try:
        # The Avahi deamon should respond for zeroconf TEZI services
        avahi = subprocess.Popen(["avahi-daemon"],
                                 stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)

        # Serve TEZI images directory via HTTP
        log.info("Currently serving Toradex Easy Installer images from "
                 f"'{images_directory}'. You may now run Toradex Easy Installer "
                 "on your Toradex Device and install these images. Press "
                 "'Ctrl+C' to quit and stop serving these images.\n")
        with http.server.ThreadingHTTPServer(("", 80), Handler) as httpd:
            httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        avahi.terminate()
        avahi.wait()


def get_device_info(r_host, r_username, r_password, r_port):
    """
    Access a "live" TorizonCore device and get some information about it.

    :param r_host: TorizonCore hostname.
    :param r_username: TorizonCore remote username.
    :param r_password: TorizonCore remote password.
    :returns:
        version: TorizonCore version.
        hostname: TorizonCore hostname
        container: Container runtime engine.
    """

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    client.connect(hostname=r_host,
                   username=r_username,
                   password=r_password,
                   port=r_port)

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

    return version, hostname, container


# pylint: disable=too-many-locals
def download_tezi(r_host, r_username, r_password, r_port,
                  tezi_dir, src_sysroot_dir, src_ostree_archive_dir):
    """
    Download appropriate Tezi Image based on target device.
    """

    version, hostname, container = get_device_info(r_host,
                                                   r_username,
                                                   r_password,
                                                   r_port)

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
        rt_flag = "-rt"
    else:
        rt_flag = ""

    sem_ver = re.findall(r'.*([0-9]+\.[0-9]+\.[0-9]+)\.*', version)[0]

    module_name = hostname[:-10]

    url = "https://artifacts.toradex.com/artifactory/{0}/{1}/{2}/{3}/{4}/" \
          "torizon{5}{6}/torizon-core-{7}/oedeploy/" \
          "torizon-core-{7}{6}-{4}-Tezi_{8}{9}{10}+build.{3}.tar".format(
              prod, yocto, build_type, build_number, module_name, kernel_type,
              rt_flag, container, sem_ver, devel, date)

    # Download and unpack tezi image
    log.info(f"Downloading image from: {url}\n")
    log.info("The download may take some time. Please wait...")
    download_file = os.path.basename(url)
    download_file_cwd = os.path.abspath(download_file)
    try:
        urllib.request.urlretrieve(url, download_file_cwd)
        log.info("Download Complete!\n")
    except:
        raise TorizonCoreBuilderError("The requested image could not be found "
                                      "in the Toradex Artifactory.")
    set_output_ownership(download_file_cwd)
    import_local_image(download_file, tezi_dir,
                       src_sysroot_dir, src_ostree_archive_dir)
# pylint: enable=too-many-locals


def unpack_local_image(image_dir, sysroot_dir):
    """Extract the root fs tarball from the image into the sysroot directory"""
    tarfile = get_rootfs_tarball(image_dir)

    # pylint: disable=line-too-long
    # This is a OSTree bare repository. Care must been taken to preserve all
    # file system attributes. Python tar does not support xattrs, so use GNU tar
    # here
    # See: https://dev.gentoo.org/~mgorny/articles/portability-of-tar-features.html#extended-file-metadata
    # pylint: enable=line-too-long
    tarcmd = "cat '{0}' | {1} | tar --xattrs --xattrs-include='*' -xhf - -C {2}".format(
                tarfile, get_unpack_command(tarfile), sysroot_dir)
    log.debug(f"Running tar command: {tarcmd}")
    subprocess.check_output(tarcmd, shell=True, stderr=subprocess.STDOUT)

    # Remove the tarball since we have it unpacked now
    os.unlink(tarfile)


def _make_tezi_extract_dir(tezi_dir):
    """Create target directory where to extract the tezi image"""
    extract_dir = tezi_dir + '.tmp'
    if os.path.exists(extract_dir):
        shutil.rmtree(extract_dir)
    os.mkdir(extract_dir)
    return extract_dir


def import_local_image(image_dir, tezi_dir, src_sysroot_dir, src_ostree_archive_dir):
    """Import local Toradex Easy Installer image

    Import local Toradex Easy installer image to be customized. Assuming an
    empty/non-existing src_sysroot_dir as well as src_ostree_archive_dir.
    """
    os.mkdir(src_sysroot_dir)

    # If provided image_dir is archived, extract it first
    # pylint: disable=C0330
    extract_dir = None
    if (image_dir.endswith(".tar") or image_dir.endswith(".tar.gz") or
        image_dir.endswith(".tgz")):
        log.info("Unpacking Toradex Easy Installer image.")
        if "Tezi" in image_dir:
            extract_dir = _make_tezi_extract_dir(tezi_dir)
            final_dir = os.path.join(
                extract_dir, os.path.splitext(os.path.basename(image_dir))[0])
        elif "teziimage" in image_dir:
            extract_dir = _make_tezi_extract_dir(tezi_dir)
            final_dir = extract_dir
        else:
            raise InvalidArgumentError(
                f"Unknown naming pattern for file {image_dir}")
        tarcmd = "cat {0} | {1} | tar -xf - -C {2}".format(
            image_dir, get_unpack_command(image_dir), extract_dir)
        log.debug(f"Running tar command: {tarcmd}")
        subprocess.check_output(tarcmd, shell=True, stderr=subprocess.STDOUT)
        image_dir = final_dir

    elif image_dir.endswith(".zip"):
        log.info("Unzipping Toradex Easy Installer image.")
        with ZipFile(image_dir, 'r') as file:
            extract_dir = _make_tezi_extract_dir(tezi_dir)
            file.extractall(extract_dir)
            image_dir = extract_dir

    log.info("Copying Toradex Easy Installer image.")
    log.debug(f"Copy directory {image_dir} -> {tezi_dir}.")
    shutil.copytree(image_dir, tezi_dir)

    # Get rid of the extraction directory (if we created one).
    if extract_dir is not None:
        shutil.rmtree(extract_dir)

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

# EOF
