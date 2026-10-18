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
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from sdlc.normative_tree import (
    LEGACY_NORMATIVE_TREE_VERSION,
    NORMATIVE_TREE_VERSION,
    InvalidTreeManifest,
    TreeManifest,
)
from sdlc.process_result import ProcessResult
from sdlc.standard_analysis import FindingKind, ProductQuestion, RelationKind
from sdlc.standard_review import (
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
    VerificationOutcome,
    WhatStatus,
    derive_verdict,
    derive_what_status,
    question_blocks,
)

# 0.2 binds the normative tree (Requirement-Normative-Tree-Binding-v0.1); 0.1
# is the legacy Root-only binding, still readable as history, never written.
# 0.3 binds manifest v2 (exact canonical-byte fingerprints, audit A8); 0.2
# bound manifest v1 under the older algorithm; 0.1 is Root-only. Older
# versions are history: readable, never written, never reinterpreted.
# 0.4 is 0.3 plus the verified product questions and the derived WHAT status
# of the Material-WHAT Gate v0.1. A 0.3 Review Result stays current tree
# evidence but establishes no WHAT status: it is never read as CLEAR.
REVIEW_RESULT_VERSION = "0.4"
PRE_WHAT_REVIEW_RESULT_VERSION = "0.3"
TREE_BOUND_LEGACY_REVIEW_RESULT_VERSION = "0.2"
LEGACY_REVIEW_RESULT_VERSION = "0.1"
SUPPORTED_REVIEW_RESULT_VERSIONS = frozenset(
    {
        REVIEW_RESULT_VERSION,
        PRE_WHAT_REVIEW_RESULT_VERSION,
        TREE_BOUND_LEGACY_REVIEW_RESULT_VERSION,
        LEGACY_REVIEW_RESULT_VERSION,
    }
)
CURRENT_TREE_REVIEW_RESULT_VERSIONS = frozenset(
    {REVIEW_RESULT_VERSION, PRE_WHAT_REVIEW_RESULT_VERSION}
)
MANIFEST_VERSION_BY_RESULT_VERSION = {
    TREE_BOUND_LEGACY_REVIEW_RESULT_VERSION: LEGACY_NORMATIVE_TREE_VERSION,
    PRE_WHAT_REVIEW_RESULT_VERSION: NORMATIVE_TREE_VERSION,
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


class InvalidReviewResult(ValueError):
    """A persisted Review Result cannot be trusted."""


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
    # 0.4 only; None on every older version, which establishes no WHAT status.
    reviewed_product_questions: tuple[ProductQuestion, ...] | None = None
    question_verifications: tuple[QuestionVerification, ...] = ()
    material_unresolved_what: tuple[MaterialWhat, ...] = ()
    what_status: WhatStatus | None = None

    @property
    def name(self) -> str:
        return review_result_name(self.requirement_id, self.iteration)

    @property
    def is_tree_bound(self) -> bool:
        return self.reviewed_tree is not None

    @property
    def is_current(self) -> bool:
        """0.3 or 0.4 with a manifest v2 tree: current tree evidence.

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
) -> ReviewResult:
    """Assemble the artifact, deriving verdict and WHAT status, never accepting.

    `reviewed_product_questions` are the bound Process Result's questions, the
    ones the review verified.
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
    return ReviewResult(
        requirement_id=requirement_id,
        iteration=iteration,
        reviewed_document_fingerprint=reviewed_document_fingerprint,
        reviewed_process_iteration=reviewed_process_iteration,
        reviewed_process_output_fingerprint=reviewed_process_output_fingerprint,
        verdict=derive_verdict(review.finding_verifications, review.new_findings),
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
        ),
    )


def _derive_what_status(
    questions: tuple[ProductQuestion, ...],
    verifications: tuple[QuestionVerification, ...],
    material: tuple[MaterialWhat, ...],
) -> WhatStatus:
    try:
        return derive_what_status(questions, verifications, material)
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
        **(_what_payload(result) if result.version == REVIEW_RESULT_VERSION else {}),
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
            f"A Review Result {REVIEW_RESULT_VERSION} must carry its WHAT evidence."
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

    verdict = _read_verdict(payload.get(VERDICT_KEY))
    recalculated = derive_verdict(verifications, new_findings)
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
    what = _read_what_evidence(payload, version)
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
        relation_verifications=tuple(
            _read_relation_verification(entry)
            for entry in _as_list(payload.get(RELATION_VERIFICATIONS_KEY))
        ),
        new_findings=new_findings,
        assessment=dict(payload.get(ASSESSMENT_KEY) or {}),
        version=version,
        reviewed_tree=reviewed_tree,
        **what,
    )


def _read_what_evidence(payload: dict[str, object], version: str) -> dict:
    """The 0.4 WHAT evidence, its status recomputed; none for older versions."""
    if version != REVIEW_RESULT_VERSION:
        present = [key for key in WHAT_KEYS if key in payload]
        if present:
            raise InvalidReviewResult(
                f"A {version} Review Result cannot carry WHAT evidence: "
                + ", ".join(present)
            )
        return {}
    missing = [key for key in WHAT_KEYS if key not in payload]
    if missing:
        raise InvalidReviewResult(
            f"A {REVIEW_RESULT_VERSION} Review Result is missing its WHAT evidence: "
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
    recalculated = _derive_what_status(questions, verifications, material)
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
    return review.what_status


def open_material_questions(review: ReviewResult) -> tuple[str, ...]:
    """The material WHAT questions a 0.4 Review Result leaves open, for humans."""
    questions = review.reviewed_product_questions or ()
    by_index = {item.question_index: item for item in review.question_verifications}
    open_questions = [
        question.detail
        for index, question in enumerate(questions)
        if index in by_index and question_blocks(question, by_index[index])
    ]
    return (
        *open_questions,
        *(item.detail for item in review.material_unresolved_what),
    )


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
