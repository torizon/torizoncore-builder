load 'bats/bats-support/load.bash'
load 'bats/bats-assert/load.bash'
load 'bats/bats-file/load.bash'
load 'lib/common.bash'

@test "platform: check help output" {
    run torizoncore-builder platform push --help
    assert_success
    assert_output --partial 'usage: torizoncore-builder platform push'
}

@test "platform: docker-compose canonicalization" {
    local CANON_DIR="$SAMPLES_DIR/push/canonicalize"

	# Test-case: everything good
    run torizoncore-builder platform push "$CANON_DIR/docker-compose-good.yml" --canonicalize-only --force
    assert_success
    assert_output --partial "has been generated"
	# Check produced file:
    run cat "$CANON_DIR/docker-compose-good.lock.yml"
    assert_success
    assert_output --partial "torizon/torizoncore-builder@sha256:"
    assert_output --partial "torizon/debian@sha256:"
    assert_output --partial "torizon/weston@sha256:"

	# Test-case: error present
    run torizoncore-builder platform push "$CANON_DIR/docker-compose-no-services.yml" --canonicalize-only --force
    assert_failure
    assert_output --partial "No 'services' section in compose file"

	# Test-case: error present
    run torizoncore-builder platform push "$CANON_DIR/docker-compose-no-image.yml" --canonicalize-only --force
    assert_failure
    assert_output --partial "No image specified for service"

	# Test-case: error present
    run torizoncore-builder platform push "$CANON_DIR/docker-compose-with-registry.yml" --canonicalize-only --force
    assert_failure
    assert_output --partial "Registry name specification is not supported"
}

@test "platform: provisioning-data with offline-provisioning" {
    skip-no-ota-credentials
    local CREDS_PILOT_ZIP=$(decrypt-credentials-file "$SAMPLES_DIR/credentials/credentials-pilot.zip.enc")

    # case: no arguments passed
    run torizoncore-builder platform provisioning-data
    assert_failure
    assert_output --partial 'error: the following arguments are required: --credentials'

    # case: missing arguments
    run torizoncore-builder platform provisioning-data \
        --credentials "$CREDS_PILOT_ZIP"
    assert_failure
    assert_output --partial \
        'At least one of --shared-data or --online-data must be specified (aborting)'

    # case: invalid argument
    run torizoncore-builder platform provisioning-data \
        --credentials "$CREDS_PILOT_ZIP" \
        --shared-data test.xyz
    assert_failure
    assert_output --partial 'Shared-data archive must have the .tar.gz extension'

    # case: output already exists
    local PILOT_SHDATA="pilot-shared-data.tar.gz"
    touch "$PILOT_SHDATA"
    run torizoncore-builder platform provisioning-data \
        --credentials "$CREDS_PILOT_ZIP" \
        --shared-data "$PILOT_SHDATA"
    assert_failure
    assert_output --regexp "Output file '.*' already exists \(aborting\)"
    rm -f "$PILOT_SHDATA"

    # case: generate shared-data tarball (success)
    local PILOT_SHDATA="pilot-shared-data.tar.gz"
    rm -f "$PILOT_SHDATA"
    run torizoncore-builder platform provisioning-data \
        --credentials "$CREDS_PILOT_ZIP" \
        --shared-data "$PILOT_SHDATA"
    assert_success
    assert_output --regexp "Shared data archive '.*' successfully generated"
    rm -f "$PILOT_SHDATA"

    # case: output already exists (success, with --force switch)
    local PILOT_SHDATA="pilot-shared-data.tar.gz"
    touch "$PILOT_SHDATA"
    run torizoncore-builder platform provisioning-data \
        --credentials "$CREDS_PILOT_ZIP" \
        --shared-data "$PILOT_SHDATA" \
        --force
    assert_success
    assert_output --regexp "Shared data archive '.*' successfully generated"
    rm -f "$PILOT_SHDATA"
}

@test "platform: provisioning-data with online-provisioning" {
    skip-no-ota-credentials
    local CREDS_PILOT_ZIP=$(decrypt-credentials-file "$SAMPLES_DIR/credentials/credentials-pilot.zip.enc")
    local CREDS_PILOT_NOPROV_ZIP=$(decrypt-credentials-file "$SAMPLES_DIR/credentials/credentials-pilot-noprov.zip.enc")

    # case: bad client name
    run torizoncore-builder platform provisioning-data \
        --credentials "$CREDS_PILOT_ZIP" \
        --online-data "non-existing-client"
    assert_failure
    assert_output --partial \
        'Error: Currently the only supported client-name is "DEFAULT" (aborting)'

    # case: non-existing credentials file
    run torizoncore-builder platform provisioning-data \
        --credentials "credentials-pilot-XYZ.zip" \
        --online-data "DEFAULT"
    assert_failure
    assert_output --partial 'No such file or directory'

    # case: bad credentials file
    run torizoncore-builder platform provisioning-data \
        --credentials "$CREDS_PILOT_NOPROV_ZIP" \
        --online-data "DEFAULT"
    assert_failure
    assert_output --partial \
        'Credentials file does not contain provisioning data (aborting)'
    assert_output --partial \
        'Downloading a more recent credentials.zip file from the OTA server should solve the above error'

    # case: success
    run torizoncore-builder platform provisioning-data \
        --credentials "$CREDS_PILOT_ZIP" \
        --online-data "DEFAULT"
    assert_success
    assert_output --partial 'Online provisioning data:'
}

@test "platform: provisioning-data online+offline-provisioning" {
    skip-no-ota-credentials
    local CREDS_PILOT_ZIP=$(decrypt-credentials-file "$SAMPLES_DIR/credentials/credentials-pilot.zip.enc")

    # case: success
    local PILOT_SHDATA="pilot-shared-data.tar.gz"
    rm -f "$PILOT_SHDATA"
    run torizoncore-builder platform provisioning-data \
        --credentials "$CREDS_PILOT_ZIP" \
        --shared-data "$PILOT_SHDATA" \
        --online-data "DEFAULT"
    assert_success
    assert_output --partial 'Online provisioning data:'
}
