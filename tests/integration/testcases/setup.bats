bats_load_library 'bats/bats-support/load.bash'
bats_load_library 'bats/bats-assert/load.bash'
bats_load_library 'bats/bats-file/load.bash'

# bats test_tags=requires-device
@test "Check if versions of file and installed on device matches" {
    requires-device

    DEVICE_INFO=$(device-shell cat /etc/os-release)
    installed_version=$(echo "$DEVICE_INFO" | grep VERSION_ID | cut -d= -f2 | tr -d '"')

    testing_version=$(echo "$DEFAULT_TEZI_IMAGE" | tr ' ' '\n' |
                            grep "torizon.*-"$TCB_MACHINE"-Tezi_.*\.tar" |
			                sed 's/.*Tezi_//;s/\.tar//' | sed 's/+/-/')

    assert_equal "$installed_version" "$testing_version"
}
