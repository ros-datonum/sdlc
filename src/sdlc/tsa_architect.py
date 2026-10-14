"""TSA-C01 I07 — the Architect stage: output contract, persist, apply, replay.

Implementation spec v0.3 sections 4.6.3, 9, 13.7, 14 and 16.1, with the v0.4
delta for rule S. For one cycle in durable state D this stage owns exactly:

- the response contract of 9.1, checked on the raw response (9.2), including
  rules S and X on every decoded string value before strip and escaping;
- the complete normalized `intended_output` (4.6.3.1), proven renderable by
  the I06 renderer before anything is written;
- the `tsa.process_result` artifact, persisted and confirmed by read-back
  BEFORE the Architecture Document is written (14.2);
- applying that output, first or next, through the I06 carrier builder to
  the same Architecture Document id, then confirming it by read-back;
- replaying a persisted output without a model call (cases 2 and 3), and
  refusing a divergent Architecture (case 4).

The boundary with later work items, stated so it cannot be mistaken:

- **I10** owns the complete normal recovery gate and its dispatch over every
  case of contract 14.3. What runs here is the stage-local subset the
  Architect stage itself needs before its own model call and mutations; it is
  re-run in full, fresh, at each of those boundaries, and nothing is assumed
  to have been checked elsewhere. Not performed here: the Reviewer side of
  the gate (Review currentness and derived status), Human Decision semantics
  beyond the structural REWORK binding that opens an iteration, dispositions,
  and inspection.
- **I08** owns the Reviewer. A successful result of this stage means only
  that iteration N's output is durable and applied; no review has run.
- **I12** owns the commands, their result codes and exit classes, and the
  workspace guard `hold_workspace(lock_scope)`, which contract 13 holds for a
  whole command. This stage does not take it, so a command can hold it around
  the stage without a nested acquisition. No Fibery transaction and no
  multi-host exclusion is claimed (contract 10, 13).

The current iteration is derived from durable state only: 1, or N + 1 where
iteration N carries a durable, structurally bound REWORK decision. A caller
cannot choose it, and re-running the stage never opens an iteration.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from sdlc.fibery_workspace import (
    DocumentPlacement,
    FiberyError,
    is_valid_child_placement,
    is_valid_root_placement,
)
from sdlc.model_runtime import ModelResponse, ModelRuntime, ModelRuntimeError
from sdlc.model_runtime_config import (
    TSA_ARCHITECT_ROLE,
    RuntimeSelection,
    select_runtime,
)
from sdlc.normative_tree import (
    NormativeTreeError,
    TreeManifest,
    document_fingerprint,
    read_normative_tree,
    render_normative_tree,
)
from sdlc.tsa_admission import (
    AdmissionRefused,
    AdmissionResultCode,
    AdmittedInputs,
    RequirementEvidenceWorkspace,
    UxApplicable,
    UxNotApplicable,
    admit_inputs,
)
from sdlc.tsa_architect_prompt import (
    ArchitectInputTooLarge,
    ArchitectPrompt,
    ArchitectPromptInput,
    RequirementMaterial,
    ReworkMaterial,
    build_architect_prompt,
    require_within_input_bound,
)
from sdlc.tsa_architecture import (
    ArchitectureBinding,
    ArchitectureCarrier,
    ArchitectureRefused,
    ArchitectureResultCode,
    build_architecture_carrier,
    render_architecture,
    validate_architecture_document,
)
from sdlc.tsa_artifacts import (
    ARCHITECT_ROLE,
    ARCHITECTURE,
    ARCHITECTURE_BOOTSTRAP_KEYS,
    FENCE_MARKER,
    HUMAN_DECISION,
    INPUT_MANIFEST,
    ITERATION_MAX,
    JSON_FENCE_OPENER,
    PROCESS_RESULT,
    REVIEW_RESULT,
    SCHEMA_VERSION,
    UX_APPLICABLE,
    ArtifactIdentity,
    InvalidTsaArtifact,
    TsaArtifact,
    canonical_artifact_json,
    canonical_json,
    extract_architecture_envelope,
    extract_artifact_payload,
    requirement_input_digest,
    sealed_artifact,
    ux_evidence_digest,
    validate_architect_response,
    validate_artifact,
    validate_intended_output,
    validate_structural_lineage,
)
from sdlc.tsa_cycle import (
    BootstrapContext,
    Clock,
    CycleOutcome,
    CycleRefused,
    CycleResultCode,
    CycleWorkspace,
    DocumentKind,
    bootstrap_readback_matches,
    build_bootstrap_artifact,
    created_at_now,
    derive_document_id,
    discover_cycle,
    render_bootstrap_carrier,
)
from sdlc.tsa_markdown import (
    BlockClassification,
    classify_code_blocks,
    has_fence_marker_line,
)

__all__ = [
    "ArchitectOutput",
    "ArchitectRefused",
    "ArchitectResultCode",
    "ArchitectStageOutcome",
    "ArchitectStageResult",
    "build_process_result",
    "process_result_document_name",
    "render_process_result_carrier",
    "run_architect_stage",
    "select_architect_runtime",
    "validate_architect_output",
]

#: Contract 5: the Process Result's navigation name. Never identity.
PROCESS_NAME_TEMPLATE = "TSA {cycle_id} — Process Result {iteration:04d}"
PROCESS_HEADING_TEMPLATE = "# {name}"
#: One line on purpose: Fibery stores a soft line break as a literal `<br>`.
PROCESS_PROSE = (
    "Immutable TSA artifact written by the Architect stage. It records one "
    "iteration's validated Architect output before that output is applied to "
    "the Architecture Document; it is not a review and not an approval."
)
#: The first create, then at most one retry at the same deterministic id, and
#: only after rediscovery showed the child absent (spec 3.5 step 4).
PROCESS_CREATE_ATTEMPTS = 2
FIRST_ITERATION = 1
REWORK = "REWORK"
APPROVE = "APPROVE"

#: The artifact types that may sit under an Architecture, and their id kind.
CHILD_KINDS = {
    INPUT_MANIFEST: DocumentKind.INPUT_MANIFEST,
    PROCESS_RESULT: DocumentKind.PROCESS_RESULT,
    REVIEW_RESULT: DocumentKind.REVIEW_RESULT,
    HUMAN_DECISION: DocumentKind.HUMAN_DECISION,
}


class ArchitectResultCode(StrEnum):
    """Frozen codes of spec 13.8 this stage decides that no earlier item owns."""

    CYCLE_NOT_FOUND = "CYCLE_NOT_FOUND"
    CYCLE_APPROVED = "CYCLE_APPROVED"
    MANIFEST_INPUTS_REQUIRED = "MANIFEST_INPUTS_REQUIRED"
    MODEL_RUNTIME_FAILED = "MODEL_RUNTIME_FAILED"
    INVALID_MODEL_OUTPUT = "INVALID_MODEL_OUTPUT"
    ARCHITECTURE_DIVERGED = "ARCHITECTURE_DIVERGED"
    ARTIFACT_DUPLICATE = "ARTIFACT_DUPLICATE"
    DECISION_SHELL_UNRECOVERABLE = "DECISION_SHELL_UNRECOVERABLE"
    ITERATION_LIMIT = "ITERATION_LIMIT"


ResultCode = (
    ArchitectResultCode | CycleResultCode | AdmissionResultCode | ArchitectureResultCode
)

#: The I01 refusal codes that carry their own frozen meaning.
_ARTIFACT_CODES: dict[str, ResultCode] = {
    CycleResultCode.MANIFEST_ACCEPTANCE_MISMATCH: (
        CycleResultCode.MANIFEST_ACCEPTANCE_MISMATCH
    ),
    ArchitectResultCode.ITERATION_LIMIT: ArchitectResultCode.ITERATION_LIMIT,
}


class ArchitectRefused(Exception):
    """A controlled refusal with one frozen result code of spec 13.8.

    A refusal raised by I04, I05 or I06 keeps the code it was given. `details`
    names Documents and Requirements by id; it never carries model output.
    """

    def __init__(
        self, code: ResultCode, message: str, details: tuple[str, ...] = ()
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = details


class ArchitectStageOutcome(StrEnum):
    """What the stage established. None of these is a result code (13.8)."""

    #: One fresh Architect call; its output persisted, then applied.
    OUTPUT_APPLIED = "OUTPUT_APPLIED"
    #: Case 2: a persisted output applied without a model call.
    RECORDED_OUTPUT_APPLIED = "RECORDED_OUTPUT_APPLIED"
    #: Case 3: the Architecture already held the output; nothing was written.
    ALREADY_APPLIED = "ALREADY_APPLIED"


@dataclass(frozen=True)
class ArchitectStageResult:
    """Iteration N's Architect output is durable and applied. Nothing more.

    The Reviewer has not run: this is not the Human Decision boundary, not a
    review, not an approval, and not the outcome of any command.
    """

    outcome: ArchitectStageOutcome
    iteration: int
    architecture_document_id: str
    process_result_document_id: str
    process_result_digest: str
    input_fingerprint: str
    output_fingerprint: str
    model_invoked: bool
    process_written: bool
    architecture_written: bool


class _ChildState(StrEnum):
    ABSENT = "ABSENT"
    EMPTY = "EMPTY"
    VALID = "VALID"


@dataclass(frozen=True)
class _Child:
    """One deterministic-id child slot as just observed."""

    state: _ChildState
    document_id: str
    artifact: TsaArtifact | None = None
    payload: dict[str, object] | None = None


class _Form(StrEnum):
    EMPTY = "EMPTY"
    BOOTSTRAP = "BOOTSTRAP"
    APPLIED = "APPLIED"


@dataclass(frozen=True)
class _Architecture:
    """The Architecture Document as just read and validated."""

    form: _Form
    content: str
    artifact: TsaArtifact | None = None
    payload: dict[str, object] | None = None
    fingerprint: str | None = None


@dataclass(frozen=True)
class _Rework:
    """The durable REWORK that opened the current iteration, with its lineage."""

    iteration: int
    decision: TsaArtifact
    review: TsaArtifact


@dataclass(frozen=True)
class _View:
    """One fresh stage-local gate pass. Dead after any model call or mutation."""

    context: BootstrapContext
    manifest: TsaArtifact
    iteration: int
    rework: _Rework | None
    architecture: _Architecture
    process: _Child
    has_review: bool

    @property
    def manifest_body(self) -> dict[str, object]:
        return self.manifest.body["manifest_body"]


@dataclass(frozen=True)
class ArchitectOutput:
    """A response that passed the raw contract and renders under I06."""

    architect_response: dict[str, object]
    intended_output: dict[str, object]
    content_fingerprint: str


@dataclass(frozen=True)
class _Stage:
    workspace: CycleWorkspace
    evidence: RequirementEvidenceWorkspace
    project_id: str
    cycle_id: object


def _utc_now() -> datetime:
    return datetime.now(UTC)


def select_architect_runtime(
    config: dict[str, object],
    runtime_override: str | None = None,
    model_override: str | None = None,
) -> RuntimeSelection:
    """The I09 role through the unchanged selection precedence."""
    return select_runtime(config, TSA_ARCHITECT_ROLE, runtime_override, model_override)


# ---------------------------------------------------------------------------
# Refusal plumbing
# ---------------------------------------------------------------------------


def _artifact_code(error: InvalidTsaArtifact) -> ResultCode:
    return _ARTIFACT_CODES.get(error.code, CycleResultCode.ARTIFACT_MALFORMED)


@contextmanager
def _reading(subject: str) -> Iterator[None]:
    """An adapter read failure is the frozen `FIBERY_READ_FAILED`."""
    try:
        yield
    except FiberyError as error:
        raise ArchitectRefused(
            CycleResultCode.FIBERY_READ_FAILED, f"Reading {subject} failed: {error}"
        ) from error


@contextmanager
def _validating(subject: str) -> Iterator[None]:
    """I01 and I06 refusals keep their frozen codes, naming the Document."""
    try:
        yield
    except InvalidTsaArtifact as error:
        raise ArchitectRefused(_artifact_code(error), f"{subject}: {error}") from error
    except ArchitectureRefused as refused:
        raise ArchitectRefused(refused.code, f"{subject}: {refused}") from refused


def _malformed(message: str) -> ArchitectRefused:
    return ArchitectRefused(CycleResultCode.ARTIFACT_MALFORMED, message)


def _write_failed(message: str) -> ArchitectRefused:
    return ArchitectRefused(CycleResultCode.FIBERY_WRITE_FAILED, message)


def _stale(message: str, details: tuple[str, ...] = ()) -> ArchitectRefused:
    return ArchitectRefused(AdmissionResultCode.INPUTS_STALE, message, details)


# ---------------------------------------------------------------------------
# The raw response contract (spec 9.1, 9.2; v0.4 sections 4 and 5)
# ---------------------------------------------------------------------------


def _invalid_output(message: str) -> ArchitectRefused:
    return ArchitectRefused(
        ArchitectResultCode.INVALID_MODEL_OUTPUT,
        f"The Architect response does not satisfy its closed contract: {message} "
        "It was not repaired, re-requested or persisted.",
    )


def _refuse_duplicate_names(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """A key named twice: `json.loads` would silently keep the last one."""
    names = [name for name, _ in pairs]
    repeated = sorted({name for name in names if names.count(name) > 1})
    if repeated:
        raise _invalid_output(f"the object names {repeated} more than once.")
    return dict(pairs)


def _refuse_constant(name: str) -> object:
    raise _invalid_output(f"{name} is not a JSON value.")


def _decode_response(text: str) -> dict[str, object]:
    """Exactly one JSON object; whitespace around it is the only allowance.

    No fence is unwrapped and no prose is skipped: anything else fails to
    decode and is refused.
    """
    try:
        decoded = json.loads(
            text,
            object_pairs_hook=_refuse_duplicate_names,
            parse_constant=_refuse_constant,
        )
    except ArchitectRefused:
        raise
    except (ValueError, RecursionError) as error:
        raise _invalid_output(
            "it is not exactly one JSON object with nothing around it "
            f"({type(error).__name__})."
        ) from error
    if not isinstance(decoded, dict):
        raise _invalid_output(f"it is a JSON {type(decoded).__name__}, not an object.")
    return decoded


def _string_values(value: object, path: str) -> Iterator[tuple[str, str]]:
    """Every decoded string value with its path; keys are closed by the schema."""
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _string_values(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _string_values(item, f"{path}[{index}]")


def _require_no_code_block(path: str, value: str) -> None:
    """Rules S and X on one complete decoded value, before strip (9.2)."""
    classification = classify_code_blocks(value)
    if classification.outcome is BlockClassification.CODE_BLOCK:
        raise _invalid_output(
            f"{path} contains a code block starting on line {classification.line} "
            "(rule S)."
        )
    if classification.outcome is BlockClassification.UNCLASSIFIABLE:
        raise _invalid_output(
            f"the block structure of {path} could not be classified "
            f"({classification.reason}), so rule S cannot be shown to hold."
        )
    if has_fence_marker_line(value):
        raise _invalid_output(
            f"{path} has a line opening with three or more backticks or tildes "
            "(rule X)."
        )


def _require_selected_product_questions(
    response: dict[str, object], manifest_body: dict[str, object]
) -> None:
    """A product question names a selected Requirement, never another id (9.1)."""
    selected = {row["requirement_id"] for row in manifest_body["requirements"]}
    for index, question in enumerate(response["product_questions"]):
        if question["requirement_id"] not in selected:
            raise _invalid_output(
                f"product_questions[{index}] names {question['requirement_id']!r}, "
                "which the Input Manifest did not select."
            )


def _normalized_intended_output(response: dict[str, object]) -> dict[str, object]:
    """The complete renderer input of 4.6.3.1, in I01's canonical form.

    `architecture` becomes `sections`, the five arrays are kept, traceability
    is ordered by `requirement_id`, and every string takes the NFC form the
    persisted artifact will carry, so the first apply renders exactly what a
    replay of the persisted output renders. No value is stripped, defaulted or
    invented; the renderer strips at escape time.
    """
    intended = {
        "sections": response["architecture"],
        "traceability": sorted(
            response["traceability"], key=lambda row: row["requirement_id"]
        ),
        "assumptions": response["assumptions"],
        "risks": response["risks"],
        "open_architecture_questions": response["open_architecture_questions"],
        "product_questions": response["product_questions"],
    }
    return json.loads(canonical_json(intended))


def validate_architect_output(
    text: str, manifest_body: dict[str, object]
) -> ArchitectOutput:
    """The raw response against 9.1 and 9.2, then renderability under I06.

    Order: decode exactly one object; the closed schema; rules S and X on every
    decoded string value before strip or escaping; product questions bound to
    the selection; the normalized `intended_output`; and a render, so a
    traceability, section or render refusal keeps its own frozen code. Pure:
    nothing is read, written or repaired. Structural only — whether the
    architecture is adequate, or prose smuggles a Task, is Reviewer evidence.
    """
    response = _decode_response(text)
    try:
        validate_architect_response(response, ("response",))
    except InvalidTsaArtifact as error:
        raise _invalid_output(str(error)) from error
    for path, value in _string_values(response, "response"):
        _require_no_code_block(path, value)
    _require_selected_product_questions(response, manifest_body)
    try:
        intended = _normalized_intended_output(response)
        validate_intended_output(intended)
    except InvalidTsaArtifact as error:
        raise _invalid_output(str(error)) from error
    with _validating("The Architect output does not render"):
        rendered = render_architecture(intended, manifest_body)
    return ArchitectOutput(response, intended, rendered.content_fingerprint)


# ---------------------------------------------------------------------------
# Reading durable state: children, the Architecture, the iteration
# ---------------------------------------------------------------------------


def _child_id(
    context: BootstrapContext, kind: DocumentKind, iteration: int | None
) -> str:
    return derive_document_id(
        context.workspace_identity,
        context.project_entity_id,
        context.cycle_id,
        kind,
        iteration,
    )


def _read_secret(
    workspace: CycleWorkspace, placement: DocumentPlacement, subject: str
) -> str:
    if not placement.secret:
        raise ArchitectRefused(
            CycleResultCode.FIBERY_READ_FAILED,
            f"{subject} {placement.document_id!r} exposes no content secret.",
        )
    with _reading(f"{subject} {placement.document_id!r}"):
        return workspace.read_document_content(placement.secret)


def _resolve_root(
    workspace: CycleWorkspace, context: BootstrapContext
) -> DocumentPlacement:
    """The Architecture root, resolved now and checked locally (2.2.1)."""
    document_id = context.architecture_document_id
    with _reading(f"the placement of Architecture Document {document_id!r}"):
        root = workspace.resolve_placement(document_id)
    if root is None:
        raise ArchitectRefused(
            CycleResultCode.FIBERY_READ_FAILED,
            f"Architecture Document {document_id!r} no longer resolves.",
        )
    if not is_valid_root_placement(
        root, context.project_type_id, context.project_public_id
    ):
        raise ArchitectRefused(
            CycleResultCode.CYCLE_FOREIGN_PROJECT,
            f"Document {document_id!r} is not a root of the target Project.",
        )
    return root


def _resolve_child(
    workspace: CycleWorkspace, context: BootstrapContext, document_id: str
) -> DocumentPlacement | None:
    """One child and its root, both resolved now; a foreign child is refused."""
    with _reading(f"the placement of Document {document_id!r}"):
        child = workspace.resolve_placement(document_id)
    if child is None:
        return None
    root = _resolve_root(workspace, context)
    if not is_valid_child_placement(
        child,
        root,
        context.architecture_document_id,
        context.project_type_id,
        context.project_public_id,
    ):
        raise ArchitectRefused(
            CycleResultCode.CYCLE_FOREIGN_PROJECT,
            f"Document {document_id!r} is not a child of the Architecture root.",
        )
    return child


def _require_identity(
    artifact: TsaArtifact, context: BootstrapContext, subject: str
) -> None:
    """Every identity a persisted artifact carries equals the trusted context."""
    for field, actual, expected in (
        ("workspace_identity", artifact.workspace_identity, context.workspace_identity),
        ("project_entity_id", artifact.project_entity_id, context.project_entity_id),
        ("project_code", artifact.project_code, context.project_code),
        ("cycle_id", artifact.cycle_id, context.cycle_id),
    ):
        if actual != expected:
            raise _malformed(
                f"{subject} carries {field} {actual!r}, not the trusted {expected!r}."
            )


def _parse_child(
    content: str, context: BootstrapContext, subject: str
) -> tuple[TsaArtifact, dict[str, object]]:
    with _validating(subject):
        payload = extract_artifact_payload(content)
        artifact = validate_artifact(payload)
    _require_identity(artifact, context, subject)
    return artifact, payload


def _read_child(
    workspace: CycleWorkspace,
    context: BootstrapContext,
    artifact_type: str,
    iteration: int | None,
) -> _Child:
    """A deterministic-id child: absent, an empty shell, or one valid artifact.

    Malformed content, a foreign placement or an artifact other than the one
    its id derives from is refused; nothing is ever repaired (14.4).
    """
    document_id = _child_id(context, CHILD_KINDS[artifact_type], iteration)
    placement = _resolve_child(workspace, context, document_id)
    if placement is None:
        return _Child(_ChildState.ABSENT, document_id)
    subject = f"{artifact_type} Document {document_id!r}"
    content = _read_secret(workspace, placement, subject)
    if not content.strip():
        return _Child(_ChildState.EMPTY, document_id)
    artifact, payload = _parse_child(content, context, subject)
    if artifact.artifact_type != artifact_type or artifact.iteration != iteration:
        raise _malformed(
            f"{subject} holds {artifact.artifact_type} iteration "
            f"{artifact.iteration}, not the artifact its id derives from."
        )
    return _Child(_ChildState.VALID, document_id, artifact, payload)


def _read_manifest(workspace: CycleWorkspace, context: BootstrapContext) -> TsaArtifact:
    manifest = _read_child(workspace, context, INPUT_MANIFEST, None)
    if manifest.state is _ChildState.EMPTY:
        raise ArchitectRefused(
            CycleResultCode.MANIFEST_SHELL_UNRECOVERABLE,
            f"Input Manifest Document {manifest.document_id!r} is an empty shell.",
        )
    if manifest.artifact is None:
        raise ArchitectRefused(
            ArchitectResultCode.MANIFEST_INPUTS_REQUIRED,
            f"Input Manifest Document {manifest.document_id!r} no longer resolves.",
        )
    return manifest.artifact


def _scan_children(
    workspace: CycleWorkspace, context: BootstrapContext
) -> set[tuple[str, int | None]]:
    """Every artifact under the Architecture, each only at its derived id.

    The `child_documents` cross-check of 13.7-4: an artifact of this cycle at
    any other id is a second claim to its slot, `ARTIFACT_DUPLICATE`. An empty
    Document at a non-derived id carries no artifact and claims nothing. One
    content read per child; a cycle holds the Manifest and at most three
    children per iteration.
    """
    parent = context.architecture_document_id
    with _reading(f"the children of Architecture Document {parent!r}"):
        placements = workspace.child_placements(parent)
    slots: set[tuple[str, int | None]] = set()
    for placement in placements:
        subject = f"Child Document {placement.document_id!r}"
        content = _read_secret(workspace, placement, subject)
        if not content.strip():
            continue
        artifact, _ = _parse_child(content, context, subject)
        kind = CHILD_KINDS.get(artifact.artifact_type)
        if kind is None:
            raise _malformed(f"{subject} holds {artifact.artifact_type}, not a child.")
        if placement.document_id != _child_id(context, kind, artifact.iteration):
            raise ArchitectRefused(
                ArchitectResultCode.ARTIFACT_DUPLICATE,
                f"{subject} holds {artifact.artifact_type} iteration "
                f"{artifact.iteration} at a non-derived id; that slot has one "
                "identity only.",
                (placement.document_id,),
            )
        slots.add((artifact.artifact_type, artifact.iteration))
    return slots


def _normative_markdown(content: str) -> str:
    """Everything before the one `json` opener I01 has already accepted."""
    lines = content.split("\n")
    opener = next(
        index for index, line in enumerate(lines) if line.strip() == JSON_FENCE_OPENER
    )
    return "\n".join(lines[:opener])


def _require_bootstrap_carrier(
    context: BootstrapContext,
    content: str,
    artifact: TsaArtifact,
    payload: dict[str, object],
) -> None:
    """The exact pre-apply carrier, rebuilt from trusted context (4.1.1)."""
    try:
        expected = build_bootstrap_artifact(context, artifact.body["created_at"])
    except ValueError as error:
        raise _malformed(f"The bootstrap carrier cannot conform: {error}") from error
    is_exact = canonical_artifact_json(payload) == canonical_artifact_json(expected)
    if not is_exact or not bootstrap_readback_matches(
        render_bootstrap_carrier(context, expected), content
    ):
        raise _malformed(
            f"Architecture Document {context.architecture_document_id!r} is not "
            "the exact bootstrap carrier."
        )


def _read_architecture(
    workspace: CycleWorkspace,
    context: BootstrapContext,
    manifest_body: dict[str, object],
) -> _Architecture:
    """Read the Architecture now and validate it in the form it claims.

    Pre-apply it must be exactly the I04 bootstrap carrier; post-apply it must
    pass the I06 Document validator against this Manifest. Its fingerprint is
    `document_fingerprint` of the Markdown before the envelope (4.6.1) — for a
    bootstrap carrier that is computed from its real content, never assumed.
    """
    placement = _resolve_root(workspace, context)
    subject = f"Architecture Document {placement.document_id!r}"
    content = _read_secret(workspace, placement, subject)
    if not content.strip():
        return _Architecture(_Form.EMPTY, content)
    with _validating(subject):
        payload = extract_architecture_envelope(content)
        artifact = validate_artifact(payload)
    if artifact.artifact_type != ARCHITECTURE:
        raise _malformed(f"{subject} holds {artifact.artifact_type}.")
    _require_identity(artifact, context, subject)
    if set(artifact.body) == set(ARCHITECTURE_BOOTSTRAP_KEYS):
        _require_bootstrap_carrier(context, content, artifact, payload)
        form = _Form.BOOTSTRAP
    else:
        with _validating(subject):
            validate_architecture_document(content, manifest_body)
        form = _Form.APPLIED
    return _Architecture(
        form,
        content,
        artifact,
        payload,
        document_fingerprint(_normative_markdown(content)),
    )


def _verify_rework(
    workspace: CycleWorkspace,
    context: BootstrapContext,
    manifest: TsaArtifact,
    architecture: _Architecture,
    decision: TsaArtifact,
    iteration: int,
) -> _Rework:
    """A durable REWORK opens iteration + 1 only if it binds this cycle's lineage.

    Structural only: the Review and Process it names exist at their derived
    ids, invariants 1-5 of 4.6.5 hold, every document id and digest it repeats
    is the real one, and the Architecture it bound is the rendering of that
    Process output (invariant 7). Disposition semantics are I11's.
    """
    review = _read_child(workspace, context, REVIEW_RESULT, iteration)
    process = _read_child(workspace, context, PROCESS_RESULT, iteration)
    if review.artifact is None or process.artifact is None:
        raise _malformed(
            f"The REWORK of iteration {iteration} names no durable Review and "
            "Process Result for that iteration."
        )
    with _validating(f"The REWORK of iteration {iteration}"):
        validate_structural_lineage(
            architecture=architecture.artifact,
            input_manifest=manifest,
            process_result=process.artifact,
            review_result=review.artifact,
            human_decision=decision,
            review_document_id=review.document_id,
        )
    _require_rework_bindings(context, manifest, decision, review, process)
    return _Rework(iteration, decision, review.artifact)


def _require_rework_bindings(
    context: BootstrapContext,
    manifest: TsaArtifact,
    decision: TsaArtifact,
    review: _Child,
    process: _Child,
) -> None:
    """Every id and digest the REWORK and its Review repeat is the real one."""
    assert review.artifact is not None and process.artifact is not None
    iteration = decision.iteration
    subject = f"The REWORK of iteration {iteration}"
    body = decision.body
    bound = {
        "architecture_document_id": context.architecture_document_id,
        "process_result": {
            "document_id": process.document_id,
            "payload_digest": process.artifact.artifact_digest,
        },
        "ux_evidence_digest": ux_evidence_digest(manifest.body["manifest_body"]["ux"]),
    }
    for field, expected in bound.items():
        if body[field] != expected:
            raise _malformed(f"{subject} binds another {field} than the cycle's.")
    for field, expected in (
        ("process_result_document_id", process.document_id),
        ("architecture_document_id", context.architecture_document_id),
    ):
        if review.artifact.body[field] != expected:
            raise _malformed(
                f"The Review Result of iteration {iteration} binds another {field}."
            )
    with _validating(f"The Process Result of iteration {iteration}"):
        rendered = render_architecture(
            process.artifact.body["intended_output"], manifest.body["manifest_body"]
        )
    if rendered.content_fingerprint != body["architecture_fingerprint"]:
        raise _malformed(
            f"{subject} bound an Architecture that is not the rendering of "
            f"Process Result {iteration}."
        )


def _current_iteration(
    workspace: CycleWorkspace,
    context: BootstrapContext,
    manifest: TsaArtifact,
    architecture: _Architecture,
) -> tuple[int, _Rework | None]:
    """1, or the iteration after the last durable, bound REWORK (contract 6)."""
    iteration = FIRST_ITERATION
    rework: _Rework | None = None
    while True:
        decision = _read_child(workspace, context, HUMAN_DECISION, iteration)
        if decision.state is _ChildState.ABSENT:
            return iteration, rework
        if decision.artifact is None:
            raise ArchitectRefused(
                ArchitectResultCode.DECISION_SHELL_UNRECOVERABLE,
                f"Human Decision Document {decision.document_id!r} is an empty shell.",
            )
        if decision.artifact.body["decision"] == APPROVE:
            raise ArchitectRefused(
                ArchitectResultCode.CYCLE_APPROVED,
                f"Iteration {iteration} carries an APPROVE; the cycle is closed to "
                "writes and nothing was written.",
            )
        rework = _verify_rework(
            workspace, context, manifest, architecture, decision.artifact, iteration
        )
        iteration += 1
        if iteration > ITERATION_MAX:
            raise ArchitectRefused(
                ArchitectResultCode.ITERATION_LIMIT,
                f"A REWORK of iteration {ITERATION_MAX} would open iteration "
                f"{iteration}; the limit is {ITERATION_MAX}.",
            )


# ---------------------------------------------------------------------------
# Input currentness (contract 4.4, 10; spec 14.3)
# ---------------------------------------------------------------------------


def _recorded_ux_input(ux: dict[str, object]) -> UxApplicable | UxNotApplicable:
    if ux["kind"] == UX_APPLICABLE:
        return UxApplicable(ux["document_id"], tuple(ux["scope_requirement_ids"]))
    return UxNotApplicable(ux["reason"])


def _require_inputs_current(
    stage: _Stage, context: BootstrapContext, manifest: TsaArtifact
) -> None:
    """Admit the recorded selection again, fresh, and compare it with the Manifest.

    I05's own admission runs unchanged and its rows are compared through the
    I01 requirement-input digest; nothing is re-bound to changed evidence. UX
    follows the recorded branch only (contract 4.4): `APPLICABLE` compares the
    Document id, scope and content digest read now; `NOT_APPLICABLE` reads no
    Document and compares its recorded input binding.
    """
    body = manifest.body["manifest_body"]
    fresh = _readmit(stage, context, body)
    fresh_digest = requirement_input_digest(list(fresh.requirements))
    if fresh_digest != requirement_input_digest(body["requirements"]):
        changed = tuple(
            str(row["requirement_id"])
            for row, now in zip(body["requirements"], fresh.requirements, strict=True)
            if requirement_input_digest([row]) != requirement_input_digest([now])
        )
        raise _stale(
            "Requirement evidence changed since the Manifest was accepted.", changed
        )
    _require_ux_current(body["ux"], fresh.ux, fresh_digest)


def _readmit(
    stage: _Stage, context: BootstrapContext, body: dict[str, object]
) -> AdmittedInputs:
    """I05 admission of the recorded selection and UX branch, run now.

    A read failure keeps `FIBERY_READ_FAILED`; any admission refusal of a
    frozen input is drift, `INPUTS_STALE`, with the original code in details.
    """
    selection = tuple(row["requirement_id"] for row in body["requirements"])
    try:
        return admit_inputs(
            stage.workspace,
            stage.evidence,
            context,
            selection,
            _recorded_ux_input(body["ux"]),
        )
    except AdmissionRefused as refused:
        if refused.code is CycleResultCode.FIBERY_READ_FAILED:
            raise ArchitectRefused(
                refused.code, str(refused), refused.details
            ) from refused
        raise _stale(
            f"The accepted inputs are no longer current: {refused}",
            (str(refused.code), *refused.details),
        ) from refused


def _require_ux_current(
    recorded_ux: dict[str, object], fresh_ux: dict[str, object], fresh_digest: str
) -> None:
    """Contract 4.4, by the recorded branch only."""
    if recorded_ux["kind"] == UX_APPLICABLE:
        recorded = {key: recorded_ux[key] for key in fresh_ux}
        if json.loads(canonical_json(fresh_ux)) != recorded:
            raise _stale(
                "The UX Document no longer matches its accepted digest and scope.",
                (str(recorded_ux["document_id"]),),
            )
    elif recorded_ux["requirement_input_digest"] != fresh_digest:
        raise _stale(
            "The NOT_APPLICABLE UX decision no longer binds the current inputs."
        )


# ---------------------------------------------------------------------------
# The stage-local gate
# ---------------------------------------------------------------------------


def _discover(stage: _Stage) -> BootstrapContext:
    """I04 discovery: the cycle-level revalidation. Only state D proceeds."""
    try:
        found = discover_cycle(stage.workspace, stage.project_id, stage.cycle_id)
    except CycleRefused as refused:
        raise ArchitectRefused(refused.code, str(refused)) from refused
    if found.outcome is CycleOutcome.E:
        assert found.refusal_code is not None  # set exactly in state E
        raise ArchitectRefused(found.refusal_code, found.detail)
    if found.outcome is CycleOutcome.A:
        raise ArchitectRefused(
            ArchitectResultCode.CYCLE_NOT_FOUND,
            f"No Architecture Document exists for cycle {found.context.cycle_id!r}.",
        )
    if found.outcome is not CycleOutcome.D:
        raise ArchitectRefused(
            ArchitectResultCode.MANIFEST_INPUTS_REQUIRED,
            f"Cycle {found.context.cycle_id!r} has no valid accepted Input Manifest "
            f"({found.outcome}); the Architect is never called before one exists.",
        )
    return found.context


def _require_not_empty(architecture: _Architecture, context: BootstrapContext) -> None:
    if architecture.form is _Form.EMPTY:
        raise ArchitectRefused(
            ArchitectResultCode.ARCHITECTURE_DIVERGED,
            f"Architecture Document {context.architecture_document_id!r} is empty "
            "although an accepted Manifest exists: it is neither an input nor an "
            "output of any iteration. Nothing was written.",
        )


def _require_no_later_iteration(
    slots: set[tuple[str, int | None]], iteration: int
) -> None:
    """Only a REWORK opens an iteration; an artifact beyond it is malformed."""
    later = sorted(slot for slot in slots if (slot[1] or 0) > iteration)
    if later:
        raise _malformed(
            f"Artifacts exist for iterations no REWORK opened: {later}; the "
            f"current iteration is {iteration}."
        )


def _gate(stage: _Stage) -> _View:
    """Everything the Architect stage relies on, read fresh, in one pass.

    Discovery (I04), the accepted Manifest, the children cross-check, the
    Architecture in its claimed form, the iteration, input currentness, then
    the iteration's Process and Review slots. A failure refuses before any
    model call or mutation (contract 14.1). This is the stage-local subset of
    the normal gate, not I10's complete dispatcher.
    """
    context = _discover(stage)
    manifest = _read_manifest(stage.workspace, context)
    slots = _scan_children(stage.workspace, context)
    architecture = _read_architecture(
        stage.workspace, context, manifest.body["manifest_body"]
    )
    _require_not_empty(architecture, context)
    iteration, rework = _current_iteration(
        stage.workspace, context, manifest, architecture
    )
    _require_no_later_iteration(slots, iteration)
    _require_inputs_current(stage, context, manifest)
    process = _read_child(stage.workspace, context, PROCESS_RESULT, iteration)
    review_id = _child_id(context, DocumentKind.REVIEW_RESULT, iteration)
    has_review = _resolve_child(stage.workspace, context, review_id) is not None
    if has_review and process.state is not _ChildState.VALID:
        raise _malformed(
            f"A Review Result Document exists for iteration {iteration} but no "
            "Process Result does."
        )
    return _View(
        context, manifest, iteration, rework, architecture, process, has_review
    )


# ---------------------------------------------------------------------------
# Classifying the Architecture against one Process Result (14.3, 13.7-3)
# ---------------------------------------------------------------------------


def _expected_carrier(view: _View, process: TsaArtifact) -> ArchitectureCarrier:
    """The exact post-apply Document for iteration N, from persisted output only.

    `intended_output` is read from the persisted Process Result, never from
    `architect_response`, and the Architecture's own persisted `created_at` is
    kept. No clock is read.
    """
    architecture = view.architecture
    assert architecture.artifact is not None  # the gate refuses an empty one
    context = view.context
    binding = ArchitectureBinding(
        identity=ArtifactIdentity(
            workspace_identity=context.workspace_identity,
            project_entity_id=context.project_entity_id,
            project_code=str(context.project_code),
            cycle_id=context.cycle_id,
        ),
        created_at=architecture.artifact.body["created_at"],
        current_iteration=view.iteration,
    )
    with _validating(f"Process Result {view.process.document_id!r} does not replay"):
        return build_architecture_carrier(
            process.body["intended_output"], view.manifest_body, binding
        )


def _holds_output(architecture: _Architecture, expected: ArchitectureCarrier) -> bool:
    if architecture.form is not _Form.APPLIED or architecture.payload is None:
        return False
    envelope = extract_architecture_envelope(expected.text)
    return canonical_artifact_json(architecture.payload) == canonical_artifact_json(
        envelope
    )


def _diverged(
    view: _View, process: TsaArtifact, expected: ArchitectureCarrier
) -> ArchitectRefused:
    """Case 4: refuse and report all three fingerprints (contract 14.3)."""
    return ArchitectRefused(
        ArchitectResultCode.ARCHITECTURE_DIVERGED,
        f"Architecture Document {view.context.architecture_document_id!r} matches "
        f"neither the recorded input nor the recorded output of iteration "
        f"{view.iteration}. Nothing was overwritten and no model was called; a "
        "human decides which is authoritative.",
        (
            f"input {process.body['input_fingerprint']}",
            f"output {expected.content_fingerprint}",
            f"current {view.architecture.fingerprint}",
        ),
    )


class _Case(StrEnum):
    INPUT = "INPUT"
    OUTPUT = "OUTPUT"


def _classify(
    view: _View, process: TsaArtifact, expected: ArchitectureCarrier
) -> _Case:
    """Case 3 before case 2: input == output is already applied (13.7-3)."""
    if _holds_output(view.architecture, expected):
        return _Case.OUTPUT
    if view.has_review:
        raise _malformed(
            f"A Review Result exists for iteration {view.iteration} but the "
            "Architecture does not hold that iteration's output."
        )
    if view.architecture.fingerprint == process.body["input_fingerprint"]:
        return _Case.INPUT
    raise _diverged(view, process, expected)


# ---------------------------------------------------------------------------
# Apply (14.1, 14.2) and its read-back
# ---------------------------------------------------------------------------


def _require_same_process(view: _View, persisted: dict[str, object]) -> TsaArtifact:
    process = view.process
    if process.artifact is None or process.payload is None:
        raise _write_failed(
            f"Process Result {process.document_id!r} is no longer durable; the "
            "Architecture was not written."
        )
    if canonical_artifact_json(process.payload) != canonical_artifact_json(persisted):
        raise _write_failed(
            f"Process Result {process.document_id!r} is no longer the artifact "
            "this stage confirmed; the Architecture was not written."
        )
    return process.artifact


def _confirm_architecture(
    stage: _Stage, context: BootstrapContext, view: _View, expected: ArchitectureCarrier
) -> None:
    """Immediate read-back on a fresh placement: success only for the output."""
    after = _read_architecture(stage.workspace, context, view.manifest_body)
    if after.form is _Form.EMPTY:
        raise _write_failed(
            f"Architecture Document {context.architecture_document_id!r} read back "
            "empty after the apply; nothing was retried."
        )
    if _holds_output(after, expected):
        return
    if after.fingerprint == view.architecture.fingerprint:
        raise _write_failed(
            f"Architecture Document {context.architecture_document_id!r} still "
            "holds the recorded input after the apply; nothing was retried."
        )
    raise ArchitectRefused(
        ArchitectResultCode.ARCHITECTURE_DIVERGED,
        f"Architecture Document {context.architecture_document_id!r} read back as "
        "neither the recorded input nor the intended output.",
        (f"output {expected.content_fingerprint}", f"current {after.fingerprint}"),
    )


def _apply(
    stage: _Stage, persisted: dict[str, object]
) -> tuple[bool, ArchitectureCarrier]:
    """Apply one persisted Process Result. Returns whether a write happened.

    The gate runs fresh first; then only the root placement is resolved before
    the write, with no content read in between (2.2.1). An unknown write
    outcome is classified from durable state and never retried blind.
    """
    view = _gate(stage)
    process = _require_same_process(view, persisted)
    expected = _expected_carrier(view, process)
    if _classify(view, process, expected) is _Case.OUTPUT:
        return False, expected
    root = _resolve_root(stage.workspace, view.context)
    if not root.secret:
        raise _write_failed(
            f"Architecture Document {root.document_id!r} has no secret."
        )
    try:
        stage.workspace.write_document_content(root.secret, expected.text)
    except FiberyError as error:
        after = _gate(stage)
        if _classify(after, process, expected) is _Case.OUTPUT:
            return True, expected
        raise _write_failed(
            f"The Architecture write outcome was unknown ({error}) and the "
            "Architecture still holds the recorded input; nothing was retried."
        ) from error
    _confirm_architecture(stage, view.context, view, expected)
    return True, expected


# ---------------------------------------------------------------------------
# Persisting the Process Result (4.6.3, 14.2)
# ---------------------------------------------------------------------------


def process_result_document_name(context: BootstrapContext, iteration: int) -> str:
    """The navigation name of one Process Result Document. Never identity."""
    return PROCESS_NAME_TEMPLATE.format(cycle_id=context.cycle_id, iteration=iteration)


def render_process_result_carrier(
    context: BootstrapContext, iteration: int, sealed: dict[str, object]
) -> str:
    """The immutable carrier of 4.1: heading, one paragraph, one JSON fence."""
    heading = PROCESS_HEADING_TEMPLATE.format(
        name=process_result_document_name(context, iteration)
    )
    return (
        f"{heading}\n"
        "\n"
        f"{PROCESS_PROSE}\n"
        "\n"
        f"{JSON_FENCE_OPENER}\n"
        f"{canonical_artifact_json(sealed)}\n"
        f"{FENCE_MARKER}\n"
    )


def build_process_result(
    view: _View, output: ArchitectOutput, response: ModelResponse, created_at: str
) -> dict[str, object]:
    """The sealed `tsa.process_result` of 4.6.3 for the current iteration."""
    runtime: dict[str, object] = {"role": ARCHITECT_ROLE}
    if response.model is not None:
        runtime["model"] = response.model
    context = view.context
    assert view.architecture.fingerprint is not None  # an input form was validated
    return sealed_artifact(
        {
            "artifact_type": PROCESS_RESULT,
            "schema_version": SCHEMA_VERSION,
            "workspace_identity": context.workspace_identity,
            "project_entity_id": context.project_entity_id,
            "project_code": context.project_code,
            "cycle_id": context.cycle_id,
            "iteration": view.iteration,
            "body": {
                "manifest_digest": view.manifest.body["manifest_digest"],
                "architecture_document_id": context.architecture_document_id,
                "input_fingerprint": view.architecture.fingerprint,
                "intended_output": output.intended_output,
                "architect_response": output.architect_response,
                "runtime": runtime,
                "created_at": created_at,
            },
        }
    )


def _confirmed_process(child: _Child, emitted: str) -> dict[str, object]:
    """The slot holds exactly the artifact this stage emitted, or it failed."""
    if child.state is _ChildState.EMPTY or child.payload is None:
        raise _write_failed(
            f"Process Result {child.document_id!r} is not durable: it reads back "
            f"{child.state}. The Architecture was not written; nothing was retried."
        )
    if canonical_artifact_json(child.payload) != emitted:
        raise _write_failed(
            f"Process Result {child.document_id!r} holds a different artifact than "
            "the one written. It was not overwritten or applied."
        )
    return child.payload


def _create_process_shell(stage: _Stage, view: _View) -> None:
    """Create the deterministic child; an unknown outcome is rediscovered first.

    Both levels of 3.5: the stage gate (cycle-level) runs before the slot is
    looked at again, and a retry reuses the same id. A child that appeared
    holding an artifact is never written over.
    """
    context = view.context
    document_id = view.process.document_id
    for _ in range(PROCESS_CREATE_ATTEMPTS):
        root = _resolve_root(stage.workspace, context)
        try:
            stage.workspace.create_tsa_child_document(
                document_id,
                process_result_document_name(context, view.iteration),
                root.document_id,
            )
        except FiberyError:
            view = _gate(stage)
            if view.process.state is _ChildState.EMPTY:
                return
            if view.process.state is _ChildState.VALID:
                raise _occupied(view) from None
            continue
        return
    raise _write_failed(
        f"The Process Result create did not become durable in "
        f"{PROCESS_CREATE_ATTEMPTS} attempts at the same id {document_id!r}."
    )


def _occupied(view: _View) -> ArchitectRefused:
    return ArchitectRefused(
        ArchitectResultCode.ARTIFACT_DUPLICATE,
        f"Process Result {view.process.document_id!r} already holds an output "
        f"for iteration {view.iteration}; this output was not persisted or "
        "applied, and the durable one was not overwritten.",
        (view.process.document_id,),
    )


def _persist_process(
    stage: _Stage, view: _View, sealed: dict[str, object]
) -> dict[str, object]:
    """Create if absent, fill the empty shell, then read back the exact artifact.

    After the create the gate runs again: nothing read before a mutation
    authorizes the body write. The last remote calls before the write are the
    child and root placement resolutions (2.2.1).
    """
    emitted = canonical_artifact_json(sealed)
    if view.process.state is _ChildState.ABSENT:
        _create_process_shell(stage, view)
    view = _gate(stage)
    if view.process.state is _ChildState.VALID:
        raise _occupied(view)
    if view.process.state is _ChildState.ABSENT:
        raise _write_failed(
            f"Process Result {view.process.document_id!r} is not observable after "
            "its create; nothing was written."
        )
    shell = _resolve_child(stage.workspace, view.context, view.process.document_id)
    if shell is None or not shell.secret:
        raise _write_failed(
            f"Process Result {view.process.document_id!r} has no writable body."
        )
    carrier = render_process_result_carrier(view.context, view.iteration, sealed)
    try:
        stage.workspace.write_document_content(shell.secret, carrier)
    except FiberyError as error:
        after = _gate(stage)
        if after.iteration != view.iteration:
            raise _occupied(view) from error
        return _confirmed_process(after.process, emitted)
    readback = _read_child(
        stage.workspace, view.context, PROCESS_RESULT, view.iteration
    )
    return _confirmed_process(readback, emitted)


# ---------------------------------------------------------------------------
# One fresh Architect call (case 1, or the Process shell of 13.7-7)
# ---------------------------------------------------------------------------


def _require_case_one_input(view: _View) -> None:
    """The Architecture must be exactly the input this iteration starts from.

    Iteration 1 starts from the bootstrap carrier; a reworked iteration from
    the Architecture its REWORK decision bound.
    """
    architecture = view.architecture
    if view.rework is None:
        is_input = architecture.form is _Form.BOOTSTRAP
        expected = "the bootstrap carrier"
    else:
        expected_fingerprint = view.rework.decision.body["architecture_fingerprint"]
        is_input = (
            architecture.form is _Form.APPLIED
            and architecture.fingerprint == expected_fingerprint
        )
        expected = f"the Architecture REWORK {view.rework.iteration} bound"
    if not is_input:
        raise ArchitectRefused(
            ArchitectResultCode.ARCHITECTURE_DIVERGED,
            f"Iteration {view.iteration} has no Process Result and the "
            f"Architecture is not {expected}. Nothing was written and no model "
            "was called.",
            (f"current {architecture.fingerprint}",),
        )


def _requirement_material(stage: _Stage, row: dict[str, object]) -> RequirementMaterial:
    """One full normative tree, read now and bound to the Manifest's row."""
    requirement_id = str(row["requirement_id"])
    entity_id = str(row["entity_id"])
    with _reading(f"Requirement {requirement_id}"):
        record = stage.evidence.read_requirement(entity_id)
        attached = (
            stage.evidence.documents_attached_to_requirement(record.public_id)
            if record is not None
            else []
        )
    if record is None or len(attached) != 1:
        raise _stale(
            f"{requirement_id} no longer resolves to one Root Document.",
            (requirement_id,),
        )
    try:
        tree = read_normative_tree(stage.evidence, record, attached[0])
    except NormativeTreeError as error:
        code = (
            CycleResultCode.FIBERY_READ_FAILED
            if error.read_failed
            else AdmissionResultCode.INPUTS_STALE
        )
        raise ArchitectRefused(code, error.message, error.details) from error
    bound = TreeManifest.from_payload(row["tree_manifest"])
    if tree.manifest.fingerprint != bound.fingerprint:
        raise _stale(
            f"The normative tree of {requirement_id} changed since the Manifest "
            "was accepted.",
            (requirement_id,),
        )
    return RequirementMaterial(
        requirement_id,
        entity_id,
        str(row["tree_fingerprint"]),
        render_normative_tree(tree),
    )


def _ux_content(stage: _Stage, ux: dict[str, object]) -> str | None:
    """The bound UX content for APPLICABLE; no Document read for NOT_APPLICABLE."""
    if ux["kind"] != UX_APPLICABLE:
        return None
    document_id = str(ux["document_id"])
    with _reading(f"UX Document {document_id!r}"):
        node = stage.workspace.resolve_document(document_id)
        content = (
            stage.workspace.read_document_content(node.secret)
            if node is not None and node.secret
            else None
        )
    if content is None or document_fingerprint(content) != ux["content_digest"]:
        raise _stale(
            "The UX Document no longer matches its accepted digest.", (document_id,)
        )
    return content


def _prompt_material(stage: _Stage, view: _View) -> ArchitectPromptInput:
    """Exactly the sources of 16.1, each bound to the accepted Manifest."""
    context = view.context
    with _reading(f"Project {context.project_entity_id!r}"):
        project = stage.workspace.read_project(stage.project_id)
    if project is None or project.id != context.project_entity_id:
        raise ArchitectRefused(
            CycleResultCode.FIBERY_READ_FAILED,
            f"Project {stage.project_id!r} no longer resolves to the cycle's Project.",
        )
    body = view.manifest_body
    rework = None
    if view.rework is not None:
        rework = ReworkMaterial(
            previous_iteration=view.rework.iteration,
            architecture_document=view.architecture.content,
            review_findings=view.rework.review.body["reviewer_response"],
        )
    return ArchitectPromptInput(
        project_code=str(context.project_code),
        project_name=project.name,
        manifest_body=body,
        requirements=tuple(
            _requirement_material(stage, row) for row in body["requirements"]
        ),
        ux_content=_ux_content(stage, body["ux"]),
        rework=rework,
    )


def _invoke(model: ModelRuntime, prompt: ArchitectPrompt) -> ModelResponse:
    """Exactly one call. A runtime failure is reported, never retried elsewhere."""
    try:
        return model.run(prompt.prompt, prompt.context)
    except ModelRuntimeError as error:
        raise ArchitectRefused(
            ArchitectResultCode.MODEL_RUNTIME_FAILED,
            "The configured local model runtime could not run the Architect. "
            "Nothing was persisted or applied.",
            (str(error),),
        ) from error


def _generate(
    stage: _Stage, view: _View, model: ModelRuntime, clock: Clock
) -> ArchitectStageResult:
    """Case 1 or a Process shell: one fresh call, persist, then apply."""
    _require_case_one_input(view)
    prompt = build_architect_prompt(_prompt_material(stage, view))
    require_within_input_bound(prompt)
    response = _invoke(model, prompt)
    output = validate_architect_output(response.text, view.manifest_body)
    after = _gate(stage)
    if after.iteration != view.iteration or after.process.state is _ChildState.VALID:
        raise _occupied(view)
    if after.architecture.fingerprint != view.architecture.fingerprint:
        raise ArchitectRefused(
            ArchitectResultCode.ARCHITECTURE_DIVERGED,
            "The Architecture changed while the Architect was running; its output "
            "was not persisted or applied.",
            (
                f"input {view.architecture.fingerprint}",
                f"current {after.architecture.fingerprint}",
            ),
        )
    sealed = build_process_result(after, output, response, created_at_now(clock))
    persisted = _persist_process(stage, after, sealed)
    written, expected = _apply(stage, persisted)
    return _result(
        ArchitectStageOutcome.OUTPUT_APPLIED,
        after,
        persisted,
        expected,
        model_invoked=True,
        process_written=True,
        architecture_written=written,
    )


def _result(
    outcome: ArchitectStageOutcome,
    view: _View,
    persisted: dict[str, object],
    expected: ArchitectureCarrier,
    *,
    model_invoked: bool,
    process_written: bool,
    architecture_written: bool,
) -> ArchitectStageResult:
    return ArchitectStageResult(
        outcome=outcome,
        iteration=view.iteration,
        architecture_document_id=view.context.architecture_document_id,
        process_result_document_id=view.process.document_id,
        process_result_digest=str(persisted["artifact_digest"]),
        input_fingerprint=str(persisted["body"]["input_fingerprint"]),
        output_fingerprint=expected.content_fingerprint,
        model_invoked=model_invoked,
        process_written=process_written,
        architecture_written=architecture_written,
    )


def run_architect_stage(
    workspace: CycleWorkspace,
    evidence: RequirementEvidenceWorkspace,
    model: ModelRuntime,
    project_id: str,
    raw_cycle_id: object,
    *,
    clock: Clock = _utc_now,
) -> ArchitectStageResult:
    """Carry the cycle's current iteration to a durable, applied Architect output.

    An internal stage, not a command: I12 wraps it in `hold_workspace` and maps
    its refusals to exit classes. From the stage-local gate:

    - no Process Result, or an empty Process shell: one fresh Architect call,
      validated, persisted and confirmed, then applied (case 1, 13.7-7);
    - a Process Result and the Architecture equal to its recorded output:
      nothing is written and no model is called (case 3, which also wins when
      input and output coincide);
    - a Process Result and the Architecture equal to its recorded input: the
      persisted `intended_output` is applied with no model call (case 2);
    - anything else: `ARCHITECTURE_DIVERGED`, nothing written (case 4).

    Raises `ArchitectRefused` with a frozen result code. The clock is read once,
    for the `created_at` of a freshly generated Process Result; replay reads
    none.
    """
    stage = _Stage(workspace, evidence, project_id, raw_cycle_id)
    view = _gate(stage)
    if view.process.state is not _ChildState.VALID:
        try:
            return _generate(stage, view, model, clock)
        except ArchitectInputTooLarge as error:
            raise ArchitectRefused(
                AdmissionResultCode.INPUT_TOO_LARGE, str(error)
            ) from error
    assert view.process.payload is not None and view.process.artifact is not None
    written, expected = _apply(stage, view.process.payload)
    outcome = (
        ArchitectStageOutcome.RECORDED_OUTPUT_APPLIED
        if written
        else ArchitectStageOutcome.ALREADY_APPLIED
    )
    return _result(
        outcome,
        view,
        view.process.payload,
        expected,
        model_invoked=False,
        process_written=False,
        architecture_written=written,
    )
