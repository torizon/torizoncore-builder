bats_load_library 'bats/bats-support/load.bash'
bats_load_library 'bats/bats-assert/load.bash'
bats_load_library 'bats/bats-file/load.bash'
load '../lib/registries.sh'
load '../lib/common.bash'

teardown_file() {
    stop-registries
}

@test "build: check help output" {
    run torizoncore-builder build --help
    assert_success
    assert_output --partial 'usage: torizoncore-builder build'
}

@test "build: template creation" {
    # Test with default file name:
    local FNAME='tcbuild.yaml'
    rm -f "$FNAME"
    run torizoncore-builder build --create-template
    assert_success
    assert_output --partial "Creating template file '$FNAME'"
    check-file-ownership-as-workdir "$FNAME"
    rm -f "$FNAME"

    # Test with custom file name:
    local FNAME='tcbuild-new.yaml'
    rm -f "$FNAME"
    run torizoncore-builder build --create-template --file "$FNAME"
    assert_success
    assert_output --partial "Creating template file '$FNAME'"
    check-file-ownership-as-workdir $FNAME
    rm -f "$FNAME"

    # Test sending template to stdout:
    run torizoncore-builder build --create-template --file "-"
    # Check main sections of the file:
    assert_success
    assert_output --partial 'input:'
    assert_output --partial '# customization:'
    assert_output --partial 'output:'
}

@test "build: config file with error detected by YAML parser" {
    local FNAME="$SAMPLES_DIR/config/tcbuild-with-yaml-error.yaml"
    run torizoncore-builder build --file "$FNAME"
    assert_failure
    assert_output --partial "errors found"
    assert_output --partial "expected alphabetic"
}

@test "build: config file with multiple validation errors" {
    local FNAME="$SAMPLES_DIR/config/wic-tcbuild-with-validation-errors.yaml"
    run torizoncore-builder build --file "$FNAME"
    assert_failure
    assert_output --partial 'errors found'
    assert_output --partial 'while parsing /input'
    assert_output --partial 'while parsing /customization/splash-screen'
    assert_output --partial 'while parsing /customization/filesystem/0'
    assert_output --partial 'while parsing /customization/filesystem/1'
    assert_output --partial 'while parsing /output'
}

@test "build: config file with variables" {
    local FNAME="$SAMPLES_DIR/config/wic-tcbuild-with-variables.yaml"
    run torizoncore-builder build --file "$FNAME"
    assert_failure
    assert_output --partial 'EMPTY_VAR is not set'
    assert_output --partial 'No body message'

    local FNAME="$SAMPLES_DIR/config/tcbuild-with-variables.yaml"
    run torizoncore-builder build --file "$FNAME" --set BODY='this-is-a-body-message'
    assert_failure
    assert_output --partial 'EMPTY_VAR is not set'
    refute_output --partial 'No body message'
}

@test "build: invalid rootfs label" {
    local FNAME="$SAMPLES_DIR/config/wic-tcbuild-invalid-input-rootfs-label.yaml"
    run torizoncore-builder build --file "$FNAME" --set INPUT_IMAGE="$DEFAULT_WIC_IMAGE"
    assert_failure
    assert_output --partial "Filesystem with label 'invalidlabel' not found in image"

    local FNAME="$SAMPLES_DIR/config/wic-tcbuild-invalid-output-rootfs-label.yaml"
    run torizoncore-builder build --file "$FNAME" --set INPUT_IMAGE="$DEFAULT_WIC_IMAGE"
    assert_failure
    assert_output --partial "Handling output section"
    assert_output --partial "Filesystem with label 'invalidlabel' not found in image"
}

@test "build: invalid base image" {
    local FNAME="$SAMPLES_DIR/config/wic-tcbuild-invalid-base-image.yaml"
    run torizoncore-builder build --file "$FNAME" --set INPUT_IMAGE="$DEFAULT_WIC_IMAGE"
    assert_failure
    assert_output --partial "Handling output section"
    assert_output --partial "invalidbase.wic: No such file or directory"
}

@test "build: basic customization checked on host" {

    local OUTFILE='basic_image.wic'
    run torizoncore-builder build \
        --file "$SAMPLES_DIR/config/wic-tcbuild-basic-customization.yaml" \
        --set INPUT_IMAGE="$DEFAULT_WIC_IMAGE" \
        --set OUTPUT_FILE="$OUTFILE" --force

    assert_success
    assert_output --partial 'splash screen merged'
    assert_output --partial 'Deploying commit ref: my-raw-image-branch'
    assert_output --partial "created successfully"

    local ARCHIVE='/storage/ostree-archive/'
    local COMMIT='my-raw-image-branch'

    # TODO: Check customization/splash-screen:

    # Check customization/filesystem prop:
    local CFGFILE='/usr/etc/myconfig.txt'
    run torizoncore-builder-shell "ostree --repo=$ARCHIVE ls $COMMIT $CFGFILE"
    assert_success

    # Check output/ostree/commit-{subject,body} props:
    run torizoncore-builder-shell "ostree --repo=$ARCHIVE log $COMMIT"
    assert_output --partial 'basic-customization subject'
    assert_output --partial 'basic-customization body'

    # Check the ostree branch ref-binding:
    run torizoncore-builder-shell \
      "ostree --repo=$ARCHIVE show --print-metadata-key='ostree.ref-binding' $COMMIT"
    assert_success
    assert_output --partial "['$COMMIT']"
}

# bats test_tags=requires-device
@test "build: basic customization checked on device" {
    requires-device

    # This test case assumes the previous one was executed.
    local COMMIT='my-raw-image-branch'
    local ARCHIVE='/storage/ostree-archive/'

    # Deploy custom image.
    run torizoncore-builder deploy --remote-host "$DEVICE_ADDR" \
                                   --remote-username "$DEVICE_USER" \
                                   --remote-password "$DEVICE_PASS" \
                                   --remote-port "$DEVICE_PORT" \
                                   --reboot "$COMMIT"
    assert_success
    assert_output --partial "Deploying successfully finished"

    run device-wait 20
    assert_success

    # TODO: Check customization/splash-screen:

    # Check customization/filesystem prop:
    local CFGFILE='/usr/etc/myconfig.txt'
    run device-shell-root cat "$CFGFILE"
    assert_success

    # Determine commit ID in local repo.
    run torizoncore-builder-shell \
        "ostree --repo=$ARCHIVE log $COMMIT | sed -nE 's#^commit +([0-9a-f]+).*#\1#p' | head -n1"
    assert_success
    local COMMITID="$output"

    # Check output/ostree/commit-{subject,body} props:
    run device-shell-root ostree log "$COMMITID"
    assert_success
    assert_output --partial 'basic-customization subject'
    assert_output --partial 'basic-customization body'
}
