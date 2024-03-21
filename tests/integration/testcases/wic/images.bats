bats_load_library 'bats/bats-support/load.bash'
bats_load_library 'bats/bats-assert/load.bash'
bats_load_library 'bats/bats-file/load.bash'

@test "images: check help output" {
    run torizoncore-builder images --help
    assert_success
    assert_output --partial ' {download,provision,serve,unpack}'
}
