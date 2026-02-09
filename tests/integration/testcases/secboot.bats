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
        "the following arguments are required: --kernel-key"
}

@test "secboot sign-kernel: attempt to sign kernel FIT without images unpack" {
    torizoncore-builder-clean-storage

    run torizoncore-builder secboot sign-kernel \
        --kernel-key-dir "${KERNEL_KEY_DIR}" \
        --kernel-key "name=${KERNEL_KEY_NAME};algo=${KERNEL_KEY_ALGO}"
    assert_failure
    assert_output --partial "Error: could not find an Easy Installer or WIC image in the storage"
    assert_output --partial "Please use the 'images' command to unpack an image before running this command"
}

@test "secboot sign-kernel: invalid parameters" {
    # Unpack an unsigned image just so the initial 'images unpack' check is passed
    torizoncore-builder images --remove-storage unpack "${DEFAULT_TEZI_IMAGE}"

    # --kernel-key not specified
    run torizoncore-builder secboot sign-kernel --kernel-key-dir "${KERNEL_KEY_DIR}"
    assert_failure
    assert_output --partial 'the following arguments are required: --kernel-key'

    # non-existent kernel fitImage key directory
    run torizoncore-builder secboot sign-kernel \
        --kernel-key-dir "foo" \
        --kernel-key "name=${KERNEL_KEY_NAME};algo=${KERNEL_KEY_ALGO}"
    assert_failure
    assert_output --partial 'does not exist'

    # key name that does not match file in key directory
    run torizoncore-builder secboot sign-kernel \
        --kernel-key-dir "${KERNEL_KEY_DIR}" \
        --kernel-key "name=foo;algo=${KERNEL_KEY_ALGO}"
    assert_failure
    assert_output --partial 'Could not find'

    # Invalid --kernel-key format (comma instead of semicolon)
    run torizoncore-builder secboot sign-kernel \
        --kernel-key-dir "${KERNEL_KEY_DIR}" \
        --kernel-key "name=${KERNEL_KEY_NAME},algo=${KERNEL_KEY_ALGO}"
    assert_failure
    assert_output --partial '--kernel-key is not correctly formatted'

    # --kernel-key without name
    run torizoncore-builder secboot sign-kernel \
        --kernel-key-dir "${KERNEL_KEY_DIR}" \
        --kernel-key "algo=${KERNEL_KEY_ALGO}"
    assert_failure
    assert_output --partial "Could not find value of 'name' in --kernel-key"
}

@test "secboot sign-kernel: image with unsupported kernel format" {
    requires-supported-kernel-signing-machine
    requires-non-fit-kernel

    torizoncore-builder images --remove-storage unpack "${DEFAULT_TEZI_IMAGE}"

    run torizoncore-builder secboot sign-kernel \
        --kernel-key-dir "${KERNEL_KEY_DIR}" \
        --kernel-key "name=${KERNEL_KEY_NAME};algo=${KERNEL_KEY_ALGO}"
    assert_failure
    assert_output --partial 'Unpacked image does not have the kernel in FIT format'
}

@test "secboot sign-kernel: unsupported machine" {

    unpack-image "${DEFAULT_TEZI_IMAGE}"
    local INPUT_IMAGE_DIR=$(echo ${DEFAULT_TEZI_IMAGE} | sed 's/\.tar$//g')

    # change the U-Boot environment file to change the machine name to an invalid one
    UBOOT_ENV_FILE=$(cat "${INPUT_IMAGE_DIR}/image.json" \
                         | grep u_boot_env \
                         | sed 's/.*"u_boot_env": "\(.*\)",/\1/')
    sed -i 's/^board=/board=dummy-/' "${INPUT_IMAGE_DIR}/${UBOOT_ENV_FILE}"

    # Unpack the image to internal storage
    torizoncore-builder images --remove-storage unpack "${INPUT_IMAGE_DIR}"

    run torizoncore-builder secboot sign-kernel \
        --kernel-key-dir "${KERNEL_KEY_DIR}" \
        --kernel-key "name=${KERNEL_KEY_NAME};algo=${KERNEL_KEY_ALGO}"
    assert_failure
    assert_output --partial "TorizonCore Builder doesn't support signing the kernel of images for"
    torizoncore-builder-clean-storage
    rm -rf "${INPUT_IMAGE_DIR}"
}

@test "secboot sign-kernel: sign with test key" {

    requires-supported-kernel-signing-machine
    requires-signed-image

    torizoncore-builder images --remove-storage unpack "${DEFAULT_SIGNED_TEZI_IMAGE}"

    run torizoncore-builder secboot sign-kernel \
        --kernel-key-dir "${KERNEL_KEY_DIR}" \
        --kernel-key "name=${KERNEL_KEY_NAME};algo=${KERNEL_KEY_ALGO}"
    assert_success
    assert_output --partial "Updating fitImage configurations to be signed with key name \"${KERNEL_KEY_NAME}\""
    assert_output --regexp "Signing kernel fitImage with .* algorithm: ${KERNEL_KEY_ALGO}"
    assert_output --partial 'Kernel fitImage signed successfully'
    assert_output --partial 'Kernel in unpacked Torizon OS image signed successfully'

    run torizoncore-builder-shell "ls -l /storage/kernel/usr/lib/modules/*/vmlinuz"
    assert_success

    torizoncore-builder-clean-storage

    # run with --kernel-key parameters separated with space (should still work)
    torizoncore-builder images --remove-storage unpack "${DEFAULT_SIGNED_TEZI_IMAGE}"

    run torizoncore-builder secboot sign-kernel \
        --kernel-key-dir "${KERNEL_KEY_DIR}" \
        --kernel-key "name = ${KERNEL_KEY_NAME}; algo = ${KERNEL_KEY_ALGO}"
    assert_success
    assert_output --partial "Updating fitImage configurations to be signed with key name \"${KERNEL_KEY_NAME}\""
    assert_output --regexp "Signing kernel fitImage with .* algorithm: ${KERNEL_KEY_ALGO}"
    assert_output --partial 'Kernel fitImage signed successfully'
    assert_output --partial 'Kernel in unpacked Torizon OS image signed successfully'

    run torizoncore-builder-shell "ls -l /storage/kernel/usr/lib/modules/*/vmlinuz"
    assert_success

    local CONFIG_LIST=$(torizoncore-builder-shell \
                        "fdtget -ts /storage/kernel/usr/lib/modules/*/vmlinuz \
                        /configurations -l")

    local CONFIG1=$(echo "${CONFIG_LIST}" | head -n 1)

    local CONFIG1_SUBNODES=$(torizoncore-builder-shell \
                             "fdtget -ts /storage/kernel/usr/lib/modules/*/vmlinuz \
                             /configurations/${CONFIG1} -l")

    local SIG_NODE=$(echo "${CONFIG1_SUBNODES}" | grep signature)

    local FOUND_KEY_NAME=$(torizoncore-builder-shell \
                           "fdtget -ts /storage/kernel/usr/lib/modules/*/vmlinuz \
                           /configurations/${CONFIG1}/${SIG_NODE} key-name-hint")

    run test "${FOUND_KEY_NAME}" == "${KERNEL_KEY_NAME}"
    assert_success
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
        "the following arguments are required: --cst-dir"
}

@test "secboot sign-bootloader-hab: attempt to sign kernel FIT without images unpack" {
    torizoncore-builder-clean-storage

    local CST_DIR="${CST_DIRS}/hab/cst-3.4.1_tcb_test_rsa_2048"

    run torizoncore-builder secboot sign-bootloader-hab \
        --cst-dir "${CST_DIR}" \
        --cst-crypto rsa \
        --cst-dig-algo sha256 --cst-srk-index 1 \
        --kernel-key-dir "${KERNEL_KEY_DIR}" \
        --kernel-key "name=${KERNEL_KEY_NAME};algo=${KERNEL_KEY_ALGO}"
    assert_failure
    assert_output --partial "Error: could not find an Easy Installer or WIC image in the storage"
    assert_output --partial "Please use the 'images' command to unpack an image before running this command"
}

@test "secboot sign-bootloader-hab: invalid parameters" {
    local CST_DIR="${CST_DIRS}/hab/cst-3.4.1_tcb_test_rsa_2048"

    # Unpack an unsigned image just so the initial 'images unpack' check is passed
    torizoncore-builder images --remove-storage unpack "${DEFAULT_TEZI_IMAGE}"

    # non-existent kernel key directory
    run torizoncore-builder secboot sign-bootloader-hab \
        --cst-dir "${CST_DIR}" \
        --cst-crypto rsa \
        --cst-dig-algo sha256 --cst-srk-index 1 \
        --kernel-key-dir "foo" \
        --kernel-key "name=${KERNEL_KEY_NAME};algo=${KERNEL_KEY_ALGO}"
    assert_failure
    assert_output --partial 'does not exist'

    # non-existent kernel key file in working directory
    run torizoncore-builder secboot sign-bootloader-hab \
        --cst-dir "${CST_DIR}" \
        --cst-crypto rsa \
        --cst-dig-algo sha256 --cst-srk-index 1 \
        --kernel-key "name=bad${KERNEL_KEY_NAME};algo=${KERNEL_KEY_ALGO}"
    assert_failure
    assert_output --regexp 'Could not find.*\.key.*Aborting'

    # non-existent key with provided name
    run torizoncore-builder secboot sign-bootloader-hab \
        --cst-dir "${CST_DIR}" \
        --cst-crypto rsa \
        --cst-dig-algo sha256 --cst-srk-index 1 \
        --kernel-key-dir "${KERNEL_KEY_DIR}" \
        --kernel-key "name=foo;algo=${KERNEL_KEY_ALGO}"
    assert_failure
    assert_output --partial 'Could not find'

    # Provide --kernel-key-dir but not --kernel-key
    run torizoncore-builder secboot sign-bootloader-hab \
        --cst-dir "${CST_DIR}" \
        --cst-crypto rsa \
        --cst-dig-algo sha256 --cst-srk-index 1 \
        --kernel-key-dir "${KERNEL_KEY_DIR}"
    assert_failure
    assert_output --partial '--kernel-key-dir was passed but --kernel-key was not'

    # invalid type of cryptographic keys
    run torizoncore-builder secboot sign-bootloader-hab \
        --cst-dir "${CST_DIR}" --cst-crypto invalid_key_type
    assert_failure
    assert_output --partial 'argument --cst-crypto: invalid choice:'

    # invalid CST digest algorithm
    run torizoncore-builder secboot sign-bootloader-hab \
        --cst-dir "${CST_DIR}" --cst-dig-algo invalid_dig_algo
    assert_failure
    assert_output --partial 'argument --cst-dig-algo: invalid choice:'

    # invalid SRK table index
    run torizoncore-builder secboot sign-bootloader-hab \
        --cst-dir "${CST_DIR}" --cst-srk-index 0
    assert_failure
    assert_output --partial 'argument --cst-srk-index: invalid choice:'
}

@test "secboot sign-bootloader-hab: image with unsupported kernel format" {
    requires-supported-hab-signing-machine
    requires-non-fit-kernel

    torizoncore-builder images --remove-storage unpack "${DEFAULT_TEZI_IMAGE}"

    local CST_DIR="${CST_DIRS}/hab/cst-3.4.1_tcb_test_rsa_2048"

    run torizoncore-builder secboot sign-bootloader-hab \
        --cst-dir "${CST_DIR}" \
        --cst-crypto rsa \
        --cst-key-size 2048 --cst-key-exp 65537 \
        --cst-dig-algo sha256 --cst-srk-index 1
    assert_failure
    assert_output --partial 'Unpacked image does not have the kernel in FIT format'
}

@test "secboot sign-bootloader-hab: machine not compatible with HAB" {

    unpack-image "${DEFAULT_TEZI_IMAGE}"
    local INPUT_IMAGE_DIR=$(echo ${DEFAULT_TEZI_IMAGE} | sed 's/\.tar$//g')
    local CST_DIR="${CST_DIRS}/hab/cst-3.4.1_tcb_test_rsa_2048"

    # change the U-Boot environment file to change the machine name to an invalid one
    UBOOT_ENV_FILE=$(cat "${INPUT_IMAGE_DIR}/image.json" \
                         | grep u_boot_env \
                         | sed 's/.*"u_boot_env": "\(.*\)",/\1/')
    sed -i 's/^board=/board=dummy-/' "${INPUT_IMAGE_DIR}/${UBOOT_ENV_FILE}"

    # Unpack the image to internal storage
    torizoncore-builder images --remove-storage unpack "${INPUT_IMAGE_DIR}"

    run torizoncore-builder secboot sign-bootloader-hab \
        --cst-dir "${CST_DIR}" \
        --cst-crypto rsa \
        --cst-key-size 2048 --cst-key-exp 65537 \
        --cst-dig-algo sha256 --cst-srk-index 1
    assert_failure
    assert_output --partial "is not compatible with HAB"
    rm -rf "${INPUT_IMAGE_DIR}"
}

@test "secboot sign-bootloader-hab: sign HAB image with 2048-bit RSA keys" {
    requires-supported-hab-signing-machine
    requires-signed-image

    local CST_DIR="${CST_DIRS}/hab/cst-3.4.1_tcb_test_rsa_2048"

    # copy CST binaries to CST_DIR before running tests
    cp -r "${CST_BINARIES_DIR}/linux32" "${CST_DIR}"
    cp -r "${CST_BINARIES_DIR}/linux64" "${CST_DIR}"

    # TODO: Consider dropping DEFAULT_SIGNED_TEZI_IMAGE and using DEFAULT_TEZI_IMAGE.
    torizoncore-builder images --remove-storage unpack "${DEFAULT_SIGNED_TEZI_IMAGE}"

    # non-existent CST directory
    run torizoncore-builder secboot sign-bootloader-hab \
        --cst-dir "cst_foo" \
        --cst-crypto rsa \
        --cst-key-size 2048 --cst-key-exp 65537 \
        --cst-dig-algo sha256 --cst-srk-index 1
    assert_failure
    assert_output --partial 'does not exist'

    # non-existent SRK table binary
    run torizoncore-builder secboot sign-bootloader-hab \
        --cst-dir "${CST_DIR}" \
        --cst-crypto rsa \
        --cst-key-size 2048 --cst-key-exp 65537 \
        --cst-dig-algo sha256 --cst-srk-index 1 \
        --cst-srk-table "foo.bin"
    assert_failure
    assert_output --partial 'Could not find'

    # non-existent SRK fuse binary
    run torizoncore-builder secboot sign-bootloader-hab \
        --cst-dir "${CST_DIR}" \
        --cst-crypto rsa \
        --cst-key-size 2048 --cst-key-exp 65537 \
        --cst-dig-algo sha256 --cst-srk-index 1 \
        --cst-srk-fuse "foo.bin"
    assert_failure
    assert_output --partial 'Could not find'

    # run without providing a kernel FIT public key
    run torizoncore-builder secboot sign-bootloader-hab \
        --cst-dir "${CST_DIR}" \
        --cst-crypto rsa \
        --cst-key-size 2048 --cst-key-exp 65537 \
        --cst-dig-algo sha256 --cst-srk-index 1
    assert_success
    assert_output --partial 'flash.bin created successfully'
    assert_output --partial 'Using SRK1 for signing'
    assert_output --partial 'Bootloader container signed successfully'
    assert_output --partial 'The bootloader DTBs were NOT updated with a new public key'
    assert_output --partial 'Bootloader in Torizon OS image signed successfully'

    # run for all four SRK indexes, adding kernel public key to U-Boot DTB before signing
    for i in {1..4}; do
        run torizoncore-builder secboot sign-bootloader-hab \
            --cst-dir "${CST_DIR}" \
            --kernel-key-dir "${KERNEL_KEY_DIR}" \
            --kernel-key "name=${KERNEL_KEY_NAME};algo=${KERNEL_KEY_ALGO}" \
            --cst-crypto rsa --cst-key-size 2048 \
            --cst-key-exp 65537 --cst-dig-algo sha256 \
            --cst-srk-index ${i}
        assert_success
        assert_output --partial "Adding public key '${KERNEL_KEY_NAME}' in ${KERNEL_KEY_DIR} to U-Boot DTB"
        assert_output --partial 'flash.bin created successfully'
        assert_output --partial "Using SRK${i} for signing"
        assert_output --partial 'Bootloader container signed successfully'
        assert_output --partial 'Bootloader in Torizon OS image signed successfully'
    done

    # delete copied CST binaries as they're no longer needed
    rm -rf "${CST_DIR}/linux32"
    rm -rf "${CST_DIR}/linux64"
}

@test "secboot sign-bootloader-hab: sign HAB image with 1024-bit RSA keys, CA flag not set" {
    requires-supported-hab-signing-machine
    requires-signed-image

    local CST_DIR="${CST_DIRS}/hab/cst-3.4.1_tcb_test_rsa_1024_no_ca"

    # copy CST binaries to CST_DIR before running tests
    cp -r "${CST_BINARIES_DIR}/linux32" "${CST_DIR}"
    cp -r "${CST_BINARIES_DIR}/linux64" "${CST_DIR}"

    torizoncore-builder images --remove-storage unpack "${DEFAULT_SIGNED_TEZI_IMAGE}"

    # run for all four SRK indexes, adding kernel public key to U-Boot DTB before signing
    for i in {1..4}; do
        run torizoncore-builder secboot sign-bootloader-hab \
            --cst-dir "${CST_DIR}" \
            --kernel-key-dir "${KERNEL_KEY_DIR}" \
            --kernel-key "name=${KERNEL_KEY_NAME};algo=${KERNEL_KEY_ALGO}" \
            --cst-crypto rsa --cst-key-size 1024 \
            --cst-key-exp 65537 --cst-dig-algo sha256 \
            --cst-srk-index ${i} --cst-srk-no-ca
        assert_success
        assert_output --partial "Adding public key '${KERNEL_KEY_NAME}' in ${KERNEL_KEY_DIR} to U-Boot DTB"
        assert_output --partial 'flash.bin created successfully'
        assert_output --partial "Using SRK${i} for signing"
        assert_output --partial 'Bootloader container signed successfully'
        assert_output --partial 'Bootloader in Torizon OS image signed successfully'
    done

    # delete copied CST binaries as they're no longer needed
    rm -rf "${CST_DIR}/linux32"
    rm -rf "${CST_DIR}/linux64"
}

@test "secboot sign-bootloader-hab: sign HAB image with P-384 ECDSA keys" {
    requires-supported-hab-signing-machine
    requires-signed-image

    local CST_DIR="${CST_DIRS}/hab/cst-3.4.1_tcb_test_ecdsa_p384"

    # copy CST binaries to CST_DIR before running tests
    cp -r "${CST_BINARIES_DIR}/linux32" "${CST_DIR}"
    cp -r "${CST_BINARIES_DIR}/linux64" "${CST_DIR}"

    torizoncore-builder images --remove-storage unpack "${DEFAULT_SIGNED_TEZI_IMAGE}"

    # run for all four SRK indexes, adding kernel public key to U-Boot DTB before signing
    for i in {1..4}; do
        run torizoncore-builder secboot sign-bootloader-hab \
            --cst-dir "${CST_DIR}" \
            --kernel-key-dir "${KERNEL_KEY_DIR}" \
            --kernel-key "name=${KERNEL_KEY_NAME};algo=${KERNEL_KEY_ALGO}" \
            --cst-crypto ecdsa --cst-key-size secp384r1 \
            --cst-dig-algo sha256 --cst-srk-index ${i}
        assert_success
        assert_output --partial "Adding public key '${KERNEL_KEY_NAME}' in ${KERNEL_KEY_DIR} to U-Boot DTB"
        assert_output --partial 'flash.bin created successfully'
        assert_output --partial "Using SRK${i} for signing"
        assert_output --partial 'Bootloader container signed successfully'
        assert_output --partial 'Bootloader in Torizon OS image signed successfully'
    done

    # delete copied CST binaries as they're no longer needed
    rm -rf "${CST_DIR}/linux32"
    rm -rf "${CST_DIR}/linux64"
}

@test "secboot sign-bootloader-hab: sign HAB image with P-521 ECDSA keys, CA flag not set" {
    requires-supported-hab-signing-machine
    requires-signed-image

    local CST_DIR="${CST_DIRS}/hab/cst-3.4.1_tcb_test_ecdsa_p521_no_ca"

    # copy CST binaries to CST_DIR before running tests
    cp -r "${CST_BINARIES_DIR}/linux32" "${CST_DIR}"
    cp -r "${CST_BINARIES_DIR}/linux64" "${CST_DIR}"

    torizoncore-builder images --remove-storage unpack "${DEFAULT_SIGNED_TEZI_IMAGE}"

    # run for all four SRK indexes, adding kernel public key to U-Boot DTB before signing
    for i in {1..4}; do
        run torizoncore-builder secboot sign-bootloader-hab \
            --cst-dir "${CST_DIR}" \
            --kernel-key-dir "${KERNEL_KEY_DIR}" \
            --kernel-key "name=${KERNEL_KEY_NAME};algo=${KERNEL_KEY_ALGO}" \
            --cst-crypto ecdsa --cst-key-size secp521r1 \
            --cst-dig-algo sha256 --cst-srk-index ${i} \
            --cst-srk-no-ca
        assert_success
        assert_output --partial "Adding public key '${KERNEL_KEY_NAME}' in ${KERNEL_KEY_DIR} to U-Boot DTB"
        assert_output --partial 'flash.bin created successfully'
        assert_output --partial "Using SRK${i} for signing"
        assert_output --partial 'Bootloader container signed successfully'
        assert_output --partial 'Torizon OS image signed successfully'
    done

    # delete copied CST binaries as they're no longer needed
    rm -rf "${CST_DIR}/linux32"
    rm -rf "${CST_DIR}/linux64"
}
