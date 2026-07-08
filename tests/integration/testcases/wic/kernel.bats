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
    torizoncore-builder images --remove-storage unpack "${DEFAULT_WIC_IMAGE}"

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
