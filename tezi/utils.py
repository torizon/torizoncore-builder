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
