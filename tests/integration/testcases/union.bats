load 'bats/bats-support/load.bash'
load 'bats/bats-assert/load.bash'
load 'bats/bats-file/load.bash'

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
    assert_output --regexp "Commit.*has been generated for changes and ready to be deployed."

    local COMMIT=$(echo $output | cut -d' ' -f 2)
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
    assert_output --regexp "Commit.*has been generated for changes and ready to be deployed."

    local COMMIT=$(echo $output | cut -d' ' -f 2)
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
