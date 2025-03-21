bats_load_library 'bats/bats-support/load.bash'
bats_load_library 'bats/bats-assert/load.bash'
bats_load_library 'bats/bats-file/load.bash'

@test "ubootenv: check help output" {
    run torizoncore-builder ubootenv --help
    assert_success
    assert_output --partial ' {fuses}'
}

@test "ubootenv fuses: basic tests" {
    unpack-image "$DEFAULT_TEZI_IMAGE"
    local INPUT_IMAGE_DIR=$(echo $DEFAULT_TEZI_IMAGE | sed 's/\.tar$//g')
    local OUTPUT_IMAGE_DIR="${INPUT_IMAGE_DIR}.FUSES"
    local FUSE_DIR="$SAMPLES_DIR/push/fuse"
    local FUSE_FILE=""
    local FUSE_SUPPORTED="true"
    case "$INPUT_IMAGE_DIR" in
        *apalis-imx8*|*colibri-imx8x*)
            FUSE_FILE="$FUSE_DIR/fuse-non-canon-16.yaml"
            ;;
        *imx6*|*imx7*|*imx6ull*|*imx8mm*|*imx8mp*)
            FUSE_FILE="$FUSE_DIR/fuse-non-canon-8.yaml"
            ;;
        *)
            # Just use whatever fuse file here 
            FUSE_FILE="$FUSE_DIR/fuse-non-canon-16.yaml"
            FUSE_SUPPORTED="false"
            ;;
    esac

    # no arguments passed
    run torizoncore-builder ubootenv fuses
    assert_failure
    assert_output --partial \
        'the following arguments are required: INPUT_DIRECTORY, OUTPUT_DIRECTORY, --fuse-file'

    # input directory does not exist
    run torizoncore-builder ubootenv fuses "foo" "$OUTPUT_IMAGE_DIR" \
    --fuse-file "$FUSE_FILE"
    assert_failure
    assert_output --partial 'does not exist'

    # output directory already exists
    mkdir -p "${OUTPUT_IMAGE_DIR}"
    run torizoncore-builder ubootenv fuses "$INPUT_IMAGE_DIR" "$OUTPUT_IMAGE_DIR" \
    --fuse-file "$FUSE_FILE"
    assert_failure
    assert_output --partial 'already exists'
    rm -rf "${OUTPUT_IMAGE_DIR}"

    # fuse file does not exist
    run torizoncore-builder ubootenv fuses "$INPUT_IMAGE_DIR" "$OUTPUT_IMAGE_DIR" \
    --fuse-file "foo"
    assert_failure
    assert_output --partial 'does not exist'

    # normal success
    if [ "$FUSE_SUPPORTED" = "true" ]; then
        run torizoncore-builder ubootenv fuses "$INPUT_IMAGE_DIR" "$OUTPUT_IMAGE_DIR" \
        --fuse-file "$FUSE_FILE"
        assert_success
        assert_output --partial 'variables successfully added to image'

        run grep -r "fuse_status" "$OUTPUT_IMAGE_DIR"
        assert_success
        assert_output --partial 'fuse_status=pending'

        # image already containing fuse data
        run torizoncore-builder ubootenv fuses "$OUTPUT_IMAGE_DIR" "temp" \
        --fuse-file "$FUSE_FILE"
        assert_failure
        assert_output --partial 'already contains fuse related'
        rm -rf temp
    fi

    # hardware not supported
    if [ "$FUSE_SUPPORTED" = "false" ]; then
        run torizoncore-builder ubootenv fuses "$INPUT_IMAGE_DIR" "$OUTPUT_IMAGE_DIR" \
        --fuse-file "$FUSE_FILE"
        assert_failure
        assert_output --partial 'is not supported by this command'
    fi

    rm -f "${FUSE_DIR}/fuse-non-canon-8.lock.yaml"
    rm -f "${FUSE_DIR}/fuse-non-canon-16.lock.yaml"
}
