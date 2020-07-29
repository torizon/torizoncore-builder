import gi
import logging

gi.require_version("OSTree", "1.0")

from gi.repository import GLib, Gio, OSTree

log = logging.getLogger("torizon." + __name__)

def open_ostree(ostree_dir):
    repo = OSTree.Repo.new(Gio.File.new_for_path(ostree_dir))
    repo.open()
    return repo

def create_ostree(ostree_dir, mode:OSTree.RepoMode = OSTree.RepoMode.ARCHIVE_Z2):
    repo = OSTree.Repo.new(Gio.File.new_for_path(ostree_dir))
    repo.create(mode, None)
    return repo

def load_sysroot(sysroot_dir):
    sysroot = OSTree.Sysroot.new(Gio.File.new_for_path(sysroot_dir))
    sysroot.load()
    return sysroot

def get_ref_from_sysroot(sysroot):
    # Get deployment hash of current Toradex Easy Installer image

    # There is a single deployment in our OSTree sysroots
    deployment = sysroot.get_deployments()[0]

    # Get the origin refspec
    #refhash = deployment.get_origin().get_string("origin", "refspec")

    bootparser = deployment.get_bootconfig()
    kargs = bootparser.get('options')
    ref = deployment.get_csum()
    sysroot.unload()

    return ref, kargs

def get_metadata_from_ref(repo, ref):
    result, commitvar, state = repo.load_commit(ref)
    if not result:
        raise TorizonCoreBuilderError("Error loading commit {}.".format(ref))

    # commitvar is GLib.Variant, use unpack to get a Python dictionary
    commit = commitvar.unpack()

    # Unpack commit object, see OSTree src/libostree/ostree-repo-commit.c
    metadata, parent, unused, subject, body, time, content_csum, metadata_csum = commit

    return metadata, subject, body

def pull_remote_ref(repo, uri, ref, remote=None, progress=None):
    # ostree --repo=toradex-os-tree remote add origin http://feeds.toradex.com/ostree/nightly/colibri-imx7/ --no-gpg-verify
    options = GLib.Variant("a{sv}", {
        "gpg-verify": GLib.Variant("b", False)
    })

    log.debug("Pulling remote %s reference %s", uri, ref)

    if not repo.remote_add("origin", remote, options=options):
        raise TorizonCoreBuilderError("Error adding remote.")

    # ostree --repo=toradex-os-tree pull origin torizon/torizon-core-docker --depth=1

    options = GLib.Variant("a{sv}", {
        "refs": GLib.Variant.new_strv([ref]),
        "depth": GLib.Variant("i", 1),
        "override-remote-name": GLib.Variant('s', remote),
    })

    if progress is not None:
        asyncprogress = OSTree.AsyncProgress.new()
        asyncprogress.connect("changed", progress)
    else:
        asyncprogress = None

    if not repo.pull_with_options("origin", options, progress=asyncprogress):
        raise TorizonCoreBuilderError("Error pulling contents from local repository.")

def pull_local_ref(repo, repopath, ref, remote=None):
    """ fetches reference from local repository

        args:

            repo(OSTree.Repo) - repo object
            repopath(str) - absolute path of local repository to pull from
            ref(str) - remote reference to pull
            remote = remote name used in refspec

        raises:
            Exception - for failure to perform operations
    """
    log.debug("Pulling from local repository %s reference %s", repopath, ref)

    # ostree --repo=toradex-os-tree pull-local --remote=${branch} ${repopath} ${ref}
    options = GLib.Variant("a{sv}", {
        "refs": GLib.Variant.new_strv([ref]),
    #    "depth": GLib.Variant("i", 1),
        "override-remote-name": GLib.Variant('s', remote),
    })

    if not repo.pull_with_options("file://" + repopath, options):
        raise TorizonCoreBuilderError("Error pulling contents from local repository.")

