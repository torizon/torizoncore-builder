bats_load_library 'bats/bats-support/load.bash'
bats_load_library 'bats/bats-assert/load.bash'
bats_load_library 'bats/bats-file/load.bash'
load 'lib/common.bash'

@test "images download: run without parameters" {
    run torizoncore-builder images download
    assert_failure 2
}

@test "images download: check help output" {
    run torizoncore-builder images download --help
    assert_success
    assert_output --partial "usage: torizoncore-builder images download"
}

@test "images download: download image based on device" {
    requires-device
    torizoncore-builder-clean-storage

    run torizoncore-builder images download --remote-host $DEVICE_ADDR \
                                            --remote-username $DEVICE_USER \
                                            --remote-password $DEVICE_PASS \
                                            --remote-port $DEVICE_PORT
    assert_success
    assert_output --partial "Unpacked OSTree from Toradex Easy Installer image"

    run torizoncore-builder-shell "ls /storage/"
    assert_success
    assert_output --regexp "ostree-archive.*sysroot.*tezi"

    # TODO: Improve this (get file name from program output).
    IMAGE=$(ls torizon-core*.tar)
    check-file-ownership-as-workdir $IMAGE
}
