#!/bin/bash

[ "${XTRACE}" = "1" ] && set -x

set -e

# parameters
SOC="$1"
SRK_FUSE_FILE="$2"
FUSE_CMDS_FILE="$3"
FUSE_INFO_FILE="$(dirname "$FUSE_CMDS_FILE")/imx-config.fuse"
TEMPLATES_DIR=${4:-"."}

# warning to program SRK hash fuses
WARNING1="\
# These are One-Time Programmable e-fuses. Once you write them you can't
# go back, so get it right the first time!"

# warning to 'close' the device
WARNING2="\
# After the device successfully boots a signed image without generating
# any HAB events, it is safe to secure, or 'close', the device. This is
# the last step in the process. Once the fuse is blown, the chip does
# not load an image that has not been signed using the correct PKI tree.
# Be careful! This is again a One-Time Programmable e-fuse. Once you
# write it you can't go back, so get it right the first time. If
# anything in the previous steps wasn't done correctly, after writing
# this bit, the SOM will not boot anymore!"

fuse_write_line() {
    local bank=$1
    local word=$2
    local hexval=$3
    echo "fuse prog -y $bank $word $hexval"
}

create_fuse_cmds() {
    local template_file="$1"

    echo "Generating fusing files using template [$template_file]."

    if [ ! -e "$template_file" ]; then
        echo "Template file not found [$template_file]!"
        return 1
    fi

    cp "$template_file" "$FUSE_INFO_FILE"
    echo "${WARNING1}" > "$FUSE_CMDS_FILE"

    echo "Writing fusing commands..."

    for hexval in $(hexdump -e '/4 "0x"' -e '/4 "%X""\n"' "${SRK_FUSE_FILE}"); do
        fuse_info=$(grep -m 1 "^H:F:.*:$" "$FUSE_INFO_FILE")
        bank=$(echo "$fuse_info" | cut -d: -f3)
        word=$(echo "$fuse_info" | cut -d: -f4)
        sed -i "/^$fuse_info/ s/\$/$hexval/" "$FUSE_INFO_FILE"
        fuse_write_line "$bank" "$word" "$hexval" >> "$FUSE_CMDS_FILE"
    done

    if grep -q "^H:F:.*:$" "$FUSE_INFO_FILE"; then
        rm -rf "$FUSE_INFO_FILE" "$FUSE_CMDS_FILE"
        echo "Error: there are still unpopulated fuse values!"
        return 1
    fi

    echo -e "\n${WARNING2}" >> "$FUSE_CMDS_FILE"

    echo "Writing 'close' command..."

    if grep -q "H:T:HAB" "$FUSE_INFO_FILE"; then
        fuse_info=$(grep "^H:C:" "$FUSE_INFO_FILE")
        bank=$(echo "$fuse_info" | cut -d: -f3)
        word=$(echo "$fuse_info" | cut -d: -f4)
        hexval=$(echo "$fuse_info" | cut -d: -f5)
        fuse_write_line "$bank" "$word" "$hexval" >> "$FUSE_CMDS_FILE"
    else
        echo "ahab_close" >> "$FUSE_CMDS_FILE"
    fi

    echo "Fusing files successfully generated!"
}

# Print command for Yocto logs
echo "$0" "$@"

case ${SOC} in
    "IMX6ULL"|"IMX6")
        create_fuse_cmds "${TEMPLATES_DIR}/imx6-template.fuse"
        ;;
    "IMX7")
        create_fuse_cmds "${TEMPLATES_DIR}/imx7-template.fuse"
        ;;
    "IMX8M")
        create_fuse_cmds "${TEMPLATES_DIR}/imx8m-template.fuse"
        ;;
    "iMX8QX")
        create_fuse_cmds "${TEMPLATES_DIR}/imx8qx-template.fuse"
        ;;
    "iMX8QM")
        create_fuse_cmds "${TEMPLATES_DIR}/imx8qm-template.fuse"
        ;;
    "iMX95")
        create_fuse_cmds "${TEMPLATES_DIR}/imx95-template.fuse"
        ;;
    *)
        echo "Invalid SOC!"
        return 1
        ;;
esac
