ARG IMAGE_ARCH=linux/amd64
ARG IMAGE_TAG=bullseye-slim
ARG UPTANE_SIGN_VER=3.2.6

FROM --platform=$IMAGE_ARCH debian:$IMAGE_TAG AS common-base

ARG APT_PROXY

#if argument APT_PROXY is configured, it will be used to speed-up download of deb packages
RUN if [ "$APT_PROXY" != "" ]; then \
    echo "Acquire::http::Proxy \"http://$APT_PROXY:8000\";" > /etc/apt/apt.conf.d/30proxy ;\
    echo "Acquire::http::Proxy::ppa.launchpad.net DIRECT;" >> /etc/apt/apt.conf.d/30proxy ; \
    echo "squid-deb-proxy configured"; \
    else \
    echo "no squid-deb-proxy configured"; \
    fi

# Install runtime dependencies. Install them in the common part in order to refrain
# installing them twice (build-dep would install them too)
# This are all dependencies from the regular Debian OSTree packages except
# AVAHI.
RUN apt-get -q -y update && \
    apt-get -q -y --no-install-recommends install \
            build-essential \
            libarchive13 \
            libassuan0 \
            libfuse2 \
            libglib2.0-0 \
            libgpg-error0 \
            libgpgme11 \
            liblzma5 \
            libmount1 \
            libselinux1 \
            libsoup2.4-1 \
            libssl-dev \
            libsystemd0 \
            zlib1g \
    && \
    rm -rf /var/lib/apt/lists/*

# Build SOTA tools (garage-push/garage-sign)
FROM common-base AS sota-builder

# Enable access to source packages for all feeds.
RUN sed -i '/^deb /{p;s/ /-src /}' /etc/apt/sources.list

RUN apt-get -q -y update && \
    apt-get -q -y --no-install-recommends install \
            ca-certificates \
            git \
    && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /root

# Dependencies according to README.adoc + glibc and file
RUN apt-get -q -y update && \
    apt-get -q -y --no-install-recommends install \
            asn1c \
            build-essential \
            cmake \
            curl \
            file \
            libarchive-dev \
            libboost-dev \
            libboost-log-dev \
            libboost-program-options-dev \
            libcurl4-openssl-dev \
            libglib2.0-dev \
            libostree-dev \
            libpthread-stubs0-dev \
            libsodium-dev \
            libsqlite3-dev \
            python3 \
            python3-requests \
    && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /root

RUN git clone https://github.com/toradex/aktualizr.git && \
    cd aktualizr && \
    git checkout 29a7d4bd073f762d24cb0968b814dcb488a98847 && \
    git submodule update --init --recursive

ARG UPTANE_SIGN_VER

# Get tuf cli
RUN cd aktualizr && \
    curl -L -O https://github.com/uptane/ota-tuf/releases/download/v${UPTANE_SIGN_VER}/cli-${UPTANE_SIGN_VER}.tgz && \
    echo "cf97ea2bda7dd251cb18786b80741ee485ce2104d57329de2a3d8a4a8384f146 cli-${UPTANE_SIGN_VER}.tgz | sha256sum --check"

# Build aktualizr generating an installation tarball
RUN cd aktualizr && \
    echo "tdx-$(date +%Y%m%d)-$(git rev-parse HEAD | cut -c-10)" > VERSION && \
    mkdir build/ && cd build/ && B="$(pwd)" && \
    cmake -DCMAKE_BUILD_TYPE=Release -DBUILD_DEB=ON -DBUILD_SOTA_TOOLS=ON \
          -DGARAGE_SIGN_ARCHIVE=../cli-${UPTANE_SIGN_VER}.tgz \
          -DGARAGE_SIGN_TOOL="uptane-sign" \
          -DSOTA_DEBIAN_PACKAGE_DEPENDS=openjdk-11-jre-headless \
          -DBUILD_OSTREE=ON \
          -DWARNING_AS_ERROR=OFF .. && \
    make -j"$(nproc)" DESTDIR="${B}/install-dir" install && \
    tar cjvf aktualizr.tar.bz2 \
        --show-transformed-names --transform="s,^install-dir,," install-dir/

# Build skopeo
FROM common-base AS skopeo-builder

RUN apt-get -q -y update && \
    apt-get -q -y --no-install-recommends install \
            ca-certificates \
            git \
            wget \
    && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /root

RUN echo "Installing Go..." && \
    wget https://go.dev/dl/go1.24.3.linux-amd64.tar.gz && \
    rm -rf /usr/local/go && \
    tar -C /usr/local -xzf go1.24.3.linux-amd64.tar.gz && \
    rm go1.24.3.linux-amd64.tar.gz

ENV PATH=/usr/local/go/bin:$PATH
ENV GOPATH=/root/go

RUN echo "Installing skopeo build dependencies..." && \
    apt-get -q -y update && \
    apt-get -q -y --no-install-recommends install \
            libassuan-dev \
            libbtrfs-dev \
            libgpgme-dev \
            pkg-config \
    && \
    rm -rf /var/lib/apt/lists/*

RUN echo "Fetching skopeo source code..." && \
    git clone --depth 1 --branch v1.19.0 \
        https://github.com/containers/skopeo ${GOPATH}/src/github.com/containers/skopeo

# hadolint ignore=SC2046
RUN echo "Building skopeo..." && \
    cd ${GOPATH}/src/github.com/containers/skopeo && \
    B="$(pwd)" && D="${B}/install-dir" && \
    make clean && \
    make EXTRA_LDFLAGS="-w -s" bin/skopeo && \
    make EXTRA_LDFLAGS="-w -s" DESTDIR="${D}" DISABLE_DOCS="1" install && \
    tar cjvf /root/skopeo.tar.bz2 -C "${D}" $(cd "${D}" && echo *)

FROM common-base AS tcbuilder-base

RUN apt-get -q -y update && \
    apt-get -q -y --no-install-recommends install \
            acl \
            avahi-daemon \
            bc \
            bison \
            bzip2 \
            cpio \
            cpp \
            curl \
            device-tree-compiler \
            file \
            flex \
            gzip \
            imx-code-signing-tool \
            jq \
            kmod \
            libfaketime \
            libgmp3-dev \
            libgnutls28-dev \
            libguestfs-tools \
            libmpc-dev \
            libpython3.9-dev \
            linux-image-generic \
            lz4 \
            lzop \
            python3 \
            python3-dnspython \
            python3-gi \
            python3-git \
            python3-guestfs \
            python3-ifaddr \
            python3-paramiko \
            python3-pip \
            python3-setuptools \
            python3-wheel \
            swig \
            uuid-dev \
            xxd \
            xz-utils \
            zstd \
    && \
    rm -rf /var/lib/apt/lists/*

    # imx-code-signing-tool: NXP code signing tool needed to sign the bootloader container
    # uuid-dev, libgnutls28-dev: dependency needed when building u-boot 'tools-only' target
    # swig, libpython3.9-dev: dependency needed when building u-boot 'scripts' target
    # xxd: needed for imx8m_sign.sh
    # libfaketime: needed for reproducible builds of signed flash.bin when running the NXP Code Signing Tool

# Copy Avahi files.
COPY avahi-conf/ /etc/avahi/

RUN apt-get -q -y update && \
    apt-get -q -y --no-install-recommends install \
            gir1.2-ostree-1.0 \
            ostree \
            wget \
    && \
    rm -rf /var/lib/apt/lists/*

# Refrain dash from taking over the /bin/sh symlink.
# This allows Python 'subprocess' shell enabled commands to employ bashisms such as pipefail.
RUN apt-get -q -y update && \
    apt-get -q -y --no-install-recommends install \
            bash \
    && \
    rm -rf /var/lib/apt/lists/* && \
    echo 'dash dash/sh boolean false' | debconf-set-selections && \
    DEBIAN_FRONTEND=noninteractive DEBCONF_NONINTERACTIVE_SEEN=true dpkg-reconfigure dash; \
    test "$(realpath /bin/sh)" = '/bin/bash'

# Install java dependencies for uptane
RUN mkdir -p /usr/share/man/man1/ && \
    apt-get -q -y update && \
    apt-get -q -y --no-install-recommends install \
            openjdk-11-jre-headless \
    && \
    rm -rf /var/lib/apt/lists/*

# Install aktualizr from our sota-builder generated tarball
RUN --mount=type=bind,from=sota-builder,source=/root/aktualizr/build,target=/build/aktualizr \
    tar xvf /build/aktualizr/aktualizr.tar.bz2 -C / && ldconfig -v && \
    apt-get -q -y update && \
    apt-get -q -y --no-install-recommends install \
            libboost-log1.74.0 \
            libboost-program-options1.74.0 \
    && \
    rm -rf /var/lib/apt/lists/*

# Install the skopeo tool from our skopeo-builder generated tarball
RUN --mount=type=bind,from=skopeo-builder,source=/root,target=/build/skopeo \
    tar xvf /build/skopeo/skopeo.tar.bz2 -C / && ldconfig -v && \
    apt-get -q -y update && \
    apt-get -q -y --no-install-recommends install \
            libassuan0 \
            libbtrfs0 \
            libgpgme11 \
            pkg-config \
    && \
    rm -rf /var/lib/apt/lists/*

# Debian has old version of docker and docker-compose, which does not support some of
# required functionality like escaping $ in compose file during serialization
COPY requirements_debian.txt /tmp
RUN pip3 install --no-cache-dir -r /tmp/requirements_debian.txt && \
    rm -rf /tmp/requirements_debian.txt

RUN if [ "$APT_PROXY" != "" ]; then rm /etc/apt/apt.conf.d/30proxy; fi

FROM tcbuilder-base AS tcbuilder-dev

COPY requirements_dev.txt /tmp
RUN pip3 install --no-cache-dir -r /tmp/requirements_dev.txt && \
    rm -rf /tmp/requirements_dev.txt

RUN apt-get -q -y update && \
    apt-get -q -y --no-install-recommends install \
            git \
            procps \
            ssh \
            strace \
            vim \
    && \
    rm -rf /var/lib/apt/lists/*

ARG USERNAME=vscode
ARG USER_UID=1000
ARG USER_GID=$USER_UID

# Create the user
RUN groupadd --gid $USER_GID $USERNAME && \
    useradd --uid $USER_UID --gid $USER_GID -m $USERNAME && \
    #
    # [Optional] Add sudo support. Omit if you don't need to install software after connecting.
    apt-get update && \
    apt-get install -y --no-install-recommends \
            sudo \
    && \
    echo $USERNAME ALL=\(root\) NOPASSWD:ALL > /etc/sudoers.d/$USERNAME && \
    chmod 0440 /etc/sudoers.d/$USERNAME

FROM tcbuilder-base

# Build U-Boot tools for secure boot support (U-Boot commit hash: 3f772959501c99fbe5aa0b22a36efe3478d1ae1c)
RUN git clone https://github.com/u-boot/u-boot.git -b v2024.07 /u-boot-repo && \
    cd /u-boot-repo && make tools-only_defconfig && make tools-only && make scripts && \
    mkdir /u-boot && mv /u-boot-repo/tools /u-boot && mv /u-boot-repo/scripts /u-boot && \
    rm -rf /u-boot-repo

# Put all the tools in the /builder directory
RUN mkdir -p /builder
ENV PATH=$PATH:/builder
COPY tezi /builder/tezi/
COPY tcbuilder /builder/tcbuilder/
COPY torizoncore-builder.py /builder/torizoncore-builder

# Workaround for failure when updating device-trees directory with the "dt checkout" command.
RUN git config --global --add safe.directory '/workdir/device-trees'

# Augment version string
ARG VERSION_SUFFIX=""

RUN sed -e 's/^VERSION_SUFFIX *= *["'"'"'].*$/VERSION_SUFFIX = "'"$VERSION_SUFFIX"'"/' \
        -i /builder/torizoncore-builder

WORKDIR /workdir

ENTRYPOINT [ "torizoncore-builder" ]
