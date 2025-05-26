#!/bin/bash
#
# Usage: update_fit_configs_keyname.sh <fit-with-signature-node> <new-key-name>
#
# Normally <fit-with-signature-node> would be set to the kernel fitImage.
#

set -e

[ "${XTRACE}" = "1" ] && set -x

# Set DRY_RUN to 1 to prevent modifying the target DTBs.
DRY_RUN=${DRY_RUN:-0}

# Prefix to all files accessed (defaults to CWD).
D=${PREFIX:-.}

FIT_FILE="${1?Expecting name of FIT containing signed configurations}"
KEY_NAME="${2?Expecting new key name}"

CONFIG_LIST=$(fdtget "${D}/${FIT_FILE}" "/configurations" -l)

for config in ${CONFIG_LIST}; do
    config_subnodes=$(fdtget "${D}/${FIT_FILE}" "/configurations/${config}" -l)
    for config_subnode in ${config_subnodes}; do
        if $(fdtget -ts "${D}/${FIT_FILE}" "/configurations/${config}/${config_subnode}" -p | grep -q "key-name-hint"); then
            if [ "${DRY_RUN}" = "0" ]; then
                fdtput -ts "${D}/${FIT_FILE}" "/configurations/${config}/${config_subnode}" "key-name-hint" "${KEY_NAME}"
            else
                echo "Would execute fdtput -ts ${D}/${FIT_FILE} /configurations/${config}/${config_subnode} key-name-hint ${KEY_NAME}"
            fi
        fi
    done
done
