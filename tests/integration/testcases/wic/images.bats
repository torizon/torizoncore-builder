bats_load_library 'bats/bats-support/load.bash'
bats_load_library 'bats/bats-assert/load.bash'
bats_load_library 'bats/bats-file/load.bash'

@test "images: check help output" {
    run torizoncore-builder images --help
    assert_success
    assert_output --partial ' {download,provision,serve,unpack}'
}

@test "images provision: basic offline-provisioning (standalone)" {
    local INPUT_IMAGE="$DEFAULT_WIC_IMAGE"
    local OUTPUT_IMAGE="$(echo "$DEFAULT_WIC_IMAGE" | sed 's/\.wic\|\.img$//g').PROV.img"

    # case: no arguments passed
    run torizoncore-builder images provision
    assert_failure
    assert_output --partial \
        'the following arguments are required: INPUT_PATH, OUTPUT_PATH, --mode'

    # case: wrong arguments
    rm -fr "${OUTPUT_IMAGE}"
    run torizoncore-builder images provision \
        --mode=offline "$INPUT_IMAGE" "$OUTPUT_IMAGE"
    assert_failure
    assert_output --partial 'switch --shared-data must be passed'

    # case: wrong arguments
    rm -fr "${OUTPUT_IMAGE}"
    run torizoncore-builder images provision \
        --shared-data "${SAMPLES_DIR}/provision/shared-data.tar.gz" \
        --online-data "eyJkdW1teSI6MX0K" \
        --mode=offline "$INPUT_IMAGE" "$OUTPUT_IMAGE"
    assert_failure
    assert_output --partial 'switch --online-data cannot be passed'

    # case: output exists
    touch "${OUTPUT_IMAGE}"
    run torizoncore-builder images provision \
        --shared-data "${SAMPLES_DIR}/provision/shared-data.tar.gz" \
        --mode=offline "$INPUT_IMAGE" "$OUTPUT_IMAGE"
    assert_failure
    assert_output --partial 'already exists. Aborting'
    rm -f "${OUTPUT_IMAGE}"

    # case: output is a directory
    mkdir -p "${OUTPUT_IMAGE}"
    run torizoncore-builder images provision \
        --shared-data "${SAMPLES_DIR}/provision/shared-data.tar.gz" \
        --mode=offline "$INPUT_IMAGE" "$OUTPUT_IMAGE"
    assert_failure
    assert_output --partial "For raw images the output can't be a directory"

    # case: success
    rm -fr "${OUTPUT_IMAGE}"
    run torizoncore-builder images provision \
        --shared-data "${SAMPLES_DIR}/provision/shared-data.tar.gz" \
        --mode=offline "$INPUT_IMAGE" "$OUTPUT_IMAGE"
    assert_success
    assert_output --partial 'Image successfully provisioned'

    # case: success, with --hibernated option ignored
    rm -fr "${OUTPUT_IMAGE}"
    run torizoncore-builder images provision \
        --shared-data "${SAMPLES_DIR}/provision/shared-data.tar.gz" \
        --hibernated \
        --mode=offline "$INPUT_IMAGE" "$OUTPUT_IMAGE"
    assert_success
    assert_output --partial "--hibernated is specific to online provisioning. Ignoring."
    assert_output --partial 'Hibernation Mode is deprecated'
    assert_output --partial 'Image successfully provisioned'

    # case: success, with --fleet option ignored
    rm -fr "${OUTPUT_IMAGE}"
    run torizoncore-builder images provision \
        --shared-data "${SAMPLES_DIR}/provision/shared-data.tar.gz" \
        --fleet "4a83db78-b746-4685-9ccd-ba566d1a012b" \
        --mode=offline "$INPUT_IMAGE" "$OUTPUT_IMAGE"
    assert_success
    assert_output --partial "--fleet is specific to online provisioning. Ignoring."
    assert_output --partial 'Image successfully provisioned'

    rm -fr "${OUTPUT_IMAGE}"
}

@test "images provision: basic offline-provisioning (\"build\" command)" {
    local INPUT_IMAGE="$DEFAULT_WIC_IMAGE"
    local OUTPUT_IMAGE="$(echo "$DEFAULT_WIC_IMAGE" | sed 's/\.wic\|\.img$//g').PROV.img"

    # case: missing properties
    rm -fr "${OUTPUT_IMAGE}"
    cp "${SAMPLES_DIR}/provision/tcbuild-offline-error1.yml" "tcbuild-offline-error1.yml"
    sed -i 's/easy-installer:/raw-image:/g' "tcbuild-offline-error1.yml"

    run torizoncore-builder build \
        --file "tcbuild-offline-error1.yml" \
        --set INPUT_DIR="$INPUT_IMAGE" \
        --set OUTPUT_DIR="$OUTPUT_IMAGE" \
        --set SHARED_DATA_TARBALL="${SAMPLES_DIR}/provision/shared-data.tar.gz"
    assert_failure
    assert_output --partial "property 'shared-data' must be set"

    # case: extraneous properties
    rm -fr "${OUTPUT_IMAGE}"
    cp "${SAMPLES_DIR}/provision/tcbuild-offline-error2.yml" "tcbuild-offline-error2.yml"
    sed -i 's/easy-installer:/raw-image:/g' "tcbuild-offline-error2.yml"
    run torizoncore-builder build \
        --file "tcbuild-offline-error2.yml" \
        --set INPUT_DIR="$INPUT_IMAGE" \
        --set OUTPUT_DIR="$OUTPUT_IMAGE" \
        --set SHARED_DATA_TARBALL="${SAMPLES_DIR}/provision/shared-data.tar.gz"
    assert_failure
    assert_output --partial "property 'online-data' cannot be set"

    # case: all good
    rm -fr "${OUTPUT_IMAGE}"
    cp "${SAMPLES_DIR}/provision/tcbuild-offline-basic.yml" "tcbuild-offline-basic.yml"
    sed -i 's/easy-installer:/raw-image:/g' "tcbuild-offline-basic.yml"
    run torizoncore-builder build \
        --file "tcbuild-offline-basic.yml" \
        --set INPUT_DIR="$INPUT_IMAGE" \
        --set OUTPUT_DIR="$OUTPUT_IMAGE" \
        --set SHARED_DATA_TARBALL="${SAMPLES_DIR}/provision/shared-data.tar.gz"
    assert_success
    assert_output --partial "Image successfully provisioned"

    rm -fr "${OUTPUT_IMAGE}"
}

@test "images provision: basic online-provisioning" {
    local INPUT_IMAGE="$DEFAULT_WIC_IMAGE"
    local OUTPUT_IMAGE="$(echo "$DEFAULT_WIC_IMAGE" | sed 's/\.wic\|\.img$//g').PROV.img"

    # case: no arguments passed
    run torizoncore-builder images provision
    assert_failure
    assert_output --partial \
        'the following arguments are required: INPUT_PATH, OUTPUT_PATH, --mode'

    # case: wrong arguments
    rm -fr "${OUTPUT_IMAGE}"
    run torizoncore-builder images provision \
        --mode=online "$INPUT_IMAGE" "$OUTPUT_IMAGE"
    assert_failure
    assert_output --partial 'switches --shared-data and --online-data must be passed'

    # case: wrong arguments
    rm -fr "${OUTPUT_IMAGE}"
    run torizoncore-builder images provision \
        --shared-data "${SAMPLES_DIR}/provision/shared-data.tar.gz" \
        --mode=online "$INPUT_IMAGE" "$OUTPUT_IMAGE"
    assert_failure
    assert_output --partial 'switches --shared-data and --online-data must be passed'

    # case: output exists
    touch "${OUTPUT_IMAGE}"
    run torizoncore-builder images provision \
        --shared-data "${SAMPLES_DIR}/provision/shared-data.tar.gz" \
        --online-data "eyJkdW1teSI6MX0K" \
        --mode=online "$INPUT_IMAGE" "$OUTPUT_IMAGE"
    assert_failure
    assert_output --partial 'already exists. Aborting'
    rm -f "${OUTPUT_IMAGE}"

    # case: output is a directory
    mkdir -p "${OUTPUT_IMAGE}"
    run torizoncore-builder images provision \
        --shared-data "${SAMPLES_DIR}/provision/shared-data.tar.gz" \
        --online-data "eyJkdW1teSI6MX0K" \
        --mode=online "$INPUT_IMAGE" "$OUTPUT_IMAGE"
    assert_failure
    assert_output --partial "For raw images the output can't be a directory"

    # case: success
    rm -fr "${OUTPUT_IMAGE}"
    run torizoncore-builder images provision \
        --shared-data "${SAMPLES_DIR}/provision/shared-data.tar.gz" \
        --online-data "eyJkdW1teSI6MX0K" \
        --mode=online "$INPUT_IMAGE" "$OUTPUT_IMAGE"
    assert_success
    assert_output --partial 'Image successfully provisioned'

    # case: success with --hibernated option enabled
    rm -fr "${OUTPUT_IMAGE}"
    run torizoncore-builder images provision \
        --shared-data "${SAMPLES_DIR}/provision/shared-data.tar.gz" \
        --online-data "eyJkdW1teSI6MX0K" \
        --hibernated \
        --mode=online "$INPUT_IMAGE" "$OUTPUT_IMAGE"
    assert_success
    assert_output --partial 'Hibernation Mode is deprecated'
    assert_output --partial 'Adding hibernated mode flag'
    assert_output --partial 'Image successfully provisioned'

    # case: error with --fleet option, malformed uuid
    rm -fr "${OUTPUT_IMAGE}"
    run torizoncore-builder images provision \
        --shared-data "${SAMPLES_DIR}/provision/shared-data.tar.gz" \
        --online-data "eyJkdW1teSI6MX0K" \
        --fleet "foo" \
        --mode=online "$INPUT_IMAGE" "$OUTPUT_IMAGE"
    assert_failure
    assert_output --partial 'do not appear to be a UUID'

    # case: success with --fleet option enabled
    rm -fr "${OUTPUT_IMAGE}"
    run torizoncore-builder images provision \
        --shared-data "${SAMPLES_DIR}/provision/shared-data.tar.gz" \
        --online-data "eyJkdW1teSI6MX0K" \
        --fleet "4a83db78-b746-4685-9ccd-ba566d1a012b" \
        --mode=online "$INPUT_IMAGE" "$OUTPUT_IMAGE"
    assert_success
    assert_output --partial 'Adding fleet UUID'
    assert_output --partial 'Image successfully provisioned'

    rm -fr "${OUTPUT_IMAGE}"
}

@test "images provision: basic online-provisioning (\"build\" command)" {
    local INPUT_IMAGE="$DEFAULT_WIC_IMAGE"
    local OUTPUT_IMAGE="$(echo "$DEFAULT_WIC_IMAGE" | sed 's/\.wic\|\.img$//g').PROV.img"

    # case: missing properties
    rm -fr "${OUTPUT_IMAGE}"
    cp "${SAMPLES_DIR}/provision/tcbuild-online-error1.yml" "tcbuild-online-error1.yml"
    sed -i 's/easy-installer:/raw-image:/g' "tcbuild-online-error1.yml"
    run torizoncore-builder build \
        --file "tcbuild-online-error1.yml" \
        --set INPUT_DIR="$INPUT_IMAGE" \
        --set OUTPUT_DIR="$OUTPUT_IMAGE" \
        --set SHARED_DATA_TARBALL="${SAMPLES_DIR}/provision/shared-data.tar.gz"
    assert_failure
    assert_output --partial "properties 'shared-data' and 'online-data' must be set."

    # case: extraneous properties
    rm -fr "${OUTPUT_IMAGE}"
    cp "${SAMPLES_DIR}/provision/tcbuild-online-error2.yml" "tcbuild-online-error2.yml"
    sed -i 's/easy-installer:/raw-image:/g' "tcbuild-online-error2.yml"
    run torizoncore-builder build \
        --file "tcbuild-online-error2.yml" \
        --set INPUT_DIR="$INPUT_IMAGE" \
        --set OUTPUT_DIR="$OUTPUT_IMAGE" \
        --set SHARED_DATA_TARBALL="${SAMPLES_DIR}/provision/shared-data.tar.gz"
    assert_failure
    assert_output --partial "properties 'shared-data' and 'online-data' must be set."

    # case: all good
    rm -fr "${OUTPUT_IMAGE}"
    cp "${SAMPLES_DIR}/provision/tcbuild-online-basic.yml" "tcbuild-online-basic.yml"
    sed -i 's/easy-installer:/raw-image:/g' "tcbuild-online-basic.yml"
    if [ "${DEFAULT_WIC_IMAGE_HAS_CFS_SUPPORT}" = "1" ]; then
        set-ostree-key-in-tcbuild \
            "tcbuild-online-basic.yml" \
            "name=cfs-dev;algo=ed25519" \
            "${SAMPLES_DIR}/signing_keys/ostree-good1/"
    fi
    run torizoncore-builder build \
        --file "tcbuild-online-basic.yml" \
        --set INPUT_DIR="$INPUT_IMAGE" \
        --set OUTPUT_DIR="$OUTPUT_IMAGE" \
        --set SHARED_DATA_TARBALL="${SAMPLES_DIR}/provision/shared-data.tar.gz"
    assert_success
    assert_output --partial "Image successfully provisioned"

    # case: disabled
    rm -fr "${OUTPUT_IMAGE}"
    cp "${SAMPLES_DIR}/provision/tcbuild-online-disabled.yml" "tcbuild-online-disabled.yml"
    sed -i 's/easy-installer:/raw-image:/g' "tcbuild-online-disabled.yml"
    run torizoncore-builder build \
        --file "tcbuild-online-disabled.yml" \
        --set INPUT_DIR="$INPUT_IMAGE" \
        --set OUTPUT_DIR="$OUTPUT_IMAGE" \
        --set SHARED_DATA_TARBALL="${SAMPLES_DIR}/provision/shared-data.tar.gz"
    assert_success

    rm -fr "${OUTPUT_IMAGE}"
}

@test "images provision: add containers to provisioned image" {
    local INPUT_IMAGE="$DEFAULT_WIC_IMAGE"
    local OUTPUT_IMAGE="$(echo "$DEFAULT_WIC_IMAGE" | sed 's/\.wic\|\.img$//g').PROV.img"

    # prepare image:
    rm -fr "${OUTPUT_IMAGE}"
    run torizoncore-builder images provision \
        --shared-data "${SAMPLES_DIR}/provision/shared-data.tar.gz" \
        --mode=offline "$INPUT_IMAGE" "$OUTPUT_IMAGE"
    assert_success
    assert_output --partial 'Image successfully provisioned'

    local INPUT_IMAGE="$OUTPUT_IMAGE"
    local OUTPUT_IMAGE="$(echo "$INPUT_IMAGE" | sed 's/\.wic\|\.img$//g').CONT.img"

    # actual test:
    rm -fr "${OUTPUT_IMAGE}"
    run torizoncore-builder combine \
        --bundle-directory "${SAMPLES_DIR}/bundles/hello/" \
        "$INPUT_IMAGE" "$OUTPUT_IMAGE"
    assert_success
    rm -fr "${INPUT_IMAGE}"
    rm -fr "${OUTPUT_IMAGE}"
}

@test "images provision: provision image already having containers" {
    local INPUT_IMAGE="$DEFAULT_WIC_IMAGE"
    local OUTPUT_IMAGE="$(echo "$INPUT_IMAGE" | sed 's/\.wic\|\.img$//g').CONT.img"

    # prepare image:
    rm -fr "${OUTPUT_IMAGE}"
    run torizoncore-builder combine \
        --bundle-directory "${SAMPLES_DIR}/bundles/hello/" \
        "$INPUT_IMAGE" "$OUTPUT_IMAGE"
    assert_success

    local INPUT_IMAGE="$OUTPUT_IMAGE"
    local OUTPUT_IMAGE="$(echo "$INPUT_IMAGE" | sed 's/\.wic\|\.img$//g').PROV.img"

    # actual test:
    rm -fr "${OUTPUT_IMAGE}"
    run torizoncore-builder images provision \
        --shared-data "${SAMPLES_DIR}/provision/shared-data.tar.gz" \
        --mode=offline "$INPUT_IMAGE" "$OUTPUT_IMAGE"
    assert_success
    assert_output --partial 'Image successfully provisioned'
    rm -fr "${INPUT_IMAGE}"
    rm -fr "${OUTPUT_IMAGE}"
}

@test "images provision: customize image already provisioned" {
    local INPUT_IMAGE="$DEFAULT_WIC_IMAGE"
    local OUTPUT_IMAGE="$(echo "$INPUT_IMAGE" | sed 's/\.wic\|\.img$//g').PROV.img"

    # prepare image:
    rm -fr "${OUTPUT_IMAGE}"
    run torizoncore-builder images provision \
        --shared-data "${SAMPLES_DIR}/provision/shared-data.tar.gz" \
        --mode=offline "$INPUT_IMAGE" "$OUTPUT_IMAGE"
    assert_success
    assert_output --partial 'Image successfully provisioned'

    local INPUT_IMAGE="$OUTPUT_IMAGE"
    local OUTPUT_IMAGE="$(echo "$INPUT_IMAGE" | sed 's/\.wic\|\.img$//g').CUST.img"

    # case: all good
    rm -fr "${OUTPUT_IMAGE}"
    cp "${SAMPLES_DIR}/config/wic-tcbuild-splash-customization.yaml" "wic-tcbuild-splash-customization.yaml"
    run torizoncore-builder build \
        --file "wic-tcbuild-splash-customization.yaml" \
        --set INPUT_IMAGE="$INPUT_IMAGE" \
        --set OUTPUT_FILE="$OUTPUT_IMAGE"
    assert_success
    rm -fr "${INPUT_IMAGE}"
    rm -fr "${OUTPUT_IMAGE}"
}
