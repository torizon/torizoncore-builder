load 'bats/bats-support/load.bash'
load 'bats/bats-assert/load.bash'
load 'bats/bats-file/load.bash'
load 'lib/common.bash'
load 'lib/isolate.bash'


@test "isolate: run without parameters" {
    run torizoncore-builder isolate
    assert_failure 2
    assert_output --partial "error: the following arguments are required: --remote-host"
}

@test "isolate: check help output" {
    run torizoncore-builder isolate --help
    assert_success
    assert_output --partial "usage: torizoncore-builder isolate"
}

@test "isolate: create output directory when it doesn't exist and --changes-directory is used" {
    requires-device

    local TMPFILE=$(mktemp tmp.XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX)
    local ISOLATE_FILE=/etc/$TMPFILE
    device-shell-root "touch $ISOLATE_FILE"

    local ISOLATE_DIR=$(mktemp -d tmpdir.XXXXXXXXXXXXXXXXXXXXXXXXX)
    run rm -rf $ISOLATE_DIR

    run torizoncore-builder isolate --changes-directory $ISOLATE_DIR \
                                    --remote-host $DEVICE_ADDR \
                                    --remote-username $DEVICE_USER \
                                    --remote-password $DEVICE_PASS
    assert_success
    assert_output --partial "Changes in /etc successfully isolated."

    run ls -ld $ISOLATE_DIR
    assert_success
    assert_output --partial $ISOLATE_DIR
}

@test "isolate: remove the output directory when it exists and both, --changes-directory and --force are used" {
    requires-device

    local TMPFILE=$(mktemp tmp.XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX)
    local ISOLATE_FILE=/etc/$TMPFILE
    device-shell-root "touch $ISOLATE_FILE"

    local ISOLATE_DIR=$(mktemp -d tmpdir.XXXXXXXXXXXXXXXXXXXXXXXXX)
    run touch $ISOLATE_DIR/file1

    run torizoncore-builder isolate --changes-directory $ISOLATE_DIR \
                                    --force \
                                    --remote-host $DEVICE_ADDR \
                                    --remote-username $DEVICE_USER \
                                    --remote-password $DEVICE_PASS
    assert_success
    assert_output --partial "Changes in /etc successfully isolated."

    run ls -ld $ISOLATE_DIR/file1
    assert_failure
}

@test "isolate: don't remove the output directory if it exists, --changes-directory is used and --force was not passed" {
    requires-device

    local TMPFILE=$(mktemp tmp.XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX)
    local ISOLATE_FILE=/etc/$TMPFILE
    device-shell-root "touch $ISOLATE_FILE"

    local ISOLATE_DIR=$(mktemp -d tmpdir.XXXXXXXXXXXXXXXXXXXXXXXXX)
    run touch $ISOLATE_DIR/file1

    run torizoncore-builder isolate --changes-directory $ISOLATE_DIR \
                                    --remote-host $DEVICE_ADDR \
                                    --remote-username $DEVICE_USER \
                                    --remote-password $DEVICE_PASS
    assert_failure
    assert_output --partial "There is already a directory with isolated changes. If you want to replace it, please use --force."
    run torizoncore-builder-shell "ls -l $ISOLATE_DIR/file1"
    assert_success
}

@test "isolate: don't remove the output directory if 'storage' is being used and --force was not passed" {
    requires-device

    local TMPFILE=$(mktemp tmp.XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX)
    local ISOLATE_FILE=/etc/$TMPFILE
    device-shell-root "touch $ISOLATE_FILE"

    run torizoncore-builder images --remove-storage unpack $DEFAULT_TEZI_IMAGE

    local STORAGE_DIR="/storage/changes"
    run torizoncore-builder-shell "mkdir $STORAGE_DIR"
    run torizoncore-builder-shell "touch $STORAGE_DIR/file1"

    run torizoncore-builder isolate --remote-host $DEVICE_ADDR \
                                    --remote-username $DEVICE_USER \
                                    --remote-password $DEVICE_PASS
    assert_failure
    assert_output --partial "There is already a directory with isolated changes. If you want to replace it, please use --force."
    run torizoncore-builder-shell "ls -l $STORAGE_DIR/file1"
    assert_success
}

@test "isolate: remove the output directory if 'storage' is being used and --force was passed" {
    requires-device

    local TMPFILE=$(mktemp tmp.XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX)
    local ISOLATE_FILE=/etc/$TMPFILE
    device-shell-root "touch $ISOLATE_FILE"

    run torizoncore-builder images --remove-storage unpack $DEFAULT_TEZI_IMAGE

    local STORAGE_DIR="/storage/changes"
    run torizoncore-builder-shell "mkdir $STORAGE_DIR"
    run torizoncore-builder-shell "touch $STORAGE_DIR/file1"

    run torizoncore-builder isolate --remote-host $DEVICE_ADDR \
                                    --remote-username $DEVICE_USER \
                                    --remote-password $DEVICE_PASS \
                                    --force
    assert_success
    assert_output --partial "Changes in /etc successfully isolated."
    run torizoncore-builder-shell "ls -l $STORAGE_DIR/file1"
    assert_failure
}

@test "isolate: isolate changes using workdir" {
    requires-device

    local ISOLATE_DIR="isolate_dir"
    torizoncore-builder-shell "rm -rf /workdir/$ISOLATE_DIR"
    mkdir -p $ISOLATE_DIR

    local TMPFILE1="$(mktemp -u tmp.XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX)"
    local TMPFILE2='  file with'\''special chars$ @!    '
    local TMPFILE3='  file with'\''special chars-=%  '
    local TMPDIR1='  dir with'\''special chars&#'
    local ISOLATE_FILE1="/etc/$TMPFILE1"
    local ISOLATE_FILE2="/etc/$TMPFILE2"
    local ISOLATE_FILE3="/etc/$TMPDIR1/$TMPFILE3"
    device-shell-root "mkdir -p \"/etc/$TMPDIR1\""
    device-shell-root "touch \"$ISOLATE_FILE1\""
    device-shell-root "touch \"$ISOLATE_FILE2\""
    device-shell-root "touch \"$ISOLATE_FILE3\""

    torizoncore-builder images --remove-storage unpack $DEFAULT_TEZI_IMAGE
    run torizoncore-builder isolate --changes-directory $ISOLATE_DIR \
                                    --force \
                                    --remote-host $DEVICE_ADDR \
                                    --remote-username $DEVICE_USER \
                                    --remote-password $DEVICE_PASS
    assert_success
    assert_output --partial "Changes in /etc successfully isolated."

    run ls "$ISOLATE_DIR/usr$ISOLATE_FILE1" \
           "$ISOLATE_DIR/usr$ISOLATE_FILE2" \
           "$ISOLATE_DIR/usr$ISOLATE_FILE3"
    assert_success
    device-shell-root "rm -f \"$ISOLATE_FILE1\" \"$ISOLATE_FILE2\""
    device-shell-root "rm -fr \"/etc/$TMPDIR1\""
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
    assert_output --partial "Changes in /etc successfully isolated."

    run torizoncore-builder-shell "ls /storage/changes/usr/$ISOLATE_FILE"
    assert_success
    assert_output --partial "$ISOLATE_FILE"
}

@test "isolate: isolate changes and save credentials using storage" {
    requires-device

    local STORAGE_DIR="/storage/changes"
    torizoncore-builder-shell "rm -rf $STORAGE_DIR"

    create-files-in-device

    torizoncore-builder images --remove-storage unpack $DEFAULT_TEZI_IMAGE
    run torizoncore-builder isolate --remote-host $DEVICE_ADDR \
                                    --remote-username $DEVICE_USER \
                                    --remote-password $DEVICE_PASS
    assert_success
    assert_output --partial "Changes in /etc successfully isolated."

    check-tcattr-file "storage" "$STORAGE_DIR"
    check-isolated-files "storage" "$STORAGE_DIR"
}

@test "isolate: isolate changes and save credentials using --changes-directory" {
    requires-device

    local ISOLATE_DIR="isolate_dir"
    torizoncore-builder-shell "rm -rf /workdir/$ISOLATE_DIR"

    create-files-in-device

    torizoncore-builder images --remove-storage unpack $DEFAULT_TEZI_IMAGE
    run torizoncore-builder isolate --changes-directory $ISOLATE_DIR \
                                    --remote-host $DEVICE_ADDR \
                                    --remote-username $DEVICE_USER \
                                    --remote-password $DEVICE_PASS
    assert_success
    assert_output --partial "Changes in /etc successfully isolated."

    check-tcattr-file "changes-dir" "$ISOLATE_DIR"
    check-isolated-files "changes-dir" "$ISOLATE_DIR"
}
