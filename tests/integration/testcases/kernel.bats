bats_load_library 'bats/bats-support/load.bash'
bats_load_library 'bats/bats-assert/load.bash'
bats_load_library 'bats/bats-file/load.bash'
load 'lib/common.bash'

# Local helpers:
find_uenv_txt_in_sysroot() {
    # Get path:
    run torizoncore-builder-shell "find /storage/sysroot/ostree/deploy/ -name uEnv.txt"
    assert_success
    local uenv_path="${output}"
    # Sanity check:
    run torizoncore-builder-shell "[ -f '${uenv_path}' ]"
    assert_success
    echo "${uenv_path}"
}

find_uenv_txt_in_chgsdir() {
    # Get path:
    run torizoncore-builder-shell \
        "{ [ -d /storage/dt ] && find /storage/dt/ -name uEnv.txt; } ||" \
        "{ [ -d /storage/kernel ] && find /storage/kernel/ -name uEnv.txt; }"
    assert_success
    local uenv_path="${output}"
    # Sanity check:
    run torizoncore-builder-shell "[ -f '${uenv_path}' ]"
    assert_success
    echo "${uenv_path}"
}

is_ovl_kargs_passing_supported() {
    local uenv_path="${1?uEnv.txt path required}"
    torizoncore-builder-shell "grep -q '^set_bootargs_custom=' ${uenv_path}"
}

is_uenv_kargs_passing_supported() {
    local uenv_path="${1?uEnv.txt path required}"
    torizoncore-builder-shell "grep -q '^set_bootargs_custom2=' ${uenv_path}"
}

@test "kernel: run without parameters" {
    run torizoncore-builder kernel
    assert_failure 2
    assert_output --partial "{build_module,set_custom_args,get_custom_args,clear_custom_args}"
    assert_output --partial "error: the following arguments are required: cmd"
}

@test "kernel: check help output" {
    run torizoncore-builder kernel --help
    assert_success
    assert_output --partial "usage: torizoncore-builder kernel [-h]"
    assert_output --partial "{build_module,set_custom_args,get_custom_args,clear_custom_args}"
}

@test "kernel build_module: run without images unpack" {
    torizoncore-builder-clean-storage

    local SRC_DIR="source_dir"
    mkdir -p "${SRC_DIR}"

    run torizoncore-builder kernel build_module "${SRC_DIR}"
    assert_failure
    assert_output --partial "Error: could not find an Easy Installer or WIC image in the storage."
    assert_output --partial "Please use the 'images' command to unpack an image before running this command."

    torizoncore-builder-shell "rm -rf ${SRC_DIR}"
}

@test "kernel build_module: check success cases" {
    torizoncore-builder images --remove-storage unpack "${DEFAULT_TEZI_IMAGE}"

    local idx
    local BLD_MOD_ARGS=("" "--autoload" "" "--autoload")

    # Initial cleanup:
    for ((idx=0; idx<${#BLD_MOD_ARGS[@]}; idx++)); do
        local SRC_DIR="source_dir${idx}"
        torizoncore-builder-shell "rm -rf ${SRC_DIR}"
    done

    # Build a few versions of the same module:
    for ((idx=0; idx<${#BLD_MOD_ARGS[@]}; idx++)); do
        local SRC_DIR="source_dir${idx}"

        # Prepare source directory:
        mkdir -p "${SRC_DIR}"
        cp "${SAMPLES_DIR}/kernel/hello.c" "${SRC_DIR}/hello${idx}.c"
        cp "${SAMPLES_DIR}/kernel/Makefile" "${SRC_DIR}/Makefile"
        cp "${SAMPLES_DIR}/kernel/README.md" "${SRC_DIR}/README.md"
        sed -i -e "s#hello\\.o#hello${idx}.o#" "${SRC_DIR}/Makefile"

        torizoncore-builder-shell "chown 10:20 ${SRC_DIR}/README.md"

        echo "Building kernel module in '${SRC_DIR}' with args '${BLD_MOD_ARGS[idx]}'."
        # shellcheck disable=SC2086
        run torizoncore-builder kernel build_module ${BLD_MOD_ARGS[idx]} "${SRC_DIR}"
        assert_success

        run ls -ld "${SRC_DIR}/hello${idx}.ko"
        assert_success

        # Check files ownership as work dir
        check-file-ownership-as-workdir "${SRC_DIR}/hello${idx}.c"
        check-file-ownership-as-workdir "${SRC_DIR}/hello${idx}.o"
        check-file-ownership-as-workdir "${SRC_DIR}/hello${idx}.ko"
        check-file-ownership-as-workdir "${SRC_DIR}/Makefile"

        # Check file with ownership not as "root:root"
        run ls -dln "${SRC_DIR}/README.md"
        assert_output --regexp '[ \t]+1[ \t]+10[ \t]+20[ \t]+0'
    done

    # Ensure --autoload flag was honored:
    echo "Check etc/modules-load.d/tcb.conf contents."
    run torizoncore-builder-shell \
        "echo \$(cat /storage/kernel/usr/etc/modules-load.d/tcb.conf)"
    assert_success
    assert_output 'hello1 hello3'

    # Determine the kernel/modules directory (relative to the deployment):
    # shellcheck disable=SC2016
    run torizoncore-builder-shell \
        'dpldir=$(cd /storage/sysroot/ostree/deploy/torizon/deploy/*/usr/.. && pwd) && ' \
        'moddir=$(cd ${dpldir}/usr/lib/modules/* && pwd) && ' \
        'moddirrel=$(realpath --relative-to="${dpldir}" "${moddir}") && ' \
        'echo ${moddirrel}'
    assert_success
    local moddirrel="${output}"

    # Ensure that the modules have been installed:
    echo "Check installation of kernel modules."
    run torizoncore-builder-shell \
        "echo \$(cd /storage/kernel/${moddirrel}/updates && ls -1 hello*.ko)"
    assert_success
    assert_output 'hello0.ko hello1.ko hello2.ko hello3.ko'

    # Check if the same module can be built/installed more than once; here we re-build a
    # module which was previously built with --autoload and check to see if that switch
    # was handled correctly (the last auto-loaded module should be listed at the end of
    # etc/modules-load.d/tcb.conf):
    local SRC_DIR="source_dir1"
    echo "Re-building kernel module in '${SRC_DIR}' with args '${BLD_MOD_ARGS[1]}'."
    # shellcheck disable=SC2086
    run torizoncore-builder kernel build_module ${BLD_MOD_ARGS[1]} "${SRC_DIR}"
    assert_success
    echo "Check etc/modules-load.d/tcb.conf contents again."
    run torizoncore-builder-shell \
        "echo \$(cat /storage/kernel/usr/etc/modules-load.d/tcb.conf)"
    assert_success
    assert_output 'hello3 hello1'

    # Ensure that files "vmlinuz" (kernel binary) and "overlays.txt" do not get touched
    # by the command; if they were, then other commands (e.g. "dt", "dto", "splash")
    # would likely be broken by "kernel build_module".
    run torizoncore-builder-shell \
        "echo 'DUMMY_KERNEL' > /storage/kernel/${moddirrel}/vmlinuz && " \
        "mkdir -p /storage/kernel/${moddirrel}/dtb && " \
        "echo 'DUMMY_OVERLAYS' > /storage/kernel/${moddirrel}/dtb/overlays.txt"
    assert_success
    local SRC_DIR="source_dir0"
    echo "Re-building kernel module in '${SRC_DIR}' with args '${BLD_MOD_ARGS[0]}'."
    # shellcheck disable=SC2086
    run torizoncore-builder kernel build_module ${BLD_MOD_ARGS[0]} "${SRC_DIR}"
    assert_success
    run torizoncore-builder-shell \
        "[ \"\$(cat /storage/kernel/${moddirrel}/vmlinuz)\" = 'DUMMY_KERNEL' ] && " \
        "[ \"\$(cat /storage/kernel/${moddirrel}/dtb/overlays.txt)\" = 'DUMMY_OVERLAYS' ]"
    assert_success
}

@test "kernel {set,get,clear}_custom_args: check basic errors" {
    torizoncore-builder-clean-storage

    run torizoncore-builder kernel set_custom_args "arg1=val1" "arg2=val2"
    assert_failure
    assert_output --partial "Error: could not find an Easy Installer or WIC image in the storage"
    assert_output --partial "Please use the 'images' command to unpack an image before running this command"

    run torizoncore-builder kernel get_custom_args
    assert_failure
    assert_output --partial "Error: could not find an Easy Installer or WIC image in the storage"
    assert_output --partial "Please use the 'images' command to unpack an image before running this command"

    run torizoncore-builder kernel clear_custom_args
    assert_failure
    assert_output --partial "Error: could not find an Easy Installer or WIC image in the storage"
    assert_output --partial "Please use the 'images' command to unpack an image before running this command"

    torizoncore-builder images --remove-storage unpack "${DEFAULT_TEZI_IMAGE}"

    run torizoncore-builder kernel set_custom_args ""
    assert_failure
    assert_output --partial "Error: please pass a valid string for the custom kernel arguments"
}

@test "kernel {set,get,clear}_custom_args: check unsupported bootargs passing" {
    torizoncore-builder images --remove-storage unpack "${DEFAULT_TEZI_IMAGE}"

    local uenv_path
    local ovl_kargs_supported
    local uenv_kargs_supported

    # Find uEnv.txt in storage:
    uenv_path=$(find_uenv_txt_in_sysroot)
    # Determine the supported bootargs passing methods:
    ovl_kargs_supported=$(is_ovl_kargs_passing_supported "${uenv_path}" \
                          && echo "1" || echo "0")
    uenv_kargs_supported=$(is_uenv_kargs_passing_supported "${uenv_path}" \
                           && echo "1" || echo "0")
    # Show result (for debug):
    echo "ovl_kargs_supported=${ovl_kargs_supported}"
    echo "uenv_kargs_supported=${uenv_kargs_supported}"

    # Change uEnv.txt to pretend that the new bootargs passing method is not supported.
    if [ "${uenv_kargs_supported}" = "1" ]; then
        echo "Removing uenv-based bootargs setting method from uEnv.txt"
        run torizoncore-builder-shell "sed -i -e '/^set_bootargs_custom2=/d' ${uenv_path}"
        assert_success
    fi

    if [ "${IS_DEFAULT_TEZI_IMAGE_FIT}" = "1" ]; then
        # In case of FIT images, the new passing method is strictly needed for
        # setting/clearing (not for getting); check that:
        echo "Performing basic set/get/clear checks for FIT-kernel case"
        run torizoncore-builder kernel set_custom_args "arg1=val1" "arg2=val2"
        assert_failure
        assert_output --partial "Error: the Torizon OS image you are customizing has a kernel in FIT format but it does not support the uEnv method"

        run torizoncore-builder kernel get_custom_args
        assert_success
        assert_output --partial "Notice: this image has a kernel in FIT format but it does not support the uEnv method for passing kernel arguments"

        run torizoncore-builder kernel clear_custom_args
        assert_failure
        assert_output --partial "Error: the Torizon OS image you are customizing has a kernel in FIT format but it does not support the uEnv method"
    fi

    # Change uEnv.txt to pretend that the old bootargs passing method is also
    # not supported; now not setting methods are available.
    if [ "${ovl_kargs_supported}" = "1" ]; then
        echo "Removing overlay-based bootargs setting method from uEnv.txt"
        run torizoncore-builder-shell "sed -i -e '/^set_bootargs_custom=/d' ${uenv_path}"
        assert_success
    fi

    # At this point, no bootargs setting method is available; check that:
    echo "Run kernel set_custom_args with no bootargs setting method available"
    run torizoncore-builder kernel set_custom_args "arg1=val1" "arg2=val2"
    assert_failure
    if [ "${IS_DEFAULT_TEZI_IMAGE_FIT}" = "1" ]; then
        assert_output --partial "Error: the Torizon OS image you are customizing has a kernel in FIT format but it does not support the uEnv method"
    else
        assert_output --partial "Error: the Torizon OS image you are customizing does not support custom kernel arguments"
    fi

    echo "Run kernel get_custom_args with no bootargs setting method available"
    run torizoncore-builder kernel get_custom_args
    assert_failure
    if [ "${IS_DEFAULT_TEZI_IMAGE_FIT}" = "1" ]; then
        assert_output --partial "Notice: this image has a kernel in FIT format but it does not support the uEnv method for passing kernel arguments"
    fi
    assert_output --partial "Error: the Torizon OS image you are customizing does not support custom kernel arguments"

    echo "Run kernel clear_custom_args with no bootargs setting method available"
    run torizoncore-builder kernel clear_custom_args
    assert_failure
    if [ "${IS_DEFAULT_TEZI_IMAGE_FIT}" = "1" ]; then
        assert_output --partial "Error: the Torizon OS image you are customizing has a kernel in FIT format but it does not support the uEnv method"
    else
        assert_output --partial "Error: the Torizon OS image you are customizing does not support custom kernel arguments"
    fi
}

@test "kernel {set,get,clear}_custom_args: check success cases" {
    torizoncore-builder images --remove-storage unpack "${DEFAULT_TEZI_IMAGE}"

    local uenv_path
    local ovl_kargs_supported
    local uenv_kargs_supported

    # Find uEnv.txt in storage:
    uenv_path=$(find_uenv_txt_in_sysroot)
    # Determine the supported bootargs passing methods:
    ovl_kargs_supported=$(is_ovl_kargs_passing_supported "${uenv_path}" \
                          && echo "1" || echo "0")
    uenv_kargs_supported=$(is_uenv_kargs_passing_supported "${uenv_path}" \
                           && echo "1" || echo "0")
    # Show result (for debug):
    echo "ovl_kargs_supported=${ovl_kargs_supported}"
    echo "uenv_kargs_supported=${uenv_kargs_supported}"

    # ---
    # Test the "set" command:
    # ---
    echo "Try setting custom bootargs."
    run torizoncore-builder --log-level debug kernel set_custom_args "arg1=val1" "arg2=val2"

    if [ "${uenv_kargs_supported}" = "1" ]; then
        echo "Checking output of setting custom kernel arguments via uenv method."
        assert_success
        assert_output --partial 'Kernel custom arguments successfully configured with "arg1=val1 arg2=val2"'
        assert_output --partial "Setting bootargs (uenv method)"
        assert_output --partial "Clearing bootargs (overlay method)"

        # Check uEnv.txt to see if the arguments were actually set.
        local uenv_path_chgsdir check_append
        uenv_path_chgsdir=$(find_uenv_txt_in_chgsdir)
        check_append="1"

        if [ "${IS_DEFAULT_TEZI_IMAGE_FIT}" = "1" ]; then
            echo "Run extra checks for FIT case."
            if echo "${output}" | \
               grep -q "Overlay with secboot required-bootargs found in the kernel"; then
                # Check if the overlay keeping the required-bootargs was updated.
                assert_output --regexp "req_bootargs_cur='.*'"
                refute_output --partial "req_bootargs_cur='None'"
                assert_output --partial "req_bootargs_org='None'"
                assert_output --regexp "req_bootargs_new='arg1=val1 arg2=val2 .*'"
                assert_output --partial "Storing updated required-bootargs into the overlay"
                assert_output --partial "Storing updated overlay into the kernel FIT"
                assert_output --partial "Passed string will be prepended to the original bootargs"
                assert_output --regexp "Warning: .*the custom kernel arguments will be prepended"
                check_append="0"
            else
                assert_output --partial "Passed string will be appended to the original bootargs"
            fi
        fi

        if [ "${check_append}" = "1" ]; then
            echo "Ensure new bootargs were appended to the existing ones."
            if ! torizoncore-builder-shell \
                 "grep -e '^torizon_bootargs_r=arg1=val1 arg2=val2' ${uenv_path_chgsdir}"; then
                fail "New bootargs aren't present in 'torizon_bootargs_r'."
            fi
            if torizoncore-builder-shell \
                   "grep -e '^torizon_bootargs_l=' ${uenv_path_chgsdir}"; then
                fail "Variable 'torizon_bootargs_l' shouldn't be present in uEnv.txt."
            fi
        else
            echo "Ensure new bootargs were prepended to the existing ones."
            if ! torizoncore-builder-shell \
                 "grep -e '^torizon_bootargs_l=arg1=val1 arg2=val2' ${uenv_path_chgsdir}"; then
                fail "New bootargs aren't present in 'torizon_bootargs_l'."
            fi
            if torizoncore-builder-shell \
                   "grep -e '^torizon_bootargs_r=' ${uenv_path_chgsdir}"; then
                fail "Variable 'torizon_bootargs_r' shouldn't be present in uEnv.txt."
            fi
        fi

    elif [ "${ovl_kargs_supported}" = "1" ]; then
        if [ "${IS_DEFAULT_TEZI_IMAGE_FIT}" = "1" ]; then
            # Testing with deprecated secboot image (rare).
            assert_failure
            assert_output --regexp 'Error: the Torizon OS image you are customizing has a kernel in FIT format but it does not support the uEnv method for passing kernel arguments'
            return
        else
            echo "Checking output of setting custom kernel arguments via overlay method."
            assert_success
            assert_output --partial 'Kernel custom arguments successfully configured with "arg1=val1 arg2=val2"'
            assert_output --partial "Setting bootargs (overlay method)"
            assert_output --partial "Overlay custom-kargs_overlay.dtbo successfully applied"
        fi
    else
        # Images without support for custom bootargs should no longer be available;
        # but handle them anyway.
        assert_failure
        assert_output --partial "Error: the Torizon OS image you are customizing does not support custom kernel arguments"
        return
    fi

    # ---
    # Test the "get" command:
    # ---
    echo "Try getting custom bootargs."
    run torizoncore-builder --log-level debug kernel get_custom_args
    echo "Checking output of getting custom kernel arguments."
    assert_success
    assert_output --partial 'Currently configured custom kernel arguments: "arg1=val1 arg2=val2"'

    if [ "${uenv_kargs_supported}" = "1" ] && \
       [ "${IS_DEFAULT_TEZI_IMAGE_FIT}" = "1" ]; then
        if echo "${output}" | \
           grep -q "Overlay with secboot required-bootargs found in the kernel"; then
            # Check if the overlay keeping the required-bootargs was updated.
            assert_output --regexp "req_bootargs_cur='arg1=val1 arg2=val2 .*'"
            assert_output --regexp "req_bootargs_org='.*'"
            refute_output --regexp "req_bootargs_org='None'"
        fi
    fi

    # ---
    # Test the "clear" command:
    # ---
    echo "Try clearing custom bootargs."
    run torizoncore-builder --log-level debug kernel clear_custom_args

    if [ "${uenv_kargs_supported}" = "1" ]; then
        echo "Checking output of clearing custom kernel arguments via uenv method."
        assert_success
        assert_output --partial 'Custom kernel arguments successfully cleared'
        assert_output --partial "Clearing bootargs (uenv method)"

        if [ "${IS_DEFAULT_TEZI_IMAGE_FIT}" = "1" ]; then
            if echo "${output}" | \
                    grep -q "Overlay with secboot required-bootargs found in the kernel"; then
                # Check if the required-bootargs was cleared (based on logs).
                assert_output --regexp "req_bootargs_cur='.*'"
                assert_output --regexp "req_bootargs_org='.*'"
                refute_output --regexp "req_bootargs_cur='None'"
                refute_output --regexp "req_bootargs_org='None'"
                assert_output --partial "Clearing original required-bootargs in the overlay"
                assert_output --partial "Storing updated required-bootargs into the overlay"
                assert_output --partial "Storing updated overlay into the kernel FIT"
            fi
        fi

        # Check uEnv.txt to see if the arguments variables are gone.
        local uenv_path_chgsdir
        uenv_path_chgsdir=$(find_uenv_txt_in_chgsdir)
        echo "Ensure bootargs variables are not present in '${uenv_path_chgsdir}'."
        if torizoncore-builder-shell "grep -e '^torizon_bootargs_l=' ${uenv_path_chgsdir}"; then
            fail "Variable 'torizon_bootargs_l' is present in uEnv.txt after clearing."
        fi
        if torizoncore-builder-shell "grep -e '^torizon_bootargs_r=' ${uenv_path_chgsdir}"; then
            fail "Variable 'torizon_bootargs_r' is present in uEnv.txt after clearing."
        fi

    elif [ "${ovl_kargs_supported}" = "1" ]; then
        echo "Checking output of clearing custom kernel arguments via overlay method."
        assert_success
        assert_output --partial 'Custom kernel arguments successfully cleared'
        assert_output --partial "Clearing bootargs (overlay method)"
    else
        # Images without support for custom bootargs should no longer be available;
        # but handle them anyway.
        assert_failure
        assert_output --partial "Error: the Torizon OS image you are customizing does not support custom kernel arguments"
        return
    fi

    # ---
    # Check the "get" command after clearing:
    # ---
    echo "Try getting custom bootargs after clearing."
    run torizoncore-builder --log-level debug kernel get_custom_args
    echo "Checking output of getting custom kernel arguments after clearing."
    assert_success
    assert_output --partial 'No custom kernel arguments configured'

    # ---
    # Test the "clear" command again after clearing:
    # ---
    echo "Try clearing custom bootargs after clearing."
    run torizoncore-builder --log-level debug kernel clear_custom_args
    echo "Checking output of clearing custom kernel arguments after clearing."
    assert_success
    assert_output --partial 'No custom kernel arguments configured'

    if [ "${uenv_kargs_supported}" = "1" ]; then
        echo "Checking output of clearing custom kernel arguments again."
        assert_success
        assert_output --partial "Clearing bootargs (uenv method)"

        if [ "${IS_DEFAULT_TEZI_IMAGE_FIT}" = "1" ]; then
            if echo "${output}" | \
               grep -q "Overlay with secboot required-bootargs found in the kernel"; then
                # Check if the required-bootargs was cleared (based on logs).
                assert_output --regexp "req_bootargs_cur='.*'"
                refute_output --regexp "req_bootargs_cur='None'"
                assert_output --regexp "req_bootargs_org='None'"
                assert_output --regexp "req_bootargs_new='None'"
                assert_output --partial "Overlay with required-bootargs needs no update"
            fi
        fi
    fi
}
