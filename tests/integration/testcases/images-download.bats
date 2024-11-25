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

# bats test_tags=requires-device
@test "images download: download image based on device" {
    requires-device
    torizoncore-builder-clean-storage

    # Run 'images download' in a separate directory so that check-file-ownership-as-workdir
    # doesn't mistakenly verify the image .tar already present in workdir
    rm -rf images_download_tmpdir
    mkdir -p images_download_tmpdir && cd images_download_tmpdir

    run torizoncore-builder images download --remote-host $DEVICE_ADDR \
                                            --remote-username $DEVICE_USER \
                                            --remote-password $DEVICE_PASSWORD \
                                            --remote-port $DEVICE_PORT
    assert_success
    assert_output --partial "Unpacked OSTree from Toradex Easy Installer image"
    IMAGE=$(echo $output | sed -n "s#\(.*/\)\(.*tar\)\(.*\)#\2#p")

    run torizoncore-builder-shell "ls /storage/"
    assert_success
    assert_output --regexp "ostree-archive.*sysroot.*tezi"

    check-file-ownership-as-workdir $IMAGE
    cd .. && rm -rf images_download_tmpdir
}
