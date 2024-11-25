bats_load_library 'bats/bats-support/load.bash'
bats_load_library 'bats/bats-assert/load.bash'
bats_load_library 'bats/bats-file/load.bash'
load 'lib/common.bash'
load 'lib/union.bash'

@test "union: run without parameters" {
    run torizoncore-builder union
    assert_failure
    assert_output --partial "UNION_BRANCH positional argument is required"
}

@test "union: check help output" {
    run torizoncore-builder union --help
    assert_success
    assert_output --partial "usage: torizoncore-builder union"
}

@test "union: invalid changes directory" {
    torizoncore-builder images --remove-storage unpack $DEFAULT_TEZI_IMAGE

    run torizoncore-builder union --changes-directory invalid_changes/ branch1
    assert_failure
    assert_output --partial "Changes directory \"invalid_changes/\" does not exist"
}

@test "union: create branch without images unpack" {
    torizoncore-builder-clean-storage

    run torizoncore-builder union branch1
    assert_failure
    assert_output --partial "Error: could not find an Easy Installer or WIC image in the storage."
    assert_output --partial "Please use the 'images' command to unpack an image before running this command."
}

@test "union: create branch using --changes-directory" {
    torizoncore-builder-clean-storage
    torizoncore-builder images --remove-storage unpack $DEFAULT_TEZI_IMAGE

    run torizoncore-builder union --changes-directory $SAMPLES_DIR/changes branch1
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

@test "union: create branch using multiple --changes-directory" {
    torizoncore-builder-clean-storage
    torizoncore-builder images --remove-storage unpack $DEFAULT_TEZI_IMAGE

    run torizoncore-builder union --changes-directory "$SAMPLES_DIR/changes" \
        --changes-directory "$SAMPLES_DIR/changes2" \
        --subject integration-tests --body my-customizations branch2
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

# bats test_tags=requires-device
@test "union: create branch using storage and check credentials" {
    requires-device

    torizoncore-builder-clean-storage
    torizoncore-builder images --remove-storage unpack $DEFAULT_TEZI_IMAGE

    create-files-in-device

    run torizoncore-builder isolate --remote-host $DEVICE_ADDR \
                                    --remote-username $DEVICE_USER \
                                    --remote-password $DEVICE_PASSWORD \
                                    --remote-port $DEVICE_PORT

    make-changes-to-validate-tcattr-acls "/storage/changes"

    add-files-to-check-default-credentials "/storage/changes"

    local COMMIT=tcattr-branch
    run torizoncore-builder union $COMMIT
    assert_success

    local ROOTFS=/storage/$COMMIT
    torizoncore-builder-shell "rm -rf $ROOTFS"
    torizoncore-builder-shell "ostree checkout --repo=/storage/ostree-archive/ $COMMIT $ROOTFS"

    check-credentials $ROOTFS
    check-tcattr-files-removal $ROOTFS
}

# bats test_tags=requires-device
@test "union: create branch using --changes-directory and check credentials" {
    requires-device

    torizoncore-builder-clean-storage
    torizoncore-builder images --remove-storage unpack $DEFAULT_TEZI_IMAGE

    create-files-in-device

    local ISOLATE_DIR="isolate_dir"
    rm -rf $ISOLATE_DIR
    mkdir -p $ISOLATE_DIR

    run torizoncore-builder isolate --changes-directory $ISOLATE_DIR \
                                    --force \
                                    --remote-host $DEVICE_ADDR \
                                    --remote-username $DEVICE_USER \
                                    --remote-password $DEVICE_PASSWORD \
                                    --remote-port $DEVICE_PORT

    add-files-to-check-default-credentials "/workdir/$ISOLATE_DIR"

    local COMMIT=tcattr-branch
    run torizoncore-builder union --changes-directory $ISOLATE_DIR $COMMIT
    assert_success

    local ROOTFS=/storage/$COMMIT
    torizoncore-builder-shell "rm -rf $ROOTFS"
    torizoncore-builder-shell "ostree checkout --repo=/storage/ostree-archive/ $COMMIT $ROOTFS"

    check-credentials $ROOTFS
    check-tcattr-files-removal $ROOTFS
}

@test "union: create branch using --changes-directory and check credentials for symbolic links" {
    torizoncore-builder-clean-storage
    torizoncore-builder images --remove-storage unpack $DEFAULT_TEZI_IMAGE

    local EXTRA_DIR="$SAMPLES_DIR/changes3"

    local COMMIT=tcattr-branch
    run torizoncore-builder union --changes-directory $EXTRA_DIR $COMMIT
    assert_success

    local ROOTFS=/storage/$COMMIT
    torizoncore-builder-shell "rm -rf $ROOTFS"
    torizoncore-builder-shell "ostree checkout --repo=/storage/ostree-archive/ $COMMIT $ROOTFS"

    check-credentials-for-links $ROOTFS
    check-tcattr-files-removal $ROOTFS
}
