#!/bin/bash
#
# This script assumes a working Toradex module with a clean, recent nightly build of TorizonCore pre-installed.
#
# On successful execution, the script serves a local Tezi image with the followng characteristics:
#
#   1. Based on the same nightly build with evaluation containers as per the device's installation.
#   2. Has optional device tree overlays applied.
#   3. Has a modified "bananas" boot splash screen.
#   4. Contains the file "/etc/hello.txt", that was detected as a local modification in the device.
#   5. Contains the file "/etc/hi.txt", that was introduced as an external change.
#
# The following environment variables tune the execution of the script:
#
#  WORK_DIR (working directory)
#  TCB_IMAGE (torizoncore-builder container image)
#  SSH_ADDR, SSH_USER, SSH_PASSWD (remote connection to the module)
#  DEVICE_TREE, OVERLAYS (device tree overlays to be applied)
#
# When absent, a variable of the list above assumes a default value --
# look for calls to 'setting' throughout the code below.
#

set -xeuo pipefail

# Early ask for sudo password, if any.
sudo true

# Check torizoncore-builder tool
setting() { eval echo "$1=\${$1:=$2}" 1>&2 ; }
setting WORK_DIR ~/toradex/torizoncore-builder/work
mkdir -p $WORK_DIR
cd $WORK_DIR
setting TCB_IMAGE torizon/torizoncore-builder:2
docker pull $TCB_IMAGE
tcb() { docker run --rm -it -v $WORK_DIR:/workdir -v storage:/storage -v /deploy --net=host -v /var/run/docker.sock:/var/run/docker.sock $TCB_IMAGE $@ ; }
tcb -h | grep -qi '^usage:'

# Check the SOM.
setting SSH_ADDR 192.168.15.162
setting SSH_USER torizon
setting SSH_PASSWD 1
RSH="sshpass -p$SSH_PASSWD ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no -l$SSH_USER $SSH_ADDR"
$RSH cat /etc/os-release | grep -q '^NAME="TorizonCore"$'
MACHINE=$($RSH cat /etc/profile.d/machine.sh | sed 's/.*=//')
test -n "$MACHINE"

# Retrieve the base Tezi image.
BUILD_ID=$($RSH cat /etc/os-release | sed -e '/^BUILD_ID=/!d' -e 's/.*=//' -e 's/"//g')
test -n "$BUILD_ID"
rm -f oedeploy/index.html
wget --recursive --continue --no-parent --level=1 --no-directories --directory-prefix=oedeploy \
    https://artifacts.toradex.com/artifactory/torizoncore-oe-prerelease-frankfurt/dunfell-5.x.y/nightly/$BUILD_ID/$MACHINE/torizon/torizon-core-docker-evaluation/oedeploy/
TEZI_TAR_FILE=(oedeploy/torizon-core-docker-evaluation-${MACHINE}-Tezi_*-devel-*+build.${BUILD_ID}.container.tar)
test $(sha256sum $TEZI_TAR_FILE | sed 's/[[:blank:]].*//') = $(<${TEZI_TAR_FILE}.sha256)
sudo rm -rf teziimage
mkdir teziimage
tar -C teziimage -xf $TEZI_TAR_FILE

# UNPACK
docker volume rm storage
tcb unpack --image-directory teziimage/torizon-core-docker-evaluation-*

# DT
tcb dt checkout
setting DEVICE_TREE imx8qm-apalis-v1.1-ixora-v1.1.dtb
tcb dt list-devicetrees | grep -q "\<${DEVICE_TREE}\>"
setting OVERLAYS apalis-imx8_atmel-mxt_overlay.dts,apalis-imx8_lvds_overlay.dts
test -z "$OVERLAYS" || tcb dt overlay --devicetree $DEVICE_TREE $(sed -e 's/^/,/' -e 's|,| device-trees/overlays/|g' <<<$OVERLAYS)

# ISOLATE
echo "hello world" | $RSH 'cat >hello.txt'
echo $SSH_PASSWD | $RSH sudo --stdin cp -f hello.txt /etc/
tcb isolate --remote-host $SSH_ADDR --remote-username $SSH_USER --remote-password $SSH_PASSWD

# SPLASH
wget --continue -O splash.png 'https://freesvg.org/img/pitr_Bananas_icon_1.png'
tcb splash --image splash.png

# UNION
rm -rf changes
mkdir -p changes/usr/etc
echo "hi world" >changes/usr/etc/hi.txt
tcb union --union-branch hello --extra-changes-directory changes

# DEPLOY
sudo rm -rf deploy
tcb deploy --output-directory deploy hello

# BUNDLE
sudo rm -rf bundle certs
ARCH='linux/arm' ; test $($RSH arch) != 'aarch64' || ARCH='linux/arm64'
tcb bundle --file teziimage/torizon-core-docker-evaluation-*/docker-compose.yml --platform $ARCH --host-workdir $WORK_DIR

# COMBINE
sudo rm -rf deploy-containers
mkdir deploy-containers
tcb combine --image-directory deploy --output-directory deploy-containers

# Serve Tezi image.
echo '{"config_format":1,"images":["deploy-containers/image.json"]}' >image_list.json
HOST_IF=$(ip route get $SSH_ADDR | sed -e 's/.* dev *//' -e 's/ .*//' -e 'q')
HOST_ADDR=$(ip addr show dev $HOST_IF | sed -e '/\<inet\>/!d' -e 's/.*\<inet *//' -e 's|/.*||' -e 'q')
echo "Serving Tezi image at http://$HOST_ADDR:8000/image_list.json ..."
exec python -m http.server
