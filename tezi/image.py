"""Helpers for handling image.json file in a TEZI Image."""

import json
import logging
import os
import shlex
import subprocess

from tezi.errors import (TeziError, InvalidDataError,
                         SourceInFilelistError, TargetInFilelistError)
from tezi.utils import get_unpack_command

log = logging.getLogger("torizon." + __name__)

DEFAULT_IMAGE_JSON_FILENAME = "image.json"


# TODO: It is advisable to test the usage of this class with every supported `config_format`.
#       In particular, we should test it when new `config_format`s become available in TEZI.
class ImageConfig:
    """Read/write image.json of a TEZI image.

    At the moment this class is a wrapper over a dictionary so that it mimics the
    previous interface where we loaded the file and changed the fields as needed.
    Additionally, it provides methods for dealing with the `filelist` field which
    is one usually requiring some extra work to properly handle (see methods
    `add_files` and `search_filelist`).

    Example usage::

        config = ImageConfig("a/b/image.json")
        # Check if a file is already in 'filelist':
        config.search_filelist(src="sota.tar.gz")
        # Check some directories are being populated:
        config.search_filelist(tgt="/ostree/deploy/torizon/var/lib/docker/")
        config.search_filelist(tgt="/ostree/deploy/torizon/var/sota/storage/docker-compose/")
        # Add file(s) to the filelist:
        config.add_files(
            [("sota.tar.gz", "/ostree/deploy/torizon/var/sota/", True)],
            image_dir=output_dir, update_size=True,
            fail_src_present=True, fail_tgt_present=True)
        config.save(config_fname)
    """

    def __init__(self, fname=None):
        assert fname, "Input file is currently required"
        self.fname = None
        self.json_data = None
        self.rootfs_content = None     # Ref. to rootfs "content" field within json_data
        self.rootfs_filelist = None    # Ref. to rootfs "filelist" field
        self.load(fname)

    def load(self, fname):
        """Load and parse a image.json file, save its name"""
        self.json_data = None
        self.rootfs_content = None
        self.rootfs_filelist = None
        with open(fname, "r", encoding="utf-8") as infile:
            # TODO: Consider defining a schema/checking against it.
            self.json_data = json.load(infile)
        self.fname = fname

    def add_files(self, entries, image_dir=None,
                  update_size=False, fail_src_present=True, fail_tgt_present=True):
        """Add files to the 'filelist' element

        The 'filelist' element of a Toradex Easy Installer configuration file
        lists files to be copied to the device (more specifically to the 'otaroot'
        partition on the device) at installation time. Each entry of the list has a
        source file, a destination and an optional boolean indicating if the source
        must be unpacked when being copied to the destination directory.

        :param entries: Iterable where each element is a 2/3-tuple or a string with
                        elements separated by a colon character (:).
        :param image_dir: Path to directory containing the full TEZI image where
                          from where the files will be take by TEZI; this is required
                          when `update_size` is True.
        :param update_size: Boolean indicating whether the 'uncompressed_size' field
                            must be updated.
        :param fail_src_present: Fail if a source file is already present in the current
                                 'filelist'; this should be set to True if the given
                                 source file is expected to be unique in the 'filelist'.
        :param fail_tgt_present: Fail if a destination directory is already present in the
                                 current 'filelist'; this should be set to True if the given
                                 source file is expected to be unique in the 'filelist'.

        In case of an error an exception derived from `TeziError` will be raised.
        """
        # Basic validation:
        assert update_size in [True, False], \
            f"Invalid value passed for update_size: {update_size}"
        if update_size:
            assert image_dir, "`image_dir` must be passed when updating size"

        self._init_rootfs_filelist()

        # Prepare data for searching:
        curr_srcs = set()
        curr_tgts = set()
        if fail_src_present:
            for flentry in self.rootfs_filelist:
                decoded = self._decode_flentry(flentry)
                curr_srcs.add(os.path.normpath(decoded["src"]))
        if fail_tgt_present:
            for flentry in self.rootfs_filelist:
                decoded = self._decode_flentry(flentry)
                curr_tgts.add(os.path.normpath(decoded["tgt"]))

        extra_size = 0
        for flentry in entries:
            decoded = self._decode_flentry(flentry)
            if fail_src_present and os.path.normpath(decoded["src"]) in curr_srcs:
                raise SourceInFilelistError(f"{decoded['src']} already in filelist")
            if fail_tgt_present and os.path.normpath(decoded["tgt"]) in curr_tgts:
                raise TargetInFilelistError(f"{decoded['tgt']} already in filelist")
            if update_size:
                _size_bytes = self._get_size(image_dir, decoded["src"], decoded["unpack"])
                extra_size += _size_bytes / 1024 / 1024
            self.rootfs_filelist.append(self._encode_flentry(decoded))

        if update_size:
            self.rootfs_content["uncompressed_size"] += extra_size

    @staticmethod
    def _decode_flentry(entry):
        """Decode a 'filelist' entry from a image.json file

        :return: dictionary with fields "src", "tgt" and "unpack".
        """
        if isinstance(entry, str):
            entry = entry.split(":")
            if len(entry) >= 3:
                # Convert third field into standard boolean
                _unpack = entry[2].lower()
                if _unpack not in ["true", "false"]:
                    raise InvalidDataError(f"Could not decode filelist entry {entry}")
                entry[2] = _unpack == "true"
            entry = tuple(entry)
        res = None
        if isinstance(entry, tuple) and len(entry) == 2:
            res = {"src": entry[0], "tgt": entry[1], "unpack": None}
        elif isinstance(entry, tuple) and len(entry) == 3:
            res = {"src": entry[0], "tgt": entry[1], "unpack": entry[2]}
        else:
            raise InvalidDataError(f"Could not decode filelist entry {entry}")
        return res

    @staticmethod
    def _encode_flentry(decoded):
        """Reverse the work of _decode_flentry()"""
        if decoded["unpack"] is None:
            # unpack field not specified.
            entry = [decoded["src"], decoded["tgt"]]
        else:
            entry = [decoded["src"], decoded["tgt"],
                     "true" if decoded["unpack"] else "false"]
        return ":".join(entry)

    @staticmethod
    def _get_size(image_dir, filename, unpack):
        """Get the size of a file possibly uncompressing it"""

        full_fname = os.path.join(image_dir, filename)
        if unpack:
            _output = subprocess.check_output(
                "set -o pipefail; "
                f"cat {shlex.quote(full_fname)} | {get_unpack_command(filename)} | wc -c",
                shell=True)
            size = int(_output)
        else:
            stat = os.stat(full_fname)
            size = stat.st_size
        log.debug(f"Size of {full_fname} is {size} bytes.")
        return size

    def search_filelist(self, src=None, tgt=None):
        """Search the 'filelist' for an entry with a given src and/or tgt"""

        self._init_rootfs_filelist(auto_create=False)
        if self.rootfs_filelist is None:
            log.debug("No 'filelist' present in image configuration.")
            return None
        if src:
            src = os.path.normpath(src)
        if tgt:
            tgt = os.path.normpath(tgt)
        for flentry in self.rootfs_filelist:
            decoded = self._decode_flentry(flentry)
            if src and tgt:
                if (os.path.normpath(decoded["src"]) == src and
                        os.path.normpath(decoded["tgt"]) == tgt):
                    return flentry
            elif src:
                if os.path.normpath(decoded["src"]) == src:
                    return flentry
            elif tgt:
                if os.path.normpath(decoded["tgt"]) == tgt:
                    return flentry
        return None

    def save(self, fname=None):
        """Save image.json file

        :param fname: Name of file to save into; if not passed the file will be
                      saved with the name used when load() was called.
        """

        self._init_rootfs_filelist(auto_create=False)
        if self.rootfs_filelist is not None:
            # If the 'filelist' element was employed we need config format >= 3.
            _config_format = self.json_data.get("config_format", 1)
            # Build system produces "config_format" as string: fix it.
            if isinstance(_config_format, str):
                _config_format = int(_config_format)
            self.json_data["config_format"] = max(3, _config_format)
        with open(fname or self.fname, "w", encoding="utf-8") as outfile:
            json.dump(self.json_data, outfile, indent=4)

    def __getitem__(self, key):
        """Read value of internal JSON data at index `key`"""
        assert self.json_data, "No config file loaded"
        log.debug(f"Reading json_data[key], value '{self.json_data[key]}'")
        return self.json_data[key]

    def __setitem__(self, key, value):
        """Assign value to internal JSON data at index `key`"""
        assert self.json_data, "No config file loaded"
        log.debug(f"Writing json_data[key] = '{value}'")
        self.json_data[key] = value

    def __contains__(self, key):
        """Check membership in internal JSON data"""
        assert self.json_data, "No config file loaded"
        return key in self.json_data

    def _init_rootfs_filelist(self, auto_create=True):
        if self.rootfs_filelist is not None:
            return

        self._init_rootfs_content()
        if "filelist" in self.rootfs_content:
            self.rootfs_filelist = self.rootfs_content["filelist"]
        elif auto_create:
            self.rootfs_filelist = []
            self.rootfs_content["filelist"] = self.rootfs_filelist

    def _init_rootfs_content(self):
        if self.rootfs_content is not None:
            return

        self.rootfs_content = self._find_rootfs_content()
        if self.rootfs_content is None:
            raise TeziError(f"Couldn't find rootfs 'content' inside {self.fname}")

    def _find_rootfs_content(self):
        """Find root filesystem 'content' element"""
        assert self.json_data, "No config file loaded"

        if "mtddevs" in self.json_data:
            # NAND module
            for dev in self.json_data["mtddevs"]:
                if dev["name"] != "ubi":
                    continue
                for volume in dev["ubivolumes"]:
                    if volume["name"] != "rootfs":
                        continue
                    return volume["content"]

        elif "blockdevs" in self.json_data:
            # eMMC module
            for dev in self.json_data["blockdevs"]:
                if "partitions" not in dev:
                    continue
                for part in dev["partitions"]:
                    if part["content"]["label"] != "otaroot":
                        continue
                    return part["content"]

        return None
