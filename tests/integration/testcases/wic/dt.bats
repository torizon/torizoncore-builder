bats_load_library 'bats/bats-support/load.bash'
bats_load_library 'bats/bats-assert/load.bash'
bats_load_library 'bats/bats-file/load.bash'
load '../lib/common.bash'

setup_file() {
    local UNSUPPORTED_MACHINES="intel-corei7-64 qemux86-64"
    local ARCHIVE='/storage/ostree-archive/'
    local DEFAULT_REF='base'
    torizoncore-builder images --remove-storage unpack "${DEFAULT_WIC_IMAGE}"
    IMG_MACHINE=$(torizoncore-builder-shell "ostree --repo=${ARCHIVE} show \
                  --print-metadata-key='oe.machine' ${DEFAULT_REF}" | tr -d "'")

    case "${UNSUPPORTED_MACHINES}" in
        *${IMG_MACHINE}* )
            UNSUPPORTED_MACHINE="1"
            ;;
        *)
            UNSUPPORTED_MACHINE="0"
            ;;
    esac

    export UNSUPPORTED_MACHINE
    export IMG_MACHINE
}

setup() {
  if [ "${UNSUPPORTED_MACHINE}" = "1" ]; then
    skip "DT/DTO customization is not supported for ${IMG_MACHINE}"
  fi
}

@test "dt: run without parameters" {
    run torizoncore-builder dt
    assert_failure 2
    assert_output --partial "error: the following arguments are required: cmd"
}

@test "dt: check help output" {
    run torizoncore-builder dt --help
    assert_success
    assert_output --partial "{status,checkout,apply}"
}


@test "dt: check currently enabled device tree without images unpack" {
    torizoncore-builder-clean-storage

    run torizoncore-builder dt status
    assert_failure
    assert_output --partial "Error: could not find an Easy Installer or WIC image in the storage."
    assert_output --partial "Please use the 'images' command to unpack an image before running this command."
}

@test "dt: check currently enabled device tree" {
    torizoncore-builder images --remove-storage unpack $DEFAULT_WIC_IMAGE

    run torizoncore-builder dt status
    assert [ $? = "0" -o $? = "1" ]
    assert_output --regexp "Current device tree is|error: cannot identify the enabled device tree"
}

@test "dt: apply device tree in the image without images unpack" {
    torizoncore-builder-clean-storage

    run torizoncore-builder dt apply some_dto_file
    assert_failure
    assert_output --partial "Error: could not find an Easy Installer or WIC image in the storage."
    assert_output --partial "Please use the 'images' command to unpack an image before running this command."
}

@test "dt: apply device tree in the image" {
    torizoncore-builder images --remove-storage unpack $DEFAULT_WIC_IMAGE
    torizoncore-builder-shell "rm -rf device-trees"

    local exp_dts_path="$SAMPLES_DIR/dts/small-nodev.dts"
    local exp_dts_name=${exp_dts_path##*/}
    local exp_dtb_name=${exp_dts_name%%.*}.dtb

    run torizoncore-builder dt apply "${exp_dts_path}"
    assert_success
    assert_output --regexp "Device tree.*successfully applied"

    run torizoncore-builder dt status
    assert_success
    assert_output --partial "$DTB"

    echo "Checking existence of device-tree file in kernel dtb directory."
    run torizoncore-builder-shell \
        "DTB=\$(find /storage/dt/ -wholename '*/usr/lib/modules/*/dtb/${exp_dtb_name}'); echo \${DTB}; test -n \"\${DTB}\""
    assert_success
}
