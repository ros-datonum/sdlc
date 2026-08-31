"""Result codes and result payloads defined by Project-Init-Spec-v0.3."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class ResultCode(StrEnum):
    """Every outcome `project init` is allowed to report."""

    PROJECT_INITIALIZED = "PROJECT_INITIALIZED"
    PROJECT_ALREADY_EXISTS = "PROJECT_ALREADY_EXISTS"
    INVALID_INPUT = "INVALID_INPUT"
    INVALID_PROJECT_CODE = "INVALID_PROJECT_CODE"
    PROJECT_CODE_COLLISION = "PROJECT_CODE_COLLISION"
    FIBERY_READ_FAILED = "FIBERY_READ_FAILED"
    FIBERY_WRITE_FAILED = "FIBERY_WRITE_FAILED"
    DOCUMENT_STRUCTURE_CREATE_FAILED = "DOCUMENT_STRUCTURE_CREATE_FAILED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    PARTIAL_INIT = "PARTIAL_INIT"


NORMAL_OUTCOMES = frozenset(
    {ResultCode.PROJECT_INITIALIZED, ResultCode.PROJECT_ALREADY_EXISTS}
)


@dataclass(frozen=True)
class InitResult:
    """Outcome of one `project init` invocation.

    `created` and `failed` exist so a PARTIAL_INIT can report exactly what
    became durable in Fibery and exactly what did not, as required by
    Project-Init-Spec-v0.3 section 18.
    """

    code: ResultCode
    message: str
    project_name: str
    project_code: str | None = None
    documents: tuple[str, ...] = ()
    created: tuple[str, ...] = ()
    failed: tuple[str, ...] = ()
    details: tuple[str, ...] = field(default=())

    @property
    def is_normal(self) -> bool:
        return self.code in NORMAL_OUTCOMES
