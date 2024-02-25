bats_load_library 'bats/bats-support/load.bash'
bats_load_library 'bats/bats-assert/load.bash'
bats_load_library 'bats/bats-file/load.bash'

@test "images unpack: run without parameters" {
    run torizoncore-builder images unpack
    assert_failure 254
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
    run torizoncore-builder images --remove-storage unpack teziimage_invalid.tar
    assert_failure 4
}

@test "images unpack: unpack image from tar file" {
    torizoncore-builder-clean-storage

    run torizoncore-builder images --remove-storage unpack $DEFAULT_TEZI_IMAGE
    assert_success
    assert_output --partial "Unpacked OSTree from Toradex Easy Installer image"

    run torizoncore-builder-shell "ls /storage/"
    assert_success
    assert_output --regexp "ostree-archive.*sysroot.*tezi"
}

@test "images unpack: unpack image from directory" {
    torizoncore-builder-clean-storage

    unpack-image $DEFAULT_TEZI_IMAGE
    local IMAGE_DIR=$(echo $DEFAULT_TEZI_IMAGE | sed 's/\.tar$//g')

    run torizoncore-builder images --remove-storage unpack $IMAGE_DIR
    assert_success
    assert_output --partial "Unpacked OSTree from Toradex Easy Installer image"

    run torizoncore-builder-shell "ls /storage/"
    assert_success
    assert_output --regexp "ostree-archive.*sysroot.*tezi"
}

@test "images unpack: keep only /storage/toolchain directory in storage" {
    torizoncore-builder-clean-storage

    torizoncore-builder-shell "mkdir -p /storage/{dt,changes,kernel}"
    torizoncore-builder-shell "mkdir -p /storage/toolchain"
    torizoncore-builder-shell "mkdir -p /storage/dir{1,2,3}"

    torizoncore-builder images --remove-storage unpack $DEFAULT_TEZI_IMAGE

    run torizoncore-builder-shell "ls -l /storage/{dir}?"
    assert_failure
    run torizoncore-builder-shell "ls -l /storage/{dt,changes,kernel}"
    assert_failure
    run torizoncore-builder-shell "ls -l /storage/toolchain"
    assert_success
}
