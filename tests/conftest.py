"""Shared test configuration.

The RAW execution guard (audit A10) takes a real OS lock under a per-user
directory. Tests must never touch the user's directory or contend with a
real invocation, so the whole session points the guard at a private
temporary directory. The guard itself stays fully in force.
"""

from __future__ import annotations

import os

import pytest

from sdlc.raw_execution_guard import LOCK_DIRECTORY_ENVIRONMENT


@pytest.fixture(autouse=True, scope="session")
def _private_lock_directory(tmp_path_factory):
    previous = os.environ.get(LOCK_DIRECTORY_ENVIRONMENT)
    os.environ[LOCK_DIRECTORY_ENVIRONMENT] = str(tmp_path_factory.mktemp("sdlc-locks"))
    yield
    if previous is None:
        os.environ.pop(LOCK_DIRECTORY_ENVIRONMENT, None)
    else:
        os.environ[LOCK_DIRECTORY_ENVIRONMENT] = previous
