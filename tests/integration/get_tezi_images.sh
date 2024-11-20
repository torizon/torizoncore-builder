#!/bin/bash

# images to be downloaded
# format is MACHINE:DISTRO:IMAGE
IMAGES="\
colibri-imx6:torizon-upstream:torizon-docker \
colibri-imx6ull-emmc:torizon-upstream:torizon-docker \
colibri-imx7-emmc:torizon-upstream:torizon-docker \
colibri-imx8x:torizon:torizon-docker \
apalis-imx6:torizon-upstream:torizon-docker \
verdin-imx8mm:torizon:torizon-docker \
verdin-imx8mp:torizon:torizon-docker \
verdin-am62:torizon:torizon-docker \
"

# location to save images
OUTDIR="$PWD/workdir/images"
TMPDIR="$OUTDIR/tmp"
STAMP="$OUTDIR/.images_downloaded"

# branch
BRANCH="scarthgap-7.x.y"

# CONFIGME: version
TCVERSION="7.0.0"

# CONFIGME: build number
BUILD_NUMBER="1"
BUILD_DATE="20210315"

# CONFIGME: uncomment for nightly images
#BUILD_RELEASE="prerelease"
#BUILD_TYPE="nightly"
#VERSION="${TCVERSION}-devel-${BUILD_DATE}+build.${BUILD_NUMBER}"

# CONFIGME: uncomment for monthly images
#BUILD_RELEASE="prerelease"
#BUILD_TYPE="monthly"
#VERSION="${TCVERSION}-devel-${BUILD_DATE}+build.${BUILD_NUMBER}"

# CONFIGME: uncomment for quarterly images
BUILD_RELEASE="prod"
BUILD_TYPE="release"
VERSION="${TCVERSION}+build.${BUILD_NUMBER}"

prepare() {
    mkdir -p $OUTDIR
    rm -Rf $TMPDIR $STAMP
}

cleanup() {
    rm -Rf $TMPDIR
}

download_tezi_image() {
    OE_MACHINE=$1
    OE_DISTRO=$2
    OE_IMAGE=$3

    IMAGE_FILE="${OE_IMAGE}-${OE_MACHINE}-Tezi_${VERSION}${CONTAINER}.tar"
    LINK="https://artifacts.toradex.com/artifactory/torizoncore-oe-${BUILD_RELEASE}-frankfurt/${BRANCH}/${BUILD_TYPE}/${BUILD_NUMBER}/${OE_MACHINE}/${OE_DISTRO}/${OE_IMAGE}/oedeploy/${IMAGE_FILE}"

    if [ -e $OUTDIR/$IMAGE_FILE ]; then
        echo "Image file $IMAGE_FILE already downloaded. Skiping."
    else
        echo "Downloading $IMAGE_FILE..."
        if ! wget --no-verbose -P $TMPDIR $LINK; then
            echo "Error: could not download $IMAGE_FILE."
            exit 1
        fi
        mv $TMPDIR/$IMAGE_FILE $OUTDIR/
        echo ""
    fi
}

download() {
    for image in $IMAGES; do
        MACHINE=$(echo $image | cut -d':' -f 1)
        DISTRO=$(echo $image | cut -d':' -f 2)
        IMAGE=$(echo $image | cut -d':' -f 3)
        download_tezi_image $MACHINE $DISTRO $IMAGE
    done

    touch $STAMP
    echo "All images successfully downloaded."
}

main() {
    prepare
    download
    cleanup
}

main
