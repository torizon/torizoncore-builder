bats_load_library 'bats/bats-support/load.bash'
bats_load_library 'bats/bats-assert/load.bash'
bats_load_library 'bats/bats-file/load.bash'

teardown() {
    # Make sure background process is finished in case of errors.
    stop-torizoncore-builder-bg
}

@test "ostree: run without parameters" {
    run torizoncore-builder ostree
    assert_failure
    assert_output --partial "the following arguments are required: cmd"
}

@test "ostree: check help output" {
    run torizoncore-builder ostree --help
    assert_success
    assert_output --partial "Serve OSTree on the local network using http"
}

@test "ostree serve: check help output" {
    run torizoncore-builder ostree serve --help
    assert_success
    assert_output --partial "Path to the OSTree repository to serve"
}

@test "ostree serve: run without images unpack" {
    torizoncore-builder-clean-storage

    run torizoncore-builder ostree serve
    assert_failure
    assert_output --partial "Error: could not find an Easy Installer or WIC image in the storage."
    assert_output --partial "Please use the 'images' command to unpack an image before running this command."
}

@test "ostree serve: serve repo from storage" {
    ORIGINAL_REFERENCES=("base")
    run torizoncore-builder images --remove-storage unpack $DEFAULT_TEZI_IMAGE
    assert_success
    assert_output --partial "Unpacked OSTree from Toradex Easy Installer image"

    run torizoncore-builder-shell "ostree --repo=/storage/sysroot/ostree/repo refs"
    assert_success
    while IFS= read -r line; do
      ORIGINAL_REFERENCES+=("${line#*:}")
    done < <(echo "$output" | sed -E '/ostree\/[0-9]+\/[0-9]+\/[0-9]+/d')

    torizoncore-builder-bg ostree serve

    run docker run --rm --network=host busybox:stable wget -S http://localhost:8080/config -O -
    assert_success

    run torizoncore-builder-shell "ostree --repo=/repo init && \
      ostree --repo=/repo remote add srv1 http://localhost:8080 && \
      ostree --repo=/repo remote refs srv1"
    assert_success

    for ref in "${ORIGINAL_REFERENCES[@]}"; do
      assert_line --partial "$ref"
    done
    stop-torizoncore-builder-bg
}

@test "ostree serve: serve repo from external directory" {
    run torizoncore-builder images --remove-storage unpack $DEFAULT_TEZI_IMAGE
    assert_success
    assert_output --partial "Unpacked OSTree from Toradex Easy Installer image"

    torizoncore-builder-bg ostree serve --ostree-repo-directory "samples/ostree-empty/"

    run docker run --rm --network=host busybox:stable wget -S http://localhost:8080/config -O -
    assert_success
    stop-torizoncore-builder-bg
}
