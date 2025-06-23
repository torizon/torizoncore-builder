bats_load_library 'bats/bats-support/load.bash'
bats_load_library 'bats/bats-assert/load.bash'
bats_load_library 'bats/bats-file/load.bash'

setup_file() {
    KERNEL_SIGNING_SUPPORTED_MACHINES=$(torizoncore-builder secboot sign-kernel --help \
                                        | grep '^Currently supported machines:')
    if echo "${KERNEL_SIGNING_SUPPORTED_MACHINES}" | grep -q "${MACHINE}"; then
        IS_KERNEL_SIGNING_SUPPORTED="1"
    else
        IS_KERNEL_SIGNING_SUPPORTED="0"
    fi

    HAB_SIGNING_SUPPORTED_MACHINES=$(torizoncore-builder secboot sign-bootloader-hab --help \
                                     | grep '^Currently supported machines:')
    if echo "${HAB_SIGNING_SUPPORTED_MACHINES}" | grep -q "${MACHINE}"; then
        IS_HAB_SIGNING_SUPPORTED="1"
    else
        IS_HAB_SIGNING_SUPPORTED="0"
    fi

    SIGNING_KEYS_DIR="${SAMPLES_DIR}/signing_keys"
    KERNEL_KEY_DIR="${SIGNING_KEYS_DIR}/kernel_fitimage"
    KERNEL_KEY_NAME="test"
    KERNEL_KEY_ALGO="sha256,rsa2048"

    CST_DIRS="cst_dirs"
    CST_TARBALL="${SIGNING_KEYS_DIR}/${CST_DIRS}.tar.gz"
    CST_BINARIES_DIR="${CST_DIRS}/cst-3.4.1"
    unpack-image "${CST_TARBALL}"

    export IS_KERNEL_SIGNING_SUPPORTED
    export IS_HAB_SIGNING_SUPPORTED
    export KERNEL_KEY_DIR
    export KERNEL_KEY_NAME
    export KERNEL_KEY_ALGO
    export CST_DIRS
    export CST_BINARIES_DIR
}

@test "secboot: check help output" {
    run torizoncore-builder secboot --help
    assert_success
    assert_output --partial '{sign-kernel,sign-bootloader-hab}'
}

@test "secboot sign-kernel: check help output" {
    run torizoncore-builder secboot sign-kernel --help
    assert_success
    assert_output --partial "usage: torizoncore-builder secboot sign-kernel"
    assert_output --partial "Currently supported machines:"
}

@test "secboot sign-kernel: run without parameters" {
    run torizoncore-builder secboot sign-kernel
    assert_failure
    assert_output --partial \
        "the following arguments are required: INPUT_DIRECTORY, OUTPUT_DIRECTORY, --kernel-key-dir, --kernel-key"
}

@test "secboot sign-kernel: invalid parameters" {

    local INPUT_IMAGE_DIR="TEST_$(echo ${DEFAULT_TEZI_IMAGE} | sed 's/\.tar$//g')"
    local OUTPUT_IMAGE_DIR="SIGNED_${INPUT_IMAGE_DIR}"

    # create dummy input directory
    mkdir -p "${INPUT_IMAGE_DIR}"

    # non-existent input directory
    run torizoncore-builder secboot sign-kernel "foo" "${OUTPUT_IMAGE_DIR}" \
                                                --kernel-key-dir "${KERNEL_KEY_DIR}" \
                                                --kernel-key "name=${KERNEL_KEY_NAME};algo=${KERNEL_KEY_ALGO}"
    assert_failure
    assert_output --partial 'does not exist'

    # output directory already exists and --force was not passed
    mkdir -p "${OUTPUT_IMAGE_DIR}"
    run torizoncore-builder secboot sign-kernel "${INPUT_IMAGE_DIR}" "${OUTPUT_IMAGE_DIR}" \
                                                --kernel-key-dir "${KERNEL_KEY_DIR}" \
                                                --kernel-key "name=${KERNEL_KEY_NAME};algo=${KERNEL_KEY_ALGO}"
    assert_failure
    assert_output --partial 'already exists'
    rm -rf "${OUTPUT_IMAGE_DIR}"

    # --kernel-key-dir not specified
    run torizoncore-builder secboot sign-kernel "${INPUT_IMAGE_DIR}" "${OUTPUT_IMAGE_DIR}" \
                                                --kernel-key "name=${KERNEL_KEY_NAME};algo=${KERNEL_KEY_ALGO}"
    assert_failure
    assert_output --partial 'the following arguments are required: --kernel-key-dir'

    # --kernel-key not specified
    run torizoncore-builder secboot sign-kernel "${INPUT_IMAGE_DIR}" "${OUTPUT_IMAGE_DIR}" \
                                                --kernel-key-dir "${KERNEL_KEY_DIR}"
    assert_failure
    assert_output --partial 'the following arguments are required: --kernel-key'

    # non-existent kernel fitImage key directory
    run torizoncore-builder secboot sign-kernel "${INPUT_IMAGE_DIR}" "${OUTPUT_IMAGE_DIR}" \
                                                --kernel-key-dir "foo" \
                                                --kernel-key "name=${KERNEL_KEY_NAME};algo=${KERNEL_KEY_ALGO}"
    assert_failure
    assert_output --partial 'does not exist'

    # key name that does not match file in key directory
    run torizoncore-builder secboot sign-kernel "${INPUT_IMAGE_DIR}" "${OUTPUT_IMAGE_DIR}" \
                                                --kernel-key-dir "${KERNEL_KEY_DIR}" \
                                                --kernel-key "name=foo;algo=${KERNEL_KEY_ALGO}"
    assert_failure
    assert_output --partial 'Could not find'

    # Invalid --kernel-key format (comma instead of semicolon)
    run torizoncore-builder secboot sign-kernel "${INPUT_IMAGE_DIR}" "${OUTPUT_IMAGE_DIR}" \
                                                --kernel-key-dir "${KERNEL_KEY_DIR}" \
                                                --kernel-key "name=${KERNEL_KEY_NAME},algo=${KERNEL_KEY_ALGO}"
    assert_failure
    assert_output --partial '--kernel-key is not correctly formatted'

    # --kernel-key without name
    run torizoncore-builder secboot sign-kernel "${INPUT_IMAGE_DIR}" "${OUTPUT_IMAGE_DIR}" \
                                                --kernel-key-dir "${KERNEL_KEY_DIR}" \
                                                --kernel-key "algo=${KERNEL_KEY_ALGO}"
    assert_failure
    assert_output --partial "Could not find value of 'name' in --kernel-key"
}

@test "secboot sign-kernel: image with unsupported kernel format" {
    requires-supported-kernel-signing-machine

    unpack-image "${DEFAULT_TEZI_IMAGE}"
    local INPUT_IMAGE_DIR=$(echo ${DEFAULT_TEZI_IMAGE} | sed 's/\.tar$//g')
    local OUTPUT_IMAGE_DIR="SIGNED_${INPUT_IMAGE_DIR}"

    # unsigned Torizon Docker images have the kernel in Image.gz format
    run torizoncore-builder secboot sign-kernel "${INPUT_IMAGE_DIR}" "${OUTPUT_IMAGE_DIR}" \
                                                --kernel-key-dir "${KERNEL_KEY_DIR}" \
                                                --kernel-key "name=${KERNEL_KEY_NAME};algo=${KERNEL_KEY_ALGO}"
    assert_failure
    assert_output --partial 'Provided input image does not have the kernel in fitImage format'

    rm -rf "${INPUT_IMAGE_DIR}"
}

@test "secboot sign-kernel: unsupported machine" {

    unpack-image "${DEFAULT_TEZI_IMAGE}"
    local INPUT_IMAGE_DIR=$(echo ${DEFAULT_TEZI_IMAGE} | sed 's/\.tar$//g')
    local OUTPUT_IMAGE_DIR="SIGNED_${INPUT_IMAGE_DIR}"

    # change the U-Boot environment file to change the machine name to an invalid one
    UBOOT_ENV_FILE=$(cat "${INPUT_IMAGE_DIR}/image.json" \
                         | grep u_boot_env \
                         | sed 's/.*"u_boot_env": "\(.*\)",/\1/')
    sed -i 's/^board=/board=dummy-/' "${INPUT_IMAGE_DIR}/${UBOOT_ENV_FILE}"

    run torizoncore-builder secboot sign-kernel "${INPUT_IMAGE_DIR}" "${OUTPUT_IMAGE_DIR}" \
                                                --kernel-key-dir "${KERNEL_KEY_DIR}" \
                                                --kernel-key "name=${KERNEL_KEY_NAME};algo=${KERNEL_KEY_ALGO}"
    assert_failure
    assert_output --partial "TorizonCore Builder doesn't support signing the kernel of images for"
    rm -rf "${INPUT_IMAGE_DIR}"
}

@test "secboot sign-kernel: sign with test key" {

    requires-supported-kernel-signing-machine
    requires-signed-image

    unpack-image "${DEFAULT_SIGNED_TEZI_IMAGE}"
    local INPUT_IMAGE_DIR=$(echo ${DEFAULT_SIGNED_TEZI_IMAGE} | sed 's/\.tar$//g')
    local OUTPUT_IMAGE_DIR="SIGNED_${INPUT_IMAGE_DIR}"

    if [ -d  "${OUTPUT_IMAGE_DIR}" ]; then
        rm -rf "${OUTPUT_IMAGE_DIR}"
    fi
    # run without --force
    run torizoncore-builder secboot sign-kernel "${INPUT_IMAGE_DIR}" "${OUTPUT_IMAGE_DIR}" \
                                                --kernel-key-dir "${KERNEL_KEY_DIR}" \
                                                --kernel-key "name=${KERNEL_KEY_NAME};algo=${KERNEL_KEY_ALGO}"
    assert_success
    assert_output --partial "Updating fitImage configurations to be signed with key name: ${KERNEL_KEY_NAME}"
    assert_output --partial "Using ${KERNEL_KEY_ALGO} for the signing process"
    assert_output --partial 'Kernel fitImage signed successfully'
    assert_output --partial 'Copying signed kernel fitImage to image rootfs'
    assert_output --partial 'Kernel in Torizon OS image signed successfully'

    # run with --force
    run torizoncore-builder secboot sign-kernel "${INPUT_IMAGE_DIR}" "${OUTPUT_IMAGE_DIR}" \
                                                --kernel-key-dir "${KERNEL_KEY_DIR}" \
                                                --kernel-key "name=${KERNEL_KEY_NAME};algo=${KERNEL_KEY_ALGO}" \
                                                --force
    assert_success
    assert_output --partial "Updating fitImage configurations to be signed with key name: ${KERNEL_KEY_NAME}"
    assert_output --partial "Using ${KERNEL_KEY_ALGO} for the signing process"
    assert_output --partial 'Kernel fitImage signed successfully'
    assert_output --partial 'Removing pre-existing directory'
    assert_output --partial 'Copying signed kernel fitImage to image rootfs'
    assert_output --partial 'Kernel in Torizon OS image signed successfully'

    # run with --force, --kernel-key parameters separated with space (should still work)
    run torizoncore-builder secboot sign-kernel "${INPUT_IMAGE_DIR}" "${OUTPUT_IMAGE_DIR}" \
                                                --kernel-key-dir "${KERNEL_KEY_DIR}" \
                                                --kernel-key "name = ${KERNEL_KEY_NAME}; algo = ${KERNEL_KEY_ALGO}" \
                                                --force
    assert_success
    assert_output --partial "Updating fitImage configurations to be signed with key name: ${KERNEL_KEY_NAME}"
    assert_output --partial "Using ${KERNEL_KEY_ALGO} for the signing process"
    assert_output --partial 'Kernel fitImage signed successfully'
    assert_output --partial 'Removing pre-existing directory'
    assert_output --partial 'Copying signed kernel fitImage to image rootfs'
    assert_output --partial 'Kernel in Torizon OS image signed successfully'

    # sign image in place
    run torizoncore-builder secboot sign-kernel "${OUTPUT_IMAGE_DIR}" "${OUTPUT_IMAGE_DIR}" \
                                                --kernel-key-dir "${KERNEL_KEY_DIR}" \
                                                --kernel-key "name=${KERNEL_KEY_NAME};algo=${KERNEL_KEY_ALGO}" \
                                                --force
    assert_success
    assert_output --partial "Updating fitImage configurations to be signed with key name: ${KERNEL_KEY_NAME}"
    assert_output --partial "Using ${KERNEL_KEY_ALGO} for the signing process"
    assert_output --partial 'Kernel fitImage signed successfully'
    assert_output --partial 'Updating Torizon OS image in place'
    assert_output --partial 'Copying signed kernel fitImage to image rootfs'
    assert_output --partial 'Kernel in Torizon OS image signed successfully'
}

@test "secboot sign-bootloader-hab: check help output" {
    run torizoncore-builder secboot sign-bootloader-hab --help
    assert_success
    assert_output --partial "usage: torizoncore-builder secboot sign-bootloader-hab"
    assert_output --partial "Currently supported machines:"
}

@test "secboot sign-bootloader-hab: run without parameters" {
    run torizoncore-builder secboot sign-bootloader-hab
    assert_failure
    assert_output --partial \
        "the following arguments are required: INPUT_DIRECTORY, OUTPUT_DIRECTORY, --cst-dir"
}

@test "secboot sign-bootloader-hab: invalid parameters" {

    local INPUT_IMAGE_DIR="TEST_$(echo ${DEFAULT_TEZI_IMAGE} | sed 's/\.tar$//g')"
    local OUTPUT_IMAGE_DIR="SIGNED_${INPUT_IMAGE_DIR}"
    local CST_DIR="${CST_DIRS}/hab/cst-3.4.1_tcb_test_rsa_2048"

    # create dummy input directory
    mkdir -p "${INPUT_IMAGE_DIR}"

    # non-existent input directory
    run torizoncore-builder secboot sign-bootloader-hab "foo" "${OUTPUT_IMAGE_DIR}" \
                                                        --cst-dir "${CST_DIR}" --cst-crypto rsa \
                                                        --cst-dig-algo sha256 --cst-srk-index 1
    assert_failure
    assert_output --partial 'does not exist'

    # output directory already exists and --force was not passed
    mkdir -p "${OUTPUT_IMAGE_DIR}"
    run torizoncore-builder secboot sign-bootloader-hab "${INPUT_IMAGE_DIR}" "${OUTPUT_IMAGE_DIR}" \
                                                        --cst-dir "${CST_DIR}" --cst-crypto rsa \
                                                        --cst-dig-algo sha256 --cst-srk-index 1
    assert_failure
    assert_output --partial 'already exists'
    rm -rf "${OUTPUT_IMAGE_DIR}"

    # non-existent kernel key directory
    run torizoncore-builder secboot sign-bootloader-hab "${INPUT_IMAGE_DIR}" "${OUTPUT_IMAGE_DIR}" \
                                                        --cst-dir "${CST_DIR}" --cst-crypto rsa \
                                                        --cst-dig-algo sha256 --cst-srk-index 1 \
                                                        --kernel-key-dir "foo" \
                                                        --kernel-key "name=${KERNEL_KEY_NAME};algo=${KERNEL_KEY_ALGO}"
    assert_failure
    assert_output --partial 'does not exist'

    # non-existent key with provided name
    run torizoncore-builder secboot sign-bootloader-hab "${INPUT_IMAGE_DIR}" "${OUTPUT_IMAGE_DIR}" \
                                                        --cst-dir "${CST_DIR}" --cst-crypto rsa \
                                                        --cst-dig-algo sha256 --cst-srk-index 1 \
                                                        --kernel-key-dir "${KERNEL_KEY_DIR}" \
                                                        --kernel-key "name=foo;algo=${KERNEL_KEY_ALGO}"
    assert_failure
    assert_output --partial 'Could not find'

    # Provide --kernel-key-dir but not --kernel-key
    run torizoncore-builder secboot sign-bootloader-hab "${INPUT_IMAGE_DIR}" "${OUTPUT_IMAGE_DIR}" \
                                                        --cst-dir "${CST_DIR}" --cst-crypto rsa \
                                                        --cst-dig-algo sha256 --cst-srk-index 1 \
                                                        --kernel-key-dir "${KERNEL_KEY_DIR}"
    assert_failure
    assert_output --partial '--kernel-key-dir was passed but --kernel-key was not'

    # Provide --kernel-key but not --kernel-key-dir
    run torizoncore-builder secboot sign-bootloader-hab "${INPUT_IMAGE_DIR}" "${OUTPUT_IMAGE_DIR}" \
                                                        --cst-dir "${CST_DIR}" --cst-crypto rsa \
                                                        --cst-dig-algo sha256 --cst-srk-index 1 \
                                                        --kernel-key "name=${KERNEL_KEY_NAME};algo=${KERNEL_KEY_ALGO}"
    assert_failure
    assert_output --partial '--kernel-key was passed but --kernel-key-dir was not'

    # invalid type of cryptographic keys
    run torizoncore-builder secboot sign-bootloader-hab "${INPUT_IMAGE_DIR}" "${OUTPUT_IMAGE_DIR}" \
                                                        --cst-dir "${CST_DIR}" \
                                                        --cst-crypto invalid_key_type
    assert_failure
    assert_output --partial 'argument --cst-crypto: invalid choice:'

    # invalid CST digest algorithm
    run torizoncore-builder secboot sign-bootloader-hab "${INPUT_IMAGE_DIR}" "${OUTPUT_IMAGE_DIR}" \
                                                        --cst-dir "${CST_DIR}" \
                                                        --cst-dig-algo invalid_dig_algo
    assert_failure
    assert_output --partial 'argument --cst-dig-algo: invalid choice:'

    # invalid SRK table index
    run torizoncore-builder secboot sign-bootloader-hab "${INPUT_IMAGE_DIR}" "${OUTPUT_IMAGE_DIR}" \
                                                        --cst-dir "${CST_DIR}" --cst-srk-index 0
    assert_failure
    assert_output --partial 'argument --cst-srk-index: invalid choice:'

    # delete dummy input directory
    rm -rf "${INPUT_IMAGE_DIR}"
}

@test "secboot sign-bootloader-hab: image with unsupported kernel format" {
    requires-supported-hab-signing-machine

    unpack-image "${DEFAULT_TEZI_IMAGE}"
    local INPUT_IMAGE_DIR=$(echo ${DEFAULT_TEZI_IMAGE} | sed 's/\.tar$//g')
    local OUTPUT_IMAGE_DIR="SIGNED_${INPUT_IMAGE_DIR}"
    local CST_DIR="${CST_DIRS}/hab/cst-3.4.1_tcb_test_rsa_2048"

    # unsigned Torizon Docker images have the kernel in Image.gz format
    run torizoncore-builder secboot sign-bootloader-hab "${INPUT_IMAGE_DIR}" "${OUTPUT_IMAGE_DIR}" \
                                                        --cst-dir "${CST_DIR}" --cst-crypto rsa \
                                                        --cst-key-size 2048 --cst-key-exp 65537 \
                                                        --cst-dig-algo sha256 --cst-srk-index 1
    assert_failure
    assert_output --partial 'Provided input image does not have the kernel in fitImage format'

    rm -rf "${INPUT_IMAGE_DIR}"
}

@test "secboot sign-bootloader-hab: machine not compatible with HAB" {

    unpack-image "${DEFAULT_TEZI_IMAGE}"
    local INPUT_IMAGE_DIR=$(echo ${DEFAULT_TEZI_IMAGE} | sed 's/\.tar$//g')
    local OUTPUT_IMAGE_DIR="SIGNED_${INPUT_IMAGE_DIR}"
    local CST_DIR="${CST_DIRS}/hab/cst-3.4.1_tcb_test_rsa_2048"

    # change the U-Boot environment file to change the machine name to an invalid one
    UBOOT_ENV_FILE=$(cat "${INPUT_IMAGE_DIR}/image.json" \
                         | grep u_boot_env \
                         | sed 's/.*"u_boot_env": "\(.*\)",/\1/')
    sed -i 's/^board=/board=dummy-/' "${INPUT_IMAGE_DIR}/${UBOOT_ENV_FILE}"

    run torizoncore-builder secboot sign-bootloader-hab "${INPUT_IMAGE_DIR}" "${OUTPUT_IMAGE_DIR}" \
                                                        --cst-dir "${CST_DIR}" --cst-crypto rsa \
                                                        --cst-key-size 2048 --cst-key-exp 65537 \
                                                        --cst-dig-algo sha256 --cst-srk-index 1
    assert_failure
    assert_output --partial "is not compatible with HAB"
    rm -rf "${INPUT_IMAGE_DIR}"
}

@test "secboot sign-bootloader-hab: sign HAB image with 2048-bit RSA keys" {
    requires-supported-hab-signing-machine
    requires-signed-image

    unpack-image "${DEFAULT_SIGNED_TEZI_IMAGE}"
    local INPUT_IMAGE_DIR=$(echo ${DEFAULT_SIGNED_TEZI_IMAGE} | sed 's/\.tar$//g')
    local OUTPUT_IMAGE_DIR="SIGNED_${INPUT_IMAGE_DIR}"
    local CST_DIR="${CST_DIRS}/hab/cst-3.4.1_tcb_test_rsa_2048"

    # copy CST binaries to CST_DIR before running tests
    cp -r "${CST_BINARIES_DIR}/linux32" "${CST_DIR}"
    cp -r "${CST_BINARIES_DIR}/linux64" "${CST_DIR}"

    if [ -d "${OUTPUT_IMAGE_DIR}" ]; then
        rm -rf "${OUTPUT_IMAGE_DIR}"
    fi

    # non-existent CST directory
    run torizoncore-builder secboot sign-bootloader-hab "${INPUT_IMAGE_DIR}" "${OUTPUT_IMAGE_DIR}" \
                                                        --cst-dir "cst_foo" --cst-crypto rsa \
                                                        --cst-key-size 2048 --cst-key-exp 65537 \
                                                        --cst-dig-algo sha256 --cst-srk-index 1
    assert_failure
    assert_output --partial 'does not exist'

    # non-existent SRK table binary
    run torizoncore-builder secboot sign-bootloader-hab "${INPUT_IMAGE_DIR}" "${OUTPUT_IMAGE_DIR}" \
                                                        --cst-dir "${CST_DIR}" --cst-crypto rsa \
                                                        --cst-key-size 2048 --cst-key-exp 65537 \
                                                        --cst-dig-algo sha256 --cst-srk-index 1 \
                                                        --cst-srk-table "foo.bin"
    assert_failure
    assert_output --partial 'Could not find'

    # non-existent SRK fuse binary
    run torizoncore-builder secboot sign-bootloader-hab "${INPUT_IMAGE_DIR}" "${OUTPUT_IMAGE_DIR}" \
                                                        --cst-dir "${CST_DIR}" --cst-crypto rsa \
                                                        --cst-key-size 2048 --cst-key-exp 65537 \
                                                        --cst-dig-algo sha256 --cst-srk-index 1 \
                                                        --cst-srk-fuse "foo.bin"
    assert_failure
    assert_output --partial 'Could not find'

    # run without --force
    run torizoncore-builder secboot sign-bootloader-hab "${INPUT_IMAGE_DIR}" "${OUTPUT_IMAGE_DIR}" \
                                                        --cst-dir "${CST_DIR}" --cst-crypto rsa \
                                                        --cst-key-size 2048 --cst-key-exp 65537 \
                                                        --cst-dig-algo sha256 --cst-srk-index 1
    assert_success
    assert_output --partial 'flash.bin created successfully'
    assert_output --partial 'Using SRK1 for signing'
    assert_output --partial 'Bootloader container signed successfully'
    assert_output --partial 'Bootloader in Torizon OS image signed successfully'

    # sign image in place
    run torizoncore-builder secboot sign-bootloader-hab "${OUTPUT_IMAGE_DIR}" "${OUTPUT_IMAGE_DIR}" \
                                                        --cst-dir "${CST_DIR}" --cst-crypto rsa \
                                                        --cst-key-size 2048 --cst-key-exp 65537 \
                                                        --cst-dig-algo sha256 --cst-srk-index 1 \
                                                        --force
    assert_success
    assert_output --partial 'flash.bin created successfully'
    assert_output --partial 'Using SRK1 for signing'
    assert_output --partial 'Bootloader container signed successfully'
    assert_output --partial 'Updating Torizon OS image in place'
    assert_output --partial 'Bootloader in Torizon OS image signed successfully'


    # run with --force for all four SRK indexes, adding kernel public key to U-Boot DTB before signing
    for i in {1..4}
    do
        run torizoncore-builder secboot sign-bootloader-hab "${INPUT_IMAGE_DIR}" "${OUTPUT_IMAGE_DIR}" \
                                                            --kernel-key-dir "${KERNEL_KEY_DIR}" \
                                                            --kernel-key "name=${KERNEL_KEY_NAME};algo=${KERNEL_KEY_ALGO}" \
                                                            --cst-dir "${CST_DIR}" --cst-crypto rsa \
                                                            --cst-key-size 2048 --cst-key-exp 65537 \
                                                            --cst-dig-algo sha256 --cst-srk-index ${i} \
                                                            --force
        assert_success
        assert_output --partial "Adding public key '${KERNEL_KEY_NAME}' in ${KERNEL_KEY_DIR} to U-Boot DTB"
        assert_output --partial 'flash.bin created successfully'
        assert_output --partial "Using SRK${i} for signing"
        assert_output --partial 'Bootloader container signed successfully'
        assert_output --partial 'Removing pre-existing directory'
        assert_output --partial 'Bootloader in Torizon OS image signed successfully'
    done

    # delete copied CST binaries as they're no longer needed
    rm -rf "${CST_DIR}/linux32"
    rm -rf "${CST_DIR}/linux64"
}

@test "secboot sign-bootloader-hab: sign HAB image with 1024-bit RSA keys, CA flag not set" {
    requires-supported-hab-signing-machine
    requires-signed-image

    local INPUT_IMAGE_DIR=$(echo ${DEFAULT_SIGNED_TEZI_IMAGE} | sed 's/\.tar$//g')
    local OUTPUT_IMAGE_DIR="SIGNED_${INPUT_IMAGE_DIR}"
    local CST_DIR="${CST_DIRS}/hab/cst-3.4.1_tcb_test_rsa_1024_no_ca"

    # copy CST binaries to CST_DIR before running tests
    cp -r "${CST_BINARIES_DIR}/linux32" "${CST_DIR}"
    cp -r "${CST_BINARIES_DIR}/linux64" "${CST_DIR}"

    # run with --force for all four SRK indexes, adding kernel public key to U-Boot DTB before signing
    for i in {1..4}
    do
        run torizoncore-builder secboot sign-bootloader-hab "${INPUT_IMAGE_DIR}" "${OUTPUT_IMAGE_DIR}" \
                                                            --kernel-key-dir "${KERNEL_KEY_DIR}" \
                                                            --kernel-key "name=${KERNEL_KEY_NAME};algo=${KERNEL_KEY_ALGO}" \
                                                            --cst-dir "${CST_DIR}" --cst-crypto rsa \
                                                            --cst-key-size 1024 --cst-key-exp 65537 \
                                                            --cst-dig-algo sha256 --cst-srk-index ${i} \
                                                            --cst-srk-no-ca --force
        assert_success
        assert_output --partial "Adding public key '${KERNEL_KEY_NAME}' in ${KERNEL_KEY_DIR} to U-Boot DTB"
        assert_output --partial 'flash.bin created successfully'
        assert_output --partial "Using SRK${i} for signing"
        assert_output --partial 'Bootloader container signed successfully'
        assert_output --partial 'Removing pre-existing directory'
        assert_output --partial 'Bootloader in Torizon OS image signed successfully'
    done

    # delete copied CST binaries as they're no longer needed
    rm -rf "${CST_DIR}/linux32"
    rm -rf "${CST_DIR}/linux64"
}

@test "secboot sign-bootloader-hab: sign HAB image with P-384 ECDSA keys" {
    requires-supported-hab-signing-machine
    requires-signed-image

    local INPUT_IMAGE_DIR=$(echo ${DEFAULT_SIGNED_TEZI_IMAGE} | sed 's/\.tar$//g')
    local OUTPUT_IMAGE_DIR="SIGNED_${INPUT_IMAGE_DIR}"
    local CST_DIR="${CST_DIRS}/hab/cst-3.4.1_tcb_test_ecdsa_p384"

    # copy CST binaries to CST_DIR before running tests
    cp -r "${CST_BINARIES_DIR}/linux32" "${CST_DIR}"
    cp -r "${CST_BINARIES_DIR}/linux64" "${CST_DIR}"

    # run with --force for all four SRK indexes, adding kernel public key to U-Boot DTB before signing
    for i in {1..4}
    do
        run torizoncore-builder secboot sign-bootloader-hab "${INPUT_IMAGE_DIR}" "${OUTPUT_IMAGE_DIR}" \
                                                            --kernel-key-dir "${KERNEL_KEY_DIR}" \
                                                            --kernel-key "name=${KERNEL_KEY_NAME};algo=${KERNEL_KEY_ALGO}" \
                                                            --cst-dir "${CST_DIR}" --cst-crypto ecdsa \
                                                            --cst-key-size secp384r1 --cst-dig-algo sha256 \
                                                            --cst-srk-index ${i} --force
        assert_success
        assert_output --partial "Adding public key '${KERNEL_KEY_NAME}' in ${KERNEL_KEY_DIR} to U-Boot DTB"
        assert_output --partial 'flash.bin created successfully'
        assert_output --partial "Using SRK${i} for signing"
        assert_output --partial 'Bootloader container signed successfully'
        assert_output --partial 'Removing pre-existing directory'
        assert_output --partial 'Bootloader in Torizon OS image signed successfully'
    done

    # delete copied CST binaries as they're no longer needed
    rm -rf "${CST_DIR}/linux32"
    rm -rf "${CST_DIR}/linux64"
}

@test "secboot sign-bootloader-hab: sign HAB image with P-521 ECDSA keys, CA flag not set" {
    requires-supported-hab-signing-machine
    requires-signed-image

    local INPUT_IMAGE_DIR=$(echo ${DEFAULT_SIGNED_TEZI_IMAGE} | sed 's/\.tar$//g')
    local OUTPUT_IMAGE_DIR="SIGNED_${INPUT_IMAGE_DIR}"
    local CST_DIR="${CST_DIRS}/hab/cst-3.4.1_tcb_test_ecdsa_p521_no_ca"

    # copy CST binaries to CST_DIR before running tests
    cp -r "${CST_BINARIES_DIR}/linux32" "${CST_DIR}"
    cp -r "${CST_BINARIES_DIR}/linux64" "${CST_DIR}"

    # run with --force for all four SRK indexes, adding kernel public key to U-Boot DTB before signing
    for i in {1..4}
    do
        run torizoncore-builder secboot sign-bootloader-hab "${INPUT_IMAGE_DIR}" "${OUTPUT_IMAGE_DIR}" \
                                                            --kernel-key-dir "${KERNEL_KEY_DIR}" \
                                                            --kernel-key "name=${KERNEL_KEY_NAME};algo=${KERNEL_KEY_ALGO}" \
                                                            --cst-dir "${CST_DIR}" --cst-crypto ecdsa \
                                                            --cst-key-size secp521r1 --cst-dig-algo sha256 \
                                                            --cst-srk-index ${i} --cst-srk-no-ca --force
        assert_success
        assert_output --partial "Adding public key '${KERNEL_KEY_NAME}' in ${KERNEL_KEY_DIR} to U-Boot DTB"
        assert_output --partial 'flash.bin created successfully'
        assert_output --partial "Using SRK${i} for signing"
        assert_output --partial 'Bootloader container signed successfully'
        assert_output --partial 'Removing pre-existing directory'
        assert_output --partial 'Torizon OS image signed successfully'
    done

    # delete copied CST binaries as they're no longer needed
    rm -rf "${CST_DIR}/linux32"
    rm -rf "${CST_DIR}/linux64"
}
