#!/bin/bash

#
# Globally accessible functions in the test cases
#

# run torizoncore-builder
torizoncore-builder() {
    local CMD=$(eval echo $TCBCMD)
    $CMD $@
}
export -f torizoncore-builder

# run command inside torizoncore-builder container
# $@ = command to be executed
torizoncore-builder-shell() {
    local TCB=$(echo ${TCBCMD##* })
    docker run --rm -v $(pwd):/workdir -v storage:/storage --entrypoint /bin/bash $TCB -c "$@"
}
export -f torizoncore-builder-shell

# clean torizoncore-builder storage
torizoncore-builder-clean-storage() {
    docker container prune -f >/dev/null 2>&-
    docker volume rm storage -f >/dev/null 2>&-
}
export -f torizoncore-builder-clean-storage

# run command in the device via SSH
# $@ = command to be executed
device-shell() {
    local OPTS="-o ConnectTimeout=5 -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no"
    sshpass -p $DEVICE_PASS ssh -n -q $OPTS $DEVICE_USER@$DEVICE_ADDR $@
}
export -f device-shell

# run command in the device via SSH using sudo
# $@ = command to be executed with sudo
device-shell-root() {
    device-shell "echo $DEVICE_PASS | sudo -S $@"
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
