"""
This module offers the `UnpackedInitramfs` class to manipulate an unpacked initramfs file.
"""

import logging
import os
import subprocess
import shutil

from tcbuilder.errors import \
    (InvalidArgumentError, InvalidDataError, PathNotExistError, TorizonCoreBuilderError)
from tcbuilder.backend.common import \
    (get_storage_dir, is_file_type_fit, OSTREE_ROOT_DEPLOY_PATH)
from tcbuilder.backend import kernel as kernel_be
from tcbuilder.backend import splash as splash_be
from tcbuilder.backend import ostree
from tcbuilder.backend.kernelfit import KernelFit

log = logging.getLogger("torizon." + __name__)

MAX_INITRAMFS_FILE_SIZE = 64*1024*1024
# Initramfs binary has the same root subdir path as the kernel
OSTREE_INITRAMFS_SUBDIR_PATH = kernel_be.OSTREE_KERNEL_SUBDIR_PATH
OSTREE_INITRAMFS_FILENAME = "initramfs.img"

UNPACKED_INITRAMFS_DIR = "initramfs_{suffix}"


def check_initramfs_data_size(data):
    """Check if data is above the maximum defined initramfs file size."""

    if len(data) > MAX_INITRAMFS_FILE_SIZE:
        raise InvalidDataError(
            f"New initramfs file size of {data/1024:.2f} kiB would exceed "
            f"limit of {MAX_INITRAMFS_FILE_SIZE/1024:.2f} kiB. Aborting.")


def get_initramfs_subdir():
    """Get the versioned initramfs path."""

    storage_dir = get_storage_dir()
    src_sysroot_dir = os.path.join(storage_dir, "sysroot")
    src_sysroot = ostree.load_sysroot(src_sysroot_dir)
    csum, _ = ostree.get_deployment_info_from_sysroot(src_sysroot)
    kernel_version = ostree.get_kernel_version(src_sysroot.repo(), csum)
    return OSTREE_INITRAMFS_SUBDIR_PATH.format(kver=kernel_version)


def find_initramfs_in_sysroot():
    """
    Find initramfs binary path in the unpacked image sysroot. Raises an error if
    it cannot find it.

    :returns: String with absolute path of the initramfs binary inside sysroot.
    """

    storage_dir = get_storage_dir()
    sysroot_path = os.path.join(storage_dir, "sysroot")

    # As the initramfs path is composed of directories named after the deployment commit and the
    # kernel version, get them via OSTree metadata.
    sysroot_obj = ostree.load_sysroot(sysroot_path)
    csum, _ = ostree.get_deployment_info_from_sysroot(sysroot_obj)
    kernel_version = ostree.get_kernel_version(sysroot_obj.repo(), csum)
    # Add deployment index part to checksum string, which is 0 for a new deployment
    csum += ".0"

    initramfs_path = os.path.join(
        OSTREE_ROOT_DEPLOY_PATH.format(csum=csum),
        OSTREE_INITRAMFS_SUBDIR_PATH.format(kver=kernel_version)
    )
    initramfs_path = os.path.join(sysroot_path, initramfs_path, OSTREE_INITRAMFS_FILENAME)

    if os.path.isfile(initramfs_path):
        log.debug(f"Initramfs found at '{initramfs_path}'")
    else:
        raise PathNotExistError("Initramfs not found in unpacked sysroot. Aborting.")

    return initramfs_path


def find_initramfs_in_changes_dir(changes_dir, basename=None):
    """Find path of initramfs binary in the given changes directory."""

    initramfs_subdir = get_initramfs_subdir()
    initramfs_src_dir = os.path.join(changes_dir, initramfs_subdir)
    initramfs_src_path = os.path.join(initramfs_src_dir, basename or OSTREE_INITRAMFS_FILENAME)
    if os.path.isfile(initramfs_src_path):
        log.debug(f"Initramfs found at '{initramfs_src_path}'", )
    else:
        log.debug(f"Initramfs not found at '{initramfs_src_path}'")
        return None

    return initramfs_src_path


def _get_initramfs_path(source, fixed_path=None):
    """Get initramfs file path according to source."""

    if source == "fixed":
        return fixed_path, source
    if source == "sysroot":
        return find_initramfs_in_sysroot(), source

    changes_dir = splash_be.get_splash_changes_dir()
    changes_path = find_initramfs_in_changes_dir(changes_dir)
    if source == "auto":
        if changes_path:
            return changes_path, "changes"
        return find_initramfs_in_sysroot(), "sysroot"

    if source == "changes":
        return changes_path, source
    raise InvalidArgumentError(f"_get_initramfs_path(): invalid initramfs source '{source}'")


def _get_kernel_path(source, fixed_path=None):
    """Get kernel file path according to source."""

    if source == "fixed":
        return fixed_path, source
    if source == "sysroot":
        return kernel_be.find_kernel_in_sysroot(), source

    changes_dir = kernel_be.get_kernel_changes_dir()
    changes_path = kernel_be.find_kernel_in_changes_dir(changes_dir)
    if source == "auto":
        if changes_path:
            return changes_path, "changes"
        return kernel_be.find_kernel_in_sysroot(), "sysroot"

    if source == "changes":
        return changes_path, source
    raise InvalidArgumentError(f"_get_kernel_path(): invalid kernel source '{source}'")


def extract_initramfs_from_fit(fit):
    """Extract initramfs data from a FIT object and save it to a file."""

    initramfs_name, initramfs_data = fit.extract_default_ramdisk()

    changes_dir = kernel_be.get_kernel_changes_dir()
    os.makedirs(changes_dir, exist_ok=True)
    initramfs_path = os.path.join(changes_dir, initramfs_name)
    with open(initramfs_path, "wb") as fhandle:
        fhandle.write(initramfs_data)
    log.debug(f"Extracted initramfs node '{initramfs_name}' inside FIT to '{initramfs_path}'.")
    return initramfs_path


def stage_kernel_fit(fit, dst_path=None):
    """Create kernel FIT file from given object and stage it for commit.

    The staging is performed by default; but, if `dst_path` is specified, then
    the FIT image is copied over to that path.
    """

    changes_dir = kernel_be.get_kernel_changes_dir()
    os.makedirs(changes_dir, exist_ok=True)
    src_path = os.path.join(changes_dir, kernel_be.KERNEL_FIT_FILENAME)
    log.debug(f"Writing contents to {src_path}")
    with open(src_path, "wb") as fhandle:
        fit.write(fhandle)

    # If the new file was created successfully, remove any previous kernel FIT and move
    # it to its respective union command "staging dir" or to the specified destination.
    if dst_path is None:
        dst_path = os.path.join(
            changes_dir,
            kernel_be.get_kernel_subdir(), kernel_be.KERNEL_FIT_FILENAME)

    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    if os.path.isfile(dst_path):
        os.remove(dst_path)
    log.debug(f"Moving {src_path} -> {dst_path}")
    shutil.move(src_path, dst_path)


def stage_initramfs_contents(data, dst_path=None):
    """Create initramfs file from given data and stage it for commit.

    The staging is performed by default; but, if dst_path is specified, then
    the generated initramfs file is copied over to that path.
    """

    changes_dir = splash_be.get_splash_changes_dir()
    os.makedirs(changes_dir, exist_ok=True)
    src_path = os.path.join(changes_dir, OSTREE_INITRAMFS_FILENAME)
    log.debug(f"Writing contents to {src_path}")
    with open(src_path, "wb") as fhandle:
        fhandle.write(data)

    # If the new file was created successfully, remove any previous initramfs file and
    # move it to its respective union command "staging dir" or to the specified destination.
    if dst_path is None:
        dst_path = os.path.join(
            changes_dir,
            get_initramfs_subdir(), OSTREE_INITRAMFS_FILENAME)

    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    if os.path.isfile(dst_path):
        os.remove(dst_path)
    log.debug(f"Moving {src_path} -> {dst_path}")
    shutil.move(src_path, dst_path)


class UnpackedInitramfs:
    """
    Context Manager to handle an initramfs file, or the initramfs contents of a kernel FIT.

    Unpacks a gzipped initramfs obtained according to 'source' and makes the corresponding
    directory tree path available while inside the runtime context, allowing direct access and
    modification of its contents e.g. read/add/remove/modify files or directories.

    Once the context ends the unpacked directory tree is packed and gzipped back to a file
    (or inside the kernel FIT), which is then copied to a "staging directory", ready to be
    processed by the union command. This step can be skipped by setting the 'repack' variable
    to 'False'. The unpacked directory is always deleted at the end of the context.

    Args:
        source: Indicates the location to search for the kernel FIT or initramfs file
                Possible values are: 'sysroot', 'changes', 'auto' or 'fixed'
                If the value is set to:
                - 'sysroot': Only the unpacked sysroot directory will be checked
                - 'changes': Only the appropriate changes directory will be checked
                - 'auto': First search in the appropriate changes directory; if the file is
                          not found there, search in the unpacked sysroot directory.
                - 'fixed': Get the input from a fixed path specified via `src_file`.

        src_file: Full path to the FIT image (FIT case) or to the initramfs file to be taken
                  as input when `source` is "fixed".
        dst_file: Final destination path for the output FIT image (FIT case) or for the initramfs
                  file; this is optional and independent of `source`. When specified, it prevents
                  the normal staging of the output file.
        repack: Boolean variable that tells whether the unpacked initramfs is repacked and staged
                at the end of the context. 'True' by default.

    Usage example:
    --------------------------------------------------------------------------------------------
    with UnpackedInitramfs(source="auto", repack=True) as irfs_obj:
        irfs_path = irfs_obj.get_path()
        # Unpacked initramfs path available (irfs_path) inside this block.
        # Any file modification made inside irfs_path will be saved once
        # execution leaves this block of code.

        # While inside the context the value of 'repack' can be changed
        # at any time if needed.
        irfs_obj.set_repack(False)

    # Once outside the block, the unpacked initramfs directory will be packed back and staged if
    # 'repack' is set to 'True'.
    --------------------------------------------------------------------------------------------

    NOTE: If source is set to 'changes' and no file is found in the corresponding changes
          directory, the get_path() method will return 'None'.
          If no file is found for 'sysroot' and 'auto' source types an exception will be thrown
          during initialization.
    """

    def __init__(self, source="auto", *, src_file=None, dst_file=None, repack=True):
        # Ensure valid source was passed:
        assert source in ["auto", "sysroot", "changes", "fixed"], \
            f"UnpackedInitramfs: Invalid source: '{source}'."
        if source == "fixed":
            assert src_file, "UnpackedInitramfs: src_file must be passed."
        else:
            assert not src_file, "UnpackedInitramfs: src_file must not be passed."

        # The kernel type is always determined from the kernel in the sysroot.
        log.debug("UnpackedInitramfs: Checking if unpacked OS image kernel is in FIT format.")
        self.kernel_is_fit = is_file_type_fit(kernel_be.find_kernel_in_sysroot())
        log.debug("UnpackedInitramfs: source='%s', kernel_is_fit=%s.",
                  source, str(self.kernel_is_fit))

        # Object holding a representation for the kernel FIT image.
        self.fit_obj = None
        # Source file: path to the initramfs file or the FIT image from where the initramfs
        # contents is to be taken.
        self.src_file = None
        # Destination file: path to the initramfs file or the FIT image to which the initramfs
        # contents is to be written (optional).
        self.dst_file = dst_file
        self.src_initramfs_file = None
        self.repack = repack
        suffix = ''

        if self.kernel_is_fit:
            log.debug("UnpackedInitramfs: Searching for kernel FIT to extract initramfs.")
            self.src_file, suffix = _get_kernel_path(source, src_file)
            if self.src_file:
                log.debug("UnpackedInitramfs: Loading kernel FIT from '%s'.", self.src_file)
                with open(self.src_file, "rb") as fhandle:
                    self.fit_obj = KernelFit(fhandle)
                self.src_initramfs_file = extract_initramfs_from_fit(self.fit_obj)
        else:
            log.debug("UnpackedInitramfs: Searching for initramfs.")
            self.src_file, suffix = _get_initramfs_path(source, src_file)
            self.src_initramfs_file = self.src_file

        # Define directory where the initramfs file will be unpacked.
        self.unpacked_initramfs_dir = os.path.join(
            get_storage_dir(), UNPACKED_INITRAMFS_DIR.format(suffix=suffix))

        log.debug("UnpackedInitramfs: src_file='%s', src_initramfs_file='%s'.",
                  self.src_file, self.src_initramfs_file)

    def __enter__(self):
        """Unpack initramfs contents to storage."""

        if not self.src_initramfs_file:
            log.debug("__enter__(): Unable to find initramfs contents, skipping unpack.")
            self.unpacked_initramfs_dir = None
            return self

        log.debug(f"__enter__(): Unpacking initramfs to {self.unpacked_initramfs_dir}")
        if os.path.isdir(self.unpacked_initramfs_dir):
            shutil.rmtree(self.unpacked_initramfs_dir)
        os.makedirs(self.unpacked_initramfs_dir)
        try:
            gzip_out = subprocess.check_output(["gzip", "-dc", self.src_initramfs_file])
            cpio_cmd = [
                "cpio", "--directory", self.unpacked_initramfs_dir,
                "--extract", "--make-directories"
            ]
            # gzip -dc initramfs.img |
            # cpio --directory=unpacked_initramfs_dir --extract --make-directories
            subprocess.check_output(cpio_cmd, input=gzip_out, stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as exc:
            # pylint: disable-next=raise-missing-from
            raise TorizonCoreBuilderError(exc.output.strip())

        log.debug(f"__enter__(): Initramfs contents available in {self.unpacked_initramfs_dir}")
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Repack initramfs contents in storage to changes directory."""

        if not self.unpacked_initramfs_dir:
            log.debug("__exit__(): Unpack not done, nothing to do.")
            return
        if not self.repack:
            log.debug(f"__exit__(): Skipping repack of {self.unpacked_initramfs_dir}")
            return

        try:
            log.debug(f"__exit__(): Repacking {self.unpacked_initramfs_dir}")
            # cd unpacked_initramfs_dir/ && find . -print | cpio --create --format=newc | gzip
            find_cmd = [
                "find", ".", "-print"
            ]
            cpio_cmd = [
                "cpio", "--directory", self.unpacked_initramfs_dir,
                "--create", "--format=newc"
            ]
            find_out = subprocess.check_output(find_cmd, cwd=self.unpacked_initramfs_dir)
            cpio_out = subprocess.check_output(cpio_cmd, input=find_out)
            gzip_out = subprocess.check_output("gzip", input=cpio_out)

            check_initramfs_data_size(gzip_out)

            if self.kernel_is_fit:
                # Update fit object with new initramfs contents
                initramfs_name = os.path.basename(self.src_initramfs_file)
                log.debug(f"Updating {initramfs_name} with {len(gzip_out)/1024:.2f} "
                          "kiB in size into FIT image.")
                self.fit_obj.update_ramdisk(initramfs_name, gzip_out)
                # Remove old initramfs file extracted from FIT
                log.debug(f"__exit__(): Removing {self.src_initramfs_file}")
                os.remove(self.src_initramfs_file)
                # Stage updated kernel FIT to be committed
                stage_kernel_fit(self.fit_obj, self.dst_file)
            else:
                # Stage updated initramfs to be committed
                log.debug(f"New initramfs file will be {len(gzip_out)/1024:.2f} kiB in size")
                stage_initramfs_contents(gzip_out, self.dst_file)
        except subprocess.CalledProcessError as exc:
            # pylint: disable-next=raise-missing-from
            raise TorizonCoreBuilderError(exc.output.strip())
        finally:
            log.debug(f"__exit__(): Removing directory {self.unpacked_initramfs_dir}")
            shutil.rmtree(self.unpacked_initramfs_dir)

    def get_path(self):
        """Get the path where the initramfs was unpacked."""
        return self.unpacked_initramfs_dir

    def set_repack(self, repack):
        """Set value of the repack variable."""
        self.repack = repack
