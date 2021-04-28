load 'bats/bats-support/load.bash'
load 'bats/bats-assert/load.bash'
load 'bats/bats-file/load.bash'
load 'lib/common.bash'
load 'lib/union.bash'

@test "union: run without parameters" {
    run torizoncore-builder union
    assert_failure 2
    assert_output --partial "error: the following arguments are required: --union-branch"
}

@test "union: check help output" {
    run torizoncore-builder union --help
    assert_success
    assert_output --partial "usage: torizoncore-builder union"
}

@test "union: invalid changes directory" {
    torizoncore-builder images --remove-storage unpack $DEFAULT_TEZI_IMAGE

    run torizoncore-builder union --changes-directory invalid_changes/ --union-branch branch1
    assert_failure 255
    assert_output --partial "Changes directory \"invalid_changes/\" does not exist"
}

@test "union: create branch using --changes-directory" {
    torizoncore-builder-clean-storage
    torizoncore-builder images --remove-storage unpack $DEFAULT_TEZI_IMAGE

    run torizoncore-builder union --changes-directory $SAMPLES_DIR/changes --union-branch branch1
    assert_success
    assert_output --regexp "Commit.*has been generated for changes and (is )?ready to be deployed."

    local COMMIT=$(echo "$output" | grep '^Commit' | cut -d' ' -f 2)
    local ROOTFS=/storage/$COMMIT
    torizoncore-builder-shell "ostree checkout --repo=/storage/ostree-archive/ $COMMIT $ROOTFS"
    run torizoncore-builder-shell "cat $ROOTFS/usr/etc/myconfig.txt"
    assert_success
    assert_output --partial "enabled=1"

    run torizoncore-builder-shell "ostree refs --repo=/storage/ostree-archive/"
    assert_success
    assert_output --partial "branch1"
}

@test "union: create branch using multiple --extra-changes-directory" {
    torizoncore-builder-clean-storage
    torizoncore-builder images --remove-storage unpack $DEFAULT_TEZI_IMAGE

    run torizoncore-builder "union --extra-changes-directory $SAMPLES_DIR/changes \
                                  --extra-changes-directory $SAMPLES_DIR/changes2 \
                                  --subject integration-tests --body my-customizations \
                                  --union-branch branch2"
    assert_success
    assert_output --regexp "Commit.*has been generated for changes and (is )?ready to be deployed."

    local COMMIT=$(echo "$output" | grep '^Commit' | cut -d' ' -f 2)
    local ROOTFS=/storage/$COMMIT
    torizoncore-builder-shell "ostree checkout --repo=/storage/ostree-archive/ $COMMIT $ROOTFS"
    run torizoncore-builder-shell "cat $ROOTFS/usr/etc/myconfig.txt"
    assert_success
    assert_output --partial "enabled=1"
    run torizoncore-builder-shell "$ROOTFS/usr/sbin/secret_of_life"
    assert_failure 42

    run torizoncore-builder-shell "ostree refs --repo=/storage/ostree-archive/"
    assert_success
    assert_output --partial "branch2"

    run torizoncore-builder-shell "ostree log --repo /storage/ostree-archive/ $COMMIT"
    assert_success
    assert_output --partial "integration-tests"
    assert_output --partial "my-customizations"
}

@test "union: create branch using storage and check credentials" {
    requires-device

    torizoncore-builder-clean-storage
    torizoncore-builder images --remove-storage unpack $DEFAULT_TEZI_IMAGE

    create-files-in-device

    run torizoncore-builder isolate --remote-host $DEVICE_ADDR \
                                    --remote-username $DEVICE_USER \
                                    --remote-password $DEVICE_PASS

    make-changes-to-validate-tcattr-acls "/storage/changes"

    add-files-to-check-default-credentials "/storage/changes"

    local COMMIT=tcattr-branch
    run torizoncore-builder union --union-branch $COMMIT
    assert_success

    local ROOTFS=/storage/$COMMIT
    torizoncore-builder-shell "rm -rf $ROOTFS"
    torizoncore-builder-shell "ostree checkout --repo=/storage/ostree-archive/ $COMMIT $ROOTFS"

    check-credentials $ROOTFS
    check-tcattr-files-removal $ROOTFS
}

@test "union: create branch using --changes-directory and check credentials" {
    requires-device

    torizoncore-builder-clean-storage
    torizoncore-builder images --remove-storage unpack $DEFAULT_TEZI_IMAGE

    create-files-in-device

    local ISOLATE_DIR="isolate_dir"
    torizoncore-builder-shell "rm -rf /workdir/$ISOLATE_DIR"
    mkdir -p $ISOLATE_DIR

    run torizoncore-builder isolate --changes-directory $ISOLATE_DIR \
                                    --remote-host $DEVICE_ADDR \
                                    --remote-username $DEVICE_USER \
                                    --remote-password $DEVICE_PASS

    add-files-to-check-default-credentials "/workdir/$ISOLATE_DIR"

    local COMMIT=tcattr-branch
    run torizoncore-builder union --changes-directory $ISOLATE_DIR \
                                  --union-branch $COMMIT
    assert_success

    local ROOTFS=/storage/$COMMIT
    torizoncore-builder-shell "rm -rf $ROOTFS"
    torizoncore-builder-shell "ostree checkout --repo=/storage/ostree-archive/ $COMMIT $ROOTFS"

    check-credentials $ROOTFS
    check-tcattr-files-removal $ROOTFS
}

@test "union: create branch using --extra-changes-dirs and check credentials" {
    requires-device

    torizoncore-builder-clean-storage
    torizoncore-builder images --remove-storage unpack $DEFAULT_TEZI_IMAGE

    create-files-in-device

    local EXTRA_DIR="$SAMPLES_DIR/changes3"

    run torizoncore-builder isolate --remote-host $DEVICE_ADDR \
                                    --remote-username $DEVICE_USER \
                                    --remote-password $DEVICE_PASS

    local COMMIT=tcattr-branch
    run torizoncore-builder union --extra-changes-directory $EXTRA_DIR \
                                  --union-branch $COMMIT
    assert_success

    local ROOTFS=/storage/$COMMIT
    torizoncore-builder-shell "rm -rf $ROOTFS"
    torizoncore-builder-shell "ostree checkout --repo=/storage/ostree-archive/ $COMMIT $ROOTFS"

    check-credentials-extra $ROOTFS
    check-tcattr-files-removal $ROOTFS
}
