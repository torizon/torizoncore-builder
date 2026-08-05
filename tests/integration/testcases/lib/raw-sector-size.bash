#!/bin/bash

#
# Shared helpers for --raw-sector-size (4Kn) test coverage, used across
# images-unpack.bats, deploy.bats and combine.bats under wic/.
#

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

# Cleans storage, unpacks $DEFAULT_WIC_IMAGE, measures its sysroot size
# once, then builds a synth raw image for each "<out> <sector> <slack_kb>"
# triple passed in - so the margin doesn't drift if the wic image changes.
raw-sector-size-setup-synth-images() {
    if [ $(( $# % 3 )) -ne 0 ]; then
        echo "raw-sector-size-setup-synth-images: expected a multiple of 3 args (out sector slack_kb ...), got $#" >&2
        return 1
    fi

    torizoncore-builder-clean-storage
    torizoncore-builder images --remove-storage unpack $DEFAULT_WIC_IMAGE

    local sysroot_kb
    sysroot_kb=$(torizoncore-builder-shell "du -s /storage/sysroot" | cut -f1)

    while [ "$#" -ge 3 ]; do
        build-synth-raw-image "$1" "$2" $(( sysroot_kb + $3 ))
        shift 3
    done
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
