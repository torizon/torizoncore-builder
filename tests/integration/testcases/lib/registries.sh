#! /bin/bash

# SR stands for Secure Registry
export SR_NO_AUTH="secure-registry-no-auth"
export SR_NO_AUTH_IP="172.20.0.2"
export SR_NO_AUTH_CERTS="secure_registry_no_auth"

export SR_WITH_AUTH="secure-registry-with-auth"
export SR_WITH_AUTH_IP="172.20.0.3:444"
export SR_WITH_AUTH_CERTS="secure_registry_with_auth"

export INSEC_REG="insecure-registry"
export INSEC_REG_IP="172.20.0.4:9180"

export DIND_CONTAINER="dind-for-registries"

export REGISTRIES_NETWORK="registry-network"


_start-registries() {
    local if_ci="" && [ "${TCB_UNDER_CI}" = "1" ] && if_ci="1"
    # Create the network as the first step so that if it fails we consider there is something
    # already running from a previous execution and that should be cleaned up first.
    echo "== Creating network ${REGISTRIES_NETWORK} =="
    if ! docker network create --subnet=172.20.0.0/16 "${REGISTRIES_NETWORK}"; then
	echo "Could not create registries network; maybe it's already present."
	return 1
    fi

    # Create the folders.
    mkdir -p "${SR_NO_AUTH_CERTS}" "${SR_WITH_AUTH_CERTS}" "${SR_WITH_AUTH_CERTS}/auth"

    echo "== Generating credentials =="
    docker run \
      --rm --entrypoint htpasswd \
      httpd:2 -Bbn toradex test > "${SR_WITH_AUTH_CERTS}/auth/htpasswd"

    echo "== Generating certificates =="
    openssl req \
	-newkey rsa:4096 -nodes -sha256 -keyout "${SR_NO_AUTH_CERTS}/server.key" \
	-subj "/C=AU/ST=./L=./O=./CN=myregistry.domain.com" \
	-addext "subjectAltName = DNS:myregistry.domain.com, IP:${SR_NO_AUTH_IP}" \
	-x509 -days 365 -out "${SR_NO_AUTH_CERTS}/cacert.crt"

    openssl req \
	-newkey rsa:4096 -nodes -sha256 -keyout "${SR_WITH_AUTH_CERTS}/server.key" \
	-subj "/C=AU/ST=./L=./O=./CN=myregistry.domain.com" \
	-addext "subjectAltName = DNS:myregistry.domain.com, IP:${SR_WITH_AUTH_IP%%:*}" \
	-x509 -days 365 -out "${SR_WITH_AUTH_CERTS}/cacert.crt"

    echo "== Creating secure registries =="
    docker run \
        -d --restart=always --name "${SR_NO_AUTH}" \
        -v "$(pwd)/${SR_NO_AUTH_CERTS}:/certs" \
        -e "REGISTRY_HTTP_ADDR=0.0.0.0:443" \
        -e "REGISTRY_HTTP_TLS_CERTIFICATE=/certs/cacert.crt" \
        -e "REGISTRY_HTTP_TLS_KEY=/certs/server.key" \
        -p 443:443 \
        --net "${REGISTRIES_NETWORK}" \
        --ip "${SR_NO_AUTH_IP}" \
        registry:2

    docker run \
	-d --restart=always --name "${SR_WITH_AUTH}" \
	-v "$(pwd)/${SR_WITH_AUTH_CERTS}:/certs" \
	-e "REGISTRY_HTTP_ADDR=0.0.0.0:444" \
	-e "REGISTRY_HTTP_TLS_CERTIFICATE=/certs/cacert.crt" \
	-e "REGISTRY_HTTP_TLS_KEY=/certs/server.key" \
	-e "REGISTRY_AUTH=htpasswd" \
	-e "REGISTRY_AUTH_HTPASSWD_REALM=Registry Realm" \
	-e "REGISTRY_AUTH_HTPASSWD_PATH=/certs/auth/htpasswd" \
	-p 444:444 \
	--net "${REGISTRIES_NETWORK}" \
	--ip "${SR_WITH_AUTH_IP%%:*}" \
	registry:2

    echo "== Creating insecure registry =="
    docker run \
        -d --restart=always --name "${INSEC_REG}" \
	-e "REGISTRY_HTTP_ADDR=0.0.0.0:9180" \
        -p 9180:9180 \
	--net "${REGISTRIES_NETWORK}" \
	--ip "${INSEC_REG_IP%%:*}" \
	registry:2

    # Create the Docker DinD container used to populate the registries.
    echo "== Creating auxiliary DinD container =="
    if [ -n "$(docker container ls -qaf name="^${DIND_CONTAINER}\$")" ]; then
        docker container rm -f "${DIND_CONTAINER}"
    fi
    docker run \
        -d --name "${DIND_CONTAINER}" --privileged --network host \
        -v "$(pwd):/certs" -e DOCKER_HOST="tcp://127.0.0.1:23736" \
	docker:19.03.8-dind dockerd \
	--host=tcp://0.0.0.0:23736 --insecure-registry="${INSEC_REG_IP}"

    # Add the CA certificates to DinD.
    docker exec "${DIND_CONTAINER}" /bin/ash -c "\
	mkdir -p /etc/docker/certs.d/${SR_NO_AUTH_IP} /etc/docker/certs.d/${SR_WITH_AUTH_IP} && \
	cp /certs/${SR_NO_AUTH_CERTS}/cacert.crt /etc/docker/certs.d/${SR_NO_AUTH_IP}/cacert.crt && \
	cp /certs/${SR_WITH_AUTH_CERTS}/cacert.crt /etc/docker/certs.d/${SR_WITH_AUTH_IP}/cacert.crt"

    echo "== Populating registries =="
    local TGT_IMAGES="
	${SR_NO_AUTH_IP}/test1
	${SR_NO_AUTH_IP}/test2
	${SR_NO_AUTH_IP}/test1:dummy-tag
	${SR_NO_AUTH_IP}/test2:dummy-tag
	${SR_WITH_AUTH_IP}/test1
	${SR_WITH_AUTH_IP}/test2
	${SR_WITH_AUTH_IP}/test1:dummy-tag
	${SR_WITH_AUTH_IP}/test2:dummy-tag
	${INSEC_REG_IP}/test1
	${INSEC_REG_IP}/test2
	${INSEC_REG_IP}/test1:dummy-tag
	${INSEC_REG_IP}/test2:dummy-tag

	${SR_NO_AUTH_IP}/levelone/test1
	${SR_NO_AUTH_IP}/levelone/test2
	${SR_NO_AUTH_IP}/levelone/test1:dummy-tag
	${SR_NO_AUTH_IP}/levelone/test2:dummy-tag
	${SR_WITH_AUTH_IP}/levelone/test1
	${SR_WITH_AUTH_IP}/levelone/test2
	${SR_WITH_AUTH_IP}/levelone/test1:dummy-tag
	${SR_WITH_AUTH_IP}/levelone/test2:dummy-tag
	${INSEC_REG_IP}/levelone/test1
	${INSEC_REG_IP}/levelone/test2
	${INSEC_REG_IP}/levelone/test1:dummy-tag
	${INSEC_REG_IP}/levelone/test2:dummy-tag

	${SR_NO_AUTH_IP}/levelone/leveltwo/test1
	${SR_NO_AUTH_IP}/levelone/leveltwo/test2
	${SR_NO_AUTH_IP}/levelone/leveltwo/test1:dummy-tag
	${SR_NO_AUTH_IP}/levelone/leveltwo/test2:dummy-tag
	${SR_WITH_AUTH_IP}/levelone/leveltwo/test1
	${SR_WITH_AUTH_IP}/levelone/leveltwo/test2
	${SR_WITH_AUTH_IP}/levelone/leveltwo/test1:dummy-tag
	${SR_WITH_AUTH_IP}/levelone/leveltwo/test2:dummy-tag
	${INSEC_REG_IP}/levelone/leveltwo/test1
	${INSEC_REG_IP}/levelone/leveltwo/test2
	${INSEC_REG_IP}/levelone/leveltwo/test1:dummy-tag
	${INSEC_REG_IP}/levelone/leveltwo/test2:dummy-tag
    "

    # The digest here must be for the manifest, NOT for the manifest list.
    local SRC_IMAGE="hello-world@sha256:f54a58bc1aac5ea1a25d796ae155dc228b3f0e11d046ae276b39c4bf2f13d8c4"

    docker exec "${DIND_CONTAINER}" /bin/ash -c "\
	docker login -u toradex -p test ${SR_WITH_AUTH_IP} && \
	${if_ci:+docker login -u "${CI_DOCKER_HUB_PULL_USER}" -p "${CI_DOCKER_HUB_PULL_PASSWORD}" && } \
	docker pull ${SRC_IMAGE} && \
        err=0 &&
	for image in $(echo ${TGT_IMAGES}); do \
            echo \"** Tagging \$image.\"; \
	    if ! docker tag ${SRC_IMAGE} \${image}; then \
                err=1; \
                break; \
            fi; \
        done; \
        [ \$err -eq 0 ] && \
	for image in $(echo ${TGT_IMAGES}); do \
            echo \"** Pushing \$image to registry.\"; \
	    if ! docker push \${image}; then \
                err=1; \
                break; \
            fi; \
        done; \
        [ \$err -eq 0 ]"
}

start-registries() {
    (set -eo pipefail; _start-registries "$@")
}

_check-registries() {
    local CONTAINERS=("${SR_NO_AUTH}" "${SR_WITH_AUTH}" "${INSEC_REG}")
    local REGISTRIES=("${SR_NO_AUTH_IP}" "${SR_WITH_AUTH_IP}" "${INSEC_REG_IP}")

    # Check if the containers IP address are correct.
    for ((i=0; i < ${#CONTAINERS[@]}; i++)); do
	local expect="${REGISTRIES[i]%%:*}"
	local actual=$(docker inspect -f '{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}' \
                       $(docker container ls -qf name="${CONTAINERS[i]}$"))
	if [ "${expect}" != "${actual}" ]; then
	    echo "Container ${CONTAINERS[i]} IP ${actual} does not match expected IP ${expect}"
	    return 1
	fi
    done
}

check-registries() {
    _check-registries "$@"
}

_stop-registries() {
    # Removing existing containers and networks.
    if [ -n "$(docker container ls -qaf name="^${DIND_CONTAINER}\$")" ]; then
        docker container rm -f "${DIND_CONTAINER}"
    fi

    if [ -n "$(docker container ls -qaf name="^${INSEC_REG}\$")" ]; then
        docker container rm -f "${INSEC_REG}"
    fi

    if [ -n "$(docker container ls -qaf name="^${SR_WITH_AUTH}\$")" ]; then
        docker container rm -f "${SR_WITH_AUTH}"
    fi

    if [ -n "$(docker container ls -qaf name="^${SR_NO_AUTH}\$")" ]; then
        docker container rm -f "${SR_NO_AUTH}"
    fi

    rm -rf "${SR_NO_AUTH_CERTS}" "${SR_WITH_AUTH_CERTS}"

    if [ -n "$(docker network ls -qf name="^${REGISTRIES_NETWORK}\$")" ]; then
        docker network rm "${REGISTRIES_NETWORK}"
    fi
}

stop-registries() {
    _stop-registries "$@"
}
