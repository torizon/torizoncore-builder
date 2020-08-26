FROM debian:buster-slim AS common-base

ARG APT_PROXY

#if argument APT_PROXY is configured, it will be used to speed-up download of deb packages
RUN if [ "$APT_PROXY" != "" ]; then \
    echo "Acquire::http::Proxy \"http://$APT_PROXY:8000\";" > /etc/apt/apt.conf.d/30proxy ;\
    echo "Acquire::http::Proxy::ppa.launchpad.net DIRECT;" >> /etc/apt/apt.conf.d/30proxy ; \
    echo "squid-deb-proxy configured"; \
    else \
    echo "no squid-deb-proxy configured"; \
    fi

# Enable buster backports to get a newer OSTree version 2019.6
# buster's original OSTree version 2019.1 has a buggy bare repo -> bare repo
# import. We anyway build OSTree ourselfs, but using the backports repo as base
# makes sure we use build dependencies of the correct version.
RUN echo "deb http://deb.debian.org/debian buster-backports main" >> /etc/apt/sources.list

# Install runtime dependencies. Install them in the common part so we can safe
# having to install them twice (build-dep would install them too)
# This are all dependencies from the regular Debian OSTree packages except
# AVAHI.
RUN apt-get -q -y update && apt-get -q -y --no-install-recommends install \
    libarchive13 libassuan0 libfuse2 libglib2.0-0  libgpg-error0  libgpgme11 \
    liblzma5 libmount1 libselinux1 libsoup2.4-1 libsystemd0 zlib1g \
    && rm -rf /var/lib/apt/lists/*

# Build OSTree from source so we can patch it with device tree deployment
# capabilities.
FROM common-base AS ostree-builder

COPY sources.list /etc/apt/sources.list

RUN apt-get -q -y update && apt-get -q -y --no-install-recommends install \
    build-essential git && \
    apt-get -q -y build-dep ostree \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /root

# Clone the same version we have from Debian buster backports
RUN git clone https://github.com/ostreedev/ostree.git && cd ostree && \
    git checkout v2019.6

COPY 0001-deploy-support-devicetree-directory.patch /root/ostree

RUN cd ostree && patch -p1 < 0001-deploy-support-devicetree-directory.patch && \
    ./autogen.sh && ./configure --without-avahi && make && \
    make install DESTDIR=/ostree-build

# Build SOTA tools (garage-push/garage-sign)

# Dependencies according to README.adoc + glibc and file
RUN apt-get -q -y update && apt-get -q -y --no-install-recommends install \
    asn1c build-essential cmake curl libarchive-dev \
    libboost-dev libboost-filesystem-dev libboost-log-dev libboost-program-options-dev \
    libcurl4-openssl-dev libpthread-stubs0-dev libsodium-dev libsqlite3-dev \
    libssl-dev python3 libglib2.0-dev file && \
    apt-get -q -y build-dep ostree \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /root

RUN git clone --recursive https://github.com/advancedtelematic/aktualizr && cd aktualizr && \
    git checkout 2020.8

COPY 0001-Allow-custom-Debian-package-dependencies.patch /root/aktualizr

RUN cd aktualizr && patch -p1 < 0001-Allow-custom-Debian-package-dependencies.patch && \
    mkdir build/ && cd build/ && \
    cmake -DCMAKE_BUILD_TYPE=Release -DBUILD_DEB=ON -DBUILD_SOTA_TOOLS=ON \
          -DSOTA_DEBIAN_PACKAGE_DEPENDS=openjdk-11-jre-headless .. && \
    make package

FROM common-base AS tcbuilder-base

RUN apt-get -q -y update && apt-get -q -y --no-install-recommends install \
    python3 python3-pip python3-setuptools python3-wheel python3-gi \
    curl gzip xz-utils lz4 lzop zstd cpio \
    device-tree-compiler cpp \
    && apt-get -t buster-backports -q -y --no-install-recommends install python3-paramiko \
    python3-dnspython && rm -rf /var/lib/apt/lists/*

# Copy OSTree (including gir support) from build stage
COPY --from=ostree-builder /ostree-build/ /
RUN echo "/usr/local/lib" > /etc/ld.so.conf.d/local.conf && ldconfig
ENV GI_TYPELIB_PATH=/usr/local/lib/girepository-1.0/

# Copy and install SOTA tools from build stage
COPY --from=ostree-builder /root/aktualizr/build/garage_deploy.deb /

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

FROM tcbuilder-base AS tcbuilder-dev

COPY requirements_dev.txt /tmp
RUN pip3 install -r /tmp/requirements_dev.txt \
     && rm -rf /tmp/requirements_dev.txt

RUN apt-get -q -y update && apt-get -q -y --no-install-recommends install \
    git strace procps \
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
ADD tezi /builder/tezi/
ADD tcbuilder /builder/tcbuilder/
ADD dockerbundle.py /builder/
ADD torizoncore-builder.py /builder/torizoncore-builder

WORKDIR /workdir

ENTRYPOINT [ "torizoncore-builder" ]
