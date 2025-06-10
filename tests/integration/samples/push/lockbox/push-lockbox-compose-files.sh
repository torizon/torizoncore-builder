#!/bin/bash

if [ "$#" != 1 ]; then
    echo "Usage: push-lockbox-compose-files.sh <credentials.zip>"
    echo "Note: The present script must be sourced."
    return 1
fi

if ! [[ "$(type -t torizoncore-builder)" == @("alias"|"function") ]]; then
    echo "Please source the torizoncore-builder environment setup script first." >&2
    return 1
fi

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

. "${SCRIPT_DIR}/../../../testcases/lib/registries.sh"

_tcb() {
    local cmd=$(alias torizoncore-builder |
                    sed -ne "s/^.*torizoncore-builder='\(.*\)'$/\1/p")
    echo ">> torizoncore-builder $*"
    eval ${cmd} "$@"
}

_TCB_CREDENTIALS="${1?credentials file name must be passed}"
_TCB_COMPOSE_FILES="
    docker-compose-lkbx-32bit.yml
    docker-compose-lkbx-64bit.yml 
    docker-compose-lkbx-badmix.yml
    docker-compose-lkbx-mixed-mp32bit.yml
    docker-compose-lkbx-mutiplat.yml
    docker-compose-lkbx-regaccess.yml.in
    docker-compose-lkbx-regaccess-dh.yml.in
    docker-compose-lkbx-regaccess-noauth.yml.in
    docker-compose-lkbx-regaccess-auth.yml.in
    docker-compose-lkbx-regaccess-err.yml.in
"

for _tcb_cf in ${_TCB_COMPOSE_FILES}; do
    if [ "${_tcb_cf##*.}" == "in" ]; then
        # File needs pre-processing before pushing:
        cp "${_tcb_cf}" "${_tcb_cf%.*}"
        _tcb_cf="${_tcb_cf%.*}"

        sed -e "s/@SR_NO_AUTH_IP@/${SR_NO_AUTH_IP}/" -i "${_tcb_cf}"
        sed -e "s/@SR_WITH_AUTH_IP@/${SR_WITH_AUTH_IP}/" -i "${_tcb_cf}"

        #cat "${_tcb_cf}"
        _tcb platform push "${_tcb_cf}" --canonicalize --credentials "${_TCB_CREDENTIALS}"

        rm "${_tcb_cf}"
    else
        _tcb platform push "${_tcb_cf}" --canonicalize --credentials "${_TCB_CREDENTIALS}"
    fi
done
