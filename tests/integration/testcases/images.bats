bats_load_library 'bats/bats-support/load.bash'
bats_load_library 'bats/bats-assert/load.bash'
bats_load_library 'bats/bats-file/load.bash'

@test "images: check help output" {
    run torizoncore-builder images --help
    assert_success
    assert_output --partial ' {download,provision,serve,unpack}'
}

@test "images provision: basic offline-provisioning (standalone)" {
    unpack-image "$DEFAULT_TEZI_IMAGE"
    local INPUT_IMAGE_DIR=$(echo $DEFAULT_TEZI_IMAGE | sed 's/\.tar$//g')
    local OUTPUT_IMAGE_DIR="${INPUT_IMAGE_DIR}.PROV"

    # case: no arguments passed
    run torizoncore-builder images provision
    assert_failure
    assert_output --partial \
        'the following arguments are required: INPUT_DIRECTORY, OUTPUT_DIRECTORY, --mode'

    # case: wrong arguments
    rm -fr "${OUTPUT_IMAGE_DIR}"
    run torizoncore-builder images provision \
        --mode=offline "$INPUT_IMAGE_DIR" "$OUTPUT_IMAGE_DIR"
    assert_failure
    assert_output --partial 'switch --shared-data must be passed'

    # case: wrong arguments
    rm -fr "${OUTPUT_IMAGE_DIR}"
    run torizoncore-builder images provision \
        --shared-data "${SAMPLES_DIR}/provision/shared-data.tar.gz" \
        --online-data "eyJkdW1teSI6MX0K" \
        --mode=offline "$INPUT_IMAGE_DIR" "$OUTPUT_IMAGE_DIR"
    assert_failure
    assert_output --partial 'switch --online-data cannot be passed'

    # case: output directory exists
    mkdir -p "${OUTPUT_IMAGE_DIR}"
    run torizoncore-builder images provision \
        --shared-data "${SAMPLES_DIR}/provision/shared-data.tar.gz" \
        --mode=offline "$INPUT_IMAGE_DIR" "$OUTPUT_IMAGE_DIR"
    assert_failure
    assert_output --partial 'already exists: aborting'

    # case: success
    rm -fr "${OUTPUT_IMAGE_DIR}"
    run torizoncore-builder images provision \
        --shared-data "${SAMPLES_DIR}/provision/shared-data.tar.gz" \
        --mode=offline "$INPUT_IMAGE_DIR" "$OUTPUT_IMAGE_DIR"
    assert_success
    assert_output --partial 'Image successfully provisioned'

    run cat "${OUTPUT_IMAGE_DIR}/image.json"
    assert_output --partial 'provisioning-data.tar.gz:/ostree/deploy/torizon/var/sota/:true'

    # case: success, with --hibernated option ignored
    rm -fr "${OUTPUT_IMAGE_DIR}"
    run torizoncore-builder images provision \
        --shared-data "${SAMPLES_DIR}/provision/shared-data.tar.gz" \
        --hibernated \
        --mode=offline "$INPUT_IMAGE_DIR" "$OUTPUT_IMAGE_DIR"
    assert_success
    assert_output --partial "--hibernated is specific to online provisioning. Ignoring."
    assert_output --partial 'Image successfully provisioned'

    run cat "${OUTPUT_IMAGE_DIR}/image.json"
    assert_output --partial 'provisioning-data.tar.gz:/ostree/deploy/torizon/var/sota/:true'

    # check if uncompressed_size field was updated correctly:
    # we are using 'bc' here due to the floating point calculations.
    local ORG_SIZE=$(cat ${INPUT_IMAGE_DIR}/image.json  | sed -Ene 's/^.*"uncompressed_size" *: *([0-9]+(\.[0-9]*))?.*$/\1/gp')
    local NEW_SIZE=$(cat ${OUTPUT_IMAGE_DIR}/image.json | sed -Ene 's/^.*"uncompressed_size" *: *([0-9]+(\.[0-9]*))?.*$/\1/gp')

    local CORRECT_DELTA_BYTES=$(cat "${OUTPUT_IMAGE_DIR}/provisioning-data.tar.gz" | gzip -dc | wc -c)
    local CORRECT_DELTA=$(echo "scale=9; $CORRECT_DELTA_BYTES / 1024 / 1024" | bc)
    local ACTUAL_DELTA=$(echo "$NEW_SIZE - $ORG_SIZE" | bc)
    local SIZE_ERROR=$(echo "$ACTUAL_DELTA - $CORRECT_DELTA" | bc)
    local SIZE_STATUS=$(echo "-0.01 < $SIZE_ERROR && $SIZE_ERROR < 0.01" | bc)
    #echo "$ORG_SIZE; $NEW_SIZE; $ACTUAL_DELTA ?= $CORRECT_DELTA; $CORRECT_DELTA_BYTES; $SIZE_ERROR" >&3

    assert_equal "$SIZE_STATUS" "1"

    rm -fr "${OUTPUT_IMAGE_DIR}"
}

@test "images provision: basic offline-provisioning (\"build\" command)" {
    unpack-image "$DEFAULT_TEZI_IMAGE"
    local INPUT_IMAGE_DIR=$(echo $DEFAULT_TEZI_IMAGE | sed 's/\.tar$//g')
    local OUTPUT_IMAGE_DIR="${INPUT_IMAGE_DIR}.PROV"

    # case: missing properties
    rm -fr "${OUTPUT_IMAGE_DIR}"
    run torizoncore-builder build \
        --file "${SAMPLES_DIR}/provision/tcbuild-offline-error1.yml" \
        --set INPUT_DIR="$INPUT_IMAGE_DIR" \
        --set OUTPUT_DIR="$OUTPUT_IMAGE_DIR" \
        --set SHARED_DATA_TARBALL="${SAMPLES_DIR}/provision/shared-data.tar.gz"
    assert_failure
    assert_output --partial "property 'shared-data' must be set"

    # case: extraneous properties
    rm -fr "${OUTPUT_IMAGE_DIR}"
    run torizoncore-builder build \
        --file "${SAMPLES_DIR}/provision/tcbuild-offline-error2.yml" \
        --set INPUT_DIR="$INPUT_IMAGE_DIR" \
        --set OUTPUT_DIR="$OUTPUT_IMAGE_DIR" \
        --set SHARED_DATA_TARBALL="${SAMPLES_DIR}/provision/shared-data.tar.gz"
    assert_failure
    assert_output --partial "property 'online-data' cannot be set"

    # case: all good
    rm -fr "${OUTPUT_IMAGE_DIR}"
    run torizoncore-builder build \
        --file "${SAMPLES_DIR}/provision/tcbuild-offline-basic.yml" \
        --set INPUT_DIR="$INPUT_IMAGE_DIR" \
        --set OUTPUT_DIR="$OUTPUT_IMAGE_DIR" \
        --set SHARED_DATA_TARBALL="${SAMPLES_DIR}/provision/shared-data.tar.gz"
    assert_success
    assert_output --partial "Image successfully provisioned"

    run cat "${OUTPUT_IMAGE_DIR}/image.json"
    assert_output --partial 'provisioning-data.tar.gz:/ostree/deploy/torizon/var/sota/:true'

    rm -fr "${OUTPUT_IMAGE_DIR}"
}

@test "images provision: basic online-provisioning" {
    unpack-image "$DEFAULT_TEZI_IMAGE"
    local INPUT_IMAGE_DIR=$(echo $DEFAULT_TEZI_IMAGE | sed 's/\.tar$//g')
    local OUTPUT_IMAGE_DIR="${INPUT_IMAGE_DIR}.PROV"

    # case: no arguments passed
    run torizoncore-builder images provision
    assert_failure
    assert_output --partial \
        'the following arguments are required: INPUT_DIRECTORY, OUTPUT_DIRECTORY, --mode'

    # case: wrong arguments
    rm -fr "${OUTPUT_IMAGE_DIR}"
    run torizoncore-builder images provision \
        --mode=online "$INPUT_IMAGE_DIR" "$OUTPUT_IMAGE_DIR"
    assert_failure
    assert_output --partial 'switches --shared-data and --online-data must be passed'

    # case: wrong arguments
    rm -fr "${OUTPUT_IMAGE_DIR}"
    run torizoncore-builder images provision \
        --shared-data "${SAMPLES_DIR}/provision/shared-data.tar.gz" \
        --mode=online "$INPUT_IMAGE_DIR" "$OUTPUT_IMAGE_DIR"
    assert_failure
    assert_output --partial 'switches --shared-data and --online-data must be passed'

    # case: output directory exists
    mkdir -p "${OUTPUT_IMAGE_DIR}"
    run torizoncore-builder images provision \
        --shared-data "${SAMPLES_DIR}/provision/shared-data.tar.gz" \
        --online-data "eyJkdW1teSI6MX0K" \
        --mode=online "$INPUT_IMAGE_DIR" "$OUTPUT_IMAGE_DIR"
    assert_failure
    assert_output --partial 'already exists: aborting'

    # case: success
    rm -fr "${OUTPUT_IMAGE_DIR}"
    run torizoncore-builder images provision \
        --shared-data "${SAMPLES_DIR}/provision/shared-data.tar.gz" \
        --online-data "eyJkdW1teSI6MX0K" \
        --mode=online "$INPUT_IMAGE_DIR" "$OUTPUT_IMAGE_DIR"
    assert_success
    assert_output --partial 'Image successfully provisioned'

    run cat "${OUTPUT_IMAGE_DIR}/image.json"
    assert_output --partial 'provisioning-data.tar.gz:/ostree/deploy/torizon/var/sota/:true'

    # case: success with --hibernated option enabled
    rm -fr "${OUTPUT_IMAGE_DIR}"
    run torizoncore-builder images provision \
        --shared-data "${SAMPLES_DIR}/provision/shared-data.tar.gz" \
        --online-data "eyJkdW1teSI6MX0K" \
        --hibernated \
        --mode=online "$INPUT_IMAGE_DIR" "$OUTPUT_IMAGE_DIR"
    assert_success
    assert_output --partial 'Adding hibernated mode flag'
    assert_output --partial 'Image successfully provisioned'

    run cat "${OUTPUT_IMAGE_DIR}/image.json"
    assert_output --partial 'provisioning-data.tar.gz:/ostree/deploy/torizon/var/sota/:true'
    tar -xf "${OUTPUT_IMAGE_DIR}/provisioning-data.tar.gz"
    run cat "auto-provisioning.json"
    assert_output --partial '"hibernated": true'

    # check if uncompressed_size field was updated correctly:
    # we are using 'bc' here due to the floating point calculations.
    local ORG_SIZE=$(cat ${INPUT_IMAGE_DIR}/image.json  | sed -Ene 's/^.*"uncompressed_size" *: *([0-9]+(\.[0-9]*))?.*$/\1/gp')
    local NEW_SIZE=$(cat ${OUTPUT_IMAGE_DIR}/image.json | sed -Ene 's/^.*"uncompressed_size" *: *([0-9]+(\.[0-9]*))?.*$/\1/gp')

    local CORRECT_DELTA_BYTES=$(cat "${OUTPUT_IMAGE_DIR}/provisioning-data.tar.gz" | gzip -dc | wc -c)
    local CORRECT_DELTA=$(echo "scale=9; $CORRECT_DELTA_BYTES / 1024 / 1024" | bc)
    local ACTUAL_DELTA=$(echo "$NEW_SIZE - $ORG_SIZE" | bc)
    local SIZE_ERROR=$(echo "$ACTUAL_DELTA - $CORRECT_DELTA" | bc)
    local SIZE_STATUS=$(echo "-0.01 < $SIZE_ERROR && $SIZE_ERROR < 0.01" | bc)
    #echo "$ORG_SIZE; $NEW_SIZE; $ACTUAL_DELTA ?= $CORRECT_DELTA; $CORRECT_DELTA_BYTES; $SIZE_ERROR" >&3

    assert_equal "$SIZE_STATUS" "1"

    rm -fr "${OUTPUT_IMAGE_DIR}"
}

@test "images provision: basic online-provisioning (\"build\" command)" {
    unpack-image "$DEFAULT_TEZI_IMAGE"
    local INPUT_IMAGE_DIR=$(echo $DEFAULT_TEZI_IMAGE | sed 's/\.tar$//g')
    local OUTPUT_IMAGE_DIR="${INPUT_IMAGE_DIR}.PROV"

    # case: missing properties
    rm -fr "${OUTPUT_IMAGE_DIR}"
    run torizoncore-builder build \
        --file "${SAMPLES_DIR}/provision/tcbuild-online-error1.yml" \
        --set INPUT_DIR="$INPUT_IMAGE_DIR" \
        --set OUTPUT_DIR="$OUTPUT_IMAGE_DIR" \
        --set SHARED_DATA_TARBALL="${SAMPLES_DIR}/provision/shared-data.tar.gz"
    assert_failure
    assert_output --partial "properties 'shared-data' and 'online-data' must be set."

    # case: extraneous properties
    rm -fr "${OUTPUT_IMAGE_DIR}"
    run torizoncore-builder build \
        --file "${SAMPLES_DIR}/provision/tcbuild-online-error2.yml" \
        --set INPUT_DIR="$INPUT_IMAGE_DIR" \
        --set OUTPUT_DIR="$OUTPUT_IMAGE_DIR" \
        --set SHARED_DATA_TARBALL="${SAMPLES_DIR}/provision/shared-data.tar.gz"
    assert_failure
    assert_output --partial "properties 'shared-data' and 'online-data' must be set."

    # case: all good
    rm -fr "${OUTPUT_IMAGE_DIR}"
    run torizoncore-builder build \
        --file "${SAMPLES_DIR}/provision/tcbuild-online-basic.yml" \
        --set INPUT_DIR="$INPUT_IMAGE_DIR" \
        --set OUTPUT_DIR="$OUTPUT_IMAGE_DIR" \
        --set SHARED_DATA_TARBALL="${SAMPLES_DIR}/provision/shared-data.tar.gz"
    assert_success
    assert_output --partial "Image successfully provisioned"

    run cat "${OUTPUT_IMAGE_DIR}/image.json"
    assert_output --partial 'provisioning-data.tar.gz:/ostree/deploy/torizon/var/sota/:true'

    # case: disabled
    rm -fr "${OUTPUT_IMAGE_DIR}"
    run torizoncore-builder build \
        --file "${SAMPLES_DIR}/provision/tcbuild-online-disabled.yml" \
        --set INPUT_DIR="$INPUT_IMAGE_DIR" \
        --set OUTPUT_DIR="$OUTPUT_IMAGE_DIR" \
        --set SHARED_DATA_TARBALL="${SAMPLES_DIR}/provision/shared-data.tar.gz"
    assert_success

    run cat "${OUTPUT_IMAGE_DIR}/image.json"
    refute_output --partial 'provisioning-data.tar.gz:/ostree/deploy/torizon/var/sota/:true'

    rm -fr "${OUTPUT_IMAGE_DIR}"
}

@test "images provision: add containers to provisioned image" {
    unpack-image "$DEFAULT_TEZI_IMAGE"
    local INPUT_IMAGE_DIR=$(echo $DEFAULT_TEZI_IMAGE | sed 's/\.tar$//g')
    local OUTPUT_IMAGE_DIR="${INPUT_IMAGE_DIR}.PROV"

    # prepare image:
    rm -fr "${OUTPUT_IMAGE_DIR}"
    run torizoncore-builder images provision \
        --shared-data "${SAMPLES_DIR}/provision/shared-data.tar.gz" \
        --mode=offline "$INPUT_IMAGE_DIR" "$OUTPUT_IMAGE_DIR"
    assert_success
    assert_output --partial 'Image successfully provisioned'

    local INPUT_IMAGE_DIR="$OUTPUT_IMAGE_DIR"
    local OUTPUT_IMAGE_DIR="${OUTPUT_IMAGE_DIR}.CONT"

    # actual test:
    rm -fr "${OUTPUT_IMAGE_DIR}"
    run torizoncore-builder combine \
        --bundle-directory "${SAMPLES_DIR}/bundles/hello/" \
        "$INPUT_IMAGE_DIR" "$OUTPUT_IMAGE_DIR"
    assert_success

    run cat "${OUTPUT_IMAGE_DIR}/image.json"
    assert_output --partial 'docker-compose.yml:/ostree/deploy/torizon/var/sota/storage/docker-compose'
    assert_output --partial 'docker-storage.tar.xz:/ostree/deploy/torizon/var/lib/docker/:true'
    assert_output --partial 'provisioning-data.tar.gz:/ostree/deploy/torizon/var/sota/:true'
    assert_output --regexp '"version".*\.container'
}

@test "images provision: provision image already having containers" {
    unpack-image "$DEFAULT_TEZI_IMAGE"
    local INPUT_IMAGE_DIR=$(echo $DEFAULT_TEZI_IMAGE | sed 's/\.tar$//g')
    local OUTPUT_IMAGE_DIR="${INPUT_IMAGE_DIR}.CONT"

    # prepare image:
    rm -fr "${OUTPUT_IMAGE_DIR}"
    run torizoncore-builder combine \
        --bundle-directory "${SAMPLES_DIR}/bundles/hello/" \
        "$INPUT_IMAGE_DIR" "$OUTPUT_IMAGE_DIR"
    assert_success

    local INPUT_IMAGE_DIR="$OUTPUT_IMAGE_DIR"
    local OUTPUT_IMAGE_DIR="${OUTPUT_IMAGE_DIR}.PROV"

    # actual test:
    rm -fr "${OUTPUT_IMAGE_DIR}"
    run torizoncore-builder images provision \
        --shared-data "${SAMPLES_DIR}/provision/shared-data.tar.gz" \
        --mode=offline "$INPUT_IMAGE_DIR" "$OUTPUT_IMAGE_DIR"
    assert_success
    assert_output --partial 'Image successfully provisioned'

    run cat "${OUTPUT_IMAGE_DIR}/image.json"
    assert_output --partial 'docker-compose.yml:/ostree/deploy/torizon/var/sota/storage/docker-compose'
    assert_output --partial 'docker-storage.tar.xz:/ostree/deploy/torizon/var/lib/docker/:true'
    assert_output --partial 'provisioning-data.tar.gz:/ostree/deploy/torizon/var/sota/:true'
    assert_output --regexp '"version".*\.container'
}

@test "images provision: customize image already provisioned" {
    unpack-image "$DEFAULT_TEZI_IMAGE"
    local INPUT_IMAGE_DIR=$(echo $DEFAULT_TEZI_IMAGE | sed 's/\.tar$//g')
    local OUTPUT_IMAGE_DIR="${INPUT_IMAGE_DIR}.PROV"

    # prepare image:
    rm -fr "${OUTPUT_IMAGE_DIR}"
    run torizoncore-builder images provision \
        --shared-data "${SAMPLES_DIR}/provision/shared-data.tar.gz" \
        --mode=offline "$INPUT_IMAGE_DIR" "$OUTPUT_IMAGE_DIR"
    assert_success
    assert_output --partial 'Image successfully provisioned'

    local INPUT_IMAGE_DIR="$OUTPUT_IMAGE_DIR"
    local OUTPUT_IMAGE_DIR="${OUTPUT_IMAGE_DIR}.CUST"

    # case: all good
    rm -fr "${OUTPUT_IMAGE_DIR}"
    run torizoncore-builder build \
        --file "${SAMPLES_DIR}/provision/tcbuild-custom-description.yml" \
        --set INPUT_DIR="$INPUT_IMAGE_DIR" \
        --set OUTPUT_DIR="$OUTPUT_IMAGE_DIR"
    assert_success

    run cat "${OUTPUT_IMAGE_DIR}/image.json"
    assert_output --partial 'provisioning-data.tar.gz:/ostree/deploy/torizon/var/sota/:true'
    assert_output --regexp '"description".*"my custom image"'
    assert_output --regexp '"version".*\.modified'
}
