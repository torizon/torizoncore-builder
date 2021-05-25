#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import os
import re
import shutil
import subprocess
import time

from datetime import datetime

import compose.config
import compose.config.environment
import compose.config.serialize
import docker
import docker.types

from tcbuilder.errors import OperationFailureError

log = logging.getLogger("torizon." + __name__)


def get_compression_command(output_file):
    """Get compression command

    Args:
        output_filename: File name or path with compression extension

    Returns:
        (str, str): output_file without compression ending, compression command
    """
    command = None
    if output_file.endswith(".xz"):
        output_file_tar = output_file[:-3]
        command = ["xz", "-3", "-z", output_file_tar]
    elif output_file.endswith(".gz"):
        output_file_tar = output_file[:-3]
        command = ["gzip", output_file_tar]
    elif output_file.endswith(".lzo"):
        output_file_tar = output_file[:-4]
        command = ["lzop", "-U", "-o", output_file, output_file_tar]
    elif output_file.endswith(".lz4"):
        output_file_tar = output_file[:-4]
        command = ["lz4", "-1", "-z", output_file, output_file_tar]
    elif output_file.endswith(".zst"):
        output_file_tar = output_file[:-4]
        command = ["zstd", "--rm", output_file_tar, "-o", output_file]

    return (output_file_tar, command)


# pylint: disable=no-self-use
class DockerManager:
    """Docker bundling helper class

    This class assumes we can use host Docker to create a bundle of the
    containers. Note that this is most often not the case as other images are
    already preinstalled.
    """
    def __init__(self, output_dir):
        if not os.path.isdir(output_dir):
            os.mkdir(output_dir)
        self.output_dir = output_dir
        self.output_dir_host = output_dir

    def start(self, network_name=None, default_platform=None):
        pass

    def stop(self):
        pass

    def get_tar_command(self, output_file):
        return [
            "tar", "--numeric-owner",
            "--preserve-permissions", "--directory=/var/lib/docker",
            "--xattrs-include='*'", "--create", "--file", output_file,
            "overlay2/", "image/"
        ]

    def get_client(self):
        return docker.from_env()

    def save_tar(self, output_file):

        output_file_tar, compression_command = get_compression_command(output_file)

        # Use host tar to store the Docker storage backend
        subprocess.run(
            self.get_tar_command(os.path.join(self.output_dir, output_file_tar)),
            check=True)

        output_filepath = os.path.join(self.output_dir, output_file)
        if os.path.exists(output_filepath):
            os.remove(output_filepath)
        subprocess.run(compression_command, cwd=self.output_dir, check=True)

# pylint: enable=no-self-use


class DindManager(DockerManager):
    """Docker bundling class using a Docker-in-Docker instance

    TODO: Explain
    """

    DIND_CONTAINER_IMAGE = "docker:19.03.8-dind"
    DIND_VOLUME_NAME = "dind-volume"
    DIND_CONTAINER_NAME = "tcb-fetch-dind"
    TAR_CONTAINER_NAME = "tcb-build-tar"

    def __init__(self, output_dir, host_workdir):
        super(DindManager, self).__init__(output_dir)

        # Create certificate directory based on date/time.
        cert_dir_rel = datetime.now().strftime("certs_%Y%m%d%H%M%S_%f.tmp")
        cert_dir = os.path.join(os.getcwd(), cert_dir_rel)
        os.mkdir(cert_dir)

        # Certificates and output directory as accessible from our container.
        self.cert_dir = cert_dir
        self.bundle_dir = output_dir

        if isinstance(host_workdir, str):
            # How to access certs and output directory from other containers.
            # Form: mount, bind-type, relative path
            self.cert_dir_host = (host_workdir, 'bind', cert_dir_rel)
            self.bundle_dir_host = (host_workdir, 'bind', output_dir)

        elif isinstance(host_workdir, tuple):
            # host_workdir = (volume-name, bind-type, True)
            # host_workdir = (host-directory, bind-type, False)
            assert len(host_workdir) == 3 and isinstance(host_workdir[2], bool)
            self.cert_dir_host = (host_workdir[0], host_workdir[1], cert_dir_rel)
            self.bundle_dir_host = (host_workdir[0], host_workdir[1], output_dir)

        else:
            assert False, f"Bad argument type, host_workdir={host_workdir}"

        self.host_client = docker.from_env()
        self.network = None

        self.docker_host = None
        self.dind_volume = None
        self.dind_container = None

    def _wait_certs(self):
        # Wait until TLS certificate is generated
        needed_files = [
            os.path.join(self.cert_dir, 'client', 'ca.pem'),
            os.path.join(self.cert_dir, 'client', 'cert.pem'),
            os.path.join(self.cert_dir, 'client', 'key.pem')
        ]

        success = False
        for _retry in range(30):
            time.sleep(1)
            if all(os.path.exists(file) for file in needed_files):
                success = True
                break

        # The simple presence of the files does not ensure the other process has
        # finished writing them: add some time here as an imperfect safeguard.
        time.sleep(1)

        if not success:
            raise OperationFailureError(
                "The script could not access the TLS certificates which have "
                "been created by the Docker in Docker instance. Make sure "
                f"{self.cert_dir} is a shared location between this script and "
                "the Docker host.")

    def start(self, network_name="fetch-dind-network", default_platform=None):
        dind_cmd = ["--storage-driver", "overlay2"]

        if network_name == "host":
            # Choose a safe and high port to avoid conflict with already
            # running docker instance...
            port = 22376
            dind_cmd.append(f"--host=tcp://0.0.0.0:{port}")

            if "DOCKER_HOST" in os.environ:
                # In case we use a Docker host, also connect to that host to
                # reach the DIND instance (Gitlab CI case)
                docker_host = os.environ["DOCKER_HOST"]
                results = re.findall(r"tcp?:\/\/(.*):(\d*)\/?.*", docker_host)
                if not results or len(results) < 1:
                    raise Exception("Regex does not match: {}".format(docker_host))
                host_ip = results[0][0]
                self.docker_host = f"tcp://{host_ip}:{port}"
            else:
                self.docker_host = f"tcp://127.0.0.1:{port}"
            log.info(f"Using Docker host \"{self.docker_host}\"")
        else:
            log.info(f"Create network \"{network_name}\"")
            self.network = self.host_client.networks.create(network_name, driver="bridge")

        # Create the volume to hold the /var/lib/docker data.
        self.dind_volume = self.host_client.volumes.create(name=self.DIND_VOLUME_NAME)

        # The workdir below is for the DinD instance.
        _environ = {
            'DOCKER_TLS_CERTDIR': os.path.join('/workdir/', self.cert_dir_host[2])
        }
        if default_platform is not None:
            log.debug(f"Default platform: {default_platform}")
            _environ['DOCKER_DEFAULT_PLATFORM'] = default_platform

        _mounts = [
            docker.types.Mount(
                source=self.cert_dir_host[0],
                type=self.cert_dir_host[1],
                target='/workdir/',
                read_only=False
            ),
            docker.types.Mount(
                source=self.DIND_VOLUME_NAME,
                type='volume',
                target='/var/lib/docker/',
                read_only=False
            )
        ]
        log.debug(f"Volume mapping for DinD: {_mounts}")

        self.dind_container = self.host_client.containers.run(
            self.DIND_CONTAINER_IMAGE,
            privileged=True,
            environment=_environ,
            mounts=_mounts,
            network=network_name,
            name=self.DIND_CONTAINER_NAME,
            auto_remove=True,
            detach=True,
            command=dind_cmd)

        if network_name != "host":
            # Find IP of the DIND container (make sure attributes are current...)
            self.dind_container.reload()
            dind_ip = self.dind_container.attrs \
                ["NetworkSettings"]["Networks"][network_name]["IPAddress"]
            self.docker_host = "tcp://{}:2376".format(dind_ip)

    def stop(self):
        if self.dind_container is not None:
            self.dind_container.stop()
        # Remove certs directory generated by DinD.
        if os.path.exists(self.cert_dir):
            shutil.rmtree(self.cert_dir)
        # Otherwise Docker API throws exceptions...
        time.sleep(1)
        if self.dind_volume is not None:
            self.dind_volume.remove()
        if self.network is not None:
            self.network.remove()

    def get_client(self):
        # Wait until certificates are generated.
        self._wait_certs()

        # Use TLS to authenticate
        tls_config = docker.tls.TLSConfig(
            ca_cert=os.path.join(self.cert_dir, 'client', 'ca.pem'),
            verify=os.path.join(self.cert_dir, 'client', 'ca.pem'),
            client_cert=(os.path.join(self.cert_dir, 'client', 'cert.pem'),
                         os.path.join(self.cert_dir, 'client', 'key.pem')),
            assert_hostname=False)

        log.info(f"Connecting to Docker Daemon at \"{self.docker_host}\"")
        dind_client = docker.DockerClient(base_url=self.docker_host, tls=tls_config)
        return dind_client

    def save_tar(self, output_file):
        log.info(f"Storing container bundle into \"{self.bundle_dir}\"")

        # Get tar filename and compression command to convert to compressed tar
        # locally in a second command (we do not have the compression utils in
        # the tar container).
        (output_file_tar, compression_command) = get_compression_command(output_file)

        # Use a container to tar the Docker storage backend instead of the
        # built-in save_tar() is more flexible...
        _mount_dir = "/mnt"
        _mounts = [
            docker.types.Mount(
                source=self.bundle_dir_host[0],
                type=self.bundle_dir_host[1],
                target=_mount_dir,
                read_only=False
            ),
            docker.types.Mount(
                source=self.DIND_VOLUME_NAME,
                type='volume',
                target='/var/lib/docker/',
                read_only=True
            )
        ]
        log.debug(f"Volume mapping for tar container: {_mounts}")
        _tar_command = self.get_tar_command(
            os.path.join(_mount_dir, self.bundle_dir, output_file_tar))
        log.debug(f"tar command: {_tar_command}")

        # Due to issues with WSL, we are running the container detached and
        # explicitly waiting it to stop.
        _tar_container = self.host_client.containers.run(
            "debian:bullseye-slim",
            name=self.TAR_CONTAINER_NAME,
            mounts=_mounts,
            command=_tar_command,
            detach=True)

        try:
            _tar_container.wait(timeout=300)
        except Exception as exc:
            _err = OperationFailureError("Tarball generation command timed out.")
            raise _err from exc
        finally:
            _tar_container.stop()
            _tar_container.remove()

        output_filepath_tar = os.path.join(self.bundle_dir, output_file_tar)
        if not os.path.exists(output_filepath_tar):
            raise OperationFailureError(
                f"Could not create output tarball in '{output_file_tar}'.")

        log.debug(f"compression_command: {compression_command}")

        output_filepath = os.path.join(self.bundle_dir, output_file)
        if os.path.exists(output_filepath):
            os.remove(output_filepath)
        subprocess.run(compression_command, cwd=self.bundle_dir, check=True)


def download_containers_by_compose_file(
        output_dir, compose_file, host_workdir,
        docker_username, docker_password, registry,
        platform, output_filename, use_host_docker=False):
    """
    Creates a container bundle using Docker (either Host Docker or Docker in Docker)

    :param output_dir: Relative output directory to host_workdir
    :param compose_file: Docker Compose YAML file or path
    :param host_workdir: Working directory location on the Docker Host (the
                            system where dockerd we are accessing is running)
    :param docker_username: Username to be used to access docker images
    :param docker_password: Password to be used to access docker images
    :param registry: Alternative container registry used to images
    :param use_host_docker: Use host docker (instead of Docker in Docker)
                            Note: This only really works if the Host Docker
                            Engine is not used by anything else than this
                            script. Otherwise all images stored in the
                            Host Docker storage is going to end up in the
                            Bundle.
    :param platform: Container Platform to fetch (if an image is multi-arch
                        capable)
    :param output_filename: Output filename of the processed Docker Compose
                            YAML.
    """
    # Open Docker Compose file
    if not os.path.isabs(compose_file):
        base_dir = os.path.dirname(os.path.abspath(compose_file))
    else:
        base_dir = os.path.dirname(compose_file)

    environ = compose.config.environment.Environment.from_env_file(base_dir)
    details = compose.config.find(
        base_dir, [os.path.basename(compose_file)], environ, None)
    config = compose.config.load(details)

    log.info("Starting DIND container")
    if use_host_docker:
        log.debug("Using DockerManager")
        manager = DockerManager(output_dir)
    else:
        log.debug("Using DindManager")
        manager = DindManager(output_dir, host_workdir)

    try:
        manager.start("host", default_platform=platform)

        dind_client = manager.get_client()
        if dind_client is None:
            return

        # Now we can fetch the containers...
        if docker_username is not None:
            if registry is not None:
                dind_client.login(docker_username, docker_password, registry=registry)
            else:
                dind_client.login(docker_username, docker_password)

        for service in config.services:
            image = service['image']
            log.info(f"Fetching container image {image}")
            if not ":" in image:
                image += ":latest"
            image = dind_client.images.pull(image, platform=platform)
            service['image'] = image.attrs['RepoDigests'][0]

        log.info("Saving Docker Compose file")
        with open(os.path.join(manager.output_dir, "docker-compose.yml"), "w") as file:
            # Serialization need to escape dollar sign and requires no
            # environment variables interpolation.
            file.write(compose.config.serialize.serialize_config(
                config, escape_dollar=False).replace("@@MACHINE@@", "$MACHINE", 1))

        log.info("Exporting storage")
        manager.save_tar(output_filename)

    finally:
        log.info("Stopping DIND container")
        manager.stop()
