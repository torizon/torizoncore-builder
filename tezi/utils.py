UNPACK_COMMANDS_MAP = {
    ".gz": "gzip -dc",
    ".tgz": "gzip -dc",
    ".xz": "xz -dc",
    ".lzo": "lzop -dc",
    ".zst": "zstd -dc",
    ".lz4": "lz4 -dc",
    ".bz2": "bzip2 -dc"
}


def find_rootfs_content(jsondata):
    """ Finds root filesystem content data from given image json object

    Parameters:
        jsondata (dict): Tezi image json dictionary
    Returns:
        dict: Json dictionary of the "content" part of the rootfs
        partition/volume
    """
    content = None
    if "mtddevs" in jsondata:
        # NAND module
        for dev in jsondata["mtddevs"]:
            if dev["name"] == "ubi":
                for volume in dev["ubivolumes"]:
                    if volume["name"] == "rootfs":
                        content = volume["content"]

    elif "blockdevs" in jsondata:
        # eMMC module
        for dev in jsondata["blockdevs"]:
            if "partitions" in dev:
                for part in dev["partitions"]:
                    if part["content"]["label"] == "otaroot":
                        content = part["content"]

    return content


def get_unpack_command(filename):
    """Get shell command to unpack a given file format"""
    for ext, cmd in UNPACK_COMMANDS_MAP.items():
        if filename.endswith(ext):
            return cmd
    return "cat"
