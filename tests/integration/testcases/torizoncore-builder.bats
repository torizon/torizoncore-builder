load 'bats/bats-support/load.bash'
load 'bats/bats-assert/load.bash'
load 'bats/bats-file/load.bash'

@test "torizoncore-builder: run without parameters" {
    run torizoncore-builder
    assert_failure 2
    assert_output --partial 'error: the following arguments are required: cmd'
}

@test "torizoncore-builder: get software version" {
    run torizoncore-builder --version
    assert_success
}
