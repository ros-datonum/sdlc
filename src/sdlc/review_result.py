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
own contents is rejected rather than acted on.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from sdlc.standard_analysis import FindingKind, RelationKind
from sdlc.standard_review import (
    FindingVerification,
    NewFinding,
    RelationVerification,
    ReviewOutput,
    ReviewSeverity,
    ReviewVerdict,
    VerificationOutcome,
    derive_verdict,
)

REVIEW_RESULT_VERSION = "0.1"
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
VERDICT_KEY = "derived_verdict"
FINDING_VERIFICATIONS_KEY = "process_finding_verifications"
RELATION_VERIFICATIONS_KEY = "relation_proposal_verifications"
CONFIRMED_RELATIONS_KEY = "confirmed_relation_proposals"
NEW_FINDINGS_KEY = "new_findings"
ASSESSMENT_KEY = "assessment"


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

    @property
    def name(self) -> str:
        return review_result_name(self.requirement_id, self.iteration)

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
) -> ReviewResult:
    """Assemble the artifact, deriving the verdict rather than accepting one."""
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
    )


def render_review_result(result: ReviewResult) -> str:
    """Render the artifact: a short human header plus the machine payload."""
    payload = {
        VERSION_KEY: result.version,
        ITERATION_KEY: result.iteration,
        REQUIREMENT_ID_KEY: result.requirement_id,
        DOCUMENT_FINGERPRINT_KEY: result.reviewed_document_fingerprint,
        PROCESS_ITERATION_KEY: result.reviewed_process_iteration,
        PROCESS_FINGERPRINT_KEY: result.reviewed_process_output_fingerprint,
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
    if version != REVIEW_RESULT_VERSION:
        raise InvalidReviewResult(
            f"Review Result version {version!r} is not supported; this reviewer "
            f"reads {REVIEW_RESULT_VERSION!r}."
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

    return ReviewResult(
        requirement_id=_require_text(payload.get(REQUIREMENT_ID_KEY), "requirement_id"),
        iteration=iteration,
        reviewed_document_fingerprint=_require_text(
            payload.get(DOCUMENT_FINGERPRINT_KEY), DOCUMENT_FINGERPRINT_KEY
        ),
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
    )


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
