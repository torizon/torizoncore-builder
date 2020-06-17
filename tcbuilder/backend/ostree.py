import gi

gi.require_version("OSTree", "1.0")

from gi.repository import GLib, Gio, OSTree

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

