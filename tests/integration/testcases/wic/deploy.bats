bats_load_library 'bats/bats-support/load.bash'
bats_load_library 'bats/bats-assert/load.bash'
bats_load_library 'bats/bats-file/load.bash'
load '../lib/common.bash'

@test "deploy: run without parameters" {
    run torizoncore-builder deploy
    assert_failure 255
    assert_output --partial "One of the following arguments is required: --output-directory, --base-wic, --remote-host"
}

@test "deploy: check help output" {
    run torizoncore-builder deploy --help
    assert_success
    assert_output --partial "usage: torizoncore-builder deploy"
}

@test "deploy: deploy changes to WIC image without images unpack" {
    torizoncore-builder-clean-storage

    run torizoncore-builder deploy --base-wic some_file some_branch
    assert_failure
    assert_output --partial "Error: could not find an Easy Installer or WIC image in the storage."
    assert_output --partial "Please use the 'images' command to unpack an image before running this command."
}

@test "deploy: deploy changes to WIC image with an invalid base rootfs label" {
    torizoncore-builder-clean-storage
    torizoncore-builder images --remove-storage unpack $DEFAULT_WIC_IMAGE
    torizoncore-builder union --changes-directory $SAMPLES_DIR/changes branch1

    rm -rf out.wic
    run torizoncore-builder deploy --base-wic $DEFAULT_WIC_IMAGE --wic-rootfs-label invalid_label --output-wic out.wic branch1
    assert_failure
    assert_output --partial "Filesystem with label 'invalid_label' not found in image"
}

@test "deploy: deploy changes to WIC image" {
    local ROOTFS=temp_rootfs
    rm -rf my_new_image
    rm -rf $ROOTFS

    torizoncore-builder-clean-storage
    torizoncore-builder images --remove-storage unpack $DEFAULT_WIC_IMAGE
    torizoncore-builder union --changes-directory $SAMPLES_DIR/changes branch1

    run torizoncore-builder deploy --base-wic $DEFAULT_WIC_IMAGE --output-wic my_new_image branch1
    assert_success
    assert_output --partial "created successfully!"

#     mkdir $ROOTFS && cd $ROOTFS
#     tar -I zstd -xvf ../my_new_image/*.ota.tar.zst
#     run cat ostree/deploy/torizon/deploy/*/etc/myconfig.txt
#     assert_success
#     assert_output --partial "enabled=1"
#
#     check-file-ownership-as-workdir ../my_new_image
#     check-file-ownership-as-workdir ../my_new_image/*.ota.tar.zst
#
#     cd .. && rm -rf $ROOTFS my_new_image
}

# bats test_tags=requires-device
@test "deploy: deploy changes to device without images unpack" {
    requires-device
    torizoncore-builder-clean-storage

    run torizoncore-builder deploy --remote-host $DEVICE_ADDR \
                                   --remote-username $DEVICE_USER \
                                   --remote-password $DEVICE_PASS \
                                   --remote-port $DEVICE_PORT \
                                   --reboot some_branch
    assert_failure
    assert_output --partial "Error: could not find an Easy Installer or WIC image in the storage."
    assert_output --partial "Please use the 'images' command to unpack an image before running this command."
}

# bats test_tags=requires-device
@test "deploy: deploy changes to device" {
    requires-device

    torizoncore-builder-clean-storage
    torizoncore-builder images --remove-storage unpack $DEFAULT_WIC_IMAGE
    torizoncore-builder union --changes-directory $SAMPLES_DIR/changes2 branch1

    run torizoncore-builder deploy --remote-host $DEVICE_ADDR \
                                   --remote-username $DEVICE_USER \
                                   --remote-password $DEVICE_PASS \
                                   --remote-port $DEVICE_PORT \
                                   --reboot branch1
    assert_success
    assert_output --partial "Deploying successfully finished"

    run device-wait 20
    assert_success

    run device-shell-root /usr/sbin/secret_of_life
    assert_failure 42
}
