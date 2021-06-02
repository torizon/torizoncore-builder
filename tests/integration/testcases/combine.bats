load 'bats/bats-support/load.bash'
load 'bats/bats-assert/load.bash'
load 'bats/bats-file/load.bash'


@test "combine: check if image directory has a valid tezi image" {
    local COMPOSE='docker-compose.yml'
    cp "$SAMPLES_DIR/compose/hello/docker-compose.yml" "$COMPOSE"
    torizoncore-builder-shell "rm -rf /workdir/bundle"
    torizoncore-builder bundle $COMPOSE

    local FILES="image.json *.zst"
    for FILE in $FILES
    do
        unpack-image $DEFAULT_TEZI_IMAGE
        local IMAGE_DIR=$(echo $DEFAULT_TEZI_IMAGE | sed 's/\.tar$//g')
        local OUTPUT_DIR="combine_output_dir"
        rm $IMAGE_DIR/$FILE

        run torizoncore-builder combine $IMAGE_DIR $OUTPUT_DIR
        assert_failure
        assert_output --partial "Error: directory $IMAGE_DIR does not contain a valid TEZI image"

        rm -rf $IMAGE_DIR
        torizoncore-builder-shell "rm -rf /workdir/$OUTPUT_DIR"
    done

    torizoncore-builder-shell "rm -f $COMPOSE"
    torizoncore-builder-shell "rm -rf /workdir/bundle"
}

@test "combine: run with the deprecated --image-directory switch" {
    local COMPOSE='docker-compose.yml'
    cp "$SAMPLES_DIR/compose/hello/docker-compose.yml" "$COMPOSE"

    torizoncore-builder-shell "rm -rf /workdir/bundle"
    torizoncore-builder bundle $COMPOSE

    unpack-image $DEFAULT_TEZI_IMAGE
    local IMAGE_DIR=$(echo $DEFAULT_TEZI_IMAGE | sed 's/\.tar$//g')
    local OUTPUT_DIR="output"

    run torizoncore-builder combine --image-directory $IMAGE_DIR \
                                    $OUTPUT_DIR
    assert_failure
    assert_output --partial "Error: the switch --image-directory has been removed"
    assert_output --partial "please provide the image directory without passing the switch."

    torizoncore-builder-shell "rm -f $COMPOSE"
    torizoncore-builder-shell "rm -rf /workdir/bundle"
    torizoncore-builder-shell "rm -rf /workdir/$OUTPUT_DIR"
    rm -rf $IMAGE_DIR
}

@test "combine: run with the deprecated --output-directory switch" {
    local COMPOSE='docker-compose.yml'
    cp "$SAMPLES_DIR/compose/hello/docker-compose.yml" "$COMPOSE"

    torizoncore-builder-shell "rm -rf /workdir/bundle"
    torizoncore-builder bundle $COMPOSE

    unpack-image $DEFAULT_TEZI_IMAGE
    local IMAGE_DIR=$(echo $DEFAULT_TEZI_IMAGE | sed 's/\.tar$//g')
    local OUTPUT_DIR="output"

    run torizoncore-builder combine $IMAGE_DIR \
                                    --output-directory $OUTPUT_DIR
    assert_failure
    assert_output --partial "Error: the switch --output-directory has been removed"
    assert_output --partial "please provide the output directory without passing the switch."

    torizoncore-builder-shell "rm -f $COMPOSE"
    torizoncore-builder-shell "rm -rf /workdir/bundle"
    torizoncore-builder-shell "rm -rf /workdir/$OUTPUT_DIR"
    rm -rf $IMAGE_DIR
}

@test "combine: check without --bundle-directory parameter" {
    local COMPOSE='docker-compose.yml'
    cp "$SAMPLES_DIR/compose/hello/docker-compose.yml" "$COMPOSE"

    torizoncore-builder-shell "rm -rf /workdir/bundle"
    torizoncore-builder bundle $COMPOSE

    unpack-image $DEFAULT_TEZI_IMAGE
    local IMAGE_DIR=$(echo $DEFAULT_TEZI_IMAGE | sed 's/\.tar$//g')
    local OUTPUT_DIR="output"

    run torizoncore-builder combine $IMAGE_DIR $OUTPUT_DIR
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
                                    $IMAGE_DIR $OUTPUT_DIR
    assert_success
    run ls -l $OUTPUT_DIR/$COMPOSE
    assert_success

    torizoncore-builder-shell "rm -f $COMPOSE"
    torizoncore-builder-shell "rm -rf /workdir/$BUNDLE_DIR"
    torizoncore-builder-shell "rm -rf /workdir/$OUTPUT_DIR"
    rm -rf $IMAGE_DIR
}
