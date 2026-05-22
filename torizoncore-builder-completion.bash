#!/usr/bin/env bash

TCB_COMP_ARGS_MAIN="
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

TCB_COMP_ARGS_MAIN_LOGLEVEL="
    debug
    info
    warning
    error
    critical
"

TCB_COMP_ARGS_BUILD="
    --help
    --create-template
    --file
    --force
    --set
    --no-subst
"

TCB_COMP_ARGS_BUILD_SET="
    VAR=\"value\"
"

TCB_COMP_ARGS_BUNDLE="
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

TCB_COMP_ARGS_BUNDLE_PLATFORM="
    linux/arm/v7
    linux/arm64
"

TCB_COMP_ARGS_COMBINE="
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

TCB_COMP_ARGS_DEPLOY="
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

TCB_COMP_ARGS_DT="
    --help
    status
    checkout
    apply
"

TCB_COMP_ARGS_DT_STATUS="
    --help
"

TCB_COMP_ARGS_DT_CHECKOUT="
    --help
    --update
"

TCB_COMP_ARGS_DT_APPLY="
    --help
    --include-dir
"

TCB_COMP_ARGS_DTO="
    --help
    apply
    list
    status
    remove
    deploy
"

TCB_COMP_ARGS_DTO_APPLY="
    --help
    --include-dir
    --device-tree
    --force
"

TCB_COMP_ARGS_DTO_LIST="
    --help
    --device-tree
"

TCB_COMP_ARGS_DTO_STATUS="
    --help
"

TCB_COMP_ARGS_DTO_REMOVE="
    --help
    --all
"

TCB_COMP_ARGS_DTO_DEPLOY="
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

TCB_COMP_ARGS_IMAGES="
    --help
    --remove-storage
    download
    provision
    serve
    unpack
"

TCB_COMP_ARGS_IMAGES_DOWNLOAD="
    --help
    --remote-host
    --remote-username
    --remote-password
    --remote-port
    --mdns-source
"

TCB_COMP_ARGS_IMAGES_PROVISION="
    --help
    --mode
    --force
    --shared-data
    --online-data
"

TCB_COMP_ARGS_IMAGES_PROVISION_MODES="
    offline
    online
"

TCB_COMP_ARGS_IMAGES_UNPACK="
    --help
"

TCB_COMP_ARGS_IMAGES_SERVE="
    --help
"

TCB_COMP_ARGS_ISOLATE="
    --help
    --changes-directory
    --force
    --remote-host
    --remote-username
    --remote-password
    --remote-port
    --mdns-source
"

TCB_COMP_ARGS_KERNEL="
    --help
    build_module
    set_custom_args
    get_custom_args
    clear_custom_args
"

TCB_COMP_ARGS_KERNEL_BUILD_MODULE="
    --help
    --autoload
"

TCB_COMP_ARGS_KERNEL_SET_CUSTOM_ARGS="
    --help
"

TCB_COMP_ARGS_KERNEL_GET_CUSTOM_ARGS="
    --help
"

TCB_COMP_ARGS_KERNEL_CLEAR_CUSTOM_ARGS="
    --help
"

TCB_COMP_ARGS_OSTREE="
    --help
    serve
"

TCB_COMP_ARGS_OSTREE_SERVE="
    --help
    --ostree-repo-directory
"

TCB_COMP_ARGS_PLATFORM="
    --help
    lockbox
    provisioning-data
    push
"

TCB_COMP_ARGS_PLATFORM_LOCKBOX="
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

TCB_COMP_ARGS_PLATFORM_LOCKBOX_PLATFORM="$TCB_COMP_ARGS_BUNDLE_PLATFORM"

TCB_COMP_ARGS_PLATFORM_PROVDATA="
    --help
    --credentials
    --force
    --shared-data
    --online-data
"

TCB_COMP_ARGS_PUSH="
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

TCB_COMP_ARGS_SPLASH="
    --help
"

TCB_COMP_ARGS_UNION="
    --help
    --changes-directory
    --subject
    --body
"

# default value to complete parameters
TCB_COMP_ARGS_DEF_PASSWORD="_TYPE_HERE_PASSWORD_"
TCB_COMP_ARGS_DEF_USERNAME="_TYPE_HERE_USERNAME_"
TCB_COMP_ARGS_DEF_REGISTRY="_TYPE_HERE_REGISTRY_"
TCB_COMP_ARGS_DEF_CERT="_TYPE_HERE_CERT_"
TCB_COMP_ARGS_DEF_DIND_PARAM="_TYPE_HERE_DIND_PARAM_"
TCB_COMP_ARGS_DEF_DIND_ENV="ENV1=VAL1"
TCB_COMP_ARGS_DEF_IMAGE_NAME="_TYPE_HERE_IMAGE_NAME_"
TCB_COMP_ARGS_DEF_IMAGE_DESCRIPTION="_TYPE_HERE_IMAGE_DESCRIPTION_"
TCB_COMP_ARGS_DEF_REMOTE_HOST="_TYPE_HERE_REMOTE_HOST_"
TCB_COMP_ARGS_DEF_REMOTE_USERNAME="torizon"
TCB_COMP_ARGS_DEF_REMOTE_PASSWORD="_TYPE_HERE_PASSWORD_"
TCB_COMP_ARGS_DEF_REMOTE_PORT="_TYPE_HERE_REMOTE_PORT_"
TCB_COMP_ARGS_DEF_MDNS_SOURCE="_TYPE_HERE_MDNS_SOURCE_"
TCB_COMP_ARGS_DEF_KERNEL_ARGS="ARG1=VAL1"
TCB_COMP_ARGS_DEF_HARDWAREID="_TYPE_HERE_HARDWARE_ID_"
TCB_COMP_ARGS_DEF_SUBJECT="_TYPE_HERE_COMMIT_SUBJECT_"
TCB_COMP_ARGS_DEF_BODY="_TYPE_HERE_COMMIT_BODY_"
TCB_COMP_ARGS_DEF_OSTREE_REF="_TYPE_HERE_OSTREE_REF_OR_COMPOSE_FILE_NAME_"
TCB_COMP_ARGS_DEF_UNION_BRANCH="_TYPE_HERE_UNION_BRANCH_"
TCB_COMP_ARGS_DEF_PACKAGE_NAME="_TYPE_HERE_PACKAGE_NAME_"
TCB_COMP_ARGS_DEF_PACKAGE_VERSION="_TYPE_HERE_PACKAGE_VERSION_"
TCB_COMP_ARGS_DEF_ONLINE_PROVDATA="_TYPE_HERE_ONLINE_PROVISIONING_STRING_"
TCB_COMP_ARGS_DEF_LOCKBOX_NAME="_TYPE_HERE_LOCKBOX_NAME_"
TCB_COMP_ARGS_DEF_SHARED_DATA="_TYPE_HERE_SHARED_DATA_FILE_NAME_"
TCB_COMP_ARGS_DEF_CLIENT_NAME="_TYPE_HERE_API_CLIENT_NAME_"

# return in $COMPREPLY a list of files and directories starting from the
# current working directory. The first parameter can be used to filter
# the output files (e.g. *.txt), and if not passed, only directories are
# returned. The second parameter, if true, can be used in conjuction with the first
# to exclude the directories from the results
_torizoncore-builder_completions_helper_filter_files_and_dirs() {
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

_torizoncore-builder_completions_helper_filter_files() {
    _torizoncore-builder_completions_helper_filter_files_and_dirs "$1" true
}

# return in $COMPREPLY a list of directories starting from the current
# working directory.
_torizoncore-builder_completions_helper_filter_dirs() {
    _torizoncore-builder_completions_helper_filter_files_and_dirs ""
}

# return in $COMPREPLY a list of static options passed as a parameter
# to this function, removing the list the last typed word
_torizoncore-builder_completions_helper_static_options() {
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
_torizoncore-builder_completions_helper_find_subcmd() {
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
_torizoncore-builder_completions_build() {
    local prev="${COMP_WORDS[COMP_CWORD-1]}"

    case "$prev" in
        --file)
            _torizoncore-builder_completions_helper_filter_files_and_dirs "*.y*ml"
            ;;
        --set)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_BUILD_SET"
            ;;
        *)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_BUILD"
            ;;
    esac
}

# 'bundle' command
_torizoncore-builder_completions_bundle() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local prev1="${COMP_WORDS[COMP_CWORD-1]}"
    local prev2="${COMP_WORDS[COMP_CWORD-2]}"
    local prev3="${COMP_WORDS[COMP_CWORD-3]}"

    case "$prev3" in
        --login-to)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DEF_PASSWORD"
            return
            ;;
    esac

    case "$prev2" in
        --login)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DEF_PASSWORD"
            return
            ;;
        --login-to)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DEF_USERNAME"
            return
            ;;
        --cacert-to)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DEF_CERT"
            ;;
    esac

    case "$prev1" in
        --bundle-directory)
            _torizoncore-builder_completions_helper_filter_dirs
            ;;
        --platform)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_BUNDLE_PLATFORM"
            ;;
        --login)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DEF_USERNAME"
            ;;
        --login-to)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DEF_REGISTRY"
            ;;
        --cacert-to)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DEF_REGISTRY"
            ;;
        --dind-param)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DEF_DIND_PARAM"
            ;;
        --dind-env)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DEF_DIND_ENV"
            ;;
        *)
            if [ -n "$cur" ]; then
                _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_BUNDLE"
            fi
            if [ -z "$COMPREPLY" ]; then
                _torizoncore-builder_completions_helper_filter_files_and_dirs "*.y*ml"
            fi
            ;;
    esac
}

# 'combine' command
_torizoncore-builder_completions_combine() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local prev="${COMP_WORDS[COMP_CWORD-1]}"

    case "$prev" in
        --bundle-directory)
            _torizoncore-builder_completions_helper_filter_dirs
            ;;
        --image-name)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DEF_IMAGE_NAME"
            ;;
        --image-description)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DEF_IMAGE_DESCRIPTION"
            ;;
        --image-licence|--image-release-notes)
            _torizoncore-builder_completions_helper_filter_files_and_dirs "*"
            ;;
        *)
            if [ -n "$cur" ]; then
                _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_COMBINE"
            fi
            if [ -z "$COMPREPLY" ]; then
                _torizoncore-builder_completions_helper_filter_dirs
            fi
            ;;
    esac
}

# 'deploy' command
_torizoncore-builder_completions_deploy() {
    local prev="${COMP_WORDS[COMP_CWORD-1]}"

    case "$prev" in
        --bundle-directory|--output-directory|--deploy-sysroot-directory)
            _torizoncore-builder_completions_helper_filter_dirs
            ;;
        --image-name)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DEF_IMAGE_NAME"
            ;;
        --image-description)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DEF_IMAGE_DESCRIPTION"
            ;;
        --remote-host)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DEF_REMOTE_HOST"
            ;;
        --remote-username)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DEF_REMOTE_USERNAME"
            ;;
        --remote-password)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DEF_REMOTE_PASSWORD"
            ;;
        --remote-port)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DEF_REMOTE_PORT"
            ;;
        --mdns-source)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DEF_MDNS_SOURCE"
            ;;
        --image-licence|--image-release-notes)
            _torizoncore-builder_completions_helper_filter_files_and_dirs "*"
            ;;
        *)
            if [ -n "$cur" ]; then
                _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DEPLOY"
            fi
            if [ -z "$COMPREPLY" ]; then
                _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DEF_OSTREE_REF"
            fi
            ;;
    esac
}

# 'dt apply' command
_torizoncore-builder_completions_dt_apply() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local prev="${COMP_WORDS[COMP_CWORD-1]}"

    case "$prev" in
        --include-dir)
            _torizoncore-builder_completions_helper_filter_dirs
            ;;
        *.dts)
            ;;
        *)
            if [ -n "$cur" ]; then
                _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DT_APPLY"
            fi
            if [ -z "$COMPREPLY" ]; then
                _torizoncore-builder_completions_helper_filter_files_and_dirs "*.dts"
            fi
            ;;
    esac
}

# 'dt' command
_torizoncore-builder_completions_dt() {
    local prev="${COMP_WORDS[COMP_CWORD-1]}"

    local cmd=$(_torizoncore-builder_completions_helper_find_subcmd "dt" "$TCB_COMP_ARGS_DT")

    case "$cmd" in
        status)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DT_STATUS"
            ;;
        checkout)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DT_CHECKOUT"
            ;;
        apply)
            _torizoncore-builder_completions_dt_apply
            ;;
        *)
            if [ "$prev" = "dt" ]; then
                _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DT"
            fi
            ;;
    esac
}

# 'dto apply' command
_torizoncore-builder_completions_dto_apply() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local prev="${COMP_WORDS[COMP_CWORD-1]}"
    local prev2="${COMP_WORDS[COMP_CWORD-2]}"

    case "$prev" in
        --include-dir)
            _torizoncore-builder_completions_helper_filter_dirs
            ;;
        --device-tree)
            _torizoncore-builder_completions_helper_filter_files_and_dirs "*.dts"
            ;;
        *.dts)
            if [ "$prev2" != "--device-tree" ]; then
                return;
            fi
            if [ -n "$cur" ]; then
                _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DTO_APPLY"
            fi
            if [ -z "$COMPREPLY" ]; then
                _torizoncore-builder_completions_helper_filter_files_and_dirs "*.dts"
            fi
            ;;
        *)
            if [ -n "$cur" ]; then
                _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DTO_APPLY"
            fi
            if [ -z "$COMPREPLY" ]; then
                _torizoncore-builder_completions_helper_filter_files_and_dirs "*.dts"
            fi
            ;;
    esac
}

# 'dto list' command
_torizoncore-builder_completions_dto_list() {
    local prev="${COMP_WORDS[COMP_CWORD-1]}"

    case "$prev" in
        --device-tree)
            _torizoncore-builder_completions_helper_filter_files_and_dirs "*.dts"
            ;;
        *)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DTO_LIST"
            ;;
    esac
}

# 'dto remove' command
_torizoncore-builder_completions_dto_remove() {
    local prev="${COMP_WORDS[COMP_CWORD-1]}"

    case "$prev" in
        *.dtbo)
            ;;
        *)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DTO_REMOVE"
            ;;
    esac
}

# 'dto deploy' command
_torizoncore-builder_completions_dto_deploy() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local prev="${COMP_WORDS[COMP_CWORD-1]}"
    local prev2="${COMP_WORDS[COMP_CWORD-2]}"

    case "$prev" in
        --include-dir)
            _torizoncore-builder_completions_helper_filter_dirs
            ;;
        --device-tree)
            _torizoncore-builder_completions_helper_filter_files_and_dirs "*.dts"
            ;;
        --remote-host)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DEF_REMOTE_HOST"
            ;;
        --remote-username)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DEF_REMOTE_USERNAME"
            ;;
        --remote-password)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DEF_REMOTE_PASSWORD"
            ;;
        --remote-port)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DEF_REMOTE_PORT"
            ;;
        --mdns-source)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DEF_MDNS_SOURCE"
            ;;
        *.dts)
            if [ "$prev2" != "--device-tree" ]; then
                return;
            fi
            if [ -n "$cur" ]; then
                _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DTO_DEPLOY"
            fi
            if [ -z "$COMPREPLY" ]; then
                _torizoncore-builder_completions_helper_filter_files_and_dirs "*.dts"
            fi
            ;;
        *)
            if [ -n "$cur" ]; then
                _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DTO_DEPLOY"
            fi
            if [ -z "$COMPREPLY" ]; then
                _torizoncore-builder_completions_helper_filter_files_and_dirs "*.dts"
            fi
            ;;
    esac
}

# 'dto' command
_torizoncore-builder_completions_dto() {
    local prev="${COMP_WORDS[COMP_CWORD-1]}"
    local cmd=$(_torizoncore-builder_completions_helper_find_subcmd "dto" "$TCB_COMP_ARGS_DTO")

    case "$cmd" in
        apply)
            _torizoncore-builder_completions_dto_apply
            ;;
        list)
            _torizoncore-builder_completions_dto_list
            ;;
        status)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DTO_STATUS"
            ;;
        remove)
            _torizoncore-builder_completions_dto_remove
            ;;
        deploy)
            _torizoncore-builder_completions_dto_deploy
            ;;
        *)
            if [ "$prev" = "dto" ]; then
                _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DTO"
            fi
            ;;
    esac
}

# 'images unpack' command
_torizoncore-builder_completions_images_unpack() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local prev="${COMP_WORDS[COMP_CWORD-1]}"

    case "$prev" in
        *)
            if [ -n "$cur" ]; then
                _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_IMAGES_UNPACK"
            fi
            if [ -z "$COMPREPLY" ]; then
                _torizoncore-builder_completions_helper_filter_files_and_dirs "*"
            fi
            ;;
    esac
}

# 'images download' command
_torizoncore-builder_completions_images_download() {
    local prev="${COMP_WORDS[COMP_CWORD-1]}"

    case "$prev" in
        --remote-host)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DEF_REMOTE_HOST"
            ;;
        --remote-username)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DEF_REMOTE_USERNAME"
            ;;
        --remote-password)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DEF_REMOTE_PASSWORD"
            ;;
        --remote-port)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DEF_REMOTE_PORT"
            ;;
        --mdns-source)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DEF_MDNS_SOURCE"
            ;;
        *)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_IMAGES_DOWNLOAD"
            ;;
    esac
}

# 'images provision' command
_torizoncore-builder_completions_images_provision() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local prev="${COMP_WORDS[COMP_CWORD-1]}"

    case "$prev" in
        --mode)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_IMAGES_PROVISION_MODES"
            ;;
        --shared-data)
            _torizoncore-builder_completions_helper_filter_files_and_dirs "*.tar.gz"
            ;;
        --online-data)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DEF_ONLINE_PROVDATA"
            ;;
        *)
            if [ -n "$cur" ]; then
                _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_IMAGES_PROVISION"
            fi
            if [ -z "$COMPREPLY" ]; then
                _torizoncore-builder_completions_helper_filter_dirs
            fi
            ;;
    esac
}

# 'images serve' command
_torizoncore-builder_completions_images_serve() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local prev="${COMP_WORDS[COMP_CWORD-1]}"

    case "$prev" in
        *)
            if [ -n "$cur" ]; then
                _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_IMAGES_SERVE"
            fi
            if [ -z "$COMPREPLY" ]; then
                _torizoncore-builder_completions_helper_filter_dirs
            fi
            ;;
    esac
}

# 'images' command
_torizoncore-builder_completions_images() {
    local cmd=$(_torizoncore-builder_completions_helper_find_subcmd "images" "$TCB_COMP_ARGS_IMAGES")

    case "$cmd" in
        download)
            _torizoncore-builder_completions_images_download
            ;;
        provision)
            _torizoncore-builder_completions_images_provision
            ;;
        serve)
            _torizoncore-builder_completions_images_serve
            ;;
        unpack)
            _torizoncore-builder_completions_images_unpack
            ;;
        *)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_IMAGES"
            ;;
    esac
}

# 'isolate' command
_torizoncore-builder_completions_isolate() {
    local prev="${COMP_WORDS[COMP_CWORD-1]}"

    case "$prev" in
        --changes-directory)
            _torizoncore-builder_completions_helper_filter_dirs
            ;;
        --remote-host)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DEF_REMOTE_HOST"
            ;;
        --remote-username)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DEF_REMOTE_USERNAME"
            ;;
        --remote-password)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DEF_REMOTE_PASSWORD"
            ;;
        --remote-port)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DEF_REMOTE_PORT"
            ;;
        --mdns-source)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DEF_MDNS_SOURCE"
            ;;
        *)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_ISOLATE"
            ;;
    esac
}

# 'kernel build_module' command
_torizoncore-builder_completions_kernel_build_module() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local prev="${COMP_WORDS[COMP_CWORD-1]}"

    case "$prev" in
        *)
            if [ -n "$cur" ]; then
                _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_KERNEL_BUILD_MODULE"
            fi
            if [ -z "$COMPREPLY" ]; then
                _torizoncore-builder_completions_helper_filter_dirs "*"
            fi
            ;;
    esac
}

# 'kernel set_custom_args' command
_torizoncore-builder_completions_kernel_set_custom_args() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local prev="${COMP_WORDS[COMP_CWORD-1]}"

    case "$prev" in
        set_custom_args)
            if [ -n "$cur" ]; then
                _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_KERNEL_SET_CUSTOM_ARGS"
            fi
            if [ -z "$COMPREPLY" ]; then
                _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DEF_KERNEL_ARGS"
            fi
            ;;
    esac
}

# 'kernel' command
_torizoncore-builder_completions_kernel() {
    local cmd=$(_torizoncore-builder_completions_helper_find_subcmd "kernel" "$TCB_COMP_ARGS_KERNEL")

    case "$cmd" in
        build_module)
            _torizoncore-builder_completions_kernel_build_module
            ;;
        set_custom_args)
            _torizoncore-builder_completions_kernel_set_custom_args
            ;;
        get_custom_args)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_KERNEL_GET_CUSTOM_ARGS"
            ;;
        clear_custom_args)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_KERNEL_CLEAR_CUSTOM_ARGS"
            ;;
        *)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_KERNEL"
            ;;
    esac
}

# 'ostree serve' command
_torizoncore-builder_completions_ostree_serve() {
    local prev="${COMP_WORDS[COMP_CWORD-1]}"

    case "$prev" in
        --ostree-repo-directory)
            _torizoncore-builder_completions_helper_filter_dirs
            ;;
        *)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_OSTREE_SERVE"
            ;;
    esac
}

# 'ostree' command
_torizoncore-builder_completions_ostree() {
    local prev="${COMP_WORDS[COMP_CWORD-1]}"
    local cmd=$(_torizoncore-builder_completions_helper_find_subcmd "ostree" "$TCB_COMP_ARGS_OSTREE")

    case "$cmd" in
        serve)
            _torizoncore-builder_completions_ostree_serve
            ;;
        *)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_OSTREE"
            ;;
    esac
}

_torizoncore-builder_completions_platform_lockbox() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local prev1="${COMP_WORDS[COMP_CWORD-1]}"
    local prev2="${COMP_WORDS[COMP_CWORD-2]}"
    local prev3="${COMP_WORDS[COMP_CWORD-3]}"

    case "$prev3" in
        --login-to)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DEF_PASSWORD"
            return
            ;;
    esac

    case "$prev2" in
        --login)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DEF_PASSWORD"
            return
            ;;
        --login-to)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DEF_USERNAME"
            return
            ;;
        --cacert-to)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DEF_CERT"
            ;;
    esac

    case "$prev1" in
        --credentials)
            _torizoncore-builder_completions_helper_filter_files_and_dirs "credentials.zip"
            ;;
        --platform)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_PLATFORM_LOCKBOX_PLATFORM"
            ;;
        --login)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DEF_USERNAME"
            ;;
        --login-to)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DEF_REGISTRY"
            ;;
        --cacert-to)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DEF_REGISTRY"
            ;;
        --dind-param)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DEF_DIND_PARAM"
            ;;
        --dind-env)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DEF_DIND_ENV"
            ;;
        --output-directory)
            _torizoncore-builder_completions_helper_filter_dirs
            ;;
        *)
            if [ -n "$cur" ]; then
                _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_PLATFORM_LOCKBOX"
            fi
            if [ -z "$COMPREPLY" ]; then
                _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DEF_LOCKBOX_NAME"
            fi
            ;;
    esac
}

_torizoncore-builder_completions_platform_provisioning_data() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local prev="${COMP_WORDS[COMP_CWORD-1]}"

    case "$prev" in
        --credentials)
            _torizoncore-builder_completions_helper_filter_files_and_dirs "credentials.zip"
            ;;
        --shared-data)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DEF_SHARED_DATA"
            ;;
        --online-data)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DEF_CLIENT_NAME"
            ;;
        *)
            if [ -n "$cur" ]; then
                _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_PLATFORM_PROVDATA"
            fi
            ;;
    esac
}

_torizoncore-builder_completions_platform_push() {
    _torizoncore-builder_completions_push "$@"
}

# 'platform' command
_torizoncore-builder_completions_platform() {
    local cmd=$(_torizoncore-builder_completions_helper_find_subcmd "platform" "$TCB_COMP_ARGS_PLATFORM")

    case "$cmd" in
        lockbox)
            _torizoncore-builder_completions_platform_lockbox
            ;;
        provisioning-data)
            _torizoncore-builder_completions_platform_provisioning_data
            ;;
        push)
            _torizoncore-builder_completions_platform_push
            ;;
        *)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_PLATFORM"
            ;;
    esac
}

# return in $COMPREPLY a list of references. references can either be
# a compose file ending with .yaml/yml or the list of references from
# the ostree folder if the `--repo` argument is already present and it
# points to a valid ostree folder.
_torizoncore-builder_completions_push_reference() {
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
        _torizoncore-builder_completions_helper_filter_files "*.y*ml"
    fi

}

# 'push' command
_torizoncore-builder_completions_push() {
    local prev="${COMP_WORDS[COMP_CWORD-1]}"

    case "$prev" in
        --credentials)
            _torizoncore-builder_completions_helper_filter_files_and_dirs "credentials.zip"
            ;;
        --repo)
            _torizoncore-builder_completions_helper_filter_dirs
            ;;
        --hardwareid)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DEF_HARDWAREID"
            ;;
        --package-name)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DEF_PACKAGE_NAME"
            ;;
        --package-version)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DEF_PACKAGE_VERSION"
            ;;
        *)
            if [ -n "$cur" ]; then
                _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_PUSH"
            fi
            if [ -z "$COMPREPLY" ]; then
                _torizoncore-builder_completions_push_reference
            fi
            ;;
    esac
}

# 'splash' command
_torizoncore-builder_completions_splash() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local prev="${COMP_WORDS[COMP_CWORD-1]}"

    case "$prev" in
        *)
            if [ -n "$cur" ]; then
                _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_SPLASH"
            fi
            if [ -z "$COMPREPLY" ]; then
                _torizoncore-builder_completions_helper_filter_files_and_dirs "*"
            fi
            ;;
    esac
}

# 'union' command
_torizoncore-builder_completions_union() {
    local prev="${COMP_WORDS[COMP_CWORD-1]}"

    case "$prev" in
        --changes-directory)
            _torizoncore-builder_completions_helper_filter_dirs
            ;;
        --subject)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DEF_SUBJECT"
            ;;
        --body)
            _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DEF_BODY"
            ;;
        *)
            if [ -n "$cur" ]; then
                _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_UNION"
            fi
            if [ -z "$COMPREPLY" ]; then
                _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_DEF_UNION_BRANCH"
            fi
            ;;
    esac
}

# 'main' command
_torizoncore-builder_completions() {
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
                    _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_MAIN_LOGLEVEL"
                    return
                else
                    i=$((i + 1))
                fi
                ;;
            --log-file)
                if [ "$i" -eq "$COMP_CWORD" ]; then
                    _torizoncore-builder_completions_helper_filter_files_and_dirs "*"
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
        _torizoncore-builder_completions_helper_static_options "$TCB_COMP_ARGS_MAIN"
        return
    fi

    case "$cmd" in
        build)
            _torizoncore-builder_completions_build
            ;;
        bundle)
            _torizoncore-builder_completions_bundle
            ;;
        combine)
            _torizoncore-builder_completions_combine
            ;;
        deploy)
            _torizoncore-builder_completions_deploy
            ;;
        dt)
            _torizoncore-builder_completions_dt
            ;;
        dto)
            _torizoncore-builder_completions_dto
            ;;
        images)
            _torizoncore-builder_completions_images
            ;;
        isolate)
            _torizoncore-builder_completions_isolate
            ;;
        kernel)
            _torizoncore-builder_completions_kernel
            ;;
        ostree)
            _torizoncore-builder_completions_ostree
            ;;
        platform)
            _torizoncore-builder_completions_platform
            ;;
        push)
            _torizoncore-builder_completions_push
            ;;
        splash)
            _torizoncore-builder_completions_splash
            ;;
        union)
            _torizoncore-builder_completions_union
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
  complete -o bashdefault -F _torizoncore-builder_completions torizoncore-builder
else
  setopt completealiases
  autoload bashcompinit && bashcompinit
  _function=('-F' '_torizoncore-builder_completions')
  compdef _bash_complete_zsh\ ${(j. .)${(q)_function}} torizoncore-builder
fi

