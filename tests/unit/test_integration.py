"""Integration test for TorizonCore Builder

Note: These tests heavily rely on the environment:
- /workdir needs to exist, and a Tezi image needs to be in /workdir/tezi
- fast-banana.png need to exist for the splash screen test
- /storage needs to exist, /storage/pytest will be used for testing
"""

import logging

import py
import pytest

from tcbuilder.backend import deploy, ostree, splash, unpack


@pytest.fixture(name="storage_dir", scope="module")
def fixture_storage_dir():
    """Initialize/cleanup storage directory for pytest"""
    storage_dir = py.path.local("/storage/pytest")
    if not storage_dir.isdir():
        storage_dir.mkdir()
    assert not storage_dir.join("tezi").isdir()
    assert not storage_dir.join("sysroot").isdir()
    assert not storage_dir.join("ostree-archive").isdir()
    assert not storage_dir.join("splash").isdir()

    yield storage_dir

    # /storage is bind mounted, we should not rm -rf it...
    logging.info(f"Cleaning up {str(storage_dir)}...")
    storage_dir.join("tezi").remove(rec=1)
    storage_dir.join("sysroot").remove(rec=1)
    storage_dir.join("ostree-archive").remove(rec=1)
    storage_dir.join("splash").remove(rec=1)

@pytest.fixture(name="deploy_dir", scope="module")
def fixture_deploy_dir():
    """Initialize deploy directory for pytest"""
    deploy_dir = py.path.local("/deploy")
    assert not deploy_dir.join("sysroot").isdir()
    deploy_dir.join("sysroot").mkdir()

    yield deploy_dir

    logging.info(f"Cleaning up {str(deploy_dir)}...")
    deploy_dir.join("sysroot").remove(rec=1)


def test_unpack(storage_dir, work_dir):
    """"Test unpack sub-command"""

    tezi = storage_dir.join("tezi")
    sysroot_dir = storage_dir.join("sysroot")
    ostree_archive = storage_dir.join("ostree-archive")

    tezi_src = work_dir.join("tezi")

    unpack.import_local_image(
        str(tezi_src), str(tezi), str(sysroot_dir), str(ostree_archive))

    sysroot = ostree.load_sysroot(str(sysroot_dir))
    csum, _kargs = ostree.get_deployment_info_from_sysroot(sysroot)

    print(csum)
    assert len(csum) > 1

    config = ostree_archive.join("config")
    assert "mode=archive-z2" in config.read()

def test_splash(storage_dir, work_dir):
    """"Test splash sub-command"""

    splash_work_dir = storage_dir.join("splash")
    ostree_archive = storage_dir.join("ostree-archive")

    splashimage = str(work_dir.join("fast-banana.png"))
    logging.info(f"Using {splashimage} as splash screen image.")
    splash.create_splash_initramfs(str(splash_work_dir), str(splashimage), str(ostree_archive))

def test_deploy_using_csum(storage_dir, deploy_dir, work_dir):
    """"Test deploy Tezi image sub-command"""

    tezi = storage_dir.join("tezi")
    sysroot_dir = storage_dir.join("sysroot")
    ostree_archive = storage_dir.join("ostree-archive")

    deploy_sysroot = deploy_dir.join("sysroot")

    sysroot = ostree.load_sysroot(str(sysroot_dir))
    csum, _kargs = ostree.get_deployment_info_from_sysroot(sysroot)

    output = work_dir.join("output")

    deploy.deploy_tezi_image(str(tezi), str(sysroot_dir), str(ostree_archive),
                             str(output), str(deploy_sysroot), csum)

    files = [str(outfile) for outfile in output.listdir()]

    assert any(("image.json" in outfile) for outfile in files)
    assert any(("bootfs.tar" in outfile) for outfile in files)
