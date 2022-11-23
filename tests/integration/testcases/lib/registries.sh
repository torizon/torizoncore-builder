#! /bin/bash

# SR stand for Secure Registry
export SR_NO_AUTH="secure-registry-no-auth"
export SR_NO_AUTH_IP="172.20.0.2"
export SR_NO_AUTH_CERTS="secure_registry_no_auth"

export SR_WITH_AUTH="secure-registry-with-auth"
export SR_WITH_AUTH_IP="172.20.0.3:444"
export SR_WITH_AUTH_CERTS="secure_registry_with_auth"

export DIND_CONTAINER="dind-for-registries"

export DOCKER_NETWORK="registry-network"


function remove_registries() {
  (
    set +e

    # Removing existing containers and networks
    if [ -n "$(docker container ls -qaf name="^${DIND_CONTAINER}\$")" ]; then
      docker container rm -f "${DIND_CONTAINER}"
    fi

    if [ -n "$(docker container ls -qaf name="^${SR_NO_AUTH}\$")" ]; then
      docker container rm -f "${SR_NO_AUTH}"
    fi

    if [ -n "$(docker container ls -qaf name="^${SR_WITH_AUTH}\$")" ]; then
      docker container rm -f "${SR_WITH_AUTH}"
    fi

    if [ -n "$(docker network ls -qf name="^${DOCKER_NETWORK}\$")" ]; then
      docker network rm "${DOCKER_NETWORK}"
    fi

    rm -rf "${SR_NO_AUTH_CERTS}" "${SR_WITH_AUTH_CERTS}"
  )

}

function check_registries() {
  (
    set -eo pipefail

    local CONTAINERS=("${SR_NO_AUTH}" "${SR_WITH_AUTH}")
    local REGISTRIES=("${SR_NO_AUTH_IP}" "${SR_WITH_AUTH_IP}")

    # Check if the containers IP address are correct.
    for i in {0..1}; do
        test "${REGISTRIES[i]/:[0-9]*/}" = \
          "$(docker inspect -f \
          '{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}' \
           $(docker container ls -qf name="${CONTAINERS[i]}$"))"
    done
  )
}

function build_registries() {
  remove_registries

  (
    set -eo pipefail

    # Creating the folders
    mkdir -p "${SR_NO_AUTH_CERTS}" "${SR_WITH_AUTH_CERTS}" "${SR_WITH_AUTH_CERTS}/auth"

    # Creating the auth
    docker run \
      --entrypoint htpasswd \
      httpd:2 -Bbn toradex test > "${SR_WITH_AUTH_CERTS}/auth/htpasswd"

    # Creating the Certificates
    openssl req \
      -newkey rsa:4096 -nodes -sha256 -keyout "${SR_NO_AUTH_CERTS}/server.key" \
      -subj "/C=AU/ST=./L=./O=./CN=myregistry.domain.com" \
      -addext "subjectAltName = DNS:myregistry.domain.com, IP:${SR_NO_AUTH_IP}" \
      -x509 -days 365 -out "${SR_NO_AUTH_CERTS}/cacert.crt"

    openssl req \
      -newkey rsa:4096 -nodes -sha256 -keyout "${SR_WITH_AUTH_CERTS}/server.key" \
      -subj "/C=AU/ST=./L=./O=./CN=myregistry.domain.com" \
      -addext "subjectAltName = DNS:myregistry.domain.com, IP:${SR_WITH_AUTH_IP/:[0-9]*/}" \
      -x509 -days 365 -out "${SR_WITH_AUTH_CERTS}/cacert.crt"

    docker network create --subnet=172.20.0.0/16 "${DOCKER_NETWORK}"

    # Creating the Secure Registries
    docker run -d --restart=always --name "${SR_NO_AUTH}" \
              -v "$(pwd)/${SR_NO_AUTH_CERTS}:/certs" \
              -e REGISTRY_HTTP_ADDR=0.0.0.0:443 \
              -e REGISTRY_HTTP_TLS_CERTIFICATE=/certs/cacert.crt \
              -e REGISTRY_HTTP_TLS_KEY=/certs/server.key \
              -p 443:443 \
              --net "${DOCKER_NETWORK}" \
              --ip "${SR_NO_AUTH_IP}" \
              registry:2

    docker run -d --restart=always --name "${SR_WITH_AUTH}" \
              -v "$(pwd)/${SR_WITH_AUTH_CERTS}:/certs" \
              -e REGISTRY_HTTP_ADDR=0.0.0.0:444 \
              -e REGISTRY_HTTP_TLS_CERTIFICATE=/certs/cacert.crt \
              -e REGISTRY_HTTP_TLS_KEY=/certs/server.key \
              -e "REGISTRY_AUTH=htpasswd" \
              -e "REGISTRY_AUTH_HTPASSWD_REALM=Registry Realm" \
              -e REGISTRY_AUTH_HTPASSWD_PATH=/certs/auth/htpasswd \
              -p 444:444 \
              --net "${DOCKER_NETWORK}" \
              --ip "${SR_WITH_AUTH_IP/:[0-9]*/}" \
              registry:2

    # Creating the docker dind container
    if [ -n "$(docker container ls -qaf name="^${DIND_CONTAINER}\$")" ]; then
      docker container rm -f "${DIND_CONTAINER}"
    fi
    docker run -d --name "${DIND_CONTAINER}" --privileged --network host \
              -v "$(pwd):/certs" -e DOCKER_HOST="tcp://127.0.0.1:23736" \
              docker:19.03.8-dind dockerd --host=tcp://0.0.0.0:23736

    # Addind the cacerts to DIND
    docker exec "${DIND_CONTAINER}" /bin/ash -c "\
      mkdir -p /etc/docker/certs.d/${SR_NO_AUTH_IP} \
      /etc/docker/certs.d/${SR_WITH_AUTH_IP} && \
      cp /certs/${SR_NO_AUTH_CERTS}/cacert.crt /etc/docker/certs.d/${SR_NO_AUTH_IP}/cacert.crt && \
      cp /certs/${SR_WITH_AUTH_CERTS}/cacert.crt /etc/docker/certs.d/${SR_WITH_AUTH_IP}/cacert.crt"

    docker exec "${DIND_CONTAINER}" /bin/ash -c "\
      docker login -u toradex -p test ${SR_WITH_AUTH_IP} && \
      docker pull hello-world && \
      docker tag hello-world ${SR_NO_AUTH_IP}/test1 && \
      docker tag hello-world ${SR_NO_AUTH_IP}/test2 && \
      docker tag hello-world ${SR_WITH_AUTH_IP}/test1 && \
      docker tag hello-world ${SR_WITH_AUTH_IP}/test2 && \
      docker push ${SR_NO_AUTH_IP}/test1 && \
      docker push ${SR_NO_AUTH_IP}/test2 && \
      docker push ${SR_WITH_AUTH_IP}/test1 && \
      docker push ${SR_WITH_AUTH_IP}/test2"
  )
}

