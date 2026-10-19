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
- **every existing dependency is verified exactly once**
  (Requirement-Dependency-Bindings-v0.1): a DEPENDS_ON edge the Requirement
  already has is a claim about its normative meaning like any proposal;
- **every rework response is verified exactly once**
  (Requirement-Rework-Brief-v0.1). A Process claim to have resolved or
  rebutted a material WHAT item clears nothing: only a CONFIRMED verification
  does, and an escalation stays a product question under the gate above;
- **every autonomous resolution is verified exactly once, check by check**
  (Requirement-Autonomous-Resolution-v0.1 §6). The outcome must agree with
  the reviewer's own ten checks, so a resolution cannot be confirmed by
  assertion, and one that is not confirmed keeps WHAT blocked.

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
    Resolution,
    ResolutionClass,
    ReworkOutcome,
    ReworkResponse,
    SourceKind,
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

    ANSWERED_BY_OTHER_REQUIREMENT clears a material question only when the
    named Requirement is a verified, bound normative dependency of this one
    (Requirement-Dependency-Bindings-v0.1 section 8); a bare Requirement ID,
    an AFFECTS peer or a transitive dependency never does.
    """

    ANSWERED_IN_THIS_REQUIREMENT = "ANSWERED_IN_THIS_REQUIREMENT"
    TECHNICAL_HOW = "TECHNICAL_HOW"
    ANSWERED_BY_OTHER_REQUIREMENT = "ANSWERED_BY_OTHER_REQUIREMENT"


class CheckOutcome(StrEnum):
    """The reviewer's answer to one resolution check."""

    PASS = "PASS"
    FAIL = "FAIL"
    UNCERTAIN = "UNCERTAIN"
    # Only `within_policy_clause`, and only for a resolution that cites no
    # policy (SOURCE_GROUNDED, DEPENDENCY_GROUNDED).
    NOT_APPLICABLE = "NOT_APPLICABLE"


#: Autonomous Resolution v0.1 §6, A to J, in order.
RESOLUTION_CHECKS = (
    "issue_identified",
    "source_supports_answer",
    "authority_class_correct",
    "within_policy_clause",
    "consistent_with_raw",
    "consistent_with_related",
    "no_unsupported_obligation",
    "no_new_contradiction",
    "no_material_what_open",
    "testable_at_what_level",
)
POLICY_CHECK = "within_policy_clause"


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
DEPENDENCY_VERIFICATION_KEYS = frozenset(
    {"requirement_id", "outcome", "severity", "reason"}
)
DEPENDENCY_VERIFICATIONS_KEY = "dependency_verifications"
RESOLUTION_VERIFICATION_KEYS = frozenset(
    {"resolution_index", "outcome", "severity", "checks", "reason"}
)
RESOLUTION_VERIFICATIONS_KEY = "resolution_verifications"
REVIEW_KEYS = frozenset(
    {
        "finding_verifications",
        "relation_verifications",
        "new_findings",
        "assessment",
        "question_verifications",
        "material_unresolved_what",
        REWORK_VERIFICATIONS_KEY,
        DEPENDENCY_VERIFICATIONS_KEY,
        RESOLUTION_VERIFICATIONS_KEY,
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
class DependencyVerification:
    """The reviewer's conclusion about one DEPENDS_ON edge the Requirement has.

    CONFIRMED: understanding this Requirement needs what the target owns.
    REJECTED: it does not, so the edge is a false dependency; that is a
    defect and carries a severity. UNRESOLVED: the context cannot settle it.
    Only a CONFIRMED edge can answer a material question (section 8).
    """

    requirement_id: str
    outcome: VerificationOutcome
    reason: str
    severity: ReviewSeverity | None = None


@dataclass(frozen=True)
class ResolutionVerification:
    """The reviewer's conclusion about one Process resolution, check by check.

    `checks` holds an outcome for every name in RESOLUTION_CHECKS, in that
    order. CONFIRMED: every check passes. REJECTED: at least one fails, so
    a defect remains and carries a severity. UNRESOLVED: none fails and at
    least one is uncertain; no severity.
    """

    resolution_index: int
    outcome: VerificationOutcome
    checks: tuple[tuple[str, CheckOutcome], ...]
    reason: str
    severity: ReviewSeverity | None = None


def require_coherent_checks(
    verification: ResolutionVerification,
    resolution: Resolution,
    where: str,
    error: type[ValueError],
) -> None:
    """The outcome agrees with the checks; shared with the Review Result reader."""
    if tuple(name for name, _ in verification.checks) != RESOLUTION_CHECKS:
        raise error(
            f"{where} must answer exactly these checks, in order: "
            + ", ".join(RESOLUTION_CHECKS)
        )
    checks = dict(verification.checks)
    cites_policy = resolution.resolution_class is ResolutionClass.DELEGATED_DEFAULT
    if (checks[POLICY_CHECK] is CheckOutcome.NOT_APPLICABLE) == cites_policy:
        raise error(
            f"{where}: {POLICY_CHECK} is NOT_APPLICABLE exactly when the "
            "resolution cites no policy clause."
        )
    if any(
        outcome is CheckOutcome.NOT_APPLICABLE
        for name, outcome in verification.checks
        if name != POLICY_CHECK
    ):
        raise error(f"{where}: only {POLICY_CHECK} may be NOT_APPLICABLE.")
    outcomes = set(checks.values()) - {CheckOutcome.NOT_APPLICABLE}
    expected = (
        VerificationOutcome.REJECTED
        if CheckOutcome.FAIL in outcomes
        else VerificationOutcome.UNRESOLVED
        if CheckOutcome.UNCERTAIN in outcomes
        else VerificationOutcome.CONFIRMED
    )
    if verification.outcome is not expected:
        raise error(
            f"{where} is {verification.outcome.value}, but its checks derive "
            f"{expected.value}: a confirmation needs every check to pass."
        )
    if (verification.outcome is VerificationOutcome.REJECTED) != (
        verification.severity is not None
    ):
        raise error(
            f"{where} carries a severity if and only if it rejects the resolution."
        )


def resolutions_leave_what_open(
    resolutions: tuple[Resolution, ...],
    verifications: tuple[ResolutionVerification, ...],
    verified_dependencies: frozenset[str] = frozenset(),
) -> bool:
    """Whether a resolution fails to settle the product question it answered.

    Only CONFIRMED stops a resolution from blocking. A confirmed
    DEPENDENCY_GROUNDED resolution also needs every dependency it cites to be
    a verified, bound direct DEPENDS_ON of this review (Dependency Bindings
    v0.1 §8): an AFFECTS peer, an unbindable proposal or a transitive
    dependency is not authority here.
    """
    by_index = {item.resolution_index: item for item in verifications}
    for index, resolution in enumerate(resolutions):
        verification = by_index.get(index)
        if (
            verification is None
            or verification.outcome is not VerificationOutcome.CONFIRMED
        ):
            return True
        if (
            resolution.resolution_class is ResolutionClass.DEPENDENCY_GROUNDED
            and not {
                source.requirement_id
                for source in resolution.sources
                if source.kind is SourceKind.DEPENDENCY
            }
            <= verified_dependencies
        ):
            return True
    return False


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
    dependency_verifications: tuple[DependencyVerification, ...] = ()
    resolution_verifications: tuple[ResolutionVerification, ...] = ()

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
    dependency_verifications: tuple[DependencyVerification, ...] = (),
    resolution_verifications: tuple[ResolutionVerification, ...] = (),
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

    A rejected rework response asserts that a defect remains, a rejected
    existing dependency asserts a false dependency, and a rejected resolution
    asserts an unsupported or unauthorized product decision, so each counts
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
            for verification in (
                *rework_verifications,
                *dependency_verifications,
                *resolution_verifications,
            )
            if verification.outcome is VerificationOutcome.REJECTED
        }
    )
    if ReviewSeverity.BLOCKING in severities:
        return ReviewVerdict.BLOCKING
    if ReviewSeverity.WARNING in severities:
        return ReviewVerdict.NEEDS_WORK
    return ReviewVerdict.PASS


def question_blocks(
    question: ProductQuestion,
    verification: QuestionVerification,
    verified_dependencies: frozenset[str] = frozenset(),
) -> bool:
    """Whether one verified Process question leaves a material WHAT open.

    CONFIRMED follows the reviewer's own materiality judgement. A rejection as
    answered in this Requirement or as technical HOW clears it. A rejection
    that rests on another Requirement clears it only when that Requirement is
    one of `verified_dependencies`: a direct DEPENDS_ON target the review
    verified and bound to its exact normative version. Otherwise the Process
    materiality claim stands. UNRESOLVED always blocks: the reviewer could not
    settle the question, and a Process claim alone never clears one.
    """
    if verification.outcome is VerificationOutcome.CONFIRMED:
        return bool(verification.material)
    if verification.outcome is VerificationOutcome.UNRESOLVED:
        return True
    if verification.basis is RejectionBasis.ANSWERED_BY_OTHER_REQUIREMENT:
        return question.material and (
            verification.requirement_id not in verified_dependencies
        )
    return False


def rework_leaves_what_open(
    what_refs: frozenset[str],
    escalated_refs: frozenset[str],
    rework_verifications: tuple[ReworkVerification, ...],
) -> bool:
    """Whether a material WHAT Brief item is not settled by consistent evidence.

    Resolving or rebutting a material WHAT item is a Process claim that only
    the independent reviewer's CONFIRMED can make good. Escalating one says it
    stays open, so it never clears, whatever the reviewer concludes: a
    confirmed escalation agrees that it is open, and a rejected or unresolved
    one leaves a defect or doubt.
    """
    return bool(what_refs & escalated_refs) or any(
        verification.item in what_refs
        and verification.outcome is not VerificationOutcome.CONFIRMED
        for verification in rework_verifications
    )


def verified_dependencies(
    relation_verifications: tuple[RelationVerification, ...],
    dependency_verifications: tuple[DependencyVerification, ...],
) -> frozenset[str]:
    """The direct DEPENDS_ON targets this review verified as necessary.

    A confirmed existing edge or a confirmed proposal; never an AFFECTS edge,
    a rejected or unresolved one, or a transitive dependency. A proposal that
    repeats an existing edge decides nothing: that edge's own verification
    does, so a rejected edge cannot be cleared again as a proposal. Binding
    them to their exact normative versions is the reviewer stage's job, and
    only a bound one is admitted (Requirement-Dependency-Bindings-v0.1 §6).
    """
    existing = {item.requirement_id for item in dependency_verifications}
    return frozenset(
        item.requirement_id
        for item in dependency_verifications
        if item.outcome is VerificationOutcome.CONFIRMED
    ) | frozenset(
        item.requirement_id
        for item in relation_verifications
        if item.kind is RelationKind.DEPENDS_ON
        and item.outcome is VerificationOutcome.CONFIRMED
        and item.requirement_id not in existing
    )


def contradictory_escalations(
    product_questions: tuple[ProductQuestion, ...],
    question_verifications: tuple[QuestionVerification, ...],
    escalations: tuple[tuple[str, int], ...],
    rework_verifications: tuple[ReworkVerification, ...],
    verified_dependencies: frozenset[str] = frozenset(),
) -> tuple[str, ...]:
    """Material WHAT escalations the reviewer both confirmed and contradicted.

    `escalations` are (item, product_question_index) of the ESCALATED
    responses to material WHAT items. CONFIRMED asserts the WHAT is still
    open, so the reviewer's own verification of the named question must
    leave it open too (`question_blocks`); rejecting it as answered or as
    technical HOW, or judging it immaterial, says the opposite. One review
    cannot assert both.
    """
    confirmed = {
        verification.item
        for verification in rework_verifications
        if verification.outcome is VerificationOutcome.CONFIRMED
    }
    by_index = {item.question_index: item for item in question_verifications}
    return tuple(
        item
        for item, index in escalations
        if item in confirmed
        and index in by_index
        and index < len(product_questions)
        and not question_blocks(
            product_questions[index], by_index[index], verified_dependencies
        )
    )


def derive_what_status(
    product_questions: tuple[ProductQuestion, ...],
    question_verifications: tuple[QuestionVerification, ...],
    material_unresolved_what: tuple[MaterialWhat, ...],
    rework_what_open: bool = False,
    verified_dependencies: frozenset[str] = frozenset(),
    resolution_what_open: bool = False,
) -> WhatStatus:
    """CLEAR only when no material product question is left open.

    Requires exactly one verification per question; anything else is a
    contract violation the caller has already refused. `rework_what_open`
    is `rework_leaves_what_open` for the reviewed rework responses and
    `resolution_what_open` is `resolutions_leave_what_open`: either can only
    block, never clear.
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
        or resolution_what_open
        or material_unresolved_what
        or any(
            question_blocks(question, by_index[index], verified_dependencies)
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
    rework_what_refs: frozenset[str] = frozenset(),
    existing_dependencies: tuple[str, ...] = (),
    resolutions: tuple[Resolution, ...] | None = None,
) -> ReviewOutput:
    """Validate the reviewer's JSON response against the Process claims.

    The Process Result is needed here, not merely afterwards: a verification
    only means something in relation to the specific claim it addresses, so
    coverage is part of the contract rather than a later check.
    `rework_responses` are the Process rework claims, None when that Process
    received no Rework Brief; `rework_what_refs` the Brief items among them
    that are material WHAT questions. `existing_dependencies` are the DEPENDS_ON
    targets the Requirement already has, each verified exactly once.
    `resolutions` are the Process resolutions, each verified exactly once;
    None for a Process Result that predates them, which none may verify.
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

    rework = _read_rework_verifications(payload, rework_responses)
    dependencies = _read_dependency_verifications(payload, existing_dependencies)
    resolution_verifications = _read_resolution_verifications(payload, resolutions)
    contradicted = contradictory_escalations(
        product_questions,
        questions,
        material_escalations(rework_responses or (), rework_what_refs),
        rework,
        verified_dependencies(relations, dependencies),
    )
    if contradicted:
        raise InvalidReviewOutput(
            "The review confirms that a material WHAT stays open and, in its "
            "verification of the product question that keeps it open, that it "
            "does not: " + ", ".join(contradicted)
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
        rework_verifications=rework,
        dependency_verifications=dependencies,
        resolution_verifications=resolution_verifications,
    )


def _read_resolution_verifications(
    payload: dict[str, object], resolutions: tuple[Resolution, ...] | None
) -> tuple[ResolutionVerification, ...]:
    entries = payload.get(RESOLUTION_VERIFICATIONS_KEY)
    if resolutions is None:
        if entries:
            raise InvalidReviewOutput(
                "resolution_verifications verifies resolutions, but the Process "
                "Result predates them."
            )
        return ()
    if resolutions and RESOLUTION_VERIFICATIONS_KEY not in payload:
        raise InvalidReviewOutput(
            "The Process Result resolved product questions itself, so "
            "resolution_verifications must verify each: its absence verifies none."
        )
    verifications = tuple(
        _read_resolution_verification(entry, index, resolutions)
        for index, entry in enumerate(_as_list(entries, RESOLUTION_VERIFICATIONS_KEY))
    )
    _require_exact_coverage(
        addressed=[item.resolution_index for item in verifications],
        expected=list(range(len(resolutions))),
        describe=lambda index: f"Process resolution {index}",
    )
    return verifications


def _read_resolution_verification(
    entry: object, index: int, resolutions: tuple[Resolution, ...]
) -> ResolutionVerification:
    where = f"resolution verification {index}"
    if not isinstance(entry, dict):
        raise InvalidReviewOutput(f"{where} must be an object.")
    _reject_unknown(entry, RESOLUTION_VERIFICATION_KEYS, where)
    missing = sorted({"resolution_index", "outcome", "checks", "reason"} - set(entry))
    if missing:
        raise InvalidReviewOutput(f"{where} is missing: " + ", ".join(missing))
    target = entry["resolution_index"]
    if not isinstance(target, int) or isinstance(target, bool):
        raise InvalidReviewOutput(
            f"{where} has resolution_index {target!r}, which is not an integer."
        )
    if not 0 <= target < len(resolutions):
        raise InvalidReviewOutput(
            f"{where} addresses resolution {target}, but the Process Result has "
            f"{len(resolutions)}."
        )
    checks = entry["checks"]
    if not isinstance(checks, dict) or set(checks) != set(RESOLUTION_CHECKS):
        raise InvalidReviewOutput(
            f"{where} checks must answer exactly: " + ", ".join(RESOLUTION_CHECKS)
        )
    severity = entry.get("severity")
    verification = ResolutionVerification(
        resolution_index=target,
        outcome=_read_enum(VerificationOutcome, entry["outcome"], where),
        checks=tuple(
            (name, _read_enum(CheckOutcome, checks[name], f"{where} check {name}"))
            for name in RESOLUTION_CHECKS
        ),
        reason=_read_text(entry["reason"], f"{where} reason"),
        severity=(
            _read_enum(ReviewSeverity, severity, where)
            if severity is not None
            else None
        ),
    )
    require_coherent_checks(
        verification, resolutions[target], where, InvalidReviewOutput
    )
    return verification


def _read_dependency_verifications(
    payload: dict[str, object], existing: tuple[str, ...]
) -> tuple[DependencyVerification, ...]:
    entries = payload.get(DEPENDENCY_VERIFICATIONS_KEY)
    if existing and DEPENDENCY_VERIFICATIONS_KEY not in payload:
        raise InvalidReviewOutput(
            "The Requirement already has DEPENDS_ON edges, so "
            "dependency_verifications must verify each: its absence verifies none."
        )
    verifications = tuple(
        _read_dependency_verification(entry, index)
        for index, entry in enumerate(_as_list(entries, DEPENDENCY_VERIFICATIONS_KEY))
    )
    _require_exact_coverage(
        addressed=[item.requirement_id for item in verifications],
        expected=list(existing),
        describe=lambda target: f"existing dependency DEPENDS_ON {target}",
    )
    return verifications


def _read_dependency_verification(entry: object, index: int) -> DependencyVerification:
    where = f"dependency verification {index}"
    if not isinstance(entry, dict):
        raise InvalidReviewOutput(f"{where} must be an object.")
    _reject_unknown(entry, DEPENDENCY_VERIFICATION_KEYS, where)
    missing = sorted({"requirement_id", "outcome", "reason"} - set(entry))
    if missing:
        raise InvalidReviewOutput(f"{where} is missing: " + ", ".join(missing))
    outcome = _read_enum(VerificationOutcome, entry["outcome"], where)
    severity = entry.get("severity")
    if (outcome is VerificationOutcome.REJECTED) != (severity is not None):
        raise InvalidReviewOutput(
            f"{where} carries a severity if and only if it rejects the dependency."
        )
    return DependencyVerification(
        requirement_id=_read_requirement_id(entry["requirement_id"], where),
        outcome=outcome,
        reason=_read_text(entry["reason"], f"{where} reason"),
        severity=(
            _read_enum(ReviewSeverity, severity, where)
            if severity is not None
            else None
        ),
    )


def material_escalations(
    rework_responses: tuple[ReworkResponse, ...], what_refs: frozenset[str]
) -> tuple[tuple[str, int], ...]:
    """(item, product_question_index) of each escalated material WHAT item."""
    return tuple(
        (response.item, response.product_question_index)
        for response in rework_responses
        if response.item in what_refs
        and response.outcome is ReworkOutcome.ESCALATED
        and response.product_question_index is not None
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
