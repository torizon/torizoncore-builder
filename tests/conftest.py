"""Shared test fixtures"""
import logging

import py
import pytest

@pytest.fixture(name="work_dir", scope="module")
def fixture_work_dir():
    """Initialize work directory for pytest"""
    work_dir = py.path.local("/workdir")

    # Make sure a Tezi image is available in /workdir/tezi
    # Ideally we should automatically download a test image here...
    assert work_dir.join("tezi").isdir()

    yield work_dir

    # Delete output
    logging.info("Cleaning up /workdir/output...")
    if work_dir.join("output").isdir():
        work_dir.join("output").remove(rec=1)
    logging.info("Cleaning up /workdir/bundle...")
    if work_dir.join("bundle").isdir():
        work_dir.join("bundle").remove(rec=1)
