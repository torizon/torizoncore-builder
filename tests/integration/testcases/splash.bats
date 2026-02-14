
bats_load_library 'bats/bats-support/load.bash'
bats_load_library 'bats/bats-assert/load.bash'
bats_load_library 'bats/bats-file/load.bash'

@test "splash: run without parameters" {
    run torizoncore-builder splash
    assert_failure
    assert_output --partial "the following arguments are required: SPLASH_IMAGE"
}

@test "splash: check help output" {
    run torizoncore-builder splash --help
    assert_success
    assert_output --partial "Path and name of splash screen image (REQUIRED)."
}

@test "splash: run with the deprecated --image switch" {
    run torizoncore-builder splash --image $SAMPLES_DIR/splash/fast-banana.png
    assert_failure
    assert_output --partial "Error: the switch --image has been removed"
    assert_output --partial "please provide the image filename without passing the switch."
}

@test "splash: run with the deprecated --work-dir switch" {
    run torizoncore-builder splash --work-dir /tmp \
                                   $SAMPLES_DIR/splash/fast-banana.png
    assert_failure
    assert_output --partial "Error: the switch --work-dir has been removed"
    assert_output --partial "the initramfs file should be created in storage."
}

@test "splash: create splash initramfs without images unpack" {
    torizoncore-builder-clean-storage

    run torizoncore-builder splash $SAMPLES_DIR/splash/fast-banana.png
    assert_failure
    assert_output --partial "Error: could not find an Easy Installer or WIC image in the storage."
    assert_output --partial "Please use the 'images' command to unpack an image before running this command."
}

@test "splash: create splash" {
    torizoncore-builder images --remove-storage unpack $DEFAULT_TEZI_IMAGE

    run torizoncore-builder splash $SAMPLES_DIR/splash/fast-banana.png
    assert_success
    assert_output --partial "Initramfs splash screen updated"
    assert_output --partial "Sysroot splash screen updated"

    local STORAGE_DIR="/storage/splash"
    if [ "${DEFAULT_TEZI_IMAGE_HAS_FIT_KERNEL}" != "1" ]; then
        run torizoncore-builder-shell "ls -l ${STORAGE_DIR}/usr/lib/modules/*/initramfs.img"
        assert_success
    else
        STORAGE_DIR="/storage/kernel"
        run torizoncore-builder-shell "ls -l ${STORAGE_DIR}/usr/lib/modules/*/vmlinuz"
        assert_success
    fi

    run torizoncore-builder-shell "ls -l ${STORAGE_DIR}/usr/share/plymouth/themes/spinner/watermark.png"
    assert_success
}
