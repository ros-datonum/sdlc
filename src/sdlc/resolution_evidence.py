"""Deterministic checks on autonomous-resolution evidence.

Implements Requirement-Autonomous-Resolution-v0.1 sections 4, 6 and 8. Code
proves what code can prove — that each citation names the source it claims,
that its quote occurs there, which entity and content fingerprint it binds,
and that a policy clause exists in the approved policy — and nothing more. A
substring match is not semantic support and a fingerprint is change detection,
not a signature: whether a source justifies an answer, and whether a decision
stays within its authority, is the independent Reviewer's judgement.

Three moments:

- **Process** binds each citation the model returned to what the run read
  (`bind_citations`); anything that does not hold is the model's invalid
  output and nothing is persisted.
- **Review** re-establishes every citation and the policy against current
  Fibery and configuration before the reviewer runs
  (`require_current_citations`, `require_current_policy`).
- **Ready, Apply and TSA admission** refuse evidence whose policy or cited
  sources changed since it was bound (`require_current_resolutions`).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Protocol

from sdlc.autonomy_policy import AutonomyPolicies, AutonomyPolicy, PolicyBinding
from sdlc.fibery_workspace import DocumentNode, FiberyError, RequirementRecord
from sdlc.normative_tree import (
    NormativeTreeError,
    document_fingerprint,
    read_normative_tree,
    render_normative_tree,
)
from sdlc.process_result import ProcessResult
from sdlc.review_result import ReviewResult
from sdlc.standard_analysis import (
    AnalysisResult,
    InvalidAnalysisOutput,
    Resolution,
    ResolutionClass,
    SourceCitation,
    SourceKind,
)


class ResolutionFailure(StrEnum):
    """Why resolution evidence does not hold. Consumers map it to their codes."""

    # A citation's identity or quote does not hold against an unchanged source.
    INVALID = "INVALID"
    # A cited source or the bound policy changed, vanished or is not active.
    STALE = "STALE"
    # Fibery could not be read; nothing is known either way.
    READ_FAILED = "READ_FAILED"


class ResolutionEvidenceError(Exception):
    """Resolution evidence cannot be established; nothing may act on it."""

    def __init__(
        self, failure: ResolutionFailure, message: str, details: tuple[str, ...] = ()
    ) -> None:
        super().__init__(message)
        self.failure = failure
        self.message = message
        self.details = details


class CitationWorkspace(Protocol):
    """The reads a citation re-check needs. It has no write method."""

    def read_requirement(self, entity_id: str) -> RequirementRecord | None:
        """Read one Requirement entity by id."""

    def documents_attached_to_requirement(self, public_id: str) -> list[DocumentNode]:
        """Documents attached to this Requirement entity."""

    def child_documents(self, parent_document_id: str) -> list[DocumentNode]:
        """Documents nested directly under this Document."""

    def read_document_content(self, secret: str) -> str:
        """Read a Document's Markdown content."""


@dataclass(frozen=True)
class SourceText:
    """One citable Requirement as the run read it: identity and its text.

    A RAW's text is its Root Document; a dependency's is its whole normative
    tree as rendered for the model (`render_normative_tree`), the text the
    model was shown and the text a citation of it is checked against.
    """

    requirement_id: str
    entity_id: str
    content: str


@dataclass(frozen=True)
class SourceCorpus:
    """Everything a Process run may cite, exactly as it read it.

    `raws` are the originating RAWs (Derived From); `requirement_text` the
    normative input the run consumed (Root and children), never its output;
    `dependencies` the existing and proposed DEPENDS_ON targets, each a
    same-Project Standard with its rendered normative tree. An AFFECTS-only
    peer is absent:
    AFFECTS gives no normative authority. `policy` is the Project's active
    policy, or None.
    """

    raws: Mapping[str, SourceText]
    requirement_text: str
    input_tree_fingerprint: str
    dependencies: Mapping[str, SourceText]
    policy: AutonomyPolicy | None


def render_raw_ancestry(raws: Iterable[SourceText]) -> str:
    """Each originating RAW's document behind its identity marker.

    The one rendering Process and Review both show their model, so a RAW
    citation names the same text either stage saw.
    """
    return "\n\n".join(
        f"<!-- RAW {raw.requirement_id} -->\n{raw.content}" for raw in raws
    )


def quote_occurs(quote: str, text: str) -> bool:
    """Whether `quote` occurs in `text`, whitespace runs treated as one space."""
    return " ".join(quote.split()) in " ".join(text.split())


def bind_citations(analysis: AnalysisResult, corpus: SourceCorpus) -> AnalysisResult:
    """Bind every citation of the model's output, or refuse the output.

    Raises InvalidAnalysisOutput: a citation that does not hold, or a
    delegated default without an approved clause, is the model's error.
    """
    resolutions = tuple(
        _bind_resolution(resolution, index, corpus)
        for index, resolution in enumerate(analysis.resolutions)
    )
    responses = tuple(
        replace(
            response,
            evidence=tuple(
                _bind(source, f"rework response for {response.item}", corpus)
                for source in response.evidence
            ),
        )
        for response in analysis.rework_responses
    )
    return replace(analysis, resolutions=resolutions, rework_responses=responses)


def _bind_resolution(
    resolution: Resolution, index: int, corpus: SourceCorpus
) -> Resolution:
    where = f"resolution {index}"
    if resolution.resolution_class is ResolutionClass.DELEGATED_DEFAULT:
        if corpus.policy is None:
            raise InvalidAnalysisOutput(
                f"{where} is DELEGATED_DEFAULT, but no autonomy policy is approved "
                "for this Project: a decision no source settles stays a product "
                "question."
            )
        if corpus.policy.clause(resolution.policy_clause or "") is None:
            raise InvalidAnalysisOutput(
                f"{where} names policy clause {resolution.policy_clause!r}, which "
                f"policy {corpus.policy.policy_id} does not contain."
            )
    return replace(
        resolution,
        sources=tuple(_bind(source, where, corpus) for source in resolution.sources),
    )


def _bind(source: SourceCitation, where: str, corpus: SourceCorpus) -> SourceCitation:
    if source.kind is SourceKind.REQUIREMENT:
        if not quote_occurs(source.quote, corpus.requirement_text):
            raise InvalidAnalysisOutput(
                f"{where} quotes this Requirement, but the quote is not in the "
                "normative content it was given (its own output cannot be cited)."
            )
        return replace(source, fingerprint=corpus.input_tree_fingerprint)
    pool = corpus.raws if source.kind is SourceKind.RAW else corpus.dependencies
    text = pool.get(source.requirement_id or "")
    if text is None:
        raise InvalidAnalysisOutput(
            f"{where} cites {source.kind.value} {source.requirement_id}, which is "
            + (
                "not an originating RAW of this Requirement."
                if source.kind is SourceKind.RAW
                else "not an existing or proposed DEPENDS_ON target (AFFECTS and "
                "unrelated peers give no normative authority)."
            )
        )
    if not quote_occurs(source.quote, text.content):
        raise InvalidAnalysisOutput(
            f"{where} quotes {source.requirement_id}, but the quote is not in the "
            "text it was given."
        )
    return replace(
        source,
        entity_id=text.entity_id,
        fingerprint=document_fingerprint(text.content),
    )


# -- currentness ----------------------------------------------------------------


def require_current_policy(
    relies_on_policy: bool,
    binding: PolicyBinding | None,
    clauses: Iterable[str],
    policies: AutonomyPolicies,
) -> AutonomyPolicy | None:
    """The bound policy, still active and unchanged, when anything relies on it.

    Returns None when no resolution relies on a policy: then whatever the
    configuration says now is irrelevant to this evidence.
    """
    if not relies_on_policy:
        return None
    current = policies.current(binding) if binding is not None else None
    if current is None:
        raise ResolutionEvidenceError(
            ResolutionFailure.STALE,
            "A DELEGATED_DEFAULT resolution relies on autonomy policy "
            f"{binding.policy_id if binding else '(none)'}, which is no longer "
            "active with the content it was bound to (changed, removed or "
            "disabled). A historical resolution is never reinterpreted under "
            "other authority.",
            (binding.fingerprint,) if binding else (),
        )
    missing = sorted({clause for clause in clauses if current.clause(clause) is None})
    if missing:
        raise ResolutionEvidenceError(
            ResolutionFailure.INVALID,
            f"Policy {current.policy_id} does not contain the clause(s) a "
            "resolution names.",
            tuple(missing),
        )
    return current


def require_current_citations(
    workspace: CitationWorkspace,
    citations: Iterable[SourceCitation],
    input_tree_fingerprint: str | None,
    *,
    raw_entity_ids: frozenset[str] | None = None,
    dependency_ids: frozenset[str] | None = None,
) -> None:
    """Every bound citation still names the same source, unchanged, with its quote.

    `raw_entity_ids` and `dependency_ids`, when given, are the originating RAW
    entities and the DEPENDS_ON targets the citations must stay within (the
    Review re-establishes provenance and direction; later consumers check
    identity and integrity only). Each source is read once.
    """
    texts: dict[str, str] = {}
    for citation in citations:
        if citation.kind is SourceKind.REQUIREMENT:
            if citation.fingerprint != input_tree_fingerprint:
                raise ResolutionEvidenceError(
                    ResolutionFailure.INVALID,
                    "A citation of this Requirement does not carry the input "
                    "tree its Process Result consumed.",
                )
            continue
        _require_within(citation, raw_entity_ids, dependency_ids)
        entity_id = citation.entity_id or ""
        if entity_id not in texts:
            texts[entity_id] = _read_source_text(workspace, citation)
        content = texts[entity_id]
        if document_fingerprint(content) != citation.fingerprint:
            raise ResolutionEvidenceError(
                ResolutionFailure.STALE,
                f"Cited {citation.kind.value} {citation.requirement_id} changed "
                "after the resolution evidence bound it.",
                (citation.requirement_id or "",),
            )
        if not quote_occurs(citation.quote, content):
            raise ResolutionEvidenceError(
                ResolutionFailure.INVALID,
                f"A citation of {citation.requirement_id} quotes text its unchanged "
                "source does not contain.",
                (citation.requirement_id or "",),
            )


def _require_within(
    citation: SourceCitation,
    raw_entity_ids: frozenset[str] | None,
    dependency_ids: frozenset[str] | None,
) -> None:
    if (
        citation.kind is SourceKind.RAW
        and raw_entity_ids is not None
        and citation.entity_id not in raw_entity_ids
    ):
        raise ResolutionEvidenceError(
            ResolutionFailure.INVALID,
            f"Cited RAW {citation.requirement_id} is not an originating RAW of "
            "this Requirement.",
            (citation.requirement_id or "",),
        )
    if (
        citation.kind is SourceKind.DEPENDENCY
        and dependency_ids is not None
        and citation.requirement_id not in dependency_ids
    ):
        raise ResolutionEvidenceError(
            ResolutionFailure.INVALID,
            f"Cited dependency {citation.requirement_id} is not an existing or "
            "proposed DEPENDS_ON target of this Requirement.",
            (citation.requirement_id or "",),
        )


def _read_source_text(workspace: CitationWorkspace, citation: SourceCitation) -> str:
    """The cited entity's text, read fresh exactly as it was bound.

    A RAW's Root content; a dependency's rendered normative tree.
    """
    label = f"{citation.kind.value} {citation.requirement_id}"
    try:
        record = workspace.read_requirement(citation.entity_id or "")
        if record is None:
            raise ResolutionEvidenceError(
                ResolutionFailure.STALE,
                f"Cited {label} no longer exists.",
                (citation.requirement_id or "",),
            )
        if record.requirement_id != citation.requirement_id:
            raise ResolutionEvidenceError(
                ResolutionFailure.INVALID,
                f"Cited entity {citation.entity_id} is {record.requirement_id!r}, "
                f"not {citation.requirement_id!r}.",
                (citation.requirement_id or "",),
            )
        attached = workspace.documents_attached_to_requirement(record.public_id)
        if len(attached) != 1:
            raise ResolutionEvidenceError(
                ResolutionFailure.STALE,
                f"Cited {label} has {len(attached)} attached Documents, not one Root.",
                (citation.requirement_id or "",),
            )
        if citation.kind is SourceKind.DEPENDENCY:
            return render_normative_tree(
                read_normative_tree(workspace, record, attached[0])
            )
        return workspace.read_document_content(attached[0].secret or "")
    except NormativeTreeError as error:
        raise ResolutionEvidenceError(
            ResolutionFailure.READ_FAILED
            if error.read_failed
            else ResolutionFailure.STALE,
            f"The normative tree of cited {label} could not be read: {error.message}",
            error.details,
        ) from error
    except FiberyError as error:
        raise ResolutionEvidenceError(
            ResolutionFailure.READ_FAILED,
            f"Cited {label} could not be read from Fibery.",
            (str(error),),
        ) from error


def require_current_resolutions(
    workspace: CitationWorkspace,
    process: ProcessResult,
    review: ReviewResult,
    policies: AutonomyPolicies,
) -> None:
    """Ready, Apply and TSA admission: the reviewed evidence is still current.

    Only resolution-bound (0.7) evidence carries resolutions; older evidence
    recorded none and is governed by the earlier rules alone. The caller has
    already checked, through `what_clearance`, that the review verified
    exactly `process`'s resolutions and policy binding.
    """
    if not review.is_resolution_bound:
        return
    require_current_policy(
        review.relies_on_policy,
        review.reviewed_autonomy_policy,
        (
            resolution.policy_clause
            for resolution in review.reviewed_resolutions
            if resolution.policy_clause is not None
        ),
        policies,
    )
    require_current_citations(
        workspace,
        review.citations,
        process.input_tree.fingerprint if process.input_tree else None,
    )
