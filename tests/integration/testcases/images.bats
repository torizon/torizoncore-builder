load 'bats/bats-support/load.bash'
load 'bats/bats-assert/load.bash'
load 'bats/bats-file/load.bash'

@test "images: check help output" {
    run torizoncore-builder images --help
    assert_success
    assert_output --partial '{download,unpack}'
}
