#!/bin/bash

# images to be downloaded
# format is MACHINE:IMAGE
IMAGES="\
intel-corei7-64:torizon-core-common-docker-dev \
qemux86-64:torizon-core-common-docker-dev \
"

# location to save images
OUTDIR="$PWD/workdir/images"
TMPDIR="$OUTDIR/tmp"
STAMP="$OUTDIR/.wic_images_downloaded"

# CONFIGME: version
TCVERSION="6.6.0-common"

prepare() {
    mkdir -p $OUTDIR
    rm -Rf $TMPDIR $STAMP
}

cleanup() {
    rm -Rf $TMPDIR
}

download_wic_image() {
    OE_MACHINE=$1
    OE_IMAGE=$2

    IMAGE_FILE="${OE_IMAGE}-v${TCVERSION}-${OE_MACHINE}.zip"

    LINK="https://github.com/commontorizon/meta-common-torizon/releases/download/v${TCVERSION}/${IMAGE_FILE}"

    if [ -e $OUTDIR/$IMAGE_FILE ]; then
        echo "Image file $IMAGE_FILE already downloaded. Skiping."
    else
        echo "Downloading $IMAGE_FILE..."
        if ! wget --no-verbose --show-progress -P $TMPDIR $LINK; then
            echo "Error: could not download $IMAGE_FILE."
            exit 1
        fi
        echo ""
    fi
}

extract() {

    unzip $TMPDIR/'*.zip' -d $TMPDIR
    mv $TMPDIR/*.wic $OUTDIR/

    touch $STAMP
    echo "All images successfully downloaded."
}

download() {
    for image in $IMAGES; do
        MACHINE=$(echo $image | cut -d':' -f 1)
        IMAGE=$(echo $image | cut -d':' -f 2)
        download_wic_image $MACHINE $IMAGE
    done
}

main() {
    prepare
    download
    extract
    cleanup
}

main
