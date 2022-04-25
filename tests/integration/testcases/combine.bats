load 'bats/bats-support/load.bash'
load 'bats/bats-assert/load.bash'
load 'bats/bats-file/load.bash'
load 'lib/common.bash'


@test "combine: check if image directory has a valid tezi image" {
    local COMPOSE='docker-compose.yml'
    if [ "$TCB_UNDER_CI" = "1" ]; then
        cp "$SAMPLES_DIR/compose/hello/docker-compose-proxy.yml" "$COMPOSE"
    else
        cp "$SAMPLES_DIR/compose/hello/docker-compose.yml" "$COMPOSE"
    fi
    rm -rf bundle
    torizoncore-builder bundle $COMPOSE

    local FILES="image.json *.zst"
    for FILE in $FILES
    do
        unpack-image $DEFAULT_TEZI_IMAGE
        local IMAGE_DIR=$(echo $DEFAULT_TEZI_IMAGE | sed 's/\.tar$//g')
        local OUTPUT_DIR=$(mktemp -d tmpdir.XXXXXXXXXXXXXXXXXXXXXXXXX)
        rm $IMAGE_DIR/$FILE

        run torizoncore-builder combine $IMAGE_DIR $OUTPUT_DIR
        assert_failure
        assert_output --partial "Error: directory $IMAGE_DIR does not contain a valid TEZI image"

        rm -rf "$IMAGE_DIR" "$OUTPUT_DIR"
    done

    rm -rf "$COMPOSE" bundle
}

@test "combine: run with the deprecated --image-directory switch" {
    local COMPOSE='docker-compose.yml'
    if [ "$TCB_UNDER_CI" = "1" ]; then
        cp "$SAMPLES_DIR/compose/hello/docker-compose-proxy.yml" "$COMPOSE"
    else
        cp "$SAMPLES_DIR/compose/hello/docker-compose.yml" "$COMPOSE"
    fi

    rm -rf bundle
    torizoncore-builder bundle $COMPOSE

    unpack-image $DEFAULT_TEZI_IMAGE
    local IMAGE_DIR=$(echo $DEFAULT_TEZI_IMAGE | sed 's/\.tar$//g')
    local OUTPUT_DIR=$(mktemp -d tmpdir.XXXXXXXXXXXXXXXXXXXXXXXXX)

    run torizoncore-builder combine --image-directory $IMAGE_DIR \
                                    $OUTPUT_DIR
    assert_failure
    assert_output --partial "Error: the switch --image-directory has been removed"
    assert_output --partial "please provide the image directory without passing the switch."

    rm -rf "$COMPOSE" bundle "$OUTPUT_DIR" "$IMAGE_DIR"
}

@test "combine: run with the deprecated --output-directory switch" {
    local COMPOSE='docker-compose.yml'
    if [ "$TCB_UNDER_CI" = "1" ]; then
        cp "$SAMPLES_DIR/compose/hello/docker-compose-proxy.yml" "$COMPOSE"
    else
        cp "$SAMPLES_DIR/compose/hello/docker-compose.yml" "$COMPOSE"
    fi

    rm -rf bundle
    torizoncore-builder bundle $COMPOSE

    unpack-image $DEFAULT_TEZI_IMAGE
    local IMAGE_DIR=$(echo $DEFAULT_TEZI_IMAGE | sed 's/\.tar$//g')
    local OUTPUT_DIR=$(mktemp -d tmpdir.XXXXXXXXXXXXXXXXXXXXXXXXX)

    run torizoncore-builder combine $IMAGE_DIR \
                                    --output-directory $OUTPUT_DIR
    assert_failure
    assert_output --partial "Error: the switch --output-directory has been removed"
    assert_output --partial "please provide the output directory without passing the switch."

    rm -rf "$COMPOSE" bundle "$OUTPUT_DIR" "$IMAGE_DIR"
}

@test "combine: check without --bundle-directory parameter" {
    local COMPOSE='docker-compose.yml'
    if [ "$TCB_UNDER_CI" = "1" ]; then
        cp "$SAMPLES_DIR/compose/hello/docker-compose-proxy.yml" "$COMPOSE"
    else
        cp "$SAMPLES_DIR/compose/hello/docker-compose.yml" "$COMPOSE"
    fi

    rm -rf bundle
    torizoncore-builder bundle $COMPOSE

    unpack-image $DEFAULT_TEZI_IMAGE
    local IMAGE_DIR=$(echo $DEFAULT_TEZI_IMAGE | sed 's/\.tar$//g')
    local OUTPUT_DIR=$(mktemp -d -u tmpdir.XXXXXXXXXXXXXXXXXXXXXXXXX)

    run torizoncore-builder combine $IMAGE_DIR $OUTPUT_DIR
    assert_success
    run ls -l $OUTPUT_DIR/$COMPOSE
    assert_success

    check-file-ownership-as-workdir "$OUTPUT_DIR"

    rm -rf "$COMPOSE" bundle "$OUTPUT_DIR" "$IMAGE_DIR"
}

@test "combine: check with --bundle-directory parameters" {
    local COMPOSE='docker-compose.yml'
    if [ "$TCB_UNDER_CI" = "1" ]; then
        cp "$SAMPLES_DIR/compose/hello/docker-compose-proxy.yml" "$COMPOSE"
    else
        cp "$SAMPLES_DIR/compose/hello/docker-compose.yml" "$COMPOSE"
    fi
    local BUNDLE_DIR=$(mktemp -d -u tmpdir.XXXXXXXXXXXXXXXXXXXXXXXXX)

    torizoncore-builder bundle --bundle-directory $BUNDLE_DIR $COMPOSE

    unpack-image $DEFAULT_TEZI_IMAGE
    local IMAGE_DIR=$(echo $DEFAULT_TEZI_IMAGE | sed 's/\.tar$//g')
    local OUTPUT_DIR=$(mktemp -d -u tmpdir.XXXXXXXXXXXXXXXXXXXXXXXXX)

    run torizoncore-builder combine --bundle-directory $BUNDLE_DIR \
                                    $IMAGE_DIR $OUTPUT_DIR
    assert_success
    run ls -l $OUTPUT_DIR/$COMPOSE
    assert_success

    check-file-ownership-as-workdir "$OUTPUT_DIR"

    rm -rf "$COMPOSE" "$BUNDLE_DIR" "$OUTPUT_DIR" "$IMAGE_DIR"
}

@test "combine: check with --image-autoinstall" {
  local COMPOSE='docker-compose.yml'
  if [ "$TCB_UNDER_CI" = "1" ]; then
    cp "$SAMPLES_DIR/compose/hello/docker-compose-proxy.yml" "$COMPOSE"
  else
    cp "$SAMPLES_DIR/compose/hello/docker-compose.yml" "$COMPOSE"
  fi

  rm -rf bundle
  torizoncore-builder bundle $COMPOSE

  unpack-image $DEFAULT_TEZI_IMAGE
  local IMAGE_DIR=$(echo $DEFAULT_TEZI_IMAGE | sed 's/\.tar$//g')
  local OUTPUT_DIR=$(mktemp -d -u tmpdir.XXXXXXXXXXXXXXXXXXXXXXXXX)

  run torizoncore-builder combine $IMAGE_DIR $OUTPUT_DIR
  assert_success
  run grep autoinstall $OUTPUT_DIR/image.json
  assert_output --partial "false"

  rm -rf "$OUTPUT_DIR"

  run torizoncore-builder combine $IMAGE_DIR $OUTPUT_DIR --image-autoinstall
  assert_success
  run grep autoinstall $OUTPUT_DIR/image.json
  assert_output --partial "true"

  rm -rf "$OUTPUT_DIR"

  run torizoncore-builder combine $IMAGE_DIR $OUTPUT_DIR --no-image-autoinstall
  assert_success
  run grep autoinstall $OUTPUT_DIR/image.json
  assert_output --partial "false"

  rm -rf "$COMPOSE" "$OUTPUT_DIR" "$IMAGE_DIR"
}

@test "combine: check with --image-autoreboot" {
  local COMPOSE='docker-compose.yml'
  local REG_EX_GENERATED='^\s*reboot\s+-f\s*#\s*torizoncore-builder\s+generated'
  if [ "$TCB_UNDER_CI" = "1" ]; then
      cp "$SAMPLES_DIR/compose/hello/docker-compose-proxy.yml" "$COMPOSE"
  else
      cp "$SAMPLES_DIR/compose/hello/docker-compose.yml" "$COMPOSE"
  fi

  rm -rf bundle
  torizoncore-builder bundle $COMPOSE

  unpack-image $DEFAULT_TEZI_IMAGE
  local IMAGE_DIR=$(echo $DEFAULT_TEZI_IMAGE | sed 's/\.tar$//g')
  local OUTPUT_DIR=$(mktemp -d -u tmpdir.XXXXXXXXXXXXXXXXXXXXXXXXX)

  run torizoncore-builder combine $IMAGE_DIR $OUTPUT_DIR
  assert_success
  run grep -E $REG_EX_GENERATED $OUTPUT_DIR/wrapup.sh
  refute_output

  rm -rf "$OUTPUT_DIR"

  run torizoncore-builder combine $IMAGE_DIR $OUTPUT_DIR --image-autoreboot
  assert_success
  run grep -E $REG_EX_GENERATED $OUTPUT_DIR/wrapup.sh
  assert_success

  rm -rf "$OUTPUT_DIR"

  run torizoncore-builder combine $IMAGE_DIR $OUTPUT_DIR --no-image-autoreboot
  assert_success
  run grep -E $REG_EX_GENERATED $OUTPUT_DIR/wrapup.sh
  refute_output

  rm -rf "$COMPOSE" "$OUTPUT_DIR" "$IMAGE_DIR"
}
