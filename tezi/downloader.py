import os
import json
import urllib.request
import logging

def find(key, dictionary):
    if (not (isinstance(dictionary, dict))):
        return
    for k, v in dictionary.items():
        if k == key:
            yield v
        elif isinstance(v, dict):
            for result in find(key, v):
                yield result
        elif isinstance(v, list):
            for d in v:
                for result in find(key, d):
                    yield result

def download_file(filename, baseurl, destdir):
    """ Download a single file to the destination directory

        args:
            filename(str) : file name
            baseurl(str) : base url of tezi image
            destdir(str) : destination directory
    """

    url = os.path.join(baseurl, filename)
    targetfile = os.path.join(destdir, filename)

    logging.debug(f"Downloading {filename}")
    urllib.request.urlretrieve(url, filename=targetfile)

def download_tezi_filename(filename, baseurl, destdir):
    """ Download a single file entry from the Toradex Easy Installer image filename or filelist
    tag.
        args:
            filename(str) : filename string (may contain target/unpack information)
            baseurl(str) : base url of easy installer image
            destdir(str) : destination directory
    """
    # Image format 3 supports "scrfile:destdir:unpack" format to control
    # where an image on the module should be placed. To download Tezi we
    # are only interested in the source file name.
    filename = filename.split(":")[0]
    download_file(filename, baseurl, destdir)

def download(image_url, destdir):
    """Downloads a Toradex Easy Installer image from a given URL to the a given directory

    Parameters:
        image_url (string): Source URL of the Toradex Easy Installer image (image.json location).
        destdir (string): Destination directory, must already exist.
    """
    ROOT_FILE_TAGS = ["u_boot_env", "prepare_script",
            "wrapup_script", "error_script", "license", "releasenotes",
            "marketing", "icon"]
    image_json_filename = os.path.basename(image_url)
    logging.debug(f"Downloading image json {image_json_filename}")
    req = urllib.request.urlopen(image_url)
    content =  req.read().decode(req.headers.get_content_charset() or "utf-8")

    f = open(os.path.join(destdir, image_json_filename), "w")
    f.write(content)
    f.close()

    # Parse image json file to find all required files for this image
    logging.debug(f"Parsing configuration file {image_json_filename}...")
    imagejson = json.loads(content)

    image_base_url = os.path.dirname(image_url)
    for tag in ROOT_FILE_TAGS:
        if tag not in imagejson:
            continue
        filename = imagejson[tag]
        download_file(filename, image_base_url, destdir)

    # Search recursively through the whole image json to find all json keys with
    # name "filename". Those point to a file we have to download too.
    filelist = list(find("filename", imagejson))
    for filename in filelist:
        download_tezi_filename(filename, image_base_url, destdir)

    filelists = list(find("filelist", imagejson))
    for filelist in filelists:
        for filename in filelist:
            download_tezi_filename(filename, image_base_url, destdir)
