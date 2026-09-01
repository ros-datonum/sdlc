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


class AddResultCode(StrEnum):
    """Every outcome `project requirement add` is allowed to report."""

    RAW_REQUIREMENT_ADDED = "RAW_REQUIREMENT_ADDED"
    REQUIREMENT_ALREADY_ADDED = "REQUIREMENT_ALREADY_ADDED"
    INVALID_INPUT = "INVALID_INPUT"
    PROJECT_NOT_FOUND = "PROJECT_NOT_FOUND"
    PROJECT_AMBIGUOUS = "PROJECT_AMBIGUOUS"
    PROJECT_STRUCTURE_INVALID = "PROJECT_STRUCTURE_INVALID"
    SOURCE_FILE_NOT_FOUND = "SOURCE_FILE_NOT_FOUND"
    SOURCE_FILE_UNREADABLE = "SOURCE_FILE_UNREADABLE"
    INVALID_REQUIREMENT_SOURCE = "INVALID_REQUIREMENT_SOURCE"
    UNSUPPORTED_REQUIREMENTS_FORMAT = "UNSUPPORTED_REQUIREMENTS_FORMAT"
    REQUIREMENT_ID_ALLOCATION_FAILED = "REQUIREMENT_ID_ALLOCATION_FAILED"
    FIBERY_READ_FAILED = "FIBERY_READ_FAILED"
    FIBERY_WRITE_FAILED = "FIBERY_WRITE_FAILED"
    DOCUMENT_CREATE_FAILED = "DOCUMENT_CREATE_FAILED"
    DOCUMENT_ATTACHMENT_FAILED = "DOCUMENT_ATTACHMENT_FAILED"
    CONTENT_WRITE_FAILED = "CONTENT_WRITE_FAILED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    PARTIAL_ADD = "PARTIAL_ADD"


NORMAL_ADD_OUTCOMES = frozenset(
    {AddResultCode.RAW_REQUIREMENT_ADDED, AddResultCode.REQUIREMENT_ALREADY_ADDED}
)


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


class ProcessResultCode(StrEnum):
    """Every outcome the RAW Requirement Processor is allowed to report."""

    RAW_REQUIREMENT_PROCESSED = "RAW_REQUIREMENT_PROCESSED"
    REQUIREMENT_NOT_FOUND = "REQUIREMENT_NOT_FOUND"
    NOT_A_RAW_REQUIREMENT = "NOT_A_RAW_REQUIREMENT"
    REQUIREMENT_NOT_IN_PROCESS = "REQUIREMENT_NOT_IN_PROCESS"
    PROJECT_STRUCTURE_INVALID = "PROJECT_STRUCTURE_INVALID"
    PROCESSING_STATE_CONFLICT = "PROCESSING_STATE_CONFLICT"
    INVALID_PROCESSING_RESULT = "INVALID_PROCESSING_RESULT"
    MODEL_RUNTIME_FAILED = "MODEL_RUNTIME_FAILED"
    INVALID_MODEL_OUTPUT = "INVALID_MODEL_OUTPUT"
    PROCESSING_RESULT_WRITE_FAILED = "PROCESSING_RESULT_WRITE_FAILED"
    FIBERY_READ_FAILED = "FIBERY_READ_FAILED"
    FIBERY_WRITE_FAILED = "FIBERY_WRITE_FAILED"
    DOCUMENT_CREATE_FAILED = "DOCUMENT_CREATE_FAILED"
    CONTENT_WRITE_FAILED = "CONTENT_WRITE_FAILED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    PARTIAL_PROCESSING = "PARTIAL_PROCESSING"


NORMAL_PROCESS_OUTCOMES = frozenset({ProcessResultCode.RAW_REQUIREMENT_PROCESSED})


@dataclass(frozen=True)
class ProcessResult:
    """Outcome of one RAW Requirement processing run."""

    code: ProcessResultCode
    message: str
    raw_requirement_id: str | None = None
    candidates: tuple[str, ...] = ()
    findings: tuple[str, ...] = ()
    no_candidate_reason: str | None = None
    model_invoked: bool = False
    created: tuple[str, ...] = ()
    details: tuple[str, ...] = field(default=())

    @property
    def is_normal(self) -> bool:
        return self.code in NORMAL_PROCESS_OUTCOMES


@dataclass(frozen=True)
class AddResult:
    """Outcome of one `project requirement add` invocation.

    `created` and `failed` let a PARTIAL_ADD report exactly what became durable
    in Fibery and exactly what did not, as required by
    Project-Requirement-Add-Spec-v0.3 section 22.
    """

    code: AddResultCode
    message: str
    project_name: str | None = None
    project_code: str | None = None
    requirement_id: str | None = None
    title: str | None = None
    document_path: str | None = None
    created: tuple[str, ...] = ()
    failed: tuple[str, ...] = ()
    details: tuple[str, ...] = field(default=())

    @property
    def is_normal(self) -> bool:
        return self.code in NORMAL_ADD_OUTCOMES
