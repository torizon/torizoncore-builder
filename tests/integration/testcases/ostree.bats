
load 'bats/bats-support/load.bash'
load 'bats/bats-assert/load.bash'
load 'bats/bats-file/load.bash'

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

@test "ostree: check 'serve' help output" {
    run torizoncore-builder ostree serve --help
    assert_success
    assert_output --partial "Path to the OSTree repository to serve"
}

@test "ostree: check 'serve' without images unpack" {
    torizoncore-builder-clean-storage

    run torizoncore-builder ostree serve
    assert_failure
    assert_output --partial "Error: could not find an Easy Installer image in the storage."
    assert_output --partial "Please use the 'images' command to unpack an Easy Installer image before running this command."
}
