load 'bats/bats-support/load.bash'
load 'bats/bats-assert/load.bash'
load 'bats/bats-file/load.bash'
load 'lib/common.bash'

@test "push: check deprecated" {
    run torizoncore-builder push --help
    assert_success
    assert_output --partial 'The "push" command is deprecated'
}