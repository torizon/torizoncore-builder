load 'bats/bats-support/load.bash'
load 'bats/bats-assert/load.bash'
load 'bats/bats-file/load.bash'

@test "isolate: run without parameters" {
    run torizoncore-builder isolate
    assert_failure 2
    assert_output --partial "error: the following arguments are required: --remote-host, --remote-username, --remote-password"
}

@test "isolate: check help output" {
    run torizoncore-builder isolate --help
    assert_success
    assert_output --partial "usage: torizoncore-builder isolate"
}

@test "isolate: isolate changes using workdir" {
    requires-device

    local ISOLATE_DIR="isolate_dir"
    torizoncore-builder-shell "rm -rf /workdir/$ISOLATE_DIR"
    mkdir -p $ISOLATE_DIR

    local TMPFILE=$(mktemp tmp.XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX)
    local ISOLATE_FILE=/etc/$TMPFILE
    device-shell-root "touch $ISOLATE_FILE"

    torizoncore-builder images --remove-storage unpack $DEFAULT_TEZI_IMAGE
    run torizoncore-builder isolate --changes-directory $ISOLATE_DIR --remote-host $DEVICE_ADDR \
                                    --remote-username $DEVICE_USER --remote-password $DEVICE_PASS
    assert_success
    assert_output --partial "isolation command completed"

    run ls $ISOLATE_DIR/usr/$ISOLATE_FILE
    assert_success
    assert_output --partial "$ISOLATE_FILE"
}

@test "isolate: isolate changes using storage" {
    requires-device

    torizoncore-builder-shell "rm -rf /storage/changes"

    local TMPFILE=$(mktemp tmp.XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX)
    local ISOLATE_FILE=/etc/$TMPFILE
    device-shell-root "touch $ISOLATE_FILE"

    torizoncore-builder images --remove-storage unpack $DEFAULT_TEZI_IMAGE
    run torizoncore-builder isolate --remote-host $DEVICE_ADDR --remote-username $DEVICE_USER --remote-password $DEVICE_PASS
    assert_success
    assert_output --partial "isolation command completed"

    run torizoncore-builder-shell "ls /storage/changes/usr/$ISOLATE_FILE"
    assert_success
    assert_output --partial "$ISOLATE_FILE"
}
