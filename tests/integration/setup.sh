#!/bin/bash

tcb_tests_prepare() {
    local WORKDIR=$1
    mkdir -p $WORKDIR
    unset _SETUP_SCRIPT
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

    for REPO in bats-core:v1.12.0 bats-assert:v2.1.0 bats-file:v0.4.0 bats-support:v0.3.0; do
        NAME=$(echo $REPO | cut -d':' -f 1)
        VERSION=$(echo $REPO | cut -d':' -f 2)
        if ! tcb_tests_install_bats_clone $DIR $NAME $VERSION; then
            echo "Error: could not clone $NAME repository!"
            return 1
        fi
    done
}

tcb_tests_download_script() {
    local WORKDIR=$1
    # Current version of tcb-env-script pinned to 'next' branch HEAD as of November 3rd 2026
    # TODO: Replace the default branch to master once the next branch contents go to master
    local SETUP_SCRIPT_BRANCH="${TCB_SCRIPT_BRANCH:-9fe02193554301cf324a97064342bbc7aa12c1cd}"
    _SETUP_SCRIPT=$WORKDIR/tcb-env-setup.sh

    if [ "${TCB_SKIP_SCRIPT_PULL}" = "1" ]; then
        echo "Skipping TorizonCore Builder setup script download..."
        return 0
    fi

    rm -rf ${_SETUP_SCRIPT}
    echo "Downloading TorizonCore Builder setup script..."
    echo "Setup script branch: $SETUP_SCRIPT_BRANCH"
    if ! wget -q https://raw.githubusercontent.com/toradex/tcb-env-setup/$SETUP_SCRIPT_BRANCH/tcb-env-setup.sh; then
        echo "Error: could not download setup script!"
        return 1
    fi

    if [ "$SETUP_SCRIPT_BRANCH" != "master" ]; then
        echo "NOTE: You may see a warning message saying the script is outdated."
        echo "NOTE: This only applies if you're using the 'master' branch, and can be ignored if using other branches."
    fi
    mv tcb-env-setup.sh ${_SETUP_SCRIPT}
}

tcb-ci-selfname() {
    local n="tcb_ci_${TCB_CI_RUN_ID:-$$}_$(od -An -N4 -tu4 /dev/urandom | tr -d ' ')"
    printf -- '-e TCB_CONTAINER_NAME=%s --name %s' "$n" "$n"
}
export -f tcb-ci-selfname

# Succeeds if the tcb-env-setup.sh arguments already pick a tag (-a or -t).
# Uses the same option string as tcb-env-setup.sh, so bundled flags work
# and nothing after "--" (Docker options) is looked at.
tcb-args-pick-tag() {
    local OPTIND=1 opt
    while getopts ":a:t:s:dncPh" opt; do
        case "$opt" in
            a|t) return 0 ;;
            :) [ "$OPTARG" = a ] || [ "$OPTARG" = t ] && return 0 ;;
        esac
    done
    return 1
}

tcb_tests_run_script() {
    local SCRIPT_PARAMS=("$@")
    [ ${#SCRIPT_PARAMS[@]} -eq 0 ] && SCRIPT_PARAMS=(-c -a remote)
    if ! tcb-args-pick-tag "${SCRIPT_PARAMS[@]}"; then
        echo "NOTE: Neither -t nor -a were passed to tcb-env-setup.sh."
        echo "NOTE: Adding '-a remote' to make sure the script works without user interaction."
        SCRIPT_PARAMS=(-a remote "${SCRIPT_PARAMS[@]}")   # before any "--"
    fi

    if uname -r | grep -i "microsoft" > /dev/null; then
        # tcb-env-script doesn't set --network=host on a Windows/WSL environment.
        # Add extra parameters to allow "ostree serve" to work under Windows.
        TCB_OPT_NETWORK="${TCB_OPT_NETWORK:---network=host}"
    fi

    # Make every TCB container instance have its own unique name
    export TCB_OPT_SELFNAME='$(tcb-ci-selfname)' # single quotes: expanded per call, not now

    echo "Pulling TorizonCore Builder container..."
    echo "Sourcing tcb-env-setup.sh with the following parameters: ${SCRIPT_PARAMS[*]}"
    if ! . "${_SETUP_SCRIPT}" "${SCRIPT_PARAMS[@]}"; then
        echo "Error: could not pull container and initialize environment!"
        return 2
    fi

    echo "Testing TorizonCore Builder installation..."
    if [ ! "$(type -t torizoncore-builder)" = "function" ]; then
        echo "Error: torizoncore-builder was not exported as a shell function."
        return 3
    fi

    if ! torizoncore-builder --version >/dev/null; then
        echo "Error: could not execute TorizonCore Builder!"
        return 3
    fi
}

tcb_tests_clean_storage_volume() {
    echo "Removing any leftover TCB containers..."
    if ! docker ps -aq --filter 'name=^tcb_ci_' | xargs -r docker rm -f > /dev/null; then
        echo "Error: could not remove leftover TCB containers!"
        return 3
    fi

    echo "Removing all stopped containers..."
    if ! docker container prune -f >/dev/null; then
        echo "Error: could not remove stopped containers!"
        return 1
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
        tcb_tests_download_script $WORKDIR && \
        tcb_tests_run_script "$@" && \
        tcb_tests_clean_storage_volume && \
        echo "Environment successfully configured to start integration tests."
}

tcb_tests_main "$@"
