FROM debian:buster-slim

ARG APT_PROXY

#if argument APT_PROXY is configured, it will be used to speed-up download of deb packages
RUN if [ "$APT_PROXY" != "" ]; then \
    echo "Acquire::http::Proxy \"http://$APT_PROXY:8000\";" > /etc/apt/apt.conf.d/30proxy ;\
    echo "Acquire::http::Proxy::ppa.launchpad.net DIRECT;" >> /etc/apt/apt.conf.d/30proxy ; \
    echo "squid-deb-proxy configured"; \
    else \
    echo "no squid-deb-proxy configured"; \
    fi

RUN apt-get -q -y update && apt-get -q -y --no-install-recommends install \
    ostree python3 python3-pip python3-gi \
    python3-docker docker-compose curl \
    gir1.2-ostree-1.0 python3-paramiko \
    gzip xz-utils lzop zstd \
    &&  rm -rf /var/lib/apt/lists/*

RUN if [ "$APT_PROXY" != "" ]; then rm /etc/apt/apt.conf.d/30proxy; fi

# put all the tools in the /builder directory 
RUN mkdir -p /builder
ENV PATH=$PATH:/builder
ADD tezi /builder/tezi/
ADD tcbuilder /builder/tcbuilder/
ADD dockerbundle.py /builder/
ADD torizoncore-builder.py /builder/torizoncore-builder

WORKDIR /workdir

ENTRYPOINT [ "torizoncore-builder" ]
