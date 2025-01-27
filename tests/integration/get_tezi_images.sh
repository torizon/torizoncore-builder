#!/bin/sh

# location to save images
OUTDIR="$PWD/workdir/images"
STAMP="$OUTDIR/.images_downloaded"

prepare() {
    rm -rf workdir/images
    mkdir -p "$OUTDIR"
}

download() {
    if [ "$TARGET_BUILD_TYPE" = "release" ]; then
        artifactory_url="https://artifacts.toradex.com/artifactory/torizoncore-oe-prod-frankfurt/$YOCTO_BRANCH/$TARGET_BUILD_TYPE"
    elif [ "$TARGET_BUILD_TYPE" = "nightly" ]; then
        artifactory_url="https://artifacts.toradex.com/artifactory/torizoncore-oe-prerelease-frankfurt/$YOCTO_BRANCH/$TARGET_BUILD_TYPE"
    else
        echo "ERROR: Invalid TARGET_BUILD_TYPE. Expected 'nightly' or 'release'."
        exit 1
    fi

    # Step 1: Catch all build numbers for a specific machine, in descending order
    build_numbers=$(wget -qO- "$artifactory_url" | grep -o '<a href="[0-9]*/"' |
                    sed -e 's#<a href="##' -e 's#/"##' | sort -nr)

    # Step 2: Find the highest build number for $TCB_MACHINE
    for build in $build_numbers; do
        machine_url="${artifactory_url}/${build}/${TCB_MACHINE}/"

        # Checks if machine exists in current build
        if wget --spider -q "$machine_url"; then
            latest_build=$build
            break  # Exit the loop when it finds the first valid build
        fi
    done

    if [ -z "$latest_build" ]; then
        echo "ERROR: No image found for $TCB_MACHINE."
        exit 1
    fi

    torizon_tar_url="${artifactory_url}/${latest_build}/${TCB_MACHINE}"

    # 'torizon' or 'torizon-upstream'
    upstream_variant=$(wget -qO- "$torizon_tar_url" | grep '<a href="torizon' |
                        sed -n 's#.*<a href="\([^"/]*\)/".*#\1#p' |
                        grep -E '^(torizon|torizon-upstream)$' | head -n1)
    torizon_tar_url="$torizon_tar_url/$upstream_variant"

    # 'torizon-docker' or 'torizon-core-docker'
    docker_type=$(wget -qO- "$torizon_tar_url" | grep '<a href="torizon' |
                    grep 'docker/' | sed -n 's#.*<a href="\([^"/]*\)/".*#\1#p' |
                    tail -n1)
    torizon_tar_url="$torizon_tar_url/$docker_type/oedeploy"

    # Find Torizon .tar image
    filename=$(wget -qO- "$torizon_tar_url" | grep '<a href="' |
                sed -n 's#.*<a href="\([^"]*-Tezi_[^"]*\.tar\)".*#\1#p' |
                sort -r | head -n1)
    torizon_tar_url="$torizon_tar_url/$filename"

    wget --no-verbose -P workdir/images "$torizon_tar_url"
}

main() {
    prepare
    download
    if [ $? -ne 0 ]; then
        echo "ERROR: Couldn't download Torizon image"
        exit 1
    fi
    touch "$STAMP"
    echo "Image successfully downloaded."
}

main
