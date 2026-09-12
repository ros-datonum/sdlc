"""Workspace runner guard: one `sdlc worker run` per workspace (RW-C04 section 9).

Two cooperating runners on the same host could both find the same
`Not Processed` Requirement and both claim it: Fibery offers no
compare-and-set. This module gives the runner an OS-managed advisory lock on
the configured workspace, held for the runner's whole life, so a second
runner fails immediately instead of processing in parallel.

Supported scope, exactly: cooperating runners on the same host, as the same OS
user, sharing the standard lock directory, against the same Fibery workspace.
Different machines and different OS users are not coordinated here; RW-C04
leaves multi-host exclusion unsupported.

The design principles are those of the per-RAW guard
(`raw_execution_guard.py`), and the lock directory is the same one; only the
key differs, scoped to the workspace instead of one RAW. The lock file is only
a rendezvous object for `flock`: it stays empty, is never unlinked, and holds
no lifecycle state, owner record, PID, lease or TTL. There is no stale-lock
stealing: the kernel releases the lock when the runner ends, whatever the
reason.
"""

from __future__ import annotations

import errno
import hashlib
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sdlc.raw_execution_guard import (
    DIRECTORY_MODE,
    FILE_MODE,
    KEY_SEPARATOR,
    LOCK_FILE_SUFFIX,
    lock_directory,
    normalize_scope,
)

try:
    import fcntl
except ImportError:  # pragma: no cover - not a supported platform
    fcntl = None  # type: ignore[assignment]

# Pairs with the workspace identity in place of a RAW entity id, which is
# always a uuid, so the runner's key can never equal a per-RAW key.
RUNNER_KEY_PURPOSE = "sdlc worker run"
RUNNER_LOCK_PREFIX = "worker-runner-"


class WorkerRunnerBusy(Exception):
    """Another cooperating runner owns this workspace on this host right now."""


class WorkerRunnerGuardUnavailable(Exception):
    """The guard cannot be established; the runner must not start."""


def runner_lock_key(scope: str) -> str:
    """A stable key for one workspace, the same in every shell and checkout."""
    workspace = normalize_scope(scope)
    if not workspace:
        raise WorkerRunnerGuardUnavailable(
            "The workspace identity is empty; there is nothing to guard."
        )
    material = workspace + KEY_SEPARATOR + RUNNER_KEY_PURPOSE
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def runner_lock_path(scope: str) -> Path:
    return lock_directory() / (
        RUNNER_LOCK_PREFIX + runner_lock_key(scope) + LOCK_FILE_SUFFIX
    )


@contextmanager
def hold_workspace(scope: str) -> Iterator[Path]:
    """Hold the workspace's runner lock for the block, or refuse immediately.

    Raises WorkerRunnerBusy when the lock is held (by another process or by
    another descriptor in this process: `flock` locks belong to the open file
    description) and WorkerRunnerGuardUnavailable when the lock cannot be set
    up at all. Never waits.
    """
    if fcntl is None:
        raise WorkerRunnerGuardUnavailable(
            "This platform provides no flock-style advisory lock; the worker "
            "runner does not run unguarded."
        )
    path = runner_lock_path(scope)
    descriptor = _open_rendezvous(path)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as error:
        os.close(descriptor)
        if error.errno in (errno.EWOULDBLOCK, errno.EAGAIN):
            raise WorkerRunnerBusy(
                "Another sdlc worker run owns this Fibery workspace on this host; "
                "nothing was read or written."
            ) from error
        raise WorkerRunnerGuardUnavailable(
            f"Could not take the worker runner lock: {type(error).__name__}."
        ) from error
    try:
        yield path
    finally:
        # Unlock then close; the file stays so every runner keeps locking the
        # same inode for this workspace.
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _open_rendezvous(path: Path) -> int:
    """Create the lock directory if needed and open the empty rendezvous file."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=DIRECTORY_MODE)
        return os.open(path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, FILE_MODE)
    except OSError as error:
        raise WorkerRunnerGuardUnavailable(
            f"Could not prepare the worker runner lock under {path.parent}: "
            f"{type(error).__name__}."
        ) from error
