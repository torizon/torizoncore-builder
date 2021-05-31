load 'bats/bats-support/load.bash'
load 'bats/bats-assert/load.bash'
load 'bats/bats-file/load.bash'
load 'lib/common.bash'

@test "bundle: check help output" {
    run torizoncore-builder bundle --help
    assert_success
    assert_output --partial 'usage: torizoncore-builder bundle'
}

@test "bundle: check --host-workdir parameter" {
    # Test with deprecated parameter.
    run torizoncore-builder bundle --host-workdir "$(pwd)"
    assert_failure
    assert_output --partial 'the switch --host-workdir has been removed'
}

@test "bundle: check --file parameter" {
    # Test with deprecated parameter.
    local BUNDLEDIR='bundle'
    local COMPOSE='docker-compose.yml'
    torizoncore-builder-shell "rm -fr $BUNDLEDIR"
    rm -f "$COMPOSE"
    run torizoncore-builder bundle --file "$(pwd)"
    assert_failure
    assert_output --partial 'the switch --file (-f) has been removed'

    # Test with a missing compose file.
    local BUNDLEDIR='bundle'
    local COMPOSE='docker-compose.yml'
    torizoncore-builder-shell "rm -fr $BUNDLEDIR"
    rm -f "$COMPOSE"
    run torizoncore-builder bundle "$COMPOSE"
    assert_failure
    assert_output --partial "Could not load the Docker compose file '$COMPOSE'"
}

@test "bundle: check output directory overwriting" {
    # Use a basic compose file.
    local COMPOSE='docker-compose.yml'
    cp "$SAMPLES_DIR/compose/hello/docker-compose.yml" "$COMPOSE"

    # Test with an existing output directory and default name.
    local BUNDLEDIR='bundle'
    torizoncore-builder-shell "rm -fr $BUNDLEDIR && mkdir $BUNDLEDIR"
    run torizoncore-builder bundle "$COMPOSE"
    assert_failure
    assert_output --partial "Bundle directory '$BUNDLEDIR' already exists"

    # Test with an existing output directory and non-default name.
    local BUNDLEDIR='bundle-non-default'
    torizoncore-builder-shell "rm -fr $BUNDLEDIR && mkdir $BUNDLEDIR"
    run torizoncore-builder --bundle-directory "$BUNDLEDIR" bundle "$COMPOSE"
    assert_failure
    assert_output --partial "Bundle directory '$BUNDLEDIR' already exists"
    rm -fr "$BUNDLEDIR"

    # Test with an non-existing bundle directory.
    local BUNDLEDIR='bundle'
    torizoncore-builder-shell "rm -fr $BUNDLEDIR"
    run torizoncore-builder bundle "$COMPOSE"
    assert_success
    assert_output --partial "Successfully created Docker Container bundle in \"$BUNDLEDIR\""

    # Finally force previous output to be overwritten.
    run torizoncore-builder bundle --force "$COMPOSE"
    assert_success
    assert_output --partial "Successfully created Docker Container bundle in \"$BUNDLEDIR\""
}

@test "bundle: check --platform parameter" {
    # Use a basic compose file.
    local COMPOSE='docker-compose.yml'
    cp "$SAMPLES_DIR/compose/hello/docker-compose.yml" "$COMPOSE"

    # Test with platform employed on 32-bit architectures.
    local BUNDLEDIR='bundle'
    local PLATFORM='linux/arm/v7'
    torizoncore-builder-shell "rm -fr $BUNDLEDIR"
    run torizoncore-builder --log-level debug bundle --platform "$PLATFORM" "$COMPOSE"
    assert_success
    assert_output --partial "Default platform: $PLATFORM"

    # Test with platform employed on 64-bit architectures.
    local BUNDLEDIR='bundle'
    local PLATFORM='linux/arm64'
    torizoncore-builder-shell "rm -fr $BUNDLEDIR"
    run torizoncore-builder --log-level debug bundle --platform "$PLATFORM" "$COMPOSE"
    assert_success
    assert_output --partial "Default platform: $PLATFORM"

    # Test with an unexisting platform.
    local BUNDLEDIR='bundle'
    local PLATFORM='dummy-platform'
    torizoncore-builder-shell "rm -fr $BUNDLEDIR"
    run torizoncore-builder --log-level debug bundle --platform "$PLATFORM" "$COMPOSE"
    assert_failure
    assert_output --partial "container images download failed"
}
