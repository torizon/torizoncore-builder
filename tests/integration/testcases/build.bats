bats_load_library 'bats/bats-support/load.bash'
bats_load_library 'bats/bats-assert/load.bash'
bats_load_library 'bats/bats-file/load.bash'
load 'lib/registries.sh'
load 'lib/common.bash'

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
    rm -rf dummy_output_directory
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
    rm -rf dummy_output_directory
}

@test "build: config file with variables in input section" {
    rm -rf dummy_output_directory
    run torizoncore-builder build \
        --file "$SAMPLES_DIR/config/tcbuild-with-variables2.yaml" \
        --set VERSION=5.0.0 --set RELEASE=quarterly \
        --set MACHINE=colibri-imx6 --set DISTRO=torizon-upstream \
        --set VARIANT=torizon-core-docker --set BUILD_NUMBER=1
    assert_failure
    refute_output --partial 'is not valid under any of the given schemas'
    assert_output --partial 'Error: Could not fetch URL'
    rm -rf dummy_output_directory
}

@test "build: full customization checked on host" {
    requires-image-version "$DEFAULT_TEZI_IMAGE" "5.3.0"

    local OUTDIR='fully_customized_image'
    run torizoncore-builder build \
        --file "$SAMPLES_DIR/config/tcbuild-full-customization.yaml" \
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

    # Check the ostree branch ref-binding:
    run torizoncore-builder-shell \
      "ostree --repo=$ARCHIVE show --print-metadata-key='ostree.ref-binding' $COMMIT"
    assert_success
    assert_output --partial "['$COMMIT']"
}

# bats test_tags=requires-device
@test "build: full customization checked on device" {
    requires-image-version "$DEFAULT_TEZI_IMAGE" "5.3.0"
    requires-device

    local OUTDIR='fully_customized_image'
    run torizoncore-builder build \
        --file "$SAMPLES_DIR/config/tcbuild-full-customization.yaml" \
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

    # Check output/easy-installer/{name,description,licence,release-notes}:
    run cat "$OUTDIR/image.json"
    assert_output --partial '"name": "fully-customized image"'
    assert_output --partial '"description": "fully-customized image description"'
    assert_output --partial '"license": "license-fc.html"'
    assert_output --partial '"releasenotes": "release-notes-fc.html"'

    # Check presence of container:
    run [ -e "$OUTDIR/docker-storage.tar.xz" -a -e "$OUTDIR/docker-compose.yml" ]
    assert_success

    # Deploy custom image.
    run torizoncore-builder deploy --remote-host "$DEVICE_ADDR" \
                                   --remote-username "$DEVICE_USER" \
                                   --remote-password "$DEVICE_PASSWORD" \
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

@test "build: config file with autoinstall and autoreboot" {
    local DUMMY_OUTPUT="dummy_output_directory"
    rm -rf $DUMMY_OUTPUT

    # Check if licence is present in the image.
    local licence=$(torizoncore-builder-shell "grep -E \
                  -e '\s*\"license\"\s*:\s*\".*\"\s*,' /storage/tezi/image.json")

    if [ -n "$licence" ]; then
      licence=$(echo "$licence" | sed -En -e 's/\s*\"license\":\s*\"(.*)\",/\1/p')
      run torizoncore-builder build \
          --file "$SAMPLES_DIR/config/tcbuild-with-autoinstall.yaml" \
          --set INPUT_IMAGE="$DEFAULT_TEZI_IMAGE"
      assert_failure
      assert_output --partial \
          "Error: To enable the auto-installation feature you must accept the licence \"$licence\""
    fi

    # Enable `accept-licence`
    cat "$SAMPLES_DIR/config/tcbuild-with-autoinstall.yaml" | \
              sed -Ee 's/## accept-licence/accept-licence/' > \
              "$SAMPLES_DIR/config/tcbuild-with-accept.yaml"

    run torizoncore-builder build \
          --file "$SAMPLES_DIR/config/tcbuild-with-accept.yaml" \
          --set INPUT_IMAGE="$DEFAULT_TEZI_IMAGE"
    assert_success

    run grep autoinstall $DUMMY_OUTPUT/image.json
    assert_output --partial "true"
    run grep -E '^\s*reboot\s+-f\s*#\s*torizoncore-builder\s+generated' $DUMMY_OUTPUT/wrapup.sh
    assert_success

    rm -rf "$DUMMY_OUTPUT"
}

@test "build: check overlays's clear" {
    local OVERLAY_IMAGE="overlay_image"
    local DUMMY_OUTPUT="dummy_output_directory"

    rm -rf $DUMMY_OUTPUT $OVERLAY_IMAGE

    torizoncore-builder-clean-storage

    # Create input image, clearing all overlays and adding 2 dummy overlays.
    cat "$SAMPLES_DIR/config/tcbuild-with-clear.yaml" | \
              sed -Ee 's/## add:/add:/' \
                  -Ee '/\badd:/ s/sample_overlay2/sample_overlay/' \
                  -Ee '/\badd:/ s@]@, samples/dts/sample_overlay1.dts]@' > \
              "$SAMPLES_DIR/config/tcbuild-modified.yaml"

    run torizoncore-builder build \
              --file "$SAMPLES_DIR/config/tcbuild-modified.yaml" \
              --set INPUT_IMAGE="$DEFAULT_TEZI_IMAGE" \
              --set OUTPUT_DIR="$OVERLAY_IMAGE" --force
    assert_success

    # Check if only the 2 dummy overlays are present.
    run torizoncore-builder dto status
    assert_success
    local actual_result=$(echo "$output" | sed -En -e 's/^\s*-\s*(\S+)\.dtbo/\1/p' | tr -s '\n\r' '  ')
    local expect_result="sample_overlay sample_overlay1 "
    assert_equal "$actual_result" "$expect_result"

    # Test with clear as true, Adding just one overlay.
    cat "$SAMPLES_DIR/config/tcbuild-with-clear.yaml" | \
              sed -Ee 's/## add:/add:/' > \
              "$SAMPLES_DIR/config/tcbuild-clear-true.yaml"

    run torizoncore-builder build \
            --file "$SAMPLES_DIR/config/tcbuild-clear-true.yaml" \
            --set INPUT_IMAGE="$OVERLAY_IMAGE" \
            --set OUTPUT_DIR="$DUMMY_OUTPUT" --force
    assert_success

    # Check if only the added overlay is available.
    run torizoncore-builder dto status
    assert_success
    actual_result=$(echo "$output" | sed -En -e 's/^\s*-\s*(\S+)\.dtbo/\1/p' | tr -s '\n\r' '  ')
    expect_result="sample_overlay2 "
    assert_equal "$actual_result" "$expect_result"

    # Test with clear as false, no image added.
    cat "$SAMPLES_DIR/config/tcbuild-with-clear.yaml" | \
              sed -Ee 's/\bclear:\s*true/clear: false/' \
                  -Ee 's/## add:/add:/' > \
              "$SAMPLES_DIR/config/tcbuild-clear-false.yaml"

    run torizoncore-builder build \
            --file "$SAMPLES_DIR/config/tcbuild-clear-false.yaml" \
            --set INPUT_IMAGE="$OVERLAY_IMAGE" \
            --set OUTPUT_DIR="$DUMMY_OUTPUT" --force
    assert_success

    # Check if both base overlays are present.
    run torizoncore-builder dto status
    assert_success
    actual_result=$(echo "$output" | sed -En -e 's/^\s*-\s*(\S+)\.dtbo/\1/p' | tr -s '\n\r' '  ')
    expect_result="sample_overlay sample_overlay1 sample_overlay2 "
    assert_equal "$actual_result" "$expect_result"

    # Test with clear as default, adding one image.
    cat "$SAMPLES_DIR/config/tcbuild-with-clear.yaml" | \
          sed -Ee '/\bclear:\s*true/d' -Ee 's/## add:/add:/' > \
          "$SAMPLES_DIR/config/tcbuild-clear-default.yaml"

    run torizoncore-builder build \
            --file "$SAMPLES_DIR/config/tcbuild-clear-default.yaml" \
            --set INPUT_IMAGE="$OVERLAY_IMAGE" \
            --set OUTPUT_DIR="$DUMMY_OUTPUT" --force
    assert_success

    # Check if initial overlays and the added one are present.
    run torizoncore-builder dto status
    assert_success
    actual_result=$(echo "$output" | sed -En -e 's/^\s*-\s*(\S+)\.dtbo/\1/p' | tr -s '\n\r' '  ')
    expect_result="sample_overlay sample_overlay1 sample_overlay2 "
    assert_equal "$actual_result" "$expect_result"

    rm -rf $DUMMY_OUTPUT $OVERLAY_IMAGE
}

@test "build: basic tcbuild referencing a docker-compose file" {
    local ci_dockerhub_login="$(ci-dockerhub-login-flag)"

    local COMPOSE='docker-compose.yml'
    cp "$SAMPLES_DIR/compose/hello/docker-compose.yml" "$COMPOSE"

    local OUTDIR='customized_image'
    local FILE="$SAMPLES_DIR/config/tcbuild-with-compose.yaml"


    if [ "${ci_dockerhub_login}" = "1" ]; then
        cat "$SAMPLES_DIR/config/tcbuild-with-compose.yaml" | \
              sed -Ee 's/## username:/username:/' \
                  -Ee 's/## password:/password:/' > \
              "$SAMPLES_DIR/config/tcbuild-with-compose-login.yaml"
        FILE="$SAMPLES_DIR/config/tcbuild-with-compose-login.yaml"
    fi

    run torizoncore-builder build \
        --file "$FILE" --force \
        --set INPUT_IMAGE="$DEFAULT_TEZI_IMAGE" \
        --set OUTPUT_DIR="$OUTDIR" \
        --set COMPOSE_FILE="$COMPOSE" \
        ${ci_dockerhub_login:+--set "USERNAME=${CI_DOCKER_HUB_PULL_USER}"
                 --set "PASSWORD=${CI_DOCKER_HUB_PULL_PASSWORD}"}

    assert_success
    assert_output --partial 'Connecting to Docker Daemon'

    if [ "${ci_dockerhub_login}" = "1" ]; then
        assert_output --partial "Attempting to log in to"
    fi

    # Check presence of container:
    run [ -e "$OUTDIR/docker-storage.tar.xz" -a -e "$OUTDIR/docker-compose.yml" ]
    assert_success
    rm -fr "$OUTDIR"
}

@test "build: check with secure registry with authentication" {
    local SR_COMPOSE_FOLDER="${SAMPLES_DIR}/compose/secure-registry"
    local COMPOSE="${SR_COMPOSE_FOLDER}/docker-compose.yml"
    local OUTDIR="customized_image"
    local FILE="${SAMPLES_DIR}/config/tcbuild-with-cacert-registry.yaml"
    local USERNAME="toradex"
    local PASSWORD="test"
    local REGISTRY="${SR_WITH_AUTH_IP}"
    local CA_CERTIFICATE="${SR_WITH_AUTH_CERTS}/cacert.crt"

    rm -fr "$OUTDIR"
    # At the time of writing, this is the only testcase in this module that requires the registries
    # to be running; because of that we start the registry here. Later if we have more testcases
    # requiring the registries we may consider moving the call to start-registries to a setup_file()
    # function.
    start-registries || true
    run check-registries
    assert_success

    cp "${SR_COMPOSE_FOLDER}/docker-compose-sr-only.yml" "${COMPOSE}"

    sed -i -E -e "s/# @NAME1@/test/" \
              -e "s/# image: @IMAGE5@/ image: ${SR_WITH_AUTH_IP}\/test1/" \
              "${COMPOSE}"

    run torizoncore-builder build \
        --file "$FILE" --force \
        --set "INPUT_IMAGE=$DEFAULT_TEZI_IMAGE" \
        --set "OUTPUT_DIR=$OUTDIR" \
        --set "COMPOSE_FILE=$COMPOSE" \
        --set "USERNAME=$USERNAME" \
        --set "PASSWORD=$PASSWORD" \
        --set "REGISTRY=$REGISTRY" \
        --set "CA_CERTIFICATE=$CA_CERTIFICATE"

    assert_success
    assert_output --partial "Fetching container image ${SR_WITH_AUTH_IP}/test"
    assert_output --partial "Connecting to Docker Daemon"
    assert_output --partial "Attempting to log in to"

    # Check presence of container:
    run [ -e "${OUTDIR}/docker-storage.tar.xz" -a -e "${OUTDIR}/docker-compose.yml" ]
    assert_success
    rm -fr "$OUTDIR"
}
