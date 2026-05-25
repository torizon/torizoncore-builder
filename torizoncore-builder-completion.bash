#!/usr/bin/env bash

_TCBCOMP_ARGS_MAIN="
    -h --help
    --verbose
    --log-level
    --log-file
    -v --version
    build
    bundle
    combine
    deploy
    dt
    dto
    images
    isolate
    kernel
    ostree
    platform
    push
    splash
    union
"

_TCBCOMP_ARGS_MAIN_LOGLEVEL="
    debug
    info
    warning
    error
    critical
"

_TCBCOMP_ARGS_BUILD="
    --help
    --create-template
    --file
    --force
    --set
    --no-subst
"

_TCBCOMP_ARGS_BUILD_SET="
    VAR=\"value\"
"

_TCBCOMP_ARGS_BUNDLE="
    --help
    --bundle-directory
    --force
    --platform
    --keep-double-dollar-sign
    --login
    --login-to
    --cacert-to
    --dind-param
    --dind-env
"

_TCBCOMP_ARGS_BUNDLE_PLATFORM="
    linux/arm/v7
    linux/arm64
"

_TCBCOMP_ARGS_COMBINE="
    --help
    --bundle-directory
    --image-name
    --image-description
    --image-licence
    --image-release-notes
    --image-autoinstall
    --image-autoreboot
    --no-image-autoinstall
    --no-image-autoreboot
"

_TCBCOMP_ARGS_DEPLOY="
    --help
    --output-directory
    --remote-host
    --remote-username
    --remote-password
    --remote-port
    --mdns-source
    --reboot
    --deploy-sysroot-directory
    --image-name
    --image-description
    --image-licence
    --image-release-notes
    --image-autoinstall
    --image-autoreboot
    --no-image-autoinstall
    --no-image-autoreboot
"

_TCBCOMP_ARGS_DT="
    --help
    status
    checkout
    apply
"

_TCBCOMP_ARGS_DT_STATUS="
    --help
"

_TCBCOMP_ARGS_DT_CHECKOUT="
    --help
    --update
"

_TCBCOMP_ARGS_DT_APPLY="
    --help
    --include-dir
"

_TCBCOMP_ARGS_DTO="
    --help
    apply
    list
    status
    remove
    deploy
"

_TCBCOMP_ARGS_DTO_APPLY="
    --help
    --include-dir
    --device-tree
    --force
"

_TCBCOMP_ARGS_DTO_LIST="
    --help
    --device-tree
"

_TCBCOMP_ARGS_DTO_STATUS="
    --help
"

_TCBCOMP_ARGS_DTO_REMOVE="
    --help
    --all
"

_TCBCOMP_ARGS_DTO_DEPLOY="
    --help
    --remote-host
    --remote-username
    --remote-password
    --remote-port
    --reboot
    --mdns-source
    --include-dir
    --force
    --device-tree
    --clear
"

_TCBCOMP_ARGS_IMAGES="
    --help
    --remove-storage
    download
    provision
    serve
    unpack
"

_TCBCOMP_ARGS_IMAGES_DOWNLOAD="
    --help
    --remote-host
    --remote-username
    --remote-password
    --remote-port
    --mdns-source
"

_TCBCOMP_ARGS_IMAGES_PROVISION="
    --help
    --mode
    --force
    --shared-data
    --online-data
    --fleet
"

_TCBCOMP_ARGS_IMAGES_PROVISION_MODES="
    offline
    online
"

_TCBCOMP_ARGS_IMAGES_UNPACK="
    --help
"

_TCBCOMP_ARGS_IMAGES_SERVE="
    --help
"

_TCBCOMP_ARGS_ISOLATE="
    --help
    --changes-directory
    --force
    --remote-host
    --remote-username
    --remote-password
    --remote-port
    --mdns-source
"

_TCBCOMP_ARGS_KERNEL="
    --help
    build_module
    set_custom_args
    get_custom_args
    clear_custom_args
"

_TCBCOMP_ARGS_KERNEL_BUILD_MODULE="
    --help
    --autoload
"

_TCBCOMP_ARGS_KERNEL_SET_CUSTOM_ARGS="
    --help
"

_TCBCOMP_ARGS_KERNEL_GET_CUSTOM_ARGS="
    --help
"

_TCBCOMP_ARGS_KERNEL_CLEAR_CUSTOM_ARGS="
    --help
"

_TCBCOMP_ARGS_OSTREE="
    --help
    serve
"

_TCBCOMP_ARGS_OSTREE_SERVE="
    --help
    --ostree-repo-directory
"

_TCBCOMP_ARGS_PLATFORM="
    --help
    lockbox
    provisioning-data
    push
"

_TCBCOMP_ARGS_PLATFORM_LOCKBOX="
    --help
    --credentials
    --force
    --platform
    --login
    --login-to
    --cacert-to
    --dind-param
    --dind-env
    --output-directory
"

_TCBCOMP_ARGS_PLATFORM_LOCKBOX_PLATFORM="$_TCBCOMP_ARGS_BUNDLE_PLATFORM"

_TCBCOMP_ARGS_PLATFORM_PROVDATA="
    --help
    --credentials
    --force
    --shared-data
    --online-data
"

_TCBCOMP_ARGS_PUSH="
    --help
    --credentials
    --repo
    --hardwareid
    --canonicalize
    --no-canonicalize
    --canonicalize-only
    --package-name
    --package-version
    --force
    --verbose
"

_TCBCOMP_ARGS_SPLASH="
    --help
"

_TCBCOMP_ARGS_UNION="
    --help
    --changes-directory
    --subject
    --body
    --ostree-key
    --ostree-key-dir
"

# default value to complete parameters
_TCBCOMP_ARGS_DEF_PASSWORD="_TYPE_HERE_PASSWORD_"
_TCBCOMP_ARGS_DEF_USERNAME="_TYPE_HERE_USERNAME_"
_TCBCOMP_ARGS_DEF_REGISTRY="_TYPE_HERE_REGISTRY_"
_TCBCOMP_ARGS_DEF_CERT="_TYPE_HERE_CERT_"
_TCBCOMP_ARGS_DEF_DIND_PARAM="_TYPE_HERE_DIND_PARAM_"
_TCBCOMP_ARGS_DEF_DIND_ENV="ENV1=VAL1"
_TCBCOMP_ARGS_DEF_IMAGE_NAME="_TYPE_HERE_IMAGE_NAME_"
_TCBCOMP_ARGS_DEF_IMAGE_DESCRIPTION="_TYPE_HERE_IMAGE_DESCRIPTION_"
_TCBCOMP_ARGS_DEF_REMOTE_HOST="_TYPE_HERE_REMOTE_HOST_"
_TCBCOMP_ARGS_DEF_REMOTE_USERNAME="torizon"
_TCBCOMP_ARGS_DEF_REMOTE_PASSWORD="_TYPE_HERE_PASSWORD_"
_TCBCOMP_ARGS_DEF_REMOTE_PORT="_TYPE_HERE_REMOTE_PORT_"
_TCBCOMP_ARGS_DEF_MDNS_SOURCE="_TYPE_HERE_MDNS_SOURCE_"
_TCBCOMP_ARGS_DEF_KERNEL_ARGS="ARG1=VAL1"
_TCBCOMP_ARGS_DEF_HARDWAREID="_TYPE_HERE_HARDWARE_ID_"
_TCBCOMP_ARGS_DEF_SUBJECT="_TYPE_HERE_COMMIT_SUBJECT_"
_TCBCOMP_ARGS_DEF_BODY="_TYPE_HERE_COMMIT_BODY_"
_TCBCOMP_ARGS_DEF_OSTREE_REF="_TYPE_HERE_OSTREE_REF_OR_COMPOSE_FILE_NAME_"
_TCBCOMP_ARGS_DEF_UNION_BRANCH="_TYPE_HERE_UNION_BRANCH_"
_TCBCOMP_ARGS_DEF_PACKAGE_NAME="_TYPE_HERE_PACKAGE_NAME_"
_TCBCOMP_ARGS_DEF_PACKAGE_VERSION="_TYPE_HERE_PACKAGE_VERSION_"
_TCBCOMP_ARGS_DEF_ONLINE_PROVDATA="_TYPE_HERE_ONLINE_PROVISIONING_STRING_"
_TCBCOMP_ARGS_DEF_FLEET_UUID="_TYPE_HERE_FLEET_UUID_"
_TCBCOMP_ARGS_DEF_LOCKBOX_NAME="_TYPE_HERE_LOCKBOX_NAME_"
_TCBCOMP_ARGS_DEF_SHARED_DATA="_TYPE_HERE_SHARED_DATA_FILE_NAME_"
_TCBCOMP_ARGS_DEF_CLIENT_NAME="_TYPE_HERE_API_CLIENT_NAME_"

# return in $COMPREPLY a list of files and directories starting from the
# current working directory. The first parameter can be used to filter
# the output files (e.g. *.txt), and if not passed, only directories are
# returned. The second parameter, if true, can be used in conjuction with the first
# to exclude the directories from the results
_tcbcomp_helper_filter_files_and_dirs() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local filterpath="$1"

    local IFS=$'\n'
    local LASTCHAR=' '

    local arg=(-o plusdirs)

    if [ "$2" = "true" ]; then
        arg=()
    fi

    if [ -z "$ZSH_VERSION" ]; then
      compopt -o nospace
    fi

    if [ -z "$filterpath" ]; then
        COMPREPLY=($(compgen_compat -d -- ${cur}))
    else
        COMPREPLY=($(compgen_compat ${arg[@]} -f -X "!$filterpath" -- ${cur}))
    fi

    if [ ${#COMPREPLY[@]} = 1 ]; then
        [ -d "$COMPREPLY" ] && LASTCHAR=/
        [ -z "$ZSH_VERSION" ] && \
        COMPREPLY=$(printf %q%s "$COMPREPLY" "$LASTCHAR")
    else
        for ((i=0; i < ${#COMPREPLY[@]}; i++)); do
            [ -z "$ZSH_VERSION" ] && [ -d "${COMPREPLY[$i]}" ] && \
            COMPREPLY[$i]=${COMPREPLY[$i]}/
        done
    fi
}

_tcbcomp_helper_filter_files() {
    _tcbcomp_helper_filter_files_and_dirs "$1" true
}

# return in $COMPREPLY a list of directories starting from the current
# working directory.
_tcbcomp_helper_filter_dirs() {
    _tcbcomp_helper_filter_files_and_dirs ""
}

# return in $COMPREPLY a list of static options passed as a parameter
# to this function, removing the list the last typed word
_tcbcomp_helper_static_options() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local prev="${COMP_WORDS[COMP_CWORD-1]}"
    local opts=($(compgen_compat -W "$@" -- ${cur}))
    local i=0
    for opt in "${opts[@]}"; do
      [ "$opt" = "$prev" ] && unset opts["$i"]
      ((++i))
    done
    COMPREPLY=(${opts[@]})
}

# given the current command line, return the current subcommand being processed.
# For example, 'torizoncore-builder images unpack' will return 'unpack'
_tcbcomp_helper_find_subcmd() {
    local cmd=$1
    local opts=$2

    local cmd_found=0
    local i=1

    while [ $i -lt $((COMP_CWORD+1)) ]; do
        local word="${COMP_WORDS[i]}"
        local opt=""

        first_chars=$(echo $word | cut -c1-2)

        if [ "$word" == "$cmd" ]; then
            cmd_found=1
        elif [ "$cmd_found" == "1" -a "$first_chars" != "--" ]; then
            for opt in $opts; do
                if [ "$word" == "$opt" ]; then
                    echo $word
                    return
                fi
            done
        fi

        i=$((i + 1))
    done
}

# 'build' command
_tcbcomp_build() {
    local prev="${COMP_WORDS[COMP_CWORD-1]}"

    case "$prev" in
        --file)
            _tcbcomp_helper_filter_files_and_dirs "*.y*ml"
            ;;
        --set)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_BUILD_SET"
            ;;
        *)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_BUILD"
            ;;
    esac
}

# 'bundle' command
_tcbcomp_bundle() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local prev1="${COMP_WORDS[COMP_CWORD-1]}"
    local prev2="${COMP_WORDS[COMP_CWORD-2]}"
    local prev3="${COMP_WORDS[COMP_CWORD-3]}"

    case "$prev3" in
        --login-to)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEF_PASSWORD"
            return
            ;;
    esac

    case "$prev2" in
        --login)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEF_PASSWORD"
            return
            ;;
        --login-to)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEF_USERNAME"
            return
            ;;
        --cacert-to)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEF_CERT"
            ;;
    esac

    case "$prev1" in
        --bundle-directory)
            _tcbcomp_helper_filter_dirs
            ;;
        --platform)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_BUNDLE_PLATFORM"
            ;;
        --login)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEF_USERNAME"
            ;;
        --login-to)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEF_REGISTRY"
            ;;
        --cacert-to)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEF_REGISTRY"
            ;;
        --dind-param)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEF_DIND_PARAM"
            ;;
        --dind-env)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEF_DIND_ENV"
            ;;
        *)
            if [ -n "$cur" ]; then
                _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_BUNDLE"
            fi
            if [ -z "$COMPREPLY" ]; then
                _tcbcomp_helper_filter_files_and_dirs "*.y*ml"
            fi
            ;;
    esac
}

# 'combine' command
_tcbcomp_combine() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local prev="${COMP_WORDS[COMP_CWORD-1]}"

    case "$prev" in
        --bundle-directory)
            _tcbcomp_helper_filter_dirs
            ;;
        --image-name)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEF_IMAGE_NAME"
            ;;
        --image-description)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEF_IMAGE_DESCRIPTION"
            ;;
        --image-licence|--image-release-notes)
            _tcbcomp_helper_filter_files_and_dirs "*"
            ;;
        *)
            if [ -n "$cur" ]; then
                _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_COMBINE"
            fi
            if [ -z "$COMPREPLY" ]; then
                _tcbcomp_helper_filter_dirs
            fi
            ;;
    esac
}

# 'deploy' command
_tcbcomp_deploy() {
    local prev="${COMP_WORDS[COMP_CWORD-1]}"

    case "$prev" in
        --bundle-directory|--output-directory|--deploy-sysroot-directory)
            _tcbcomp_helper_filter_dirs
            ;;
        --image-name)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEF_IMAGE_NAME"
            ;;
        --image-description)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEF_IMAGE_DESCRIPTION"
            ;;
        --remote-host)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEF_REMOTE_HOST"
            ;;
        --remote-username)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEF_REMOTE_USERNAME"
            ;;
        --remote-password)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEF_REMOTE_PASSWORD"
            ;;
        --remote-port)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEF_REMOTE_PORT"
            ;;
        --mdns-source)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEF_MDNS_SOURCE"
            ;;
        --image-licence|--image-release-notes)
            _tcbcomp_helper_filter_files_and_dirs "*"
            ;;
        *)
            if [ -n "$cur" ]; then
                _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEPLOY"
            fi
            if [ -z "$COMPREPLY" ]; then
                _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEF_OSTREE_REF"
            fi
            ;;
    esac
}

# 'dt apply' command
_tcbcomp_dt_apply() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local prev="${COMP_WORDS[COMP_CWORD-1]}"

    case "$prev" in
        --include-dir)
            _tcbcomp_helper_filter_dirs
            ;;
        *.dts)
            ;;
        *)
            if [ -n "$cur" ]; then
                _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DT_APPLY"
            fi
            if [ -z "$COMPREPLY" ]; then
                _tcbcomp_helper_filter_files_and_dirs "*.dts"
            fi
            ;;
    esac
}

# 'dt' command
_tcbcomp_dt() {
    local prev="${COMP_WORDS[COMP_CWORD-1]}"

    local cmd=$(_tcbcomp_helper_find_subcmd "dt" "$_TCBCOMP_ARGS_DT")

    case "$cmd" in
        status)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DT_STATUS"
            ;;
        checkout)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DT_CHECKOUT"
            ;;
        apply)
            _tcbcomp_dt_apply
            ;;
        *)
            if [ "$prev" = "dt" ]; then
                _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DT"
            fi
            ;;
    esac
}

# 'dto apply' command
_tcbcomp_dto_apply() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local prev="${COMP_WORDS[COMP_CWORD-1]}"
    local prev2="${COMP_WORDS[COMP_CWORD-2]}"

    case "$prev" in
        --include-dir)
            _tcbcomp_helper_filter_dirs
            ;;
        --device-tree)
            _tcbcomp_helper_filter_files_and_dirs "*.dts"
            ;;
        *.dts)
            if [ "$prev2" != "--device-tree" ]; then
                return;
            fi
            if [ -n "$cur" ]; then
                _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DTO_APPLY"
            fi
            if [ -z "$COMPREPLY" ]; then
                _tcbcomp_helper_filter_files_and_dirs "*.dts"
            fi
            ;;
        *)
            if [ -n "$cur" ]; then
                _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DTO_APPLY"
            fi
            if [ -z "$COMPREPLY" ]; then
                _tcbcomp_helper_filter_files_and_dirs "*.dts"
            fi
            ;;
    esac
}

# 'dto list' command
_tcbcomp_dto_list() {
    local prev="${COMP_WORDS[COMP_CWORD-1]}"

    case "$prev" in
        --device-tree)
            _tcbcomp_helper_filter_files_and_dirs "*.dts"
            ;;
        *)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DTO_LIST"
            ;;
    esac
}

# 'dto remove' command
_tcbcomp_dto_remove() {
    local prev="${COMP_WORDS[COMP_CWORD-1]}"

    case "$prev" in
        *.dtbo)
            ;;
        *)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DTO_REMOVE"
            ;;
    esac
}

# 'dto deploy' command
_tcbcomp_dto_deploy() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local prev="${COMP_WORDS[COMP_CWORD-1]}"
    local prev2="${COMP_WORDS[COMP_CWORD-2]}"

    case "$prev" in
        --include-dir)
            _tcbcomp_helper_filter_dirs
            ;;
        --device-tree)
            _tcbcomp_helper_filter_files_and_dirs "*.dts"
            ;;
        --remote-host)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEF_REMOTE_HOST"
            ;;
        --remote-username)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEF_REMOTE_USERNAME"
            ;;
        --remote-password)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEF_REMOTE_PASSWORD"
            ;;
        --remote-port)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEF_REMOTE_PORT"
            ;;
        --mdns-source)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEF_MDNS_SOURCE"
            ;;
        *.dts)
            if [ "$prev2" != "--device-tree" ]; then
                return;
            fi
            if [ -n "$cur" ]; then
                _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DTO_DEPLOY"
            fi
            if [ -z "$COMPREPLY" ]; then
                _tcbcomp_helper_filter_files_and_dirs "*.dts"
            fi
            ;;
        *)
            if [ -n "$cur" ]; then
                _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DTO_DEPLOY"
            fi
            if [ -z "$COMPREPLY" ]; then
                _tcbcomp_helper_filter_files_and_dirs "*.dts"
            fi
            ;;
    esac
}

# 'dto' command
_tcbcomp_dto() {
    local prev="${COMP_WORDS[COMP_CWORD-1]}"
    local cmd=$(_tcbcomp_helper_find_subcmd "dto" "$_TCBCOMP_ARGS_DTO")

    case "$cmd" in
        apply)
            _tcbcomp_dto_apply
            ;;
        list)
            _tcbcomp_dto_list
            ;;
        status)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DTO_STATUS"
            ;;
        remove)
            _tcbcomp_dto_remove
            ;;
        deploy)
            _tcbcomp_dto_deploy
            ;;
        *)
            if [ "$prev" = "dto" ]; then
                _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DTO"
            fi
            ;;
    esac
}

# 'images unpack' command
_tcbcomp_images_unpack() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local prev="${COMP_WORDS[COMP_CWORD-1]}"

    case "$prev" in
        *)
            if [ -n "$cur" ]; then
                _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_IMAGES_UNPACK"
            fi
            if [ -z "$COMPREPLY" ]; then
                _tcbcomp_helper_filter_files_and_dirs "*"
            fi
            ;;
    esac
}

# 'images download' command
_tcbcomp_images_download() {
    local prev="${COMP_WORDS[COMP_CWORD-1]}"

    case "$prev" in
        --remote-host)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEF_REMOTE_HOST"
            ;;
        --remote-username)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEF_REMOTE_USERNAME"
            ;;
        --remote-password)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEF_REMOTE_PASSWORD"
            ;;
        --remote-port)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEF_REMOTE_PORT"
            ;;
        --mdns-source)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEF_MDNS_SOURCE"
            ;;
        *)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_IMAGES_DOWNLOAD"
            ;;
    esac
}

# 'images provision' command
_tcbcomp_images_provision() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local prev="${COMP_WORDS[COMP_CWORD-1]}"

    case "$prev" in
        --mode)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_IMAGES_PROVISION_MODES"
            ;;
        --shared-data)
            _tcbcomp_helper_filter_files_and_dirs "*.tar.gz"
            ;;
        --online-data)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEF_ONLINE_PROVDATA"
            ;;
        --fleet)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEF_FLEET_UUID"
            ;;
        *)
            if [ -n "$cur" ]; then
                _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_IMAGES_PROVISION"
            fi
            if [ -z "$COMPREPLY" ]; then
                _tcbcomp_helper_filter_dirs
            fi
            ;;
    esac
}

# 'images serve' command
_tcbcomp_images_serve() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local prev="${COMP_WORDS[COMP_CWORD-1]}"

    case "$prev" in
        *)
            if [ -n "$cur" ]; then
                _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_IMAGES_SERVE"
            fi
            if [ -z "$COMPREPLY" ]; then
                _tcbcomp_helper_filter_dirs
            fi
            ;;
    esac
}

# 'images' command
_tcbcomp_images() {
    local cmd=$(_tcbcomp_helper_find_subcmd "images" "$_TCBCOMP_ARGS_IMAGES")

    case "$cmd" in
        download)
            _tcbcomp_images_download
            ;;
        provision)
            _tcbcomp_images_provision
            ;;
        serve)
            _tcbcomp_images_serve
            ;;
        unpack)
            _tcbcomp_images_unpack
            ;;
        *)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_IMAGES"
            ;;
    esac
}

# 'isolate' command
_tcbcomp_isolate() {
    local prev="${COMP_WORDS[COMP_CWORD-1]}"

    case "$prev" in
        --changes-directory)
            _tcbcomp_helper_filter_dirs
            ;;
        --remote-host)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEF_REMOTE_HOST"
            ;;
        --remote-username)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEF_REMOTE_USERNAME"
            ;;
        --remote-password)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEF_REMOTE_PASSWORD"
            ;;
        --remote-port)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEF_REMOTE_PORT"
            ;;
        --mdns-source)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEF_MDNS_SOURCE"
            ;;
        *)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_ISOLATE"
            ;;
    esac
}

# 'kernel build_module' command
_tcbcomp_kernel_build_module() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local prev="${COMP_WORDS[COMP_CWORD-1]}"

    case "$prev" in
        *)
            if [ -n "$cur" ]; then
                _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_KERNEL_BUILD_MODULE"
            fi
            if [ -z "$COMPREPLY" ]; then
                _tcbcomp_helper_filter_dirs "*"
            fi
            ;;
    esac
}

# 'kernel set_custom_args' command
_tcbcomp_kernel_set_custom_args() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local prev="${COMP_WORDS[COMP_CWORD-1]}"

    case "$prev" in
        set_custom_args)
            if [ -n "$cur" ]; then
                _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_KERNEL_SET_CUSTOM_ARGS"
            fi
            if [ -z "$COMPREPLY" ]; then
                _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEF_KERNEL_ARGS"
            fi
            ;;
    esac
}

# 'kernel' command
_tcbcomp_kernel() {
    local cmd=$(_tcbcomp_helper_find_subcmd "kernel" "$_TCBCOMP_ARGS_KERNEL")

    case "$cmd" in
        build_module)
            _tcbcomp_kernel_build_module
            ;;
        set_custom_args)
            _tcbcomp_kernel_set_custom_args
            ;;
        get_custom_args)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_KERNEL_GET_CUSTOM_ARGS"
            ;;
        clear_custom_args)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_KERNEL_CLEAR_CUSTOM_ARGS"
            ;;
        *)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_KERNEL"
            ;;
    esac
}

# 'ostree serve' command
_tcbcomp_ostree_serve() {
    local prev="${COMP_WORDS[COMP_CWORD-1]}"

    case "$prev" in
        --ostree-repo-directory)
            _tcbcomp_helper_filter_dirs
            ;;
        *)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_OSTREE_SERVE"
            ;;
    esac
}

# 'ostree' command
_tcbcomp_ostree() {
    local prev="${COMP_WORDS[COMP_CWORD-1]}"
    local cmd=$(_tcbcomp_helper_find_subcmd "ostree" "$_TCBCOMP_ARGS_OSTREE")

    case "$cmd" in
        serve)
            _tcbcomp_ostree_serve
            ;;
        *)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_OSTREE"
            ;;
    esac
}

_tcbcomp_platform_lockbox() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local prev1="${COMP_WORDS[COMP_CWORD-1]}"
    local prev2="${COMP_WORDS[COMP_CWORD-2]}"
    local prev3="${COMP_WORDS[COMP_CWORD-3]}"

    case "$prev3" in
        --login-to)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEF_PASSWORD"
            return
            ;;
    esac

    case "$prev2" in
        --login)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEF_PASSWORD"
            return
            ;;
        --login-to)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEF_USERNAME"
            return
            ;;
        --cacert-to)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEF_CERT"
            ;;
    esac

    case "$prev1" in
        --credentials)
            _tcbcomp_helper_filter_files_and_dirs "credentials.zip"
            ;;
        --platform)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_PLATFORM_LOCKBOX_PLATFORM"
            ;;
        --login)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEF_USERNAME"
            ;;
        --login-to)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEF_REGISTRY"
            ;;
        --cacert-to)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEF_REGISTRY"
            ;;
        --dind-param)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEF_DIND_PARAM"
            ;;
        --dind-env)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEF_DIND_ENV"
            ;;
        --output-directory)
            _tcbcomp_helper_filter_dirs
            ;;
        *)
            if [ -n "$cur" ]; then
                _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_PLATFORM_LOCKBOX"
            fi
            if [ -z "$COMPREPLY" ]; then
                _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEF_LOCKBOX_NAME"
            fi
            ;;
    esac
}

_tcbcomp_platform_provisioning_data() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local prev="${COMP_WORDS[COMP_CWORD-1]}"

    case "$prev" in
        --credentials)
            _tcbcomp_helper_filter_files_and_dirs "credentials.zip"
            ;;
        --shared-data)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEF_SHARED_DATA"
            ;;
        --online-data)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEF_CLIENT_NAME"
            ;;
        *)
            if [ -n "$cur" ]; then
                _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_PLATFORM_PROVDATA"
            fi
            ;;
    esac
}

_tcbcomp_platform_push() {
    _tcbcomp_push "$@"
}

# 'platform' command
_tcbcomp_platform() {
    local cmd=$(_tcbcomp_helper_find_subcmd "platform" "$_TCBCOMP_ARGS_PLATFORM")

    case "$cmd" in
        lockbox)
            _tcbcomp_platform_lockbox
            ;;
        provisioning-data)
            _tcbcomp_platform_provisioning_data
            ;;
        push)
            _tcbcomp_platform_push
            ;;
        *)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_PLATFORM"
            ;;
    esac
}

# return in $COMPREPLY a list of references. references can either be
# a compose file ending with .yaml/yml or the list of references from
# the ostree folder if the `--repo` argument is already present and it
# points to a valid ostree folder.
_tcbcomp_push_reference() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local repo

    for ((index=0; index < ${#COMP_WORDS[@]}; index++)); do
        if [ "${COMP_WORDS[index]}" = "--repo" -a "${COMP_WORDS[index+1]}" = "=" ]; then
            repo="${COMP_WORDS[index+2]}"
        elif [[ "${COMP_WORDS[index]}" =~ ^--repo= ]]; then
            repo=${COMP_WORDS[index]:7}
        elif [ "${COMP_WORDS[index]}" = "--repo" ]; then
            repo="${COMP_WORDS[index+1]}"
        fi
    done

    repo=$(echo $repo | tr -d '"')
    local refs_path="$PWD/$repo/refs/heads/"

    if [ -d "$refs_path"  -a -n "$repo" ]; then
        local results=($(find "$refs_path" -type f 2>/dev/null))
        results=${results[@]/$refs_path/}
        COMPREPLY=($(compgen_compat -W "$results" -- ${cur}))
    else
        _tcbcomp_helper_filter_files "*.y*ml"
    fi

}

# 'push' command
_tcbcomp_push() {
    local prev="${COMP_WORDS[COMP_CWORD-1]}"

    case "$prev" in
        --credentials)
            _tcbcomp_helper_filter_files_and_dirs "credentials.zip"
            ;;
        --repo)
            _tcbcomp_helper_filter_dirs
            ;;
        --hardwareid)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEF_HARDWAREID"
            ;;
        --package-name)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEF_PACKAGE_NAME"
            ;;
        --package-version)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEF_PACKAGE_VERSION"
            ;;
        *)
            if [ -n "$cur" ]; then
                _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_PUSH"
            fi
            if [ -z "$COMPREPLY" ]; then
                _tcbcomp_push_reference
            fi
            ;;
    esac
}

# 'splash' command
_tcbcomp_splash() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local prev="${COMP_WORDS[COMP_CWORD-1]}"

    case "$prev" in
        *)
            if [ -n "$cur" ]; then
                _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_SPLASH"
            fi
            if [ -z "$COMPREPLY" ]; then
                _tcbcomp_helper_filter_files_and_dirs "*"
            fi
            ;;
    esac
}

# 'union' command
_tcbcomp_union() {
    local prev="${COMP_WORDS[COMP_CWORD-1]}"

    case "$prev" in
        --changes-directory)
            _tcbcomp_helper_filter_dirs
            ;;
        --subject)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEF_SUBJECT"
            ;;
        --body)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEF_BODY"
            ;;
        --ostree-key)
            _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEF_OSTREE_KEY"
            ;;
        --ostree-key-dir)
            _tcbcomp_helper_filter_dirs
            ;;
        *)
            if [ -n "$cur" ]; then
                _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_UNION"
            fi
            if [ -z "$COMPREPLY" ]; then
                _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_DEF_UNION_BRANCH"
            fi
            ;;
    esac
}

# 'main' command
_tcbcomp() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local i=1 cmd

    # find the subcommand
    while [[ "$i" -lt "$COMP_CWORD" ]]
    do
        local s="${COMP_WORDS[i]}"
        i=$((i + 1))
        case "$s" in
            --log-level)
                if [ "$i" -eq "$COMP_CWORD" ]; then
                    _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_MAIN_LOGLEVEL"
                    return
                else
                    i=$((i + 1))
                fi
                ;;
            --log-file)
                if [ "$i" -eq "$COMP_CWORD" ]; then
                    _tcbcomp_helper_filter_files_and_dirs "*"
                    return
                else
                    i=$((i + 1))
                fi
                ;;
            -*)
                ;;
            *)
                cmd="$s"
                break
                ;;
        esac
    done

    if [ -z "$cmd" ]; then
        _tcbcomp_helper_static_options "$_TCBCOMP_ARGS_MAIN"
        return
    fi

    case "$cmd" in
        build)
            _tcbcomp_build
            ;;
        bundle)
            _tcbcomp_bundle
            ;;
        combine)
            _tcbcomp_combine
            ;;
        deploy)
            _tcbcomp_deploy
            ;;
        dt)
            _tcbcomp_dt
            ;;
        dto)
            _tcbcomp_dto
            ;;
        images)
            _tcbcomp_images
            ;;
        isolate)
            _tcbcomp_isolate
            ;;
        kernel)
            _tcbcomp_kernel
            ;;
        ostree)
            _tcbcomp_ostree
            ;;
        platform)
            _tcbcomp_platform
            ;;
        push)
            _tcbcomp_push
            ;;
        splash)
            _tcbcomp_splash
            ;;
        union)
            _tcbcomp_union
            ;;
        *)
            ;;
    esac
}

compgen_compat() {
  if [ -z "$ZSH_VERSION" ]; then
      compgen "$@"
  else
      compgen_zsh "$@"
  fi
}

# Mimics the results bash compgen function would output
compgen_zsh() {
  local R_PATH="*"
  local CUR=".*"
  local ARGS="-1"
  local X
  local WORD
  local FILTER=";p"
  local DIR_FILTER=";p"

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --)
        # Prevents unwanted output if nothing is passed after `--`
        [ -n "$2" ] && shift || break;
        CUR="$1"
        ;;
      -o)
        shift
        COMP_OPTION="$1"
        ;;
      -d)
        # Filter only Directories
        ARGS+='adp'
        DIR_FILTER='/\/$/p'
      ;;
      -f)
        ARGS+='adp'
      ;;
      -X)
        shift
        # Dumb parser to comply with regex. tested only with the patterns in this file.
        X=$(tr -d '!' <<< "$1" | sed -En -e  's@^\*@\.\*@1; s@\*@.?@2; s@\.@\\.@2; p;')
      ;;
      -W)
        shift
        WORD="$1"
      ;;
      *)

      ;;
    esac
    shift
  done

  if [ "$COMP_OPTION" = "plusdirs" ]; then
    ARGS+='adp'
  fi

  if [ -n "$WORD" -a -n "$CUR" ]; then
    echo "$WORD" | awk 'NF' | tr ' ' '\n' | sed -En "s;^($CUR.*)$;\1;p"
    return
  fi

  # Update pattern to comply with compgen -X '<patter>'
  if [ -n "$X" ]; then
    if [ "$COMP_OPTION" = "plusdirs" ]; then
      FILTER="/($X|.*\/)$/p;"
    else
      FILTER="/$X$/p;"
    fi
  fi

  # Gets the base dir and add `(.*|*)`.
  [ -d "$CUR" -a "$CUR" != '..' ] && R_PATH="$CUR(.*|*)"
  if [ ! -d "$CUR" -a -n "$CUR" ]; then
    [ $(dirname -- "$CUR") = '.' ] && R_PATH="(.*|*)" || \
    R_PATH=$(dirname -- "$CUR" | sed -En -e 's@$@\/(.*|*)@p')
  fi

  # If either no arguments are passed or the target folder is empty, return nothing
  [ "$ARGS" = "-1" -o $( (eval "ls -1d $R_PATH" 2>/dev/null) | wc -l) -eq 0 ] && return

  eval "ls $ARGS $R_PATH | sed -En -e '$DIR_FILTER' | sed -En -e '$FILTER' | sed -En -e 's;^($CUR.*)$;\1;p'"
}

_bash_complete_zsh () {
	local ret=1
	local -a suf matches
	local -x COMP_POINT COMP_CWORD
	local -a COMP_WORDS COMPREPLY BASH_VERSINFO
	local -x COMP_LINE="$words"
	local -A savejobstates savejobtexts
	(( COMP_POINT = 1 + ${#${(j. .)words[1,CURRENT-1]}} + $#QIPREFIX + $#IPREFIX + $#PREFIX ))
	(( COMP_CWORD = CURRENT - 1))
	COMP_WORDS=($words)
	BASH_VERSINFO=(2 05b 0 1 release)
	savejobstates=(${(kv)jobstates})
	savejobtexts=(${(kv)jobtexts})
	[[ ${argv[${argv[(I)nospace]:-0}-1]} = -o ]] && suf=(-S '')
	matches=(${(f)"$(compgen $@ -- ${words[CURRENT]})"})
	if [[ -n $matches ]]
	then
		if [[ ${argv[${argv[(I)filenames]:-0}-1]} = -o ]]
		then
			compset -P '*/' && matches=(${matches##*/})
			compset -S '/*' && matches=(${matches%%/*})
			compadd -Q -f "${suf[@]}" -a matches && ret=0
		else
			if [ ${#matches[@]} = 1 ] && [ -d "$matches" ]; then
        compadd -Q -S '' "${suf[@]}" -a matches && ret=0
      else
        compadd -Q "${suf[@]}" -a matches && ret=0
      fi
		fi
	fi
	if (( ret ))
	then
		if [[ ${argv[${argv[(I)default]:-0}-1]} = -o ]]
		then
			_default "${suf[@]}" && ret=0
		elif [[ ${argv[${argv[(I)dirnames]:-0}-1]} = -o ]]
		then
			_directories "${suf[@]}" && ret=0
		fi
	fi
	return ret
}

if [ -z "$ZSH_VERSION" ]; then
  complete -o bashdefault -F _tcbcomp torizoncore-builder
else
  setopt completealiases
  autoload bashcompinit && bashcompinit
  _function=('-F' '_tcbcomp')
  compdef _bash_complete_zsh\ ${(j. .)${(q)_function}} torizoncore-builder
fi
