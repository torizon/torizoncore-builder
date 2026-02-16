#!/bin/bash

#
# Globally accessible functions in the test cases
#

# run torizoncore-builder
torizoncore-builder() {
    local CMD=$(eval echo $TCBCMD)
    $CMD "$@"
}
export -f torizoncore-builder

# Usage: torizoncore-builder-ex <docker-run-params> -- <tcb-params>
torizoncore-builder-ex() {
    local extra_params=()

    # Consume parameters up to the separator ("--")
    while true; do
        if [ "$1" = "--" ]; then
            shift
            break
        else
            extra_params+=("'$1'")
            shift
        fi
    done

    #local CMD=$(eval printf "{%s}" ${TCBCMD/ run / run "${extra_params[@]}" })
    local CMD=$(eval echo ${TCBCMD/ run / run "${extra_params[@]}" })
    $CMD "$@"
}
export -f torizoncore-builder-ex

# Global variable keeping the current torizoncore-builder running in the background
export TCB_BG_CONTAINER=""

# run torizoncore-builder-bg
torizoncore-builder-bg() {
    # Make sure no other process is running in the background
    assert [ -z $TCB_BG_CONTAINER ]
    # Make sure the docker command does not have the "-it" parameter(s)
    [[ $TCBCMD == *" -it"* ]] && assert false
    # Replace the "run" in "docker run ..." with "run -d" to run it in detached mode
    # and to output the ID of the container.
    local CMD=$(eval echo ${TCBCMD/ run / run -d })
    # Print alias definition if test fail
    echo "torizoncore-builder-bg alias was defined as: $CMD $@"
    # Run container in the background
    run $CMD $@
    assert_success
    # Save the ID of the container.
    TCB_BG_CONTAINER=$output
    echo "# Started container $TCB_BG_CONTAINER in the background"
    # Wait some time so TorizonCore Builder can be initialized.
    sleep 5
}
export -f torizoncore-builder-bg

# run stop-torizoncore-builder-bg
stop-torizoncore-builder-bg() {
    [ -z $TCB_BG_CONTAINER ] && return 0
    echo "# Stopping container $TCB_BG_CONTAINER in the background"
    docker container stop -t5 $TCB_BG_CONTAINER
    TCB_BG_CONTAINER=""
}
export -f stop-torizoncore-builder-bg

# run command inside torizoncore-builder container
# $@ = command to be executed
torizoncore-builder-shell() {
    local TCB=$(echo ${TCBCMD##* })
    docker run --rm -v $(pwd):/workdir -v storage:/storage --net=host --entrypoint /bin/bash $TCB -c "$*"
}
export -f torizoncore-builder-shell

# clean torizoncore-builder storage
torizoncore-builder-clean-storage() {
    # TODO: Question: Why are we closing stderr?
    docker container prune -f >/dev/null 2>&-
    docker volume rm storage -f >/dev/null 2>&-
}
export -f torizoncore-builder-clean-storage

# run command in the device via SSH
# $@ = command to be executed
device-shell() {
    local OPTS="-o ConnectTimeout=5 -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no"
    sshpass -p $DEVICE_PASSWORD ssh -p $DEVICE_PORT -n -q $OPTS $DEVICE_USER@$DEVICE_ADDR "$@"
}
export -f device-shell

# run command in the device via SSH using sudo
# $@ = command to be executed with sudo
device-shell-root() {
    device-shell "echo $DEVICE_PASSWORD | sudo -S $@"
}
export -f device-shell-root

# wait for SSH connection to be available
# $1 = number of tries (1 try every 5 seconds)
device-wait() {
    local QTD=$1
    for try in $(seq 1 $QTD); do
        if device-shell "exit 0"; then
            return 0
        fi
	sleep 5
    done
    echo "Could not connect to device after $QTD tries."
    return 1
}
export -f device-wait

# reboot device
device-reboot() {
    run device-shell-root "reboot"
}
export -f device-reboot

# run get-host-ip
get-host-ip() {
    local TARGET_IP=${1?target IP must be passed}
    if uname -r 2>/dev/null | grep -iq "microsoft"; then
        ipconfig.exe 2>/dev/null |
        sed -n '/adapter \(Ethernet\|Wi[- ]Fi\)/,/^[^[:space:]]/{
            /^[[:space:]]*IPv4 Address/{
                s/.*: *\([0-9.]\+\).*/\1/p
                q
            }
        }'
    else
        ip route get $TARGET_IP | sed -ne 's/.*\bsrc\b \b\([^ ]\+\)\b.*/\1/p'
    fi
}
export -f get-host-ip

# skip test if device not configured
requires-device() {
    if [ -z "$DEVICE_ADDR" ]; then
        skip "device not configured"
    fi
}
export -f requires-device

# unpack image if needed
# $1 = path to image tarball
unpack-image() {
	if [ ! -d "$1" ]; then
		echo "Unpacking image $1"
		tar xvf "$1"
	fi
}
export -f unpack-image

# determine image version string "major.minor.patch" from image file name
# $1 = image file name
image-version() {
	echo "$1" | sed -E -ne 's#^.*Tezi_([0-9]+\.[0-9]+\.[0-9]+).*$#\1#p'
}
export -f image-version

# skip test if image version is not greater or equal than major.minor.patch
# $1 = image file name
# $2 = required minimal semver (e.g. "5.2.0")
requires-image-version() {
	local VER="$(image-version \"$1\")"
	if [ -z "$VER" ]; then
		skip "cannot determine image version"
	fi
	# Extract parts of semver:
	local MAJOR MINOR PATCH
	IFS='.' read MAJOR MINOR PATCH <<< "$VER"
	local CURVER="$(($MAJOR*10000 + $MINOR*100 + $PATCH))"
	IFS='.' read MAJOR MINOR PATCH <<< "$2"
	local REQVER="$(($MAJOR*10000 + $MINOR*100 + $PATCH))"
	if [ $CURVER -lt $REQVER  ]; then
		skip "image must be version $2+ for this test (but it is $VER)"
	fi
}
export -f requires-image-version

# skip test if running under CI
skip-under-ci() {
    if [ "$TCB_UNDER_CI" = "1" ]; then
        skip "running under CI"
    fi
}
export -f skip-under-ci

skip-no-ota-credentials() {
    if [ -z "$TCB_OTA_CREDENTIALS_PWD" ]; then
        skip "TCB_OTA_CREDENTIALS_PWD not set"
    fi
}
export -f skip-no-ota-credentials

# Decrypt a file previously encrypted with key stored in variable TCB_OTA_CREDENTIALS_PWD
# $1 = file to be decrypted
# Output the name of the decrypted file
decrypt-credentials-file() {
    if [ -z "$TCB_OTA_CREDENTIALS_PWD" ]; then
        echo "# TCB_OTA_CREDENTIALS_PWD not set" >&3
        return 1
    fi
    if [ "${1##*.}" != "enc" ]; then
        echo "# decrypt-credentials-file: input file must have a .enc extension" >&3
        return 1
    fi

    local INFILE="$1"
    local OUTFILE="${1%.enc}.dec"

    # See https://stackoverflow.com/a/55975571/10335947
    # To encrypt all .zip files in a directory:
    # $ for fn in *.zip; do openssl enc -aes-256-cbc -pbkdf2 -iter 20000 -in "$fn" -out "${fn}.enc" -k "$TCB_OTA_CREDENTIALS_PWD"; done
    openssl enc -d \
        -aes-256-cbc -pbkdf2 -iter 20000 \
        -in "$INFILE" -out "$OUTFILE" -k "$TCB_OTA_CREDENTIALS_PWD"

    echo "$OUTFILE"
}
export -f decrypt-credentials-file

is-major-version-greater-than-5() {
    local MAJOR_VERSION=$(echo "${DEFAULT_TEZI_IMAGE}" | sed 's/.*Tezi_\([0-9]\).*/\1/')
    [ "${MAJOR_VERSION}" -gt "5" ]
}
export -f is-major-version-greater-than-5

get-unique-version() {
    echo "${MACHINE}-${EPOCHSECONDS}"
}
export -f get-unique-version

is-dockerhub-login-set() {
   [ -n "${CI_DOCKER_HUB_PULL_USER}" ] && [ -n "${CI_DOCKER_HUB_PULL_PASSWORD}" ]
}
export -f is-dockerhub-login-set

# Returns string "1" if all checks are successful; otherwise nothing is returned.
# This function is used to facilitate the use of the ${parameter:+word} substitution feature in Bash.
ci-dockerhub-login-flag() {
    [ "${TCB_UNDER_CI}" = "1" ] && is-dockerhub-login-set && echo "1"
}
export -f ci-dockerhub-login-flag

requires-signed-image() {
    if [ -z "${DEFAULT_SIGNED_TEZI_IMAGE}" ]; then
        skip "signed image not found"
    fi
}
export -f requires-signed-image

requires-unsigned-image() {
    if [ -n "${DEFAULT_SIGNED_TEZI_IMAGE}" ]; then
        skip "Unsupported test for signed images"
    fi
}
export -f requires-unsigned-image

requires-supported-kernel-signing-machine() {
    if [ "${IS_KERNEL_SIGNING_SUPPORTED}" != "1" ]; then
        skip "machine not supported"
    fi
}
export -f requires-supported-kernel-signing-machine

requires-supported-hab-signing-machine() {
    if [ "${IS_HAB_SIGNING_SUPPORTED}" != "1" ]; then
        skip "machine not supported"
    fi
}
export -f requires-supported-hab-signing-machine

contains-all-words() {
    local haystack=$(echo "$1" | tr '\n' ' ')
    local needle=$(echo "$2" | tr '\n' ' ')
    local word

    for word in $needle; do
        case " $haystack " in
            *" $word "*) ;; # found — continue
            *) return 1 ;;  # missing — fail immediately
        esac
    done
    return 0
}
export -f contains-all-words

unpacked-kernel-in-fit-format() {
    local FDT_HEADER_MAGIC="d00dfeed"
    local OSTREE_KERNEL_FILENAME="vmlinuz"
    local OSTREE_KERNEL_DEPLOY_PATH="/storage/sysroot/ostree/deploy/torizon/deploy/*/usr/lib/modules/*/"

    local REQUIRED_PROPS="timestamp"
    local REQUIRED_NODES="images configurations"

    local OSTREE_KERNEL="${OSTREE_KERNEL_DEPLOY_PATH}${OSTREE_KERNEL_FILENAME}"

    local kernel_header found_props found_nodes

    if torizoncore-builder-shell "[ ! -f ${OSTREE_KERNEL} ]"; then
        # Error case
        echo "Cannot find kernel in unpacked image. Did you run 'images unpack' beforehand?" >&2
        return 3
    fi

    kernel_header=$(torizoncore-builder-shell "hexdump -n 4 -e '4/1 \"%02x\"' ${OSTREE_KERNEL}")

    if [ "${kernel_header}" = "${FDT_HEADER_MAGIC}" ]; then
        found_props=$(torizoncore-builder-shell "fdtget ${OSTREE_KERNEL} / -p")
        found_nodes=$(torizoncore-builder-shell "fdtget ${OSTREE_KERNEL} / -l")

        if ! contains-all-words "${found_props}" "${REQUIRED_PROPS}"; then
            # Error case
            echo "Kernel in invalid FIT format" >&2
            return 2
        fi

        if ! contains-all-words "${found_nodes}" "${REQUIRED_NODES}"; then
            # Error case
            echo "Kernel in invalid FIT format" >&2
            return 2
        fi

        return 0 # Kernel is in FIT format
    else
        return 1 # Kernel is not in FIT format
    fi
}
export -f unpacked-kernel-in-fit-format

requires-non-fit-kernel() {
    if [ "${DEFAULT_TEZI_IMAGE_HAS_FIT_KERNEL}" = "1" ]; then
        skip "kernel in FIT format is unsupported"
    fi
}
export -f requires-non-fit-kernel

requires-fit-kernel() {
    if [ "${DEFAULT_TEZI_IMAGE_HAS_FIT_KERNEL}" != "1" ]; then
        skip "kernel is not in FIT format"
    fi
}
export -f requires-fit-kernel

signing-artifacts-in-unpacked-tezi-image() {
    local DEFAULT_TCB_SIGNING_FILES_TARNAME="tcb_signing_files.tar.gz"

    if torizoncore-builder-shell "[ ! -d /storage/tezi ]"; then
        # Error case
        echo "Cannot find unpacked image in internal storage. Did you run 'images unpack' beforehand?" >&2
        return 1
    fi

    # Check if image has signing artifacts
    torizoncore-builder-shell "[ -f /storage/tezi/${DEFAULT_TCB_SIGNING_FILES_TARNAME} ]"
}
export -f signing-artifacts-in-unpacked-tezi-image

unpacked-ostree-repo-has-composefs-support() {
    local status
    local repo="/storage/sysroot/ostree/repo/"
    local prop="ex-integrity.composefs"
    if status=$(torizoncore-builder-shell "ostree config --repo ${repo} get ${prop}"); then
	if [[ "${status}" == @(true|yes|1) ]]; then
	    # composefs is enabled
	    return 0
	fi
	# composefs is not enabled
	return 1
    fi
    # composefs is not configured (default state: disabled)
    return 2
}
export -f unpacked-ostree-repo-has-composefs-support

requires-no-cfs-support() {
    if [ "${DEFAULT_TEZI_IMAGE_HAS_CFS_SUPPORT}" = "1" ]; then
        skip "composefs image not supported"
    fi
}
export -f requires-no-cfs-support

requires-cfs-support() {
    if [ "${DEFAULT_TEZI_IMAGE_HAS_CFS_SUPPORT}" != "1" ]; then
        skip "non-composefs image not supported"
    fi
}
export -f requires-cfs-support

# Returns string "1" if the default tezi image has composefs support.
# This function is used to facilitate the use of the ${parameter:+word} substitution feature in Bash.
cfs-support-flag() {
    [ "${DEFAULT_TEZI_IMAGE_HAS_CFS_SUPPORT}" = "1" ] && echo "1"
}
export -f cfs-support-flag

# Usage: set-ostree-key-in-tcbuild <tcbuild> <ostree-key> [<ostree-key-dir>]
#
# Contents of the tcbuild file should look like this:
#
# ```
# # customization:
#   # secboot:
#     # sign-ostree:
#       # ostree-key-dir: {{ ostree_key_dir }}
#       # ostree-key:
#          # - name: {{ ostree_key_name }}
#          #   algo: {{ ostree_key_algo }}
# ```
#
# Example:
#
# $ set-ostree-key-in-tcbuild "tcbuild.yaml" "name=CFS;algo=ed25519" "key-dir/"
#
set-ostree-key-in-tcbuild() {
    local tcbuild="${1?tcbuild file path expected}"
    local ostree_key="${2?ostree-key expected}"
    local ostree_key_dir="${3-}"

    # Uncomment parent properties:
    sed -e '/^[[:space:]]*##[[:space:]]*\(customization\|secboot\|sign-ostree\):$/ {s/## //}' \
	"${tcbuild}" > "${tcbuild}.tmp"

    if [ -n "${ostree_key_dir}" ]; then
	sed -e "\,^[[:space:]]*##.*{{ ostree_key_dir }}, {
                   s,## ,,
                   s,{{ ostree_key_dir }},\"${ostree_key_dir}\",
               }" \
	    -i "${tcbuild}.tmp"
    fi

    sed -e '/^[[:space:]]*##[[:space:]]*ostree-key:$/ {s/## //}' \
	-i "${tcbuild}.tmp"

    (
	IFS=";"
	for fld in ${ostree_key}; do
	    local key="${fld%%=*}"
	    local val="${fld#*=}"
	    sed -e "\,^[[:space:]]*##.*{{ ostree_key_${key} }}, {
                       s,## ,,
                       s,{{ ostree_key_${key} }},\"${val}\",
                   }" \
		-i "${tcbuild}.tmp"
	done
    )

    if [ "${DBG_SET_OSTREE_KEY-0}" = "1" ]; then
        cat "${tcbuild}.tmp"
    else
        mv "${tcbuild}.tmp" "${tcbuild}"
    fi
}
export -f set-ostree-key-in-tcbuild
