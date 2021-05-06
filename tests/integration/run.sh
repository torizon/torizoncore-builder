#!/bin/bash

BASE_DIR=$PWD
WORK_DIR=$PWD/workdir
IMAGES_DIR=$WORK_DIR/images
TESTCASES_DIR=$BASE_DIR/testcases

REPORT_DIR=$WORK_DIR/reports
REPORT_FILE=$REPORT_DIR/$(date +"%Y%02m%02d%H%M%S").log

TESTCASES="\
$TESTCASES_DIR/torizoncore-builder.bats \
$TESTCASES_DIR/images.bats \
$TESTCASES_DIR/images-unpack.bats \
$TESTCASES_DIR/images-download.bats \
$TESTCASES_DIR/union.bats \
$TESTCASES_DIR/deploy.bats \
$TESTCASES_DIR/isolate.bats \
$TESTCASES_DIR/dt.bats \
$TESTCASES_DIR/dto.bats \
"

# test case to run
if [ ! -z "$TCB_TESTCASE" ]; then
    TESTCASES="$TESTCASES_DIR/$TCB_TESTCASE.bats"
fi

# BATS command
BATS_BIN="./bats/bats-core/bin/bats"
BATS_CMD="$BATS_BIN --timing $TESTCASES"

# directory with samples files to use in the tests
export SAMPLES_DIR=samples

# device address and credentials
export DEVICE_ADDR=$TCB_DEVICE
export DEVICE_USER="torizon"
export DEVICE_PASS="1"

# machine defines the default tezi image used in test cases
if [ ! -z "$TCB_MACHINE" ]; then
    MACHINE=$TCB_MACHINE
else
    MACHINE="apalis-imx6"
fi

# check if setup.sh was sourced.
if [ -z "$TCBCMD" ]; then
    echo "Error: setup.sh was not sourced. Please execute 'source setup.sh' before running the test cases."
    exit 1
fi

# remove '-it' from TorizonCore Builder command (this causes problems when running
# the test cases in an environment not attached to a TTY (e.g. GitLab CI)
export TCBCMD=$(echo $TCBCMD | sed -e "s/ -it//g")

# use a custom torizoncore-builder image
if [ ! -z "$TCB_CUSTOM_IMAGE" ]; then
    echo "Using custom TorizonCore Builder image [$TCB_CUSTOM_IMAGE]."
    export TCBCMD=$(echo $TCBCMD | sed -e "s/torizon\/torizoncore-builder:.*/${TCB_CUSTOM_IMAGE//\//\\/}/g")
fi

# check if Tezi images were downloaded
if [ ! -e $IMAGES_DIR/.images_downloaded ]; then
    echo "Error: Tezi images were not completely downloaded. Please run './get_tezi_images.sh' to download Tezi images."
    exit 2
fi

# load global functions used in the test cases
. ./functions.sh

# check device connection
if [ ! -z "$DEVICE_ADDR" ]; then
    printf "Checking connection with device $DEVICE_ADDR..."
    DEVICE_INFO=$(device-shell cat /etc/os-release)
    echo $DEVICE_INFO | grep -iq torizoncore
    if [ $? = "0" ]; then
        printf "OK!"
    else
        printf "\nError: could not communicate with device!\n"
        exit 3
    fi

    DEVICE_HOSTNAME=$(device-shell hostname)
    MACHINE=$(echo ${DEVICE_HOSTNAME%-*})
    if [ ! -z "$MACHINE" ]; then
        echo " Found machine $MACHINE."
    else
        printf "\nError: could not identify machine!\n"
        exit 4
    fi
fi

# copy image that will be used in the tests
export DEFAULT_TEZI_IMAGE="$(basename $(ls $IMAGES_DIR/*-${MACHINE}-*.tar 2>&-) 2>&-)"
if [ ! -z "$DEFAULT_TEZI_IMAGE" ]; then
    echo "Test cases using image $DEFAULT_TEZI_IMAGE for machine $MACHINE."
    cp $IMAGES_DIR/$DEFAULT_TEZI_IMAGE $WORK_DIR
else
    echo "Error: could not find image for machine $MACHINE! Did you run get_tezi_images.sh?"
    exit 5
fi

# prepare tests
cd $WORK_DIR
rm -rf $SAMPLES_DIR && cp -a ../$SAMPLES_DIR .
mkdir -p $REPORT_DIR
echo -e "Starting integration tests...\n"

# run tests
if [ "$TCB_REPORT" = "1" ]; then
    $BATS_CMD 2>&1 | tee $REPORT_FILE
    echo "Test report available in $REPORT_FILE"
else
    $BATS_CMD
fi

# end tests
echo "Integration tests finished!"
cd $BASE_DIR
