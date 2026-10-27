#!/bin/bash

# run_all.sh - Wrapper script to run all integration tests

# Run all tests without a device:
# ./run_all.sh
#
# Run tests that require a device where the network information is provided by a
# shell-sourceable device-info file (as written by `magma-client flash --tos-password`):
#
# ./run_all.sh --device --device-info custom_device_information
#
# Run a specific test case:
# ./run_all.sh --testcase dto
#
# Run all tests with a specific TCB tag:
# ./run_all.sh --tcb-tags "requires-device" --device
#
# Use a custom TorizonCore Builder image:
# ./run_all.sh --tcb-custom-image torizoncore-builder:v1

usage() {
    echo "Usage: $0 [options]"
    echo "Options:"
    echo "  -h, --help                 Show this help message"
    echo "  -d, --device               Use device connection if required by tests"
    echo "  -i, --device-info FILE     Use specified device information file (default: device_information)"
    echo "  -m, --machine MACHINE      Specify machine type (e.g., apalis-imx6)"
    echo "  -t, --testcase TESTCASE    Specify test case(s) to run"
    echo "  -r, --report               Generate test report"
    echo "  --tcb-tags TAGS            Specify TCB tags"
    echo "  --tcb-custom-image IMAGE   Use custom TorizonCore Builder image"
    echo "  --                         Pass the rest of the arguments to test scripts"
    echo
    echo "Examples:"
    echo "  $0 -d                      Run tests, using device connection if required"
    echo "  $0 -t dto                  Run the 'dto' test case"
    echo "  $0 --tcb-tags requires-device -d  Run tests with 'requires-device' tag, using device connection"
    exit 0
}

export IS_WIC=${IS_WIC:-0}

USE_DEVICE=0
DEVICE_INFO_FILE="device_information"
export TCB_TESTCASE=""
export TCB_REPORT=0
export TCB_TAGS="all"
export TCB_CUSTOM_IMAGE=""
export TCB_DEVICE=""
export DEVICE_ADDR=""
export DEVICE_USER="torizon"

while [[ "$1" != "" ]]; do
    case $1 in
        -d | --device )
            USE_DEVICE=1
            ;;
        -i | --device-info )
            shift
            DEVICE_INFO_FILE="$1"
            ;;
        -m | --machine )
            shift
            export TCB_MACHINE="$1"
            ;;
        -t | --testcase )
            shift
            export TCB_TESTCASE="$1"
            ;;
        -r | --report )
            export TCB_REPORT=1
            ;;
        --tcb-tags )
            shift
            export TCB_TAGS="$1"
            ;;
        --tcb-custom-image )
            shift
            export TCB_CUSTOM_IMAGE="$1"
            ;;
        -h | --help )
            usage
            ;;
        -- )
            shift
            TEST_ARGS="$@"
            break
            ;;
        * )
            echo "Unknown option: $1"
            usage
            ;;
    esac
    shift
done

check_device_connection() {
    if [ -f "$DEVICE_INFO_FILE" ]; then
        # shellcheck disable=SC1090
        source "$DEVICE_INFO_FILE"

        if [ -z "$DEVICE_IP" ]; then
            echo "Error: DEVICE_IP not set by '$DEVICE_INFO_FILE'."
            exit 1
        fi

        export DEVICE_ADDR="$DEVICE_IP"
        export TCB_DEVICE="$DEVICE_IP"

        echo "Using device at IP address $DEVICE_ADDR"
    else
        echo "Error: device information file '$DEVICE_INFO_FILE' not found."
        exit 1
    fi
}

if [ $USE_DEVICE -eq 1 ]; then
    check_device_connection
else
    echo "Device connection not used."
fi

echo "Running setup..."
source ./setup.sh

if [ $? -ne 0 ]; then
    echo "Error running setup.sh"
    exit 1
fi

if [ $IS_WIC = "0" ]; then
    if [ ! -e workdir/images/.images_downloaded ]; then
        echo "Images not found. Attempting to download images..."
        ./get_tezi_images.sh

        if [ ! -e workdir/images/.images_downloaded ]; then
            echo "Error: Images not found and could not be downloaded automatically."
            echo "Please download images manually and place them in workdir/images/."
            exit 1
        fi
    fi
elif [ $IS_WIC = "1" ]; then
    if [ ! -e workdir/images/.raw_images_downloaded ]; then
        echo "Raw Images not found. Attempting to download images..."
        ./get_raw_images.sh

        if [ ! -e workdir/images/.raw_images_downloaded ]; then
            echo "Error: Raw Images not found and could not be downloaded automatically."
            echo "Please download images manually and place them in workdir/images/."
            exit 1
        fi
    fi
else
    echo "Error: IS_WIC (${IS_WIC}) is not set correctly (\"0\" or \"1\")."
    exit 1
fi

echo "Running integration tests..."

RUN_CMD="./run.sh $TEST_ARGS"

$RUN_CMD

if [ $? -ne 0 ]; then
    echo "Error: Integration tests failed."
    exit 1
fi

echo "Integration tests completed successfully."
