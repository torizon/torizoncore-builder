#!/bin/bash

BASE_DIR=$PWD
WORK_DIR=$PWD/workdir
IMAGES_DIR=$WORK_DIR/images
TESTCASES_DIR=$BASE_DIR/testcases

REPORT_DIR=$WORK_DIR/reports
REPORT_FILE=$REPORT_DIR/$(date +"%Y%02m%02d%H%M%S").xml

TESTCASES="\
$TESTCASES_DIR/setup.bats \
$TESTCASES_DIR/torizoncore-builder.bats \
$TESTCASES_DIR/images.bats \
$TESTCASES_DIR/images-unpack.bats \
$TESTCASES_DIR/images-download.bats \
$TESTCASES_DIR/images-serve.bats \
$TESTCASES_DIR/secboot.bats \
$TESTCASES_DIR/union.bats \
$TESTCASES_DIR/deploy.bats \
$TESTCASES_DIR/isolate.bats \
$TESTCASES_DIR/dt.bats \
$TESTCASES_DIR/dto.bats \
$TESTCASES_DIR/build.bats \
$TESTCASES_DIR/bundle.bats \
$TESTCASES_DIR/bundle-registry.bats \
$TESTCASES_DIR/combine.bats \
$TESTCASES_DIR/kernel.bats \
$TESTCASES_DIR/ostree.bats \
$TESTCASES_DIR/platform.bats \
$TESTCASES_DIR/push.bats \
$TESTCASES_DIR/splash.bats \
$TESTCASES_DIR/splashconfig.bats \
$TESTCASES_DIR/ubootenv.bats \
"

WIC_TESTCASES="\
$TESTCASES_DIR/torizoncore-builder.bats \
$TESTCASES_DIR/wic/images.bats \
$TESTCASES_DIR/wic/images-unpack.bats \
$TESTCASES_DIR/wic/images-download.bats \
$TESTCASES_DIR/wic/union.bats \
$TESTCASES_DIR/wic/deploy.bats \
$TESTCASES_DIR/wic/splash.bats \
$TESTCASES_DIR/wic/splashconfig.bats \
$TESTCASES_DIR/wic/combine.bats \
$TESTCASES_DIR/wic/build.bats \
"

# directory with samples files to use in the tests
export SAMPLES_DIR=samples

# device address and credentials
export DEVICE_ADDR=$TCB_DEVICE
export DEVICE_USER="torizon"

export WIC_MACHINES="intel-corei7-64 qemux86-64 raspberrypi4-64"

# DEVICE_PORT defines the default SSH port used in test cases
if [ ! -z "$TCB_PORT" ]; then
    export DEVICE_PORT=$TCB_PORT
else
    export DEVICE_PORT="22"
fi

# machine defines the default tezi image used in test cases
if [ ! -z "$TCB_MACHINE" ]; then
    export MACHINE=$TCB_MACHINE
else
    echo "Error: TCB_MACHINE is not set."
    exit 1
fi

# check if device password if defined when using device
if [[ -n "$TCB_DEVICE" ]]; then
    if [[ -z "$DEVICE_PASSWORD" ]]; then
        echo "Error: Device password not defined."
        exit 1
    fi
fi

# Variable IS_WIC can be passed to force a specific value; when not passed, it
# is automatically set with a default value that depends on the current machine.
if [[ "$WIC_MACHINES" == *"$MACHINE"* ]]; then
    export IS_WIC="${IS_WIC:-1}"
else
    export IS_WIC="${IS_WIC:-0}"
fi

# test case to run
if [ ! -z "$TCB_TESTCASE" ]; then

    if [ "$IS_WIC" = "1" ]; then
        WIC_TESTCASES=""
        for test in $TCB_TESTCASE; do
            if [ -e "$TESTCASES_DIR/wic/$test.bats" ]; then
                WIC_TESTCASES+="$TESTCASES_DIR/wic/$test.bats "
            else
                echo "Group of tests '$test' not found. Ensure the '$test.bats' file" \
                    "is present in the 'tests/integration/testcases/wic' folder."
            fi
        done
    else
        TESTCASES=""
        for test in $TCB_TESTCASE; do
            if [ -e "$TESTCASES_DIR/$test.bats" ]; then
                TESTCASES+="$TESTCASES_DIR/$test.bats "
            else
                echo "Group of tests '$test' not found. Ensure the '$test.bats' file" \
                    "is present in the 'tests/integration/testcases' folder."
            fi
        done
    fi
fi

# test tag filters
FILTER_TAGS=""
if [ -v TCB_TAGS ]; then
    case "$TCB_TAGS" in
        "")
            echo "Running untagged tests."
            FILTER_TAGS='--filter-tags ,'
            ;;
        "all")
            echo "Running all tests."
            ;;
        *all*)
            echo "Error: 'all' filter cannot be used with other filters."
            exit 1
            ;;
        *)
            TCB_TAGS=$(echo "$TCB_TAGS" | sed 's/^\s*//;s/\s*$//;s/\s\+/ /g')
            FILTER_TAGS=${TCB_TAGS// /" --filter-tags "}
            FILTER_TAGS="--filter-tags $FILTER_TAGS"

            FILTER_MSG=${TCB_TAGS// /" or "}
            echo -e "Running tests tagged with: $FILTER_MSG."
            ;;
    esac
fi

# BATS command
BATS_BIN="./bats/bats-core/bin/bats"

if [ "$IS_WIC" = "1" ]; then
    echo "Using specific WIC/raw image tests."
    BATS_CMD="$BATS_BIN --timing ${FILTER_TAGS} $WIC_TESTCASES"
else
    BATS_CMD="$BATS_BIN --timing ${FILTER_TAGS} $TESTCASES"
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
if [ "$IS_WIC" != "1" ] && [ ! -e $IMAGES_DIR/.images_downloaded ]; then
    echo "Error: Tezi images were not completely downloaded. Please run './get_tezi_images.sh' to download Tezi images."
    exit 2
fi

# check if WIC images were downloaded
if [ "$IS_WIC" = 1 ] && [ ! -e $IMAGES_DIR/.raw_images_downloaded ]; then
    echo "Error: WIC/raw images were not completely downloaded. Please run './get_raw_images.sh' to download .img/.wic images."
    exit 2
fi

# load global functions used in the test cases
. ./functions.sh

# check device connection
if [ ! -z "$DEVICE_ADDR" ]; then
    printf "Checking connection with device $DEVICE_ADDR..."
    DEVICE_INFO=$(device-shell cat /etc/os-release)
    echo $DEVICE_INFO | grep -iq torizon
    if [ $? = "0" ]; then
        printf "OK!"
    else
        printf "\nError: could not communicate with device!\n"
        exit 3
    fi

    MACHINE=$(device-shell "/etc/profile.d/machine.sh; echo $MACHINE")
    if [ ! -z "$MACHINE" ]; then
        echo " Found machine $MACHINE."
    else
        printf "\nError: could not identify machine!\n"
        exit 4
    fi
fi

# copy image that will be used in the tests
export DEFAULT_TEZI_IMAGE="$(basename $(ls $IMAGES_DIR/*-${MACHINE}*.tar 2>&-) 2>&-)"
export DEFAULT_SIGNED_TEZI_IMAGE=""
export DEFAULT_WIC_IMAGE="$(basename $(ls $IMAGES_DIR/*-${MACHINE}*.wic 2>&-) 2>&-)"

# There's probably a better way to put the .wic and .img search in a single regex,
# but I wasn't able to figure it out.
if [ "$IS_WIC" = "1" ] && [ -z "$DEFAULT_WIC_IMAGE" ]; then
    export DEFAULT_WIC_IMAGE="$(basename $(ls $IMAGES_DIR/*-${MACHINE}*.img 2>&-) 2>&-)"
fi

if [ "$IS_WIC" != "1" ] && [ ! -z "$DEFAULT_TEZI_IMAGE" ]; then
    echo "Test cases using image $DEFAULT_TEZI_IMAGE for machine $MACHINE."
    cp $IMAGES_DIR/$DEFAULT_TEZI_IMAGE $WORK_DIR
elif [ "$IS_WIC" = "1" ] && [ ! -z "$DEFAULT_WIC_IMAGE" ]; then
    echo "Test cases using image $DEFAULT_WIC_IMAGE for machine $MACHINE."
    cp $IMAGES_DIR/$DEFAULT_WIC_IMAGE $WORK_DIR
else
    echo "Error: could not find image for machine $MACHINE! Did you run get_tezi_images.sh or get_raw_images.sh?"
    exit 5
fi

# prepare tests
export BATS_LIB_PATH="$WORK_DIR"
export DEFAULT_TEZI_IMAGE_HAS_FIT_KERNEL=""
export DEFAULT_TEZI_IMAGE_HAS_CFS_SUPPORT=""
cd $WORK_DIR
rm -rf $SAMPLES_DIR && cp -a ../$SAMPLES_DIR .
mkdir -p $REPORT_DIR
echo -e "Starting integration tests...\n"

_setup_fit_image_vars() {
    if unpacked-kernel-in-fit-format; then
        echo "Image has kernel in FIT format."
        DEFAULT_TEZI_IMAGE_HAS_FIT_KERNEL="1" # valid FIT kernel

        # Check if image with FIT kernel has signing artifacts
        if signing-artifacts-in-unpacked-tezi-image; then
            echo "Image has signing artifacts;" \
                 "Secure boot related tests will be executed for machine ${MACHINE}."
            DEFAULT_SIGNED_TEZI_IMAGE="${DEFAULT_TEZI_IMAGE}"
        fi
    else
        status=$?
        if [ $status -eq 1 ]; then
            DEFAULT_TEZI_IMAGE_HAS_FIT_KERNEL="0" # non-FIT kernel
        else
            # Error case: specific error message provided by the function
            exit $status
        fi
    fi
}

_setup_cfs_supp_vars() {
    DEFAULT_TEZI_IMAGE_HAS_CFS_SUPPORT="0"
    if unpacked-ostree-repo-has-composefs-support; then
        echo "Image has composefs (root filesystem protection) support."
        DEFAULT_TEZI_IMAGE_HAS_CFS_SUPPORT="1"
    else
        echo "Image has NO composefs (root filesystem protection) support."
    fi
}

# If using TEZI image, check if it has a kernel in FIT format as some tests need this info
if [ "$IS_WIC" != "1" ] && [ -n "$DEFAULT_TEZI_IMAGE" ]; then
    torizoncore-builder images --remove-storage unpack "$DEFAULT_TEZI_IMAGE"
    _setup_fit_image_vars
    _setup_cfs_supp_vars
fi

# Run tests
if [ "$TCB_REPORT" = "1" ]; then
    if [ "$TCB_UNDER_CI" = "1" ]; then
        BATS_CMD="$BATS_CMD --report-formatter junit --output $REPORT_DIR"
        echo "Running in CI with JUnit formatter..."
        $BATS_CMD
        EXIT_CODE_TESTS=$?
        mv "$REPORT_DIR/report.xml" "$REPORT_DIR/report-${CI_JOB_NAME}.xml"
        echo "Test report available in $REPORT_DIR/report-${CI_JOB_NAME}.xml"
    else
        echo "Running locally with tee to save report..."
        $BATS_CMD 2>&1 | tee "$REPORT_FILE"
        EXIT_CODE_TESTS=$?
        echo "Test report available in ${REPORT_FILE}."
    fi
else
    echo "Running without report..."
    $BATS_CMD
    EXIT_CODE_TESTS=$?
fi

# end tests
echo "Integration tests finished!"
cd $BASE_DIR
exit $EXIT_CODE_TESTS
