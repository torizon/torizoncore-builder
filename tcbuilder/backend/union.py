import datetime
import logging
import os
import shutil

from tcbuilder.backend import ostree
from tcbuilder.backend.common import get_int_ostree_dir, SECBOOT_ARTIFACTS_DIR
from tcbuilder.backend.secboot import SIGNED_BOOTLOADER_ARTIFACTS_DIR
from tcbuilder.errors import OSTreeSigningError, TorizonCoreBuilderError

# pylint: disable=wrong-import-order,wrong-import-position
import gi
gi.require_version("OSTree", "1.0")
from gi.repository import GLib, OSTree, Gio
# pylint: enable=wrong-import-order,wrong-import-position

log = logging.getLogger("torizon." + __name__)


def remove_tcattr_files_from_ostree(mtree):
    """
    Remove all ".tcattr" (metadata) files before committing to OSTree so
    they won't end up in the final file system.
    """
    for filename in mtree.get_files().keys():
        if filename == '.tcattr':
            mtree.remove(filename, False)


def process_whiteouts(mtree, path="/"):

    remove_tcattr_files_from_ostree(mtree)

    # Check for opaque whiteouts
    if any(name == ostree.OSTREE_OPAQUE_WHITEOUT_NAME
           for name in mtree.get_files().keys()):
        log.debug(f"Removing all contents from {path}.")
        for name in mtree.get_files().keys():
            mtree.remove(name, False)
        return

    for name in mtree.get_files().keys():
        if name.startswith(ostree.OSTREE_WHITEOUT_PREFIX):
            mtree.remove(name, False)
            name_to_remove = name[4:]
            log.debug(f"Removing file {path}/{name_to_remove}.")
            try:
                result = mtree.remove(name_to_remove, False)
            except GLib.Error as glibex:
                log.debug(f"Removing file {name_to_remove}, False.")
                if glibex.matches(Gio.io_error_quark(), Gio.IOErrorEnum.NOT_FOUND):
                    log.warning(
                        f"  Can't remove {path}/{name_to_remove}: File not found. Ignoring...")
                else:
                    log.warning(
                        f"  Can't remove {path}/{name_to_remove}: {str(glibex)}. Ignoring...")
            else:
                log.debug(f"Removing file {name_to_remove}, {result}.")

    for dirname, submt in mtree.get_subdirs().items():
        process_whiteouts(submt, os.path.join(path, dirname))


def _sign_commit(repo, commit, ostree_key):
    """Sign a commit.

    :param repo: OSTree repository (OSTree.Repo).
    :param commit: Checksum of commit to be signed.
    :param ostree_key: Wrapper object for key information (OSTreeKey).
    """

    pk_file = ostree_key.get_sec_key_path()
    log.info("Signing commit '%s' with private-key file '%s'.", commit, pk_file)

    sign = None
    algo = ostree_key.get_key_algo()
    log.debug("Getting signing engine for algorithm '%s'.", algo)
    try:
        sign = OSTree.Sign.get_by_name(algo)
        if not sign:
            raise OSTreeSigningError(
                "OSTree.Sign.get_by_name returned no engine.")
    except (GLib.Error, OSTreeSigningError) as exc:
        raise OSTreeSigningError(
            f"Error: Could not obtain signing engine for algorithm '{algo}'.") from exc

    try:
        # Read the secret key from file.
        with open(pk_file, "r", encoding="utf-8") as seck:
            b64key = seck.read()
    except OSError as exc:
        raise TorizonCoreBuilderError(
            f"Error: Could not load private-key file '{pk_file}'.") from exc

    # Store key data into engine object.
    sign.set_sk(GLib.Variant("s", b64key))

    # Sign the commit.
    if not sign.commit(repo, commit, None):
        raise OSTreeSigningError(
            f"Failed to sign commit '{commit}'; aborting.")


# pylint: disable-next=too-many-locals
def _commit_changes(repo, ref, changes_dirs, branch_name, *,
                    subject=None, body=None,
                    ostree_key=None, pre_apply_callback=None):
    # ostree --repo=toradex-os-tree commit -b my-changes --tree=ref=<ref> --tree=dir=my-changes
    if not repo.prepare_transaction():
        raise TorizonCoreBuilderError("Error preparing transaction.")

    mtree = OSTree.MutableTree.new()

    # --tree=ref=<ref>
    result, root, csum = repo.read_commit(ref)
    if not result:
        raise TorizonCoreBuilderError("Read base commit failed.")

    result = repo.write_directory_to_mtree(root, mtree)
    if not result:
        raise TorizonCoreBuilderError("Write base tree failed.")

    # --tree=dir=my-changes
    for changes_dir in changes_dirs:
        # Inform upper layer about what we are going to do.
        if pre_apply_callback:
            pre_apply_callback(changes_dir)

        changesdir_fd = os.open(changes_dir, os.O_DIRECTORY)
        if not repo.write_dfd_to_mtree(changesdir_fd, ".", mtree):
            raise TorizonCoreBuilderError("Adding directory to commit failed.")

        log.debug("Processing whiteouts.")
        process_whiteouts(mtree)

        result, root = repo.write_mtree(mtree)
        if not result:
            raise TorizonCoreBuilderError("Write mtree failed.")

    result, commitvar, _state = repo.load_commit(csum)
    if not result:
        raise TorizonCoreBuilderError(f"Error loading parent commit {csum}.")

    # Unpack commit object, see OSTree src/libostree/ostree-repo-commit.c
    # We cannot use commitvar.unpack() here since this would lead to a pure
    # Python object. However, we want to retain the metadata as GLib.Variant
    # so we can transparently pass them to our commit. Otherwise we need to know
    # the whole GLib.Variant's structure, which we do not know (e.g. future
    # OSTree commits might add structured data we do not know about today).
    metadata = commitvar.get_child_value(0)
    #_orig_subject = commitvar.get_child_value(3).get_string()
    #_orig_body = commitvar.get_child_value(4).get_string()

    # TODO: Put metadata into a VariantDict to simplify manipulations.
    newmetadata = []
    timestamp = datetime.datetime.now()
    for ind in range(metadata.n_children()):
        val = metadata.get_child_value(ind)
        if val.get_child_value(0).get_string() == "version":
            # Adjust the "version" metadata.
            # "version" itself is a Variant, which just contains a string...
            version = val.get_child_value(1).get_child_value(0).get_string()
            version += "-tcbuilder." + timestamp.strftime("%Y%m%d%H%M%S")
            newmetadata.append(
                GLib.Variant.new_dict_entry(
                    GLib.Variant("s", "version"),
                    GLib.Variant("v", GLib.Variant("s", version))))
        elif val.get_child_value(0).get_string() == "ostree.ref-binding":
            # Adjust the "ostree.ref-binding" metadata to avoid ref bindings mismatch.
            newmetadata.append(
                GLib.Variant.new_dict_entry(
                    GLib.Variant("s", "ostree.ref-binding"),
                    GLib.Variant("v", GLib.Variant("as", [branch_name]))))
        elif val.get_child_value(0).get_string().startswith("ostree.composefs.digest"):
            # Drop this metadata field which will be set again when signing.
            log.debug("Dropping composefs digest from commit metadata.")
        else:
            # Pass everything else transparently.
            newmetadata.append(val)

    # GLib.Variant of type "a{sv}" (array of dictionaries), which is the
    # metadata obeject
    newmetadatavar = GLib.Variant.new_array(GLib.VariantType("{sv}"), newmetadata)

    # Add composefs properties (esp. digest) to the commit metadata.
    if ostree_key is not None:
        newmetadatavar_dict = GLib.VariantDict.new(newmetadatavar)
        assert repo.commit_add_composefs_metadata(0, newmetadatavar_dict, root, None)
        newmetadatavar = newmetadatavar_dict.end()

    if subject is None:
        isodatetime = timestamp.replace(microsecond=0).isoformat()
        subject = f"TorizonCore Builder union commit created at {isodatetime}"

    result, commit = repo.write_commit(csum, subject, body, newmetadatavar, root)
    if not result:
        raise TorizonCoreBuilderError("Write commit failed.")

    if ostree_key is not None:
        _sign_commit(repo, commit, ostree_key)

    repo.transaction_set_ref(None, branch_name, commit)
    result, stats = repo.commit_transaction()
    if not result:
        raise TorizonCoreBuilderError("Commit failed.")

    log.debug(f"Transaction committed. {stats.content_bytes_written} bytes "
              f"{stats.content_objects_written} objects written.")

    return commit


def union_changes(*,
                  changes_dir, union_branch, subject, body,
                  ostree_key=None, pre_apply_callback=None):
    """Create new commit with the changes overlaid in a single transaction."""

    repo = ostree.open_ostree(get_int_ostree_dir())
    commit = _commit_changes(
        repo, ostree.OSTREE_BASE_REF, changes_dir, union_branch,
        subject=subject, body=body,
        ostree_key=ostree_key, pre_apply_callback=pre_apply_callback)

    track_signed_bootloader(commit)

    return commit


def track_signed_bootloader(commit_hash):
    """
    If applicable, internally track the bootloader and fusing instructions text file in
    FLASH_BIN_SIGNING_DIR by copying them inside a directory named after commit_hash
    in SECBOOT_ARTIFACTS_DIR.

    :param commit_hash: OSTree commit hash to be associated with the signed bootloader
    """

    # Check if there's any signed bootloader artifacts to track, and if so store them to be
    # deployed with the new branch
    if (os.path.isdir(SIGNED_BOOTLOADER_ARTIFACTS_DIR) and
            os.listdir(SIGNED_BOOTLOADER_ARTIFACTS_DIR)):
        log.info("Found signed bootloader in storage. Applying changes.")

        # Create a new directory named after the commit hash (if it doesn't exist already)
        # and put the signed bootloader in it
        commit_dir = os.path.join(SECBOOT_ARTIFACTS_DIR, commit_hash)
        shutil.copytree(SIGNED_BOOTLOADER_ARTIFACTS_DIR, commit_dir, dirs_exist_ok=True)
        log.info(f"Signed bootloader will be applied when deploying {commit_hash} "
                 "to a local directory.")
