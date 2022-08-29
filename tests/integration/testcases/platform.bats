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
    local GOOD_YML="docker-compose-good"

    # Test-case: everything good
    run torizoncore-builder platform push "$CANON_DIR/$GOOD_YML.yml" --canonicalize-only --force
    assert_success
    assert_output --partial "'$CANON_DIR/$GOOD_YML.lock.yml' has been generated"
	  # Check produced file:
    run cat "$CANON_DIR/docker-compose-good.lock.yml"
    assert_success
    assert_output --partial "torizon/torizoncore-builder@sha256:"
    assert_output --partial "torizon/debian@sha256:"
    assert_output --partial "torizon/weston@sha256:"

    # Test-case: with file already present and no --force
    run torizoncore-builder platform push "$CANON_DIR/$GOOD_YML.yml" --canonicalize-only
    assert_failure
    assert_output --partial "'$CANON_DIR/$GOOD_YML.lock.yml' already exists. Please use the '--force' parameter"

    # Test-case: file with no yml/yaml extension
    run torizoncore-builder platform push "$CANON_DIR/$GOOD_YML" --canonicalize-only --force
    assert_failure
    assert_output --partial "'$CANON_DIR/$GOOD_YML' does not seem like a Docker compose file."

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
    local CREDS_PROD_ZIP=$(decrypt-credentials-file "$SAMPLES_DIR/credentials/credentials-prod.zip.enc")

    # case: no arguments passed
    run torizoncore-builder platform provisioning-data
    assert_failure
    assert_output --partial 'error: the following arguments are required: --credentials'

    # case: missing arguments
    run torizoncore-builder platform provisioning-data \
        --credentials "$CREDS_PROD_ZIP"
    assert_failure
    assert_output --partial \
        'At least one of --shared-data or --online-data must be specified (aborting)'

    # case: invalid argument
    run torizoncore-builder platform provisioning-data \
        --credentials "$CREDS_PROD_ZIP" \
        --shared-data test.xyz
    assert_failure
    assert_output --partial 'Shared-data archive must have the .tar.gz extension'

    # case: output already exists
    local PILOT_SHDATA="pilot-shared-data.tar.gz"
    touch "$PILOT_SHDATA"
    run torizoncore-builder platform provisioning-data \
        --credentials "$CREDS_PROD_ZIP" \
        --shared-data "$PILOT_SHDATA"
    assert_failure
    assert_output --regexp "Output file '.*' already exists \(aborting\)"
    rm -f "$PILOT_SHDATA"

    # case: generate shared-data tarball (success)
    local PILOT_SHDATA="pilot-shared-data.tar.gz"
    rm -f "$PILOT_SHDATA"
    run torizoncore-builder platform provisioning-data \
        --credentials "$CREDS_PROD_ZIP" \
        --shared-data "$PILOT_SHDATA"
    assert_success
    assert_output --regexp "Shared data archive '.*' successfully generated"
    rm -f "$PILOT_SHDATA"

    # case: output already exists (success, with --force switch)
    local PILOT_SHDATA="pilot-shared-data.tar.gz"
    touch "$PILOT_SHDATA"
    run torizoncore-builder platform provisioning-data \
        --credentials "$CREDS_PROD_ZIP" \
        --shared-data "$PILOT_SHDATA" \
        --force
    assert_success
    assert_output --regexp "Shared data archive '.*' successfully generated"
    rm -f "$PILOT_SHDATA"
}

@test "platform: provisioning-data with online-provisioning" {
    skip-no-ota-credentials
    local CREDS_PROD_ZIP=$(decrypt-credentials-file "$SAMPLES_DIR/credentials/credentials-prod.zip.enc")
    local CREDS_PILOT_NOPROV_ZIP=$(decrypt-credentials-file "$SAMPLES_DIR/credentials/credentials-pilot-noprov.zip.enc")

    # case: bad client name
    run torizoncore-builder platform provisioning-data \
        --credentials "$CREDS_PROD_ZIP" \
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
        --credentials "$CREDS_PROD_ZIP" \
        --online-data "DEFAULT"
    assert_success
    assert_output --partial 'Online provisioning data:'
}

@test "platform: provisioning-data online+offline-provisioning" {
    skip-no-ota-credentials
    local CREDS_PROD_ZIP=$(decrypt-credentials-file "$SAMPLES_DIR/credentials/credentials-prod.zip.enc")

    # case: success
    local PILOT_SHDATA="pilot-shared-data.tar.gz"
    rm -f "$PILOT_SHDATA"
    run torizoncore-builder platform provisioning-data \
        --credentials "$CREDS_PROD_ZIP" \
        --shared-data "$PILOT_SHDATA" \
        --online-data "DEFAULT"
    assert_success
    assert_output --partial 'Online provisioning data:'
}

@test "platform: test push with docker-compose files" {
    skip-no-ota-credentials
    local CREDS_PROD_ZIP=$(decrypt-credentials-file "$SAMPLES_DIR/credentials/credentials-prod.zip.enc")
    local CANON_DIR="$SAMPLES_DIR/push/canonicalize"
    local GOOD_YML="docker-compose-good"
    local P_VERSION="Test_Version"
    local P_NAME=$(git rev-parse --short HEAD 2>/dev/null || date +'%m%d%H%M%S')

    # Test-case: push a non-canonical file
    run torizoncore-builder platform push "$CANON_DIR/$GOOD_YML.yml" \
        --credentials "$CREDS_PROD_ZIP"
    assert_success
    assert_output --partial 'This package is not in its canonical form'
    assert_output --partial 'Successfully pushed'
    refute_output --partial 'Canonicalized file'

    # Test-case: push generating canonicalized file
    run torizoncore-builder platform push "$CANON_DIR/$GOOD_YML.yml" \
        --credentials "$CREDS_PROD_ZIP" --canonicalize --force
    assert_success
    assert_output --partial "Canonicalized file '$CANON_DIR/$GOOD_YML.lock.yml' has been generated."
    assert_output --partial 'Successfully pushed'
    refute_output --partial 'the pakcage must end with ".lock.yml"'

    # Test-case: push a canonicalized file with a non canonicalized package name
    run torizoncore-builder platform push "$CANON_DIR/$GOOD_YML.lock.yml" \
        --package-version "$P_VERSION" --package-name "$P_NAME.yaml" \
        --credentials "$CREDS_PROD_ZIP" --description "Test_docker-compose"
    assert_success
    assert_output --partial 'the package name must end with ".lock.yml"'
    assert_output --partial "package version $P_VERSION"
    assert_output --partial 'Successfully pushed'
    assert_output --partial "Description for $P_NAME.yaml updated."
}

@test "platform: test push with images" {
    skip-no-ota-credentials
    local CREDS_PROD_ZIP=$(decrypt-credentials-file "$SAMPLES_DIR/credentials/credentials-prod.zip.enc")
    local CANON_DIR="$SAMPLES_DIR/push/canonicalize"
    local IMG_NAME="my_custom_image"

    torizoncore-builder-clean-storage
    torizoncore-builder images --remove-storage unpack $DEFAULT_TEZI_IMAGE

    run torizoncore-builder union $IMG_NAME
    assert_success

    # Grab Commit hash created by the union command
    local ARCHIVE="/storage/ostree-archive/"
    run torizoncore-builder-shell "ostree --repo=$ARCHIVE show $IMG_NAME | \
                                   sed -Ene 's/^commit\s([0-9a-f]{64}$)/\1/p'"
    assert_success
    local UNION_HASH=$output

    run torizoncore-builder-shell "ostree --repo=$ARCHIVE --print-metadata-key=oe.machine \
                                   show $IMG_NAME"
    assert_success
    local METADATA_MACHINE=$output

    run torizoncore-builder platform push "$IMG_NAME" --hardwareid "modelA" \
        --hardwareid "modelB" --credentials "$CREDS_PROD_ZIP"
    assert_success
    assert_output --partial "The default hardware id $METADATA_MACHINE is being overridden"
    assert_output --partial "Signed and pushed OSTree package $IMG_NAME successfully"
    assert_output --partial "Pushing $IMG_NAME (commit checksum $UNION_HASH)"
    assert_output --regexp "Signing OSTree package $IMG_NAME.*Hardware Id\(s\) \"modelA,modelB\""

    run torizoncore-builder platform push "$IMG_NAME" --hardwareid "$METADATA_MACHINE" \
        --hardwareid "modelA" --credentials "$CREDS_PROD_ZIP"
    assert_success
    assert_output --partial "Signed and pushed OSTree package $IMG_NAME successfully"
    assert_output --partial "Pushing $IMG_NAME (commit checksum $UNION_HASH)"
    refute_output --partial "The default hardware id '$METADATA_MACHINE' is being overridden"

    # Get and test Branch name
    local EXTRN_OSTREE_DIR="$SAMPLES_DIR/ostree-archive"
    run ostree --repo="$EXTRN_OSTREE_DIR" refs
    assert_success
    local EXTRN_OSTREE_BRANCH=$(echo "$output" | sed -n 1p)

    run ostree --repo="$EXTRN_OSTREE_DIR" show "$EXTRN_OSTREE_BRANCH"
    assert_success
    local EXTRN_COMMIT_HASH=$(echo "$output" | sed -Ene 's/^commit\s([0-9a-f]{64})$/\1/p')

    # Test with no hardwareid defined
    run torizoncore-builder platform push "$EXTRN_OSTREE_BRANCH" --repo "$EXTRN_OSTREE_DIR" \
        --credentials "$CREDS_PROD_ZIP"
    assert_failure
    assert_output "No hardware id found in OSTree metadata and none provided."

    # Test with hardwareid defined and description
    local HARDWARE_ID="test-id"
    run torizoncore-builder platform push "$EXTRN_OSTREE_BRANCH" --repo "$EXTRN_OSTREE_DIR" \
        --hardwareid "$HARDWARE_ID" --credentials "$CREDS_PROD_ZIP" --description "Test"
    assert_success
    assert_output --regexp "The default hardware id .* is being overridden"
    assert_output --partial "Pushing $EXTRN_OSTREE_BRANCH (commit checksum $EXTRN_COMMIT_HASH)"
    assert_output --partial "for Hardware Id(s) \"$HARDWARE_ID\""
    assert_output --partial "OSTree package $EXTRN_OSTREE_BRANCH successfully"
    assert_output --partial "Description for $EXTRN_OSTREE_BRANCH updated."
}
