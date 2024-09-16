#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bundle CLI backend"""

import logging
import os
import re
import shutil
import subprocess
import sys
import time

from datetime import datetime

import docker
import docker.errors
import docker.types
import yaml

from tcbuilder.errors import (InvalidArgumentError, OperationFailureError,
                              InvalidStorageDriverError)
from tcbuilder.backend.common import get_own_network, validate_compose_file
from tcbuilder.backend.registryops import RegistryOperations

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

    def start(self, network_name=None, default_platform=None, dind_params=None):
        """Start manager (dummy implementation)"""

    def stop(self):
        """Stop manager (dummy implementation)"""

    def get_tar_command(self, output_file):
        """Create the tar command to archive the Docker images"""
        return [
            "tar", "--numeric-owner",
            "--preserve-permissions", "--directory=/var/lib/docker",
            "--xattrs-include='*'", "--create", "--file", output_file,
            "overlay2/", "image/"
        ]

    def get_client(self):
        """Create an instance of the Docker client"""
        return docker.from_env()

    def save_tar(self, output_file):
        """Create compressed tar archive of the Docker images"""

        output_file_tar, compression_command = get_compression_command(output_file)

        # Use host tar to store the Docker storage backend
        subprocess.run(
            self.get_tar_command(os.path.join(self.output_dir, output_file_tar)),
            check=True)

        output_filepath = os.path.join(self.output_dir, output_file)
        if os.path.exists(output_filepath):
            os.remove(output_filepath)
        subprocess.run(compression_command, cwd=self.output_dir, check=True)

    def add_cacerts(self, cacerts):
        assert cacerts is None, "`cacerts` should be used with DindManager"

# pylint: enable=no-self-use


# pylint: disable=too-many-instance-attributes
class DindManager(DockerManager):
    """Docker bundling class using a Docker-in-Docker instance

    We use Docker-in-Docker so that the state directory (/var/lib/docker) will
    only contain information related to the images of interest and no others.
    This is needed because our goal is to compress the state directory in its
    raw state without requiring Docker so that later we can simply uncompress
    the state directory on a target device as it is done by the Toradex Easy
    Installer tool.
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

        storage_driver = self.host_client.info()["Driver"]
        if storage_driver != "overlay2":
            raise InvalidStorageDriverError(
                f"Error: Incompatible Docker Storage Driver '{storage_driver}'; "
                "only 'overlay2' is currently supported.\nLearn more on "
                "https://developer.toradex.com/software/torizon/"
                "torizoncore-builder-issue-tracker?issue=TCB-328")

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

    def start(self, network_name="fetch-dind-network",
              default_platform=None, dind_params=None):
        """Start manager

        This will start the Docker-in-Docker container which can then be used
        to perform other operations such as pulling images from a registry.
        """

        log.info("\nStarting DIND container")
        dind_cmd = ["--storage-driver", "overlay2"]
        ports = None

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
            port = 22376
            ports = {f"{port}/tcp": port}
            dind_cmd.append(f"--host=tcp://0.0.0.0:{port}")

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

        # Augment DinD program arguments.
        if dind_params is not None:
            dind_cmd.extend(dind_params)

        log.debug(f"Running DinD container: ports={ports}, network={network_name}")
        self.dind_container = self.host_client.containers.run(
            self.DIND_CONTAINER_IMAGE,
            privileged=True,
            environment=_environ,
            mounts=_mounts,
            ports=ports,
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
            self.docker_host = "tcp://{}:22376".format(dind_ip)

    def stop(self):
        """Stop manager

        This will stop the Docker-in-Docker container and do other necessary
        cleanup.
        """

        log.info("Stopping DIND container")
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
        """Create a client object associated to the DinD instance"""

        # Wait until certificates are generated.
        self._wait_certs()

        # Use TLS to authenticate
        tls_config = docker.tls.TLSConfig(
            ca_cert=os.path.join(self.cert_dir, 'client', 'ca.pem'),
            verify=os.path.join(self.cert_dir, 'client', 'ca.pem'),
            client_cert=(os.path.join(self.cert_dir, 'client', 'cert.pem'),
                         os.path.join(self.cert_dir, 'client', 'key.pem')))

        log.info(f"Connecting to Docker Daemon at \"{self.docker_host}\"")
        dind_client = docker.DockerClient(base_url=self.docker_host, tls=tls_config)
        return dind_client

    def save_tar(self, output_file):
        """Create compressed tar archive of the Docker images"""

        log.info(f"Storing container bundle into \"{self.bundle_dir}\"")

        # Get tar filename and compression command to convert to compressed tar
        # locally in a second command (we do not have the compression utils in
        # the tar container).
        (output_file_tar, compression_command) = get_compression_command(output_file)

        # Notice that here we mount the DIND volume containing the Docker images
        # as a read-only input so that the compression command will have access
        # to them in order to operate. The bundle directory, in turn, is where
        # the output will be generated.
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

    def add_cacerts(self, cacerts):
        """Add the required certificate files for a secure registry
        to the container

        :param cacerts: List of CAcerts to perform: each element on the list must
                        be a 2-tuple with: (REGISTRY, CERTIFICATE). CERTIFICATE must
                        be an absolute path.
        """
        if not cacerts:
            return

        for cacert in cacerts:
            registry, cert = cacert

            if not os.path.exists(cert):
                raise InvalidArgumentError(
                    f"Error: CAcert File '{cert}' not found.")

            file_name = os.path.basename(cert)
            file, _ = os.path.splitext(file_name)
            log.info(f"Adding CAcert file '{file_name}' to "
                     f"'{registry}' registry")
            self.dind_container.exec_run(
                f'mkdir -p /etc/docker/certs.d/{registry}/')

            self.dind_container.exec_run(
                f'cp {cert} '
                f'/etc/docker/certs.d/{registry}/{file}.crt')

# pylint: enable=too-many-instance-attributes


def show_pull_progress_xterm(pull_stream):
    """Show the container pulling progress similarly to `docker pull`

    This function uses terminal XTerm control sequences to position the cursor.

    :param pull_stream: A generator produced by client.api.pull()
    """

    rows_order = []
    rows_by_id = {}

    # Note that here we more the cursor by using XTerm control sequences:
    # https://www.xfree86.org/current/ctlseqs.html
    # ESC [K: clear to the end of the line
    # ESC [<N>A: move cursor up N lines

    def show_row(row):
        """Helper to show a single row of information."""
        if 'id' in row and len(row['id']) >= 8:
            print(f"  {row['id']}: {row['status']} {row.get('progress', '')}\033[K")
        elif 'status' in row:
            print(f"  {row['status']}\033[K")
        elif 'error' in row:
            print(f"  Error: {row['error']}\033[K")

    def show_rows(redisp=True):
        """Helper to show all rows currently stored in `rows_by_id`"""
        if redisp:
            # Use terminal command to move cursor up.
            print(f"\033[{len(rows_order)}A", end='', flush=True)
        for _id in rows_order:
            show_row(rows_by_id[_id])

    for res in pull_stream:
        # Give an ID to each row.
        _id = res.get('id', id(res))
        # Save row data.
        rows_by_id[_id] = res
        # Maybe add a new row.
        if _id not in rows_order:
            rows_order.append(_id)
            show_row(res)
        # Redisplay all rows.
        show_rows()
        # print(res)


def login_to_registries(client, logins):
    """Log in to multiple registries

    :param client: A DockerClient object to use on the operations.
    :param logins: List of logins to perform: each element of the list must
                   be either a 2-tuple: (USERNAME, PASSWORD) or a 3-tuple:
                   (REGISTRY, USERNAME, PASSWORD) or equivalent iterable.
    """

    for login in logins:
        login = tuple(login)
        assert len(login) in [2, 3], "`logins` must be a 2- or 3-tuple"
        if len(login) == 2:
            registry = None
            username, password = login
        else:
            registry, username, password = login

        log.info(f"Attempting to log in to registry '{registry or 'default'}' "
                 f"with username={username}")

        client.login(username, password, registry=registry)


# pylint: disable=too-many-arguments,too-many-locals
def download_containers_by_compose_file(
        output_dir, compose_file, host_workdir, output_filename,
        platform=None, dind_params=None, use_host_docker=False,
        show_progress=True):
    """
    Creates a container bundle using Docker (either Host Docker or Docker in Docker)

    :param output_dir: Relative output directory to host_workdir
    :param compose_file: Docker Compose YAML file or path
    :param host_workdir: Working directory location on the Docker Host (the
                            system where dockerd we are accessing is running)
    :param output_filename: Output filename of the processed Docker Compose
                            YAML.
    :param platform: Container Platform to fetch (if an image is multi-arch
                        capable)
    :param dind_params: Parameters to pass to Docker-in-Docker (list).
    :param use_host_docker: Use host docker (instead of Docker in Docker)
                            Note: This only really works if the Host Docker
                            Engine is not used by anything else than this
                            script. Otherwise all images stored in the
                            Host Docker storage is going to end up in the
                            Bundle.
    :param show_progress: Whether or not to show progress of the pull process;
                          only relevant when there is a TTY attached to stdout
                          and the terminal is compatible with an xterm.
    """
    # Open Docker Compose file
    if not os.path.isabs(compose_file):
        compose_path = os.path.abspath(compose_file)

    if not os.path.exists(compose_path):
        raise InvalidArgumentError(f"Error: File does not exist: {compose_file}. Aborting.")

    if not os.path.isfile(compose_path):
        raise InvalidArgumentError(f"Error: Not a file: {compose_file}. Aborting.")

    log.info("NOTE: TCB no longer expands environment variables present in the compose file.")

    if show_progress:
        _term = os.environ.get('TERM')
        if not sys.stdout.isatty():
            show_progress = False
        elif not (_term.startswith('xterm') or _term.startswith('rxvt')):
            show_progress = False

    with open(compose_path, encoding='utf-8') as file:
        compose_file_data = yaml.safe_load(file)

    # Basic compose file validation e.g. if it has 'services' section, images are specified, etc.
    validate_compose_file(compose_file_data)

    if use_host_docker:
        log.debug("Using DockerManager")
        manager = DockerManager(output_dir)
    else:
        log.debug("Using DindManager")
        manager = DindManager(output_dir, host_workdir)

    network = get_own_network()
    cacerts = RegistryOperations.get_cacerts()
    logins = RegistryOperations.get_logins()
    try:
        manager.start(network, default_platform=platform, dind_params=dind_params)
        manager.add_cacerts(cacerts)

        dind_client = manager.get_client()
        if dind_client is None:
            return

        # Login to all registries before trying to fetch anything.
        if logins:
            login_to_registries(dind_client, logins)

        # Now we can fetch the containers...
        for svc_name, svc_spec in compose_file_data['services'].items():
            image_name = svc_spec.get('image')
            log.info(f"Fetching container image {image_name} in service {svc_name}")
            if not ":" in image_name:
                image_name += ":latest"

            if show_progress:
                # Use low-level API to get progress information.
                res_stream = dind_client.api.pull(
                    image_name, stream=True, decode=True, platform=platform)
                show_pull_progress_xterm(res_stream)
                image = dind_client.images.get(image_name)
            else:
                # Use high-level API (no progress info).
                image = dind_client.images.pull(image_name, platform=platform)

            svc_spec['image'] = image.attrs['RepoDigests'][0]

        log.info("Saving Docker Compose file")
        with open(os.path.join(manager.output_dir, "docker-compose.yml"), "w") as file:
            file.write(yaml.safe_dump(compose_file_data))

        log.info("Exporting storage")
        manager.save_tar(output_filename)

    except docker.errors.APIError as exc:
        raise OperationFailureError(
            f"Error: container images download failed: {str(exc)}") from exc

    finally:
        manager.stop()

# pylint: enable=too-many-arguments,too-many-locals
