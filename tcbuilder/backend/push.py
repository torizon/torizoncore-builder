"""Garage push backend

Push given reference to TreeHub OSTree server using garage-push and sign the
commit using garage-sign.
"""

import logging
import subprocess
import os
import json

from tcbuilder.errors import TorizonCoreBuilderError
from tcbuilder.backend import ostree

log = logging.getLogger("torizon." + __name__)

def update_targets(targets_file_path, packagename, commit, subject, body):
    """Add Toradex specific metadata in targets.json"""

    with open(targets_file_path, 'r') as targets_file:
        data = json.load(targets_file)

    target_name = f"{packagename}-{commit}"
    if target_name not in data["targets"]:
        raise TorizonCoreBuilderError(f"Target {target_name} not found in targets.json")

    data["targets"][target_name]["custom"]["commitSubject"] = subject
    data["targets"][target_name]["custom"]["commitBody"] = body

    log.debug("targets.json for this commit: \"{}\"", data["targets"][target_name])

    with open(targets_file_path, 'w') as targets_file:
        json.dump(data, targets_file, indent=2)

def run_garage_command(command):
    """Run a single command using garage-sign/garage-push"""
    garage_command = subprocess.run(command, check=False,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if garage_command.returncode != 0:
        raise TorizonCoreBuilderError("Error running garage command \"{}\" with arguments \"{}\""
                                      .format(command[0], command[1:]))

    stdoutstr = garage_command.stdout.decode()
    if len(stdoutstr) > 0:
        log.debug(stdoutstr)

    # Show warnings to user by default.
    stderrstr = garage_command.stderr.decode()
    if len(stderrstr) > 0:
        log.warning(stderrstr)


def push_ref(ostree_dir, tuf_repo, credentials, ref, hardwareids=None):
    """Push OSTree reference to OTA server.

    Push given reference of a given archive OSTree repository to the OTA server
    referenced by the credentials.zip file.
    """

    repo = ostree.open_ostree(ostree_dir)
    commit = repo.read_commit(ref).out_commit

    metadata, subject, body = ostree.get_metadata_from_ref(repo, commit)

    # Try to find harware id to use from OSTree metadata
    module = None
    if "oe.sota-hardware-id" in metadata:
        module = metadata["oe.sota-hardware-id"]
    elif "oe.machine" in metadata:
        module = metadata["oe.machine"]

    if module is None:
        if hardwareids is None:
            raise TorizonCoreBuilderError(
                "No hardware id found in OSTree metadata and none provided.")
        module = hardwareids

    log.info(f"Pushing {ref} (commit checksum {commit}) to OTA server.")
    run_garage_command(["garage-push",
                        "--credentials", credentials,
                        "--repo", ostree_dir,
                        "--ref", commit])

    log.info(f"Pushed {ref} successfully.")

    packagename = ref

    log.info(f"Signing OSTree package {packagename} (commit checksum {commit}) "
             f"for Hardware Id(s) \"{module}\".")

    run_garage_command(["garage-sign", "init",
                        "--credentials", credentials,
                        "--repo", tuf_repo])

    run_garage_command(["garage-sign", "targets", "pull",
                        "--repo", tuf_repo])

    run_garage_command(["garage-sign", "targets", "add",
                        "--repo", tuf_repo,
                        "--name", packagename,
                        "--format", "OSTREE",
                        "--version", commit,
                        "--length", "0",
                        "--sha256", commit,
                        "--hardwareids", module])

    # Extend target info with OSTree commit metadata
    targets_file_path = os.path.join(tuf_repo, "roles/unsigned/targets.json")
    update_targets(targets_file_path, packagename, commit, subject, body)

    run_garage_command(["garage-sign", "targets", "sign",
                        "--repo", tuf_repo,
                        "--key-name", "targets"])

    run_garage_command(["garage-sign", "targets", "push",
                        "--repo", tuf_repo])

    log.info(f"Signed and pushed OSTree package {packagename} successfully.")
