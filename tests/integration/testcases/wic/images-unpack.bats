bats_load_library 'bats/bats-support/load.bash'
bats_load_library 'bats/bats-assert/load.bash'
bats_load_library 'bats/bats-file/load.bash'

@test "images unpack: run without parameters" {
    run torizoncore-builder images unpack
    assert_failure
}

@test "images unpack: check help output" {
    run torizoncore-builder images unpack --help
    assert_success
    assert_output --partial "usage: torizoncore-builder images unpack"
}

@test "images unpack: check empty storage" {
    torizoncore-builder-clean-storage
    run torizoncore-builder-shell "ls /storage/"
    assert_success
    refute_output
}

@test "images unpack: unpack non-existent image" {
    run torizoncore-builder images --remove-storage unpack invalid_image.wic
    assert_failure
}

@test "images unpack: point to an invalid rootfs label" {
    run torizoncore-builder images --remove-storage unpack --raw-rootfs-label invalid_label $DEFAULT_WIC_IMAGE
    assert_failure
    assert_output --partial "Filesystem with label 'invalid_label' not found in image"
}

@test "images unpack: unpack image from WIC file" {
    torizoncore-builder-clean-storage

    run torizoncore-builder images --remove-storage unpack $DEFAULT_WIC_IMAGE
    assert_success
    assert_output --partial "Unpacked OSTree from WIC/raw image"

    run torizoncore-builder-shell "ls /storage/"
    assert_success
    assert_output --regexp "ostree-archive.*sysroot"
}

@test "images unpack: keep only /storage/toolchain directory in storage" {
    torizoncore-builder-clean-storage

    torizoncore-builder-shell "mkdir -p /storage/{dt,changes,kernel}"
    torizoncore-builder-shell "mkdir -p /storage/toolchain"
    torizoncore-builder-shell "mkdir -p /storage/dir{1,2,3}"

    torizoncore-builder images --remove-storage unpack $DEFAULT_WIC_IMAGE

    run torizoncore-builder-shell "ls -l /storage/{dir}?"
    assert_failure
    run torizoncore-builder-shell "ls -l /storage/{dt,changes,kernel}"
    assert_failure
    run torizoncore-builder-shell "ls -l /storage/toolchain"
    assert_success
}
