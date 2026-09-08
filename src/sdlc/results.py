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
    VALIDATION_FAILED = "VALIDATION_FAILED"
    PARTIAL_INIT = "PARTIAL_INIT"


class AddResultCode(StrEnum):
    """Every outcome `project requirement add` is allowed to report."""

    RAW_REQUIREMENT_ADDED = "RAW_REQUIREMENT_ADDED"
    REQUIREMENT_ALREADY_ADDED = "REQUIREMENT_ALREADY_ADDED"
    INVALID_INPUT = "INVALID_INPUT"
    PROJECT_NOT_FOUND = "PROJECT_NOT_FOUND"
    PROJECT_AMBIGUOUS = "PROJECT_AMBIGUOUS"
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
    # Audit A10: another cooperating local invocation holds this RAW, or the
    # per-RAW execution lock cannot be established at all.
    RAW_PROCESSING_IN_PROGRESS = "RAW_PROCESSING_IN_PROGRESS"
    RAW_PROCESSING_GUARD_UNAVAILABLE = "RAW_PROCESSING_GUARD_UNAVAILABLE"
    INVALID_PROCESSING_RESULT = "INVALID_PROCESSING_RESULT"
    MODEL_RUNTIME_FAILED = "MODEL_RUNTIME_FAILED"
    INVALID_MODEL_OUTPUT = "INVALID_MODEL_OUTPUT"
    COMPARISON_CONTEXT_INCOMPLETE = "COMPARISON_CONTEXT_INCOMPLETE"
    NORMATIVE_TREE_INVALID = "NORMATIVE_TREE_INVALID"
    NORMATIVE_TREE_EVIDENCE_REQUIRED = "NORMATIVE_TREE_EVIDENCE_REQUIRED"
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


class StandardProcessResultCode(StrEnum):
    """Every outcome the Standard Requirement Processor may report."""

    REQUIREMENT_PROCESSED = "REQUIREMENT_PROCESSED"
    NO_CHANGES_TO_PROCESS = "NO_CHANGES_TO_PROCESS"
    REQUIREMENT_NOT_FOUND = "REQUIREMENT_NOT_FOUND"
    NOT_A_STANDARD_REQUIREMENT = "NOT_A_STANDARD_REQUIREMENT"
    REQUIREMENT_NOT_IN_PROCESS = "REQUIREMENT_NOT_IN_PROCESS"
    PROJECT_STRUCTURE_INVALID = "PROJECT_STRUCTURE_INVALID"
    PROCESSING_STATE_CONFLICT = "PROCESSING_STATE_CONFLICT"
    INVALID_PROCESSING_RESULT = "INVALID_PROCESSING_RESULT"
    MODEL_RUNTIME_FAILED = "MODEL_RUNTIME_FAILED"
    INVALID_MODEL_OUTPUT = "INVALID_MODEL_OUTPUT"
    COMPARISON_CONTEXT_INCOMPLETE = "COMPARISON_CONTEXT_INCOMPLETE"
    NORMATIVE_TREE_INVALID = "NORMATIVE_TREE_INVALID"
    NORMATIVE_TREE_EVIDENCE_REQUIRED = "NORMATIVE_TREE_EVIDENCE_REQUIRED"
    PROCESS_RESULT_WRITE_FAILED = "PROCESS_RESULT_WRITE_FAILED"
    CONTENT_WRITE_FAILED = "CONTENT_WRITE_FAILED"
    FIBERY_READ_FAILED = "FIBERY_READ_FAILED"
    FIBERY_WRITE_FAILED = "FIBERY_WRITE_FAILED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    PARTIAL_PROCESSING = "PARTIAL_PROCESSING"


NORMAL_STANDARD_OUTCOMES = frozenset(
    {
        StandardProcessResultCode.REQUIREMENT_PROCESSED,
        StandardProcessResultCode.NO_CHANGES_TO_PROCESS,
    }
)


@dataclass(frozen=True)
class StandardProcessResult:
    """Outcome of one Standard Requirement processing run."""

    code: StandardProcessResultCode
    message: str
    requirement_id: str | None = None
    iteration: int | None = None
    findings: tuple[str, ...] = ()
    proposed_relations: tuple[str, ...] = ()
    model_invoked: bool = False
    created: tuple[str, ...] = ()
    details: tuple[str, ...] = field(default=())

    @property
    def is_normal(self) -> bool:
        return self.code in NORMAL_STANDARD_OUTCOMES


class StandardReviewResultCode(StrEnum):
    """Every outcome the independent Standard Requirement Reviewer may report.

    The quality verdict is deliberately absent: a BLOCKING review is a
    successful execution, so the verdict travels in the payload rather than the
    status. Collapsing the two would make the processor fail exactly when it
    did its job well.
    """

    REQUIREMENT_REVIEWED = "REQUIREMENT_REVIEWED"
    NO_CHANGES_TO_REVIEW = "NO_CHANGES_TO_REVIEW"
    REQUIREMENT_NOT_FOUND = "REQUIREMENT_NOT_FOUND"
    NOT_A_STANDARD_REQUIREMENT = "NOT_A_STANDARD_REQUIREMENT"
    REQUIREMENT_NOT_IN_REVIEW = "REQUIREMENT_NOT_IN_REVIEW"
    PROJECT_STRUCTURE_INVALID = "PROJECT_STRUCTURE_INVALID"
    NO_PROCESS_RESULT = "NO_PROCESS_RESULT"
    INVALID_PROCESS_RESULT = "INVALID_PROCESS_RESULT"
    REVIEW_STATE_CONFLICT = "REVIEW_STATE_CONFLICT"
    INVALID_REVIEW_RESULT = "INVALID_REVIEW_RESULT"
    REVIEW_RESULT_STALE = "REVIEW_RESULT_STALE"
    MODEL_RUNTIME_FAILED = "MODEL_RUNTIME_FAILED"
    INVALID_MODEL_OUTPUT = "INVALID_MODEL_OUTPUT"
    COMPARISON_CONTEXT_INCOMPLETE = "COMPARISON_CONTEXT_INCOMPLETE"
    NORMATIVE_TREE_INVALID = "NORMATIVE_TREE_INVALID"
    NORMATIVE_TREE_EVIDENCE_REQUIRED = "NORMATIVE_TREE_EVIDENCE_REQUIRED"
    REVIEW_RESULT_WRITE_FAILED = "REVIEW_RESULT_WRITE_FAILED"
    FIBERY_READ_FAILED = "FIBERY_READ_FAILED"
    FIBERY_WRITE_FAILED = "FIBERY_WRITE_FAILED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    PARTIAL_REVIEW = "PARTIAL_REVIEW"


NORMAL_REVIEW_OUTCOMES = frozenset(
    {
        StandardReviewResultCode.REQUIREMENT_REVIEWED,
        StandardReviewResultCode.NO_CHANGES_TO_REVIEW,
    }
)


@dataclass(frozen=True)
class StandardReviewResult:
    """Outcome of one independent Standard Requirement review run."""

    code: StandardReviewResultCode
    message: str
    requirement_id: str | None = None
    iteration: int | None = None
    verdict: str | None = None
    blocking: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    verifications: tuple[str, ...] = ()
    relations: tuple[str, ...] = ()
    model_invoked: bool = False
    created: tuple[str, ...] = ()
    details: tuple[str, ...] = field(default=())

    @property
    def is_normal(self) -> bool:
        return self.code in NORMAL_REVIEW_OUTCOMES


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
    document_name: str | None = None
    created: tuple[str, ...] = ()
    failed: tuple[str, ...] = ()
    details: tuple[str, ...] = field(default=())

    @property
    def is_normal(self) -> bool:
        return self.code in NORMAL_ADD_OUTCOMES


class ReadyDecisionResultCode(StrEnum):
    """Every outcome the Standard Requirement Ready Decision may report.

    The Review verdict is deliberately absent here too: approving a BLOCKING
    Requirement is a successful execution of a human decision, and the verdict
    the human acknowledged travels in the payload.
    """

    REQUIREMENT_APPROVED = "REQUIREMENT_APPROVED"
    REQUIREMENT_SENT_FOR_REWORK = "REQUIREMENT_SENT_FOR_REWORK"
    REQUIREMENT_ALREADY_APPROVED = "REQUIREMENT_ALREADY_APPROVED"
    REQUIREMENT_ALREADY_IN_REWORK = "REQUIREMENT_ALREADY_IN_REWORK"
    REQUIREMENT_NOT_FOUND = "REQUIREMENT_NOT_FOUND"
    NOT_A_STANDARD_REQUIREMENT = "NOT_A_STANDARD_REQUIREMENT"
    REQUIREMENT_NOT_IN_READY = "REQUIREMENT_NOT_IN_READY"
    PROJECT_STRUCTURE_INVALID = "PROJECT_STRUCTURE_INVALID"
    NO_PROCESS_RESULT = "NO_PROCESS_RESULT"
    INVALID_PROCESS_RESULT = "INVALID_PROCESS_RESULT"
    NO_REVIEW_RESULT = "NO_REVIEW_RESULT"
    INVALID_REVIEW_RESULT = "INVALID_REVIEW_RESULT"
    REVIEW_STATE_CONFLICT = "REVIEW_STATE_CONFLICT"
    REVIEW_RESULT_STALE = "REVIEW_RESULT_STALE"
    NORMATIVE_TREE_INVALID = "NORMATIVE_TREE_INVALID"
    NORMATIVE_TREE_EVIDENCE_REQUIRED = "NORMATIVE_TREE_EVIDENCE_REQUIRED"
    VERDICT_ACKNOWLEDGEMENT_REQUIRED = "VERDICT_ACKNOWLEDGEMENT_REQUIRED"
    VERDICT_ACKNOWLEDGEMENT_MISMATCH = "VERDICT_ACKNOWLEDGEMENT_MISMATCH"
    INVALID_VERDICT_ACKNOWLEDGEMENT = "INVALID_VERDICT_ACKNOWLEDGEMENT"
    FIBERY_READ_FAILED = "FIBERY_READ_FAILED"
    FIBERY_WRITE_FAILED = "FIBERY_WRITE_FAILED"
    VALIDATION_FAILED = "VALIDATION_FAILED"


NORMAL_READY_OUTCOMES = frozenset(
    {
        ReadyDecisionResultCode.REQUIREMENT_APPROVED,
        ReadyDecisionResultCode.REQUIREMENT_SENT_FOR_REWORK,
        ReadyDecisionResultCode.REQUIREMENT_ALREADY_APPROVED,
        ReadyDecisionResultCode.REQUIREMENT_ALREADY_IN_REWORK,
    }
)


@dataclass(frozen=True)
class ReadyDecisionResult:
    """Outcome of one human decision recorded at Ready.

    There is no `created` collection: the only durable change this capability
    can make is one workflow State transition, reported through `state`. The
    review sections are what the human was deciding about, so a refusal that
    needs an acknowledgement can show exactly what would have been approved.
    """

    code: ReadyDecisionResultCode
    message: str
    decision: str
    requirement_id: str | None = None
    state: str | None = None
    iteration: int | None = None
    verdict: str | None = None
    blocking: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    relations: tuple[str, ...] = ()
    details: tuple[str, ...] = field(default=())

    @property
    def is_normal(self) -> bool:
        return self.code in NORMAL_READY_OUTCOMES


class ApplyResultCode(StrEnum):
    """Every outcome the Standard Requirement Apply may report."""

    REQUIREMENT_APPLIED = "REQUIREMENT_APPLIED"
    REQUIREMENT_ALREADY_APPLIED = "REQUIREMENT_ALREADY_APPLIED"
    REQUIREMENT_NOT_FOUND = "REQUIREMENT_NOT_FOUND"
    NOT_A_STANDARD_REQUIREMENT = "NOT_A_STANDARD_REQUIREMENT"
    REQUIREMENT_NOT_IN_APPLY = "REQUIREMENT_NOT_IN_APPLY"
    PROJECT_STRUCTURE_INVALID = "PROJECT_STRUCTURE_INVALID"
    NO_PROCESS_RESULT = "NO_PROCESS_RESULT"
    INVALID_PROCESS_RESULT = "INVALID_PROCESS_RESULT"
    NO_REVIEW_RESULT = "NO_REVIEW_RESULT"
    INVALID_REVIEW_RESULT = "INVALID_REVIEW_RESULT"
    REVIEW_STATE_CONFLICT = "REVIEW_STATE_CONFLICT"
    REVIEW_RESULT_STALE = "REVIEW_RESULT_STALE"
    NORMATIVE_TREE_INVALID = "NORMATIVE_TREE_INVALID"
    NORMATIVE_TREE_EVIDENCE_REQUIRED = "NORMATIVE_TREE_EVIDENCE_REQUIRED"
    RELATION_TARGET_NOT_FOUND = "RELATION_TARGET_NOT_FOUND"
    INVALID_RELATION_TARGET = "INVALID_RELATION_TARGET"
    PARTIAL_APPLY = "PARTIAL_APPLY"
    FIBERY_READ_FAILED = "FIBERY_READ_FAILED"
    FIBERY_WRITE_FAILED = "FIBERY_WRITE_FAILED"
    VALIDATION_FAILED = "VALIDATION_FAILED"


NORMAL_APPLY_OUTCOMES = frozenset(
    {
        ApplyResultCode.REQUIREMENT_APPLIED,
        ApplyResultCode.REQUIREMENT_ALREADY_APPLIED,
    }
)


@dataclass(frozen=True)
class ApplyResult:
    """Outcome of one deterministic application of an approved Requirement.

    `created` lists the normative steps that became durable, so a
    PARTIAL_APPLY reports exactly which edges exist; a retry completes only
    what is missing.
    """

    code: ApplyResultCode
    message: str
    requirement_id: str | None = None
    state: str | None = None
    relations_added: tuple[str, ...] = ()
    relations_present: tuple[str, ...] = ()
    created: tuple[str, ...] = ()
    details: tuple[str, ...] = field(default=())

    @property
    def is_normal(self) -> bool:
        return self.code in NORMAL_APPLY_OUTCOMES
