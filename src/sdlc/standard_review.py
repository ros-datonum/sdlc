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
  than it was given;
- **the model cannot state a WHAT status either.** `derive_what_status` is the
  only thing that says CLEAR or BLOCKED_ON_WHAT
  (Requirement-Material-WHAT-Gate-v0.1), and it is a separate axis from the
  quality verdict;
- **every rework response is verified exactly once**
  (Requirement-Rework-Brief-v0.1). A Process claim to have resolved or
  rebutted a material WHAT item clears nothing: only a CONFIRMED verification
  does, and an escalation stays a product question under the gate above.

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
    ProductQuestion,
    ProposedRelation,
    RelationKind,
    ReworkResponse,
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


class WhatStatus(StrEnum):
    """Whether a material product question about WHAT is still open.

    Derived by code from the verified questions, never authored, and
    independent of `ReviewVerdict`: a NEEDS_WORK Requirement may be CLEAR,
    and a PASS one may be BLOCKED_ON_WHAT.
    """

    CLEAR = "CLEAR"
    BLOCKED_ON_WHAT = "BLOCKED_ON_WHAT"


class RejectionBasis(StrEnum):
    """Why the reviewer holds that a Process product question is not open.

    ANSWERED_BY_OTHER_REQUIREMENT is recorded but never clears a material
    question: until dependency evidence is bound (a later work item), a peer's
    text is not proof that this Requirement's WHAT is settled.
    """

    ANSWERED_IN_THIS_REQUIREMENT = "ANSWERED_IN_THIS_REQUIREMENT"
    TECHNICAL_HOW = "TECHNICAL_HOW"
    ANSWERED_BY_OTHER_REQUIREMENT = "ANSWERED_BY_OTHER_REQUIREMENT"


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
QUESTION_VERIFICATION_KEYS = frozenset(
    {"question_index", "outcome", "material", "basis", "requirement_id", "reason"}
)
MATERIAL_WHAT_KEYS = frozenset({"detail"})
REWORK_VERIFICATION_KEYS = frozenset({"item", "outcome", "severity", "reason"})
REWORK_VERIFICATIONS_KEY = "rework_verifications"
REVIEW_KEYS = frozenset(
    {
        "finding_verifications",
        "relation_verifications",
        "new_findings",
        "assessment",
        "question_verifications",
        "material_unresolved_what",
        REWORK_VERIFICATIONS_KEY,
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
class QuestionVerification:
    """The reviewer's conclusion about one Process product question.

    CONFIRMED carries the reviewer's own `material` judgement and no basis.
    REJECTED carries a `basis`, and a `requirement_id` exactly when the basis
    is ANSWERED_BY_OTHER_REQUIREMENT. UNRESOLVED carries neither.
    """

    question_index: int
    outcome: VerificationOutcome
    reason: str
    material: bool | None = None
    basis: RejectionBasis | None = None
    requirement_id: str | None = None


@dataclass(frozen=True)
class MaterialWhat:
    """A material unresolved WHAT question the reviewer found itself."""

    detail: str


@dataclass(frozen=True)
class ReworkVerification:
    """The reviewer's conclusion about one Process rework response.

    CONFIRMED: the claimed resolution, rebuttal or escalation is correct.
    REJECTED: it is not, so a defect remains; it carries the severity of what
    remains, as a confirmed finding does. UNRESOLVED: the context cannot
    settle it, which asserts no defect and carries no severity.
    """

    item: str
    outcome: VerificationOutcome
    reason: str
    severity: ReviewSeverity | None = None


@dataclass(frozen=True)
class ReviewOutput:
    """One validated review response."""

    finding_verifications: tuple[FindingVerification, ...]
    relation_verifications: tuple[RelationVerification, ...]
    new_findings: tuple[NewFinding, ...]
    assessment: dict[str, str]
    question_verifications: tuple[QuestionVerification, ...] = ()
    material_unresolved_what: tuple[MaterialWhat, ...] = ()
    rework_verifications: tuple[ReworkVerification, ...] = ()

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
    rework_verifications: tuple[ReworkVerification, ...] = (),
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

    A rejected rework response asserts that a defect remains, so it counts
    with its own severity, exactly like a confirmed finding.
    """
    severities = (
        {
            verification.severity
            for verification in finding_verifications
            if verification.outcome is VerificationOutcome.CONFIRMED
        }
        | {finding.severity for finding in new_findings}
        | {
            verification.severity
            for verification in rework_verifications
            if verification.outcome is VerificationOutcome.REJECTED
        }
    )
    if ReviewSeverity.BLOCKING in severities:
        return ReviewVerdict.BLOCKING
    if ReviewSeverity.WARNING in severities:
        return ReviewVerdict.NEEDS_WORK
    return ReviewVerdict.PASS


def question_blocks(
    question: ProductQuestion, verification: QuestionVerification
) -> bool:
    """Whether one verified Process question leaves a material WHAT open.

    CONFIRMED follows the reviewer's own materiality judgement. A rejection as
    answered in this Requirement or as technical HOW clears it. A rejection
    that rests on another Requirement leaves the Process materiality claim
    standing. UNRESOLVED always blocks: the reviewer could not settle the
    question, and a Process claim alone never clears one.
    """
    if verification.outcome is VerificationOutcome.CONFIRMED:
        return bool(verification.material)
    if verification.outcome is VerificationOutcome.UNRESOLVED:
        return True
    if verification.basis is RejectionBasis.ANSWERED_BY_OTHER_REQUIREMENT:
        return question.material
    return False


def rework_leaves_what_open(
    what_refs: frozenset[str], rework_verifications: tuple[ReworkVerification, ...]
) -> bool:
    """Whether a material WHAT Brief item is not confirmed as settled.

    Resolving, rebutting or escalating a material WHAT item is a Process
    claim; only the independent reviewer's CONFIRMED clears the claim. A
    confirmed escalation still leaves its product question to the WI-1 gate.
    """
    return any(
        verification.item in what_refs
        and verification.outcome is not VerificationOutcome.CONFIRMED
        for verification in rework_verifications
    )


def derive_what_status(
    product_questions: tuple[ProductQuestion, ...],
    question_verifications: tuple[QuestionVerification, ...],
    material_unresolved_what: tuple[MaterialWhat, ...],
    rework_what_open: bool = False,
) -> WhatStatus:
    """CLEAR only when no material product question is left open.

    Requires exactly one verification per question; anything else is a
    contract violation the caller has already refused. `rework_what_open`
    is `rework_leaves_what_open` for the reviewed rework responses: it can
    only block, never clear.
    """
    by_index = {item.question_index: item for item in question_verifications}
    if sorted(by_index) != list(range(len(product_questions))) or len(by_index) != len(
        question_verifications
    ):
        raise InvalidReviewOutput(
            "Every product question must be verified exactly once before a WHAT "
            "status can be derived."
        )
    if (
        rework_what_open
        or material_unresolved_what
        or any(
            question_blocks(question, by_index[index])
            for index, question in enumerate(product_questions)
        )
    ):
        return WhatStatus.BLOCKED_ON_WHAT
    return WhatStatus.CLEAR


def parse_review_output(
    text: str,
    process_findings: tuple[Finding, ...],
    proposed_relations: tuple[ProposedRelation, ...],
    product_questions: tuple[ProductQuestion, ...],
    rework_responses: tuple[ReworkResponse, ...] | None = None,
) -> ReviewOutput:
    """Validate the reviewer's JSON response against the Process claims.

    The Process Result is needed here, not merely afterwards: a verification
    only means something in relation to the specific claim it addresses, so
    coverage is part of the contract rather than a later check.
    `rework_responses` are the Process rework claims, None when that Process
    received no Rework Brief.
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

    if "material_unresolved_what" not in payload:
        raise InvalidReviewOutput(
            "The review must state material_unresolved_what, even as an empty "
            "list: its absence is not an assertion that none were found."
        )
    questions = tuple(
        _read_question_verification(entry, index, len(product_questions))
        for index, entry in enumerate(
            _as_list(payload.get("question_verifications"), "question_verifications")
        )
    )
    _require_exact_coverage(
        addressed=[item.question_index for item in questions],
        expected=list(range(len(product_questions))),
        describe=lambda index: f"Process product question {index}",
    )

    return ReviewOutput(
        question_verifications=questions,
        material_unresolved_what=tuple(
            _read_material_what(entry, index)
            for index, entry in enumerate(
                _as_list(
                    payload.get("material_unresolved_what"), "material_unresolved_what"
                )
            )
        ),
        finding_verifications=verifications,
        relation_verifications=relations,
        new_findings=tuple(
            _read_new_finding(entry, index)
            for index, entry in enumerate(
                _as_list(payload.get("new_findings"), "new_findings")
            )
        ),
        assessment=_read_assessment(payload.get("assessment")),
        rework_verifications=_read_rework_verifications(payload, rework_responses),
    )


def _read_rework_verifications(
    payload: dict[str, object], rework_responses: tuple[ReworkResponse, ...] | None
) -> tuple[ReworkVerification, ...]:
    entries = payload.get(REWORK_VERIFICATIONS_KEY)
    if rework_responses is None:
        if entries:
            raise InvalidReviewOutput(
                "rework_verifications verifies rework responses, but the Process "
                "Result received no Rework Brief."
            )
        return ()
    if REWORK_VERIFICATIONS_KEY not in payload:
        raise InvalidReviewOutput(
            "The Process Result answered a Rework Brief, so rework_verifications "
            "must verify every response: its absence verifies none."
        )
    verifications = tuple(
        _read_rework_verification(entry, index)
        for index, entry in enumerate(_as_list(entries, REWORK_VERIFICATIONS_KEY))
    )
    _require_exact_coverage(
        addressed=[item.item for item in verifications],
        expected=[response.item for response in rework_responses],
        describe=lambda ref: f"rework response {ref}",
    )
    return verifications


def _read_rework_verification(entry: object, index: int) -> ReworkVerification:
    where = f"rework verification {index}"
    if not isinstance(entry, dict):
        raise InvalidReviewOutput(f"{where} must be an object.")
    _reject_unknown(entry, REWORK_VERIFICATION_KEYS, where)
    missing = sorted({"item", "outcome", "reason"} - set(entry))
    if missing:
        raise InvalidReviewOutput(f"{where} is missing: " + ", ".join(missing))
    outcome = _read_enum(VerificationOutcome, entry["outcome"], where)
    severity = entry.get("severity")
    if outcome is VerificationOutcome.REJECTED:
        if severity is None:
            raise InvalidReviewOutput(
                f"{where} rejects a rework response, so a defect remains and its "
                "severity must be graded."
            )
    elif severity is not None:
        raise InvalidReviewOutput(
            f"{where} is {outcome.value} and asserts no remaining defect, so it "
            "must not carry a severity."
        )
    return ReworkVerification(
        item=_read_text(entry["item"], f"{where} item"),
        outcome=outcome,
        reason=_read_text(entry["reason"], f"{where} reason"),
        severity=(
            _read_enum(ReviewSeverity, severity, where)
            if severity is not None
            else None
        ),
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


def _read_question_verification(
    entry: object, index: int, question_count: int
) -> QuestionVerification:
    where = f"question verification {index}"
    if not isinstance(entry, dict):
        raise InvalidReviewOutput(f"{where} must be an object.")
    _reject_unknown(entry, QUESTION_VERIFICATION_KEYS, where)
    missing = sorted({"question_index", "outcome", "reason"} - set(entry))
    if missing:
        raise InvalidReviewOutput(f"{where} is missing: " + ", ".join(missing))
    target = entry["question_index"]
    if not isinstance(target, int) or isinstance(target, bool):
        raise InvalidReviewOutput(
            f"{where} has question_index {target!r}, which is not an integer."
        )
    if not 0 <= target < question_count:
        raise InvalidReviewOutput(
            f"{where} addresses product question {target}, but the Process Result "
            f"has {question_count}."
        )
    outcome = _read_enum(VerificationOutcome, entry["outcome"], where)
    material = entry.get("material")
    basis = entry.get("basis")
    requirement_id = entry.get("requirement_id")
    if outcome is VerificationOutcome.CONFIRMED:
        if not isinstance(material, bool):
            raise InvalidReviewOutput(
                f"{where} confirms a question and must judge material as true or false."
            )
        if basis is not None or requirement_id is not None:
            raise InvalidReviewOutput(
                f"{where} confirms a question and must carry no basis or "
                "requirement_id."
            )
    elif material is not None:
        raise InvalidReviewOutput(
            f"{where} is {outcome.value}; only a CONFIRMED question carries material."
        )
    if outcome is VerificationOutcome.REJECTED:
        if basis is None:
            raise InvalidReviewOutput(f"{where} rejects a question and needs a basis.")
        basis = _read_enum(RejectionBasis, basis, where)
        if basis is RejectionBasis.ANSWERED_BY_OTHER_REQUIREMENT:
            if requirement_id is None:
                raise InvalidReviewOutput(
                    f"{where} rests on another Requirement and must name it."
                )
            requirement_id = _read_requirement_id(requirement_id, where)
        elif requirement_id is not None:
            raise InvalidReviewOutput(
                f"{where} with basis {basis.value} must not name a Requirement."
            )
    elif outcome is VerificationOutcome.UNRESOLVED and (
        basis is not None or requirement_id is not None
    ):
        raise InvalidReviewOutput(
            f"{where} is UNRESOLVED and must carry no basis or requirement_id."
        )
    return QuestionVerification(
        question_index=target,
        outcome=outcome,
        reason=_read_text(entry["reason"], f"{where} reason"),
        material=material,
        basis=basis,
        requirement_id=requirement_id,
    )


def _read_material_what(entry: object, index: int) -> MaterialWhat:
    where = f"material unresolved WHAT {index}"
    if not isinstance(entry, dict):
        raise InvalidReviewOutput(f"{where} must be an object.")
    _reject_unknown(entry, MATERIAL_WHAT_KEYS, where)
    if "detail" not in entry:
        raise InvalidReviewOutput(f"{where} is missing: detail")
    return MaterialWhat(detail=_read_text(entry["detail"], f"{where} detail"))


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
