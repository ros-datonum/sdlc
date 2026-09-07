"""Comparison context: the Project's other Standard Requirements, with content.

A model asked to spot a duplicate, a conflict or a dependency needs the
obligations it is comparing against, not an index of their titles. This
module reads, validates and renders that small corpus in one place, so RAW
Process, Standard Process and Standard Review supply the same evidence.

Scope is deliberately explicit: each entry is the peer's entity metadata and
its complete current Root Document. Child Documents are not included, so a
detail that lives only in a normative child is outside what this context can
verify (audit finding A5, tracked separately). Process and Review Result
children are never comparison material.

The corpus is bounded, not truncated. More records than the supported limit,
or a rendered section larger than the input budget, refuses the invocation
instead of quietly comparing against part of the Project.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sdlc.fibery_workspace import FiberyError, RequirementRecord

STANDARD_TYPE = "Standard"
APPLIED_STATE = "Applied"
UNSPECIFIED = "unspecified"

# Admission limits for the small-corpus contract. The record limit is the
# former index cap kept as a limit rather than a cut; the input limit is an
# application budget in characters of the rendered section, not a claim
# about any model's token capacity.
COMPARISON_RECORD_LIMIT = 100
COMPARISON_INPUT_LIMIT_CHARACTERS = 400_000

STANDING_APPROVED = "approved normative comparison (Applied)"
STANDING_CANDIDATE = "candidate, not approved authority"

SECTION_HEADER = "# Other Standard Requirements in this Project"
SECTION_SCOPE = (
    "Each entry is that Requirement's complete current Root Document with its "
    "entity metadata. Child Documents are not included. Use these to detect "
    "duplication, conflict, change, supersession or dependency. They never "
    "authorize replacing this Requirement's intent, and a peer that is not "
    "Applied is a candidate under review, not approved authority."
)


class ComparisonContextError(Exception):
    """The comparison corpus could not be established completely.

    Raised before any model call. `details` name the affected records by
    Requirement ID and the reason; they never carry document content.
    """

    def __init__(self, message: str, details: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class ComparisonWorkspace:
    """The two reads comparison context needs; every workspace protocol has them."""

    def documents_attached_to_requirement(
        self, public_id: str
    ) -> list:  # pragma: no cover
        ...

    def read_document_content(self, secret: str) -> str:  # pragma: no cover
        ...


@dataclass(frozen=True)
class ComparisonEntry:
    """One peer: entity metadata and its complete current Root Document."""

    entity_id: str
    requirement_id: str
    title: str
    type_name: str
    state: str | None
    category: str | None
    root_document_id: str
    root_content: str

    @property
    def standing(self) -> str:
        return STANDING_APPROVED if self.state == APPLIED_STATE else STANDING_CANDIDATE


@dataclass(frozen=True)
class ComparisonContext:
    """The complete admitted corpus for one model invocation."""

    project_id: str
    entries: tuple[ComparisonEntry, ...]

    @property
    def requirement_ids(self) -> frozenset[str]:
        return frozenset(entry.requirement_id for entry in self.entries)

    @property
    def summary(self) -> str:
        """Controlled metadata for diagnostics: counts, never bodies."""
        return (
            f"comparison scope: Root Documents of {len(self.entries)} other Standard "
            f"Requirement(s) in the Project"
        )


def assemble_comparison_context(
    workspace: ComparisonWorkspace,
    project_id: str,
    target_entity_id: str,
    candidates: Sequence[RequirementRecord],
) -> ComparisonContext:
    """Read and validate the comparison corpus for one new model invocation.

    `candidates` is the bounded Standard-only query result, which may hold one
    record more than the limit so that overflow is visible. The target, RAW
    records and foreign-Project records are excluded; anything else that
    cannot be established completely refuses the whole corpus.
    """
    peers = [
        record
        for record in candidates
        if record.id != target_entity_id and record.type_name == STANDARD_TYPE
    ]
    _require_identities(peers, project_id)
    if len(peers) > COMPARISON_RECORD_LIMIT:
        raise ComparisonContextError(
            f"The Project has more than {COMPARISON_RECORD_LIMIT} other Standard "
            f"Requirements (at least {len(peers)} were read); the supported "
            "comparison corpus is exhausted and the model was not invoked.",
        )
    entries = tuple(
        _read_entry(workspace, record)
        for record in sorted(peers, key=lambda record: record.requirement_id or "")
    )
    context = ComparisonContext(project_id=project_id, entries=entries)
    rendered = render_comparison_section(context)
    if len(rendered) > COMPARISON_INPUT_LIMIT_CHARACTERS:
        raise ComparisonContextError(
            f"The comparison corpus renders to {len(rendered)} characters, above "
            f"the {COMPARISON_INPUT_LIMIT_CHARACTERS}-character input budget; "
            "it was not truncated and the model was not invoked.",
        )
    return context


def _require_identities(peers: list[RequirementRecord], project_id: str) -> None:
    problems: list[str] = []
    seen: dict[str, str] = {}
    for record in peers:
        if not record.requirement_id:
            problems.append(f"entity {record.id}: no Requirement ID")
            continue
        if record.project_id != project_id:
            problems.append(f"{record.requirement_id}: belongs to another Project")
        if record.requirement_id in seen:
            problems.append(
                f"{record.requirement_id}: ambiguous, also entity {seen[record.requirement_id]}"
            )
        seen[record.requirement_id] = record.id
    if problems:
        raise ComparisonContextError(
            "The comparison corpus is not unambiguous; the model was not invoked.",
            tuple(problems),
        )


def _read_entry(
    workspace: ComparisonWorkspace, record: RequirementRecord
) -> ComparisonEntry:
    requirement_id = record.requirement_id or ""
    try:
        attached = workspace.documents_attached_to_requirement(record.public_id)
    except FiberyError as error:
        raise ComparisonContextError(
            f"Could not list the Documents of {requirement_id}; the model was not "
            "invoked.",
            (f"{requirement_id}: {type(error).__name__}",),
        ) from error
    if len(attached) != 1:
        raise ComparisonContextError(
            f"{requirement_id} has {len(attached)} attached Documents; exactly one "
            "Root Document is required for comparison, so the model was not invoked.",
        )
    root = attached[0]
    if not root.secret:
        raise ComparisonContextError(
            f"The Root Document of {requirement_id} exposes no content; the model "
            "was not invoked.",
        )
    try:
        content = workspace.read_document_content(root.secret)
    except FiberyError as error:
        raise ComparisonContextError(
            f"Could not read the Root Document of {requirement_id}; the model was "
            "not invoked.",
            (f"{requirement_id}: {type(error).__name__}",),
        ) from error
    if not content.strip():
        raise ComparisonContextError(
            f"The Root Document of {requirement_id} is empty; a title is not "
            "comparison evidence, so the model was not invoked.",
        )
    return ComparisonEntry(
        entity_id=record.id,
        requirement_id=requirement_id,
        title=record.title or "",
        type_name=record.type_name or STANDARD_TYPE,
        state=record.state,
        category=record.category,
        root_document_id=root.id,
        root_content=content,
    )


def render_comparison_section(context: ComparisonContext) -> str:
    """The prompt section: metadata and the complete Root Document per entry."""
    if not context.entries:
        return f"{SECTION_HEADER}\n(none)"
    blocks = [SECTION_HEADER, SECTION_SCOPE]
    for entry in context.entries:
        blocks.append(
            "\n".join(
                [
                    f"## {entry.requirement_id} — {entry.title}",
                    f"Type: {entry.type_name}",
                    f"State: {entry.state or UNSPECIFIED}",
                    f"Category: {entry.category or UNSPECIFIED}",
                    f"Standing: {entry.standing}",
                    "",
                    entry.root_content.rstrip(),
                ]
            )
        )
    return "\n\n".join(blocks)


def render_target_metadata(record: RequirementRecord) -> tuple[str, str]:
    """The target's own Type and Category lines, kept separate and honest."""
    return (
        f"Type: {record.type_name or UNSPECIFIED}",
        f"Category: {record.category or UNSPECIFIED}",
    )
