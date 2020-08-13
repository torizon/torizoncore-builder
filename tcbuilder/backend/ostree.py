"""Common OSTree functions

Helper functions for commonly used OSTree functions.
"""

import logging
import os

import gi
gi.require_version("OSTree", "1.0")
from gi.repository import Gio, GLib, OSTree

from tcbuilder.errors import TorizonCoreBuilderError

log = logging.getLogger("torizon." + __name__)

OSTREE_BASE_REF = "base"

def open_ostree(ostree_dir):
    repo = OSTree.Repo.new(Gio.File.new_for_path(ostree_dir))
    if not repo.open(None):
        raise TorizonCoreBuilderError("Opening the archive OSTree repository failed.")
    return repo

def create_ostree(ostree_dir, mode:OSTree.RepoMode = OSTree.RepoMode.ARCHIVE_Z2):
    repo = OSTree.Repo.new(Gio.File.new_for_path(ostree_dir))
    repo.create(mode, None)
    return repo

def load_sysroot(sysroot_dir):
    sysroot = OSTree.Sysroot.new(Gio.File.new_for_path(sysroot_dir))
    sysroot.load()
    return sysroot

def get_deployment_info_from_sysroot(sysroot):
    # Get commit csum and kernel arguments from the currenty sysroot

    # There is a single deployment in our OSTree sysroots
    deployment = sysroot.get_deployments()[0]

    # Get the origin refspec
    #refhash = deployment.get_origin().get_string("origin", "refspec")

    bootparser = deployment.get_bootconfig()
    kargs = bootparser.get('options')
    csum = deployment.get_csum()
    sysroot.unload()

    return csum, kargs

def get_metadata_from_ref(repo, ref):
    result, commitvar, _state = repo.load_commit(ref)
    if not result:
        raise TorizonCoreBuilderError("Error loading commit {}.".format(ref))

    # commitvar is GLib.Variant, use unpack to get a Python dictionary
    commit = commitvar.unpack()

    # Unpack commit object, see OSTree src/libostree/ostree-repo-commit.c
    metadata, _parent, _, subject, body, _time, _content_csum, _metadata_csum = commit

    return metadata, subject, body

def pull_remote_ref(repo, uri, ref, remote=None, progress=None):
    options = GLib.Variant("a{sv}", {
        "gpg-verify": GLib.Variant("b", False)
    })

    log.debug("Pulling remote {} reference {}", uri, ref)

    if not repo.remote_add("origin", remote, options=options):
        raise TorizonCoreBuilderError("Error adding remote.")

    # ostree --repo=toradex-os-tree pull origin torizon/torizon-core-docker --depth=0

    options = GLib.Variant("a{sv}", {
        "refs": GLib.Variant.new_strv([ref]),
        "depth": GLib.Variant("i", 0),
        "override-remote-name": GLib.Variant('s', remote),
    })

    if progress is not None:
        asyncprogress = OSTree.AsyncProgress.new()
        asyncprogress.connect("changed", progress)
    else:
        asyncprogress = None

    if not repo.pull_with_options("origin", options, progress=asyncprogress):
        raise TorizonCoreBuilderError("Error pulling contents from local repository.")

def pull_local_ref(repo, repopath, csum, remote=None):
    """ fetches reference from local repository

        args:

            repo(OSTree.Repo) - repo object
            repopath(str) - absolute path of local repository to pull from
            ref(str) - remote reference to pull
            remote = remote name used in refspec

        raises:
            Exception - for failure to perform operations
    """
    log.debug("Pulling from local repository {} commit checksum {}", repopath, csum)

    # ostree --repo=toradex-os-tree pull-local --remote=${branch} ${repopath} ${ref} --depth=0
    options = GLib.Variant("a{sv}", {
        "refs": GLib.Variant.new_strv([csum]),
        "depth": GLib.Variant("i", 0),
        "override-remote-name": GLib.Variant('s', remote),
    })

    if not repo.pull_with_options("file://" + repopath, options):
        raise TorizonCoreBuilderError("Error pulling contents from local repository.")

    # Note: In theory we can do this with two options in one go, but that seems
    # to validate ref-bindings... (has probably something to do with Collection IDs etc..)
    #"refs": GLib.Variant.new_strv(["base"]),
    #"override-commit-ids": GLib.Variant.new_strv([ref]),
    repo.set_collection_ref_immediate(OSTree.CollectionRef.new(None, OSTREE_BASE_REF), csum)

def ls(repo, path, commit):
    """ return a list of files and directories in a ostree repo under path

        args:
            repo(OSTree.Repo) - repo object
            path(str) - absolute path which we want to enumerate
            commit(str) - the ostree commit hash or name

        return:
            file_list(list) - list of files and directories under path

        raises:
            TorizonCoreBuilderError - if commit does not exist
    """
    # Make sure we don't end the path with / because this confuses ostree
    path = os.path.realpath(path)
    ret, root, _commit = repo.read_commit(commit)
    if not ret:
        raise TorizonCoreBuilderError(f"Error couldn't reat commit: {commit}")

    sub_path = root.resolve_relative_path(path)

    file_list = sub_path.enumerate_children(
        "*", Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS, None)

    return list(map(lambda f: f.get_name(), file_list))
