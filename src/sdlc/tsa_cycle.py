"""TSA-C01 I04 — cycle identity, discovery and the Architecture bootstrap.

Owns exactly what implementation spec v0.2 section 18.1 assigns to I04:
deterministic Document ids (3.5), the trusted expected context (4.1.1), the
ordered Architecture discovery (3.4), the durable classification A / B / D / E
and the `EMPTY_ARCHITECTURE_SHELL` recovery condition (3.4.1), the bootstrap
carrier with its read-back rule (4.1.1), and the rediscovery that follows an
unknown bootstrap mutation outcome (3.5).

It builds no Input Manifest, admits no Requirement or UX evidence, renders no
sixteen-heading Architecture and calls no model: those are I05, I06 and later.
An existing Input Manifest child is only classified structurally — and always
before a bootstrap mutation is permitted (contract 14.1.2): a Document at the
deterministic Input Manifest id overrides an otherwise A, B or
`EMPTY_ARCHITECTURE_SHELL` observation.

Nothing here caches a placement or a Project read across a mutation: every
step that relies on one reads it again (2.2.1).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from sdlc.fibery_workspace import (
    ArchitectureWorkspace,
    DocumentPlacement,
    FiberyError,
    is_valid_child_placement,
    is_valid_root_placement,
)
from sdlc.tsa_artifacts import (
    ARCHITECTURE,
    ARCHITECTURE_BOOTSTRAP_KEYS,
    FENCE_MARKER,
    INPUT_MANIFEST,
    ITERATION_MAX,
    ITERATION_MIN,
    JSON_FENCE_OPENER,
    SCHEMA_VERSION,
    InvalidTsaArtifact,
    canonical_cycle_id,
    canonical_json,
    extract_architecture_envelope,
    extract_artifact_payload,
    sealed_artifact,
    validate_artifact,
)

#: 3.5: `uuid5(uuid.NAMESPACE_URL, "https://github.com/ros-datonum/sdlc/tsa/v1")`.
TSA_DOCUMENT_NAMESPACE = uuid.UUID("9164554b-34b0-5f02-8f0c-6050170c7eee")
ID_TUPLE_DELIMITER = "|"
ITERATION_DIGITS = 4

#: Line 3 of the pre-apply carrier, verbatim (4.1.1).
BOOTSTRAP_SENTENCE = "Bootstrap shell. No Architect output has been applied."
ARCHITECTURE_NAME_TEMPLATE = "{project_code} — TSA {cycle_id} — Architecture"
CARRIER_HEADING_TEMPLATE = "# {name}"
CREATED_AT_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
MANIFEST_ACCEPTANCE_MISMATCH_CODE = "MANIFEST_ACCEPTANCE_MISMATCH"

Clock = Callable[[], datetime]


class DocumentKind(StrEnum):
    """The closed short artifact-type vocabulary of the id tuple (3.5)."""

    ARCHITECTURE = "architecture"
    INPUT_MANIFEST = "input_manifest"
    PROCESS_RESULT = "process_result"
    REVIEW_RESULT = "review_result"
    HUMAN_DECISION = "human_decision"


NON_ITERATED_KINDS = frozenset({DocumentKind.ARCHITECTURE, DocumentKind.INPUT_MANIFEST})


class CycleResultCode(StrEnum):
    """The frozen result codes of 13.8 that I04 can report. No new code."""

    INVALID_CYCLE_ID = "INVALID_CYCLE_ID"
    CYCLE_AMBIGUOUS = "CYCLE_AMBIGUOUS"
    CYCLE_FOREIGN_PROJECT = "CYCLE_FOREIGN_PROJECT"
    ARTIFACT_MALFORMED = "ARTIFACT_MALFORMED"
    MANIFEST_ACCEPTANCE_MISMATCH = MANIFEST_ACCEPTANCE_MISMATCH_CODE
    MANIFEST_SHELL_UNRECOVERABLE = "MANIFEST_SHELL_UNRECOVERABLE"
    FIBERY_READ_FAILED = "FIBERY_READ_FAILED"
    FIBERY_WRITE_FAILED = "FIBERY_WRITE_FAILED"


class CycleOutcome(StrEnum):
    """What discovery produces: one durable state, or the shell condition.

    `EMPTY_ARCHITECTURE_SHELL` is a recovery condition that precedes B. It is
    not a state letter and never a result code. Command-local `C` has no member:
    no durable observation can produce it.
    """

    A = "A"
    B = "B"
    D = "D"
    E = "E"
    EMPTY_ARCHITECTURE_SHELL = "EMPTY_ARCHITECTURE_SHELL"


DURABLE_STATES = frozenset(
    {CycleOutcome.A, CycleOutcome.B, CycleOutcome.D, CycleOutcome.E}
)


class CycleWorkspace(ArchitectureWorkspace, Protocol):
    """`ArchitectureWorkspace` plus the Project Database type id.

    Root placement validation needs that id (2.2.1). The live adapter and the
    fake both already expose it; the frozen protocol does not list it, so it is
    required here rather than added there.
    """

    @property
    def project_type_id(self) -> str:
        """The Project Database's Fibery type id."""


@dataclass(frozen=True)
class BootstrapContext:
    """The trusted expected context of 4.1.1.

    Every value comes from the workspace, a fresh Project read or the caller's
    cycle id. None is ever learned from a Document's content.
    """

    workspace_identity: str
    project_type_id: str
    project_entity_id: str
    project_public_id: str
    project_code: str | None
    cycle_id: str

    @property
    def architecture_document_id(self) -> str:
        return derive_document_id(
            self.workspace_identity,
            self.project_entity_id,
            self.cycle_id,
            DocumentKind.ARCHITECTURE,
        )

    @property
    def input_manifest_document_id(self) -> str:
        return derive_document_id(
            self.workspace_identity,
            self.project_entity_id,
            self.cycle_id,
            DocumentKind.INPUT_MANIFEST,
        )

    @property
    def has_usable_project_code(self) -> bool:
        return isinstance(self.project_code, str) and self.project_code.strip() != ""


@dataclass(frozen=True)
class CycleDiscovery:
    """One durable classification. `refusal_code` is set exactly in state E."""

    context: BootstrapContext
    outcome: CycleOutcome
    refusal_code: CycleResultCode | None = None
    detail: str = ""


class CycleRefused(Exception):
    """A controlled refusal that is not itself a durable classification.

    `rediscovered` carries the classification found after an unknown mutation
    outcome, so a caller can see what a later command will start from.
    """

    def __init__(
        self,
        code: CycleResultCode,
        message: str,
        rediscovered: CycleDiscovery | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.rediscovered = rediscovered


@dataclass(frozen=True)
class _AdoptedArchitecture:
    """The derived Architecture passed step 11; pre-apply means bootstrap carrier."""

    is_pre_apply: bool


# ---------------------------------------------------------------------------
# Deterministic Document identity (3.5)
# ---------------------------------------------------------------------------


def derive_document_id(
    workspace_identity: str,
    project_entity_id: str,
    cycle_id: str,
    kind: DocumentKind,
    iteration: int | None = None,
) -> str:
    """The UUIDv5 Fibery id of one TSA Document.

    A pure function of durable inputs. Neither the Project public id, the
    Project Code nor a Document name takes part.
    """
    kind = DocumentKind(kind)
    parts = [
        workspace_identity,
        project_entity_id,
        canonical_cycle_id(cycle_id),
        kind.value,
    ]
    if kind in NON_ITERATED_KINDS:
        if iteration is not None:
            raise ValueError(f"A {kind} Document id carries no iteration.")
    else:
        parts.append(_rendered_iteration(iteration))
    return str(uuid.uuid5(TSA_DOCUMENT_NAMESPACE, ID_TUPLE_DELIMITER.join(parts)))


def _rendered_iteration(iteration: int | None) -> str:
    is_integer = isinstance(iteration, int) and not isinstance(iteration, bool)
    if not is_integer or not ITERATION_MIN <= iteration <= ITERATION_MAX:
        raise ValueError(
            f"An iteration must be an integer in {ITERATION_MIN}..{ITERATION_MAX}, "
            f"not {iteration!r}."
        )
    return f"{iteration:0{ITERATION_DIGITS}d}"


# ---------------------------------------------------------------------------
# Trusted expected context (4.1.1)
# ---------------------------------------------------------------------------


@contextmanager
def _reading(subject: str) -> Iterator[None]:
    """Turn an adapter read failure into the frozen `FIBERY_READ_FAILED`."""
    try:
        yield
    except FiberyError as error:
        raise CycleRefused(
            CycleResultCode.FIBERY_READ_FAILED, f"Reading {subject} failed: {error}"
        ) from error


def resolve_bootstrap_context(
    workspace: CycleWorkspace, project_id: str, raw_cycle_id: object
) -> BootstrapContext:
    """Fix the trusted expected context from one fresh Project read."""
    try:
        cycle_id = canonical_cycle_id(raw_cycle_id)
    except InvalidTsaArtifact as error:
        raise CycleRefused(CycleResultCode.INVALID_CYCLE_ID, str(error)) from error
    with _reading("the workspace identity and the target Project"):
        workspace_identity = workspace.lock_scope
        project_type_id = workspace.project_type_id
        project = workspace.read_project(project_id)
    if project is None:
        raise CycleRefused(
            CycleResultCode.FIBERY_READ_FAILED,
            f"Project {project_id!r} could not be read, so no trusted context exists.",
        )
    if not (
        workspace_identity and project_type_id and project.id and project.public_id
    ):
        raise CycleRefused(
            CycleResultCode.FIBERY_READ_FAILED,
            f"Project {project_id!r} did not resolve to a usable workspace "
            "identity, Project Database type id, entity id and public id.",
        )
    return BootstrapContext(
        workspace_identity=workspace_identity,
        project_type_id=project_type_id,
        project_entity_id=project.id,
        project_public_id=project.public_id,
        project_code=project.code,
        cycle_id=cycle_id,
    )


def _require_project_code(context: BootstrapContext) -> BootstrapContext:
    """Refuse before any bootstrap mutation that needs the name or the carrier."""
    if not context.has_usable_project_code:
        raise CycleRefused(
            CycleResultCode.FIBERY_READ_FAILED,
            f"Project {context.project_entity_id!r} carries no usable Project "
            "Code, so no conforming Architecture carrier can be constructed. "
            "Nothing was created or written.",
        )
    return context


# ---------------------------------------------------------------------------
# Bootstrap carrier (4.1.1)
# ---------------------------------------------------------------------------


def architecture_document_name(context: BootstrapContext) -> str:
    """The navigation name of the Architecture Document. Never identity."""
    if not context.has_usable_project_code:
        raise ValueError("The Architecture name needs a usable Project Code.")
    return ARCHITECTURE_NAME_TEMPLATE.format(
        project_code=context.project_code, cycle_id=context.cycle_id
    )


def build_bootstrap_artifact(
    context: BootstrapContext, created_at: str
) -> dict[str, object]:
    """The sealed pre-apply `tsa.architecture` artifact, from trusted context."""
    if not context.has_usable_project_code:
        raise ValueError("The bootstrap artifact needs a usable Project Code.")
    return sealed_artifact(
        {
            "artifact_type": ARCHITECTURE,
            "schema_version": SCHEMA_VERSION,
            "workspace_identity": context.workspace_identity,
            "project_entity_id": context.project_entity_id,
            "project_code": context.project_code,
            "cycle_id": context.cycle_id,
            "body": {"cycle_id": context.cycle_id, "created_at": created_at},
        }
    )


def render_bootstrap_carrier(
    context: BootstrapContext, sealed: dict[str, object]
) -> str:
    """The emission form `W`: heading, sentence, one JSON fence, one final LF."""
    heading = CARRIER_HEADING_TEMPLATE.format(name=architecture_document_name(context))
    return (
        f"{heading}\n"
        "\n"
        f"{BOOTSTRAP_SENTENCE}\n"
        "\n"
        f"{JSON_FENCE_OPENER}\n"
        f"{canonical_json(sealed)}\n"
        f"{FENCE_MARKER}\n"
    )


def bootstrap_readback_matches(emitted: str, readback: str) -> bool:
    """The only transport normalization of a bootstrap read-back (4.1.1).

    Exactly as emitted, or as emitted less its one final LF — the one difference
    the live probe observed. Nothing else, and not general Markdown equivalence.
    """
    if readback == emitted:
        return True
    return emitted.endswith("\n") and readback == emitted[:-1]


def created_at_now(clock: Clock) -> str:
    """One RFC-3339 UTC timestamp, second precision, `Z` suffix."""
    moment = clock()
    if moment.tzinfo is None:
        raise ValueError("The clock must return a timezone-aware datetime.")
    return moment.astimezone(UTC).strftime(CREATED_AT_FORMAT)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _require_binding(field: str, actual: object, expected: object) -> None:
    if actual != expected:
        raise InvalidTsaArtifact(
            f"The persisted {field} {actual!r} does not equal the trusted "
            f"expected value {expected!r}."
        )


def _validate_derived_architecture(context: BootstrapContext, content: str) -> bool:
    """Validate non-empty content at the derived Architecture id (3.4 step 7).

    Returns whether it is the pre-apply bootstrap carrier. Raises
    `InvalidTsaArtifact` for every failure. For a pre-apply body, `W` is rebuilt
    from the trusted context and only the persisted `created_at` (4.1.1); the
    post-apply prose is I06's to validate, not this module's.
    """
    payload = extract_architecture_envelope(content)
    artifact = validate_artifact(payload)
    _require_binding("artifact_type", artifact.artifact_type, ARCHITECTURE)
    _require_binding("cycle_id", artifact.cycle_id, context.cycle_id)
    _require_binding(
        "project_entity_id", artifact.project_entity_id, context.project_entity_id
    )
    if set(artifact.body) != set(ARCHITECTURE_BOOTSTRAP_KEYS):
        return False
    _require_binding(
        "workspace_identity", artifact.workspace_identity, context.workspace_identity
    )
    _require_binding("project_code", artifact.project_code, context.project_code)
    _require_binding("body.cycle_id", artifact.body["cycle_id"], context.cycle_id)
    expected = build_bootstrap_artifact(context, artifact.body["created_at"])
    if payload != expected:
        raise InvalidTsaArtifact(
            "The persisted bootstrap artifact is not the artifact the trusted "
            "context seals to."
        )
    if not bootstrap_readback_matches(
        render_bootstrap_carrier(context, expected), content
    ):
        raise InvalidTsaArtifact(
            "The Document is not the exact bootstrap carrier, nor that carrier "
            "less its one final newline."
        )
    return True


# ---------------------------------------------------------------------------
# Discovery (3.4) and durable classification (3.4.1)
# ---------------------------------------------------------------------------


def _refusing(
    context: BootstrapContext, code: CycleResultCode, detail: str
) -> CycleDiscovery:
    return CycleDiscovery(context, CycleOutcome.E, code, detail)


def _is_root(placement: DocumentPlacement, context: BootstrapContext) -> bool:
    return is_valid_root_placement(
        placement, context.project_type_id, context.project_public_id
    )


def _read_content(
    workspace: CycleWorkspace, placement: DocumentPlacement, subject: str
) -> str:
    if not placement.secret:
        raise CycleRefused(
            CycleResultCode.FIBERY_READ_FAILED,
            f"{subject} {placement.document_id!r} exposes no content secret.",
        )
    with _reading(f"{subject} {placement.document_id!r}"):
        return workspace.read_document_content(placement.secret)


def _is_same_cycle_architecture(context: BootstrapContext, content: str) -> bool:
    """Whether content is a valid `tsa.architecture` for this Project and cycle."""
    if not content.strip():
        return False
    try:
        artifact = validate_artifact(extract_architecture_envelope(content))
    except InvalidTsaArtifact:
        return False
    return (
        artifact.artifact_type == ARCHITECTURE
        and artifact.project_entity_id == context.project_entity_id
        and artifact.cycle_id == context.cycle_id
    )


def _non_derived_candidates(
    workspace: CycleWorkspace, context: BootstrapContext
) -> list[str]:
    """Ids of valid same-cycle Architectures at a non-derived id (3.4 step 8).

    Names take no part. The adapter offers no batched content read, so this is
    one content read per root Document the Project contains.
    """
    with _reading("the Documents contained by the Project"):
        placements = workspace.documents_attached_to_project(context.project_public_id)
    candidates = []
    for placement in placements:
        if placement.document_id == context.architecture_document_id:
            continue
        if not _is_root(placement, context) or not placement.secret:
            continue
        content = _read_content(workspace, placement, "Project Document")
        if _is_same_cycle_architecture(context, content):
            candidates.append(placement.document_id)
    return candidates


def _discover_architecture(
    workspace: CycleWorkspace, context: BootstrapContext
) -> CycleDiscovery | _AdoptedArchitecture:
    """Steps 3–11 of 3.4, in the frozen order and precedence."""
    derived_id = context.architecture_document_id
    with _reading(f"the placement of Architecture Document {derived_id!r}"):
        placement = workspace.resolve_placement(derived_id)
    adopted: _AdoptedArchitecture | None = None
    if placement is not None:
        if not _is_root(placement, context):
            return _refusing(
                context,
                CycleResultCode.CYCLE_FOREIGN_PROJECT,
                f"Document {derived_id!r} is not a root of the target Project.",
            )
        content = _read_content(workspace, placement, "Architecture Document")
        if content.strip():
            try:
                adopted = _AdoptedArchitecture(
                    _validate_derived_architecture(context, content)
                )
            except InvalidTsaArtifact as error:
                return _refusing(
                    context,
                    CycleResultCode.ARTIFACT_MALFORMED,
                    f"Architecture Document {derived_id!r}: {error}",
                )
    conflicts = _non_derived_candidates(workspace, context)
    if conflicts:
        return _refusing(
            context,
            CycleResultCode.CYCLE_AMBIGUOUS,
            f"Valid same-cycle Architecture at non-derived id(s) {conflicts}.",
        )
    if placement is None:
        return CycleDiscovery(context, CycleOutcome.A)
    if adopted is None:
        return CycleDiscovery(context, CycleOutcome.EMPTY_ARCHITECTURE_SHELL)
    return adopted


def _manifest_refusal_code(error: InvalidTsaArtifact) -> CycleResultCode:
    if error.code == MANIFEST_ACCEPTANCE_MISMATCH_CODE:
        return CycleResultCode.MANIFEST_ACCEPTANCE_MISMATCH
    return CycleResultCode.ARTIFACT_MALFORMED


def _validate_input_manifest(context: BootstrapContext, content: str) -> None:
    artifact = validate_artifact(extract_artifact_payload(content))
    _require_binding("artifact_type", artifact.artifact_type, INPUT_MANIFEST)
    _require_binding("cycle_id", artifact.cycle_id, context.cycle_id)
    _require_binding(
        "project_entity_id", artifact.project_entity_id, context.project_entity_id
    )


def _is_child_of_architecture(
    workspace: CycleWorkspace, context: BootstrapContext, child: DocumentPlacement
) -> bool:
    """The child predicate of 2.2.1, against a freshly resolved root."""
    with _reading("the placement of the Architecture root"):
        root = workspace.resolve_placement(context.architecture_document_id)
    return root is not None and is_valid_child_placement(
        child,
        root,
        context.architecture_document_id,
        context.project_type_id,
        context.project_public_id,
    )


def _without_manifest(
    context: BootstrapContext, adopted: _AdoptedArchitecture
) -> CycleDiscovery:
    """What an adopted Architecture classifies as when no Manifest exists."""
    if adopted.is_pre_apply:
        return CycleDiscovery(context, CycleOutcome.B)
    return _refusing(
        context,
        CycleResultCode.ARTIFACT_MALFORMED,
        "The Architecture Document carries applied output, but no Input "
        "Manifest Document exists for the cycle.",
    )


def _classify_input_manifest(
    workspace: CycleWorkspace,
    context: BootstrapContext,
    without_manifest: CycleDiscovery,
) -> CycleDiscovery:
    """Structural D / E from the deterministic Input Manifest child (3.4.1).

    `without_manifest` is the Architecture observation — A, B or
    `EMPTY_ARCHITECTURE_SHELL` — and stands only when no Document exists at the
    Manifest id. An existing one overrides it, so no bootstrap mutation is ever
    permitted over durable Manifest evidence (contract 14.1.2).

    No admission, no currentness, no write: an existing Manifest is only read.
    """
    manifest_id = context.input_manifest_document_id
    with _reading(f"the placement of Input Manifest Document {manifest_id!r}"):
        child = workspace.resolve_placement(manifest_id)
    if child is None:
        return without_manifest
    if not _is_child_of_architecture(workspace, context, child):
        return _refusing(
            context,
            CycleResultCode.CYCLE_FOREIGN_PROJECT,
            f"Document {manifest_id!r} is not a child of the Architecture root.",
        )
    content = _read_content(workspace, child, "Input Manifest Document")
    if not content.strip():
        return _refusing(
            context,
            CycleResultCode.MANIFEST_SHELL_UNRECOVERABLE,
            f"Input Manifest Document {manifest_id!r} is an empty shell.",
        )
    try:
        _validate_input_manifest(context, content)
    except InvalidTsaArtifact as error:
        return _refusing(
            context,
            _manifest_refusal_code(error),
            f"Input Manifest Document {manifest_id!r}: {error}",
        )
    return CycleDiscovery(context, CycleOutcome.D)


def discover_cycle(
    workspace: CycleWorkspace, project_id: str, raw_cycle_id: object
) -> CycleDiscovery:
    """Classify one cycle from durable Fibery state. Read-only.

    This is also the bootstrap gate: it validates everything that already
    exists, and a caller mutates only on A or `EMPTY_ARCHITECTURE_SHELL`. The
    Architecture is decided first; the Input Manifest child is then inspected
    before any of A, B or `EMPTY_ARCHITECTURE_SHELL` is returned.
    """
    context = resolve_bootstrap_context(workspace, project_id, raw_cycle_id)
    found = _discover_architecture(workspace, context)
    if isinstance(found, _AdoptedArchitecture):
        found = _without_manifest(context, found)
    elif found.outcome is CycleOutcome.E:
        return found
    return _classify_input_manifest(workspace, context, found)


def rediscover_after_unknown_outcome(
    workspace: CycleWorkspace,
    project_id: str,
    raw_cycle_id: object,
    target: DocumentKind,
) -> CycleDiscovery:
    """Both rediscovery levels after an unknown bootstrap mutation outcome (3.5).

    For the Architecture the full discovery is both levels. For the Input
    Manifest the same discovery runs the cycle-level revalidation first and
    reaches the deterministic child only once the Architecture is adopted. It
    never retries: whether a Manifest create may be repeated is I05's decision.
    """
    if target not in NON_ITERATED_KINDS:
        raise ValueError(f"{target!r} is not a bootstrap mutation target.")
    return discover_cycle(workspace, project_id, raw_cycle_id)


# ---------------------------------------------------------------------------
# Bootstrap mutation: create, then the one carrier write contract (4.1.1)
# ---------------------------------------------------------------------------


def ensure_bootstrap_architecture(
    workspace: CycleWorkspace,
    project_id: str,
    raw_cycle_id: object,
    *,
    create_if_absent: bool,
    clock: Clock = _utc_now,
) -> CycleDiscovery:
    """Run the bootstrap gate, then the minimum write that reaches B.

    Returns the durable classification: A only when `create_if_absent` is
    false, otherwise B, D or E. E is returned untouched — a failed gate writes
    nothing. Raises `CycleRefused` when a bootstrap mutation was required but
    could not be attempted or validated.
    """
    found = discover_cycle(workspace, project_id, raw_cycle_id)
    cycle_id = found.context.cycle_id
    if found.outcome is CycleOutcome.A and create_if_absent:
        return _create_architecture_shell(workspace, project_id, cycle_id, clock)
    if found.outcome is CycleOutcome.EMPTY_ARCHITECTURE_SHELL:
        return _complete_empty_shell(workspace, project_id, cycle_id, clock)
    return found


def _require_bootstrapped(found: CycleDiscovery, reason: str) -> CycleDiscovery:
    """After a rediscovery: B, D and E stand; A or a shell is a failed write."""
    if found.outcome in (CycleOutcome.A, CycleOutcome.EMPTY_ARCHITECTURE_SHELL):
        raise CycleRefused(
            CycleResultCode.FIBERY_WRITE_FAILED,
            f"{reason} Rediscovery found {found.outcome}; nothing was retried.",
            rediscovered=found,
        )
    return found


def _create_architecture_shell(
    workspace: CycleWorkspace, project_id: str, cycle_id: str, clock: Clock
) -> CycleDiscovery:
    """State A: create at the derived id. Creation alone never establishes B.

    The create is a revalidation boundary of its own: whatever it returns, the
    gate runs again in full before the carrier write may be authorized.
    """
    context = _require_project_code(
        resolve_bootstrap_context(workspace, project_id, cycle_id)
    )
    derived_id = context.architecture_document_id
    with _reading(f"the placement of Architecture Document {derived_id!r}"):
        is_still_absent = workspace.resolve_placement(derived_id) is None
    if not is_still_absent:
        reason = "The derived Architecture id appeared before the create."
    else:
        reason = "The created Architecture Document is not durably observable."
        try:
            workspace.create_project_document(
                derived_id,
                architecture_document_name(context),
                context.project_public_id,
            )
        except FiberyError as error:
            reason = f"The Architecture create outcome is unknown ({error})."
    return _revalidate_after_create(workspace, project_id, cycle_id, clock, reason)


def _revalidate_after_create(
    workspace: CycleWorkspace,
    project_id: str,
    cycle_id: str,
    clock: Clock,
    reason: str,
) -> CycleDiscovery:
    """The full gate again after a create, known or unknown; never a second create.

    Nothing read before the create authorizes the carrier write: the Project,
    the root placement, the conflict listing and the Input Manifest child are
    all rediscovered, and only a fresh `EMPTY_ARCHITECTURE_SHELL` proceeds.
    """
    found = discover_cycle(workspace, project_id, cycle_id)
    if found.outcome is CycleOutcome.EMPTY_ARCHITECTURE_SHELL:
        return _complete_empty_shell(workspace, project_id, cycle_id, clock)
    return _require_bootstrapped(found, reason)


def _complete_empty_shell(
    workspace: CycleWorkspace, project_id: str, cycle_id: str, clock: Clock
) -> CycleDiscovery:
    """The one bootstrap carrier write, for a shell of either origin."""
    context = _require_project_code(
        resolve_bootstrap_context(workspace, project_id, cycle_id)
    )
    derived_id = context.architecture_document_id
    with _reading(f"the placement of Architecture Document {derived_id!r}"):
        placement = workspace.resolve_placement(derived_id)
    if placement is None:
        raise CycleRefused(
            CycleResultCode.FIBERY_WRITE_FAILED,
            f"Architecture Document {derived_id!r} does not resolve, so its "
            "bootstrap carrier was not written.",
        )
    if not _is_root(placement, context):
        raise CycleRefused(
            CycleResultCode.CYCLE_FOREIGN_PROJECT,
            f"Document {derived_id!r} is no longer a root of the target "
            "Project; nothing was written.",
        )
    if _read_content(workspace, placement, "Architecture Document").strip():
        return _require_bootstrapped(
            discover_cycle(workspace, project_id, cycle_id),
            "The Architecture Document is no longer empty; it was not overwritten.",
        )
    emitted = render_bootstrap_carrier(
        context, build_bootstrap_artifact(context, created_at_now(clock))
    )
    try:
        workspace.write_document_content(placement.secret, emitted)
    except FiberyError as error:
        return _require_bootstrapped(
            discover_cycle(workspace, project_id, cycle_id),
            f"The bootstrap carrier write outcome is unknown ({error}).",
        )
    return _validate_carrier_write(workspace, project_id, cycle_id, emitted)


def _validate_carrier_write(
    workspace: CycleWorkspace, project_id: str, cycle_id: str, emitted: str
) -> CycleDiscovery:
    """The immediate read-back matrix R-1 … R-4, on fresh reads only."""
    context = resolve_bootstrap_context(workspace, project_id, cycle_id)
    derived_id = context.architecture_document_id
    try:
        readback = _read_back_carrier(workspace, context)
    except FiberyError as error:
        return _require_bootstrapped(
            discover_cycle(workspace, project_id, cycle_id),
            f"The bootstrap carrier read-back failed ({error}).",
        )
    if not readback.strip():
        raise CycleRefused(
            CycleResultCode.FIBERY_WRITE_FAILED,
            f"The bootstrap carrier of {derived_id!r} read back empty; the "
            "Document remains an empty shell and nothing was retried.",
        )
    try:
        is_pre_apply = _validate_derived_architecture(context, readback)
    except InvalidTsaArtifact as error:
        raise _malformed_readback(derived_id, str(error)) from error
    if not is_pre_apply or not bootstrap_readback_matches(emitted, readback):
        raise _malformed_readback(derived_id, "it is not the carrier just emitted")
    return _classify_input_manifest(
        workspace, context, CycleDiscovery(context, CycleOutcome.B)
    )


def _read_back_carrier(workspace: CycleWorkspace, context: BootstrapContext) -> str:
    """Fresh placement first; content is read only from a root of the Project."""
    derived_id = context.architecture_document_id
    placement = workspace.resolve_placement(derived_id)
    if placement is None:
        raise CycleRefused(
            CycleResultCode.FIBERY_WRITE_FAILED,
            f"Architecture Document {derived_id!r} no longer resolves after the "
            "bootstrap write, so its carrier is not durable; nothing was retried.",
        )
    if not _is_root(placement, context):
        raise CycleRefused(
            CycleResultCode.CYCLE_FOREIGN_PROJECT,
            f"Document {derived_id!r} is not a root of the target Project "
            "after the bootstrap write.",
        )
    return workspace.read_document_content(placement.secret) if placement.secret else ""


def _malformed_readback(derived_id: str, reason: str) -> CycleRefused:
    return CycleRefused(
        CycleResultCode.ARTIFACT_MALFORMED,
        f"The bootstrap carrier of {derived_id!r} read back non-conforming: "
        f"{reason}. Nothing was overwritten or repaired.",
    )
