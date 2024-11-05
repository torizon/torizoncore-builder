bats_load_library 'bats/bats-support/load.bash'
bats_load_library 'bats/bats-assert/load.bash'
bats_load_library 'bats/bats-file/load.bash'
load '../lib/common.bash'


@test "combine: check if image is a valid raw image" {
    local ci_dockerhub_login="$(ci-dockerhub-login-flag)"

    local COMPOSE='docker-compose.yml'
    cp "$SAMPLES_DIR/compose/hello/docker-compose.yml" "$COMPOSE"

    rm -rf bundle $OUTPUT_IMAGE
    run torizoncore-builder bundle "$COMPOSE" \
        ${ci_dockerhub_login:+"--login" "${CI_DOCKER_HUB_PULL_USER}" "${CI_DOCKER_HUB_PULL_PASSWORD}"}
    assert_success

    if [ "${ci_dockerhub_login}" = "1" ]; then
        assert_output --partial "Attempting to log in to"
    fi

    local OUTPUT_IMAGE="$(echo $DEFAULT_WIC_IMAGE | sed 's/\.wic$//g')_bundled.wic"

    truncate -s +1K invalid_image.wic

    run torizoncore-builder combine invalid_image.wic $OUTPUT_IMAGE
    assert_failure
    assert_output --partial "Image doesn't have any partitions or it's not a valid raw image"

    rm -rf "invalid_image.wic" $OUTPUT_IMAGE

    rm -rf "$COMPOSE" bundle
}

@test "combine: check without --bundle-directory parameter" {
    local ci_dockerhub_login="$(ci-dockerhub-login-flag)"

    local COMPOSE='docker-compose.yml'
    cp "$SAMPLES_DIR/compose/hello/docker-compose.yml" "$COMPOSE"

    rm -rf bundle
    run torizoncore-builder bundle "$COMPOSE" \
        ${ci_dockerhub_login:+"--login" "${CI_DOCKER_HUB_PULL_USER}" "${CI_DOCKER_HUB_PULL_PASSWORD}"}
    assert_success

    if [ "${ci_dockerhub_login}" = "1" ]; then
        assert_output --partial "Attempting to log in to"
    fi

    local OUTPUT_IMAGE="$(echo $DEFAULT_WIC_IMAGE | sed 's/\.wic$//g')_bundled.wic"

    run torizoncore-builder combine $DEFAULT_WIC_IMAGE $OUTPUT_IMAGE --force
    assert_success

    check-file-ownership-as-workdir "$OUTPUT_IMAGE"

    rm -rf "$COMPOSE" bundle "$OUTPUT_IMAGE"
}

@test "combine: check with --bundle-directory parameters" {
    local ci_dockerhub_login="$(ci-dockerhub-login-flag)"

    local COMPOSE='docker-compose.yml'
    cp "$SAMPLES_DIR/compose/hello/docker-compose.yml" "$COMPOSE"

    local BUNDLE_DIR=$(mktemp -d -u tmpdir.XXXXXXXXXXXXXXXXXXXXXXXXX)

    run torizoncore-builder bundle --bundle-directory "$BUNDLE_DIR" "$COMPOSE" \
        ${ci_dockerhub_login:+"--login" "${CI_DOCKER_HUB_PULL_USER}" "${CI_DOCKER_HUB_PULL_PASSWORD}"}
    assert_success

    if [ "${ci_dockerhub_login}" = "1" ]; then
        assert_output --partial "Attempting to log in to"
    fi

    local OUTPUT_IMAGE="$(echo $DEFAULT_WIC_IMAGE | sed 's/\.wic$//g')_bundled.wic"

    run torizoncore-builder combine --bundle-directory $BUNDLE_DIR \
                                    $DEFAULT_WIC_IMAGE $OUTPUT_IMAGE --force
    assert_success

    check-file-ownership-as-workdir "$OUTPUT_IMAGE"

    rm -rf "$COMPOSE" "$BUNDLE_DIR" "$OUTPUT_IMAGE"
}
