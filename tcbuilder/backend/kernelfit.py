"""
This module offers the class `KernelFit` for manipulating FIT images.
"""

import logging
import re
from typing import Dict, List, Union, Optional, Any, BinaryIO

import libfdt
from libfdt import QUIET_NOTFOUND

log = logging.getLogger("torizon." + __name__)

MAX_FIT_IMAGE_SIZE = 64*1024*1024
CONFIG_NODE_PATH = "/configurations"
IMAGES_NODE_PATH = "/images"
DTB_IMAGE_NAME_PROP = "fdt"
DTB_IMAGE_DATA_PROP = "data"
DTBO_NODE_SUFFIX = ".dtbo"
DTB_NODE_SUFFIX = ".dtb"
DEFAULT_DTB_PROP = "default"
RAMDISK_IMAGE_NAME_PROP = "ramdisk"
RAMDISK_IMAGE_DATA_PROP = "data"

SIGNATURE_PROPS_TO_DELETE = [
    "hashed-nodes",
    "hashed-strings",
    "padding",
    "sign-images",
    "signer-name",
    "signer-version",
    "timestamp",
    "value"
]

HASH_PROPS_TO_DELETE = [
    "value"
]

DELETE_PROPS_ON_DTB_COPY = True


class KernelFitException(Exception):
    """Exception thrown by KernelFit class methods and internal helpers"""


def _get_prop(fdt: libfdt.Fdt,
              node_path: str, prop_name: str, defval: Any = None):
    try:
        node_off = fdt.path_offset(node_path)
        value = fdt.getprop(node_off, prop_name)
        return value
    except libfdt.FdtException as exc:
        if defval is not None:
            log.debug("_get_prop: ignoring libfdt exception %s.", str(exc))
            return defval
        raise KernelFitException(
            f"Could not read property {node_path}/{prop_name} from FDT.") \
            from exc


def _del_prop(fdt: libfdt.Fdt,
              node_path: str, prop_name: str, ignore_errors: bool = True):
    try:
        fdt_size_org = fdt.totalsize()
        node_off = fdt.path_offset(node_path)
        fdt.delprop(node_off, prop_name, quiet=QUIET_NOTFOUND)
        fdt.pack()
        fdt_size_new = fdt.totalsize()
        log.debug("_del_prop(%s/%s): size: %d -> %d",
                  node_path, prop_name, fdt_size_org, fdt_size_new)
    except libfdt.FdtException as exc:
        if ignore_errors:
            log.debug("_del_prop: ignoring libfdt exception %s.", str(exc))
            return
        raise KernelFitException(
            f"Could not delete property {node_path}/{prop_name} from FDT.") \
            from exc


def _set_prop(fdt: libfdt.Fdt,
              ptype: str, node_path: str, prop_name: str, val: Any):
    fdt_size_org = fdt.totalsize()
    # Make room from the property name and value:
    fdt.resize(fdt.totalsize() + (len(prop_name) + len(val) + 64))

    # Set property:
    node_off = fdt.path_offset(node_path)

    if ptype == "raw":
        fdt.setprop(node_off, prop_name, val)
    elif ptype == "str":
        fdt.setprop_str(node_off, prop_name, val)
    elif ptype == "u32":
        fdt.setprop_u32(node_off, prop_name, val)
    elif ptype == "u64":
        fdt.setprop_u64(node_off, prop_name, val)
    else:
        raise KernelFitException(
            f"Invalid ptype={ptype} passed when setting {node_path}/{prop_name}.")

    # Determine final size:
    fdt.pack()
    fdt_size_new = fdt.totalsize()
    log.debug("_set_prop(%s/%s): size: %d -> %d",
              node_path, prop_name, fdt_size_org, fdt_size_new)


def _node_present(fdt: libfdt.Fdt, *args: str):
    node_path = "/".join(args)
    try:
        node_off = fdt.path_offset(node_path, quiet=QUIET_NOTFOUND)
    except libfdt.FdtException as exc:
        raise KernelFitException(
            f"Error obtaining offset of '{node_path}' within FDT.") \
            from exc
    return node_off >= 0


def _estimate_node_size(fdt: libfdt.Fdt, node_offset: int):
    """Estimate the size in bytes of an FDT node.

    Estimate the size in bytes of an FDT node, including its
    properties and children recursively.
    """
    def _align4(num: int) -> int:
        """Round up to next multiple of 4."""
        return (num + 3) & ~3

    size = 0

    # Opening tag (FDT_BEGIN_NODE) + name + NUL + padding
    name = fdt.get_name(node_offset)
    size += 4  # token
    size += _align4(len(name) + 1)  # name + '\0' + padding

    # Properties
    prop_off = fdt.first_property_offset(node_offset)
    while prop_off >= 0:
        prop = fdt.get_property_by_offset(prop_off)
        size += 4  # token
        size += 4  # len
        size += 4  # nameoff
        size += _align4(len(prop))  # property value + padding
        prop_off = fdt.next_property_offset(prop_off, QUIET_NOTFOUND)

    # Children
    child_off = fdt.first_subnode(node_offset, QUIET_NOTFOUND)
    while child_off >= 0:
        size += _estimate_node_size(fdt, child_off)
        child_off = fdt.next_subnode(child_off, QUIET_NOTFOUND)

    # End node tag
    size += 4

    return size


def _copy_node_across_fdts(fdt_src: libfdt.Fdt, src_off: int,
                           fdt_dst: libfdt.Fdt, dst_parent_off: int,
                           new_name: str = None):
    if new_name is None:
        new_name = fdt_src.get_name(src_off)
    dst_off = fdt_dst.add_subnode(dst_parent_off, new_name)

    # copy properties
    poff = fdt_src.first_property_offset(src_off, QUIET_NOTFOUND)
    while poff >= 0:
        prop = fdt_src.get_property_by_offset(poff)
        fdt_dst.setprop(dst_off, prop.name, bytes(prop))
        poff = fdt_src.next_property_offset(poff, QUIET_NOTFOUND)

    # copy children
    child_off = fdt_src.first_subnode(src_off, QUIET_NOTFOUND)
    while child_off >= 0:
        _copy_node_across_fdts(fdt_src, child_off, fdt_dst, dst_off)
        child_off = fdt_src.next_subnode(child_off, QUIET_NOTFOUND)

    return dst_off


def _copy_node(fdt: libfdt.Fdt, node_path: str, src_name: str, dst_name: str):
    log.debug("_copy_node: node_path='%s', src_name='%s', dst_name='%s'",
              node_path, src_name, dst_name)

    fdt_size_org = fdt.totalsize()

    # We cannot traverse the FDT and change it simultaneously (because the iterators are
    # invalidated); to solve this we create an auxiliary FDT to hold the to-be-copied node
    # temporarily.
    src_off = fdt.path_offset(f"{node_path}/{src_name}")
    fdt_aux_size = _estimate_node_size(fdt, src_off)
    log.debug("_copy_node: fdt_aux_size=%d", fdt_aux_size)
    # Since size is estimated add some extra.
    fdt_aux_size += (fdt_aux_size // 10) * 12 + 256
    fdt_aux = libfdt.Fdt.create_empty_tree(fdt_aux_size)
    dst_aux_off = fdt.path_offset("/")
    _copy_node_across_fdts(fdt, src_off, fdt_aux, dst_aux_off, new_name=dst_name)

    # Ensure there's enough room for the new node on the destination FDT:
    fdt.resize(fdt.totalsize() + fdt_aux_size)

    # Copy the auxiliary FDT into a new node:
    src_off = fdt_aux.path_offset(f"/{dst_name}")
    dst_off = fdt.path_offset(node_path)
    _copy_node_across_fdts(fdt_aux, src_off, fdt, dst_off)

    # Determine final size:
    fdt.pack()
    fdt_size_new = fdt.totalsize()
    log.debug("_copy_node: size: %d -> %d", fdt_size_org, fdt_size_new)


def _remove_prefix(strval: str, prefix: str, force: bool = True):
    if strval.startswith(prefix):
        return strval[len(prefix):]
    if force:
        raise KernelFitException(
            f"String '{strval}' does not have expected prefix '{prefix}'.")
    return strval


class KernelFit:
    """Class for manipulating a kernel FIT image."""

    def __init__(self, fhandle: BinaryIO = None, *,
                 conf_prefix: str = "conf-",
                 dtb_prefix: str = "", dtbimg_prefix: str = "fdt-"):
        """
        Class representing a FIT image with methods to manipulate it.

        Args:
            fhandle (BinaryIO): handle to FIT image file opened in binary mode.
            conf_prefix (str): prefix used with configuration nodes.
            dtb_prefix (str): first prefix added to DTB/DTBO files packed inside
                the FIT image.
            dtbimg_prefix (str): second prefix added to DTB/DTBO nodes in the
                image section of the FIT image.

        Example:
            ```dts
            images {
                fdt-freescale_imx8mp-verdin-nonwifi-dahlia.dtb {
                |__||________|
                (3)    (2)
                }
            }
            configurations {
                default = "conf-freescale_imx8mp-verdin-nonwifi-dahlia.dtb";
                conf-freescale_imx8mp-verdin-nonwifi-dahlia.dtb {
                |___||________|
                 (1)    (2)
                }
                ...
            }
            # Legend:
            # (1): conf_prefix
            # (2): dtb_prefix
            # (3): dtbimg_prefix
            ```
        """
        self.fdt = None
        self.dtb_prefix = dtb_prefix
        self.conf_prefix = conf_prefix
        self.dtbimg_prefix = dtbimg_prefix
        if fhandle:
            self._read(fhandle)

    def _read(self, fhandle: BinaryIO = None) -> None:
        data = fhandle.read(MAX_FIT_IMAGE_SIZE+1)
        if len(data) > MAX_FIT_IMAGE_SIZE:
            raise KernelFitException(
                f"FIT image size exceeds limit of {MAX_FIT_IMAGE_SIZE} bytes.")
        self.fdt = libfdt.Fdt(data)
        log.debug("Loaded FIT image; totalsize=%d.", self.fdt.totalsize())

    def read(self, fhandle: BinaryIO = None) -> None:
        """Load a FIT image from the given file handle.

        Args:
            fhandle (BinaryIO): handle to file opened for reading in binary mode.
        """
        self._read(fhandle)

    def write(self, fhandle: BinaryIO = None) -> None:
        """Write a FIT image into a file/stream.

        Write the in-memory representation of a FIT image into a file.

        Args:
            fhandle (BinaryIO): handle to file opened for writing in binary mode.
        """
        fhandle.write(self.fdt.as_bytearray())

    def _list_nodes(self, node_path: str, pattern: str) -> List[str]:
        """List nodes whose name match a given pattern (regex)"""
        pattern = re.compile(pattern)
        nodeoff = self.fdt.path_offset(node_path)
        subnodeoff = self.fdt.first_subnode(nodeoff)
        nodes = []
        while subnodeoff >= 0:
            name = self.fdt.get_name(subnodeoff)
            if pattern.fullmatch(name):
                nodes.append(name)
            subnodeoff = self.fdt.next_subnode(subnodeoff, QUIET_NOTFOUND)
        return nodes

    def _get_dtb_conf_pref_suf(self, overlay=False):
        if overlay:
            pref = self.conf_prefix
            suf = DTBO_NODE_SUFFIX
        else:
            pref = f"{self.conf_prefix}{self.dtb_prefix}"
            suf = DTB_NODE_SUFFIX
        return (pref, suf)

    def _get_dtb_image_pref_suf(self, overlay=False):
        if overlay:
            pref = self.dtbimg_prefix
            suf = ".dtbo"
        else:
            pref = f"{self.dtbimg_prefix}{self.dtb_prefix}"
            suf = ".dtb"
        return (pref, suf)

    # pylint: disable-next=no-self-use
    def _get_std_node_path(self, ntype, *args):
        if ntype == "conf":
            node_path = "/".join([CONFIG_NODE_PATH, *args])
        elif ntype == "image":
            node_path = "/".join([IMAGES_NODE_PATH, *args])
        else:
            assert False, f"_get_std_node_path: bad parameter: ntype='{ntype}'"
        return node_path

    def _del_node(self, ntype: str, node_name: str) -> None:
        node_path = self._get_std_node_path(ntype, node_name)
        siz0 = self.fdt.totalsize()
        self.fdt.del_node(self.fdt.path_offset(node_path), node_name)
        self.fdt.pack()
        siz1 = self.fdt.totalsize()
        log.debug("Deleted node '%s' (size: %d -> %d).", node_path, siz0, siz1)

    def get_dtb_entries_helper(self, pref: str, suf: str) -> List[Dict[str, str]]:
        """Get DTB/DTBO configuration entries with a given prefix and suffix.

        Returns:
           list[dict]: A list of dictionaries, each with the fields:
               - conf_name (str): Name of the configuration node.
               - image_name (str): Name of the image referenced by the configuration
                     node.
               - file_name (str): This is expected to represent the name of the file
                     that originated the entry in the FIT image.
        """
        sufre = suf.replace('.', '\\.')
        names = self._list_nodes(CONFIG_NODE_PATH, f"{pref}.*{sufre}")
        # Go over nodes extracting basic information for an entry:
        nodes = []
        for name in names:
            conf_name = name
            image_name = _get_prop(
                self.fdt,
                self._get_std_node_path("conf", conf_name), DTB_IMAGE_NAME_PROP)
            image_name = image_name.as_str()
            file_name = _remove_prefix(conf_name, pref)
            entry = {
                "conf_name": conf_name,
                "image_name": image_name,
                "file_name": file_name
            }
            nodes.append(entry)
        return nodes

    def get_dtb_list(self, overlay=False) -> List[Dict[str, str]]:
        """Get DTB/DTBO configuration entries.

        Args:
            overlay (bool): False selects DTs while True selects DTBOs.
        See Also:
            get_dtb_entries_helper(): This generates the actual return value.
        """
        return self.get_dtb_entries_helper(*self._get_dtb_conf_pref_suf(overlay))

    def _make_templ_name(self, ntype, overlay):
        if ntype == "conf":
            pref, suf = self._get_dtb_conf_pref_suf(overlay)
        elif ntype == "image":
            pref, suf = self._get_dtb_image_pref_suf(overlay)
        else:
            assert False, f"_make_templ_name: bad parameter: ntype='{ntype}'"
        return f"_{pref}template{suf}"

    def _dtb_templ_present(self, ntype, overlay):
        chd_node_name = self._make_templ_name(ntype, overlay)
        par_node_name = self._get_std_node_path(ntype)
        res = _node_present(self.fdt, par_node_name, chd_node_name)
        log.debug("Node '%s' was %s under '%s'.",
                  chd_node_name, ["not found", "found"][res], par_node_name)
        return res

    def _copy_dtb(self,
                  src_conf_name: str, src_image_name: str,
                  dst_conf_name: str, dst_image_name: str):
        # Copy configuration:
        conf_node_path = self._get_std_node_path("conf")
        _copy_node(self.fdt,
                   node_path=conf_node_path,
                   src_name=src_conf_name,
                   dst_name=dst_conf_name)

        # Copy image:
        image_node_path = self._get_std_node_path("image")
        _copy_node(self.fdt,
                   node_path=image_node_path,
                   src_name=src_image_name,
                   dst_name=dst_image_name)

        # Fix the template reference: config -> image:
        image_name_prop_path = self._get_std_node_path("conf", dst_conf_name)
        _set_prop(self.fdt, "str",
                  image_name_prop_path, DTB_IMAGE_NAME_PROP, dst_image_name)

        # Set the "data" prop to avoid taking up space:
        image_data_prop_path = self._get_std_node_path("image", dst_image_name)
        _set_prop(self.fdt, "str",
                  image_data_prop_path, DTB_IMAGE_DATA_PROP, "empty")

        if not DELETE_PROPS_ON_DTB_COPY:
            return

        # Clean configuration node:
        for index in range(8):
            par_node_path = self._get_std_node_path("conf", dst_conf_name)
            chd_node_name = f"signature-{index}"
            chd_node_path = self._get_std_node_path("conf", dst_conf_name, chd_node_name)
            if _node_present(self.fdt, par_node_path, chd_node_name):
                for prop_name in SIGNATURE_PROPS_TO_DELETE:
                    _del_prop(self.fdt, chd_node_path, prop_name)

        # Clean image node:
        for index in range(8):
            par_node_path = self._get_std_node_path("image", dst_image_name)
            chd_node_name = f"hash-{index}"
            chd_node_path = self._get_std_node_path("image", dst_image_name, chd_node_name)
            if _node_present(self.fdt, par_node_path, chd_node_name):
                for prop_name in HASH_PROPS_TO_DELETE:
                    _del_prop(self.fdt, chd_node_path, prop_name)

    def _make_dtb_templ(self, conf_name, overlay):
        log.debug("Making template from '%s'.", conf_name)

        src_conf_name = conf_name
        dst_conf_name = self._make_templ_name("conf", overlay)

        image_name_prop_path = self._get_std_node_path("conf", conf_name)
        src_image_name = _get_prop(self.fdt, image_name_prop_path, DTB_IMAGE_NAME_PROP)
        src_image_name = src_image_name.as_str()
        dst_image_name = self._make_templ_name("image", overlay)

        self._copy_dtb(src_conf_name, src_image_name,
                       dst_conf_name, dst_image_name)

    def del_dtb(self, file_name: str, *, overlay: bool = False) -> bool:
        """Delete DTB/DTBO entry.

        Delete both the configuration and image nodes related to a given
        DTB/DTBO file name.

        :param file_name: Name of the DTB/DTBO file associated with the entry;
            this name will be prefixed appropriately to determine the actual
            entry names (configuration/image) to be deleted.
        """

        # Check if the node corresponding to the file is present in the image.
        dtb_list = self.get_dtb_list(overlay)
        dtb_list_entry = None
        for dle in dtb_list:
            if file_name == dle["file_name"]:
                dtb_list_entry = dle
                break
        if dtb_list_entry is None:
            log.debug("Configuration node corresponding to '%s' was not "
                      "found in the FIT image.", file_name)
            return False

        log.debug("Configuration node corresponding to '%s' was found "
                  "in the FIT image.", file_name)

        if self._dtb_templ_present("conf", overlay):
            # If we already have a template it's okay to delete this node.
            pass
        elif len(dtb_list) > 1:
            # If there are other nodes it's okay to delete this node.
            pass
        elif len(dtb_list) == 1:
            # There's only one DTB/DTBO node left; copy it as a template.
            self._make_dtb_templ(dtb_list_entry["conf_name"], overlay)

        # Delete configuration and corresponding image.
        self._del_node("image", dtb_list_entry["image_name"])
        self._del_node("conf", dtb_list_entry["conf_name"])

        return True

    def add_dtb(self,
                file_name: str,
                data: Optional[Union[bytes, bytearray]] = None, *,
                overlay=False, overwrite=True, set_default=True) -> None:
        """Add DTB/DTBO entry to the FIT image.

        A DTB/DTBO entry inside the FIT image is made up of two nodes:

        One representing a configuration (which combines the kernel, ramdisk,
        DTB to be selected by the bootloader) and another representing the image,
        that is, the actual DTB data. Both of them are created by this method.

        :param file_name: Name of the DTB/DTBO file associated with the entry;
            this name will be prefixed appropriately to determine the actual
            entry names (configuration/image) to be added.
        :param data: Data of the DTB/DTBO; this is optional mainly to simplify
            testing.
        :param overlay: True to indicate the entries relate to an overlay (DTBO)
            rather than a plain device-tree.
        :param overwrite: Whether to overwrite existing entries with the same
            name; if this is False and an entry exists, an exception will be
            thrown.
        :param set_default:" Whether to set the "default" configuration field
            in the FIT image to the specified DTB.
        """

        # Check if the node corresponding to the file is present in the image.
        dtb_list = self.get_dtb_list(overlay)
        dtb_list_entry = None
        for dle in dtb_list:
            if file_name == dle["file_name"]:
                dtb_list_entry = dle
                break
        if dtb_list_entry is not None:
            if overwrite:
                log.debug("Configuration node corresponding to '%s' was found "
                          "in the FIT image and will be overwritten.", file_name)
                self.del_dtb(file_name, overlay=overlay)
            else:
                raise KernelFitException(
                    f"add_dtb: Configuration node corresponding to '{file_name}' "
                    f"is already present in the FIT image.")

        # Determine the template to use:
        dtb_list = self.get_dtb_list(overlay)
        if dtb_list:
            # Use existing DTB/DTBO as template:
            src_conf_name = dtb_list[0]["conf_name"]
            src_image_name = dtb_list[0]["image_name"]
        else:
            # Use previously saved template:
            src_conf_name = self._make_templ_name("conf", overlay)
            src_image_name = self._make_templ_name("image", overlay)

        conf_pref_suf = self._get_dtb_conf_pref_suf(overlay)
        if not file_name.endswith(conf_pref_suf[1]):
            raise KernelFitException(
                f"add_dtb: Filename {file_name} does not end with "
                f"'{conf_pref_suf[1]}'.")

        image_pref_suf = self._get_dtb_image_pref_suf(overlay)

        dst_conf_name = f"{conf_pref_suf[0]}{file_name}"
        dst_image_name = f"{image_pref_suf[0]}{file_name}"

        self._copy_dtb(src_conf_name, src_image_name,
                       dst_conf_name, dst_image_name)

        if data is not None:
            _set_prop(self.fdt, "raw",
                      self._get_std_node_path("image", dst_image_name),
                      DTB_IMAGE_DATA_PROP, data)

        if not overlay and set_default:
            self.set_default_dtb(file_name)

    def set_default_dtb(self, file_name: str, *, check=True) -> None:
        """Set the default configuration field in the FIT."""

        conf_pref_suf = self._get_dtb_conf_pref_suf()
        if not file_name.endswith(conf_pref_suf[1]):
            raise KernelFitException(
                f"set_default_dtb: Filename {file_name} does not end with "
                f"'{conf_pref_suf[1]}'.")

        conf_name = f"{conf_pref_suf[0]}{file_name}"

        if not _node_present(self.fdt, CONFIG_NODE_PATH, conf_name):
            log.debug("Configuration node '%s' does not exist", conf_name)
            if check:
                raise KernelFitException(
                    f"set_default_dtb: Configuration node '{conf_name}'"
                    " does not exist.")

        conf_node_path = self._get_std_node_path("conf")
        _set_prop(self.fdt, "str",
                  conf_node_path, DEFAULT_DTB_PROP, conf_name)

    def get_default_dtb(self) -> Optional[str]:
        """Get the default configuration field in the FIT."""

        conf_node_path = self._get_std_node_path("conf")
        default_dtb = _get_prop(self.fdt, conf_node_path, DEFAULT_DTB_PROP, defval="unset")

        if str(default_dtb) == "unset":
            log.debug("Default configuration node not set.")
            return None
        return default_dtb.as_str()

    def extract_dtb(self, file_name: str, *, overlay=False) -> bytearray:
        """Extract the data of a DTB/DTBO entry.

        :param file_name: Name of the DTB/DTBO file associated with the entry;
            this name will be prefixed appropriately to determine the actual
            entry names (configuration/image) to be searched.
        :param overlay: True to indicate the entries relate to an overlay (DTBO)
            rather than a plain device-tree.
        :returns: Raw data as a bytearray.
        """

        # Check if the node corresponding to the file is present in the image.
        dtb_list = self.get_dtb_list(overlay)
        dtb_list_entry = None
        for dle in dtb_list:
            if file_name == dle["file_name"]:
                dtb_list_entry = dle
                break
        if dtb_list_entry is None:
            raise KernelFitException(
                f"extract_dtb: Configuration node corresponding to '{file_name}' "
                f"was not found in the FIT image.")

        img_name = dtb_list_entry["image_name"]
        img_data = _get_prop(
            self.fdt,
            self._get_std_node_path("image", img_name), DTB_IMAGE_DATA_PROP)
        img_data = bytes(img_data)
        return img_data

    def update_ramdisk(self, ramdisk_name: str, data: Union[bytes, bytearray]) -> None:
        """Update the data contents of a ramdisk node.

        Args:
            ramdisk_name (str): Name of the ramdisk node to be updated.
            data (bytes): New data to be written in the node. Any previous data
                          will be overwritten.
        """

        ramdisk_path = self._get_std_node_path("image", ramdisk_name)

        if not _node_present(self.fdt, ramdisk_path):
            raise KernelFitException(
                f"update_ramdisk: ramdisk path '{ramdisk_path}' does not exist.")

        log.debug("Updating ramdisk entry '%s'.", ramdisk_name)
        _set_prop(self.fdt, "raw", ramdisk_path, RAMDISK_IMAGE_DATA_PROP, data)

        # Remove relevant properties from hash nodes:
        for index in range(8):
            hash_node_name = f"hash-{index}"
            hash_node_path = self._get_std_node_path("image", ramdisk_name, hash_node_name)
            if _node_present(self.fdt, ramdisk_path, hash_node_name):
                for prop_name in HASH_PROPS_TO_DELETE:
                    _del_prop(self.fdt, hash_node_path, prop_name)

    def extract_ramdisk(self, conf_name: str) -> tuple[str, bytearray]:
        """Extract the data of a ramdisk entry in a given DTB configuration node.

        Args:
            conf_name (str): Name of the configuration node.

        :returns: Tuple with the ramdisk node name, and its raw data as a bytearray.
        """
        # Check if the given conf node is a DTB one
        conf_pref_suf = self._get_dtb_conf_pref_suf()
        if not conf_name.endswith(conf_pref_suf[1]):
            raise KernelFitException(
                f"extract_ramdisk: conf_name {conf_name} does not end with "
                f"'{conf_pref_suf[1]}'.")

        # Check if the configuration path exists
        config_path = self._get_std_node_path("conf", conf_name)
        if not _node_present(self.fdt, config_path):
            raise KernelFitException(
                f"extract_ramdisk: Configuration path '{config_path}' does not exist.")

        ramdisk_name = _get_prop(
            self.fdt, config_path, RAMDISK_IMAGE_NAME_PROP)
        ramdisk_name = ramdisk_name.as_str()

        log.debug("Extracting ramdisk entry '%s'", ramdisk_name)
        ramdisk_data = _get_prop(
            self.fdt,
            self._get_std_node_path("image", ramdisk_name), RAMDISK_IMAGE_DATA_PROP)
        return ramdisk_name, bytearray(ramdisk_data)

    def extract_default_ramdisk(self) -> tuple[str, bytearray]:
        """Extract the data of the ramdisk entry of the default configuration node.

        This method will first try to extract the ramdisk entry pointed by the default
        configuration node if it is set. Otherwise it will extract the ramdisk pointed
        by the first DTB config node found in get_dtb_list().

        :returns: Tuple with the ramdisk node name, and its raw data as a bytearray.
        """
        default_config = self.get_default_dtb()

        if default_config:
            log.debug("Using default config node '%s' to get the ramdisk data.", default_config)
            return self.extract_ramdisk(default_config)

        # Default config not set, so use the first DTB config node on the DTB list
        # We don't want the overlay configs, as those don't have a ramdisk entry
        dtb_list = self.get_dtb_list()
        if not dtb_list:
            raise KernelFitException(
                "extract_default_ramdisk: Could not find any DTB configuration "
                "entries in the kernel FIT.")
        config_node = dtb_list[0]["conf_name"]
        log.debug("Using configuration node '%s' to get the ramdisk data.", config_node)
        return self.extract_ramdisk(config_node)

# TODO: Consider creating unit tests.
#
# if __name__ == "__main__":
#     logging.basicConfig(level=logging.DEBUG,
#                         format='%(asctime)s: %(levelname)s: %(message)s')

#     import os
#     import sys
#     # Directory containing a "vmlinuz.org" must be passed.
#     os.chdir(sys.argv[1])

#     FIT_FILE_IN = "vmlinuz.org"
#     FIT_FILE_OUT = "vmlinuz-out"
#     with open(FIT_FILE_IN, "rb") as _fhandle:
#         fit = KernelFit(_fhandle, dtb_prefix="freescale_")

#     print("\nDTBs:")
#     dtb_nodes = fit.get_dtb_list()
#     for node in dtb_nodes:
#         print(node)

#     print("\nDTBOs:")
#     dto_nodes = fit.get_dtb_list(True)
#     for node in dto_nodes:
#         print(node)

#     assert fit.del_dtb("conf-DUMMY1.dtb") is False

#     # import random

#     # Delete all nodes, except one.
#     print("\nDeleting all DTBs but one.")
#     dtb_nodes = fit.get_dtb_list()
#     # random.shuffle(dtb_nodes)
#     for node in dtb_nodes[:-1]:
#         assert fit.del_dtb(node["file_name"]) is True
#     print("DTBs (after deleting all but one):")
#     dtb_nodes = fit.get_dtb_list()
#     for node in dtb_nodes:
#         print(node)

#     # Delete all nodes, except one.
#     print("\nDeleting all DTBOs but one.")
#     dtbo_nodes = fit.get_dtb_list(True)
#     # random.shuffle(dtbo_nodes)
#     for node in dtbo_nodes[:-1]:
#         assert fit.del_dtb(node["file_name"], overlay=True) is True
#     print("DTBOs (after deleting all but one):")
#     dtbo_nodes = fit.get_dtb_list(True)
#     for node in dtbo_nodes:
#         print(node)

#     with open(f"{FIT_FILE_OUT}-onedtbdtbo.fit", "wb") as _fhandle:
#         fit.write(_fhandle)

#     # # Delete last DTB node.
#     # print("\nDeleting last DTB node.")
#     # dtb_nodes = fit.get_dtb_list()
#     # assert len(dtb_nodes) == 1
#     # assert fit.del_dtb(dtb_nodes[0]["file_name"]) == True
#     # assert len(fit.get_dtb_list()) == 0
#     # assert fit._dtb_templ_present("conf", False) == True

#     # # Delete last DTBO node.
#     # print("\nDeleting last DTBO node.")
#     # dtb_nodes = fit.get_dtb_list(True)
#     # assert len(dtb_nodes) == 1
#     # assert fit.del_dtb(dtb_nodes[0]["file_name"], overlay=True) == True
#     # assert len(fit.get_dtb_list(True)) == 0
#     # assert fit._dtb_templ_present("conf", True) == True

#     with open(f"{FIT_FILE_OUT}-nodtbdtbo.fit", "wb") as _fhandle:
#         fit.write(_fhandle)

#     fit.set_default_dtb("TEST_DTB.dtb", check=False)
#     fit.add_dtb("TEST_DTB.dtb", overlay=False)
#     fit.set_default_dtb("TEST_DTB.dtb")
#     fit.add_dtb("TEST_DTBO.dtbo", overlay=True)

#     fit.add_dtb("imx8mp-verdin-wifi-yavia.dtb", overlay=False)
#     fit.add_dtb("verdin-imx8mp_spidev_overlay.dtbo", b"aaaabbbb", overlay=True)

#     with open(f"{FIT_FILE_OUT}-dummyadds.fit", "wb") as _fhandle:
#         fit.write(_fhandle)
