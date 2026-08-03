bats_load_library 'bats/bats-support/load.bash'
bats_load_library 'bats/bats-assert/load.bash'
bats_load_library 'bats/bats-file/load.bash'
load '../lib/common.bash'

RSS_SYNTH_4K=rss_synth_4k.img
RSS_SYNTH_512=rss_synth_512.img
# Lands the 4Kn image's free space just inside combine's 98%-full growth
# path, short of the free-space-exactly-zero case (a ZeroDivisionError in
# combine.py itself).
RSS_SLACK_4K_KB=132400
# No ratio target for the 512 case (only proves the synthesis helper is
# sector-size-agnostic) - a generous fixed margin is fine here.
RSS_SLACK_512_KB=204800

# Builds a synthetic raw disk mirroring write_rootfs_to_raw_image()'s own
# primitives, so it's exactly what the code under test expects to open.
build-synth-raw-image() {
    local out="$1"
    local sector="$2"
    local size_kb="$3"
    # Round up to a whole sector - guestfish/qemu need a sector-aligned
    # disk. Mirrors grow_last_partition()'s own rounding.
    local total_bytes=$(( size_kb * 1024 ))
    total_bytes=$(( (total_bytes + sector - 1) / sector * sector ))
    local total_sectors=$(( total_bytes / sector ))
    # 33 LBAs reserved for the GPT backup header, converted to this disk's
    # sector size - grow_last_partition's own calculation.
    local gpt_tail=$(( (33 * 512 + sector - 1) / sector ))
    local end_sector=$(( total_sectors - 1 - gpt_tail ))
    local blocksize_opt=""
    [ "$sector" = "4096" ] && blocksize_opt="--blocksize=4096"

    # copy-in can't flatten a directory's contents in one call, so copy each
    # top-level entry - same as write_rootfs_to_raw_image().
    local copy_in_ops=""
    local entry
    while IFS= read -r entry; do
        [ "$entry" = "lost+found" ] && continue
        copy_in_ops+=" copy-in /storage/sysroot/$entry / :"
    done < <(torizoncore-builder-shell "ls /storage/sysroot")

    rm -f "$out"
    torizoncore-builder-shell "truncate -s $total_bytes $out"
    torizoncore-builder-shell "guestfish $blocksize_opt -a $out -- \
        run : \
        part-init /dev/sda gpt : \
        part-add /dev/sda primary 2048 $end_sector : \
        mkfs ext4 /dev/sda1 : \
        set-label /dev/sda1 otaroot : \
        mount /dev/sda1 / : \
        $copy_in_ops \
        umount /"
}

# Echoes "<partition bytes> <filesystem bytes>" for a 4Kn raw disk.
raw-sector-size-4k-fs-stats() {
    local img="$1"
    torizoncore-builder-shell "guestfish --blocksize=4096 -a $img -- \
        run : \
        part-list /dev/sda : \
        mount /dev/sda1 / : \
        statvfs /" \
    | awk '
        /part_size:/ { part_size = $2 }
        /blocks:/    { blocks = $2 }
        /bsize:/     { bsize = $2 }
        END {
            if (part_size == "" || blocks == "" || bsize == "") {
                print "raw-sector-size-4k-fs-stats: missing field(s) in guestfish output" > "/dev/stderr"
                exit 1
            }
            print part_size, blocks * bsize
        }
    '
}

setup_file() {
    torizoncore-builder-clean-storage
    torizoncore-builder images --remove-storage unpack $DEFAULT_WIC_IMAGE

    # Measure the sysroot size rather than assume it, so the margin doesn't
    # drift if the default WIC image changes.
    local sysroot_kb
    sysroot_kb=$(torizoncore-builder-shell "du -s /storage/sysroot" | cut -f1)

    build-synth-raw-image "$RSS_SYNTH_4K" 4096 $(( sysroot_kb + RSS_SLACK_4K_KB ))
    build-synth-raw-image "$RSS_SYNTH_512" 512 $(( sysroot_kb + RSS_SLACK_512_KB ))
}

teardown_file() {
    rm -f "$RSS_SYNTH_4K" "$RSS_SYNTH_512"
}

teardown() {
    rm -rf rss_docker-compose.yml rss_bundle rss_combine_out.img rss_deploy_out.img
}

@test "raw sector size: images unpack from a 4Kn raw image" {
    torizoncore-builder-clean-storage

    run torizoncore-builder images --remove-storage unpack --raw-sector-size 4096 $RSS_SYNTH_4K
    assert_success
    assert_output --partial "Unpacked OSTree from WIC/raw image"
}

@test "raw sector size: deploy changes to a 4Kn raw image" {
    rm -rf rss_deploy_out.img

    torizoncore-builder-clean-storage
    torizoncore-builder images --remove-storage unpack --raw-sector-size 4096 $RSS_SYNTH_4K
    torizoncore-builder union --changes-directory $SAMPLES_DIR/changes branch1

    run torizoncore-builder deploy --base-raw $RSS_SYNTH_4K --raw-sector-size 4096 \
                                   --output-raw rss_deploy_out.img branch1
    assert_success
    assert_output --partial "created successfully!"
}

@test "raw sector size: combine grows a 4Kn image past the 98% ratio" {
    local ci_dockerhub_login="$(ci-dockerhub-login-flag)"

    # Read before combine grows anything, to compare against below.
    read -r part_size_before fs_bytes_before <<< "$(raw-sector-size-4k-fs-stats "$RSS_SYNTH_4K")"

    local compose='rss_docker-compose.yml'
    cp "$SAMPLES_DIR/compose/hello/docker-compose.yml" "$compose"

    rm -rf rss_bundle rss_combine_out.img
    run torizoncore-builder bundle --bundle-directory rss_bundle "$compose" \
        ${ci_dockerhub_login:+"--login" "${CI_DOCKER_HUB_PULL_USER}" "${CI_DOCKER_HUB_PULL_PASSWORD}"}
    assert_success

    if [ "${ci_dockerhub_login}" = "1" ]; then
        assert_output --partial "Attempting to log in to"
    fi

    run torizoncore-builder combine --bundle-directory rss_bundle --force --raw-sector-size 4096 \
                                    $RSS_SYNTH_4K rss_combine_out.img
    assert_success
    assert_output --partial "Output disk will be increased"

    read -r part_size_after fs_bytes_after <<< "$(raw-sector-size-4k-fs-stats rss_combine_out.img)"

    # The filesystem must grow along with the partition.
    run awk -v before="$fs_bytes_before" -v after="$fs_bytes_after" \
        'BEGIN { exit !(after > before * 1.05) }'
    assert_success

    # ...and roughly fill it, matching mkfs's own baseline ratio.
    run awk -v ps_before="$part_size_before" -v fs_before="$fs_bytes_before" \
             -v ps_after="$part_size_after" -v fs_after="$fs_bytes_after" \
        'BEGIN { exit !(fs_after / ps_after >= (fs_before / ps_before) * 0.98) }'
    assert_success
}

@test "raw sector size: images unpack from a 512 raw image (regression guard on the new synthesis helper)" {
    torizoncore-builder-clean-storage

    run torizoncore-builder images --remove-storage unpack $RSS_SYNTH_512
    assert_success
    assert_output --partial "Unpacked OSTree from WIC/raw image"
}
