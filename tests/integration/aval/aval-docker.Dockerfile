# Uses the AVAL container as a base, which is built in its own repo. From there, it adds
# the docker that is necessary to run the TCB container in the tests, in addition to the
# "sshpass" and "bats" dependencies that are also used in the tests.
FROM gitlab.int.toradex.com:4567/rd/torizon-core-containers/aval/aval:main

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
        tar openssl zip bc avahi-utils
