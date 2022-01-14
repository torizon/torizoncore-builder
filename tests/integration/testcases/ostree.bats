load 'bats/bats-support/load.bash'
load 'bats/bats-assert/load.bash'
load 'bats/bats-file/load.bash'

function teardown() {
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
    assert_output --partial "Error: could not find an Easy Installer image in the storage."
    assert_output --partial "Please use the 'images' command to unpack an Easy Installer image before running this command."
}

@test "ostree serve: serve repo from storage" {
    run torizoncore-builder images --remove-storage unpack $DEFAULT_TEZI_IMAGE
    assert_success
    assert_output --partial "Unpacked OSTree from Toradex Easy Installer image"

    torizoncore-builder-bg ostree serve

    run curl http://localhost:8080/config
    assert_success
    stop-torizoncore-builder-bg
}

@test "ostree serve: serve repo from external directory" {
    run torizoncore-builder images --remove-storage unpack $DEFAULT_TEZI_IMAGE
    assert_success
    assert_output --partial "Unpacked OSTree from Toradex Easy Installer image"

    torizoncore-builder-bg ostree serve --ostree-repo-directory "samples/ostree-empty/"

    run curl http://localhost:8080/config
    assert_success
    stop-torizoncore-builder-bg
}
