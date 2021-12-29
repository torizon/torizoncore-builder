load 'bats/bats-support/load.bash'
load 'bats/bats-assert/load.bash'
load 'bats/bats-file/load.bash'
load 'lib/common.bash'

@test "dt: run without parameters" {
    run torizoncore-builder dt
    assert_failure 2
    assert_output --partial "error: the following arguments are required: cmd"
}

@test "dt: check help output" {
    run torizoncore-builder dt --help
    assert_success
    assert_output --partial "{status,checkout,apply}"
}

@test "dt: checkout device tree overlays directory without images unpack" {
    torizoncore-builder-clean-storage
    rm -rf device-trees

    run torizoncore-builder dt checkout
    assert_failure
    assert_output --partial "Error: could not find an Easy Installer image in the storage."
    assert_output --partial "Please use the 'images' command to unpack an Easy Installer image before running this command."
}

@test "dt: checkout device tree overlays directory" {
    torizoncore-builder images --remove-storage unpack $DEFAULT_TEZI_IMAGE
    rm -rf device-trees

    run torizoncore-builder dt checkout
    assert_success
    refute_output

    run ls device-trees/overlays/*.dts
    assert_success

    check-file-ownership-as-workdir "device-trees"
    check-file-ownership-as-workdir "device-trees/overlays"

    for FILE_DTS in device-trees/overlays/*.dts
    do
        check-file-ownership-as-workdir $FILE_DTS
    done
}

@test "dt: check currently enabled device tree without images unpack" {
    torizoncore-builder-clean-storage

    run torizoncore-builder dt status
    assert_failure
    assert_output --partial "Error: could not find an Easy Installer image in the storage."
    assert_output --partial "Please use the 'images' command to unpack an Easy Installer image before running this command."
}

@test "dt: check currently enabled device tree" {
    torizoncore-builder images --remove-storage unpack $DEFAULT_TEZI_IMAGE

    run torizoncore-builder dt status
    assert [ $? = "0" -o $? = "1" ]
    assert_output --regexp "^Current device tree is|^error: cannot identify the enabled device tree"
}

@test "dt: apply device tree in the image without images unpack" {
    torizoncore-builder-clean-storage

    run torizoncore-builder dt apply some_dto_file
    assert_failure
    assert_output --partial "Error: could not find an Easy Installer image in the storage."
    assert_output --partial "Please use the 'images' command to unpack an Easy Installer image before running this command."
}

@test "dt: apply device tree in the image" {
    torizoncore-builder images --remove-storage unpack $DEFAULT_TEZI_IMAGE

    run torizoncore-builder-shell "ls /storage/sysroot/boot/ostree/torizon-*/dtb/*.dtb"
    local DTB=$(basename "${lines[0]}")
    local DTS="${DTB%.*}.dts"

    run find device-trees/ -name $DTS
    assert_success
    local DTS_LOCATION=$output

    run torizoncore-builder dt apply $DTS_LOCATION
    assert_success
    assert_output --regexp "Device tree.*successfully applied"

    run torizoncore-builder dt status
    assert_success
    assert_output --partial "$DTB"
}

@test "dt: deploy device tree in the device" {
    requires-device

    torizoncore-builder images --remove-storage unpack $DEFAULT_TEZI_IMAGE

    # Determine device-tree being used on device:
    run device-shell-root "fw_printenv fdtfile"
    assert_success
    assert_output --partial "fdtfile="
    local DTB="${output/*fdtfile=/}"
    local DTS="${DTB%.*}.dts"

    # Find corresponding device-tree source and apply it.
    run find device-trees/ -name $DTS
    assert_success
    local DTS_LOCATION=$output
    # echo "# DTS_LOCATION: $DTS_LOCATION" >&3

    run torizoncore-builder dt apply $DTS_LOCATION
    assert_success
    assert_output --regexp "Device tree.*successfully applied"

    # Make a slight change in the device tree and deploy it to device.
    local DTB_LOCATION="$(echo /storage/dt/usr/lib/modules/*/dtb/)$DTB"
    # echo "# DTB_LOCATION: $DTB_LOCATION" >&3

    local MODEL="tcb_test--$(date +%Y%m%d-%H%M)"
    run torizoncore-builder-shell "fdtput -t s $DTB_LOCATION / model $MODEL"
    assert_success

    torizoncore-builder union branch1
    run torizoncore-builder deploy --remote-host "$DEVICE_ADDR" \
                                   --remote-username "$DEVICE_USER" \
                                   --remote-password "$DEVICE_PASS" \
                                   --remote-port "$DEVICE_PORT" \
                                   --reboot branch1
    assert_success
    assert_output --partial "Deploying successfully finished"

    run device-wait 20
    assert_success

    run device-shell "cat /proc/device-tree/model"
    assert_success
    assert_output --partial "$MODEL"
}
