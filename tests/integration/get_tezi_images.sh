#!/bin/bash

# default values (commonly overridden)
TARGET_BUILD_TYPE="${TARGET_BUILD_TYPE:-nightly}"
YOCTO_BRANCH="${YOCTO_BRANCH:-scarthgap-7.x.y}"
TCB_MACHINE="${TCB_MACHINE:-colibri-imx6}"
TARGET_SIGNING_CLASS="${TARGET_SIGNING_CLASS-}"

# low-level control (less commonly overridden)
ACCEPT_DISTROS=${ACCEPT_DISTROS-torizon torizon-upstream}
ACCEPT_VARIANTS=${ACCEPT_VARIANTS-torizon-docker torizon-core-docker}
BASE_ARTIFACTORY_URL_PROD=${BASE_ARTIFACTORY_URL_PROD-https://artifacts.toradex.com/artifactory/torizoncore-oe-prod-frankfurt}
BASE_ARTIFACTORY_URL_PRERELEASE=${BASE_ARTIFACTORY_URL_PRERELEASE-https://artifacts.toradex.com/artifactory/torizoncore-oe-prerelease-frankfurt}

# logging
ENABLE_LOG=${ENABLE_LOG:-1}
ENABLE_DBG=${ENABLE_DBG:-0}

# location to save images
OUTDIR="${PWD}/workdir/images"
STAMP="${OUTDIR}/.images_downloaded"

log() {
    if [ "${ENABLE_LOG}" = "1" ]; then
        echo "$@"
    fi
}

dbg() {
    if [ "${ENABLE_DBG}" = "1" ]; then
        echo "$@"
    fi
}

error() {
    echo "ERROR:" "$@" >&2
    exit 1
}

prepare() {
    rm -rf workdir/images
    mkdir -p "${OUTDIR}"
}

download() {
    if [ "${TARGET_BUILD_TYPE}" = "release" ]; then
        _base_url="${BASE_ARTIFACTORY_URL_PROD:?variable not set}"
    elif [ "${TARGET_BUILD_TYPE}" = "nightly" ]; then
        _base_url="${BASE_ARTIFACTORY_URL_PRERELEASE:?variable not set}"
    else
        error "Invalid TARGET_BUILD_TYPE. Expected 'nightly' or 'release'."
    fi

    artifactory_url="${_base_url}/${YOCTO_BRANCH}/${TARGET_BUILD_TYPE}"

    # Determine the available build numbers (limited to 10)
    build_numbers=$(wget -qO- "${artifactory_url}" | grep -o '<a href="[0-9]*/"' |
                    sed -e 's#<a href="##' -e 's#/"##' | sort -nr | head -n10)

    torizon_tar_url=""

    # shellcheck disable=SC2086
    echo "Available build numbers:" ${build_numbers}
    for build in ${build_numbers}; do
        machine_url="${artifactory_url}/${build}/${TCB_MACHINE}/"
        dbg "Accessing ${machine_url}"
        if ! wget --spider -q "${machine_url}"; then
            log "Build #${build}: not available for machine ${TCB_MACHINE}"
            continue
        fi

        distros=$(wget -qO- "${machine_url}" |
                      grep -Eo "href=\"(${ACCEPT_DISTROS/ /|})/*\"" |
                      sed 's/href="\([-a-z]*\).*"/\1/')
        # shellcheck disable=SC2086
        log "Build #${build}: available distros:" ${distros}

        for distro in ${distros}; do
            distro_url="${artifactory_url}/${build}/${TCB_MACHINE}/${distro}/"
            dbg "Accessing ${distro_url}"
            variants=$(wget -qO- "${distro_url}" |
                          grep -Eo "href=\"(${ACCEPT_VARIANTS/ /|})/*\"" |
                          sed 's/href="\([-a-z]*\).*"/\1/')
            # shellcheck disable=SC2086
            log "Build #${build}: available variants:" ${variants}

            for variant in ${variants}; do
                variant_url="${artifactory_url}/${build}/${TCB_MACHINE}/${distro}/${variant}/"

                # Select between signed classes (if any):
                if [ -n "${TARGET_SIGNING_CLASS}" ]; then
                    oedeploy_url="${variant_url}${TARGET_SIGNING_CLASS}/oedeploy/"
                else
                    oedeploy_url="${variant_url}oedeploy/"
                fi

                dbg "Accessing ${oedeploy_url}"
                filename=$(wget -qO- "${oedeploy_url}" | grep '<a href="' |
                               sed -n 's#.*<a href="\([^"]*-Tezi_[^"]*\.tar\)".*#\1#p' |
                               sort -r | head -n1)
                [ -z "${filename}" ] && continue

                torizon_tar_url="${oedeploy_url}${filename}"
                # Leave all loops:
                break 3
            done
        done
    done

    [ -n "${torizon_tar_url}" ] || return 1

    log "Image URL: ${torizon_tar_url}"

    # The loading bar of wget is dynamically rendered using terminal control characters,
    # this breaks the logs. So, disable the loading bar in CI
    if [ "${TCB_UNDER_CI}" = "1" ]; then
        wget --no-verbose -P workdir/images "${torizon_tar_url}"
    else
        wget -P workdir/images "${torizon_tar_url}"
    fi
}

main() {
    prepare
    if ! download; then
        error "Couldn't download Torizon image"
        exit 1
    fi
    touch "${STAMP}"
    echo "Image successfully downloaded."
}

main
