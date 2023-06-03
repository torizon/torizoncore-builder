#!/bin/bash

set -e

DOCKER_REPO=""

# Reference: https://stackoverflow.com/a/246128/10335947
SCRIPT_DIR=$(cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd)

MAN_BUILDER_NAME="manifest-test-builder"
CUR_BUILDER=""
OLD_BUILDER=""

create-builder() {
    [ -n "${OLD_BUILDER}${CUR_BUILDER}" ] && return 0

    OLD_BUILDER=$(docker buildx ls | sed -ne 's/^\([-_[:alnum:]]\+\)[[:space:]]*\*.*$/\1/p')
    
    if ! docker buildx ls | grep -e "^${MAN_BUILDER_NAME}[[:space:]]*\*" >/dev/null; then
	echo "Creating builder ${MAN_BUILDER_NAME}."
	docker buildx create \
	       --name "${MAN_BUILDER_NAME}" --driver docker-container --bootstrap
    else
	echo "Builder ${MAN_BUILDER_NAME} already exists."
    fi

    CUR_BUILDER="${MAN_BUILDER_NAME}"

    echo "Setting builder ${OLD_BUILDER} -> ${CUR_BUILDER}"
    docker buildx use "${CUR_BUILDER}"
}

delete-builder() {
    [ -z "${OLD_BUILDER}${CUR_BUILDER}" ] && return 0

    if [ -n "${OLD_BUILDER}" ]; then
	echo "Switching builder ${CUR_BUILDER} -> ${OLD_BUILDER}"
	docker buildx use "${OLD_BUILDER}"
    else
	echo "No previous builder."
    fi

    docker buildx rm "${CUR_BUILDER}"
}

ensure() {
    if ! "$@"; then
        echo "Condition failed: $*"
        return 1
    fi
    return 0
}

build-images() {
    local image=""
    local media_type=""

    trap 'echo -e "\nStopping..."; delete-builder;' INT TERM
    create-builder

    ##if false; then
    echo "Generating single-platform (linux/arm/v7) image with a Docker manifest."
    image="${DOCKER_REPO}/manifest-test-armv7-vnddck"
    docker buildx build \
           --file ./manifest-test.Dockerfile \
           --platform linux/arm/v7 \
           --provenance=false \
           --output="type=registry,oci-mediatypes=false" \
           -t "${image}" .
 
    media_type=$(docker buildx imagetools inspect --raw "${image}" | jq -r ".mediaType")
    ensure [ "application/vnd.docker.distribution.manifest.v2+json" = "${media_type}" ]
 
    echo "Generating single-platform (linux/arm/v7) image with an OCI manifest."
    image="${DOCKER_REPO}/manifest-test-armv7-vndoci"
    docker buildx build \
           --file ./manifest-test.Dockerfile \
           --platform linux/arm/v7 \
           --provenance=false \
           --output="type=registry,oci-mediatypes=true" \
           -t "${image}" .
 
    media_type=$(docker buildx imagetools inspect --raw "${image}" | jq -r ".mediaType")
    ensure [ "application/vnd.oci.image.manifest.v1+json" = "${media_type}" ]
    ##fi

    ##if false; then
    echo "Generating single-platform (linux/arm64/v8) image with a Docker manifest."
    image="${DOCKER_REPO}/manifest-test-arm64v8-vnddck"
    docker buildx build \
           --file ./manifest-test.Dockerfile \
           --platform linux/arm64/v8 \
           --provenance=false \
           --output="type=registry,oci-mediatypes=false" \
           -t "${image}" .
 
    media_type=$(docker buildx imagetools inspect --raw "${image}" | jq -r ".mediaType")
    ensure [ "application/vnd.docker.distribution.manifest.v2+json" = "${media_type}" ]
 
    echo "Generating single-platform (linux/arm64/v8) image with an OCI manifest."
    image="${DOCKER_REPO}/manifest-test-arm64v8-vndoci"
    docker buildx build \
           --file ./manifest-test.Dockerfile \
           --platform linux/arm64/v8 \
           --provenance=false \
           --output="type=registry,oci-mediatypes=true" \
           -t "${image}" .
 
    media_type=$(docker buildx imagetools inspect --raw "${image}" | jq -r ".mediaType")
    ensure [ "application/vnd.oci.image.manifest.v1+json" = "${media_type}" ]
    ##fi

    ##if false; then
    echo "Generating multi-platform image with a Docker manifest list."
    image="${DOCKER_REPO}/manifest-test-multi-vnddck-manlst"
    docker buildx build \
           --file ./manifest-test.Dockerfile \
           --platform linux/amd64,linux/arm/v7,linux/arm64/v8 \
           --provenance=false \
           --output="type=registry,oci-mediatypes=false" \
           -t "${image}" .
 
    media_type=$(docker buildx imagetools inspect --raw "${image}" | jq -r ".mediaType")
    ensure [ "${media_type}" = "application/vnd.docker.distribution.manifest.list.v2+json" ]
 
    echo "Generating multi-platform image with an OCI image index."
    image="${DOCKER_REPO}/manifest-test-multi-vndoci-imgidx"
    docker buildx build \
           --file ./manifest-test.Dockerfile \
           --platform linux/amd64,linux/arm/v7,linux/arm64/v8 \
           --provenance=false \
           --output="type=registry,oci-mediatypes=true" \
           -t "${image}" .
 
    media_type=$(docker buildx imagetools inspect --raw "${image}" | jq -r ".mediaType")
    ensure [ "${media_type}" = "application/vnd.oci.image.index.v1+json" ]
    ##fi

    delete-builder
    return 0
}

run() {
    build-images
}

show-usage() {
    local prog
    prog=$(basename "$0")
    cat <<EOF
Usage: ${prog} <target-repo>

Build manifest test images (OCI/non-OCI) and push them to a registry.

<target-repo> is a prefix to be added to all images; it can include a registry and
path/namespace.

Examples:

  # Push images to DockerHub's registry into namespace 'torizon'.
  \$ ${prog} torizon

  # Push images to the internal Docker registry provided by Gitlab.
  \$ ${prog} gitlat.com/my/project/location
EOF
}

# Parse command-line:
for arg in "$@"; do
    case "$arg" in
	-h|--help)
	    show-usage "$@"
	    exit 0
	    ;;
	*)
	    if [ -n "${DOCKER_REPO}" ]; then
		echo "target-repo already specified."
		exit 1
	    fi
	    DOCKER_REPO="$arg"
	    ;;
    esac
done

if [ -z "${DOCKER_REPO}" ]; then
    echo "target-repo must be specified."
    exit 1
fi

echo "Images will be prefixed with \"${DOCKER_REPO}\"."
echo "Running inside directory \"${SCRIPT_DIR}\"."
cd "${SCRIPT_DIR}"
run
echo "Succeded!"
