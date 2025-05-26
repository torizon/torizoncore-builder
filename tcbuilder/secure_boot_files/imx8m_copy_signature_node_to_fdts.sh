#!/bin/bash
#
# Usage: imx8m_copy_signature_node_to_fdts.sh <dtb-with-signature-node>
#
# Normally <dtb-with-signature-node> would be set to u-boot.dtb or u-boot.dtb-signed.
#

set -e

[ "${XTRACE}" = "1" ] && set -x

declare -A KNOWN_PROP_TYPES=(
    ["algo"]="s"
    ["key-name-hint"]="s"
    ["required"]="s"
    ["rsa,r-squared"]="lx"
    ["rsa,modulus"]="lx"
    ["rsa,exponent"]="lx"
    ["rsa,n0-inverse"]="lx"
    ["rsa,num-bits"]="lx"
    ["ecdsa,curve"]="s"
    ["ecdsa,x-point"]="lx"
    ["ecdsa,y-point"]="lx"
)

# Set DRY_RUN to 1 to prevent modifying the target DTBs.
DRY_RUN=${DRY_RUN:-0}

# Prefix to all files accessed (defaults to CWD).
D=${PREFIX:-.}

# Text filename with U-Boot CONFIG build options (defaults to .config)
UBOOT_CONFIG_FILE="${UBOOT_CONFIG_FILE:-.config}"

# Copy signature node from source to destination DTB.
#
# The source DTB should have a signature node that would look like this:
#
# / {
#     compatible = "toradex,verdin-imx8mm-wifi-dev", "toradex,verdin-imx8mm-wifi", "toradex,verdin-imx8mm", "fsl,imx8mm";
#     ...
#     signature {
#         key-dev {
#             required = "conf";
#             algo = "sha256,rsa2048";
#             rsa,r-squared = <0x06d11c22 0x56f31661 0x133143bb 0xfdbcde51 0xd653d2a5 ...>;
#             rsa,modulus = <0xdb06864a 0x12a1e033 0x04b0b457 0x46e5d967 0xc6a6f78d ...>;
#             rsa,exponent = <0x00000000 0x00010001>;
#             rsa,n0-inverse = <0x8925c5c7>;
#             rsa,num-bits = <0x00000800>;
#             key-name-hint = "dev";
#         };
#     };
#     ...
# };
#
# Parameters:
#
# $1: source DTB
# $2: target DTB
#
copy_signature_node() {
    local src_dtb="${1?path to source DTB expected}"
    local tgt_dtb="${2?path to target DTB expected}"

    if [ "$(fdtget "${D}/${src_dtb}" "/signature" -p)" ]; then
        echo "Unexpected properties inside /signature node" >&2
        exit 1
    fi

    keynodes=$(fdtget "${D}/${src_dtb}" "/signature" -l)
    for keynode in ${keynodes}; do
        if [ "$(fdtget "${D}/${src_dtb}" "/signature/${keynode}" -l)" ]; then
            echo "Unexpected sub-nodes inside /signature/${keynode} node" >&2
            exit 1
        fi

        propnodes=$(fdtget "${D}/${src_dtb}" "/signature/${keynode}" -p)
        for propnode in ${propnodes}; do
            k="/signature/${keynode}"
            t=${KNOWN_PROP_TYPES[${propnode}]}
            if [ -z "${t}" ]; then
                echo "Unexpected property '${propnode}' inside /signature/${keynode} node" >&2
                exit 1
            fi
            v=$(fdtget -t"${t}" "${D}/${src_dtb}" "${k}" "${propnode}")
            if [ "${DRY_RUN}" = "0" ]; then
                # shellcheck disable=SC2086
                fdtput -p -t"${t}" "${D}/${tgt_dtb}" "${k}" "${propnode}" ${v}
            else
                echo "Would execute fdtput -p -t${t} ${D}/${tgt_dtb} ${k} ${propnode} ${v}"
            fi
        done
    done
}

proc_of_list() {
    local src_dtb="${1?path to source DTB expected}"
    local tgt_dtb

    dtb_list=$(sed -ne 's#^CONFIG_OF_LIST="\(.*\)"#\1#p' "${D}/${UBOOT_CONFIG_FILE}")
    if [ -z "${dtb_list}" ]; then
        echo "CONFIG_OF_LIST is not properly set" >&2
        exit 1
    fi

    for dtb in ${dtb_list}; do
        tgt_dtb=$(find "${D}" -wholename "*/${dtb}.dtb" -printf '%P\n')
        if [ -z "${tgt_dtb}" ] || [ ! -e "${D}/${tgt_dtb}" ]; then
            echo "Could not find file ${dtb} to add signature data" >&2
            exit 1
        fi
        copy_signature_node "${src_dtb}" "${tgt_dtb}"
    done
}

proc_of_list "${1?Expecting name of DTB file containing signature}"
