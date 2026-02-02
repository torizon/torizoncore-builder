bats_load_library 'bats/bats-support/load.bash'
bats_load_library 'bats/bats-assert/load.bash'
bats_load_library 'bats/bats-file/load.bash'

@test "splash-config: run without parameters" {
    run torizoncore-builder splash-config
    assert_failure
    assert_output --partial "the following arguments are required"
}

@test "splash-config: check help output" {
    run torizoncore-builder splash-config --help
    assert_success
    assert_output --partial "Sets a new Plymouth configuration"
}

@test "splash-config set: without parameters" {
    run torizoncore-builder splash-config set
    assert_failure
    assert_output --partial "the following arguments are required: SPLASH_CONFIG"
}

@test "splash-config set: check help output" {
    run torizoncore-builder splash-config set --help
    assert_success
    assert_output --partial "File path to the new configuration file"
}

@test "splash-config set: without images unpack" {
    torizoncore-builder-clean-storage

    run torizoncore-builder splash-config set foo
    assert_failure
    assert_output --partial "Error: could not find an Easy Installer or WIC image in the storage."
    assert_output --partial "Please use the 'images' command to unpack an image before running this command."
}

@test "splash-config set: file not found" {
    torizoncore-builder images --remove-storage unpack $DEFAULT_WIC_IMAGE

    run torizoncore-builder splash-config set foo
    assert_failure
    assert_output --partial "Unable to find configuration file"
}

@test "splash-config set: standard success case" {
    torizoncore-builder images --remove-storage unpack $DEFAULT_WIC_IMAGE

    run torizoncore-builder splash-config set $SAMPLES_DIR/splashconfig/test.plymouth
    assert_success
    assert_output --partial "Splash screen configuration updated"

    run torizoncore-builder-shell "ls -l /storage/splash/usr/share/plymouth/themes/spinner/spinner.plymouth"
    assert_success
}

@test "splash-config dump: check help output" {
    run torizoncore-builder splash-config dump --help
    assert_success
    assert_output --partial "Writes current Plymouth configuration"
}

@test "splash-config dump: without images unpack" {
    torizoncore-builder-clean-storage

    run torizoncore-builder splash-config dump
    assert_failure
    assert_output --partial "Error: could not find an Easy Installer or WIC image in the storage."
    assert_output --partial "Please use the 'images' command to unpack an image before running this command."
}

@test "splash-config dump: success case default configuration" {
    torizoncore-builder images --remove-storage unpack $DEFAULT_WIC_IMAGE

    run torizoncore-builder splash-config dump    
    assert_success
    assert_output --partial "Found default configuration file."
    assert_output --partial "Adoption of official Spinner Theme for"
}

@test "splash-config dump: success case custom configuration" {
    torizoncore-builder images --remove-storage unpack $DEFAULT_WIC_IMAGE

    run torizoncore-builder splash-config set $SAMPLES_DIR/splashconfig/test.plymouth
    assert_success

    run torizoncore-builder splash-config dump
    assert_success
    assert_output --partial "Found customized configuration file."
    assert_output --partial "Spinner theme config file for TCB"
}

@test "splash-config dump: success case output to file" {
    torizoncore-builder images --remove-storage unpack $DEFAULT_WIC_IMAGE

    run torizoncore-builder splash-config set $SAMPLES_DIR/splashconfig/test.plymouth
    assert_success

    run torizoncore-builder splash-config dump --file $SAMPLES_DIR/splashconfig/out.plymouth
    assert_success
    assert_output --partial "Found customized configuration file."
    assert_output --partial "Creating configuration file"

    grep "Spinner theme config file for TCB" $SAMPLES_DIR/splashconfig/out.plymouth
    assert_success

    rm -f $SAMPLES_DIR/splashconfig/out.plymouth
}
