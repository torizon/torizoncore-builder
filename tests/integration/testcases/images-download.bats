load 'bats/bats-support/load.bash'
load 'bats/bats-assert/load.bash'
load 'bats/bats-file/load.bash'

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

    run torizoncore-builder images download --remote-host $DEVICE_ADDR --remote-username $DEVICE_USER --remote-password $DEVICE_PASS
    assert_success
    assert_output --partial "Unpacked OSTree from Toradex Easy Installer image"

    run torizoncore-builder-shell "ls /storage/"
    assert_success
    assert_output --regexp "ostree-archive.*sysroot.*tezi"
}
