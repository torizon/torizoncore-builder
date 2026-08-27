ARG IMAGE_ARCH=linux/amd64
ARG IMAGE_TAG=trixie-slim
ARG UPTANE_SIGN_VER=3.2.6

FROM --platform=$IMAGE_ARCH debian:$IMAGE_TAG AS common-base

ENV DEBIAN_FRONTEND=noninteractive

ARG APT_PROXY

# If argument APT_PROXY is configured, it will be used to speed-up download of deb packages.
RUN if [ "$APT_PROXY" != "" ]; then \
    echo "Acquire::http::Proxy \"http://$APT_PROXY:8000\";" > /etc/apt/apt.conf.d/30proxy ;\
    echo "Acquire::http::Proxy::ppa.launchpad.net DIRECT;" >> /etc/apt/apt.conf.d/30proxy ; \
    echo "squid-deb-proxy configured"; \
    else \
    echo "no squid-deb-proxy configured"; \
    fi


# Build the image used as base for build operations.
FROM common-base AS builder-base

# Enable access to source packages for all feeds.
RUN sed -i '/^deb /{p;s/ /-src /}' /etc/apt/sources.list.d/debian.sources

# Install build tools and development libraries.
#
# Here we keep the packages that are more likely to be reused by multiple "builder"
# container images. This is basically an optimization to avoid downloading and
# installing those packages multiple times when the TorizonCore Builder container
# image.
#
# WARNING: Do not install runtime dependencies here.
#
RUN apt-get -q -y update && \
    apt-get -q -y --no-install-recommends install \
            asn1c \
            build-essential \
            ca-certificates \
            cmake \
            curl \
            file \
            git \
            libarchive-dev \
            libboost-dev \
            libboost-log-dev \
            libboost-program-options-dev \
            libcurl4-openssl-dev \
            libglib2.0-dev \
            libpthread-stubs0-dev \
            libsodium-dev \
            libsqlite3-dev \
            python3 \
            wget \
    && \
    rm -rf /var/lib/apt/lists/*


# Build ostree/libostree from source.
FROM builder-base AS ostree-builder

WORKDIR /root

# Install dependencies except those already present in builder-base.
RUN apt-get -q -y update && \
    apt-get -q -y --no-install-recommends install \
            autoconf \
            automake \
            bison \
            gobject-introspection \
            libgirepository1.0-dev \
            libtool \
            libfuse3-dev \
            libsodium-dev \
    && \
    rm -rf /var/lib/apt/lists/*

# Fetch source code.
RUN git clone -b v2024.5 https://github.com/ostreedev/ostree.git ostree && \
    cd ostree/ && \
    git submodule update --init --recursive

# Build ostree.
RUN cd ostree/ && \
    echo "Configuring ostree..." && \
    env NOCONFIGURE=1 ./autogen.sh && \
    ./configure --prefix=/usr \
                --without-soup \
                --without-gpgme \
                --with-curl \
                --with-ed25519-libsodium && \
    echo "Building ostree..." && \
    make -j"$(nproc)"

# Generate installation tarballs.
RUN cd ostree/ && B="$(pwd)" && \
    rm -fr "${B}/install-dir" && \
    make install DESTDIR="${B}/install-dir" && \
    \
    echo "Building full tarball..." && \
    tar cjvf /root/ostree-full.tar.bz2 \
             --show-transformed-names --transform="s,^install-dir,," install-dir/ && \
    \
    echo "Building stripped down tarball..." && \
    rm -fr install-dir-stripped/ && \
    cp -av install-dir/ install-dir-stripped/ && \
    rm -fr install-dir-stripped/usr/include/ostree-1/ \
           install-dir-stripped/usr/libexec/libostree/grub2-15_ostree \
           install-dir-stripped/usr/etc/grub.d/15_ostree \
    && \
    tar cjvf /root/ostree-stripped.tar.bz2 \
             --show-transformed-names --transform="s,^install-dir-stripped,," install-dir-stripped/


# Build SOTA tools (garage-push/garage-sign).
FROM builder-base AS sota-builder

WORKDIR /root

# Dependencies according to aktualizr/README.adoc except those in builder-base.
RUN --mount=type=bind,from=ostree-builder,source=/root,target=/build/ostree \
    tar xvf /build/ostree/ostree-full.tar.bz2 -C / && ldconfig -v && \
    apt-get -q -y update && \
    apt-get -q -y --no-install-recommends install \
            python3-requests \
    && \
    rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/toradex/aktualizr.git && \
    cd aktualizr && \
    git checkout 29a7d4bd073f762d24cb0968b814dcb488a98847 && \
    git submodule update --init --recursive

ARG UPTANE_SIGN_VER

# Get TUF CLI.
RUN cd aktualizr && \
    curl -L -O https://github.com/uptane/ota-tuf/releases/download/v${UPTANE_SIGN_VER}/cli-${UPTANE_SIGN_VER}.tgz && \
    echo "cf97ea2bda7dd251cb18786b80741ee485ce2104d57329de2a3d8a4a8384f146 cli-${UPTANE_SIGN_VER}.tgz | sha256sum --check"

# Build aktualizr generating an installation tarball.
RUN cd aktualizr && \
    echo "tdx-$(date +%Y%m%d)-$(git rev-parse HEAD | cut -c-10)" > VERSION && \
    mkdir build/ && cd build/ && B="$(pwd)" && \
    cmake -DCMAKE_BUILD_TYPE=Release -DBUILD_DEB=ON -DBUILD_SOTA_TOOLS=ON \
          -DGARAGE_SIGN_ARCHIVE=../cli-${UPTANE_SIGN_VER}.tgz \
          -DGARAGE_SIGN_TOOL="uptane-sign" \
          -DSOTA_DEBIAN_PACKAGE_DEPENDS=openjdk-21-jre-headless \
          -DBUILD_OSTREE=ON \
          -DWARNING_AS_ERROR=OFF .. && \
    make -j"$(nproc)" DESTDIR="${B}/install-dir" install && \
    tar cjvf aktualizr.tar.bz2 \
        --show-transformed-names --transform="s,^install-dir,," install-dir/


# Build Skopeo (tool to manipulate container images).
FROM builder-base AS skopeo-builder

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


# Build U-Boot tools (for Secure Boot support).
FROM builder-base AS uboot-builder

WORKDIR /root

# Install extra packages required when building U-Boot tools:
RUN apt-get -q -y update && \
    apt-get -q -y --no-install-recommends install \
            bison \
            flex \
            libgnutls28-dev \
            libssl-dev \
            python3-dev \
            python3-setuptools \
            swig \
            uuid-dev \
    && \
    rm -rf /var/lib/apt/lists/*

RUN echo "Fetching U-Boot tools repository..." && \
    git clone https://github.com/u-boot/u-boot.git -b v2024.07 u-boot-repo && \
    cd u-boot-repo && \
    \
    echo "Patching libfdt.i_shipped (workaround for newer SWIG)..." && \
    sed -e "s/SWIG_Python_AppendOutput/SWIG_AppendOutput/g" \
        -i scripts/dtc/pylibfdt/libfdt.i_shipped && \
    make tools-only_defconfig && \
    \
    echo "Building U-Boot tools / tools-only..." && \
    make tools-only && \
    \
    echo "Building U-Boot tools / scripts..." && \
    make scripts && \
    \
    cd - && \
    echo "Prepare output tarball..." && \
    mkdir u-boot && \
    mv u-boot-repo/tools u-boot/ && \
    mv u-boot-repo/scripts u-boot/ && \
    find u-boot/ -type f -regex ".*\\.\([cho]\|cmd\)" -exec rm -f '{}' \; && \
    rm -rf /u-boot-repo && \
    tar cjvf u-boot-tools.tar.bz2 u-boot/
    # Output available at /root/u-boot-tools.tar.bz2


# Build the base image for TorizonCore Builder.
FROM common-base AS tcbuilder-base

# Install Bash to allow the use of Bashisms in scripts invoked by TorizonCore Builder.
RUN apt-get -q -y update && \
    apt-get -q -y --no-install-recommends install \
            bash \
    && \
    rm -rf /var/lib/apt/lists/*

# Install runtime dependencies of TorizonCore Builder.
#
# - imx-code-signing-tool: NXP code signing tool needed to sign the bootloader container.
# - xxd: needed by imx8m_sign.sh.
# - libfaketime: needed for reproducible builds of signed flash.bin when running the NXP
#   Code Signing Tool.
#
# NOTE: Do not add -dev packages here since they are not supposed to be runtime
#       dependencies of TorizonCore Builder.
#
RUN apt-get -q -y update && \
    apt-get -q -y --no-install-recommends install \
            acl \
            avahi-daemon \
            bzip2 \
            cpio \
            cpp \
            curl \
            device-tree-compiler \
            file \
            gzip \
            imx-code-signing-tool \
            jq \
            libfaketime \
            libguestfs-tools \
            lz4 \
            lzop \
            python3 \
            python3-dnspython \
            python3-gi \
            python3-git \
            python3-guestfs \
            python3-ifaddr \
            python3-libfdt \
            python3-paramiko \
            python3-pip \
            python3-setuptools \
            python3-wheel \
            wget \
            xxd \
            xz-utils \
            zstd \
    && \
    rm -rf /var/lib/apt/lists/*

# Copy Avahi files.
COPY avahi-conf/ /etc/avahi/

# TODO: Consider using jlink to create a smaller runtime to run uptane-sign.
# Install java dependencies for uptane.
RUN mkdir -p /usr/share/man/man1/ && \
    apt-get -q -y update && \
    apt-get -q -y --no-install-recommends install \
            openjdk-21-jre-headless \
    && \
    rm -rf /var/lib/apt/lists/*

# Install libostree from our ostree-builder generated tarball.
RUN --mount=type=bind,from=ostree-builder,source=/root,target=/build/ostree \
    tar xvf /build/ostree/ostree-stripped.tar.bz2 -C / && ldconfig -v && \
    apt-get -q -y update && \
    apt-get -q -y --no-install-recommends install \
            libarchive13 \
            libfuse3-4 \
            libsodium23 \
    && \
    rm -rf /var/lib/apt/lists/*

# Install aktualizr from our sota-builder generated tarball.
RUN --mount=type=bind,from=sota-builder,source=/root/aktualizr/build,target=/build/aktualizr \
    tar xvf /build/aktualizr/aktualizr.tar.bz2 -C / && ldconfig -v && \
    apt-get -q -y update && \
    apt-get -q -y --no-install-recommends install \
            libboost-log1.83.0 \
            libboost-program-options1.83.0 \
    && \
    rm -rf /var/lib/apt/lists/*

# Install the skopeo tool from our skopeo-builder generated tarball.
RUN --mount=type=bind,from=skopeo-builder,source=/root,target=/build/skopeo \
    tar xvf /build/skopeo/skopeo.tar.bz2 -C / && ldconfig -v && \
    apt-get -q -y update && \
    apt-get -q -y --no-install-recommends install \
            libassuan9 \
            libbtrfs0 \
            libgpgme11 \
            pkg-config \
    && \
    rm -rf /var/lib/apt/lists/*

# Install the u-boot-tools from our uboot-builder generated tarball.
RUN --mount=type=bind,from=uboot-builder,source=/root,target=/build/uboot \
    tar xvf /build/uboot/u-boot-tools.tar.bz2 -C /

# Install Python requirements via pip; all of them are available as wheels, so no
# compiler or Python development files are needed here.
#
# TODO: Consider using a virtual environment to avoid system-wide installations.
#
COPY requirements_debian.txt /tmp
RUN echo "Installing Debian requirements (Python code dependencies)..." && \
    pip3 install --no-cache-dir --break-system-packages -r /tmp/requirements_debian.txt && \
    rm -rf /tmp/requirements_debian.txt

# Install extra development dependencies related to "kernel build_module"; notice
# that these are not dependencies of TorizonCore Builder itself but are needed
# indirectly when invoking the kernel build system to build out-of-tree modules.
#
# - libgmp3-dev, libssl-dev: needed by the kernel/toolchain used in TOS6
# - linux-image-generic: needed by libguestfs (handling WIC images)
#
# TODO: Consider moving these dependencies in a separate container and invoke it.
#
RUN echo "Installing 'kernel build_module' (dev) dependencies" && \
    apt-get -q -y update && \
    apt-get -q -y --no-install-recommends install \
            bc \
            bison \
            build-essential \
            flex \
            kmod \
            libelf-dev \
            libgmp3-dev \
            libssl-dev \
            libmpc-dev \
            linux-image-generic \
    && \
    rm -rf /var/lib/apt/lists/*

RUN if [ "$APT_PROXY" != "" ]; then rm /etc/apt/apt.conf.d/30proxy; fi


# Build the development image (used mainly by TorizonCore Builder developers).
FROM tcbuilder-base AS tcbuilder-dev

COPY requirements_dev.txt /tmp
RUN echo "Installing Debian requirements for dev container..." && \
    pip3 install --no-cache-dir --break-system-packages -r /tmp/requirements_dev.txt && \
    rm -rf /tmp/requirements_dev.txt

RUN apt-get -q -y update && \
    apt-get -q -y --no-install-recommends install \
            git \
            nano \
            procps \
            ssh \
            strace \
            vim \
    && \
    rm -rf /var/lib/apt/lists/*

# hadolint ignore=DL3064
ARG USERNAME=vscode
ARG USER_UID=1000
ARG USER_GID=$USER_UID

# Create the user
RUN groupadd --gid $USER_GID $USERNAME && \
    useradd --uid $USER_UID --gid $USER_GID -m $USERNAME && \
    #
    # [Optional] Add sudo support. Omit if you don't need to install software after connecting.
    apt-get -q -y update && \
    apt-get -q -y --no-install-recommends install \
            sudo \
    && \
    echo $USERNAME ALL=\(root\) NOPASSWD:ALL > /etc/sudoers.d/$USERNAME && \
    chmod 0440 /etc/sudoers.d/$USERNAME


# Build the actual TorizonCore Builder image.
FROM tcbuilder-base

# Put all the tools in the /builder directory
RUN mkdir -p /builder
ENV PATH=$PATH:/builder
COPY tezi /builder/tezi/
COPY tcbuilder /builder/tcbuilder/
COPY torizoncore-builder.py /builder/torizoncore-builder

# Store completion script in the image so the setup script can extract/source it
COPY torizoncore-builder-completion.bash /opt/torizoncore-builder/completion-scripts/

# Workaround for failure when updating device-trees directory with the "dt checkout" command.
RUN git config --global --add safe.directory '/workdir/device-trees'

# Augment version string
ARG VERSION_SUFFIX=""

RUN sed -e 's/^VERSION_SUFFIX *= *["'"'"'].*$/VERSION_SUFFIX = "'"$VERSION_SUFFIX"'"/' \
        -i /builder/torizoncore-builder

WORKDIR /workdir

ENTRYPOINT [ "torizoncore-builder" ]
