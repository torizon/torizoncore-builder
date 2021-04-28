load 'bats/bats-support/load.bash'
load 'bats/bats-assert/load.bash'
load 'bats/bats-file/load.bash'

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
    assert_failure 254
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

    local IMAGE_DIR=$(echo $DEFAULT_TEZI_IMAGE | sed 's/\.tar$//g')
    run torizoncore-builder images --remove-storage unpack $IMAGE_DIR
    assert_success
    assert_output --partial "Unpacked OSTree from Toradex Easy Installer image"

    run torizoncore-builder-shell "ls /storage/"
    assert_success
    assert_output --regexp "ostree-archive.*sysroot.*tezi"
}
