import datetime
import logging
import os

from tcbuilder.backend import ostree
from tcbuilder.backend.ostree import OSTREE_WHITEOUT_PREFIX, OSTREE_OPAQUE_WHITEOUT_NAME
from tcbuilder.errors import TorizonCoreBuilderError

# pylint: disable=wrong-import-order,wrong-import-position
import gi
gi.require_version("OSTree", "1.0")
from gi.repository import GLib, OSTree
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
    if any(name == OSTREE_OPAQUE_WHITEOUT_NAME for name in mtree.get_files().keys()):
        log.debug(f"Removing all contents from {path}.")
        for name in mtree.get_files().keys():
            mtree.remove(name, False)
        return

    for name in mtree.get_files().keys():
        if name.startswith(OSTREE_WHITEOUT_PREFIX):
            mtree.remove(name, False)
            name_to_remove = name[4:]
            log.debug(f"Removing file {path}/{name_to_remove}.")
            result = mtree.remove(name_to_remove, False)
            log.debug(f"Removing file {name_to_remove}, {result}.")

    for dirname, submt in mtree.get_subdirs().items():
        process_whiteouts(submt, os.path.join(path, dirname))


# pylint: disable=too-many-locals
def commit_changes(repo, ref, changes_dirs, branch_name,
                   subject, body, pre_apply_callback=None):
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
    _orig_subject = commitvar.get_child_value(3).get_string()
    _orig_body = commitvar.get_child_value(4).get_string()

    # Append something to the version object
    newmetadata = []
    timestamp = datetime.datetime.now()
    for ind in range(metadata.n_children()):
        val = metadata.get_child_value(ind)
        # Adjust the "version" metadata, and pass everything else transparently
        if val.get_child_value(0).get_string() == 'version':
            # Version itself is a Variant, which just contains a string...
            version = val.get_child_value(1).get_child_value(0).get_string()
            version += "-tcbuilder." + timestamp.strftime("%Y%m%d%H%M%S")
            newmetadata.append(
                GLib.Variant.new_dict_entry(
                    GLib.Variant("s", "version"),
                    GLib.Variant('v', GLib.Variant("s", version))))
        else:
            newmetadata.append(val)

    if subject is None:
        isodatetime = timestamp.replace(microsecond=0).isoformat()
        subject = f"TorizonCore Builder union commit created at {isodatetime}"

    # GLib.Variant of type "a{sv}" (array of dictionaries), which is the
    # metadata obeject
    newmetadatavar = GLib.Variant.new_array(GLib.VariantType("{sv}"), newmetadata)

    result, commit = repo.write_commit(csum, subject, body, newmetadatavar, root)
    if not result:
        raise TorizonCoreBuilderError("Write commit failed.")

    repo.transaction_set_ref(None, branch_name, commit)
    result, stats = repo.commit_transaction()
    if not result:
        raise TorizonCoreBuilderError("Commit failed.")

    log.debug(f"Transaction committed. {stats.content_bytes_written} bytes "
              f"{stats.content_objects_written} objects written.")

    return commit

# pylint: enable=too-many-locals


def union_changes(changes_dir, ostree_archive_dir, union_branch,
                  subject, body, pre_apply_callback=None):
    repo = ostree.open_ostree(ostree_archive_dir)

    # Create new commit with the changes overlayed in a single transaction
    final_commit = commit_changes(
        repo, ostree.OSTREE_BASE_REF, changes_dir, union_branch,
        subject, body, pre_apply_callback=pre_apply_callback)

    return final_commit
