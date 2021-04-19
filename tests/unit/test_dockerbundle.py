"""Integration test for Docker bundle

Note: These tests heavily rely on the environment:
- /workdir needs to exist, and /workdir/bundle will be used as output directory
- HOST_WORKDIR need to be set to the path of /workdir on the Docker host
  (location of workdir as seen from dockerd).
"""
import os

import yaml

import dockerbundle

TEST_DOCKER_COMPOSE_DATA = {'version': '2.4', \
    'services': {'portainer': {'image': 'portainer/portainer:latest'}}}

def test_dockerbundle(work_dir):
    compose_file = "docker-compose.yml"
    compose_file_path = os.path.join(str(work_dir), compose_file)
    output_dir_rel = "bundle"
    output_file = "docker-bundle.tar.zst"
    os.chdir(str(work_dir))

    with open(compose_file_path, "w") as f:
        f.write(yaml.dump(TEST_DOCKER_COMPOSE_DATA))

    dockerbundle.download_containers_by_compose_file(
                output_dir_rel, compose_file_path, host_workdir=os.environ["HOST_WORKDIR"], docker_username=None,
                docker_password=None, registry=None, platform="linux/arm/v7", output_filename=output_file, use_host_docker=False)

    with open(os.path.join(output_dir_rel, compose_file), "r") as f:
        compose = yaml.load(f, Loader=yaml.FullLoader)
        # Verify the image is using sha256 now
        assert "sha256" in compose["services"]["portainer"]["image"]

    output_filepath = os.path.join(output_dir_rel, output_file)
    assert os.path.isfile(output_filepath)

    stat = os.stat(output_filepath)
    # The output file should exist and be larger than lets say 1MiB
    assert stat.st_size > 1024 * 1024
