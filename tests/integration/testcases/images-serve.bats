bats_load_library 'bats/bats-support/load.bash'
bats_load_library 'bats/bats-assert/load.bash'
bats_load_library 'bats/bats-file/load.bash'

teardown() {
    # Make sure background process is finished in case of errors.
    stop-torizoncore-builder-bg
}

@test "images serve: check help output" {
    run torizoncore-builder images serve --help
    assert_success
    assert_output --partial 'Path to directory holding Toradex Easy Installer images.'
}

@test "images serve: check if 'image_list.json' file exists" {
    local IMAGE_DIR=$(mktemp -d tmpdir.XXXXXXXXXXXXXXXXXXXXXXXXX)

    run torizoncore-builder images serve $IMAGE_DIR
    assert_failure
    assert_output --regexp 'Error: The Toradex Easy Installer.*does not exist inside.*directory.$'

    rm -rf $IMAGE_DIR
}

@test "images serve: check zeroconf tezi service response." {
    IMAGE_DIR="samples/images"
    torizoncore-builder-bg-tcb_network images serve $IMAGE_DIR

    run docker run -i --rm --privileged --network=tcb_network alpine:latest sh -c "
        apk update && apk add avahi avahi-tools dbus &&
        mkdir -p /run/dbus &&
        dbus-uuidgen > /var/lib/dbus/machine-id &&
        dbus-daemon --system &&
        avahi-daemon --daemonize --no-chroot &&
        avahi-browse-domains -a -t
    "
    assert_success
    assert_output --partial '_tezi._tcp'
    assert_output --partial 'Custom Toradex Easy Installer Feed'
    stop-torizoncore-builder-bg
}

@test "images serve: check if 'image_list.json' is being served." {
    IMAGE_DIR="samples/images"
    torizoncore-builder-bg images serve $IMAGE_DIR

    run docker run --rm --network=host busybox:stable wget -S http://localhost/image_list.json -O -
    assert_success
    assert_output --partial 'Cache-Control: no-store,max-age=0'
    assert_output --partial 'config_format'
    assert_output --partial '/image.json'
    stop-torizoncore-builder-bg
}
