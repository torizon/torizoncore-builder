load 'bats/bats-support/load.bash'
load 'bats/bats-assert/load.bash'
load 'bats/bats-file/load.bash'

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

@test "dt: checkout device tree overlays directory" {
    torizoncore-builder images --remove-storage unpack $DEFAULT_TEZI_IMAGE
    torizoncore-builder-shell "rm -rf /workdir/device-trees"

    run torizoncore-builder dt checkout
    assert_success
    refute_output

    run ls device-trees/overlays/*.dts
    assert_success
}

@test "dt: check currently enabled device tree" {
    torizoncore-builder images --remove-storage unpack $DEFAULT_TEZI_IMAGE

    run torizoncore-builder dt status
    assert [ $? = "0" -o $? = "1" ]
    assert_output --regexp "^Current device tree is|^error: cannot identify the enabled device tree"
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

    run torizoncore-builder-shell "ls /storage/dt/usr/lib/modules/*/dtb/*.dtb"
    assert_success
    local DTB=${output%$'\r'}

    run torizoncore-builder-shell "fdtput -t s $DTB / model tcb_test"
    assert_success

    torizoncore-builder union branch1
    run torizoncore-builder deploy \
        --remote-host $DEVICE_ADDR --remote-username $DEVICE_USER \
        --remote-password $DEVICE_PASS --reboot branch1
    assert_success
    assert_output --partial "Deploying successfully finished"

    run device-wait 10
    assert_success

    run device-shell "cat /proc/device-tree/model"
    assert_success
    assert_output --partial "tcb_test"
}
