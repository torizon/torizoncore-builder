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

    K3_SIGNING_SUPPORTED_MACHINES=$(torizoncore-builder secboot sign-bootloader-k3 --help \
                                    | grep '^Currently supported machines:')
    if echo "${K3_SIGNING_SUPPORTED_MACHINES}" | grep -q "${MACHINE}"; then
        IS_K3_SIGNING_SUPPORTED="1"
    else
        IS_K3_SIGNING_SUPPORTED="0"
    fi

    SIGNING_KEYS_DIR="${SAMPLES_DIR}/signing_keys"
    KERNEL_KEY_DIR="${SIGNING_KEYS_DIR}/kernel_fitimage"
    KERNEL_KEY_NAME="test"
    KERNEL_KEY_ALGO="sha256,rsa2048"

    # Key the K3 boot containers are signed with in the tests. Generated here rather than
    # committed: it is a plain RSA key like the one a customer would fuse the hash of, and
    # nothing outside these tests needs to hold it.
    K3_KEY="k3_test_key.pem"
    if [ ! -f "${K3_KEY}" ]; then
        torizoncore-builder-shell "openssl genrsa -out /workdir/${K3_KEY} 4096" 2>/dev/null
    fi

    # Directories in the container's storage the tests look into.
    SIGNED_DIR="/storage/signed_bootloader_artifacts"
    FIRST_RUN_DIR="/storage/first_run_artifacts"

    # Set TCB_K3_REFERENCE_KEY to the key that signed the image under test to enable the
    # byte-for-byte comparison against it; see the test that requires it.
    K3_REFERENCE_KEY="${TCB_K3_REFERENCE_KEY:-}"

    CST_DIRS="cst_dirs"
    CST_TARBALL="${SIGNING_KEYS_DIR}/${CST_DIRS}.tar.gz"
    CST_BINARIES_DIR="${CST_DIRS}/cst-3.4.1"
    unpack-image "${CST_TARBALL}"

    export IS_KERNEL_SIGNING_SUPPORTED
    export IS_HAB_SIGNING_SUPPORTED
    export IS_K3_SIGNING_SUPPORTED
    export SIGNING_KEYS_DIR
    export K3_KEY
    export K3_REFERENCE_KEY
    export SIGNED_DIR
    export FIRST_RUN_DIR
    export KERNEL_KEY_DIR
    export KERNEL_KEY_NAME
    export KERNEL_KEY_ALGO
    export CST_DIRS
    export CST_BINARIES_DIR
}

@test "secboot: check help output" {
    run torizoncore-builder secboot --help
    assert_success
    assert_output --partial '{sign-bootloader-hab,sign-bootloader-k3,sign-kernel}'
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

@test "secboot sign-bootloader-k3: check help output" {
    run torizoncore-builder secboot sign-bootloader-k3 --help
    assert_success
    assert_output --partial "usage: torizoncore-builder secboot sign-bootloader-k3"
    assert_output --partial "Currently supported machines:"
}

@test "secboot sign-bootloader-k3: run without parameters" {
    run torizoncore-builder secboot sign-bootloader-k3
    assert_failure
    assert_output --partial "the following arguments are required: --k3-key"
}

@test "secboot sign-bootloader-k3: attempt to sign without images unpack" {
    torizoncore-builder-clean-storage

    run torizoncore-builder secboot sign-bootloader-k3 --k3-key "${K3_KEY}"
    assert_failure
    assert_output --partial "Error: could not find an Easy Installer or WIC image in the storage"
}

@test "secboot sign-bootloader-k3: invalid parameters" {
    # Unpack an image just so the initial 'images unpack' check is passed
    torizoncore-builder images --remove-storage unpack "${DEFAULT_TEZI_IMAGE}"

    # non-existent signing key
    run torizoncore-builder secboot sign-bootloader-k3 --k3-key "foo.pem"
    assert_failure
    assert_output --partial 'does not exist'

    # non-existent degenerate key
    run torizoncore-builder secboot sign-bootloader-k3 \
        --k3-key "${K3_KEY}" --k3-degenerate-key "foo.pem"
    assert_failure
    assert_output --partial 'does not exist'

    # --kernel-key-dir without --kernel-key
    run torizoncore-builder secboot sign-bootloader-k3 \
        --k3-key "${K3_KEY}" --kernel-key-dir "${KERNEL_KEY_DIR}"
    assert_failure
    assert_output --partial '--kernel-key-dir was passed but --kernel-key was not'

    # unknown kind of device
    run torizoncore-builder secboot sign-bootloader-k3 \
        --k3-key "${K3_KEY}" --target-device "fused"
    assert_failure
    assert_output --partial 'argument --target-device: invalid choice:'
}

@test "secboot sign-bootloader-k3: machine without K3 signing support" {
    unpack-image "${DEFAULT_TEZI_IMAGE}"
    local INPUT_IMAGE_DIR=$(echo ${DEFAULT_TEZI_IMAGE} | sed 's/\.tar$//g')

    # change the U-Boot environment file to change the machine name to an invalid one
    UBOOT_ENV_FILE=$(cat "${INPUT_IMAGE_DIR}/image.json" \
                         | grep u_boot_env \
                         | sed 's/.*"u_boot_env": "\(.*\)",/\1/')
    sed -i 's/^board=/board=dummy-/' "${INPUT_IMAGE_DIR}/${UBOOT_ENV_FILE}"

    torizoncore-builder images --remove-storage unpack "${INPUT_IMAGE_DIR}"

    run torizoncore-builder secboot sign-bootloader-k3 --k3-key "${K3_KEY}"
    assert_failure
    assert_output --partial "doesn't support signing the TI K3 bootloader"
    rm -rf "${INPUT_IMAGE_DIR}"
}

@test "secboot sign-bootloader-k3: sign the bootloader binaries" {
    requires-supported-k3-signing-machine
    requires-signed-image

    torizoncore-builder images --remove-storage unpack "${DEFAULT_SIGNED_TEZI_IMAGE}"

    run torizoncore-builder secboot sign-bootloader-k3 \
        --k3-key "${K3_KEY}" \
        --kernel-key-dir "${KERNEL_KEY_DIR}" \
        --kernel-key "name=${KERNEL_KEY_NAME};algo=${KERNEL_KEY_ALGO}"
    assert_success
    assert_output --partial "Signed bootloader binaries:"
    assert_output --partial "Bootloader in Torizon OS image signed successfully!"

    # Every bootloader binary the image installs must have been signed, and no key material
    # may be left behind: not in the repacked signing files, and not in the storage volume,
    # where signing stages copies of the key while it runs.
    run torizoncore-builder-shell "
        set -e
        for f in /storage/tezi/tiboot3*.bin /storage/tezi/tispl.bin /storage/tezi/u-boot.img; do
            [ -f \"\$f\" ] || continue
            [ -f \"${SIGNED_DIR}/\$(basename \$f)\" ]
        done
        [ -f ${SIGNED_DIR}/tcb_signing_files.tar.gz ]
        ! tar -tzf ${SIGNED_DIR}/tcb_signing_files.tar.gz | grep -q -e '\.pem$' -e '\.crt$'
        [ ! -e /storage/secure_boot_workdir ]"
    assert_success
}

@test "secboot sign-bootloader-k3: signing twice produces the same bytes" {
    requires-supported-k3-signing-machine
    requires-signed-image

    torizoncore-builder images --remove-storage unpack "${DEFAULT_SIGNED_TEZI_IMAGE}"

    torizoncore-builder secboot sign-bootloader-k3 \
        --k3-key "${K3_KEY}" \
        --kernel-key-dir "${KERNEL_KEY_DIR}" \
        --kernel-key "name=${KERNEL_KEY_NAME};algo=${KERNEL_KEY_ALGO}"
    torizoncore-builder-shell "rm -rf ${FIRST_RUN_DIR} && cp -a ${SIGNED_DIR} ${FIRST_RUN_DIR}"

    torizoncore-builder secboot sign-bootloader-k3 \
        --k3-key "${K3_KEY}" \
        --kernel-key-dir "${KERNEL_KEY_DIR}" \
        --kernel-key "name=${KERNEL_KEY_NAME};algo=${KERNEL_KEY_ALGO}"

    # Identical, whatever the image being signed was built with: the certificates TorizonCore
    # Builder generates are pinned even when the ones in the image are not. The tarball counts:
    # it travels in the image, so if its bytes moved between two runs the images would differ
    # even with every binary inside them identical.
    run torizoncore-builder-shell "
        set -e
        for f in ${SIGNED_DIR}/*.bin ${SIGNED_DIR}/*.img ${SIGNED_DIR}/*.tar.gz; do
            cmp \"\$f\" \"${FIRST_RUN_DIR}/\$(basename \$f)\"
        done"
    assert_success

    # The fixed validity is what says the reproducibility patch is in this container; this
    # fails if it ever falls out of it, whatever the cause.
    run torizoncore-builder-shell \
        "openssl x509 -inform DER -in ${SIGNED_DIR}/tiboot3-*-gp-*.bin -noout -enddate"
    assert_success
    assert_output --partial "notAfter=Dec 31 23:59:59 2049 GMT"

    torizoncore-builder-shell "rm -rf ${FIRST_RUN_DIR}"
}

@test "secboot sign-bootloader-k3: binaries match the ones in the image under the certificate" {
    requires-supported-k3-signing-machine
    requires-signed-image

    torizoncore-builder images --remove-storage unpack "${DEFAULT_SIGNED_TEZI_IMAGE}"

    torizoncore-builder secboot sign-bootloader-k3 \
        --k3-key "${K3_KEY}" \
        --kernel-key-dir "${KERNEL_KEY_DIR}" \
        --kernel-key "name=${KERNEL_KEY_NAME};algo=${KERNEL_KEY_ALGO}"

    # What a signing key cannot change is the payload the certificate is prepended to. Compare
    # that against the image's own containers, and check the certificate is one made with the
    # key that was passed. This holds for any image, whether or not its certificates are
    # reproducible, and it is the check that stays available when they are not.
    run torizoncore-builder-shell "
        set -e
        for f in /storage/tezi/tiboot3*.bin; do
            base=\$(basename \$f)
            python3 -c \"
import sys
def payload(path):
    data = open(path, 'rb').read()
    assert data[0] == 0x30, path
    count = data[1] & 0x7f if data[1] >= 0x80 else 0
    length = data[1] if not count else int.from_bytes(data[2:2 + count], 'big')
    return data[2 + count + length:]
assert payload(sys.argv[1]) == payload(sys.argv[2]), sys.argv[2]
\" \"\$f\" \"${SIGNED_DIR}/\$base\"
            openssl x509 -inform DER -in \"${SIGNED_DIR}/\$base\" -outform PEM -out /tmp/cert.pem
            openssl verify -CAfile /tmp/cert.pem /tmp/cert.pem >/dev/null

            # The container for GP silicon is signed with the degenerate key TorizonCore
            # Builder ships, as a Torizon OS build signs it, so it is the one binary here
            # whose certificate does not carry the key that was passed.
            key=/workdir/${K3_KEY}
            case \"\$base\" in
                *-gp-*) key=/builder/tcbuilder/secure_boot_files/ti-degenerate-key.pem ;;
            esac
            diff <(openssl x509 -in /tmp/cert.pem -noout -pubkey) \
                 <(openssl pkey -in \"\$key\" -pubout)
        done"
    assert_success
}

@test "secboot sign-bootloader-k3: binaries reproduce the ones in the image" {
    requires-supported-k3-signing-machine
    requires-signed-image
    requires-k3-reference-key

    torizoncore-builder images --remove-storage unpack "${DEFAULT_SIGNED_TEZI_IMAGE}"
    requires-pinned-certificates

    # Signed with the key the image was signed with, and with no --kernel-key so that the key
    # the image already carries is the one embedded, a re-sign has to give the image's own
    # binaries back. The container built for fused devices is not shipped in the image, so it
    # has no reference here; the determinism test covers that one.
    torizoncore-builder secboot sign-bootloader-k3 --k3-key "${K3_REFERENCE_KEY}"

    run torizoncore-builder-shell "
        set -e
        for f in /storage/tezi/tiboot3*.bin /storage/tezi/tispl.bin /storage/tezi/u-boot.img; do
            [ -f \"\$f\" ] || continue
            cmp \"\$f\" \"${SIGNED_DIR}/\$(basename \$f)\"
        done"
    assert_success

    # And so does the tarball they are repacked into, which is what lets a customer compare a
    # whole re-signed image with the one they downloaded rather than only the binaries in it.
    # It holds because the repack uses the tar options of the recipe that produced it.
    run torizoncore-builder-shell \
        "cmp /storage/tezi/tcb_signing_files.tar.gz ${SIGNED_DIR}/tcb_signing_files.tar.gz"
    assert_success
}

@test "secboot sign-bootloader-k3: say when the image's certificates are not reproducible" {
    requires-supported-k3-signing-machine
    requires-signed-image

    torizoncore-builder images --remove-storage unpack "${DEFAULT_SIGNED_TEZI_IMAGE}"
    requires-unpinned-certificates

    run torizoncore-builder secboot sign-bootloader-k3 \
        --k3-key "${K3_KEY}" \
        --kernel-key-dir "${KERNEL_KEY_DIR}" \
        --kernel-key "name=${KERNEL_KEY_NAME};algo=${KERNEL_KEY_ALGO}"
    assert_success
    assert_output --partial "were not generated reproducibly"
}

@test "secboot sign-bootloader-k3: carry the key of the image over" {
    requires-supported-k3-signing-machine
    requires-signed-image

    torizoncore-builder images --remove-storage unpack "${DEFAULT_SIGNED_TEZI_IMAGE}"

    run torizoncore-builder secboot sign-bootloader-k3 --k3-key "${K3_KEY}"
    assert_success
    assert_output --regexp "the public key '.*' already in this image is being carried over"
    assert_output --partial "Bootloader in Torizon OS image signed successfully!"

    # The key the image names must be the one the signed bootloader carries. This is the test
    # that fails if a U-Boot update changes the shape of the artifact it is read from.
    run torizoncore-builder-shell "
        python3 -c \"
import sys, libfdt
def key_name(path):
    fit = libfdt.Fdt(open(path, 'rb').read())
    configs = fit.path_offset('/configurations')
    config = fit.subnode_offset(configs, fit.getprop(configs, 'default').as_str())
    image = fit.subnode_offset(fit.path_offset('/images'),
                               fit.getprop(config, 'fdt').as_str())
    data = bytes(fit.getprop(image, 'data'))
    dtb = libfdt.Fdt(data[data.index(bytes.fromhex('d00dfeed')):])
    node = dtb.first_subnode(dtb.path_offset('/signature'))
    return dtb.getprop(node, 'key-name-hint').as_str()
original, signed = (key_name(p) for p in sys.argv[1:3])
assert original == signed, f'{original} != {signed}'
print(signed)
\" /storage/tezi/u-boot.img ${SIGNED_DIR}/u-boot.img"
    assert_success
}

@test "secboot sign-bootloader-k3: choose the kind of device the image targets" {
    requires-supported-k3-signing-machine
    requires-signed-image

    torizoncore-builder images --remove-storage unpack "${DEFAULT_SIGNED_TEZI_IMAGE}"

    local CURRENT_TARGET=$(torizoncore-builder-shell "
        grep -q -- '-hs-fs-' /storage/tezi/image.json && echo hs-fs || echo hs-se" | tr -d '\r')

    # Asking for what the image already targets leaves it alone.
    run torizoncore-builder secboot sign-bootloader-k3 \
        --k3-key "${K3_KEY}" --target-device "${CURRENT_TARGET}"
    assert_success
    assert_output --partial "already targets a ${CURRENT_TARGET^^} device"
    run torizoncore-builder-shell "[ ! -f ${SIGNED_DIR}/tcb_k3_target_device.json ]"
    assert_success

    # Asking for the other one records the request, with a warning either way about the module
    # the image will then boot on.
    local OTHER_TARGET="hs-se"
    [ "${CURRENT_TARGET}" = "hs-se" ] && OTHER_TARGET="hs-fs"

    run torizoncore-builder secboot sign-bootloader-k3 \
        --k3-key "${K3_KEY}" --target-device "${OTHER_TARGET}"
    assert_success
    assert_output --partial "will be set to target a ${OTHER_TARGET^^} device"
    assert_output --partial "Warning:"
    run torizoncore-builder-shell "[ -f ${SIGNED_DIR}/tcb_k3_target_device.json ]"
    assert_success
}

@test "secboot sign-bootloader-k3: deploy an image targeting the other kind of device" {
    requires-supported-k3-signing-machine
    requires-signed-image

    local OUTPUT_DIR="k3_retargeted_image"
    rm -rf "${OUTPUT_DIR}"

    torizoncore-builder images --remove-storage unpack "${DEFAULT_SIGNED_TEZI_IMAGE}"

    local CURRENT_VARIANT=$(torizoncore-builder-shell "
        grep -q -- '-hs-fs-' /storage/tezi/image.json && echo hs-fs || echo hs" | tr -d '\r')
    local OTHER_TARGET="hs-se" OTHER_VARIANT="hs"
    if [ "${CURRENT_VARIANT}" = "hs" ]; then
        OTHER_TARGET="hs-fs"
        OTHER_VARIANT="hs-fs"
    fi

    torizoncore-builder secboot sign-bootloader-k3 \
        --k3-key "${K3_KEY}" --target-device "${OTHER_TARGET}"
    torizoncore-builder union k3-retarget-branch
    run torizoncore-builder deploy --output-directory "${OUTPUT_DIR}" k3-retarget-branch
    assert_success
    assert_output --partial "Image set to target a ${OTHER_TARGET^^} device"

    # Every entry that named a container now names the one for the requested kind of device,
    # the file it names is in the image, and the request itself was consumed rather than
    # installed on the device.
    run grep -q -- "-${OTHER_VARIANT}-verdin" "${OUTPUT_DIR}/image.json"
    assert_success
    run grep -q -- "-${CURRENT_VARIANT}-verdin" "${OUTPUT_DIR}/image.json"
    assert_failure
    assert_file_not_exist "${OUTPUT_DIR}/tcb_k3_target_device.json"

    # The size deploy computed for the root file system survived the rewrite, and the images
    # the entries name are in the output.
    run torizoncore-builder-shell "
        python3 -c \"
import json, os
config = json.load(open('/workdir/${OUTPUT_DIR}/image.json'))
sizes, names = [], []
def walk(node):
    if isinstance(node, dict):
        for rawfile in node.get('rawfiles') or []:
            names.append(rawfile['filename'])
        if 'uncompressed_size' in node:
            sizes.append(node['uncompressed_size'])
        for value in node.values():
            walk(value)
    elif isinstance(node, list):
        for value in node:
            walk(value)
walk(config)
assert sizes and all(size > 0 for size in sizes), sizes
for name in names:
    assert os.path.isfile(os.path.join('/workdir/${OUTPUT_DIR}', name)), name
print('ok')
\""
    assert_success

    rm -rf "${OUTPUT_DIR}"
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

@test "secboot sign-kernel: invalid parameters or bad input" {
    # Unpack image so the initial 'images unpack' check passes:
    torizoncore-builder images --remove-storage unpack "${DEFAULT_TEZI_IMAGE}"

    # Switch --kernel-key not specified:
    run torizoncore-builder secboot sign-kernel --kernel-key-dir "${KERNEL_KEY_DIR}"
    assert_failure
    assert_output --partial 'the following arguments are required: --kernel-key'

    # Non-existent kernel FIT image key directory:
    run torizoncore-builder secboot sign-kernel \
        --kernel-key-dir "foo" \
        --kernel-key "name=${KERNEL_KEY_NAME};algo=${KERNEL_KEY_ALGO}"
    assert_failure
    assert_output --partial 'does not exist'

    # Key name that does not match file in key directory:
    run torizoncore-builder secboot sign-kernel \
        --kernel-key-dir "${KERNEL_KEY_DIR}" \
        --kernel-key "name=foo;algo=${KERNEL_KEY_ALGO}"
    assert_failure
    assert_output --regexp "Could not find 'foo.key' in"

    # Invalid --kernel-key format (comma instead of semicolon):
    run torizoncore-builder secboot sign-kernel \
        --kernel-key-dir "${KERNEL_KEY_DIR}" \
        --kernel-key "name=${KERNEL_KEY_NAME},algo=${KERNEL_KEY_ALGO}"
    assert_failure
    assert_output --partial '--kernel-key is not correctly formatted'

    # --kernel-key without name:
    run torizoncore-builder secboot sign-kernel \
        --kernel-key-dir "${KERNEL_KEY_DIR}" \
        --kernel-key "algo=${KERNEL_KEY_ALGO}"
    assert_failure
    assert_output --partial "Could not find value of 'name' in --kernel-key"

    if [ "${DEFAULT_TEZI_IMAGE_HAS_CFS_SUPPORT}" = "1" ]; then
        # Switch --ostree-key-dir passed without --ostree-key being passed:
        run torizoncore-builder secboot sign-kernel \
            --kernel-key-dir "${KERNEL_KEY_DIR}" \
            --kernel-key "name=${KERNEL_KEY_NAME};algo=${KERNEL_KEY_ALGO}" \
            --ostree-key-dir "${SAMPLES_DIR}/signing_keys/ostree-good1/"
        assert_failure
        assert_output --partial 'ostree-key-dir was passed but ostree-key was not provided'

        # Invalid --ostree-key format (comma instead of semicolon):
        run torizoncore-builder secboot sign-kernel \
            --kernel-key-dir "${KERNEL_KEY_DIR}" \
            --kernel-key "name=${KERNEL_KEY_NAME};algo=${KERNEL_KEY_ALGO}" \
            --ostree-key-dir "${SAMPLES_DIR}/signing_keys/ostree-good1/" \
            --ostree-key "name=cfs-dev,algo=ed25519"
        assert_failure
        assert_output --regexp 'The ostree-key parameter is not correctly formatted'

        # Non-existing ostree-key-dir passed:
        run torizoncore-builder secboot sign-kernel \
            --kernel-key-dir "${KERNEL_KEY_DIR}" \
            --kernel-key "name=${KERNEL_KEY_NAME};algo=${KERNEL_KEY_ALGO}" \
            --ostree-key-dir "${SAMPLES_DIR}/signing_keys/dummy-dir/" \
            --ostree-key "name=cfs-dev;algo=ed25519"
        assert_failure
        assert_output --regexp 'OSTree keys directory .*dummy-dir.* does not exist.'

        # Bad key name passed, no algorithm passed:
        run torizoncore-builder secboot sign-kernel \
            --kernel-key-dir "${KERNEL_KEY_DIR}" \
            --kernel-key "name=${KERNEL_KEY_NAME};algo=${KERNEL_KEY_ALGO}" \
            --ostree-key-dir "${SAMPLES_DIR}/signing_keys/ostree-good1/" \
            --ostree-key "name=badkey"
        assert_failure
        assert_output --partial "Could not find value of 'algo' in the ostree-key parameter; defaulting to"
        assert_output --partial 'Cannot read public key file'
    else
        # Switch --ostree-key passed for an image having no composefs support:
        run torizoncore-builder secboot sign-kernel \
            --kernel-key-dir "${KERNEL_KEY_DIR}" \
            --kernel-key "name=${KERNEL_KEY_NAME};algo=${KERNEL_KEY_ALGO}" \
            --ostree-key-dir "${SAMPLES_DIR}/signing_keys/ostree-good1/" \
            --ostree-key "name=cfs-dev;algo=ed25519"
        assert_failure
        assert_output --partial 'ostree-key parameter has been passed for an image that has no support for the root filesystem protection.'
    fi
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
    assert_output --partial "Updating FIT image configurations to be signed with key name \"${KERNEL_KEY_NAME}\""
    assert_output --regexp "Signing kernel FIT image with .* algorithm: ${KERNEL_KEY_ALGO}"
    assert_output --partial 'Kernel FIT image signed successfully'
    assert_output --partial 'Kernel in unpacked Torizon OS image signed successfully'

    run torizoncore-builder-shell "ls -l /storage/kernel/usr/lib/modules/*/vmlinuz"
    assert_success

    torizoncore-builder-clean-storage

    # Run with --kernel-key parameters separated with space (should still work).
    # Also check passing an ostree signing key to update the ramdisk.
    torizoncore-builder images --remove-storage unpack "${DEFAULT_SIGNED_TEZI_IMAGE}"

    local cfs_support="$(cfs-support-flag)"

    run torizoncore-builder secboot sign-kernel \
        --kernel-key-dir "${KERNEL_KEY_DIR}" \
        --kernel-key "name = ${KERNEL_KEY_NAME}; algo = ${KERNEL_KEY_ALGO}" \
        ${cfs_support:+
          --ostree-key-dir "${SAMPLES_DIR}/signing_keys/ostree-good1/"
          --ostree-key "name=cfs-dev;algo=ed25519"}
    assert_success
    assert_output --partial "Updating FIT image configurations to be signed with key name \"${KERNEL_KEY_NAME}\""
    assert_output --regexp "Signing kernel FIT image with .* algorithm: ${KERNEL_KEY_ALGO}"
    assert_output --partial 'Kernel FIT image signed successfully'
    assert_output --partial 'Kernel in unpacked Torizon OS image signed successfully'

    if [ "${DEFAULT_TEZI_IMAGE_HAS_CFS_SUPPORT}" = "1" ]; then
        assert_output --partial 'Public OSTree binding key successfully updated in initramfs'
    else
        refute_output --partial 'Public OSTree binding key successfully updated in initramfs'
    fi

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
