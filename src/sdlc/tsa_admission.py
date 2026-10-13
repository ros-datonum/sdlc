"""TSA-C01 I05 — admission, the Input Manifest and its atomic acceptance.

Owns exactly what implementation spec v0.2 section 18.1 assigns to I05: the
eight Requirement admission checks of contract 2.1, UX admission for both
branches of the union (contract 4, spec 7.3), the explicit caller acceptance
(spec 12.1), the two-layer Input Manifest (spec 7) written as one complete
artifact, and the repeated-`start` comparison of spec 13.7-2.

Everything below it is reused, never re-implemented: the normative-tree reader
and the Process / Review parsers on the Requirement side, the I01 schemas,
digests and carrier parser, and the I04 discovery, deterministic ids and
bootstrap write. No Requirement is ever written — the evidence protocol here
has no write method — and no model is called.

Admission proves that a Requirement's current content agrees with its current
Process and Review evidence. It is not evidence of how, or whether, a human
applied that Requirement (contract 2.2); the acceptance recorded here is the
caller's explicit acceptance of these inputs for this cycle, and nothing more.

Nothing here caches a placement, a Project read or an admission across a
mutation: every step that relies on one reads it again (spec 2.2.1, 14.1).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from sdlc.fibery_workspace import (
    DocumentNode,
    DocumentPlacement,
    FiberyError,
    RequirementRecord,
    is_valid_child_placement,
)
from sdlc.normative_tree import (
    NormativeTree,
    NormativeTreeError,
    TreeManifest,
    describe_drift,
    document_fingerprint,
    read_normative_tree,
)
from sdlc.process_result import (
    InvalidProcessResult,
    ProcessResult,
    parse_process_result,
    parse_process_result_name,
)
from sdlc.review_result import (
    InvalidReviewResult,
    ReviewResult,
    parse_review_result,
    parse_review_result_name,
)
from sdlc.tsa_artifacts import (
    FENCE_MARKER,
    INPUT_MANIFEST,
    JSON_FENCE_OPENER,
    SCHEMA_VERSION,
    UX_APPLICABLE,
    UX_NOT_APPLICABLE,
    InvalidTsaArtifact,
    TsaArtifact,
    canonical_artifact_json,
    canonical_json,
    extract_artifact_payload,
    manifest_digest,
    requirement_input_digest,
    sealed_artifact,
    start_input_digest,
    start_input_projection,
    validate_artifact,
)
from sdlc.tsa_cycle import (
    BootstrapContext,
    Clock,
    CycleDiscovery,
    CycleOutcome,
    CycleRefused,
    CycleResultCode,
    CycleWorkspace,
    DocumentKind,
    created_at_now,
    discover_cycle,
    ensure_bootstrap_architecture,
    rediscover_after_unknown_outcome,
)

STANDARD_TYPE = "Standard"
APPLIED_STATE = "Applied"
#: Spec 15: the selection is capped at 100 Requirements; overflow is refused.
SELECTION_LIMIT = 100
#: Contract 5: the Manifest's navigation name. Never identity.
MANIFEST_NAME_TEMPLATE = "TSA {cycle_id} — Input Manifest"
MANIFEST_HEADING_TEMPLATE = "# {name}"
#: One line on purpose: Fibery stores a soft line break as a literal `<br>`.
MANIFEST_PROSE = (
    "Immutable TSA artifact written by the Architecture cycle. It records the "
    "inputs explicitly accepted for this cycle and is not evidence of how any "
    "Requirement was applied."
)
#: The first create, then at most one retry at the same deterministic id, and
#: only after rediscovery showed the child absent (spec 3.5 step 4).
MANIFEST_CREATE_ATTEMPTS = 2

PROCESS_RESULT_LABEL = "Process Result"
REVIEW_RESULT_LABEL = "Review Result"

ResultNameParser = Callable[[str], tuple[str, int] | None]


class AdmissionResultCode(StrEnum):
    """The frozen result codes of 13.8 that I05 itself decides. No new code."""

    SELECTION_EMPTY = "SELECTION_EMPTY"
    SELECTION_DUPLICATE = "SELECTION_DUPLICATE"
    INPUT_TOO_LARGE = "INPUT_TOO_LARGE"
    REQUIREMENT_NOT_ADMISSIBLE = "REQUIREMENT_NOT_ADMISSIBLE"
    UX_EVIDENCE_INVALID = "UX_EVIDENCE_INVALID"
    UX_SCOPE_FOREIGN = "UX_SCOPE_FOREIGN"
    HUMAN_ACCEPTANCE_REQUIRED = "HUMAN_ACCEPTANCE_REQUIRED"
    MANIFEST_INPUTS_CONFLICT = "MANIFEST_INPUTS_CONFLICT"
    INPUTS_STALE = "INPUTS_STALE"


ResultCode = AdmissionResultCode | CycleResultCode


class AdmissionRefused(Exception):
    """A controlled refusal. `code` is one frozen result code of 13.8.

    A refusal raised by the I04 gate keeps the code I04 gave it. `details`
    names Documents and Requirements by id, never by content.
    """

    def __init__(
        self, code: ResultCode, message: str, details: tuple[str, ...] = ()
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = details


class RequirementEvidenceWorkspace(Protocol):
    """The Requirement reads admission needs. It has no write method.

    That absence is what makes a Requirement write, a backfill or a triggered
    Process structurally impossible from here.
    """

    def find_requirements_by_requirement_id(
        self, requirement_id: str
    ) -> list[RequirementRecord]:
        """Every Requirement carrying this Requirement ID, bounded to two."""

    def read_requirement(self, entity_id: str) -> RequirementRecord | None:
        """Read one Requirement entity by id."""

    def documents_attached_to_requirement(self, public_id: str) -> list[DocumentNode]:
        """Documents attached to this Requirement entity."""

    def child_documents(self, parent_document_id: str) -> list[DocumentNode]:
        """Documents nested directly under this Document."""

    def read_document_content(self, secret: str) -> str:
        """Read a Document's Markdown content."""


@dataclass(frozen=True)
class UxApplicable:
    """The caller's `--ux applicable` input: one Document id and its scope."""

    document_id: str
    scope_requirement_ids: tuple[str, ...]


@dataclass(frozen=True)
class UxNotApplicable:
    """The caller's `--ux not-applicable` input: the human's stated reason."""

    reason: str


UxInput = UxApplicable | UxNotApplicable


@dataclass(frozen=True)
class StartInputs:
    """Everything `start` carries that a Manifest is built from (spec 12.1).

    `accept_inputs` and `accept_ux` are the caller's explicit acceptance. They
    are never inferred — not from a State, not from a Document existing, not
    from the command having run — and only the literal `True` is acceptance.
    """

    requirement_ids: tuple[str, ...]
    ux: UxInput
    accept_inputs: bool
    accept_ux: bool


@dataclass(frozen=True)
class AdmittedInputs:
    """One complete admission: the Manifest's Requirement rows and UX evidence.

    `ux` is the caller-input projection shape of 13.7-2 and carries no
    timestamp; the acceptance records are added when the Manifest is built.
    """

    requirements: tuple[dict[str, object], ...]
    ux: dict[str, object]


@dataclass(frozen=True)
class ManifestResult:
    """The cycle's valid accepted Input Manifest, as read back from Fibery.

    `is_newly_written` is false when an existing Manifest was reused unchanged
    for the same caller inputs.
    """

    context: BootstrapContext
    artifact: TsaArtifact
    is_newly_written: bool


@dataclass(frozen=True)
class _Start:
    """One `start` invocation's fixed arguments, after argv validation."""

    workspace: CycleWorkspace
    evidence: RequirementEvidenceWorkspace
    project_id: str
    cycle_id: object
    selection: tuple[str, ...]
    ux: UxInput
    inputs: StartInputs
    clock: Clock


def _utc_now() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Caller inputs: selection, UX shape, explicit acceptance (spec 12.1)
# ---------------------------------------------------------------------------


def normalize_selection(raw_ids: Sequence[str]) -> tuple[str, ...]:
    """Trim and upper-case the selection, refuse a duplicate, sort ascending.

    A duplicate is reported, never collapsed. Sorting is what makes argument
    order irrelevant to every digest (spec 7.2).
    """
    if not raw_ids:
        raise AdmissionRefused(
            AdmissionResultCode.SELECTION_EMPTY, "No Requirement was selected."
        )
    if len(raw_ids) > SELECTION_LIMIT:
        raise AdmissionRefused(
            AdmissionResultCode.INPUT_TOO_LARGE,
            f"{len(raw_ids)} Requirements were selected; the limit is "
            f"{SELECTION_LIMIT}. Nothing was truncated.",
        )
    normalized = [_normalized_requirement_id(raw) for raw in raw_ids]
    duplicates = sorted({item for item in normalized if normalized.count(item) > 1})
    if duplicates:
        raise AdmissionRefused(
            AdmissionResultCode.SELECTION_DUPLICATE,
            f"The selection names {duplicates} more than once.",
        )
    return tuple(sorted(normalized))


def _normalized_requirement_id(raw: object) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise AdmissionRefused(
            AdmissionResultCode.REQUIREMENT_NOT_ADMISSIBLE,
            f"{raw!r} is not a Requirement ID.",
        )
    return raw.strip().upper()


def _require_acceptance(inputs: StartInputs) -> None:
    missing = [
        name
        for name, value in (
            ("accept_inputs", inputs.accept_inputs),
            ("accept_ux", inputs.accept_ux),
        )
        if value is not True
    ]
    if missing:
        raise AdmissionRefused(
            AdmissionResultCode.HUMAN_ACCEPTANCE_REQUIRED,
            f"Explicit acceptance is required and {missing} was not given. "
            "Nothing was written.",
        )


def _normalize_ux(ux: object, selection: tuple[str, ...]) -> UxInput:
    """Validate the caller's UX input without reading any Document.

    Only the two typed caller inputs are a UX decision. Anything else — a
    Manifest-shaped object that already carries its own `approval` or
    `decision`, for one — did not come from the caller's flags and is refused.
    """
    if isinstance(ux, UxNotApplicable):
        return UxNotApplicable(_require_ux_text(ux.reason, "reason"))
    if isinstance(ux, UxApplicable):
        return UxApplicable(
            _require_ux_text(ux.document_id, "document_id"),
            _normalize_scope(ux.scope_requirement_ids, selection),
        )
    raise AdmissionRefused(
        AdmissionResultCode.UX_EVIDENCE_INVALID,
        f"The UX input is {type(ux).__name__}, not a caller UX decision; a UX "
        "value is recorded only from the caller's explicit input.",
    )


def _require_ux_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AdmissionRefused(
            AdmissionResultCode.UX_EVIDENCE_INVALID, f"The UX {field} is empty."
        )
    try:
        canonical_json(value)
    except InvalidTsaArtifact as error:
        raise AdmissionRefused(
            AdmissionResultCode.UX_EVIDENCE_INVALID,
            f"The UX {field} cannot be recorded: {error}",
        ) from error
    return value


def _normalize_scope(raw_scope: object, selection: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(raw_scope, tuple | list) or not raw_scope:
        raise AdmissionRefused(
            AdmissionResultCode.UX_EVIDENCE_INVALID,
            "An applicable UX names no Requirement scope.",
        )
    scope = [_normalized_requirement_id(raw) for raw in raw_scope]
    duplicates = sorted({item for item in scope if scope.count(item) > 1})
    if duplicates:
        raise AdmissionRefused(
            AdmissionResultCode.UX_EVIDENCE_INVALID,
            f"The UX scope names {duplicates} more than once.",
        )
    foreign = sorted(set(scope) - set(selection))
    if foreign:
        raise AdmissionRefused(
            AdmissionResultCode.UX_SCOPE_FOREIGN,
            f"The UX scope names {foreign}, which the selection does not include.",
        )
    return tuple(sorted(scope))


# ---------------------------------------------------------------------------
# Requirement admission: the eight checks of contract 2.1
# ---------------------------------------------------------------------------


def _not_admissible(
    requirement_id: str, reason: str, details: tuple[str, ...] = ()
) -> AdmissionRefused:
    return AdmissionRefused(
        AdmissionResultCode.REQUIREMENT_NOT_ADMISSIBLE,
        f"{requirement_id} is not admissible: {reason} The whole selection is "
        "refused and nothing was written.",
        details,
    )


@contextmanager
def _reading(subject: str) -> Iterator[None]:
    """Turn an adapter read failure into the frozen `FIBERY_READ_FAILED`."""
    try:
        yield
    except FiberyError as error:
        raise AdmissionRefused(
            CycleResultCode.FIBERY_READ_FAILED, f"Reading {subject} failed: {error}"
        ) from error


def _resolve_exact_identity(
    evidence: RequirementEvidenceWorkspace, requirement_id: str
) -> RequirementRecord:
    """Check 1: the Requirement ID and one entity id name the same entity.

    A Requirement-ID-only match is not identity: the ID must resolve to exactly
    one entity, and that entity, read back by its own id, must carry the ID.
    """
    with _reading(f"Requirement {requirement_id}"):
        matches = evidence.find_requirements_by_requirement_id(requirement_id)
    if len(matches) != 1:
        raise _not_admissible(
            requirement_id,
            f"the Requirement ID resolves to {len(matches)} entities, not one.",
            tuple(match.id for match in matches),
        )
    entity_id = matches[0].id
    with _reading(f"Requirement entity {entity_id!r}"):
        record = evidence.read_requirement(entity_id)
    if (
        record is None
        or record.id != entity_id
        or record.requirement_id != requirement_id
    ):
        raise _not_admissible(
            requirement_id,
            f"entity {entity_id!r} does not read back as this Requirement.",
            (entity_id,),
        )
    return record


def _require_admissible_record(
    record: RequirementRecord, requirement_id: str, context: BootstrapContext
) -> None:
    """Checks 2, 3 and 4: Project, Type and State."""
    if record.project_id != context.project_entity_id:
        raise _not_admissible(
            requirement_id,
            f"it belongs to Project {record.project_id!r}, not the cycle's "
            f"Project {context.project_entity_id!r}.",
        )
    if record.type_name != STANDARD_TYPE:
        raise _not_admissible(
            requirement_id,
            f"its Type is {record.type_name!r}, not {STANDARD_TYPE!r}.",
        )
    if record.state != APPLIED_STATE:
        raise _not_admissible(
            requirement_id,
            f"its State is {record.state!r}, not {APPLIED_STATE!r}.",
        )


def _read_current_tree(
    evidence: RequirementEvidenceWorkspace,
    record: RequirementRecord,
    requirement_id: str,
) -> NormativeTree:
    """Check 5: the complete current normative tree, through the shared reader."""
    with _reading(f"the Documents attached to {requirement_id}"):
        attached = evidence.documents_attached_to_requirement(record.public_id)
    if len(attached) != 1:
        raise _not_admissible(
            requirement_id,
            f"it has {len(attached)} attached Documents; exactly one Root "
            "Document is required.",
            tuple(node.id for node in attached),
        )
    try:
        return read_normative_tree(evidence, record, attached[0])
    except NormativeTreeError as error:
        if error.read_failed:
            raise AdmissionRefused(
                CycleResultCode.FIBERY_READ_FAILED, error.message, error.details
            ) from error
        raise _not_admissible(requirement_id, error.message, error.details) from error


def _latest_result(
    tree: NormativeTree,
    requirement_id: str,
    parse_name: ResultNameParser,
    label: str,
) -> tuple[DocumentNode, int]:
    """The newest artifact of one kind. An older one is never used in its place."""
    nodes: dict[int, DocumentNode] = {}
    for artifact in tree.artifacts:
        parsed = parse_name(artifact.name)
        if parsed is None or parsed[0] != requirement_id:
            continue
        iteration = parsed[1]
        if iteration in nodes:
            raise _not_admissible(
                requirement_id,
                f"it has more than one {label} for iteration {iteration}.",
                (nodes[iteration].id, artifact.id),
            )
        nodes[iteration] = artifact
    if not nodes:
        raise _not_admissible(requirement_id, f"it has no {label}.")
    latest = max(nodes)
    return nodes[latest], latest


def _read_result_content(
    evidence: RequirementEvidenceWorkspace,
    node: DocumentNode,
    requirement_id: str,
    label: str,
) -> str:
    if not node.secret:
        raise _not_admissible(
            requirement_id,
            f"its {label} Document exposes no content secret.",
            (node.id,),
        )
    with _reading(f"{label} Document {node.id!r} of {requirement_id}"):
        return evidence.read_document_content(node.secret)


def _require_current_result(
    result: ProcessResult | ReviewResult,
    node: DocumentNode,
    iteration: int,
    requirement_id: str,
    label: str,
) -> None:
    """Checks 6 and 7: the artifact is what its name says, at the current version."""
    if result.iteration != iteration or result.requirement_id != requirement_id:
        raise _not_admissible(
            requirement_id,
            f"{label} Document {node.name!r} describes "
            f"{result.requirement_id!r} iteration {result.iteration}.",
            (node.id,),
        )
    if not result.is_current:
        raise _not_admissible(
            requirement_id,
            f"its latest {label} {iteration} is version {result.version}, which "
            "is older-format history and not current evidence. No older or newer "
            "Result is substituted.",
            (node.id,),
        )


def _read_process_result(
    evidence: RequirementEvidenceWorkspace, tree: NormativeTree, requirement_id: str
) -> tuple[DocumentNode, ProcessResult, str]:
    node, iteration = _latest_result(
        tree, requirement_id, parse_process_result_name, PROCESS_RESULT_LABEL
    )
    content = _read_result_content(evidence, node, requirement_id, PROCESS_RESULT_LABEL)
    try:
        result = parse_process_result(content)
    except InvalidProcessResult as error:
        raise _not_admissible(
            requirement_id,
            f"its latest Process Result {iteration} cannot be trusted: {error}",
            (node.id,),
        ) from error
    _require_current_result(
        result, node, iteration, requirement_id, PROCESS_RESULT_LABEL
    )
    return node, result, content


def _read_review_result(
    evidence: RequirementEvidenceWorkspace, tree: NormativeTree, requirement_id: str
) -> tuple[DocumentNode, ReviewResult, str]:
    node, iteration = _latest_result(
        tree, requirement_id, parse_review_result_name, REVIEW_RESULT_LABEL
    )
    content = _read_result_content(evidence, node, requirement_id, REVIEW_RESULT_LABEL)
    try:
        result = parse_review_result(content)
    except InvalidReviewResult as error:
        raise _not_admissible(
            requirement_id,
            f"its latest Review Result {iteration} cannot be trusted: {error}",
            (node.id,),
        ) from error
    _require_current_result(
        result, node, iteration, requirement_id, REVIEW_RESULT_LABEL
    )
    return node, result, content


def _require_tree_binding(
    requirement_id: str, label: str, bound: TreeManifest | None, current: TreeManifest
) -> None:
    if bound is None or bound.fingerprint != current.fingerprint:
        drift = describe_drift(bound, current) if bound is not None else ()
        raise _not_admissible(
            requirement_id,
            f"{label} does not bind the current normative tree.",
            drift,
        )


def _require_exact_bindings(
    requirement_id: str,
    current: TreeManifest,
    process: ProcessResult,
    review: ReviewResult,
) -> None:
    """Check 8: Process, Review and the current tree are one lineage."""
    _require_tree_binding(
        requirement_id, "the Review Result", review.reviewed_tree, current
    )
    _require_tree_binding(
        requirement_id, "the Process Result", process.output_tree, current
    )
    if review.reviewed_document_fingerprint != current.root_entry.content_fingerprint:
        raise _not_admissible(
            requirement_id,
            "the Review Result does not bind the current Root Document content.",
        )
    if not review.reviews(
        current.root_entry.content_fingerprint,
        process.iteration,
        process.output_fingerprint,
    ):
        raise _not_admissible(
            requirement_id,
            f"Review Result {review.iteration} reviewed Process iteration "
            f"{review.reviewed_process_iteration}, not the output of the latest "
            f"Process Result {process.iteration}.",
        )


def _admit_requirement(
    evidence: RequirementEvidenceWorkspace,
    context: BootstrapContext,
    requirement_id: str,
) -> dict[str, object]:
    """All eight checks for one Requirement; returns its Manifest row (7.2)."""
    record = _resolve_exact_identity(evidence, requirement_id)
    _require_admissible_record(record, requirement_id, context)
    tree = _read_current_tree(evidence, record, requirement_id)
    process_node, process, process_content = _read_process_result(
        evidence, tree, requirement_id
    )
    review_node, review, review_content = _read_review_result(
        evidence, tree, requirement_id
    )
    _require_exact_bindings(requirement_id, tree.manifest, process, review)
    return {
        "requirement_id": requirement_id,
        "entity_id": record.id,
        "tree_manifest": tree.manifest.to_payload(),
        "tree_fingerprint": tree.manifest.root_entry.content_fingerprint,
        "process_result": {
            "document_id": process_node.id,
            "iteration": process.iteration,
            "payload_digest": document_fingerprint(process_content),
        },
        "review_result": {
            "document_id": review_node.id,
            "payload_digest": document_fingerprint(review_content),
        },
    }


def _admit_requirements(
    evidence: RequirementEvidenceWorkspace,
    context: BootstrapContext,
    selection: tuple[str, ...],
) -> tuple[dict[str, object], ...]:
    """Every selected Requirement, or none: one failure refuses the whole set.

    The adapter offers no batched read, so this is a fixed handful of reads per
    Requirement plus one per Document of its tree; the selection is capped at
    `SELECTION_LIMIT` and each tree at the reader's own limits.
    """
    rows = tuple(
        _admit_requirement(evidence, context, requirement_id)
        for requirement_id in selection
    )
    entity_ids = [str(row["entity_id"]) for row in rows]
    duplicates = sorted({item for item in entity_ids if entity_ids.count(item) > 1})
    if duplicates:
        raise AdmissionRefused(
            AdmissionResultCode.SELECTION_DUPLICATE,
            f"The selection resolves to entity id(s) {duplicates} more than once.",
        )
    try:
        requirement_input_digest(list(rows))
    except InvalidTsaArtifact as error:
        raise AdmissionRefused(
            AdmissionResultCode.REQUIREMENT_NOT_ADMISSIBLE,
            f"The admitted evidence cannot be bound into a Manifest: {error}",
        ) from error
    return rows


# ---------------------------------------------------------------------------
# UX admission (contract 4, spec 7.3)
# ---------------------------------------------------------------------------


def _ux_invalid(document_id: str, reason: str) -> AdmissionRefused:
    return AdmissionRefused(
        AdmissionResultCode.UX_EVIDENCE_INVALID,
        f"UX Document {document_id!r} is not admissible evidence: {reason}",
        (document_id,),
    )


def _read_ux_evidence(workspace: CycleWorkspace, ux: UxApplicable) -> dict[str, object]:
    """Read the one UX Document by its id and fingerprint what was read.

    A name, a URL or a version label is never consulted: identity is the
    Document id and evidence is the content actually read.
    """
    document_id = ux.document_id
    try:
        node = workspace.resolve_document(document_id)
    except FiberyError as error:
        raise _ux_invalid(
            document_id, f"it could not be resolved ({error})."
        ) from error
    if node is None:
        raise _ux_invalid(document_id, "no Document exists at that id.")
    if node.id != document_id or not node.secret:
        raise _ux_invalid(document_id, "it does not resolve to readable content.")
    try:
        content = workspace.read_document_content(node.secret)
    except FiberyError as error:
        raise _ux_invalid(document_id, f"it could not be read ({error}).") from error
    if not content.strip():
        raise _ux_invalid(document_id, "it has no content.")
    return {
        "kind": UX_APPLICABLE,
        "document_id": document_id,
        "content_digest": document_fingerprint(content),
        "scope_requirement_ids": list(ux.scope_requirement_ids),
    }


def _admit_ux(workspace: CycleWorkspace, ux: UxInput) -> dict[str, object]:
    """The UX evidence of one branch. `NOT_APPLICABLE` reads no Document."""
    if isinstance(ux, UxNotApplicable):
        return {"kind": UX_NOT_APPLICABLE, "reason": ux.reason}
    return _read_ux_evidence(workspace, ux)


def admit_inputs(
    workspace: CycleWorkspace,
    evidence: RequirementEvidenceWorkspace,
    context: BootstrapContext,
    selection: tuple[str, ...],
    ux: UxInput,
) -> AdmittedInputs:
    """Admit the whole selection and the UX evidence. Read-only.

    `selection` and `ux` are the normalized caller inputs. Raises
    `AdmissionRefused` for the first failure; nothing partial is returned.
    """
    return AdmittedInputs(
        requirements=_admit_requirements(evidence, context, selection),
        ux=_admit_ux(workspace, ux),
    )


def _readmit_unchanged(
    start: _Start, context: BootstrapContext, admitted: AdmittedInputs
) -> None:
    """Admit again, fresh, and refuse if anything moved since `admitted`.

    This is the revalidation before the Manifest is frozen (contract 10, spec
    14.1): what the caller accepted is what was verified, so evidence that
    changed during the command is not silently swapped in.
    """
    fresh = admit_inputs(
        start.workspace, start.evidence, context, start.selection, start.ux
    )
    if fresh.ux != admitted.ux:
        raise AdmissionRefused(
            AdmissionResultCode.UX_EVIDENCE_INVALID,
            "The UX Document content changed while the command was running; its "
            "digest no longer matches what was admitted. No Manifest was written.",
        )
    if fresh.requirements != admitted.requirements:
        raise AdmissionRefused(
            AdmissionResultCode.INPUTS_STALE,
            "Requirement evidence changed while the command was running. No "
            "Manifest was written.",
        )


# ---------------------------------------------------------------------------
# The Input Manifest (spec 7) and its carrier (spec 4.1)
# ---------------------------------------------------------------------------


def input_manifest_document_name(context: BootstrapContext) -> str:
    """The navigation name of the Input Manifest Document. Never identity."""
    return MANIFEST_NAME_TEMPLATE.format(cycle_id=context.cycle_id)


def _manifest_ux(
    admitted: AdmittedInputs, inputs: StartInputs, recorded_at: str
) -> dict[str, object]:
    """The UX union of 7.3. The acceptance value is the caller's flag itself."""
    record = {"accepted": inputs.accept_ux, "recorded_at": recorded_at}
    if admitted.ux["kind"] == UX_APPLICABLE:
        return {**admitted.ux, "approval": record}
    return {
        **admitted.ux,
        "requirement_input_digest": requirement_input_digest(
            list(admitted.requirements)
        ),
        "decision": record,
    }


def build_input_manifest(
    context: BootstrapContext,
    admitted: AdmittedInputs,
    inputs: StartInputs,
    recorded_at: str,
) -> dict[str, object]:
    """The sealed `tsa.input_manifest`: body, digest and acceptance together.

    Two layers (7.1): `manifest_digest` covers `manifest_body` only, the
    acceptance binds that digest from outside the body, and `artifact_digest`
    covers the whole artifact including the acceptance. There is no form of
    this artifact without its acceptance.
    """
    manifest_body = {
        "workspace_identity": context.workspace_identity,
        "project_code": context.project_code,
        "project_entity_id": context.project_entity_id,
        "cycle_id": context.cycle_id,
        "created_at": recorded_at,
        "requirements": list(admitted.requirements),
        "ux": _manifest_ux(admitted, inputs, recorded_at),
    }
    digest = manifest_digest(manifest_body)
    return sealed_artifact(
        {
            "artifact_type": INPUT_MANIFEST,
            "schema_version": SCHEMA_VERSION,
            "workspace_identity": context.workspace_identity,
            "project_entity_id": context.project_entity_id,
            "project_code": context.project_code,
            "cycle_id": context.cycle_id,
            "body": {
                "manifest_body": manifest_body,
                "manifest_digest": digest,
                "acceptance": {
                    "manifest_digest": digest,
                    "accepted": inputs.accept_inputs,
                    "recorded_at": recorded_at,
                },
            },
        }
    )


def render_manifest_carrier(
    context: BootstrapContext, sealed: dict[str, object]
) -> str:
    """The immutable carrier of 4.1: heading, one paragraph, one JSON fence."""
    heading = MANIFEST_HEADING_TEMPLATE.format(
        name=input_manifest_document_name(context)
    )
    return (
        f"{heading}\n"
        "\n"
        f"{MANIFEST_PROSE}\n"
        "\n"
        f"{JSON_FENCE_OPENER}\n"
        f"{canonical_artifact_json(sealed)}\n"
        f"{FENCE_MARKER}\n"
    )


# ---------------------------------------------------------------------------
# Reading a persisted Manifest, and the repeated start (spec 13.7-2)
# ---------------------------------------------------------------------------


@contextmanager
def _cycle_refusals() -> Iterator[None]:
    """A refusal of the I04 gate keeps its own frozen code."""
    try:
        yield
    except CycleRefused as refused:
        raise AdmissionRefused(refused.code, str(refused)) from refused


def _gate(start: _Start) -> CycleDiscovery:
    """The bootstrap gate, read fresh: I04's complete discovery."""
    with _cycle_refusals():
        return discover_cycle(start.workspace, start.project_id, start.cycle_id)


def _refuse_gate_failure(found: CycleDiscovery) -> AdmissionRefused:
    assert found.refusal_code is not None  # set exactly in state E
    return AdmissionRefused(found.refusal_code, found.detail)


def _resolve_manifest_child(
    workspace: CycleWorkspace, context: BootstrapContext
) -> DocumentPlacement | None:
    """The Manifest child and its root, both resolved now (spec 2.2.1).

    Returns None when no Document exists at the deterministic id. A Document
    that is not a child of this cycle's Architecture root is refused.
    """
    manifest_id = context.input_manifest_document_id
    with _reading(f"the placement of Input Manifest Document {manifest_id!r}"):
        child = workspace.resolve_placement(manifest_id)
        root = workspace.resolve_placement(context.architecture_document_id)
    if child is None:
        return None
    if root is None or not is_valid_child_placement(
        child,
        root,
        context.architecture_document_id,
        context.project_type_id,
        context.project_public_id,
    ):
        raise AdmissionRefused(
            CycleResultCode.CYCLE_FOREIGN_PROJECT,
            f"Document {manifest_id!r} is not a child of the Architecture root.",
        )
    return child


def _read_manifest_content(workspace: CycleWorkspace, child: DocumentPlacement) -> str:
    if not child.secret:
        raise AdmissionRefused(
            CycleResultCode.FIBERY_READ_FAILED,
            f"Input Manifest Document {child.document_id!r} exposes no content secret.",
        )
    with _reading(f"Input Manifest Document {child.document_id!r}"):
        return workspace.read_document_content(child.secret)


def _load_manifest(
    workspace: CycleWorkspace, context: BootstrapContext
) -> tuple[TsaArtifact, dict[str, object]]:
    """Read and validate the persisted Manifest on fresh placement reads."""
    manifest_id = context.input_manifest_document_id
    child = _resolve_manifest_child(workspace, context)
    if child is None:
        raise AdmissionRefused(
            CycleResultCode.FIBERY_READ_FAILED,
            f"Input Manifest Document {manifest_id!r} no longer resolves.",
        )
    content = _read_manifest_content(workspace, child)
    if not content.strip():
        raise AdmissionRefused(
            CycleResultCode.MANIFEST_SHELL_UNRECOVERABLE,
            f"Input Manifest Document {manifest_id!r} is an empty shell.",
        )
    try:
        payload = extract_artifact_payload(content)
        artifact = validate_artifact(payload)
        _require_manifest_identity(artifact, context)
    except InvalidTsaArtifact as error:
        raise AdmissionRefused(
            _manifest_refusal_code(error),
            f"Input Manifest Document {manifest_id!r}: {error}",
        ) from error
    return artifact, payload


def _manifest_refusal_code(error: InvalidTsaArtifact) -> CycleResultCode:
    if error.code == CycleResultCode.MANIFEST_ACCEPTANCE_MISMATCH:
        return CycleResultCode.MANIFEST_ACCEPTANCE_MISMATCH
    return CycleResultCode.ARTIFACT_MALFORMED


def _require_manifest_identity(
    artifact: TsaArtifact, context: BootstrapContext
) -> None:
    for field, actual, expected in (
        ("artifact_type", artifact.artifact_type, INPUT_MANIFEST),
        ("cycle_id", artifact.cycle_id, context.cycle_id),
        ("project_entity_id", artifact.project_entity_id, context.project_entity_id),
    ):
        if actual != expected:
            raise InvalidTsaArtifact(
                f"The persisted {field} {actual!r} does not equal the trusted "
                f"expected value {expected!r}."
            )


def _projection(
    context: BootstrapContext,
    requirement_ids: Sequence[str],
    ux: dict[str, object],
    accept_inputs: object,
    accept_ux: object,
) -> dict[str, object]:
    return start_input_projection(
        cycle_id=context.cycle_id,
        project_entity_id=context.project_entity_id,
        requirement_ids=list(requirement_ids),
        ux=ux,
        accept_inputs=accept_inputs,
        accept_ux=accept_ux,
    )


def _persisted_projection(
    context: BootstrapContext, artifact: TsaArtifact
) -> dict[str, object]:
    """The caller-input projection of a persisted Manifest (13.7-2 step 4).

    Only caller-controlled values enter: `created_at` and both `recorded_at`
    timestamps are generated metadata and are left where they are.
    """
    body = artifact.body["manifest_body"]
    ux = body["ux"]
    if ux["kind"] == UX_APPLICABLE:
        projected = {
            "kind": UX_APPLICABLE,
            "document_id": ux["document_id"],
            "content_digest": ux["content_digest"],
            "scope_requirement_ids": ux["scope_requirement_ids"],
        }
        accept_ux = ux["approval"]["accepted"]
    else:
        projected = {"kind": UX_NOT_APPLICABLE, "reason": ux["reason"]}
        accept_ux = ux["decision"]["accepted"]
    return _projection(
        context,
        [row["requirement_id"] for row in body["requirements"]],
        projected,
        artifact.body["acceptance"]["accepted"],
        accept_ux,
    )


def _inputs_conflict(context: BootstrapContext) -> AdmissionRefused:
    return AdmissionRefused(
        AdmissionResultCode.MANIFEST_INPUTS_CONFLICT,
        f"Cycle {context.cycle_id!r} already has an accepted Input Manifest for "
        "different inputs. The Manifest is immutable and was not changed; a "
        "different Requirement selection or UX input needs a new cycle id.",
    )


def _reuse_existing_manifest(
    start: _Start, context: BootstrapContext
) -> ManifestResult:
    """Repeated `start` against a valid accepted Manifest: compare, never write.

    The comparison is over the caller-input projection, so the same inputs
    agree at any later wall-clock time and the persisted timestamps stand.
    """
    artifact, _ = _load_manifest(start.workspace, context)
    persisted_kind = artifact.body["manifest_body"]["ux"]["kind"]
    is_same_branch = (
        isinstance(start.ux, UxApplicable) and persisted_kind == UX_APPLICABLE
    ) or (isinstance(start.ux, UxNotApplicable) and persisted_kind == UX_NOT_APPLICABLE)
    if not is_same_branch:
        raise _inputs_conflict(context)
    current = _projection(
        context,
        start.selection,
        _admit_ux(start.workspace, start.ux),
        start.inputs.accept_inputs,
        start.inputs.accept_ux,
    )
    persisted = _persisted_projection(context, artifact)
    if start_input_digest(current) != start_input_digest(persisted):
        raise _inputs_conflict(context)
    return ManifestResult(context, artifact, is_newly_written=False)


# ---------------------------------------------------------------------------
# The atomic Manifest write (spec 13.1, 14.1) and its unknown outcomes (3.5)
# ---------------------------------------------------------------------------


def _resolve_after_mutation(
    start: _Start, reason: str, *, is_absent_retryable: bool
) -> ManifestResult | None:
    """Both rediscovery levels after a Manifest mutation, then classify (3.5).

    I04's rediscovery revalidates the cycle first and only then reaches the
    deterministic child. A valid accepted child is adopted, never rewritten; a
    refusing state keeps its own code; an absent child returns None only where
    the caller may retry the create at the same id.
    """
    with _cycle_refusals():
        found = rediscover_after_unknown_outcome(
            start.workspace,
            start.project_id,
            start.cycle_id,
            DocumentKind.INPUT_MANIFEST,
        )
    if found.outcome is CycleOutcome.D:
        return _reuse_existing_manifest(start, found.context)
    if found.outcome is CycleOutcome.E:
        assert found.refusal_code is not None  # set exactly in state E
        raise AdmissionRefused(found.refusal_code, f"{reason} {found.detail}")
    if found.outcome is CycleOutcome.B and is_absent_retryable:
        return None
    raise AdmissionRefused(
        CycleResultCode.FIBERY_WRITE_FAILED,
        f"{reason} Rediscovery found {found.outcome}; nothing was retried.",
    )


def _require_fresh_shell(start: _Start) -> DocumentPlacement | None:
    """After a known create: the gate again, then the shell to write into.

    The create is a revalidation boundary, so nothing read before it authorizes
    the body write. The one observation that does is the full discovery now
    reporting exactly the empty Manifest child this invocation just created —
    correctly placed under a still-valid Architecture — re-resolved immediately
    before the write. Returns None for any other observation.
    """
    found = _gate(start)
    is_own_shell = (
        found.outcome is CycleOutcome.E
        and found.refusal_code is CycleResultCode.MANIFEST_SHELL_UNRECOVERABLE
    )
    if not is_own_shell:
        return None
    child = _resolve_manifest_child(start.workspace, found.context)
    if child is None or _read_manifest_content(start.workspace, child).strip():
        return None
    return child


def _validate_manifest_write(start: _Start, emitted: str) -> ManifestResult:
    """Immediate read-back: success only if the intended Manifest is durable.

    A write call that returned normally proves nothing. The cycle is
    rediscovered, the child is read on fresh placements, and its payload must
    be exactly the one emitted.
    """
    found = _gate(start)
    if found.outcome is CycleOutcome.E:
        raise _refuse_gate_failure(found)
    if found.outcome is not CycleOutcome.D:
        raise AdmissionRefused(
            CycleResultCode.FIBERY_WRITE_FAILED,
            f"The Input Manifest write did not become durable: read-back found "
            f"{found.outcome}. Nothing was retried.",
        )
    artifact, payload = _load_manifest(start.workspace, found.context)
    if canonical_artifact_json(payload) != emitted:
        raise AdmissionRefused(
            CycleResultCode.FIBERY_WRITE_FAILED,
            "The Input Manifest read back as a different artifact than the one "
            "written. Nothing was overwritten or retried.",
        )
    return ManifestResult(found.context, artifact, is_newly_written=True)


def _write_manifest_body(start: _Start, carrier: str, emitted: str) -> ManifestResult:
    """The second half of the one Manifest write, into the shell just created."""
    shell = _require_fresh_shell(start)
    if shell is None:
        outcome = _resolve_after_mutation(
            start,
            "The created Input Manifest Document is not the empty shell that "
            "was just created; it was not written.",
            is_absent_retryable=False,
        )
        assert outcome is not None  # absent is not retryable here
        return outcome
    try:
        start.workspace.write_document_content(shell.secret, carrier)
    except FiberyError as error:
        outcome = _resolve_after_mutation(
            start,
            f"The Input Manifest write outcome is unknown ({error}).",
            is_absent_retryable=False,
        )
        assert outcome is not None  # absent is not retryable here
        return outcome
    return _validate_manifest_write(start, emitted)


def _attempt_manifest_write(
    start: _Start, admitted: AdmittedInputs, recorded_at: str
) -> ManifestResult | None:
    """One create-and-write attempt. Returns None when a retry is permitted.

    The gate runs immediately before the create and must report B: the
    Architecture is valid and no Document exists at the Manifest id.
    """
    found = _gate(start)
    if found.outcome is CycleOutcome.E:
        raise _refuse_gate_failure(found)
    if found.outcome is CycleOutcome.D:
        return _reuse_existing_manifest(start, found.context)
    if found.outcome is not CycleOutcome.B:
        raise AdmissionRefused(
            CycleResultCode.FIBERY_WRITE_FAILED,
            f"The cycle is no longer in bootstrap state B (found {found.outcome}); "
            "no Input Manifest was created.",
        )
    context = found.context
    sealed = build_input_manifest(context, admitted, start.inputs, recorded_at)
    try:
        start.workspace.create_tsa_child_document(
            context.input_manifest_document_id,
            input_manifest_document_name(context),
            context.architecture_document_id,
        )
    except FiberyError as error:
        return _resolve_after_mutation(
            start,
            f"The Input Manifest create outcome is unknown ({error}).",
            is_absent_retryable=True,
        )
    return _write_manifest_body(
        start, render_manifest_carrier(context, sealed), canonical_artifact_json(sealed)
    )


def _bootstrap_architecture(start: _Start) -> CycleDiscovery:
    """State A or an empty Architecture shell: I04's minimum write to reach B."""
    with _cycle_refusals():
        return ensure_bootstrap_architecture(
            start.workspace,
            start.project_id,
            start.cycle_id,
            create_if_absent=True,
            clock=start.clock,
        )


def _create_manifest(
    start: _Start, found: CycleDiscovery, admitted: AdmittedInputs
) -> ManifestResult:
    """Command-local `C`: validated inputs in hand, no Manifest durable yet.

    `admitted` was read before any mutation. It is read again, fresh, after
    every mutation boundary that precedes a create: the Architecture bootstrap,
    and an earlier create whose outcome was unknown.
    """
    is_admission_fresh = found.outcome is CycleOutcome.B
    if not is_admission_fresh:
        found = _bootstrap_architecture(start)
        if found.outcome is CycleOutcome.E:
            raise _refuse_gate_failure(found)
        if found.outcome is CycleOutcome.D:
            return _reuse_existing_manifest(start, found.context)
    recorded_at = created_at_now(start.clock)
    for _ in range(MANIFEST_CREATE_ATTEMPTS):
        if not is_admission_fresh:
            _readmit_unchanged(start, found.context, admitted)
        outcome = _attempt_manifest_write(start, admitted, recorded_at)
        if outcome is not None:
            return outcome
        is_admission_fresh = False
    raise AdmissionRefused(
        CycleResultCode.FIBERY_WRITE_FAILED,
        f"The Input Manifest create did not become durable in "
        f"{MANIFEST_CREATE_ATTEMPTS} attempts at the same deterministic id. "
        "Nothing else was written.",
    )


def start_input_manifest(
    workspace: CycleWorkspace,
    evidence: RequirementEvidenceWorkspace,
    project_id: str,
    raw_cycle_id: object,
    inputs: StartInputs,
    *,
    clock: Clock = _utc_now,
) -> ManifestResult:
    """Carry one cycle to a valid accepted Input Manifest, or refuse.

    Caller inputs and explicit acceptance are validated before any Fibery read.
    The I04 gate then decides: a refusing state writes nothing; an existing
    accepted Manifest is compared with the caller's inputs and never rewritten;
    otherwise the whole selection and the UX evidence are admitted before the
    first mutation, the Architecture is bootstrapped if it must be, and the
    Manifest is written as one complete artifact and read back.

    Raises `AdmissionRefused`. It calls no model and writes no Requirement.
    """
    selection = normalize_selection(inputs.requirement_ids)
    _require_acceptance(inputs)
    start = _Start(
        workspace=workspace,
        evidence=evidence,
        project_id=project_id,
        cycle_id=raw_cycle_id,
        selection=selection,
        ux=_normalize_ux(inputs.ux, selection),
        inputs=inputs,
        clock=clock,
    )
    found = _gate(start)
    if found.outcome is CycleOutcome.E:
        raise _refuse_gate_failure(found)
    if found.outcome is CycleOutcome.D:
        return _reuse_existing_manifest(start, found.context)
    admitted = admit_inputs(workspace, evidence, found.context, selection, start.ux)
    return _create_manifest(start, found, admitted)
