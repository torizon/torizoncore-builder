ARG IMAGE_ARCH=linux/amd64
ARG IMAGE_TAG=bullseye-slim
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
RUN apt-get -q -y update && apt-get -q -y --no-install-recommends install \
    libarchive13 libassuan0 libfuse2 libglib2.0-0  libgpg-error0  libgpgme11 \
    liblzma5 libmount1 libselinux1 libsoup2.4-1 libsystemd0 zlib1g  build-essential \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Build SOTA tools (garage-push/garage-sign)
FROM common-base AS sota-builder

# Enable access to source packages for all feeds.
RUN sed -i '/^deb /{p;s/ /-src /}' /etc/apt/sources.list

RUN apt-get -q -y update && apt-get -q -y --no-install-recommends install \
    git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /root

# Dependencies according to README.adoc + glibc and file
RUN apt-get -q -y update && apt-get -q -y --no-install-recommends install \
    asn1c build-essential cmake curl libarchive-dev \
    libboost-dev libboost-log-dev libboost-program-options-dev \
    libcurl4-openssl-dev libpthread-stubs0-dev libsodium-dev libsqlite3-dev \
    python3 libglib2.0-dev file \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /root

RUN git clone --recursive https://github.com/advancedtelematic/aktualizr && cd aktualizr && \
    git checkout 2020.9

RUN cd aktualizr && mkdir build/ && cd build/ && \
    cmake -DCMAKE_BUILD_TYPE=Release -DBUILD_DEB=ON -DBUILD_SOTA_TOOLS=ON \
          -DSOTA_DEBIAN_PACKAGE_DEPENDS=openjdk-11-jre-headless \
          -DWARNING_AS_ERROR=OFF .. && \
    make -j$(nproc) package

FROM common-base AS tcbuilder-base

RUN apt-get -q -y update && apt-get -q -y --no-install-recommends install \
    python3 python3-pip python3-setuptools python3-wheel python3-gi \
    file curl gzip xz-utils lz4 lzop zstd cpio jq \
    device-tree-compiler cpp  bzip2 flex bison kmod wget \
    && apt-get -q -y --no-install-recommends install python3-paramiko \
    python3-dnspython python3-ifaddr python3-git && rm -rf /var/lib/apt/lists/*

RUN apt-get -q -y update && apt-get -q -y --no-install-recommends install \
    ostree \
    gir1.2-ostree-1.0 \
    && rm -rf /var/lib/apt/lists/*

# Refrain dash from taking over the /bin/sh symlink.
# This allows Python 'subprocess' shell enabled commands to employ bashisms such as pipefail.
RUN apt-get -q -y update && apt-get -q -y --no-install-recommends install bash \
    && echo 'dash dash/sh boolean false' | debconf-set-selections \
    && DEBIAN_FRONTEND=noninteractive DEBCONF_NONINTERACTIVE_SEEN=true dpkg-reconfigure dash \
    ; test $(realpath /bin/sh) = '/bin/bash'

# Copy and install SOTA tools from build stage
COPY --from=sota-builder /root/aktualizr/build/garage_deploy.deb /

# Try to install garage deploy, and then use apt-get to install actual dependencies
# (the mkdir -p /usr/share/man/man1 is required to make JRE installation happy)
RUN apt-get -q -y update && ls && pwd \
    && mkdir -p /usr/share/man/man1 \
    && dpkg -i ./garage_deploy.deb || apt-get -q -y --fix-broken --no-install-recommends install \
    && rm ./garage_deploy.deb \
    && rm -rf /var/lib/apt/lists/*

# Debian has old version of docker and docker-compose, which does not support some of
# required functionality like escaping $ in compose file during serialization
COPY requirements_debian.txt /tmp
RUN pip3 install -r /tmp/requirements_debian.txt \
     && rm -rf /tmp/requirements_debian.txt

RUN if [ "$APT_PROXY" != "" ]; then rm /etc/apt/apt.conf.d/30proxy; fi

# Get Linaro toolchains
RUN wget -O gcc-arm-9.2-2019.12-x86_64-arm-none-linux-gnueabihf.tar.xz "http://artifactory-horw.int.toradex.com/artifactory/list/torizoncore-oe-dev-horw/gcc-arm/gcc-arm-9.2-2019.12-x86_64-arm-none-linux-gnueabihf.tar.xz"
RUN wget -O gcc-arm-9.2-2019.12-x86_64-aarch64-none-linux-gnu.tar.xz "http://artifactory-horw.int.toradex.com/artifactory/list/torizoncore-oe-dev-horw/gcc-arm/gcc-arm-9.2-2019.12-x86_64-aarch64-none-linux-gnu.tar.xz"
RUN tar xf gcc-arm-9.2-2019.12-x86_64-arm-none-linux-gnueabihf.tar.xz
RUN tar xf gcc-arm-9.2-2019.12-x86_64-aarch64-none-linux-gnu.tar.xz

FROM tcbuilder-base AS tcbuilder-dev

COPY requirements_dev.txt /tmp
RUN pip3 install -r /tmp/requirements_dev.txt \
     && rm -rf /tmp/requirements_dev.txt

RUN apt-get -q -y update && apt-get -q -y --no-install-recommends install \
    git strace procps vim ssh\
    && rm -rf /var/lib/apt/lists/*

ARG USERNAME=vscode
ARG USER_UID=1000
ARG USER_GID=$USER_UID

# Create the user
RUN groupadd --gid $USER_GID $USERNAME \
    && useradd --uid $USER_UID --gid $USER_GID -m $USERNAME \
    #
    # [Optional] Add sudo support. Omit if you don't need to install software after connecting.
    && apt-get update \
    && apt-get install -y sudo \
    && echo $USERNAME ALL=\(root\) NOPASSWD:ALL > /etc/sudoers.d/$USERNAME \
    && chmod 0440 /etc/sudoers.d/$USERNAME

FROM tcbuilder-base

# put all the tools in the /builder directory 
RUN mkdir -p /builder
ENV PATH=$PATH:/builder
COPY --from=tcbuilder-base gcc-arm-9.2-2019.12-x86_64-arm-none-linux-gnueabihf /builder/gcc-arm-9.2-2019.12-x86_64-arm-none-linux-gnueabihf
COPY --from=tcbuilder-base gcc-arm-9.2-2019.12-x86_64-aarch64-none-linux-gnu /builder/gcc-arm-9.2-2019.12-x86_64-aarch64-none-linux-gnu
ADD tezi /builder/tezi/
ADD tcbuilder /builder/tcbuilder/
ADD dockerbundle.py /builder/
ADD torizoncore-builder.py /builder/torizoncore-builder

WORKDIR /workdir

ENTRYPOINT [ "torizoncore-builder" ]
