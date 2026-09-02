"""Structured contract for independent Standard Requirement review.

The reviewer returns data only: a verification of every claim the Process
Result made, any finding Process missed, and a concise assessment. It never
writes to Fibery, never names a Fibery identifier, and is never asked for
reasoning traces.

Two properties matter more than the rest and are enforced here rather than
trusted:

- **the model cannot state a verdict.** There is no verdict field in the
  contract, so `derive_verdict` is the only thing that produces one and a
  response cannot claim PASS while listing a blocking finding;
- **every Process claim is accounted for exactly once.** Silently dropping an
  inconvenient finding would let review appear complete while verifying less
  than it was given.

Anything the contract does not define is a validation error, which is what
keeps chain-of-thought and invented mutation instructions out: no key outside
the closed sets below is accepted at any level, and every vocabulary is a
closed enum, so `operation`, `UPDATE`, `RETIRE`, `SUPERSEDE` and `APPLY` have
nowhere to appear.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum

from sdlc.standard_analysis import (
    REQUIREMENT_ID_PATTERN,
    Finding,
    FindingKind,
    ProposedRelation,
    RelationKind,
)


class ReviewSeverity(StrEnum):
    """How serious the reviewer considers one finding.

    Supplied per finding, never for the Requirement as a whole: the overall
    verdict is derived from these by `derive_verdict`.
    """

    INFO = "INFO"
    WARNING = "WARNING"
    BLOCKING = "BLOCKING"


class VerificationOutcome(StrEnum):
    """The reviewer's independent conclusion about one Process claim."""

    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    UNRESOLVED = "UNRESOLVED"


class ReviewVerdict(StrEnum):
    """The overall quality verdict. Derived by code, never authored."""

    PASS = "PASS"
    NEEDS_WORK = "NEEDS_WORK"
    BLOCKING = "BLOCKING"


class InvalidReviewOutput(ValueError):
    """The reviewer's response does not satisfy the contract."""


ASSESSMENT_KEYS = frozenset(
    {
        "clarity",
        "completeness",
        "atomicity",
        "testability",
        "internal_consistency",
        "acceptance_criteria",
    }
)
FINDING_VERIFICATION_KEYS = frozenset(
    {"process_finding_index", "outcome", "severity", "reason"}
)
RELATION_VERIFICATION_KEYS = frozenset({"kind", "requirement_id", "outcome", "reason"})
NEW_FINDING_KEYS = frozenset({"kind", "severity", "requirement_id", "detail"})
REVIEW_KEYS = frozenset(
    {
        "finding_verifications",
        "relation_verifications",
        "new_findings",
        "assessment",
    }
)


@dataclass(frozen=True)
class FindingVerification:
    """The reviewer's conclusion about one Process finding.

    `severity` is present exactly when the outcome is CONFIRMED: confirming a
    finding is asserting a real defect, and the verdict needs to know how
    serious it is. Rejecting or failing to resolve one asserts no defect, so
    grading it would be meaningless.
    """

    process_finding_index: int
    outcome: VerificationOutcome
    reason: str
    severity: ReviewSeverity | None = None


@dataclass(frozen=True)
class RelationVerification:
    """The reviewer's conclusion about one proposed relation.

    Confirming a proposal does not write it. Nothing in this capability does.
    """

    kind: RelationKind
    requirement_id: str
    outcome: VerificationOutcome
    reason: str


@dataclass(frozen=True)
class NewFinding:
    """Something the reviewer found that Process did not report."""

    kind: FindingKind
    severity: ReviewSeverity
    detail: str
    requirement_id: str | None = None


@dataclass(frozen=True)
class ReviewOutput:
    """One validated review response."""

    finding_verifications: tuple[FindingVerification, ...]
    relation_verifications: tuple[RelationVerification, ...]
    new_findings: tuple[NewFinding, ...]
    assessment: dict[str, str]

    @property
    def confirmed_relations(self) -> tuple[RelationVerification, ...]:
        """The proposals a future Apply may write, once a human approves."""
        return tuple(
            verification
            for verification in self.relation_verifications
            if verification.outcome is VerificationOutcome.CONFIRMED
        )


def derive_verdict(
    finding_verifications: tuple[FindingVerification, ...],
    new_findings: tuple[NewFinding, ...],
) -> ReviewVerdict:
    """Derive the overall verdict from the severities of asserted defects.

    The reviewer never supplies this. It is computed from every finding the
    reviewer asserts is real: a confirmed Process finding and a newly
    discovered one count the same.

    REJECTED contributes nothing because the reviewer is asserting there is no
    defect. UNRESOLVED contributes nothing either: it is an admission of
    uncertainty rather than a defect claim, and letting uncertainty downgrade
    every Requirement would make the verdict meaningless. Unresolved items stay
    fully visible in the Review Result for the human at Ready.
    """
    severities = {
        verification.severity
        for verification in finding_verifications
        if verification.outcome is VerificationOutcome.CONFIRMED
    } | {finding.severity for finding in new_findings}
    if ReviewSeverity.BLOCKING in severities:
        return ReviewVerdict.BLOCKING
    if ReviewSeverity.WARNING in severities:
        return ReviewVerdict.NEEDS_WORK
    return ReviewVerdict.PASS


def parse_review_output(
    text: str,
    process_findings: tuple[Finding, ...],
    proposed_relations: tuple[ProposedRelation, ...],
) -> ReviewOutput:
    """Validate the reviewer's JSON response against the Process claims.

    The Process Result is needed here, not merely afterwards: a verification
    only means something in relation to the specific claim it addresses, so
    coverage is part of the contract rather than a later check.
    """
    payload = _load_json(text)
    _reject_unknown(payload, REVIEW_KEYS, "review")

    verifications = tuple(
        _read_finding_verification(entry, index, len(process_findings))
        for index, entry in enumerate(
            _as_list(payload.get("finding_verifications"), "finding_verifications")
        )
    )
    _require_exact_coverage(
        addressed=[item.process_finding_index for item in verifications],
        expected=list(range(len(process_findings))),
        describe=lambda index: f"Process finding {index}",
    )

    relations = tuple(
        _read_relation_verification(entry, index)
        for index, entry in enumerate(
            _as_list(payload.get("relation_verifications"), "relation_verifications")
        )
    )
    _require_exact_coverage(
        addressed=[(item.kind, item.requirement_id) for item in relations],
        # A relation is identified by its edge, so a Process Result that
        # proposed the same edge twice is still one thing to verify.
        expected=sorted(
            {
                (relation.kind, relation.requirement_id)
                for relation in proposed_relations
            }
        ),
        describe=lambda key: f"proposed relation {key[0].value} {key[1]}",
    )

    return ReviewOutput(
        finding_verifications=verifications,
        relation_verifications=relations,
        new_findings=tuple(
            _read_new_finding(entry, index)
            for index, entry in enumerate(
                _as_list(payload.get("new_findings"), "new_findings")
            )
        ),
        assessment=_read_assessment(payload.get("assessment")),
    )


def _require_exact_coverage(addressed: list, expected: list, describe) -> None:
    """Every claim addressed exactly once: none dropped, none invented."""
    seen: set = set()
    for key in addressed:
        if key in seen:
            raise InvalidReviewOutput(f"{describe(key)} is verified more than once.")
        seen.add(key)
    unknown = [key for key in addressed if key not in expected]
    if unknown:
        raise InvalidReviewOutput(
            "The review verifies something the Process Result did not claim: "
            + ", ".join(describe(key) for key in unknown)
        )
    missing = [key for key in expected if key not in seen]
    if missing:
        raise InvalidReviewOutput(
            "The review leaves a Process claim unverified: "
            + ", ".join(describe(key) for key in missing)
        )


def _read_finding_verification(
    entry: object, index: int, finding_count: int
) -> FindingVerification:
    where = f"finding verification {index}"
    if not isinstance(entry, dict):
        raise InvalidReviewOutput(f"{where} must be an object.")
    _reject_unknown(entry, FINDING_VERIFICATION_KEYS, where)
    missing = sorted({"process_finding_index", "outcome", "reason"} - set(entry))
    if missing:
        raise InvalidReviewOutput(f"{where} is missing: " + ", ".join(missing))

    target = entry["process_finding_index"]
    if not isinstance(target, int) or isinstance(target, bool):
        raise InvalidReviewOutput(
            f"{where} has process_finding_index {target!r}, which is not an integer."
        )
    if not 0 <= target < finding_count:
        raise InvalidReviewOutput(
            f"{where} addresses Process finding {target}, but the Process Result "
            f"has {finding_count}."
        )

    outcome = _read_enum(VerificationOutcome, entry["outcome"], where)
    severity = entry.get("severity")
    if outcome is VerificationOutcome.CONFIRMED:
        if severity is None:
            raise InvalidReviewOutput(
                f"{where} confirms a finding and must grade its severity."
            )
    elif severity is not None:
        raise InvalidReviewOutput(
            f"{where} is {outcome.value} and asserts no defect, so it must not "
            "carry a severity."
        )
    return FindingVerification(
        process_finding_index=target,
        outcome=outcome,
        reason=_read_text(entry["reason"], f"{where} reason"),
        severity=(
            _read_enum(ReviewSeverity, severity, where)
            if severity is not None
            else None
        ),
    )


def _read_relation_verification(entry: object, index: int) -> RelationVerification:
    where = f"relation verification {index}"
    if not isinstance(entry, dict):
        raise InvalidReviewOutput(f"{where} must be an object.")
    _reject_unknown(entry, RELATION_VERIFICATION_KEYS, where)
    missing = sorted(RELATION_VERIFICATION_KEYS - set(entry))
    if missing:
        raise InvalidReviewOutput(f"{where} is missing: " + ", ".join(missing))
    return RelationVerification(
        kind=_read_enum(RelationKind, entry["kind"], where),
        requirement_id=_read_requirement_id(entry["requirement_id"], where),
        outcome=_read_enum(VerificationOutcome, entry["outcome"], where),
        reason=_read_text(entry["reason"], f"{where} reason"),
    )


def _read_new_finding(entry: object, index: int) -> NewFinding:
    where = f"new finding {index}"
    if not isinstance(entry, dict):
        raise InvalidReviewOutput(f"{where} must be an object.")
    _reject_unknown(entry, NEW_FINDING_KEYS, where)
    missing = sorted({"kind", "severity", "detail"} - set(entry))
    if missing:
        raise InvalidReviewOutput(f"{where} is missing: " + ", ".join(missing))
    kind = _read_enum(FindingKind, entry["kind"], where)

    requirement_id = entry.get("requirement_id")
    if kind.is_about_another_requirement:
        if requirement_id is None:
            raise InvalidReviewOutput(
                f"{where} of kind {kind.value} must name the Requirement it is about."
            )
        requirement_id = _read_requirement_id(requirement_id, where)
    elif requirement_id is not None:
        raise InvalidReviewOutput(
            f"{where} of kind {kind.value} is about this Requirement and must not "
            "name another one."
        )
    return NewFinding(
        kind=kind,
        severity=_read_enum(ReviewSeverity, entry["severity"], where),
        detail=_read_text(entry["detail"], f"{where} detail"),
        requirement_id=requirement_id,
    )


def _read_assessment(value: object) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise InvalidReviewOutput("'assessment' must be an object.")
    _reject_unknown(value, ASSESSMENT_KEYS, "assessment")
    return {
        key: _read_text(item, f"assessment {key}")
        for key, item in value.items()
        if item is not None
    }


def _load_json(text: str) -> dict[str, object]:
    stripped = (text or "").strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        stripped = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
    try:
        payload = json.loads(stripped)
    except ValueError as error:
        raise InvalidReviewOutput(f"The response is not valid JSON: {error}") from error
    if not isinstance(payload, dict):
        raise InvalidReviewOutput("The response must be a JSON object.")
    return payload


def _as_list(value: object, where: str) -> list[object]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise InvalidReviewOutput(f"{where!r} must be a list.")
    return value


def _reject_unknown(
    payload: dict[str, object], allowed: frozenset[str], what: str
) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise InvalidReviewOutput(
            f"The {what} contains keys the contract does not define: "
            + ", ".join(unknown)
        )


def _read_text(value: object, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidReviewOutput(f"{where} must be a non-empty string.")
    return value.strip()


def _read_enum(enum: type[StrEnum], value: object, where: str) -> StrEnum:
    try:
        return enum(value)
    except ValueError as error:
        raise InvalidReviewOutput(
            f"{where} has {value!r}; expected one of "
            + ", ".join(member.value for member in enum)
        ) from error


def _read_requirement_id(value: object, where: str) -> str:
    text = _read_text(value, f"{where} requirement_id")
    if not REQUIREMENT_ID_PATTERN.match(text):
        raise InvalidReviewOutput(
            f"{where} names {text!r}, which is not a Requirement ID."
        )
    return text
