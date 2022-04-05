"""Garage push backend

Push given reference to TreeHub OSTree server using garage-push and sign the
commit using garage-sign.
"""

import logging
import subprocess
import os
import json
import re
import zipfile
import requests
import yaml

from tcbuilder.errors import TorizonCoreBuilderError, InvalidDataError
from tcbuilder.backend import ostree
from tcbuilder.backend.common import set_output_ownership
from tcbuilder.backend.registryops import RegistryOperations, parse_image_name


log = logging.getLogger("torizon." + __name__)


def update_targets(targets_file_path, packagename, commit, subject, body, metadata):
    """Add Toradex specific metadata in targets.json"""

    with open(targets_file_path, 'r') as targets_file:
        data = json.load(targets_file)

    target_name = f"{packagename}-{commit}"
    if target_name not in data["targets"]:
        raise TorizonCoreBuilderError(f"Target {target_name} not found in targets.json")

    data["targets"][target_name]["custom"]["commitSubject"] = subject
    data["targets"][target_name]["custom"]["commitBody"] = body
    data["targets"][target_name]["custom"]["ostreeMetadata"] = metadata

    if log.isEnabledFor(logging.DEBUG):
        formatted_json_string = json.dumps(data["targets"][target_name], indent=2)
        log.debug(f"targets.json for this commit: \"{formatted_json_string}\"")

    with open(targets_file_path, 'w') as targets_file:
        json.dump(data, targets_file, indent=2)


def run_garage_command(command, verbose):
    """Run a single command using garage-sign/garage-push"""
    if verbose:
        command.append("--verbose")
    garage_command = subprocess.run(command, check=False, capture_output=True)

    stdoutstr = garage_command.stdout.decode().strip()
    if verbose:
        if len(stdoutstr) > 0:
            print("== garage-sign stdout:")
            log.debug(stdoutstr)

    # Show warnings to user by default.
    stderrstr = garage_command.stderr.decode()
    if len(stderrstr) > 0:
        print("== garage-sign stderr:")
        log.warning(stderrstr)

    if garage_command.returncode != 0:
        if not verbose:
            log.error(stdoutstr)
        raise TorizonCoreBuilderError(
            f'Error ({str(garage_command.returncode)}) running garage command '
            f'"{command[0]}" with arguments "{command[1:]}"')


# pylint: disable=too-many-locals
def push_ref(ostree_dir, tuf_repo, credentials, ref, package_version=None,
             package_name=None, hardwareids=None, verbose=False):
    """Push OSTree reference to OTA server.

    Push given reference of a given archive OSTree repository to the OTA server
    referenced by the credentials.zip file.
    """

    repo = ostree.open_ostree(ostree_dir)
    commit = repo.read_commit(ref).out_commit

    metadata, subject, body = ostree.get_metadata_from_checksum(repo, commit)
    package_name = package_name or ref
    package_version = package_version or subject

    # Try to find harware id to use from OSTree metadata
    module = None
    if "oe.sota-hardware-id" in metadata:
        module = metadata["oe.sota-hardware-id"]
    elif "oe.machine" in metadata:
        module = metadata["oe.machine"]

    if hardwareids is not None:
        if module not in hardwareids:
            log.info(
                f"The default hardware id '{module}' is being overridden. "
                "If you want to keep it, re-run the command adding the "
                f"flag --hardwareid '{module}'.")
        module = ",".join(hardwareids)

    if module is None:
        raise TorizonCoreBuilderError(
            "No hardware id found in OSTree metadata and none provided.")

    garage_push = ["garage-push",
                   "--credentials", credentials,
                   "--repo", ostree_dir,
                   "--ref", commit]
    if not verbose:
        garage_push.extend(["--loglevel", "4"])
    log.info(f"Pushing {ref} (commit checksum {commit}) to OTA server.")
    run_garage_command(garage_push, verbose)

    log.info(f"Pushed {ref} successfully.")

    log.info(f"Signing OSTree package {package_name} (commit checksum {commit}) "
             f"for Hardware Id(s) \"{module}\".")

    run_garage_command(["garage-sign", "init",
                        "--credentials", credentials,
                        "--repo", tuf_repo], verbose)

    run_garage_command(["garage-sign", "targets", "pull",
                        "--repo", tuf_repo], verbose)

    run_garage_command(["garage-sign", "targets", "add",
                        "--repo", tuf_repo,
                        "--name", package_name,
                        "--format", "OSTREE",
                        "--version", commit,
                        "--length", "0",
                        "--sha256", commit,
                        "--hardwareids", module], verbose)

    # Extend target info with OSTree commit metadata
    # Remove some metadata keys which are already used otherwise or ar rather
    # large and blow up targets.json unnecessary
    for key in ["oe.garage-target-name", "oe.garage-target-version", "oe.sota-hardware-id",
                "oe.layers", "oe.kargs-default"]:
        metadata.pop(key, None)
    targets_file_path = os.path.join(tuf_repo, "roles/unsigned/targets.json")

    update_targets(targets_file_path, package_name, commit, package_version,
                   body, metadata)

    run_garage_command(["garage-sign", "targets", "sign",
                        "--repo", tuf_repo,
                        "--key-name", "targets"], verbose)

    run_garage_command(["garage-sign", "targets", "push",
                        "--repo", tuf_repo], verbose)

    log.info(f"Signed and pushed OSTree package {package_name} successfully.")


def push_compose(credentials, target, version, compose_file,
                 canonicalize=None, force=False):
    """Push docker-compose file to OTA server."""

    zip_ref = zipfile.ZipFile(credentials, 'r')
    treehub_creds = json.loads(zip_ref.read("treehub.json"))
    auth_server = treehub_creds["oauth2"]["server"]
    client_id = treehub_creds["oauth2"]["client_id"]
    client_secret = treehub_creds["oauth2"]["client_secret"]

    try:
        response = requests.post(
            f"{auth_server}/token",
            data={"grant_type": "client_credentials"},
            auth=(client_id, client_secret))
        token = json.loads(response.text)["access_token"]
    except TorizonCoreBuilderError as ex:
        log.error(ex.msg)
        log.error("Couldn't get access token")

    reposerver = zip_ref.read("tufrepo.url").decode("utf-8")

    if canonicalize:
        lock_file, data = canonicalize_compose_file(compose_file, force)
    else:
        lock_file = compose_file
        with open(compose_file, encoding='utf-8') as compose_fd:
            data = compose_fd.read()
        log.info(f"WARNING: the '{os.path.basename(compose_file)}' is been "
                 "pushed to OTA as it is, but in future versions of TorizonCore "
                 "Builder it will be canonicalized in order to follow best "
                 "practices.")

    log.info(f"Pushing '{os.path.basename(lock_file)}' with package version "
             f"{version} to OTA server. You should keep this file under your "
             "version control system.")
    put = requests.put(f"{reposerver}/api/v1/user_repo/targets/{target}_{version}",
                       params={"name": f"{target}", "version": f"{version}",
                               "hardwareIds": "docker-compose"},
                       headers={"Authorization": f"Bearer {token}", }, data=data)

    if put.status_code == 204:
        log.info(f"Successfully pushed {os.path.basename(lock_file)} to OTA server.")
    else:
        log.error(f"Could not upload {os.path.basename(lock_file)} to OTA server at this time:")
        log.error(put.text)
# pylint: enable=too-many-locals


def set_images_hash(compose_file_data):
    """
    Set hash for the images defined in the Docker compose file.

    :param compose_file_data: The Docker compose file data.
    """

    registry = RegistryOperations()

    if not isinstance(compose_file_data.get('services'), dict):
        raise InvalidDataError("Error: No 'services' section in compose file.")

    for svc_name, svc_spec in compose_file_data['services'].items():
        image_name = svc_spec.get('image')
        if not image_name:
            raise InvalidDataError(f"Error: No image specified for service '{svc_name}'.")
        # TODO: Support registry name specification in the compose file.
        image = parse_image_name(image_name)
        if image.registry:
            raise TorizonCoreBuilderError(
                "Error: Registry name specification is not supported yet "
                f"(at service '{svc_name}').")
        response, image_digest = registry.get_manifest(image_name, ret_digest=True)
        if response.status_code != 200:
            raise InvalidDataError(f"Error: Can't determine digest for image '{image_name}'.")
        # Replace tag by digest:
        image.set_tag(image_digest, is_digest=True)
        svc_spec['image'] = image.get_name_with_tag()


def canonicalize_compose_file(compose_file, force=False):
    """
    Canonicalize a Docker compose file that could be pushed to OTA and
    saved as a '.lock.yml/yaml' file.

    :param compose_file: The Docker compose file.
    :param force: Force the overwriting of the canonicalized file.
    :returns:
        The canonicalized data of the Docker compose file as well as the
        name of the '.lock' file created.
    """

    if not compose_file.endswith('.yml') and not compose_file.endswith('.yaml'):
        raise TorizonCoreBuilderError(
            f"File '{compose_file}' does not seem like a Docker compose file. "
            "It does not end with '.yml' or '.yaml'.")

    with open(compose_file, encoding='utf-8') as compose_fd:
        compose_file_data = yaml.load(compose_fd, Loader=yaml.FullLoader)

    # TODO: We should check if this file is really in canonical form and not
    # only relying on the extension name.
    if compose_file.endswith(".lock.yml") or compose_file.endswith(".lock.yaml"):
        log.info(f"File '{compose_file}' (already in canonical form).")
        return compose_file, yaml.dump(compose_file_data, Dumper=yaml.Dumper)

    canonical_compose_file_lock = re.sub(r"(.ya?ml)$", r".lock\1", compose_file)
    if os.path.exists(canonical_compose_file_lock) and not force:
        raise TorizonCoreBuilderError(
            f"Canonicalized file '{canonical_compose_file_lock}' already exists. "
            "Please use the '--force' parameter if you want it to be overwritten.")

    set_images_hash(compose_file_data)
    canonical_data = yaml.dump(compose_file_data, Dumper=yaml.Dumper)

    with open(canonical_compose_file_lock, 'w', encoding='utf-8') as compose_lock_fd:
        compose_lock_fd.write(canonical_data)
    set_output_ownership(canonical_compose_file_lock)
    log.info(f"Canonicalized file '{canonical_compose_file_lock}' has been generated.")

    return canonical_compose_file_lock, canonical_data
