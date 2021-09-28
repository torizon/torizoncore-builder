load 'bats/bats-support/load.bash'
load 'bats/bats-assert/load.bash'
load 'bats/bats-file/load.bash'

@test "torizoncore-builder: run without parameters" {
    run torizoncore-builder
    assert_failure 2
    assert_output --partial 'error: the following arguments are required: '
    assert_output --partial '{build,bundle,combine,deploy,dt,dto,images,isolate,kernel,ostree,push,splash,union}'
}

@test "torizoncore-builder: get software version" {
    run torizoncore-builder --version
    assert_success
}

@test "torizoncore-builder: deprecated --bundle-directory" {
    run torizoncore-builder --bundle-directory somedir bundle
    assert_failure
    assert_output --partial 'Error: the switch --bundle-directory has been removed from the base torizoncore-builder command;'
    assert_output --partial 'it should be used only with the "bundle" and "combine" subcommands'
}

@test "torizoncore-builder: hidden --storage-directory parameter" {
    run torizoncore-builder --help
    assert_success
    refute_output --partial "--storage-directory"
}
