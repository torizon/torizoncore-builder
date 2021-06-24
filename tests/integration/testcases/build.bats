load 'bats/bats-support/load.bash'
load 'bats/bats-assert/load.bash'
load 'bats/bats-file/load.bash'
load 'lib/common.bash'

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
    local FNAME="$SAMPLES_DIR/config/tcbuild-with-validation-errors.yaml"
    run torizoncore-builder build --file "$FNAME"
    assert_failure
    assert_output --partial 'errors found'
    assert_output --partial 'while parsing /input'
    assert_output --partial 'while parsing /customization/splash-screen'
    assert_output --partial 'while parsing /customization/filesystem/0'
    assert_output --partial 'while parsing /customization/filesystem/1'
    assert_output --partial 'while parsing /customization/device-tree/include-dirs'
    assert_output --partial 'while parsing /customization/device-tree/overlays/clear'
}

@test "build: config file with variables" {
    local FNAME="$SAMPLES_DIR/config/tcbuild-with-variables.yaml"
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

@test "build: full customization checked on host" {
    requires-image-version "$DEFAULT_TEZI_IMAGE" "5.3.0"

    local OUTDIR='fully_customized_image'
    run torizoncore-builder build \
        --file samples/config/tcbuild-full-customization.yaml \
        --set INPUT_IMAGE="$DEFAULT_TEZI_IMAGE" \
        --set OUTPUT_DIR="$OUTDIR" --force

    assert_success
    assert_output --partial 'splash screen merged'
    assert_output --partial 'Overlay sample_overlay.dtbo successfully applied.'
    assert_output --partial 'Overlay custom-kargs_overlay.dtbo successfully applied.'
    assert_output --partial \
        'Kernel custom arguments successfully configured with "key1=val1 key2=val2".'
    assert_output --partial 'Deploying commit ref: my-dev-branch'

    local ARCHIVE='/storage/ostree-archive/'
    local COMMIT='my-dev-branch'

    # TODO: Check customization/splash-screen:

    # Check customization/filesystem prop:
    local CFGFILE='/usr/etc/myconfig.txt'
    run torizoncore-builder-shell "ostree --repo=$ARCHIVE ls $COMMIT $CFGFILE"
    assert_success

    # Check customization/device-tree/add prop:
    local COMMIT='my-dev-branch'
    local OVLFILE='overlays.txt'
    local MODDIR='/usr/lib/modules'
    run torizoncore-builder-shell \
        "ostree --repo=$ARCHIVE ls -R $COMMIT $MODDIR | grep $OVLFILE"
    assert_success
    assert_output --partial "$MODDIR"

    local OVFILE_FULL="$(echo $output | sed -nE 's#^.*(/usr/lib/modules/.*)$#\1#p')"
    run torizoncore-builder-shell \
        "ostree --repo=$ARCHIVE cat $COMMIT $OVFILE_FULL"
    assert_output --partial 'sample_overlay.dtbo'

    # Check customization/kernel/arguments prop (presence of overlay only):
    assert_output --partial 'custom-kargs_overlay.dtbo'

    # Check output/ostree/commit-{subject,body} props:
    run torizoncore-builder-shell "ostree --repo=$ARCHIVE log $COMMIT"
    assert_output --partial 'full-customization subject'
    assert_output --partial 'full-customization body'

    # Check output/easy-installer/{name,description,licence,release-notes}:
    run cat "$OUTDIR/image.json"
    assert_output --partial '"name": "fully-customized image"'
    assert_output --partial '"description": "fully-customized image description"'
    assert_output --partial '"license": "license-fc.html"'
    assert_output --partial '"releasenotes": "release-notes-fc.html"'

    # Check presence of container:
    run [ -e "$OUTDIR/docker-storage.tar.xz" -a -e "$OUTDIR/docker-compose.yml" ]
    assert_success
}

@test "build: full customization checked on device" {
    requires-image-version "$DEFAULT_TEZI_IMAGE" "5.3.0"
    requires-device

    # This test case assumes the previous one was executed.
    local COMMIT='my-dev-branch'
    local ARCHIVE='/storage/ostree-archive/'

    # Deploy custom image.
    run torizoncore-builder deploy \
        --remote-host "$DEVICE_ADDR" --remote-username "$DEVICE_USER" \
        --remote-password "$DEVICE_PASS" --reboot "$COMMIT"
    assert_success
    assert_output --partial "Deploying successfully finished"

    run device-wait 20
    assert_success

    # TODO: Check customization/splash-screen:

    # Check customization/filesystem prop:
    local CFGFILE='/usr/etc/myconfig.txt'
    run device-shell-root cat "$CFGFILE"
    assert_success

    # Check customization/device-tree/add prop:
    run device-shell-root cat '/usr/lib/modules/$(uname -r)/dtb/overlays.txt'
    assert_success
    assert_output --partial 'sample_overlay.dtbo'

    # Check customization/kernel/arguments prop (presence of overlay only):
    assert_output --partial 'custom-kargs_overlay.dtbo'

    # Determine commit ID in local repo.
    run torizoncore-builder-shell \
        "ostree --repo=$ARCHIVE log $COMMIT | sed -nE 's#^commit +([0-9a-f]+).*#\1#p' | head -n1"
    assert_success
    local COMMITID="$output"

    # Check output/ostree/commit-{subject,body} props:
    run device-shell-root ostree log "$COMMITID"
    assert_success
    assert_output --partial 'full-customization subject'
    assert_output --partial 'full-customization body'

    # Check customization/kernel/arguments prop (actual arguments):
    run device-shell-root cat /proc/cmdline
    assert_success
    assert_output --partial 'key1=val1'
    assert_output --partial 'key2=val2'
}
