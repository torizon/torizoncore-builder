bats_load_library 'bats/bats-support/load.bash'
bats_load_library 'bats/bats-assert/load.bash'
bats_load_library 'bats/bats-file/load.bash'

@test "dto: run without parameters" {
    run torizoncore-builder dto
    assert_failure 2
    assert_output --partial "error: the following arguments are required: cmd"
}

@test "dto: check help output" {
    run torizoncore-builder dto --help
    assert_success
    assert_output --partial "{apply,list,status,remove,deploy}"
}

@test "dto: list compatible overlays without images unpack" {
    torizoncore-builder images --remove-storage unpack $DEFAULT_TEZI_IMAGE
    rm -rf device-trees

    run torizoncore-builder dt checkout --update
    if is-major-version-6; then
        assert_failure
        skip "device-trees not available on TC6"
    fi
    assert_success

    torizoncore-builder-clean-storage

    run torizoncore-builder dto list
    assert_failure
    assert_output --partial "Error: could not find an Easy Installer image in the storage."
    assert_output --partial "Please use the 'images' command to unpack an Easy Installer image before running this command."
}

@test "dto: list compatible overlays" {
    torizoncore-builder images --remove-storage unpack $DEFAULT_TEZI_IMAGE
    rm -rf device-trees

    run torizoncore-builder dt checkout --update
    if is-major-version-6; then
        assert_failure
        skip "device-trees not available on TC6"
    fi
    assert_success

    run torizoncore-builder dto list

    if grep -q "Could not determine default device tree" <<< $output; then
        local DTB=$(echo "$output" | sed -nE -e 's/^- (.*\.dtb)/\1/p' | head -1)
        run torizoncore-builder dto list --device-tree $DTB
    fi

    assert_success
    assert_output --partial "Overlays compatible with device tree"
    assert_output --partial "_overlay.dts"
}

@test "dto: apply overlay in the image without images unpack" {
    torizoncore-builder-clean-storage

    run torizoncore-builder dto apply --force $SAMPLES_DIR/dts/sample_overlay.dts
    assert_failure
    assert_output --partial "Error: could not find an Easy Installer image in the storage."
    assert_output --partial "Please use the 'images' command to unpack an Easy Installer image before running this command."
}

@test "dto: apply overlay in the image" {
    torizoncore-builder images --remove-storage unpack $DEFAULT_TEZI_IMAGE

    run torizoncore-builder dto apply --force $SAMPLES_DIR/dts/sample_overlay.dts
    assert_success
    assert_output --partial "Overlay sample_overlay.dtbo successfully applied"

    run torizoncore-builder-shell "cat /storage/dt/usr/lib/modules/*/dtb/overlays.txt"
    assert_success
    assert_output --partial "sample_overlay.dtbo"

    run torizoncore-builder-shell "ls /storage/dt/usr/lib/modules/*/dtb/overlays/"
    assert_success
    assert_output --partial "sample_overlay.dtbo"
}

@test "dto: check currently applied overlays without images unpack" {
    torizoncore-builder-clean-storage

    run torizoncore-builder dto status
    assert_failure
    assert_output --partial "Error: could not find an Easy Installer image in the storage."
    assert_output --partial "Please use the 'images' command to unpack an Easy Installer image before running this command."
}

@test "dto: check currently applied overlays" {
    torizoncore-builder images --remove-storage unpack $DEFAULT_TEZI_IMAGE
    torizoncore-builder dto apply --force $SAMPLES_DIR/dts/sample_overlay.dts

    run torizoncore-builder dto status
    assert_success
    assert_output --partial "sample_overlay.dtbo"
}

# bats test_tags=requires-device
@test "dto: deploy overlay on the device" {
    requires-device

    run device-shell "cat /proc/device-tree/tcb_prop_test"
    assert_failure 1

    torizoncore-builder union branch1
    run torizoncore-builder deploy \
        --remote-host $DEVICE_ADDR --remote-username $DEVICE_USER \
        --remote-password $DEVICE_PASS --remote-port $DEVICE_PORT --reboot branch1
    assert_success
    assert_output --partial "Deploying successfully finished"

    run device-wait 20
    assert_success

    run device-shell "cat /proc/device-tree/tcb_prop_test"
    assert_success
    assert_output --partial "tcb_prop_value"
}

@test "dto: remove overlay in the image" {
    run torizoncore-builder dto remove sample_overlay.dtbo
    assert_success

    run torizoncore-builder dto status
    assert_success
    refute_output --partial "sample_overlay.dtbo"
}

# bats test_tags=requires-device
@test "dto: remove overlay from the device" {
    requires-device

    torizoncore-builder union branch2
    run torizoncore-builder deploy \
        --remote-host $DEVICE_ADDR --remote-username $DEVICE_USER \
        --remote-password $DEVICE_PASS --remote-port $DEVICE_PORT --reboot branch2
    assert_success
    assert_output --partial "Deploying successfully finished"

    run device-wait 20
    assert_success

    run device-shell "cat /proc/device-tree/tcb_prop_test"
    assert_failure 1
}

@test "dto: remove all overlays in the image" {
    run torizoncore-builder dto remove --all
    assert_success

    run torizoncore-builder dto status
    assert_success
    refute_output --regexp ".*dtbo"
}

@test "dto: remove overlay in the image without images unpack" {
    torizoncore-builder-clean-storage

    run torizoncore-builder dto remove sample_overlay.dtbo
    assert_failure
    assert_output --partial "Error: could not find an Easy Installer image in the storage."
    assert_output --partial "Please use the 'images' command to unpack an Easy Installer image before running this command."
}
