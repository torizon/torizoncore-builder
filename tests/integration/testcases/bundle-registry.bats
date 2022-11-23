load 'bats/bats-support/load.bash'
load 'bats/bats-assert/load.bash'
load 'bats/bats-file/load.bash'
load 'lib/registries.sh'
load 'lib/common.bash'

function teardown() {
    remove_registries
}

@test "bundle-registries: check with secure registries without authentication" {
    local SR_COMPOSE_FOLDER="${SAMPLES_DIR}/compose/secure-registry"

    run build_registries
    assert_success

    run check_registries
    assert_success

    cp "${SR_COMPOSE_FOLDER}/docker-compose-sr.yml" \
        "${SR_COMPOSE_FOLDER}/docker-compose.yml"

    sed -i -E -e "s/# @NAME1@/test/" \
              -e "s/# image: @IMAGE5@/ image: ${SR_NO_AUTH_IP}\/test1/" \
              "${SR_COMPOSE_FOLDER}/docker-compose.yml"

    run torizoncore-builder bundle --cacert-to "${SR_NO_AUTH_IP}" \
                                   "${SR_NO_AUTH_CERTS}/server.key" \
                                   --force "${SR_COMPOSE_FOLDER}/docker-compose.yml"
    assert_failure
    assert_output --partial "x509: certificate signed by unknown authority"

    run torizoncore-builder bundle --cacert-to "${SR_NO_AUTH_IP}" \
                                   "${SR_NO_AUTH_CERTS}/cacert.crt" \
                                   --force "${SR_COMPOSE_FOLDER}/docker-compose.yml"
    assert_success
    assert_output --partial "Fetching container image ${SR_NO_AUTH_IP}/test"
}

@test "bundle-registries: check with secure registry with authentication" {
    local SR_COMPOSE_FOLDER="${SAMPLES_DIR}/compose/secure-registry"

    run build_registries
    assert_success

    run build_registries
    assert_success

    cp "${SR_COMPOSE_FOLDER}/docker-compose-sr.yml" \
        "${SR_COMPOSE_FOLDER}/docker-compose.yml"

    sed -i -E -e "s/# @NAME1@/test/" \
              -e "s/# image: @IMAGE5@/ image: ${SR_WITH_AUTH_IP}\/test1/" \
              "${SR_COMPOSE_FOLDER}/docker-compose.yml"

    run torizoncore-builder bundle --login-to "${SR_WITH_AUTH_IP}" toradex wrong \
                                   --cacert-to "${SR_WITH_AUTH_IP}" \
                                   "${SR_WITH_AUTH_CERTS}/cacert.crt" \
                                   --force "${SR_COMPOSE_FOLDER}/docker-compose.yml"
    assert_failure
    assert_output --partial "Unauthorized"

    run torizoncore-builder bundle --login-to "${SR_WITH_AUTH_IP}" toradex test \
                                   --cacert-to "${SR_WITH_AUTH_IP}" \
                                   "${SR_WITH_AUTH_CERTS}/cacert.crt" \
                                   --force "${SR_COMPOSE_FOLDER}/docker-compose.yml"
    assert_success
    assert_output --partial "Fetching container image ${SR_WITH_AUTH_IP}/test"
}

@test "bundle-registries: check with with all registries" {
    local if_ci=""
    local SR_COMPOSE_FOLDER="${SAMPLES_DIR}/compose/secure-registry"
    local CONTAINERS=("${SR_NO_AUTH}" "${SR_WITH_AUTH}")
    local REGISTRIES=("${SR_NO_AUTH_IP}" "${SR_WITH_AUTH_IP}")

    if [ "$TCB_UNDER_CI" = "1" ]; then
      if_ci="1"
    fi

    run build_registries
    assert_success

    run check_registries
    assert_success

    cp "${SR_COMPOSE_FOLDER}/docker-compose-sr.yml" \
        "${SR_COMPOSE_FOLDER}/docker-compose.yml"

    for i in {1..2}; do
        if [ "$i" -eq 1 ]; then NUMBER=1; fi
        for y in {0..1}; do
            sed -i -E -e "s/# @NAME${NUMBER}@/test${NUMBER}/" \
                      -e "s/# image: @IMAGE${NUMBER}@/ image: ${REGISTRIES[y]}\/test$i/" \
                          "${SR_COMPOSE_FOLDER}/docker-compose.yml"
            ((NUMBER++))
        done
    done

    sed -i -E -e "s/# @NAME5@/alpine/" \
              -e "s/# image: @IMAGE5@/ image: alpine/" \
              "${SR_COMPOSE_FOLDER}/docker-compose.yml"

    run torizoncore-builder bundle --login-to "${SR_WITH_AUTH_IP}" toradex test \
                                   --cacert-to "${SR_WITH_AUTH_IP}" \
                                   "${SR_WITH_AUTH_CERTS}/cacert.crt" \
                                   --cacert-to "${SR_NO_AUTH_IP}" \
                                   "${SR_NO_AUTH_CERTS}/cacert.crt" \
                                   --force "${SR_COMPOSE_FOLDER}/docker-compose.yml" \
                                   ${if_ci:+"--login" "$CI_DOCKER_HUB_PULL_USER"
                                                      "$CI_DOCKER_HUB_PULL_PASSWORD"}
    assert_success
    for i in {1..2}; do
        for y in {0..1}; do
            assert_output --partial \
                  "Fetching container image ${REGISTRIES[y]}/test$i"
        done
    done

}
