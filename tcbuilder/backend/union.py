import logging
import os
import shutil
import gi
gi.require_version('OSTree', '1.0')
from gi.repository import GLib, Gio, OSTree
from tcbuilder.backend.common import TorizonCoreBuilderError
from tcbuilder.backend import ostree

log = logging.getLogger("torizon." + __name__)

def commit_changes(repo, csum, diff_dir, branch_name):
    # ostree --repo=toradex-os-tree commit -b my-changes --tree=ref=<csum> --tree=dir=my-changes
    log.debug("Committing changes from %s to %s", diff_dir, branch_name)
    if not repo.prepare_transaction():
        raise TorizonCoreBuilderError("Error preparing transaction.")

    mt = OSTree.MutableTree.new()

    # --tree=ref=<csum>
    result, root, commit = repo.read_commit(csum)
    if not result:
        raise TorizonCoreBuilderError("Read base commit failed.")
    print(root, commit)

    result = repo.write_directory_to_mtree(root, mt)
    if not result:
        raise TorizonCoreBuilderError("Write base tree failed.")

    # --tree=dir=my-changes
    changesdir_fd = os.open(diff_dir, os.O_DIRECTORY)
    if not repo.write_dfd_to_mtree(changesdir_fd, ".", mt):
        raise TorizonCoreBuilderError("Adding directory to commit failed.")

    result, root = repo.write_mtree(mt)
    if not result:
        raise TorizonCoreBuilderError("Write mtree failed.")

    result, commit = repo.write_commit(None, None, None, None, root)
    if not result:
        raise TorizonCoreBuilderError("Write commit failed.")

    repo.transaction_set_ref(None, branch_name, commit)
    result, stats = repo.commit_transaction()
    if not result:
        raise TorizonCoreBuilderError("Commit failed.")

    log.debug("Transaction committed. %s bytes %s objects written.", str(
        stats.content_bytes_written), str(stats.content_objects_written))

    return commit

def union_changes(storage_dir, diff_dir, sysroot_dir, ostree_archive_dir, union_branch):
    try:
        sysroot = ostree.load_sysroot(sysroot_dir)
        deployment = sysroot.get_deployments()[0]
        base_csum = deployment.get_csum()
        sysroot.unload()

        repo = ostree.open_ostree(ostree_archive_dir)

        # Create new commit with the changes overlayed in a single transaction
        final_commit = commit_changes(repo, base_csum, diff_dir, union_branch)

        return final_commit
    except Exception as ex:
        raise TorizonCoreBuilderError("issue occurred during creating a commit for changes. Contact Developer") \
             from ex
