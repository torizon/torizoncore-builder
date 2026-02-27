bats_load_library 'bats/bats-support/load.bash'
bats_load_library 'bats/bats-assert/load.bash'
bats_load_library 'bats/bats-file/load.bash'

@test "dto: run without parameters" {
    run torizoncore-builder dto
    assert_failure 2
    assert_output --partial "error: the following arguments are required: cmd"
}

@test "dto: check help output" {
    run torizoncore-builder dto --help
    assert_success
    assert_output --partial "{apply,list,status,remove,deploy}"
}

@test "dto list: run command without images unpack" {
    torizoncore-builder-clean-storage

    # Populate work directory with sample device-trees directory.
    rm -rf device-trees
    tar -xvf "${SAMPLES_DIR}/device-trees/device-trees.tar.gz"

    run torizoncore-builder dto list
    assert_failure
    assert_output --partial "Error: could not find an Easy Installer or WIC image in the storage."
    assert_output --partial "Please use the 'images' command to unpack an image before running this command."
}

@test "dto list: show compatible overlays" {
    torizoncore-builder images --remove-storage unpack "${DEFAULT_TEZI_IMAGE}"
    rm -rf device-trees/

    run torizoncore-builder dto list
    assert_failure
    assert_output --partial "error: missing device tree overlays directory 'device-trees/overlays'"

    # Populate work directory with sample device-trees directory.
    tar -xvf "${SAMPLES_DIR}/device-trees/device-trees.tar.gz"

    echo "Try listing overlays compatible with a bad device tree."
    run torizoncore-builder dto list --device-tree "bad-devtree.dtx"
    assert_failure
    assert_output --partial "error: the argument to --device-tree must be either a device tree source (.dts) or binary/blob (.dtb)"

    echo "Try listing overlays compatible with an unexisting device tree."
    run torizoncore-builder dto list --device-tree "bad-devtree.dts"
    assert_failure
    assert_output --partial "error: cannot read device tree source"

    echo "Check error output if user is passing a path to a device-tree blob."
    run torizoncore-builder dto list --device-tree "test/base.dtb"
    assert_failure
    assert_output --partial "device tree name (test/base.dtb) must not contain slashes."

    # Check compatibility given a .dts file (arm32); nothing in the image matters.
    echo "Check compatibility given a .dts file (arm32)."
    run torizoncore-builder dto list --device-tree "device-trees/dts-arm32/imx6dl-colibri-aster.dts"
    assert_success
    assert_output --partial "Overlays compatible with device tree"
    assert [ "$(echo "${output}" | grep -c -e '^- ')" == 16 ]

    # Check compatibility given a .dts file (arm64); nothing in the image matters.
    echo "Check compatibility given a .dts file (arm64)."
    run torizoncore-builder dto list --device-tree "device-trees/dts-arm64/imx8mm-verdin-nonwifi-dahlia.dts"
    assert_success
    assert_output --partial "Overlays compatible with device tree"
    assert [ "$(echo "${output}" | grep -c -e '^- ')" == 6 ]

    # Check compatibility with applied device-tree.
    echo "Check compatibility with applied device-tree."
    run torizoncore-builder dt apply device-trees/dts-arm32/imx6dl-colibri-aster.dts
    assert_success
    run torizoncore-builder dto list #--device-tree NOT-NEEDED
    assert_success
    assert_output --partial "Overlays compatible with device tree"
    assert [ "$(echo "${output}" | grep -c -e '^- ')" == 16 ]

    # Remove the device-tree applied in the previous step (or previously existing).
    run torizoncore-builder-shell \
	'[ -d /storage/dt ] && sed -i -e "/^fdtfile=/d" /storage/dt/usr/lib/ostree-boot/uEnv.txt'
    run torizoncore-builder-shell \
	'[ -d /storage/kernel ] && sed -i -e "/^fdtfile=/d" /storage/kernel/usr/lib/ostree-boot/uEnv.txt'
    run torizoncore-builder-shell \
	'sed -i -e "/^fdtfile=/d" /storage/tezi/u-boot-initial-env* || true'
    echo "Check behavior when no default device tree is set."
    run torizoncore-builder dto list
    assert_output --partial "Could not determine default device tree"
    if [ "$status" -eq 0 ]; then
	assert_output --partial "Proceeding with the following device tree as the assumed default"
	assert_output --regexp "(Overlays compatible with device tree|No overlays compatible with device tree)"
    else
	assert_output --partial "Please use --device-tree to pass one of the device trees"
    fi
}

@test "dto apply: run command without images unpack" {
    torizoncore-builder-clean-storage

    run torizoncore-builder dto apply --force "${SAMPLES_DIR}/dts/sample_overlay.dts"
    assert_failure
    assert_output --partial "Error: could not find an Easy Installer or WIC image in the storage."
    assert_output --partial "Please use the 'images' command to unpack an image before running this command."
}

@test "dto apply: check proper application of overlays" {
    torizoncore-builder images --remove-storage unpack "${DEFAULT_TEZI_IMAGE}"

    run torizoncore-builder dt apply "${SAMPLES_DIR}/dts/small-nodev.dts"
    assert_success

    local exp_dtos_path="${SAMPLES_DIR}/dts/sample_overlay.dts"
    local exp_dtos_name=${exp_dtos_path##*/}
    local exp_dtob_name=${exp_dtos_name%%.*}.dtbo

    echo "Check error output if user is passing a path to a device-tree blob."
    run torizoncore-builder dto apply "${exp_dtos_path}" --device-tree "test/base.dtb"
    assert_failure
    assert_output --partial "device tree name (test/base.dtb) must not contain slashes."

    echo "Initial application of sample overlay."
    run torizoncore-builder dto apply "${exp_dtos_path}"
    assert_success
    assert_output --partial "Overlay ${exp_dtob_name} successfully applied"

    echo "Second application of sample overlay (not forced)."
    run torizoncore-builder dto apply "${exp_dtos_path}"
    assert_failure
    assert_output --partial "${exp_dtob_name} is already applied."

    # Second application (forced); same behavior as (not forced) because the --force switch
    # only prevents the "test application" of the overlay.
    echo "Second application of sample overlay (forced)."
    run torizoncore-builder dto apply --force "${exp_dtos_path}"
    assert_failure
    assert_output --partial "${exp_dtob_name} is already applied."

    # Bad overlay.
    echo "Attempt applying a bad (not-applicable) overlay."
    run torizoncore-builder dto apply "${SAMPLES_DIR}/dts/bad_overlay.dts"
    assert_failure
    assert_output --partial "'bad_overlay.dts' compiles successfully"
    assert_output --partial "cannot apply device tree overlay"

    if [ "${DEFAULT_TEZI_IMAGE_HAS_FIT_KERNEL}" = "1" ]; then
        echo "Checking existence of overlays.txt in the kernel changes directory."
	run torizoncore-builder-shell "cat /storage/kernel/usr/lib/modules/*/dtb/overlays.txt"
	assert_success
	assert_output --regexp "^fdt_overlays=${exp_dtob_name}\$"

	# Ensure presence of the various nodes in the kernel FIT image.
        echo "Checking existence of overlay inside FIT image."
        run torizoncore-builder-shell \
            "VMLINUZ=\$(find /storage/kernel -name vmlinuz); echo \${VMLINUZ}; test -n \"\${VMLINUZ}\""
        assert_success
        local kpath="${output}"

        echo "Checking existence of a new configuration node."
        run torizoncore-builder-shell \
            "fdtget ${kpath} -l /configurations | grep -F '${exp_dtob_name}'"
        assert_success
        local config_node="${output}"

        echo "Checking existence of a new image node."
        run torizoncore-builder-shell \
            "fdtget ${kpath} -l /images | grep -F '${exp_dtob_name}'"
        assert_success
        local image_node="${output}"

        echo "Ensuring config node points to image node."
        run torizoncore-builder-shell \
            "test \"\$(fdtget ${kpath} /configurations/${config_node} fdt)\" == \"${image_node}\""
        assert_success
    else
        echo "Checking existence of overlays.txt in the dt changes directory."
	run torizoncore-builder-shell "cat /storage/dt/usr/lib/modules/*/dtb/overlays.txt"
	assert_success
	assert_output --regexp "^fdt_overlays=${exp_dtob_name}\$"

        echo "Checking presence of new DTBO in the overlays directory."
	run torizoncore-builder-shell "ls /storage/dt/usr/lib/modules/*/dtb/overlays/"
	assert_success
	assert_output --regexp "^${exp_dtob_name}\$"
    fi
}

@test "dto status: run command without images unpack" {
    torizoncore-builder-clean-storage

    run torizoncore-builder dto status
    assert_failure
    assert_output --partial "Error: could not find an Easy Installer or WIC image in the storage."
    assert_output --partial "Please use the 'images' command to unpack an image before running this command."
}

@test "dto status: check currently applied overlays" {
    run torizoncore-builder images --remove-storage unpack "${DEFAULT_TEZI_IMAGE}"

    run torizoncore-builder dt apply "${SAMPLES_DIR}/dts/small-nodev.dts"
    run torizoncore-builder dto status
    # Print command output for debugging purposes
    echo "${output}"
    assert_success
    assert_output --partial "Enabled overlays over device tree small-nodev.dtb"
    assert [ "$(echo "${output}" | grep -c -e '^- ')" == 0 ]

    run torizoncore-builder dto apply "${SAMPLES_DIR}/dts/sample_overlay.dts" --force
    run torizoncore-builder dto status
    assert_success
    assert_output --partial "Enabled overlays over device tree small-nodev.dtb"
    assert_output --partial "sample_overlay.dtbo"
    assert [ "$(echo "${output}" | grep -c -e '^- ')" == 1 ]

    # Remove the device-tree applied in the previous step.
    run torizoncore-builder-shell \
	'[ -d /storage/dt ] && sed -i -e "/^fdtfile=/d" /storage/dt/usr/lib/ostree-boot/uEnv.txt'
    run torizoncore-builder-shell \
	'[ -d /storage/kernel ] && sed -i -e "/^fdtfile=/d" /storage/kernel/usr/lib/ostree-boot/uEnv.txt'
    run torizoncore-builder-shell \
	'sed -i -e "/^fdtfile=/d" /storage/tezi/u-boot-initial-env* || true'
    run torizoncore-builder dto status
    assert_success
    assert_output --partial "Enabled overlays over unknown device tree"
    assert_output --partial "sample_overlay.dtbo"
    assert [ "$(echo "${output}" | grep -c -e '^- ')" == 1 ]
}

@test "dto remove: run command without images unpack" {
    torizoncore-builder-clean-storage

    run torizoncore-builder dto remove sample_overlay.dtbo
    assert_failure
    assert_output --partial "Error: could not find an Easy Installer or WIC image in the storage."
    assert_output --partial "Please use the 'images' command to unpack an image before running this command."
}

@test "dto remove: check removal of specific overlays (non-FIT)" {
    requires-non-fit-kernel

    run torizoncore-builder images --remove-storage unpack "${DEFAULT_TEZI_IMAGE}"

    # Set the stage: apply multiple overlays (possibly adding to previous ones).
    run torizoncore-builder dto apply "${SAMPLES_DIR}/dts/sample_overlay.dts" --force
    assert_success
    run torizoncore-builder dto apply "${SAMPLES_DIR}/dts/sample_overlay1.dts" --force
    assert_success
    run torizoncore-builder dto apply "${SAMPLES_DIR}/dts/sample_overlay2.dts" --force
    assert_success

    # Check initial state:
    run torizoncore-builder-shell \
	"find /storage/dt/usr/lib/modules -name 'overlays.txt' -exec cat '{}' ';'"
    assert_output --partial "sample_overlay.dtbo"
    assert_output --partial "sample_overlay1.dtbo"
    assert_output --partial "sample_overlay2.dtbo"
    run torizoncore-builder-shell "find /storage/dt/usr/lib/modules -name '*.dtbo'"
    assert_output --partial "dtb/overlays/sample_overlay.dtbo"
    assert_output --partial "dtb/overlays/sample_overlay1.dtbo"
    assert_output --partial "dtb/overlays/sample_overlay2.dtbo"
    
    # Remove an overlay and recheck:
    run torizoncore-builder dto remove sample_overlay1.dtbo
    assert_success
    run torizoncore-builder-shell \
	"find /storage/dt/usr/lib/modules -name 'overlays.txt' -exec cat '{}' ';'"
    assert_output --partial "sample_overlay.dtbo"
    refute_output --partial "sample_overlay1.dtbo"
    assert_output --partial "sample_overlay2.dtbo"
    run torizoncore-builder-shell "find /storage/dt/usr/lib/modules -name '*.dtbo'"
    assert_output --partial "dtb/overlays/sample_overlay.dtbo"
    refute_output --partial "dtb/overlays/sample_overlay1.dtbo"
    assert_output --partial "dtb/overlays/sample_overlay2.dtbo"

    # Remove another overlay and recheck:
    run torizoncore-builder dto remove sample_overlay.dtbo
    assert_success
    run torizoncore-builder-shell \
	"find /storage/dt/usr/lib/modules -name 'overlays.txt' -exec cat '{}' ';'"
    refute_output --partial "sample_overlay.dtbo"
    refute_output --partial "sample_overlay1.dtbo"
    assert_output --partial "sample_overlay2.dtbo"
    run torizoncore-builder-shell "find /storage/dt/usr/lib/modules -name '*.dtbo'"
    refute_output --partial "dtb/overlays/sample_overlay.dtbo"
    refute_output --partial "dtb/overlays/sample_overlay1.dtbo"
    assert_output --partial "dtb/overlays/sample_overlay2.dtbo"
}

@test "dto remove: check removal of specific overlays (FIT)" {
    requires-fit-kernel

    run torizoncore-builder images --remove-storage unpack "${DEFAULT_TEZI_IMAGE}"

    # Determine overlays originally applied (if any):
    run torizoncore-builder dto status
    assert_success
    local org_overlays=( $(echo "${output}" | sed -ne 's/^- //p') )

    # Set the stage: apply multiple overlays (possibly adding to previous ones).
    run torizoncore-builder dto apply "${SAMPLES_DIR}/dts/sample_overlay.dts" --force
    assert_success
    run torizoncore-builder dto apply "${SAMPLES_DIR}/dts/sample_overlay1.dts" --force
    assert_success

    # Get the location of the kernel contents we'll be checking ahead.
    run torizoncore-builder-shell \
        "VMLINUZ=\$(find /storage/kernel -name vmlinuz); echo \${VMLINUZ}; test -n \"\${VMLINUZ}\""
    assert_success
    local kpath="${output}"

    # Check initial state:
    echo "Checking existence of a new configuration nodes."
    run torizoncore-builder-shell \
	"fdtget ${kpath} -l /configurations | grep -F 'sample_overlay.dtbo'"
    assert_success
    run torizoncore-builder-shell \
        "fdtget ${kpath} -l /configurations | grep -F 'sample_overlay1.dtbo'"
    assert_success

    echo "Checking existence of a new image nodes."
    run torizoncore-builder-shell \
        "fdtget ${kpath} -l /images | grep -F 'sample_overlay.dtbo'"
    assert_success
    run torizoncore-builder-shell \
        "fdtget ${kpath} -l /images | grep -F 'sample_overlay1.dtbo'"
    assert_success

    # Remove an overlay and recheck:
    run torizoncore-builder --log-level debug dto remove "sample_overlay.dtbo"
    assert_success
    assert_output --partial "Overlay 'sample_overlay.dtbo' is not present in base image"
    run torizoncore-builder dto status
    assert_success
    refute_output --partial "sample_overlay.dtbo"

    echo "Checking removal of 'sample_overlay.dtbo' configuration node."
    run torizoncore-builder-shell \
	"fdtget ${kpath} -l /configurations | grep -F 'sample_overlay.dtbo'"
    assert_failure
    run torizoncore-builder-shell \
        "fdtget ${kpath} -l /configurations | grep -F 'sample_overlay1.dtbo'"
    assert_success

    echo "Checking removal of 'sample_overlay.dtbo' image node."
    run torizoncore-builder-shell \
        "fdtget ${kpath} -l /images | grep -F 'sample_overlay.dtbo'"
    assert_failure
    run torizoncore-builder-shell \
        "fdtget ${kpath} -l /images | grep -F 'sample_overlay1.dtbo'"
    assert_success
    
    # Remove another overlay and recheck:
    run torizoncore-builder --log-level debug dto remove "sample_overlay1.dtbo"
    assert_success
    assert_output --partial "Overlay 'sample_overlay1.dtbo' is not present in base image"
    assert_success
    run torizoncore-builder dto status
    assert_success
    refute_output --partial "sample_overlay1.dtbo"

    echo "Checking removal of 'sample_overlay1.dtbo' configuration node."
    run torizoncore-builder-shell \
	"fdtget ${kpath} -l /configurations | grep -F 'sample_overlay1.dtbo'"
    assert_failure

    echo "Checking removal of 'sample_overlay1.dtbo' image node."
    run torizoncore-builder-shell \
        "fdtget ${kpath} -l /images | grep -F 'sample_overlay1.dtbo'"
    assert_failure

    if [ "${#org_overlays[@]}" -ge 2 ]; then
	# Since the original image had at least two pre-applied overlays, use them
	# for some additional tests:
	#
	# - Case 1: Try to remove a pre-applied overlay; in that case the overlay
	#   should not be really deleted (since we try to mimic the behavior of
	#   non-FIT where overlays can only be added or modified).
	# - Case 2: Overwrite and then delete a pre-applied ovelay; in such a case,
	#   after the deletion, again the overlay should be restored from the base
	#   image.
	#

	# Case 1:
	local ovl1_to_delete="${org_overlays[0]}"
	local ovl1_img_node
	run torizoncore-builder-shell \
            "fdtget ${kpath} -l /images | grep -F '${ovl1_to_delete}'"
	assert_success
	ovl1_img_node="${output}"

	torizoncore-builder-shell \
	    "fdtget -t bx '${kpath}' '/images/${ovl1_img_node}' data" \
	    > "ovl1_data_org.hex"

	run torizoncore-builder --log-level debug dto remove "${ovl1_to_delete}"
	assert_success
	assert_output --partial "Overlay '${ovl1_to_delete}' was restored from base image"

	torizoncore-builder-shell \
	    "fdtget -t bx '${kpath}' '/images/${ovl1_img_node}' data" \
	    > "ovl1_data_del.hex"

	run cmp "ovl1_data_org.hex" "ovl1_data_del.hex"
	assert_success

	# Case 2:
	local ovl2_to_delete="${org_overlays[1]}"
	local ovl2_img_node
	run torizoncore-builder-shell \
            "fdtget ${kpath} -l /images | grep -F '${ovl2_to_delete}'"
	assert_success
	ovl2_img_node="${output}"

	torizoncore-builder-shell \
	    "fdtget -t bx '${kpath}' '/images/${ovl2_img_node}' data" \
	    > "ovl2_data_org.hex"

	# Replace the overlay from the base image:
	cp "${SAMPLES_DIR}/dts/sample_overlay.dts" "${ovl2_to_delete%.dtbo}.dts"
	run torizoncore-builder --log-level debug dto remove "${ovl2_to_delete}"
	assert_success
	run torizoncore-builder dto apply "${ovl2_to_delete%.dtbo}.dts" --force
	assert_success
	torizoncore-builder-shell \
	    "fdtget -t bx '${kpath}' '/images/${ovl2_img_node}' data" \
	    > "ovl2_data_mod.hex"

	run torizoncore-builder --log-level debug dto remove "${ovl2_to_delete}"
	assert_success
	assert_output --partial "Overlay '${ovl2_to_delete}' was restored from base image"

	torizoncore-builder-shell \
	    "fdtget -t bx '${kpath}' '/images/${ovl2_img_node}' data" \
	    > "ovl2_data_del.hex"

	run cmp "ovl2_data_org.hex" "ovl2_data_mod.hex"
	assert_failure
	run cmp "ovl2_data_org.hex" "ovl2_data_del.hex"
	assert_success
    fi
}

@test "dto remove: check removal of all overlays" {
    run torizoncore-builder images --remove-storage unpack "${DEFAULT_TEZI_IMAGE}"

    # Set the stage: apply multiple overlays (possibly adding to previous ones).
    run torizoncore-builder dto apply "${SAMPLES_DIR}/dts/sample_overlay.dts" --force
    assert_success
    run torizoncore-builder dto apply "${SAMPLES_DIR}/dts/sample_overlay1.dts" --force
    assert_success
    run torizoncore-builder dto apply "${SAMPLES_DIR}/dts/sample_overlay2.dts" --force
    assert_success

    # Check initial state:
    run torizoncore-builder dto status
    assert_success
    assert_output --partial "sample_overlay.dtbo"
    assert_output --partial "sample_overlay1.dtbo"
    assert_output --partial "sample_overlay2.dtbo"
    
    # Remove an overlay and recheck:
    run torizoncore-builder dto remove --all
    assert_success
    run torizoncore-builder dto status
    assert_success
    refute_output --regexp "- .*\\.dtbo"
}

# bats test_tags=requires-device
@test "dto: apply overlay and deploy it on the device" {
    requires-device
    requires-non-fit-kernel
    # NOTE: To test with FIT we'd need to re-sign the image.

    run device-shell "cat /proc/device-tree/tcb_prop_test"
    assert_failure 1

    torizoncore-builder images --remove-storage unpack "${DEFAULT_TEZI_IMAGE}"
    torizoncore-builder dto apply --force "${SAMPLES_DIR}/dts/sample_overlay.dts"
    torizoncore-builder union branch1
    run torizoncore-builder deploy \
	--remote-host "${DEVICE_ADDR}" --remote-username "${DEVICE_USER}" \
        --remote-password "${DEVICE_PASSWORD}" --remote-port "${DEVICE_PORT}" \
	--reboot branch1
    assert_success
    assert_output --partial "Deploying successfully finished"

    run device-wait 20
    assert_success

    run device-shell "cat /proc/device-tree/tcb_prop_test"
    assert_success
    assert_output --partial "tcb_prop_value"
}

# bats test_tags=requires-device
@test "dto: remove overlay from the device" {
    requires-device
    requires-non-fit-kernel
    # NOTE: To test with FIT we'd need to re-sign the image.

    # This test assumes that sample_overlay.dtbo is already
    # present and used in the device
    run device-shell "cat /proc/device-tree/tcb_prop_test"
    assert_success
    assert_output --partial "tcb_prop_value"

    # Recreate image with overlay
    torizoncore-builder images --remove-storage unpack "${DEFAULT_TEZI_IMAGE}"
    torizoncore-builder dto apply --force "${SAMPLES_DIR}/dts/sample_overlay.dts"
    run torizoncore-builder dto status
    assert_success
    assert_output --partial "sample_overlay.dtbo"

    run torizoncore-builder dto remove sample_overlay.dtbo
    assert_success

    run torizoncore-builder dto status
    assert_success
    refute_output --partial "sample_overlay.dtbo"

    torizoncore-builder union branch2
    run torizoncore-builder deploy \
        --remote-host "${DEVICE_ADDR}" --remote-username "${DEVICE_USER}" \
        --remote-password "${DEVICE_PASSWORD}" --remote-port "${DEVICE_PORT}" \
	--reboot branch2
    assert_success
    assert_output --partial "Deploying successfully finished"

    run device-wait 20
    assert_success

    run device-shell "cat /proc/device-tree/tcb_prop_test"
    assert_failure 1
}
