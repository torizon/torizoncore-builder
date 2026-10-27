# Builds the CI image that drives MAGMA (Toradex's labgrid-based hardware-in-the-loop
# lab tool) to provision a real board and flash it, then runs the TCB integration
# tests against it.
#
# Based on magma's own published client image (built by its magma-container-manifest
# CI job), which already has magma-client/teziget-cli on PATH via /opt/venv -- this
# just layers on the Docker CLI and TCB-specific test tooling on top.
ARG CI_REGISTRY
ARG CI_PROJECT_NAMESPACE

FROM ${CI_REGISTRY}/${CI_PROJECT_NAMESPACE}/magma:main

RUN apt-get update && \
    apt-get install -y \
        ca-certificates \
        curl && \
    install -m 0755 -d /etc/apt/keyrings

# Add Docker's official GPG key
RUN curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc && \
    chmod a+r /etc/apt/keyrings/docker.asc

# Add docker GPG keys to APT source
RUN echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
    https://download.docker.com/linux/debian $(. /etc/os-release && echo $VERSION_CODENAME) stable" | \
    tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install docker using apt
RUN apt-get update && \
    apt-get install -y \
        docker-ce \
        docker-ce-cli \
        containerd.io \
        docker-buildx-plugin \
        docker-compose-plugin

# Install dependencies to run TCB integration tests
RUN apt-get update && apt-get install -y \
        sshpass bats git zstd wget bash \
        tar openssl zip bc avahi-utils jq
