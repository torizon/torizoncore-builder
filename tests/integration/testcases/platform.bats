load 'bats/bats-support/load.bash'
load 'bats/bats-assert/load.bash'
load 'bats/bats-file/load.bash'
load 'lib/registries.sh'
load 'lib/common.bash'

# To avoid starting and stop registries on each test, we start them here. This should be safe since
# we only read from them.
#
# NOTE: The tests that actually need the registries should do:
# > run check-registries
# > assert_success
#
# TODO: Review all tests requiring a "private" registry.
#
setup_file() {
    start-registries
}

teardown_file() {
    stop-registries
}

# Test the --canonicalize-only switch of the platform push command.
#
# $1: Name of compose file ending with the .yml extension; the name is relative
#     to the directory where the canonicalize samples are kept.
# $@: Remaining arguments are forwarded to torizoncore-builder.
#
test_canonicalize_only_success() {
    local CANON_DIR="$SAMPLES_DIR/push/canonicalize"
    local ORG_FNAME="${1?Name of compose file (with .yml extension) inside ${CANON_DIR} must be passed}"
    local LCK_FNAME="${ORG_FNAME%%.yml}.lock.yml"
    shift # Extra arguments will be forwarded to torizoncore-builder.

    local ORG_IMG_COUNT=$(cat "$CANON_DIR/${ORG_FNAME}" | grep -Ee "^\\s+image *:" | wc -l)

    run torizoncore-builder platform push "$CANON_DIR/${ORG_FNAME}" --canonicalize-only "$@"
    assert_success
    assert_output --partial "'$CANON_DIR/${LCK_FNAME}' has been generated"

    local RES_IMG_COUNT=$(cat "$CANON_DIR/${LCK_FNAME}" | grep -Ee "^\\s+image *:.*@sha256:" | wc -l)
    if [ "$ORG_IMG_COUNT" -ne "$RES_IMG_COUNT" ]; then
        fail "Canonicalization failed ($ORG_IMG_COUNT != $RES_IMG_COUNT)"
    fi
}

@test "platform push: check help output" {
    run torizoncore-builder platform push --help
    assert_success
    assert_output --partial 'usage: torizoncore-builder platform push'
}

@test "platform push: multibyte characters in arguments" {
    run torizoncore-builder platform push \
        --credentials fake-creds.zip \
        --package-name "name-with-emojis-😀-😁" "SOME_REF"
    assert_failure
    assert_output --partial 'Error: the passed package name contains multibyte character(s)'

    run torizoncore-builder platform push \
        --credentials fake-creds.zip \
        --package-version "version-with-emojis-😀-😁" "SOME_REF"
    assert_failure
    assert_output --partial 'Error: the passed package version contains multibyte character(s)'

    run torizoncore-builder platform push \
        --credentials fake-creds.zip \
        --description "description-with-emojis-😀-😁" "SOME_REF"
    assert_failure
    assert_output --partial 'Error: the passed description contains multibyte character(s)'

    run torizoncore-builder platform push \
        --credentials fake-creds.zip "SOME_REF_WITH_EMOJIS_😀_😁"
    assert_failure
    assert_output --partial 'Error: the passed REF contains multibyte character(s)'
}

@test "platform push: control characters in arguments" {
    run torizoncore-builder platform push \
        --credentials fake-creds.zip \
        --package-name "name-with-ctrlchrs-$(echo -e '\a')" "SOME_REF"
    assert_failure
    assert_output --partial 'Error: the passed package name contains control character(s)'

    run torizoncore-builder platform push \
        --credentials fake-creds.zip \
        --package-version "version-with-ctrlchrs-$(echo -e '\b')" "SOME_REF"
    assert_failure
    assert_output --partial 'Error: the passed package version contains control character(s)'

    run torizoncore-builder platform push \
        --credentials fake-creds.zip \
        --description "description-with-ctrlchrs-$(echo -e '\v')" "SOME_REF"
    assert_failure
    assert_output --partial 'Error: the passed description contains control character(s)'

    run torizoncore-builder platform push \
        --credentials fake-creds.zip "SOME_REF_WITH_CTRLCHRS_$(echo -e '\v')"
    assert_failure
    assert_output --partial 'Error: the passed REF contains control character(s)'
}

@test "platform push: docker-compose canonicalization errors" {
    local CANON_DIR="$SAMPLES_DIR/push/canonicalize"

    # Test-case: file with no yml/yaml extension
    run torizoncore-builder platform push "$CANON_DIR/docker-compose-good" --canonicalize-only --force
    assert_failure
    assert_output --partial "'$CANON_DIR/docker-compose-good' does not seem like a Docker compose file."

    # Test-case: error present
    run torizoncore-builder platform push "$CANON_DIR/docker-compose-no-services.yml" --canonicalize-only --force
    assert_failure
    assert_output --partial "No 'services' section in compose file"

    # Test-case: error present
    run torizoncore-builder platform push "$CANON_DIR/docker-compose-no-image.yml" --canonicalize-only --force
    assert_failure
    assert_output --partial "No image specified for service"

    # Test-case: with file already present and no --force
    touch "$CANON_DIR/docker-compose-no-image.lock.yml"
    run torizoncore-builder platform push "$CANON_DIR/docker-compose-no-image.yml" --canonicalize-only
    assert_failure
    assert_output --partial "'$CANON_DIR/docker-compose-no-image.lock.yml' already exists. Please use the '--force' parameter"
}

@test "platform push: docker-compose canonicalization (DockerHub without authentication)" {
    if [ "${TCB_UNDER_CI}" = "1" ]; then
       skip "avoid hitting DH pull limits in CI"
    fi
    test_canonicalize_only_success "docker-compose-dh.yml" --force
}

@test "platform push: docker-compose canonicalization (DockerHub with authentication)" {
    # TODO: Consider creating a compose file referring to files only accessible after authenticating.
    if [ -z "${CI_DOCKER_HUB_PULL_USER}" -o -z "${CI_DOCKER_HUB_PULL_PASSWORD}" ]; then
       skip "DockerHub credentials not set"
    fi
    test_canonicalize_only_success \
       "docker-compose-dh.yml" \
       --force \
       --login "${CI_DOCKER_HUB_PULL_USER}" "${CI_DOCKER_HUB_PULL_PASSWORD}"
}

@test "platform push: docker-compose canonicalization (GCR without authentication)" {
    test_canonicalize_only_success "docker-compose-gcr.yml" --force
}

@test "platform push: docker-compose canonicalization (DockerHub with required authentication)" {
    # TODO: This would require a repository only accessible with a password on DockerHub.
    skip "not implemented"
}

@test "platform push: docker-compose canonicalization (GCR with required authentication)" {
    # TODO: This would require a repository only accessible with a password on GCR.
    skip "not implemented"
}

@test "platform push: docker-compose canonicalization (insecure registry)" {
    run check-registries
    assert_success

    local CANON_DIR="$SAMPLES_DIR/push/canonicalize"
    local ORG_FILE="$CANON_DIR/docker-compose-hosted.yml"
    local MOD_FILE="$CANON_DIR/docker-compose-insecure_tmp.yml"
    sed 's/@REGISTRY@/'"${INSEC_REG_IP}"'/g' "$ORG_FILE" > "$MOD_FILE"

    test_canonicalize_only_success "${MOD_FILE##*/}" --force
    ## TODO: --insecure-registry=${INSEC_REG_IP}
}

@test "platform push: docker-compose canonicalization (secure registry without authentication)" {
    run check-registries
    assert_success

    local CANON_DIR="$SAMPLES_DIR/push/canonicalize"
    local ORG_FILE="$CANON_DIR/docker-compose-hosted.yml"
    local MOD_FILE="$CANON_DIR/tmp_docker-compose-secure-without-auth.yml"
    sed 's/@REGISTRY@/'"${SR_NO_AUTH_IP}"'/g' "$ORG_FILE" > "$MOD_FILE"

    test_canonicalize_only_success "${MOD_FILE##*/}" \
        --force --cacert-to "${SR_NO_AUTH_IP}" "${SR_NO_AUTH_CERTS}/cacert.crt"
}

@test "platform push: docker-compose canonicalization (secure registry with authentication)" {
    run check-registries
    assert_success

    local CANON_DIR="$SAMPLES_DIR/push/canonicalize"
    local ORG_FILE="$CANON_DIR/docker-compose-hosted.yml"
    local MOD_FILE="$CANON_DIR/tmp_docker-compose-secure-without-auth.yml"
    sed 's/@REGISTRY@/'"${SR_WITH_AUTH_IP}"'/g' "$ORG_FILE" > "$MOD_FILE"

    test_canonicalize_only_success "${MOD_FILE##*/}" \
        --force \
        --cacert-to "${SR_WITH_AUTH_IP}" "${SR_WITH_AUTH_CERTS}/cacert.crt" \
        --login-to "${SR_WITH_AUTH_IP}" "toradex" "test"
}

@test "platform provisioning-data: offline-provisioning" {
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

@test "platform provisioning-data: online-provisioning" {
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

@test "platform provisioning-data: online+offline-provisioning" {
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

@test "platform push: test push with docker-compose files" {
    skip-no-ota-credentials
    local CREDS_PROD_ZIP=$(decrypt-credentials-file "${SAMPLES_DIR}/credentials/credentials-prod.zip.enc")
    local CANON_DIR="${SAMPLES_DIR}/push/canonicalize"
    local GOOD_YML="docker-compose-good"
    local P_NAME=$(git rev-parse --short HEAD 2>/dev/null || date +'%m%d%H%M%S')
    local TIME_AND_NAME="$(date +'%H%M%S')-${P_NAME}"

    # Test-case: push a non-canonical file
    run torizoncore-builder platform push "${CANON_DIR}/${GOOD_YML}.yml" \
        --package-name "${TIME_AND_NAME}.yml" --credentials "${CREDS_PROD_ZIP}"
    assert_success
    assert_output --partial 'This package is not in its canonical form'
    assert_output --partial 'Successfully pushed'
    refute_output --partial 'Canonicalized file'

    # Test-case: push generating canonicalized file
    run torizoncore-builder platform push "${CANON_DIR}/${GOOD_YML}.yml" \
        --credentials "${CREDS_PROD_ZIP}" --package-version "$(date +'%H%M%S')" \
        --canonicalize --force
    assert_success
    assert_output --partial "Canonicalized file '${CANON_DIR}/${GOOD_YML}.lock.yml' has been generated."
    assert_output --partial 'Successfully pushed'
    refute_output --partial 'the package name must end with ".lock.yml"'

    # Test-case: push a canonicalized file with a non canonicalized package name
    run torizoncore-builder platform push "${CANON_DIR}/${GOOD_YML}.lock.yml" \
        --package-name "${P_NAME}.yml" --package-version "${TIME_AND_NAME}" \
        --credentials "${CREDS_PROD_ZIP}" --description "Test_docker-compose"
    assert_success
    assert_output --partial 'the package name must end with ".lock.yml"'
    assert_output --partial "package version ${TIME_AND_NAME}"
    assert_output --partial 'Successfully pushed'
    assert_output --partial "Description for ${P_NAME}.yml updated."

    local V1_SHA256="44ebe00783ae397562e3a9ef099249bd9f6b3cd8c01daff46618e85420f59c37"
    local MCI_SHA256="2ba50085b4db59b2103ecb15526b3f2317d49a61bddd2bc28af67bd17e584068"

    # Test-case: push a docker-compose with compatibilities defined.
    run torizoncore-builder platform push  --credentials "${CREDS_PROD_ZIP}" \
        --compatible-with "sha256=${V1_SHA256}" --compatible-with "sha256=${MCI_SHA256}" \
        --package-version "$(date +'%H%M%S')" "${CANON_DIR}/${GOOD_YML}.lock.yml"
    assert_success
    assert_output --partial "Package v1 with version"
    assert_output --partial "Package my_custom_image with version"
}

@test "platform push: test push with TorizonCore images" {
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

@test "platform lockbox: test advanced registry access" {
    skip-no-ota-credentials
    local CREDS_PROD_ZIP=$(decrypt-credentials-file "$SAMPLES_DIR/credentials/credentials-prod.zip.enc")
    local if_ci=""
    local SR_COMPOSE_FOLDER="${SAMPLES_DIR}/compose/secure-registry"

    if [ "${TCB_UNDER_CI}" = "1" ]; then
        if_ci="1"
    fi

    run check-registries
    assert_success

    run torizoncore-builder platform lockbox \
        --credentials "${CREDS_PROD_ZIP}"  \
        --cacert-to "${SR_NO_AUTH_IP}" "${SR_NO_AUTH_CERTS}/cacert.crt" \
        --login-to "${SR_WITH_AUTH_IP}" toradex test \
        --cacert-to "${SR_WITH_AUTH_IP}" "${SR_WITH_AUTH_CERTS}/cacert.crt" \
        --force LockBox-Test \
        ${if_ci:+"--login" "$CI_DOCKER_HUB_PULL_USER"
                           "$CI_DOCKER_HUB_PULL_PASSWORD"}
    assert_success
}
