#!/bin/bash

tcb_tests_prepare() {
    local WORKDIR=$1
    mkdir -p $WORKDIR
    unset -v TCBCMD
}

tcb_tests_install_bats_clone() {
    local DIR=$1/$2
    local REPO=$2
    local VERSION=$3
    echo "Installing $REPO $VERSION..."
    if ! git clone --depth=1 https://github.com/bats-core/$REPO.git -b $VERSION $DIR >/dev/null 2>&-; then
        return 1
    fi
}

tcb_tests_install_bats() {
    local DIR="$1/bats"
    local REPO=""
    local NAME=""
    local VERSION=""

    rm -Rf $DIR

    for REPO in bats-core:v1.8.0 bats-assert:v2.0.0 bats-file:v0.3.0 bats-support:v0.3.0; do
        NAME=$(echo $REPO | cut -d':' -f 1)
        VERSION=$(echo $REPO | cut -d':' -f 2)
        if ! tcb_tests_install_bats_clone $DIR $NAME $VERSION; then
            echo "Error: could not clone $NAME repository!"
            return 1
        fi
    done
}

tcb_tests_pull_container() {
    local WORKDIR=$1
    local SETUP_SCRIPT=$WORKDIR/tcb-env-setup.sh

    if [ "$TCB_SKIP_PULL" = "1" ]; then
        echo "Skipping TorizonCore Builder configuration..."
        return 0
    fi

    rm -rf $SETUP_SCRIPT
    echo "Downloading TorizonCore Builder setup script..."
    if ! wget -q https://raw.githubusercontent.com/toradex/tcb-env-setup/master/tcb-env-setup.sh; then
        echo "Error: could not download setup script!"
        return 1
    fi
    mv tcb-env-setup.sh $SETUP_SCRIPT

    local SCRIPT_PARAMS="-a remote"
    if uname -r | grep -i "microsoft" > /dev/null; then
        # Add extra parameters to allow "ostree serve" to work under Windows.
        SCRIPT_PARAMS="${SCRIPT_PARAMS} -- -p 8080:8080"
    fi

    echo "Pulling TorizonCore Builder container..."
    if ! . $SETUP_SCRIPT $SCRIPT_PARAMS >/dev/null 2>&-; then
        echo "Error: could not pull container and initialize environment!"
        return 2
    fi

    export TCBCMD=$(alias torizoncore-builder | cut -d "'" -f 2)

    echo "Testing TorizonCore Builder installation..."
    if ! eval $TCBCMD --version >/dev/null 2>&-; then
        echo "Error: could not execute TorizonCore Builder!"
        return 3
    fi
}

tcb_tests_clean_storage_volume() {
    echo "Removing all stopped containers..."
    if ! docker container prune -f >/dev/null; then
        echo "Error: could not remove stopped containers!"
        return 1;
    fi

    echo "Removing storage volume..."
    if ! docker volume rm storage -f >/dev/null; then
        echo "Error: could not remove storage volume!"
        return 2
    fi
}

tcb_tests_main() {
    local WORKDIR="workdir"
    tcb_tests_prepare $WORKDIR && \
        tcb_tests_install_bats $WORKDIR && \
        tcb_tests_pull_container $WORKDIR && \
        tcb_tests_clean_storage_volume && \
        echo "Environment successfully configured to start integration tests."
}

tcb_tests_main
