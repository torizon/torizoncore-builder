load 'bats/bats-support/load.bash'
load 'bats/bats-assert/load.bash'
load 'bats/bats-file/load.bash'
load 'lib/common.bash'


@test "kernel: run without parameters" {
    run torizoncore-builder kernel
    assert_failure 2
    assert_output --partial "{build_module,set_custom_args,get_custom_args,clear_custom_args}"
    assert_output --partial "error: the following arguments are required: cmd"
}

@test "kernel: check help output" {
    run torizoncore-builder kernel --help
    assert_success
    assert_output --partial "usage: torizoncore-builder kernel [-h]"
    assert_output --partial "{build_module,set_custom_args,get_custom_args,clear_custom_args}"
}

@test "kernel: check build_module ownership for output files" {
    local MOD_FILE="hello"
    local MAKEFILE="Makefile"
    local README="README.md"
    local SRC_DIR="source_dir"

    mkdir -p $SRC_DIR
    cp $SAMPLES_DIR/kernel/$MOD_FILE.c $SRC_DIR
    cp $SAMPLES_DIR/kernel/$MAKEFILE $SRC_DIR
    cp $SAMPLES_DIR/kernel/$README $SRC_DIR

    torizoncore-builder-shell "chown 10:20 $SRC_DIR/$README"
    torizoncore-builder images --remove-storage unpack $DEFAULT_TEZI_IMAGE

    run torizoncore-builder kernel build_module $SRC_DIR
    assert_success

    run ls -ld $SRC_DIR/$MOD_FILE.ko
    assert_success

    # Check files ownership as work dir
    check-file-ownership-as-workdir $SRC_DIR/$MOD_FILE.c
    check-file-ownership-as-workdir $SRC_DIR/$MOD_FILE.o
    check-file-ownership-as-workdir $SRC_DIR/$MOD_FILE.ko
    check-file-ownership-as-workdir $SRC_DIR/$MAKEFILE

    # Check file with ownership not as "root:root"
    run ls -dln $SRC_DIR/$README
    assert_output --partial "1 10 20 0"

    torizoncore-builder-shell "rm -rf $SRC_DIR"
}

@test "kernel: run build_module without images unpack" {
    torizoncore-builder-clean-storage

    local SRC_DIR="source_dir"
    mkdir -p $SRC_DIR

    run torizoncore-builder kernel build_module $SRC_DIR
    assert_failure
    assert_output --partial "Error: could not find an Easy Installer image in the storage."
    assert_output --partial "Please use the 'images' command to unpack an Easy Installer image before running this command."

    torizoncore-builder-shell "rm -rf $SRC_DIR"
}
