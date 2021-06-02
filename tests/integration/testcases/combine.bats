load 'bats/bats-support/load.bash'
load 'bats/bats-assert/load.bash'
load 'bats/bats-file/load.bash'


@test "combine: check without --bundle-directory parameter" {
    local COMPOSE='docker-compose.yml'
    cp "$SAMPLES_DIR/compose/hello/docker-compose.yml" "$COMPOSE"

    torizoncore-builder-shell "rm -rf /workdir/bundle"
    torizoncore-builder bundle $COMPOSE

    unpack-image $DEFAULT_TEZI_IMAGE
    local IMAGE_DIR=$(echo $DEFAULT_TEZI_IMAGE | sed 's/\.tar$//g')
    local OUTPUT_DIR="output"

    run torizoncore-builder combine --image-directory $IMAGE_DIR \
                                    --output-directory $OUTPUT_DIR
    assert_success
    run ls -l $OUTPUT_DIR/$COMPOSE
    assert_success

    torizoncore-builder-shell "rm -f $COMPOSE"
    torizoncore-builder-shell "rm -rf /workdir/bundle"
    torizoncore-builder-shell "rm -rf /workdir/$OUTPUT_DIR"
    rm -rf $IMAGE_DIR
}

@test "combine: check with --bundle-directory parameters" {
    local COMPOSE='docker-compose.yml'
    cp "$SAMPLES_DIR/compose/hello/docker-compose.yml" "$COMPOSE"
    local BUNDLE_DIR="custom-bundle-dir"

    torizoncore-builder bundle --bundle-directory $BUNDLE_DIR $COMPOSE

    unpack-image $DEFAULT_TEZI_IMAGE
    local IMAGE_DIR=$(echo $DEFAULT_TEZI_IMAGE | sed 's/\.tar$//g')
    local OUTPUT_DIR="output"

    run torizoncore-builder combine --bundle-directory $BUNDLE_DIR \
                                    --image-directory $IMAGE_DIR \
                                    --output-directory $OUTPUT_DIR
    assert_success
    run ls -l $OUTPUT_DIR/$COMPOSE
    assert_success

    torizoncore-builder-shell "rm -f $COMPOSE"
    torizoncore-builder-shell "rm -rf /workdir/$BUNDLE_DIR"
    torizoncore-builder-shell "rm -rf /workdir/$OUTPUT_DIR"
    rm -rf $IMAGE_DIR
}
