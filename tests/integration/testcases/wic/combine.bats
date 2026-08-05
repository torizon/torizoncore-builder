bats_load_library 'bats/bats-support/load.bash'
bats_load_library 'bats/bats-assert/load.bash'
bats_load_library 'bats/bats-file/load.bash'
load '../lib/common.bash'
load '../lib/raw-sector-size.bash'

setup_file() {
    raw-sector-size-setup-synth-images "$RSS_SYNTH_4K" 4096 "$RSS_SLACK_4K_KB"
}

teardown_file() {
    rm -f "$RSS_SYNTH_4K"
}

teardown() {
    rm -rf rss_docker-compose.yml rss_bundle rss_combine_out.img
}

@test "combine: grows a 4Kn image past the 98% ratio" {
    local ci_dockerhub_login="$(ci-dockerhub-login-flag)"

    # Read before combine grows anything, to compare against below.
    read -r part_size_before fs_bytes_before <<< "$(raw-sector-size-4k-fs-stats "$RSS_SYNTH_4K")"

    local compose='rss_docker-compose.yml'
    cp "$SAMPLES_DIR/compose/hello/docker-compose.yml" "$compose"

    rm -rf rss_bundle rss_combine_out.img
    run torizoncore-builder bundle --bundle-directory rss_bundle "$compose" \
        ${ci_dockerhub_login:+"--login" "${CI_DOCKER_HUB_PULL_USER}" "${CI_DOCKER_HUB_PULL_PASSWORD}"}
    assert_success

    if [ "${ci_dockerhub_login}" = "1" ]; then
        assert_output --partial "Attempting to log in to"
    fi

    run torizoncore-builder combine --bundle-directory rss_bundle --force --raw-sector-size 4096 \
                                    $RSS_SYNTH_4K rss_combine_out.img
    assert_success
    assert_output --partial "Output disk will be increased"

    read -r part_size_after fs_bytes_after <<< "$(raw-sector-size-4k-fs-stats rss_combine_out.img)"

    # The filesystem must grow along with the partition.
    run awk -v before="$fs_bytes_before" -v after="$fs_bytes_after" \
        'BEGIN { exit !(after > before * 1.05) }'
    assert_success

    # ...and roughly fill it, matching mkfs's own baseline ratio.
    run awk -v ps_before="$part_size_before" -v fs_before="$fs_bytes_before" \
             -v ps_after="$part_size_after" -v fs_after="$fs_bytes_after" \
        'BEGIN { exit !(fs_after / ps_after >= (fs_before / ps_before) * 0.98) }'
    assert_success
}

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

    truncate -s 1K invalid_image.wic

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
