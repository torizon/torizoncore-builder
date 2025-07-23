#!/bin/bash

[ "${XTRACE}" = "1" ] && set -x

set -e

# Variables that can be overriden:
UBOOT_SPL_DDR_BINARY="${UBOOT_SPL_DDR_BINARY:-u-boot-spl-ddr.bin}"
UBOOT_DTB_BINARY="${UBOOT_DTB_BINARY:-u-boot.dtb.out}"
UBOOT_CONTAINER_BINARY="${UBOOT_CONTAINER_BINARY:-flash.bin}"
CSF_PREFIX="${CSF_PREFIX:-csf-for-}"
LIBFAKETIME_PATH="${LIBFAKETIME_PATH}"

UBOOT_CONFIG_FILE="${UBOOT_CONFIG_FILE:-.config}"

# Timestamp to be used by libfaketime. The date itself isn't important, but this needs
# to be constant between builds in order to generate deterministic CSF binaries
# Default value is: November 6, 2024 (12:00 PM UTC)
FAKETIME=${FAKETIME:-1730894400}

# shellcheck disable=SC2155
readonly FILE_SCRIPT="$(basename "$0")"
# shellcheck disable=SC2155
readonly DIR_SCRIPT="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
readonly CSF_SPL="${CSF_PREFIX}spl"
readonly CSF_FIT="${CSF_PREFIX}fit"

error() {
    echo "***" >&2
    echo " ERROR: ${1}" >&2
    echo "***" >&2
    exit 1
}

help() {
    echo
    echo " Usage: ${DIR_SCRIPT}/${FILE_SCRIPT} <options>"
    echo
    echo " Required environment variables:"
    echo
    echo "    TDX_IMX_HAB_CST_BIN       Path to NXP CST Binary"
    echo "                              e.g. cst-3.1.0/release/linux64/bin/cst"
    echo "    TDX_IMX_HAB_CST_SRK       Path to SRK Table"
    echo "                              e.g. SRK_1_2_3_4_table.bin"
    echo "    TDX_IMX_HAB_CST_SRK_CERT  Path to SRK public key certificate"
    echo "                              e.g. SRK1_sha256_2048_65537_v3_ca_crt.pem (when CA flag is set)"
    echo "                              e.g. SRK1_sha256_2048_65537_v3_usr_crt.pem (when CA flag is not set)"
    echo "    TDX_IMX_HAB_CST_CSF_CERT  Path to CSF public key certificate (needed only if CA flag is set for SRK)"
    echo "                              e.g. CSF1_1_sha256_2048_65537_v3_usr_crt.pem"
    echo "    TDX_IMX_HAB_CST_IMG_CERT  Path to IMG public key certificate (needed only if CA flag is set for SRK)"
    echo "                              e.g. IMG1_1_sha256_2048_65537_v3_usr_crt.pem"
    echo
    echo " Optional environment variables:"
    echo
    echo "    UBOOT_SPL_DDR_BINARY      Name of binary containing SPL plus DDR FW"
    echo "                              default: u-boot-spl-ddr.bin"
    echo "    UBOOT_DTB_BINARY          Name of binary containing U-Boot DTB plus data filled in by BINMAN"
    echo "                              default: u-boot.dtb.out"
    echo "    UBOOT_CONTAINER_BINARY    Name of bootloader container binary"
    echo "                              default: flash.bin"
    echo "    CSF_PREFIX                Prefix for CSF files to be produced"
    echo "                              default: csf-for-"
    echo "    LIBFAKETIME_PATH          Path to libfaketime library (needed for reproducible CSF binary builds)"
    echo "                              default: unset"
    echo
    echo " Optional switches:"
    echo "    -h --help            display this Help message"
    echo
    exit 1
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                help
                ;;
            *)    # unknown option
                echo "Unknown option: $1"
                help
                ;;
        esac
    done
}

# Verify that environment variable is set and file exists.
check_fileref() {
    local file="${1?file name expected}"
    local varname="${2?variable name expected}"
    if [ -z "${file}" ]; then
        error "Please set environment variable '${varname}'"
    fi
    if [ ! -f "${file}" ]; then
        error "Could not find '${file}' referenced by variable ${varname} (CWD=$(pwd))"
    fi
    echo "Verified ${varname}=${file}"
}

# Verify all relevant environment variables.
validate_environ() {
    check_fileref "${TDX_IMX_HAB_CST_BIN}" "TDX_IMX_HAB_CST_BIN"
    check_fileref "${TDX_IMX_HAB_CST_SRK}" "TDX_IMX_HAB_CST_SRK"
    check_fileref "${TDX_IMX_HAB_CST_SRK_CERT}" "TDX_IMX_HAB_CST_SRK_CERT"
    if [ "${TDX_IMX_HAB_CST_SRK_CERT##*_ca_}" = "crt.pem" ]; then
        check_fileref "${TDX_IMX_HAB_CST_CSF_CERT}" "TDX_IMX_HAB_CST_CSF_CERT"
        check_fileref "${TDX_IMX_HAB_CST_IMG_CERT}" "TDX_IMX_HAB_CST_IMG_CERT"
    fi

    check_fileref "${UBOOT_SPL_DDR_BINARY}" "UBOOT_SPL_DDR_BINARY"
    check_fileref "${UBOOT_DTB_BINARY}" "UBOOT_DTB_BINARY"
    check_fileref "${UBOOT_CONTAINER_BINARY}" "UBOOT_CONTAINER_BINARY"
}

# Generate a CSF text file (to be used as input to the CST tool) based on a
# template.
#
# $1: CSF file path/name w/o extension
# $2: SPL flag (1 or 0)
#
generate_csf_common() {
    local image_csf="${1?CSF file name expected}.csf"
    local spl="${2?SPL flag expected}"

    # Copy template file:
    echo "Creating CSF file: ${image_csf}"
    cp "${DIR_SCRIPT}/imx8m_template.csf" "${image_csf}"

    # Determine key index (use file name):
    local kidx
    kidx=${TDX_IMX_HAB_CST_SRK_CERT##*/}
    kidx=${kidx##SRK}
    kidx=${kidx%%_*}
    if [ "${#kidx}" != 1 ]; then
        echo "Certificate file name (defined by TDX_IMX_HAB_CST_SRK_CERT) does" \
             "not match expected pattern - could not determine SRK key index."
        exit 1
    fi

    if [ "${kidx}" -ge 1 ] && [ "${kidx}" -le 4 ]; then
        echo "Using SRK${kidx} for signing."
    else
        echo "Bad SRK key index '${kidx}' (inferred from TDX_IMX_HAB_CST_SRK_CERT) - aborting."
        exit 1
    fi
    kidx=$((kidx - 1))

    # Determine whether or not the CA flag was set:
    local ca
    if [ "${TDX_IMX_HAB_CST_SRK_CERT##*_ca_}" = "crt.pem" ]; then
        ca=1
    elif [ "${TDX_IMX_HAB_CST_SRK_CERT##*_usr_}" = "crt.pem" ]; then
        ca=0
    else
        echo "Certificate file name (defined by TDX_IMX_HAB_CST_SRK_CERT)" \
             "does not match expected pattern - could not determine if CA flag is set."
        exit 1
    fi

    # Update "Install SRK" section:
    sed -i "s|@@CST_SRK@@|${TDX_IMX_HAB_CST_SRK}|g" "${image_csf}"
    sed -i "s|@@CST_KIDX@@|${kidx}|g" "${image_csf}"

    if [ "$ca" = 1 ]; then
        # Keep "Install CSFK" section and update its contents:
        sed -i "/#+START_INSTALL_CSFK_BLOCK/d; /#+END_INSTALL_CSFK_BLOCK/d" "${image_csf}"
        sed -i "s|@@CST_CSF_CERT@@|${TDX_IMX_HAB_CST_CSF_CERT}|g" "${image_csf}"
        # Delete "Install NOCAK" section:
        sed -i "/#+START_INSTALL_NOCAK_BLOCK/,/#+END_INSTALL_NOCAK_BLOCK/d" "${image_csf}"
    else
        # Delete "Install CSFK" section:
        sed -i "/#+START_INSTALL_CSFK_BLOCK/,/#+END_INSTALL_CSFK_BLOCK/d" "${image_csf}"
        # Keep "Install NOCAK" section and update its contents:
        sed -i "/#+START_INSTALL_NOCAK_BLOCK/d; /#+END_INSTALL_NOCAK_BLOCK/d" "${image_csf}"
        sed -i "s|@@CST_SRK_CERT@@|${TDX_IMX_HAB_CST_SRK_CERT}|g" "${image_csf}"
    fi

    if [ "$spl" =  1 ]; then
        # Keep "Unlock" section:
        sed -i "/#+START_UNLOCK_BLOCK/d; /#+END_UNLOCK_BLOCK/d" "${image_csf}"
    else
        # Delete "Unlock" section:
        sed -i "/#+START_UNLOCK_BLOCK/,/#+END_UNLOCK_BLOCK/d" "${image_csf}"
    fi

    if [ "$ca" = 1 ]; then
        # Keep "Install Key" section and update its contents:
        sed -i "/#+START_INSTALL_KEY_BLOCK/d; /#+END_INSTALL_KEY_BLOCK/d" "${image_csf}"
        sed -i "s|@@CST_IMG_CERT@@|${TDX_IMX_HAB_CST_IMG_CERT}|g" "${image_csf}"
        # Update part of "Authenticate Data" section:
        # Verification index is 2 (IMGK slot).
        sed -i "s|@@CST_AUTH_KIDX@@|2|g" "${image_csf}"
    else
        # Delete "Install Key" section
        sed -i "/#+START_INSTALL_KEY_BLOCK/,/#+END_INSTALL_KEY_BLOCK/d" "${image_csf}"
        # Update part of "Authenticate Data" section:
        # Verification index is 0 (SRK slot).
        sed -i "s|@@CST_AUTH_KIDX@@|0|g" "${image_csf}"
    fi
}

# Generate the CSF blob for the SPL (SPL+DDR FW) part of the container and
# update the container in-place with that CSF blob (this effectively signs that
# part of the image).
#
# See doc/imx/habv4/guides/mx8m_spl_secure_boot.txt for details on the whole
# process.
#
generate_spl_csf_and_update_container() {
    generate_csf_common "${CSF_SPL}" "1"

    # Update "Blocks" data in "Authenticate Data" section:
    spl_block_base=$(printf "0x%x" $(( $(sed -n "/CONFIG_SPL_TEXT_BASE=/ s@.*=@@p" "${UBOOT_CONFIG_FILE}") - 0x40)) )
    # shellcheck disable=SC2046
    spl_block_size=$(printf "0x%x" $(stat -tc "%s" "${UBOOT_SPL_DDR_BINARY}"))
    if [ "${spl_block_base}" = "0x0" ] || [ "${spl_block_size}" = "0x0" ]; then
        error "Could not determine SPL block base (${spl_block_base}) or size (${spl_block_size})"
        exit 1
    fi
    sed -i "/Blocks = / s@.*@    Blocks = ${spl_block_base} 0x0 ${spl_block_size} \"${UBOOT_CONTAINER_BINARY}\"@" "${CSF_SPL}.csf"

    # Generate CSF blob:
    if ! env ${LIBFAKETIME_PATH+LD_PRELOAD="${LIBFAKETIME_PATH}"
                                FAKETIME_FMT="%s"
                                FAKETIME="@${FAKETIME}"} \
             "${TDX_IMX_HAB_CST_BIN}" -i "${CSF_SPL}.csf" -o "${CSF_SPL}.bin" > "${CSF_SPL}.log" 2>&1
    then
        echo "CST execution log:" >&2
        cat "${CSF_SPL}.log" | sed 's@^@|@' >&2
        error "CST failed to execute; please check logs."
    fi
    cat "${CSF_SPL}.log"

    # Patch CSF blob into flash.bin:
    spl_csf_offset=$(xxd -s 24 -l 4 -e "${UBOOT_CONTAINER_BINARY}" | cut -d " " -f 2 | sed "s@^@0x@")
    spl_bin_offset=$(xxd -s 4 -l 4 -e "${UBOOT_CONTAINER_BINARY}" | cut -d " " -f 2 | sed "s@^@0x@")
    spl_dd_offset=$((spl_csf_offset - spl_bin_offset + 0x40))
    dd if="${CSF_SPL}.bin" of="${UBOOT_CONTAINER_BINARY}" bs=1 seek=${spl_dd_offset} conv=notrunc
}

# Generate the CSF blob for the FIT (U-Boot proper, ATF, etc.) part of the
# container and update the container in-place with that CSF blob (this
# effectively signs that part of the image).
#
# See doc/imx/habv4/guides/mx8m_spl_secure_boot.txt for details on the whole
# process.
#
generate_fit_csf_and_update_container() {
    generate_csf_common "${CSF_FIT}" "0"

    # NOTE: Below, if we were to follow the NXP docs we would do:
    #
    # fit_block_offset=$(printf "0x%s" $(fdtget -t x "${UBOOT_DTB_BINARY}" /binman/imx-boot/uboot offset))
    # fit_block_size=$(printf "0x%x" $(( ( ( $(stat -tc %s "u-boot.itb") + 0x1000 - 0x1 ) & ~(0x1000 - 0x1)) + 0x20 )) )
    #
    # However, the node "/binman/imx-boot/uboot" is not available in Toradex
    # dtbs. Also, the logic explicitly requires the existence of a u-boot.itb
    # file which is not normally generated.

    # Update "Blocks" data in "Authenticate Data" section:
    # shellcheck disable=SC2046
    fit_block_base=$(printf "0x%x" $(sed -n "/CONFIG_SPL_LOAD_FIT_ADDRESS=/ s@.*=@@p" "${UBOOT_CONFIG_FILE}"))
    if [ "${fit_block_base}" = "0x0" ]; then
        error "Configuration 'CONFIG_SPL_LOAD_FIT_ADDRESS' must be properly set for use with HAB; please review your defconfig"
        exit 1
    fi

    # shellcheck disable=SC2046
    fit_block_offset=$(printf "0x%s" $(fdtget -t x "${UBOOT_DTB_BINARY}" /binman/section/fit offset))
    fit_block_size=$(printf "0x%x" $(( ( ( $(fdtget -t u "${UBOOT_DTB_BINARY}" /binman/section/fit size) + 0x1000 - 0x1 ) & ~(0x1000 - 0x1)) + 0x20 )) )
    if [ "${fit_block_offset}" = "0x0" ] || [ "${fit_block_size}" = "0x0" ]; then
        error "U-Boot DTB file '${UBOOT_DTB_BINARY}' does not have the required binman sections"
        exit 1
    fi
    sed -i "/Blocks = / s@.*@    Blocks = ${fit_block_base} ${fit_block_offset} ${fit_block_size} \"${UBOOT_CONTAINER_BINARY}\"@" "${CSF_FIT}.csf"

    # Generate an IVT (Image Vector Table) for the image:
    ivt_block_base=$(printf "%08x" $(( fit_block_base + fit_block_size - 0x20 )) | sed "s@\(..\)\(..\)\(..\)\(..\)@0x\4\3\2\1@")
    csf_block_base=$(printf "%08x" $(( fit_block_base + fit_block_size )) | sed "s@\(..\)\(..\)\(..\)\(..\)@0x\4\3\2\1@")
    ivt_block_offset=$((fit_block_offset + fit_block_size - 0x20))
    csf_block_offset=$((ivt_block_offset + 0x20))

    # IVT fields - each one is a 32-bit word:
    # - header    : 0xd1002041 (type=0xd1, length=0x0020, version=0x40 or 0x41)
    # - entry     : abs address of first instruction to execute
    # - reserved1 : 0x00000000
    # - dcd       : abs address of image DCD
    # - boot_data : abs address of boot data
    # - self      : abs address of IVT
    # - csf       : abs address of Command Sequence File
    # - reserved2 : 0x00000000
    echo "0xd1002041 ${ivt_block_base} 0x00000000 0x00000000 0x00000000 ${ivt_block_base} ${csf_block_base} 0x00000000" | xxd -r -p > ivt.bin
    dd if=ivt.bin of="${UBOOT_CONTAINER_BINARY}" bs=1 seek=${ivt_block_offset} conv=notrunc

    # Generate CSF blob:
    if ! env ${LIBFAKETIME_PATH+LD_PRELOAD="${LIBFAKETIME_PATH}"
                                FAKETIME_FMT="%s"
                                FAKETIME="@${FAKETIME}"} \
             "${TDX_IMX_HAB_CST_BIN}" -i "${CSF_FIT}.csf" -o "${CSF_FIT}.bin" > "${CSF_FIT}.log" 2>&1
    then
        echo "CST execution log:" >&2
        cat "${CSF_FIT}.log" | sed 's@^@|@' >&2
        error "CST failed to execute; please check logs."
    fi
    cat "${CSF_FIT}.log"

    # Comment from doc/imx/habv4/csf_examples/mx8m/csf.sh:
    #
    # When loading flash.bin via USB, we must ensure that the file being served
    # is as large as the target expects (see board_spl_fit_size_align()),
    # otherwise the target will hang in rom_api_download_image() waiting for the
    # remaining bytes.
    #
    # Note that in order for dd to actually extend the file, one must not pass
    # conv=notrunc here. With a non-zero seek= argument, dd is documented to
    # preserve the contents of the file seeked past; in particular, dd does not
    # open the file with O_TRUNC.
    #
    csf_size=$(sed -n "/CONFIG_CSF_SIZE=/ s@.*=@@p" "${UBOOT_CONFIG_FILE}")
    dd if=/dev/null of="${CSF_FIT}.bin" bs=1 seek=$((csf_size - 0x20)) count=0

    # Patch CSF blob into flash.bin:
    dd if="${CSF_FIT}.bin" of="${UBOOT_CONTAINER_BINARY}" bs=1 seek=${csf_block_offset} conv=notrunc
}

parse_args "$@"

# Print command for Yocto logs
echo "$0" "$@"

validate_environ

generate_spl_csf_and_update_container
generate_fit_csf_and_update_container
