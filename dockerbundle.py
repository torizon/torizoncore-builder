#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import docker
import compose.config
import compose.config.environment
import compose.config.serialize

class DindManager:
    DIND_NETWORK_NAME = "fetch-dind-network"
    DIND_CONTAINER_IMAGE = "docker:19.03.2-dind"
    DIND_CONTAINER_NAME = "fetch-dind"
    DIND_VOLUME_NAME = "dind-volume"

    def __init__(self):
        cert_dir = os.path.join(os.getcwd(), "certs")
        if not os.path.isdir(cert_dir):
            os.mkdir(cert_dir)
        self.cert_dir = cert_dir

        output_dir = os.path.join(os.getcwd(), "output")
        if not os.path.isdir(output_dir):
            os.mkdir(output_dir)
        self.output_dir = output_dir

        self.host_client = docker.from_env()


    def start(self):
        self.dind_volume = self.host_client.volumes.create(name=self.DIND_VOLUME_NAME)
        self.dind_container = self.host_client.containers.run(self.DIND_CONTAINER_IMAGE,
            privileged=True,
            environment= { 'DOCKER_TLS_CERTDIR': '/certs' },
            volumes= {
                       self.cert_dir: {'bind': '/certs/client', 'mode': 'rw'},
                       self.DIND_VOLUME_NAME: {'bind': '/var/lib/docker/', 'mode': 'rw'}
                     },
            network=self.DIND_NETWORK_NAME,
            name=self.DIND_CONTAINER_NAME,
            auto_remove=True,
            detach=True,
            command = [ "--storage-driver", "overlay2" ])

    def stop(self):
        self.dind_container.stop()
        # Otherwise Docker API throws execeptions...
        time.sleep(1)
        self.dind_volume.remove()

    def get_client(self):
        # Use TLS to authenticate
        tls_config = docker.tls.TLSConfig(ca_cert='certs/ca.pem', verify='certs/ca.pem',
                client_cert=('certs/cert.pem', 'certs/key.pem'), assert_hostname=False)

        # Find IP of the DIND cotainer (make sure attributes are current...)
        self.dind_container.reload()
        dind_ip = self.dind_container.attrs["NetworkSettings"]["Networks"][self.DIND_NETWORK_NAME]["IPAddress"]
        dind_url = "tcp://{}:2376".format(dind_ip)

        dind_client = docker.DockerClient(base_url=dind_url, tls=tls_config)
        return dind_client

    def save_tar(self, filename):
        output_mount_dir = "/mnt"
        output_file = os.path.join(output_mount_dir, filename)

        # Use a container to tar the Docker storage backend instead of the
        # built-in save_tar() is more flexible...
        tar_container = self.host_client.containers.run("debian:buster",
                volumes = {
                            self.DIND_VOLUME_NAME: {'bind': '/var/lib/docker/', 'mode': 'ro'},
                            self.output_dir: {'bind': output_mount_dir, 'mode': 'rw'}
                          },
                command = [ "/usr/bin/tar", "--numeric-owner",
                "--preserve-permissions", "--directory=/var/lib/docker",
                "--xattrs-include='*'", "--create", "--file", output_file,
                "overlay2/", "image/" ],
                auto_remove=True)


def main():
    dind_manager = DindManager()

    print("Starting DIND container")
    dind_manager.start()

    # Wait until Docker is ready...
    time.sleep(5)

    try:
        dind_client = dind_manager.get_client()

        # Open Docker Compose file
        base_dir = "/home/ags/projects/toradex/torizon/kiosk-mode-browser"
        environment = compose.config.environment.Environment.from_env_file(base_dir)
        config = compose.config.find(base_dir, None, environment, None)
        cfg = compose.config.load(config)

        # Now we can fetch the containers...
        for service in cfg.services:
            image = service['image']
            print("Fetching container image {}".format(image))
            image = dind_client.images.pull(image, platform="linux/arm/v7")

            # Replace image with concrete Image ID
            service['image'] = image.attrs['RepoDigests'][0]

        print("Save Docker Compose file")
        f = open(os.path.join(dind_manager.output_dir, "docker-compose.yml"), "w")
        f.write(compose.config.serialize.serialize_config(cfg))
        f.close()
       
        print("Exporting storage")
        dind_manager.save_tar("docker-storage.tar")

    finally:
        print("Stopping DIND container")
        dind_manager.stop()

if __name__== "__main__":
    main()

