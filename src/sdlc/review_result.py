"""Review Result iterations for independent Standard Requirement review.

Each completed review writes a numbered, immutable child Document recording
what it concluded and, critically, *what it reviewed*: the Root Document
fingerprint, the Process Result iteration, and that iteration's output
fingerprint.

Those three bindings are the whole staleness mechanism. A review certifies one
exact input, so if any of them has moved by the time the state transition is
attempted, the certification no longer describes reality and must not be
applied.

The persisted verdict is never trusted on read-back: it is recomputed from the
findings the artifact carries, so an artifact whose verdict disagrees with its
own contents is rejected rather than acted on. The same holds for the WHAT
status of version 0.4 (Requirement-Material-WHAT-Gate-v0.1): it is recomputed
from the product questions the review saw and their verifications, and
`what_clearance` checks that those questions are the bound Process Result's.
Version 0.5 (Requirement-Rework-Brief-v0.1) also verifies the bound Process
Result's rework responses; a material WHAT item whose response it does not
confirm keeps the status BLOCKED_ON_WHAT.

Version 0.6 (Requirement-Dependency-Bindings-v0.1) verifies every DEPENDS_ON
edge the Requirement already has and binds every normative dependency, direct
and transitive, to its entity, normative-tree fingerprint and Review Result;
only a verified, bound direct dependency can answer a material question.

`build_rework_brief` turns one completed Review Result and the Process Result
it reviewed into the Rework Brief the next Process iteration receives.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum

from sdlc.normative_tree import (
    LEGACY_NORMATIVE_TREE_VERSION,
    NORMATIVE_TREE_VERSION,
    InvalidTreeManifest,
    TreeManifest,
)
from sdlc.process_result import ProcessResult
from sdlc.rework_brief import (
    BriefCategory,
    BriefItem,
    InvalidReworkBrief,
    ReviewSource,
    ReworkBrief,
    item_ref,
)
from sdlc.standard_analysis import (
    FindingKind,
    ProductQuestion,
    RelationKind,
    ReworkOutcome,
    ReworkResponse,
)
from sdlc.standard_review import (
    DependencyVerification,
    FindingVerification,
    InvalidReviewOutput,
    MaterialWhat,
    NewFinding,
    QuestionVerification,
    RejectionBasis,
    RelationVerification,
    ReviewOutput,
    ReviewSeverity,
    ReviewVerdict,
    ReworkVerification,
    VerificationOutcome,
    WhatStatus,
    contradictory_escalations,
    derive_verdict,
    derive_what_status,
    material_escalations,
    question_blocks,
    rework_leaves_what_open,
    verified_dependencies,
)

# 0.2 binds the normative tree (Requirement-Normative-Tree-Binding-v0.1); 0.1
# is the legacy Root-only binding, still readable as history, never written.
# 0.3 binds manifest v2 (exact canonical-byte fingerprints, audit A8); 0.2
# bound manifest v1 under the older algorithm; 0.1 is Root-only. Older
# versions are history: readable, never written, never reinterpreted.
# 0.4 is 0.3 plus the verified product questions and the derived WHAT status
# of the Material-WHAT Gate v0.1. A 0.3 Review Result stays current tree
# evidence but establishes no WHAT status: it is never read as CLEAR.
# 0.5 is 0.4 plus the verified rework responses of Requirement-Rework-Brief
# v0.1; a 0.4 Review Result still establishes WHAT status for a Process
# Result that received no Rework Brief.
# 0.6 is 0.5 plus the verified existing dependencies and the dependency
# bindings of Requirement-Dependency-Bindings-v0.1. A 0.4 or 0.5 Review Result
# keeps its WHAT and rework evidence but establishes no dependency evidence.
REVIEW_RESULT_VERSION = "0.6"
PRE_DEPENDENCY_REVIEW_RESULT_VERSION = "0.5"
PRE_REWORK_REVIEW_RESULT_VERSION = "0.4"
PRE_WHAT_REVIEW_RESULT_VERSION = "0.3"
TREE_BOUND_LEGACY_REVIEW_RESULT_VERSION = "0.2"
LEGACY_REVIEW_RESULT_VERSION = "0.1"
SUPPORTED_REVIEW_RESULT_VERSIONS = frozenset(
    {
        REVIEW_RESULT_VERSION,
        PRE_DEPENDENCY_REVIEW_RESULT_VERSION,
        PRE_REWORK_REVIEW_RESULT_VERSION,
        PRE_WHAT_REVIEW_RESULT_VERSION,
        TREE_BOUND_LEGACY_REVIEW_RESULT_VERSION,
        LEGACY_REVIEW_RESULT_VERSION,
    }
)
CURRENT_TREE_REVIEW_RESULT_VERSIONS = frozenset(
    {
        REVIEW_RESULT_VERSION,
        PRE_DEPENDENCY_REVIEW_RESULT_VERSION,
        PRE_REWORK_REVIEW_RESULT_VERSION,
        PRE_WHAT_REVIEW_RESULT_VERSION,
    }
)
#: Versions that carry WHAT evidence and establish a WHAT status.
WHAT_BOUND_REVIEW_RESULT_VERSIONS = frozenset(
    {
        REVIEW_RESULT_VERSION,
        PRE_DEPENDENCY_REVIEW_RESULT_VERSION,
        PRE_REWORK_REVIEW_RESULT_VERSION,
    }
)
#: Versions that carry the verified rework responses.
REWORK_BOUND_REVIEW_RESULT_VERSIONS = frozenset(
    {REVIEW_RESULT_VERSION, PRE_DEPENDENCY_REVIEW_RESULT_VERSION}
)
MANIFEST_VERSION_BY_RESULT_VERSION = {
    TREE_BOUND_LEGACY_REVIEW_RESULT_VERSION: LEGACY_NORMATIVE_TREE_VERSION,
    PRE_WHAT_REVIEW_RESULT_VERSION: NORMATIVE_TREE_VERSION,
    PRE_REWORK_REVIEW_RESULT_VERSION: NORMATIVE_TREE_VERSION,
    PRE_DEPENDENCY_REVIEW_RESULT_VERSION: NORMATIVE_TREE_VERSION,
    REVIEW_RESULT_VERSION: NORMATIVE_TREE_VERSION,
}
REVIEW_RESULT_SUFFIX = "Review Result"
ITERATION_WIDTH = 4
FIRST_ITERATION = 1

NAME_PATTERN = re.compile(
    rf"^(?P<requirement_id>.+) — {REVIEW_RESULT_SUFFIX} "
    rf"(?P<iteration>\d{{{ITERATION_WIDTH},}})$"
)
JSON_FENCE = re.compile(r"```json\s*\n(?P<body>.*?)\n```", re.DOTALL)

VERSION_KEY = "review_result_version"
ITERATION_KEY = "iteration"
REQUIREMENT_ID_KEY = "requirement_id"
DOCUMENT_FINGERPRINT_KEY = "reviewed_document_fingerprint"
PROCESS_ITERATION_KEY = "reviewed_process_iteration"
PROCESS_FINGERPRINT_KEY = "reviewed_process_output_fingerprint"
REVIEWED_TREE_KEY = "reviewed_normative_tree"
VERDICT_KEY = "derived_verdict"
FINDING_VERIFICATIONS_KEY = "process_finding_verifications"
RELATION_VERIFICATIONS_KEY = "relation_proposal_verifications"
CONFIRMED_RELATIONS_KEY = "confirmed_relation_proposals"
NEW_FINDINGS_KEY = "new_findings"
ASSESSMENT_KEY = "assessment"
REVIEWED_QUESTIONS_KEY = "reviewed_product_questions"
QUESTION_VERIFICATIONS_KEY = "product_question_verifications"
MATERIAL_WHAT_KEY = "material_unresolved_what"
WHAT_STATUS_KEY = "derived_what_status"
WHAT_KEYS = (
    REVIEWED_QUESTIONS_KEY,
    QUESTION_VERIFICATIONS_KEY,
    MATERIAL_WHAT_KEY,
    WHAT_STATUS_KEY,
)
REVIEWED_BRIEF_KEY = "reviewed_rework_brief_identity"
REVIEWED_RESPONSES_KEY = "reviewed_rework_responses"
REWORK_VERIFICATIONS_KEY = "rework_verifications"
REWORK_KEYS = (REVIEWED_BRIEF_KEY, REVIEWED_RESPONSES_KEY, REWORK_VERIFICATIONS_KEY)
REVIEWED_RESPONSE_KEYS = frozenset(
    {"item", "outcome", "explanation", "product_question_index", "blocks_what"}
)
DEPENDENCY_VERIFICATIONS_KEY = "dependency_verifications"
DEPENDENCY_BINDINGS_KEY = "dependency_bindings"
DEPENDENCY_KEYS = (DEPENDENCY_VERIFICATIONS_KEY, DEPENDENCY_BINDINGS_KEY)
DEPENDENCY_VERIFICATION_KEYS = frozenset(
    {"requirement_id", "outcome", "severity", "reason"}
)
BINDING_KEYS = frozenset(
    {
        "requirement_id",
        "entity_id",
        "origin",
        "tree_fingerprint",
        "review_iteration",
        "review_digest",
    }
)


class DependencyOrigin(StrEnum):
    """Why a Requirement is in the interpretation set of the reviewed one."""

    # A DEPENDS_ON edge the reviewed Requirement already had.
    EXISTING = "EXISTING"
    # A DEPENDS_ON proposal the review confirmed; Apply writes the edge.
    PROPOSED = "PROPOSED"
    # A dependency of a dependency, reached through bound edges.
    TRANSITIVE = "TRANSITIVE"


@dataclass(frozen=True)
class DependencyBinding:
    """One normative dependency, bound to the exact version that was reviewed.

    `tree_fingerprint` is the dependency's normative-tree fingerprint and
    `review_digest` the canonical-content fingerprint of its latest Review
    Result, both as read when the review ran: change detection, not an
    authenticated signature.
    """

    requirement_id: str
    entity_id: str
    origin: DependencyOrigin
    tree_fingerprint: str
    review_iteration: int
    review_digest: str

    @property
    def is_direct(self) -> bool:
        return self.origin is not DependencyOrigin.TRANSITIVE

    def to_payload(self) -> dict[str, object]:
        return {
            "requirement_id": self.requirement_id,
            "entity_id": self.entity_id,
            "origin": self.origin.value,
            "tree_fingerprint": self.tree_fingerprint,
            "review_iteration": self.review_iteration,
            "review_digest": self.review_digest,
        }


class InvalidReviewResult(ValueError):
    """A persisted Review Result cannot be trusted."""


@dataclass(frozen=True)
class ReviewedReworkResponse:
    """A copy of one Process rework response, as the review verified it.

    `blocks_what` is copied from the Brief item it answers, so the WHAT
    status can be recomputed from the Review Result alone.
    """

    response: ReworkResponse
    blocks_what: bool


def _escalated_refs(
    responses: tuple[ReviewedReworkResponse, ...],
) -> frozenset[str]:
    return frozenset(
        reviewed.response.item
        for reviewed in responses
        if reviewed.response.outcome is ReworkOutcome.ESCALATED
    )


def review_result_name(requirement_id: str, iteration: int) -> str:
    """`<Requirement ID> — Review Result 0001`."""
    return f"{requirement_id} — {REVIEW_RESULT_SUFFIX} {iteration:0{ITERATION_WIDTH}d}"


def parse_review_result_name(name: str) -> tuple[str, int] | None:
    """Split an artifact name back into Requirement ID and iteration."""
    match = NAME_PATTERN.match(name.strip())
    if match is None:
        return None
    return match.group("requirement_id"), int(match.group("iteration"))


@dataclass(frozen=True)
class ReviewResult:
    """One completed review iteration, bound to exactly what it reviewed."""

    requirement_id: str
    iteration: int
    reviewed_document_fingerprint: str
    reviewed_process_iteration: int
    reviewed_process_output_fingerprint: str
    verdict: ReviewVerdict
    finding_verifications: tuple[FindingVerification, ...]
    relation_verifications: tuple[RelationVerification, ...]
    new_findings: tuple[NewFinding, ...]
    assessment: dict[str, str]
    version: str = REVIEW_RESULT_VERSION
    # The normative tree this review actually saw. None on a legacy 0.1 result.
    reviewed_tree: TreeManifest | None = None
    # 0.4 and 0.5; None on every older version, which establishes no WHAT
    # status.
    reviewed_product_questions: tuple[ProductQuestion, ...] | None = None
    question_verifications: tuple[QuestionVerification, ...] = ()
    material_unresolved_what: tuple[MaterialWhat, ...] = ()
    what_status: WhatStatus | None = None
    # 0.5 only: the Brief the reviewed Process received, its responses and
    # their verification. None and () when that Process received no Brief.
    reviewed_brief_identity: str | None = None
    reviewed_rework_responses: tuple[ReviewedReworkResponse, ...] = ()
    rework_verifications: tuple[ReworkVerification, ...] = ()
    # 0.6 only: the existing DEPENDS_ON edges verified, and every normative
    # dependency bound. Empty on older versions, which establish no
    # dependency evidence at all (not "no dependencies").
    dependency_verifications: tuple[DependencyVerification, ...] = ()
    dependency_bindings: tuple[DependencyBinding, ...] = ()

    @property
    def name(self) -> str:
        return review_result_name(self.requirement_id, self.iteration)

    @property
    def is_tree_bound(self) -> bool:
        return self.reviewed_tree is not None

    @property
    def is_rework_bound(self) -> bool:
        """Whether this review records the rework claims it verified (0.5+)."""
        return self.version in REWORK_BOUND_REVIEW_RESULT_VERSIONS

    @property
    def is_dependency_bound(self) -> bool:
        """Whether this review establishes dependency evidence (0.6)."""
        return self.version == REVIEW_RESULT_VERSION

    @property
    def verified_dependencies(self) -> frozenset[str]:
        """The direct, verified, bound DEPENDS_ON targets (section 8).

        None before 0.6: an older review bound no dependency, so a confirmed
        DEPENDS_ON proposal in it never answers a question.
        """
        if not self.is_dependency_bound:
            return frozenset()
        return verified_dependencies(
            self.relation_verifications, self.dependency_verifications
        )

    @property
    def rework_what_refs(self) -> frozenset[str]:
        return frozenset(
            reviewed.response.item
            for reviewed in self.reviewed_rework_responses
            if reviewed.blocks_what
        )

    @property
    def rework_escalated_refs(self) -> frozenset[str]:
        return _escalated_refs(self.reviewed_rework_responses)

    @property
    def is_current(self) -> bool:
        """0.3 to 0.6 with a manifest v2 tree: current tree evidence.

        Whether it also establishes a WHAT status is `what_status`.
        """
        return (
            self.version in CURRENT_TREE_REVIEW_RESULT_VERSIONS
            and self.reviewed_tree is not None
            and self.reviewed_tree.is_current
        )

    def reviews_tree(self, tree_fingerprint: str) -> bool:
        return (
            self.reviewed_tree is not None
            and self.reviewed_tree.fingerprint == tree_fingerprint
        )

    @property
    def confirmed_relations(self) -> tuple[RelationVerification, ...]:
        return tuple(
            verification
            for verification in self.relation_verifications
            if verification.outcome is VerificationOutcome.CONFIRMED
        )

    def reviews(
        self,
        document_fingerprint: str,
        process_iteration: int,
        process_output_fingerprint: str,
    ) -> bool:
        """Whether this result certifies exactly that input."""
        return (
            self.reviewed_document_fingerprint == document_fingerprint
            and self.reviewed_process_iteration == process_iteration
            and self.reviewed_process_output_fingerprint == process_output_fingerprint
        )


def build_review_result(
    requirement_id: str,
    iteration: int,
    reviewed_document_fingerprint: str,
    reviewed_process_iteration: int,
    reviewed_process_output_fingerprint: str,
    review: ReviewOutput,
    reviewed_tree: TreeManifest,
    *,
    reviewed_product_questions: tuple[ProductQuestion, ...],
    reviewed_rework_brief: ReworkBrief | None = None,
    reviewed_rework_responses: tuple[ReworkResponse, ...] = (),
    dependency_bindings: tuple[DependencyBinding, ...] = (),
) -> ReviewResult:
    """Assemble the artifact, deriving verdict and WHAT status, never accepting.

    `reviewed_product_questions` are the bound Process Result's questions, the
    ones the review verified; `reviewed_rework_brief` and
    `reviewed_rework_responses` its Rework Brief and the responses verified;
    `dependency_bindings` the dependencies the reviewer stage bound.
    """
    if not reviewed_tree.is_current:
        raise InvalidReviewResult(
            f"A Review Result {REVIEW_RESULT_VERSION} binds manifest version "
            f"{NORMATIVE_TREE_VERSION}, not {reviewed_tree.version}."
        )
    if reviewed_tree.root_entry.content_fingerprint != reviewed_document_fingerprint:
        raise InvalidReviewResult(
            "The reviewed tree's Root fingerprint disagrees with the reviewed "
            "document fingerprint."
        )
    reviewed_responses = (
        tuple(
            ReviewedReworkResponse(
                response=response,
                blocks_what=response.item in reviewed_rework_brief.what_refs,
            )
            for response in reviewed_rework_responses
        )
        if reviewed_rework_brief is not None
        else ()
    )
    what_refs = frozenset(
        reviewed.response.item
        for reviewed in reviewed_responses
        if reviewed.blocks_what
    )
    return ReviewResult(
        requirement_id=requirement_id,
        iteration=iteration,
        reviewed_document_fingerprint=reviewed_document_fingerprint,
        reviewed_process_iteration=reviewed_process_iteration,
        reviewed_process_output_fingerprint=reviewed_process_output_fingerprint,
        verdict=derive_verdict(
            review.finding_verifications,
            review.new_findings,
            review.rework_verifications,
            review.dependency_verifications,
        ),
        finding_verifications=review.finding_verifications,
        relation_verifications=review.relation_verifications,
        new_findings=review.new_findings,
        assessment=dict(review.assessment),
        reviewed_tree=reviewed_tree,
        reviewed_product_questions=tuple(reviewed_product_questions),
        question_verifications=review.question_verifications,
        material_unresolved_what=review.material_unresolved_what,
        what_status=_derive_what_status(
            tuple(reviewed_product_questions),
            review.question_verifications,
            review.material_unresolved_what,
            rework_leaves_what_open(
                what_refs,
                _escalated_refs(reviewed_responses),
                review.rework_verifications,
            ),
            verified_dependencies(
                review.relation_verifications, review.dependency_verifications
            ),
        ),
        reviewed_brief_identity=(
            reviewed_rework_brief.identity if reviewed_rework_brief else None
        ),
        reviewed_rework_responses=reviewed_responses,
        rework_verifications=review.rework_verifications,
        dependency_verifications=review.dependency_verifications,
        dependency_bindings=tuple(
            sorted(dependency_bindings, key=lambda binding: binding.requirement_id)
        ),
    )


def _derive_what_status(
    questions: tuple[ProductQuestion, ...],
    verifications: tuple[QuestionVerification, ...],
    material: tuple[MaterialWhat, ...],
    rework_what_open: bool = False,
    dependencies: frozenset[str] = frozenset(),
) -> WhatStatus:
    try:
        return derive_what_status(
            questions, verifications, material, rework_what_open, dependencies
        )
    except InvalidReviewOutput as error:
        raise InvalidReviewResult(str(error)) from error


def render_review_result(result: ReviewResult) -> str:
    """Render the artifact: a short human header plus the machine payload."""
    payload = {
        VERSION_KEY: result.version,
        ITERATION_KEY: result.iteration,
        REQUIREMENT_ID_KEY: result.requirement_id,
        DOCUMENT_FINGERPRINT_KEY: result.reviewed_document_fingerprint,
        PROCESS_ITERATION_KEY: result.reviewed_process_iteration,
        PROCESS_FINGERPRINT_KEY: result.reviewed_process_output_fingerprint,
        **(
            {REVIEWED_TREE_KEY: result.reviewed_tree.to_payload()}
            if result.version != LEGACY_REVIEW_RESULT_VERSION
            and result.reviewed_tree is not None
            else {}
        ),
        VERDICT_KEY: result.verdict.value,
        FINDING_VERIFICATIONS_KEY: [
            {
                "process_finding_index": verification.process_finding_index,
                "outcome": verification.outcome.value,
                "severity": (
                    verification.severity.value if verification.severity else None
                ),
                "reason": verification.reason,
            }
            for verification in result.finding_verifications
        ],
        RELATION_VERIFICATIONS_KEY: [
            _relation_payload(verification)
            for verification in result.relation_verifications
        ],
        CONFIRMED_RELATIONS_KEY: [
            _relation_payload(verification)
            for verification in result.confirmed_relations
        ],
        NEW_FINDINGS_KEY: [
            {
                "kind": finding.kind.value,
                "severity": finding.severity.value,
                "requirement_id": finding.requirement_id,
                "detail": finding.detail,
            }
            for finding in result.new_findings
        ],
        ASSESSMENT_KEY: result.assessment,
        **(
            _what_payload(result)
            if result.version in WHAT_BOUND_REVIEW_RESULT_VERSIONS
            else {}
        ),
        **(_rework_payload(result) if result.is_rework_bound else {}),
        **(_dependency_payload(result) if result.is_dependency_bound else {}),
    }
    body = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False)
    return (
        f"# {result.name}\n"
        "\n"
        "Review artifact written by the independent Standard Requirement "
        "Reviewer. It records the verification of one exact reviewed state so a "
        "human at Ready can see what was checked and what was concluded. It is "
        "immutable review history. The verdict is derived from the findings "
        "below, and the relations it confirms are not written to Fibery.\n"
        "\n"
        f"```json\n{body}\n```\n"
    )


def _what_payload(result: ReviewResult) -> dict[str, object]:
    if result.what_status is None or result.reviewed_product_questions is None:
        raise InvalidReviewResult(
            f"A Review Result {result.version} must carry its WHAT evidence."
        )
    return {
        REVIEWED_QUESTIONS_KEY: [
            {"detail": question.detail, "material": question.material}
            for question in result.reviewed_product_questions
        ],
        QUESTION_VERIFICATIONS_KEY: [
            {
                "question_index": item.question_index,
                "outcome": item.outcome.value,
                "material": item.material,
                "basis": item.basis.value if item.basis else None,
                "requirement_id": item.requirement_id,
                "reason": item.reason,
            }
            for item in result.question_verifications
        ],
        MATERIAL_WHAT_KEY: [
            {"detail": item.detail} for item in result.material_unresolved_what
        ],
        WHAT_STATUS_KEY: result.what_status.value,
    }


def _rework_payload(result: ReviewResult) -> dict[str, object]:
    return {
        REVIEWED_BRIEF_KEY: result.reviewed_brief_identity,
        REVIEWED_RESPONSES_KEY: [
            {
                "item": reviewed.response.item,
                "outcome": reviewed.response.outcome.value,
                "explanation": reviewed.response.explanation,
                "product_question_index": reviewed.response.product_question_index,
                "blocks_what": reviewed.blocks_what,
            }
            for reviewed in result.reviewed_rework_responses
        ],
        REWORK_VERIFICATIONS_KEY: [
            {
                "item": item.item,
                "outcome": item.outcome.value,
                "severity": item.severity.value if item.severity else None,
                "reason": item.reason,
            }
            for item in result.rework_verifications
        ],
    }


def _dependency_payload(result: ReviewResult) -> dict[str, object]:
    return {
        DEPENDENCY_VERIFICATIONS_KEY: [
            {
                "requirement_id": item.requirement_id,
                "outcome": item.outcome.value,
                "severity": item.severity.value if item.severity else None,
                "reason": item.reason,
            }
            for item in result.dependency_verifications
        ],
        DEPENDENCY_BINDINGS_KEY: [
            binding.to_payload() for binding in result.dependency_bindings
        ],
    }


def _relation_payload(verification: RelationVerification) -> dict[str, str]:
    return {
        "kind": verification.kind.value,
        "requirement_id": verification.requirement_id,
        "outcome": verification.outcome.value,
        "reason": verification.reason,
    }


def parse_review_result(text: str) -> ReviewResult:
    """Read a persisted review back, or refuse to trust it."""
    payload = _read_payload(text)
    version = payload.get(VERSION_KEY)
    if version not in SUPPORTED_REVIEW_RESULT_VERSIONS:
        raise InvalidReviewResult(
            f"Review Result version {version!r} is not supported; this reviewer "
            f"reads {sorted(SUPPORTED_REVIEW_RESULT_VERSIONS)!r}."
        )
    iteration = _require_iteration(payload.get(ITERATION_KEY), "iteration")
    verifications = tuple(
        _read_finding_verification(entry)
        for entry in _as_list(payload.get(FINDING_VERIFICATIONS_KEY))
    )
    new_findings = tuple(
        _read_new_finding(entry) for entry in _as_list(payload.get(NEW_FINDINGS_KEY))
    )

    _forbid_what_evidence(payload, version)
    rework = _read_rework_evidence(payload, version)
    relations = tuple(
        _read_relation_verification(entry)
        for entry in _as_list(payload.get(RELATION_VERIFICATIONS_KEY))
    )
    dependency = _read_dependency_evidence(payload, version, relations)
    verdict = _read_verdict(payload.get(VERDICT_KEY))
    recalculated = derive_verdict(
        verifications,
        new_findings,
        rework.get("rework_verifications", ()),
        dependency.get("dependency_verifications", ()),
    )
    if verdict is not recalculated:
        # The artifact grades itself. If the stored verdict and the findings it
        # stores disagree, one of them is wrong and neither can be preferred.
        raise InvalidReviewResult(
            f"The persisted verdict {verdict.value} contradicts the findings, "
            f"which derive {recalculated.value}."
        )

    requirement_id = _require_text(payload.get(REQUIREMENT_ID_KEY), "requirement_id")
    reviewed_document = _require_text(
        payload.get(DOCUMENT_FINGERPRINT_KEY), DOCUMENT_FINGERPRINT_KEY
    )
    reviewed_tree = _read_reviewed_tree(
        payload, version, requirement_id, reviewed_document
    )
    what = _read_what_evidence(
        payload,
        version,
        rework,
        # Only a dependency-bound review has verified dependencies; an older
        # one is read under the rules it was written with.
        verified_dependencies(relations, dependency["dependency_verifications"])
        if version == REVIEW_RESULT_VERSION
        else frozenset(),
    )
    return ReviewResult(
        requirement_id=requirement_id,
        iteration=iteration,
        reviewed_document_fingerprint=reviewed_document,
        reviewed_process_iteration=_require_iteration(
            payload.get(PROCESS_ITERATION_KEY), PROCESS_ITERATION_KEY
        ),
        reviewed_process_output_fingerprint=_require_text(
            payload.get(PROCESS_FINGERPRINT_KEY), PROCESS_FINGERPRINT_KEY
        ),
        verdict=verdict,
        finding_verifications=verifications,
        relation_verifications=relations,
        new_findings=new_findings,
        assessment=dict(payload.get(ASSESSMENT_KEY) or {}),
        version=version,
        reviewed_tree=reviewed_tree,
        **what,
        **rework,
        **dependency,
    )


def _read_dependency_evidence(
    payload: dict[str, object],
    version: str,
    relations: tuple[RelationVerification, ...],
) -> dict:
    """The 0.6 dependency evidence, closed and coherent; none before 0.6.

    The EXISTING bindings are exactly the verified existing edges, the
    PROPOSED ones exactly the confirmed DEPENDS_ON proposals that were not
    already edges, and a TRANSITIVE one is neither.
    """
    if version != REVIEW_RESULT_VERSION:
        present = [key for key in DEPENDENCY_KEYS if key in payload]
        if present:
            raise InvalidReviewResult(
                f"A {version} Review Result cannot carry dependency evidence: "
                + ", ".join(present)
            )
        return {}
    missing = [key for key in DEPENDENCY_KEYS if key not in payload]
    if missing:
        raise InvalidReviewResult(
            f"A {REVIEW_RESULT_VERSION} Review Result is missing its dependency "
            "evidence: " + ", ".join(missing)
        )
    for key in DEPENDENCY_KEYS:
        if not isinstance(payload[key], list):
            raise InvalidReviewResult(f"{key} must be a list.")
    verifications = tuple(
        _read_dependency_verification(entry)
        for entry in payload[DEPENDENCY_VERIFICATIONS_KEY]
    )
    bindings = tuple(_read_binding(entry) for entry in payload[DEPENDENCY_BINDINGS_KEY])
    ids = [binding.requirement_id for binding in bindings]
    if len(set(ids)) != len(ids) or ids != sorted(ids):
        raise InvalidReviewResult(
            "dependency_bindings must name each Requirement once, in order."
        )
    by_origin = {
        origin: {b.requirement_id for b in bindings if b.origin is origin}
        for origin in DependencyOrigin
    }
    verified = [item.requirement_id for item in verifications]
    proposed = {
        item.requirement_id
        for item in relations
        if item.kind is RelationKind.DEPENDS_ON
        and item.outcome is VerificationOutcome.CONFIRMED
    } - by_origin[DependencyOrigin.EXISTING]
    if (
        len(set(verified)) != len(verified)
        or set(verified) != by_origin[DependencyOrigin.EXISTING]
        or proposed != by_origin[DependencyOrigin.PROPOSED]
    ):
        raise InvalidReviewResult(
            "The persisted dependency bindings disagree with the verified "
            "existing dependencies and the confirmed DEPENDS_ON proposals."
        )
    return {
        "dependency_verifications": verifications,
        "dependency_bindings": bindings,
    }


def _read_dependency_verification(entry: object) -> DependencyVerification:
    if not isinstance(entry, dict) or set(entry) != DEPENDENCY_VERIFICATION_KEYS:
        raise InvalidReviewResult(f"Malformed dependency verification: {entry!r}")
    try:
        outcome = VerificationOutcome(entry["outcome"])
        severity = entry["severity"]
        verification = DependencyVerification(
            requirement_id=entry["requirement_id"],
            outcome=outcome,
            reason=entry["reason"],
            severity=ReviewSeverity(severity) if severity is not None else None,
        )
    except ValueError as error:
        raise InvalidReviewResult(
            f"Malformed dependency verification: {error}"
        ) from error
    if (
        not isinstance(verification.requirement_id, str)
        or not verification.requirement_id.strip()
        or not isinstance(verification.reason, str)
        or not verification.reason.strip()
        or (outcome is VerificationOutcome.REJECTED) != (severity is not None)
    ):
        raise InvalidReviewResult(
            "A persisted dependency verification carries a severity if and only "
            "if it rejects the dependency."
        )
    return verification


def _read_binding(entry: object) -> DependencyBinding:
    if not isinstance(entry, dict) or set(entry) != BINDING_KEYS:
        raise InvalidReviewResult(f"Malformed dependency binding: {entry!r}")
    try:
        origin = DependencyOrigin(entry["origin"])
    except ValueError as error:
        raise InvalidReviewResult(f"Malformed dependency binding: {error}") from error
    texts = ("requirement_id", "entity_id", "tree_fingerprint", "review_digest")
    iteration = entry["review_iteration"]
    if (
        any(not isinstance(entry[key], str) or not entry[key].strip() for key in texts)
        or not isinstance(iteration, int)
        or isinstance(iteration, bool)
        or iteration < FIRST_ITERATION
    ):
        raise InvalidReviewResult(f"Malformed dependency binding: {entry!r}")
    return DependencyBinding(
        requirement_id=entry["requirement_id"],
        entity_id=entry["entity_id"],
        origin=origin,
        tree_fingerprint=entry["tree_fingerprint"],
        review_iteration=iteration,
        review_digest=entry["review_digest"],
    )


def _read_rework_evidence(payload: dict[str, object], version: str) -> dict:
    """The 0.5+ rework evidence, closed and exactly covered; none before 0.5."""
    if version not in REWORK_BOUND_REVIEW_RESULT_VERSIONS:
        present = [key for key in REWORK_KEYS if key in payload]
        if present:
            raise InvalidReviewResult(
                f"A {version} Review Result cannot carry rework evidence: "
                + ", ".join(present)
            )
        return {}
    missing = [key for key in REWORK_KEYS if key not in payload]
    if missing:
        raise InvalidReviewResult(
            f"A {version} Review Result is missing its rework evidence: "
            + ", ".join(missing)
        )
    identity = payload[REVIEWED_BRIEF_KEY]
    if identity is not None and (not isinstance(identity, str) or not identity):
        raise InvalidReviewResult(f"{REVIEWED_BRIEF_KEY} must be text or null.")
    for key in (REVIEWED_RESPONSES_KEY, REWORK_VERIFICATIONS_KEY):
        if not isinstance(payload[key], list):
            raise InvalidReviewResult(f"{key} must be a list.")
    responses = tuple(
        _read_reviewed_response(entry) for entry in payload[REVIEWED_RESPONSES_KEY]
    )
    verifications = tuple(
        _read_rework_verification(entry) for entry in payload[REWORK_VERIFICATIONS_KEY]
    )
    if identity is None and responses:
        raise InvalidReviewResult(
            "A review of a Process Result without a Rework Brief verified rework "
            "responses."
        )
    expected = [reviewed.response.item for reviewed in responses]
    addressed = [item.item for item in verifications]
    if len(set(expected)) != len(expected) or sorted(addressed) != sorted(expected):
        raise InvalidReviewResult(
            "The persisted rework verifications do not cover each reviewed rework "
            "response exactly once."
        )
    return {
        "reviewed_brief_identity": identity,
        "reviewed_rework_responses": responses,
        "rework_verifications": verifications,
    }


def _read_reviewed_response(entry: object) -> ReviewedReworkResponse:
    if not isinstance(entry, dict) or set(entry) != REVIEWED_RESPONSE_KEYS:
        raise InvalidReviewResult(f"Malformed reviewed rework response: {entry!r}")
    index = entry["product_question_index"]
    try:
        outcome = ReworkOutcome(entry["outcome"])
    except ValueError as error:
        raise InvalidReviewResult(
            f"Malformed reviewed rework response: {error}"
        ) from error
    if (
        not isinstance(entry["item"], str)
        or not isinstance(entry["explanation"], str)
        or not entry["explanation"].strip()
        or not isinstance(entry["blocks_what"], bool)
        or (
            index is not None
            and (not isinstance(index, int) or isinstance(index, bool))
        )
        or (index is not None and outcome is not ReworkOutcome.ESCALATED)
    ):
        raise InvalidReviewResult(f"Malformed reviewed rework response: {entry!r}")
    return ReviewedReworkResponse(
        response=ReworkResponse(
            item=entry["item"],
            outcome=outcome,
            explanation=entry["explanation"],
            product_question_index=index,
        ),
        blocks_what=entry["blocks_what"],
    )


def _read_rework_verification(entry: object) -> ReworkVerification:
    if not isinstance(entry, dict) or set(entry) != {
        "item",
        "outcome",
        "severity",
        "reason",
    }:
        raise InvalidReviewResult(f"Malformed rework verification: {entry!r}")
    try:
        outcome = VerificationOutcome(entry["outcome"])
        severity = entry["severity"]
        verification = ReworkVerification(
            item=entry["item"],
            outcome=outcome,
            reason=entry["reason"],
            severity=ReviewSeverity(severity) if severity is not None else None,
        )
    except ValueError as error:
        raise InvalidReviewResult(f"Malformed rework verification: {error}") from error
    if (
        not isinstance(verification.item, str)
        or not isinstance(verification.reason, str)
        or not verification.reason.strip()
        or (outcome is VerificationOutcome.REJECTED) != (severity is not None)
    ):
        raise InvalidReviewResult(
            "A persisted rework verification carries a severity if and only if "
            "it rejects the response."
        )
    return verification


def _forbid_what_evidence(payload: dict[str, object], version: str) -> None:
    if version in WHAT_BOUND_REVIEW_RESULT_VERSIONS:
        return
    present = [key for key in WHAT_KEYS if key in payload]
    if present:
        raise InvalidReviewResult(
            f"A {version} Review Result cannot carry WHAT evidence: "
            + ", ".join(present)
        )


def _read_what_evidence(
    payload: dict[str, object],
    version: str,
    rework: dict,
    dependencies: frozenset[str] = frozenset(),
) -> dict:
    """The 0.4+ WHAT evidence, its status recomputed; none for older versions.

    `dependencies` are the verified, bound direct dependencies (0.6), the
    only peers that can answer a material question.
    """
    if version not in WHAT_BOUND_REVIEW_RESULT_VERSIONS:
        return {}
    missing = [key for key in WHAT_KEYS if key not in payload]
    if missing:
        raise InvalidReviewResult(
            f"A {version} Review Result is missing its WHAT evidence: "
            + ", ".join(missing)
        )
    for key in (REVIEWED_QUESTIONS_KEY, QUESTION_VERIFICATIONS_KEY, MATERIAL_WHAT_KEY):
        if not isinstance(payload[key], list):
            raise InvalidReviewResult(f"{key} must be a list.")
    questions = tuple(
        _read_product_question(entry)
        for entry in _as_list(payload.get(REVIEWED_QUESTIONS_KEY))
    )
    verifications = tuple(
        _read_question_verification(entry)
        for entry in _as_list(payload.get(QUESTION_VERIFICATIONS_KEY))
    )
    material = tuple(
        _read_material_what(entry) for entry in _as_list(payload.get(MATERIAL_WHAT_KEY))
    )
    try:
        stored = WhatStatus(payload.get(WHAT_STATUS_KEY))
    except ValueError as error:
        raise InvalidReviewResult(
            f"Unknown persisted WHAT status {payload.get(WHAT_STATUS_KEY)!r}."
        ) from error
    responses = rework.get("reviewed_rework_responses", ())
    what_refs = frozenset(
        reviewed.response.item for reviewed in responses if reviewed.blocks_what
    )
    rework_verifications = rework.get("rework_verifications", ())
    contradicted = contradictory_escalations(
        questions,
        verifications,
        material_escalations(
            tuple(reviewed.response for reviewed in responses), what_refs
        ),
        rework_verifications,
        dependencies,
    )
    if contradicted:
        raise InvalidReviewResult(
            "The persisted review both confirms and contradicts that a material "
            "WHAT stays open: " + ", ".join(contradicted)
        )
    recalculated = _derive_what_status(
        questions,
        verifications,
        material,
        rework_leaves_what_open(
            what_refs, _escalated_refs(responses), rework_verifications
        ),
        dependencies,
    )
    if stored is not recalculated:
        raise InvalidReviewResult(
            f"The persisted WHAT status {stored.value} contradicts the verified "
            f"questions, which derive {recalculated.value}."
        )
    return {
        "reviewed_product_questions": questions,
        "question_verifications": verifications,
        "material_unresolved_what": material,
        "what_status": stored,
    }


def what_clearance(review: ReviewResult, process: ProcessResult) -> WhatStatus | None:
    """The WHAT status a Review Result establishes for the Process it binds.

    None means the evidence establishes no status at all (a Review Result
    older than 0.4): never CLEAR. A 0.4 review whose verified questions are not
    exactly the bound Process Result's questions is incoherent and refused, and
    so is an older review of a Process Result that recorded questions: the
    reviewer of such a Process always writes 0.4. The caller has already
    checked that `review` binds `process`.
    """
    if review.what_status is None:
        if process.has_question_evidence:
            raise InvalidReviewResult(
                f"Review Result {review.iteration} (version {review.version}) "
                f"carries no WHAT evidence for Process Result {process.iteration}, "
                "which recorded product questions."
            )
        return None
    if not process.has_question_evidence or (
        review.reviewed_product_questions != process.product_questions
    ):
        raise InvalidReviewResult(
            f"Review Result {review.iteration} verified product questions that are "
            f"not the questions of Process Result {process.iteration}."
        )
    _require_rework_coherence(review, process)
    return review.what_status


def _require_rework_coherence(review: ReviewResult, process: ProcessResult) -> None:
    """The review verified exactly the rework claims the bound Process made.

    A 0.4 review predates rework evidence, so it can only have reviewed a
    Process Result that received no Brief; the reviewer of a 0.5 Process
    Result always writes 0.5, so a downgraded review is incoherent.
    """
    if not review.is_rework_bound:
        if process.is_rework_bound:
            raise InvalidReviewResult(
                f"Review Result {review.iteration} (version {review.version}) "
                "carries no rework evidence for Process Result "
                f"{process.iteration}, which records it."
            )
        return
    expected = (
        tuple(
            ReviewedReworkResponse(
                response=response,
                blocks_what=response.item in process.rework_brief.what_refs,
            )
            for response in process.rework_responses
        )
        if process.rework_brief is not None
        else ()
    )
    if (
        review.reviewed_brief_identity != process.brief_identity
        or review.reviewed_rework_responses != expected
    ):
        raise InvalidReviewResult(
            f"Review Result {review.iteration} verified rework responses that are "
            f"not those of Process Result {process.iteration}."
        )


def open_material_questions(review: ReviewResult) -> tuple[str, ...]:
    """The material WHAT questions a 0.4+ Review Result leaves open, for humans."""
    questions = review.reviewed_product_questions or ()
    by_index = {item.question_index: item for item in review.question_verifications}
    dependencies = review.verified_dependencies
    open_questions = [
        question.detail
        for index, question in enumerate(questions)
        if index in by_index
        and question_blocks(question, by_index[index], dependencies)
    ]
    what_refs = review.rework_what_refs
    escalated = review.rework_escalated_refs
    explanations = {
        reviewed.response.item: reviewed.response.explanation
        for reviewed in review.reviewed_rework_responses
    }
    open_rework = [
        f"{item.item}: {explanations[item.item]}"
        for item in review.rework_verifications
        if item.item in what_refs
        and (
            item.item in escalated or item.outcome is not VerificationOutcome.CONFIRMED
        )
    ]
    return (
        *open_questions,
        *(item.detail for item in review.material_unresolved_what),
        *open_rework,
    )


def build_rework_brief(review: ReviewResult, process: ProcessResult) -> ReworkBrief:
    """The Rework Brief one completed review gives the next Process iteration.

    `process` must be the Process Result `review` reviewed. Every actionable
    item keeps its source: a Process finding with the Review's outcome, a
    new finding, an unconfirmed relation proposal, a verified product
    question, an added material WHAT question, and an unconfirmed rework
    response. Confirmed relations and confirmed rework responses are not
    actionable and are left out; nothing else is. The assessment travels as
    context. Raises InvalidReviewResult when the pair is not a coherent
    lineage, so a malformed or mismatched review is refused, not skipped.
    """
    if review.requirement_id != process.requirement_id or not (
        review.reviewed_process_iteration == process.iteration
        and review.reviewed_process_output_fingerprint == process.output_fingerprint
    ):
        raise InvalidReviewResult(
            f"Review Result {review.iteration} does not review Process Result "
            f"{process.iteration} of {process.requirement_id}."
        )
    what_clearance(review, process)
    source = ReviewSource(
        requirement_id=review.requirement_id,
        review_iteration=review.iteration,
        review_version=review.version,
        process_iteration=process.iteration,
        process_output_fingerprint=process.output_fingerprint,
        process_version=process.version,
    )
    brief = ReworkBrief(
        source=source,
        items=(
            *_finding_items(review, process),
            *_new_finding_items(review),
            *_relation_items(review, process),
            *_question_items(review),
            *_material_what_items(review),
            *_dependency_items(review),
            *_rework_claim_items(review, process),
        ),
        assessment=dict(review.assessment),
    )
    # The persisted Review readers are looser than the Brief's closed shape
    # (an empty reason, a blank assessment); hold the Brief to the shape it
    # will be read back with, so such a Review refuses before any model call.
    try:
        ReworkBrief.from_payload(brief.to_payload())
    except InvalidReworkBrief as error:
        raise InvalidReviewResult(
            f"Review Result {review.iteration} cannot be carried as a Rework "
            f"Brief: {error}"
        ) from error
    return brief


def _ref(review: ReviewResult, category: BriefCategory, index: int) -> str:
    return item_ref(review.iteration, category, index)


def _finding_items(
    review: ReviewResult, process: ProcessResult
) -> tuple[BriefItem, ...]:
    items = []
    for verification in review.finding_verifications:
        index = verification.process_finding_index
        if not 0 <= index < len(process.findings):
            raise InvalidReviewResult(
                f"Review Result {review.iteration} verifies Process finding {index}, "
                f"but Process Result {process.iteration} has "
                f"{len(process.findings)}."
            )
        finding = process.findings[index]
        items.append(
            BriefItem(
                ref=_ref(review, BriefCategory.PROCESS_FINDING, index),
                category=BriefCategory.PROCESS_FINDING,
                detail=finding.detail,
                feedback=verification.reason,
                outcome=verification.outcome,
                kind=finding.kind.value,
                severity=verification.severity,
                requirement_id=finding.requirement_id,
            )
        )
    return tuple(items)


def _new_finding_items(review: ReviewResult) -> tuple[BriefItem, ...]:
    return tuple(
        BriefItem(
            ref=_ref(review, BriefCategory.NEW_FINDING, index),
            category=BriefCategory.NEW_FINDING,
            detail=finding.detail,
            kind=finding.kind.value,
            severity=finding.severity,
            requirement_id=finding.requirement_id,
        )
        for index, finding in enumerate(review.new_findings)
    )


def _relation_items(
    review: ReviewResult, process: ProcessResult
) -> tuple[BriefItem, ...]:
    rationale = {
        (relation.kind, relation.requirement_id): relation.rationale
        for relation in process.proposed_relations
    }
    items = []
    for index, verification in enumerate(review.relation_verifications):
        edge = (verification.kind, verification.requirement_id)
        if edge not in rationale:
            raise InvalidReviewResult(
                f"Review Result {review.iteration} verifies relation "
                f"{verification.kind.value} {verification.requirement_id}, which "
                f"Process Result {process.iteration} did not propose."
            )
        if verification.outcome is VerificationOutcome.CONFIRMED:
            continue
        items.append(
            BriefItem(
                ref=_ref(review, BriefCategory.RELATION_PROPOSAL, index),
                category=BriefCategory.RELATION_PROPOSAL,
                detail=rationale[edge],
                feedback=verification.reason,
                outcome=verification.outcome,
                kind=verification.kind.value,
                requirement_id=verification.requirement_id,
            )
        )
    return tuple(items)


def _question_items(review: ReviewResult) -> tuple[BriefItem, ...]:
    questions = review.reviewed_product_questions or ()
    return tuple(
        BriefItem(
            ref=_ref(review, BriefCategory.PRODUCT_QUESTION, item.question_index),
            category=BriefCategory.PRODUCT_QUESTION,
            detail=questions[item.question_index].detail,
            blocks_what=question_blocks(
                questions[item.question_index], item, review.verified_dependencies
            ),
            feedback=item.reason,
            outcome=item.outcome,
            requirement_id=item.requirement_id,
        )
        for item in review.question_verifications
    )


def _dependency_items(review: ReviewResult) -> tuple[BriefItem, ...]:
    """Existing DEPENDS_ON edges the review did not confirm, with their target."""
    return tuple(
        BriefItem(
            ref=_ref(review, BriefCategory.EXISTING_DEPENDENCY, index),
            category=BriefCategory.EXISTING_DEPENDENCY,
            detail=f"{RelationKind.DEPENDS_ON.value} {item.requirement_id}",
            feedback=item.reason,
            outcome=item.outcome,
            kind=RelationKind.DEPENDS_ON.value,
            severity=item.severity,
            requirement_id=item.requirement_id,
        )
        for index, item in enumerate(review.dependency_verifications)
        if item.outcome is not VerificationOutcome.CONFIRMED
    )


def _material_what_items(review: ReviewResult) -> tuple[BriefItem, ...]:
    return tuple(
        BriefItem(
            ref=_ref(review, BriefCategory.MATERIAL_WHAT, index),
            category=BriefCategory.MATERIAL_WHAT,
            detail=item.detail,
            blocks_what=True,
        )
        for index, item in enumerate(review.material_unresolved_what)
    )


def _rework_claim_items(
    review: ReviewResult, process: ProcessResult
) -> tuple[BriefItem, ...]:
    """Rework responses of the reviewed Process the review did not confirm.

    The earlier item is carried forward by its own text, with the response
    and the review's reason, so the next iteration answers it again.
    """
    if process.rework_brief is None:
        return ()
    claims = {
        reviewed.response.item: reviewed
        for reviewed in review.reviewed_rework_responses
    }
    items = []
    for index, verification in enumerate(review.rework_verifications):
        if verification.outcome is VerificationOutcome.CONFIRMED:
            continue
        claim = claims[verification.item]
        earlier = process.rework_brief.item(verification.item)
        items.append(
            BriefItem(
                ref=_ref(review, BriefCategory.REWORK_CLAIM, index),
                category=BriefCategory.REWORK_CLAIM,
                detail=(
                    f"{earlier.detail} (answered {claim.response.outcome.value}: "
                    f"{claim.response.explanation})"
                ),
                blocks_what=claim.blocks_what,
                feedback=verification.reason,
                outcome=verification.outcome,
                severity=verification.severity,
                kind=earlier.kind,
                requirement_id=earlier.requirement_id,
                origin_ref=earlier.ref,
            )
        )
    return tuple(items)


def _read_product_question(entry: object) -> ProductQuestion:
    if (
        not isinstance(entry, dict)
        or set(entry) != {"detail", "material"}
        or not isinstance(entry["detail"], str)
        or not entry["detail"].strip()
        or not isinstance(entry["material"], bool)
    ):
        raise InvalidReviewResult(f"Malformed reviewed product question: {entry!r}")
    return ProductQuestion(detail=entry["detail"], material=entry["material"])


def _read_question_verification(entry: object) -> QuestionVerification:
    if not isinstance(entry, dict) or not set(entry) <= {
        "question_index",
        "outcome",
        "material",
        "basis",
        "requirement_id",
        "reason",
    }:
        raise InvalidReviewResult(
            "Each question verification must be an object of the defined keys."
        )
    try:
        outcome = VerificationOutcome(entry["outcome"])
        basis = entry.get("basis")
        verification = QuestionVerification(
            question_index=entry["question_index"],
            outcome=outcome,
            reason=entry["reason"],
            material=entry.get("material"),
            basis=RejectionBasis(basis) if basis is not None else None,
            requirement_id=entry.get("requirement_id"),
        )
    except (KeyError, ValueError) as error:
        raise InvalidReviewResult(
            f"Malformed persisted question verification: {error}"
        ) from error
    is_confirmed = outcome is VerificationOutcome.CONFIRMED
    is_rejected = outcome is VerificationOutcome.REJECTED
    names_peer = verification.basis is RejectionBasis.ANSWERED_BY_OTHER_REQUIREMENT
    if (
        not isinstance(verification.question_index, int)
        or isinstance(verification.question_index, bool)
        or not isinstance(verification.reason, str)
        or not verification.reason.strip()
        or is_confirmed != isinstance(verification.material, bool)
        or (not is_confirmed and verification.material is not None)
        or is_rejected != (verification.basis is not None)
        or names_peer != (verification.requirement_id is not None)
    ):
        raise InvalidReviewResult(
            "A persisted question verification does not have the shape its "
            "outcome requires."
        )
    return verification


def _read_material_what(entry: object) -> MaterialWhat:
    if not isinstance(entry, dict) or set(entry) != {"detail"}:
        raise InvalidReviewResult("Each material unresolved WHAT must be an object.")
    detail = entry["detail"]
    if not isinstance(detail, str) or not detail.strip():
        raise InvalidReviewResult("A material unresolved WHAT has no detail.")
    return MaterialWhat(detail=detail)


def _read_reviewed_tree(
    payload: dict[str, object],
    version: str,
    requirement_id: str,
    reviewed_document: str,
) -> TreeManifest | None:
    """The tree binding of a 0.2 or 0.3 payload; none for 0.1, never synthesized.

    The manifest version must be the one the Result version declares; a
    mixture is a contradiction, not a best-effort read.
    """
    if version == LEGACY_REVIEW_RESULT_VERSION:
        if REVIEWED_TREE_KEY in payload:
            raise InvalidReviewResult(
                "A 0.1 Review Result cannot carry a normative tree binding."
            )
        return None
    try:
        tree = TreeManifest.from_payload(payload.get(REVIEWED_TREE_KEY))
    except InvalidTreeManifest as error:
        raise InvalidReviewResult(f"Invalid normative tree binding: {error}") from error
    expected_manifest = MANIFEST_VERSION_BY_RESULT_VERSION[version]
    if tree.version != expected_manifest:
        raise InvalidReviewResult(
            f"A Review Result {version} binds manifest version {expected_manifest}, "
            f"but {REVIEWED_TREE_KEY} is version {tree.version}; the payload mixes "
            "fingerprint algorithms."
        )
    if tree.requirement_id != requirement_id:
        raise InvalidReviewResult(
            f"{REVIEWED_TREE_KEY} belongs to {tree.requirement_id!r}, not "
            f"{requirement_id!r}."
        )
    if tree.root_entry.content_fingerprint != reviewed_document:
        raise InvalidReviewResult(
            f"{REVIEWED_TREE_KEY}'s Root entry disagrees with "
            f"{DOCUMENT_FINGERPRINT_KEY}."
        )
    return tree


def read_confirmed_relation_mirror(text: str) -> tuple[tuple[RelationKind, str], ...]:
    """The persisted `confirmed_relation_proposals`, as logical edges.

    `parse_review_result` derives the confirmed set from the verifications and
    deliberately ignores this mirror. Apply, the first normative consumer, must
    check that the two agree, so the mirror is exposed here beside the parser
    rather than re-extracted by a second reader of the artifact.
    """
    payload = _read_payload(text)
    edges = []
    for entry in _as_list(payload.get(CONFIRMED_RELATIONS_KEY)):
        verification = _read_relation_verification(entry)
        if verification.outcome is not VerificationOutcome.CONFIRMED:
            raise InvalidReviewResult(
                f"confirmed_relation_proposals carries a {verification.outcome.value} "
                f"entry for {verification.kind.value} {verification.requirement_id}."
            )
        edges.append((verification.kind, verification.requirement_id))
    return tuple(edges)


def _read_payload(text: str) -> dict[str, object]:
    match = JSON_FENCE.search(text or "")
    if match is None:
        raise InvalidReviewResult(
            "The Review Result document contains no JSON payload."
        )
    try:
        payload = json.loads(match.group("body"))
    except ValueError as error:
        raise InvalidReviewResult(
            f"The Review Result payload is not valid JSON: {error}"
        ) from error
    if not isinstance(payload, dict):
        raise InvalidReviewResult("The Review Result payload must be an object.")
    return payload


def _as_list(value: object) -> list[object]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise InvalidReviewResult("A Review Result collection must be a list.")
    return value


def _require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidReviewResult(f"The Review Result has no {field}.")
    return value


def _require_iteration(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < FIRST_ITERATION:
        raise InvalidReviewResult(
            f"Review Result {field} {value!r} is not a positive integer."
        )
    return value


def _read_verdict(value: object) -> ReviewVerdict:
    try:
        return ReviewVerdict(value)
    except ValueError as error:
        raise InvalidReviewResult(f"Unknown persisted verdict {value!r}.") from error


def _read_finding_verification(entry: object) -> FindingVerification:
    if not isinstance(entry, dict):
        raise InvalidReviewResult("Each finding verification must be an object.")
    try:
        outcome = VerificationOutcome(entry["outcome"])
        severity = entry.get("severity")
        verification = FindingVerification(
            process_finding_index=entry["process_finding_index"],
            outcome=outcome,
            reason=entry["reason"],
            severity=ReviewSeverity(severity) if severity is not None else None,
        )
    except (KeyError, ValueError) as error:
        raise InvalidReviewResult(
            f"Malformed persisted finding verification: {error}"
        ) from error
    if (verification.outcome is VerificationOutcome.CONFIRMED) != (
        verification.severity is not None
    ):
        raise InvalidReviewResult(
            "A persisted finding verification carries a severity if and only if "
            "it confirms the finding."
        )
    return verification


def _read_relation_verification(entry: object) -> RelationVerification:
    if not isinstance(entry, dict):
        raise InvalidReviewResult("Each relation verification must be an object.")
    try:
        return RelationVerification(
            kind=RelationKind(entry["kind"]),
            requirement_id=entry["requirement_id"],
            outcome=VerificationOutcome(entry["outcome"]),
            reason=entry["reason"],
        )
    except (KeyError, ValueError) as error:
        raise InvalidReviewResult(
            f"Malformed persisted relation verification: {error}"
        ) from error


def _read_new_finding(entry: object) -> NewFinding:
    if not isinstance(entry, dict):
        raise InvalidReviewResult("Each new finding must be an object.")
    try:
        return NewFinding(
            kind=FindingKind(entry["kind"]),
            severity=ReviewSeverity(entry["severity"]),
            detail=entry["detail"],
            requirement_id=entry.get("requirement_id"),
        )
    except (KeyError, ValueError) as error:
        raise InvalidReviewResult(
            f"Malformed persisted new finding: {error}"
        ) from error
