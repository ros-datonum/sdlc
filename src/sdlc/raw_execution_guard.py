"""Per-RAW execution guard: one local RAW invocation at a time (audit A10).

Two cooperating invocations of the RAW Requirement Processor for the same RAW
Requirement could both observe "no Processing Result" and both persist one.
This module gives every RAW invocation an OS-managed advisory lock, held for
the whole invocation, so a competing invocation returns busy immediately.

Supported scope, exactly: cooperating SDLC invocations on the same host, as
the same OS user, sharing the standard lock directory, against the same
Fibery workspace and RAW entity id. Different machines, different OS users,
direct Fibery writes and other pipeline stages are not coordinated here.

The lock file is only a rendezvous object for `flock`: it holds no content,
is never unlinked on release, and proves nothing about workflow state.
There is no owner record, TTL, heartbeat or stale-lock stealing; the kernel
releases the lock when the holding process ends, whatever the reason.
"""

from __future__ import annotations

import errno
import hashlib
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - not a supported platform
    fcntl = None  # type: ignore[assignment]

# A private, stable, per-user place outside any checkout, temporary
# directory or model-runtime cwd. The override exists for tests and isolated
# environments; it changes where the rendezvous files live, never whether
# the guard applies.
LOCK_DIRECTORY_ENVIRONMENT = "SDLC_LOCK_DIR"
DEFAULT_LOCK_DIRECTORY = Path.home() / ".sdlc" / "locks"
LOCK_FILE_SUFFIX = ".lock"
DIRECTORY_MODE = 0o700
FILE_MODE = 0o600
KEY_SEPARATOR = "\n"


class RawProcessingBusy(Exception):
    """Another cooperating invocation holds this RAW right now."""


class RawGuardUnavailable(Exception):
    """The guard cannot be established; the guarded operation must not run."""


def normalize_scope(scope: str) -> str:
    """The workspace part of the key: case-insensitive host, exact space id."""
    return scope.strip().lower()


def lock_key(scope: str, raw_entity_id: str) -> str:
    """A stable key for one RAW in one workspace, the same in every shell."""
    if not raw_entity_id.strip():
        raise RawGuardUnavailable("The RAW entity id is empty; nothing to guard.")
    material = normalize_scope(scope) + KEY_SEPARATOR + raw_entity_id.strip()
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def lock_directory() -> Path:
    override = os.environ.get(LOCK_DIRECTORY_ENVIRONMENT, "").strip()
    return Path(override) if override else DEFAULT_LOCK_DIRECTORY


def lock_path(scope: str, raw_entity_id: str) -> Path:
    return lock_directory() / (lock_key(scope, raw_entity_id) + LOCK_FILE_SUFFIX)


@contextmanager
def hold(scope: str, raw_entity_id: str) -> Iterator[Path]:
    """Hold the RAW's lock for the block, or refuse immediately.

    Raises RawProcessingBusy when the lock is held (by another process or by
    another descriptor in this process: `flock` locks belong to the open file
    description, so a second `open` in the same process contends too) and
    RawGuardUnavailable when the lock cannot be set up at all. Never waits.
    """
    if fcntl is None:
        raise RawGuardUnavailable(
            "This platform provides no flock-style advisory lock; RAW processing "
            "is not supported unguarded."
        )
    path = lock_path(scope, raw_entity_id)
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=DIRECTORY_MODE)
        descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, FILE_MODE)
    except OSError as error:
        raise RawGuardUnavailable(
            f"Could not prepare the RAW execution lock under {path.parent}: "
            f"{type(error).__name__}."
        ) from error
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as error:
        os.close(descriptor)
        if error.errno in (errno.EWOULDBLOCK, errno.EAGAIN):
            raise RawProcessingBusy(
                "Another RAW processing invocation for this Requirement is "
                "running on this host; nothing was read or written."
            ) from error
        raise RawGuardUnavailable(
            f"Could not take the RAW execution lock: {type(error).__name__}."
        ) from error
    try:
        yield path
    finally:
        # Unlock then close; the file stays so every process keeps locking the
        # same inode for this key.
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)
