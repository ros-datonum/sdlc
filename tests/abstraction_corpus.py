"""Requirement abstraction regression corpus (RW-R05).

Ten synthetic cases, one per frozen abstraction class, each pairing a RAW
source with what a correct Requirement-level interpretation of it must keep
or avoid:

    Requirement                     = WHAT must be true
    Technical Solution Architecture = HOW it will be satisfied
    Delivery Planning               = executable decomposition
    Task                            = implementation, test, deployment work

This is a deterministic, case-specific semantic proxy, not a general semantic
or NLP classifier. Each case records, for its own synthetic source:

- meaning as `Concept`s. A concept is a bounded list of equivalent
  expressions chosen for that source and is present when any one of them
  appears. An obligation may need several concepts, and all of them must be
  present. Concepts identify each source obligation, the observable
  acceptance, the open product question and the answers to it, and the
  architecture question;
- identity as exact strings, and only where identity is itself the property:
  a source-mandated mechanism (`argv`, `shell`) and the implementation or test
  identifiers that must never become Requirement content (`ModelRequest`,
  `request_id`, `pytest`, ...).

Whole model sentences are never golden output. The reference outputs are one
valid example per stage, and any output whose wording stays within a case's
configured equivalents passes. A novel valid paraphrase outside those
equivalents can still be flagged: that calls for reviewer judgement and,
where the meaning truly is equivalent, an explicit update to the case's
concept alternatives. Such a flag is not by itself evidence that the product
behavior is wrong.

Cardinality is stated only where the synthetic source fixes it: one
capability, or two genuinely independent obligations. There is no global or
ideal candidate count, and no count from the historical AMR corpus is a
target anywhere here.

Reference outputs cover each stage where the case's property matters (RAW
decomposition for all ten; Standard Process and Standard Review where the
property is theirs). The checks take the parsed structured output of any run,
so an independent reviewer or a dogfood harness can apply the same case to a
live model's validated output:

    decomposition_violations(case, parse_model_output(text).candidates)
    analysis = parse_analysis_output(text)
    normalization_violations(case, analysis.normalized, analysis.findings)
    review_violations(case, asserted_kinds(process_kinds, verifications, new))

An empty list means every property holds; otherwise each Violation names the
case, the property it breaks, and why. The checks show whether one output
respects the boundary as this proxy models it. They do not show that a live
model will produce such output; that is dogfood evidence. No live model, live
Fibery or AMR state is used, and this module imports no prompt, so prompt
wording can change freely.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sdlc.raw_processing import Candidate, Category
from sdlc.standard_analysis import Finding, FindingKind, NormalizedRequirement
from sdlc.standard_review import FindingVerification, NewFinding, VerificationOutcome

# The properties a violation can name.
CARDINALITY = "obligation-cardinality"
OBLIGATION_LOST = "source-obligation-lost"
OBLIGATIONS_MERGED = "independent-obligations-merged"
CATEGORY = "category"
UNESTABLISHED_CANDIDATE = "candidate-without-source-obligation"
IMPLEMENTATION_PROMOTED = "implementation-detail-as-requirement"
MANDATE_DROPPED = "mandated-mechanism-dropped"
QUESTION_CLOSED = "open-product-question-closed"
ANSWER_INVENTED = "open-product-question-answered"
ARCHITECTURE_UPSTREAM = "architecture-question-as-requirement"
ACCEPTANCE_LOST = "observable-acceptance-lost"
TEST_MECHANICS = "test-mechanics-as-acceptance"
FINDING_MISSING = "expected-finding-missing"
FINDING_UNWARRANTED = "unwarranted-finding"

# Sections that state WHAT: technical detail and test mechanics never belong.
WHAT_SECTIONS = (
    "title",
    "requirement",
    "detailed_behavior",
    "acceptance_verification",
    "constraints_edge_cases",
)
# Every section that could settle a question; only Open Questions may pose one.
DECIDING_SECTIONS = (*WHAT_SECTIONS, "rationale", "non_goals")
# Where a mandated mechanism is Requirement truth.
MANDATE_SECTIONS = ("requirement", "constraints_edge_cases")
# Where an obligation is identified.
STATEMENT_SECTIONS = ("title", "requirement")

Statement = Candidate | NormalizedRequirement


@dataclass(frozen=True)
class Violation:
    """One broken property of one case."""

    case_id: str
    rule: str
    detail: str


@dataclass(frozen=True)
class Concept:
    """One meaning, present when any of its accepted expressions appears.

    The alternatives are a bounded list of equivalents for one synthetic
    source, compared case-insensitively as substrings; they are not a general
    synonym model.
    """

    alternatives: tuple[str, ...]

    @property
    def label(self) -> str:
        return self.alternatives[0]

    def is_in(self, text: str) -> bool:
        return any(alternative.lower() in text for alternative in self.alternatives)


def any_of(*alternatives: str) -> Concept:
    return Concept(alternatives)


@dataclass(frozen=True)
class Obligation:
    """One source-established obligation: every concept it needs, and its category."""

    concepts: tuple[Concept, ...]
    category: Category

    def is_carried_by(self, statement: Statement) -> bool:
        text = _text(statement, STATEMENT_SECTIONS)
        return all(concept.is_in(text) for concept in self.concepts)

    @property
    def label(self) -> str:
        return " + ".join(concept.label for concept in self.concepts)


@dataclass(frozen=True)
class ProcessScenario:
    """A Standard Root handed to Process, and one valid normalization of it.

    `draft` holds the Root's sections as decomposition left them, defects
    included; `required_findings` are the findings that defect calls for.
    """

    draft: dict[str, str]
    reference: dict[str, object]
    required_findings: frozenset[FindingKind] = frozenset()


@dataclass(frozen=True)
class ReviewScenario:
    """A Root under review, the Process claims on it, and one valid review."""

    root: dict[str, str]
    reference: dict[str, object]
    process_findings: tuple[tuple[FindingKind, str], ...] = ()
    required_findings: frozenset[FindingKind] = frozenset()
    expects_no_defect: bool = False


@dataclass(frozen=True)
class AbstractionCase:
    """One frozen abstraction class: a source and what must hold for it.

    `obligations` lists every obligation the source establishes; when
    `cardinality_is_exact`, a decomposition has exactly that many candidates.
    `implementation_detail`, `mandated` and `test_mechanics` are identities
    matched exactly; the Concept fields are meanings.
    """

    case_id: str
    abstraction_class: str
    source: str
    obligations: tuple[Obligation, ...]
    decomposition: dict[str, object]
    cardinality_is_exact: bool = True
    implementation_detail: tuple[str, ...] = ()
    mandated: tuple[str, ...] = ()
    open_question: Concept | None = None
    invented_answer: Concept | None = None
    architecture_question: Concept | None = None
    acceptance: tuple[Concept, ...] = ()
    test_mechanics: tuple[str, ...] = ()
    never_findings: frozenset[FindingKind] = frozenset()
    process: ProcessScenario | None = None
    review: ReviewScenario | None = None
    notes: tuple[str, ...] = ()

    def violation(self, rule: str, detail: str) -> Violation:
        return Violation(self.case_id, rule, detail)


# -- the checks -----------------------------------------------------------------


def decomposition_violations(
    case: AbstractionCase, candidates: Sequence[Candidate]
) -> list[Violation]:
    """What a RAW decomposition gets wrong about `case`, if anything."""
    found = []
    if case.cardinality_is_exact and len(candidates) != len(case.obligations):
        found.append(
            case.violation(
                CARDINALITY,
                f"the source establishes {len(case.obligations)} independently "
                f"meaningful obligation(s); the output has {len(candidates)}",
            )
        )
    unmatched = list(candidates)
    for obligation in case.obligations:
        carrier = next((c for c in unmatched if obligation.is_carried_by(c)), None)
        if carrier is None:
            merged = any(obligation.is_carried_by(c) for c in candidates)
            found.append(
                case.violation(
                    OBLIGATIONS_MERGED if merged else OBLIGATION_LOST,
                    f"no candidate of its own states {obligation.label!r}",
                )
            )
            continue
        unmatched.remove(carrier)
        if carrier.category is not obligation.category:
            found.append(
                case.violation(
                    CATEGORY,
                    f"{carrier.title!r} is {carrier.category.value}, expected "
                    f"{obligation.category.value}",
                )
            )
    found += [
        case.violation(
            UNESTABLISHED_CANDIDATE,
            f"{candidate.title!r} states no obligation the source establishes",
        )
        for candidate in unmatched
    ]
    return found + _content_violations(case, candidates)


def normalization_violations(
    case: AbstractionCase,
    normalized: NormalizedRequirement,
    findings: Sequence[Finding],
) -> list[Violation]:
    """What a Standard Process normalization gets wrong about `case`."""
    found = []
    if not any(o.is_carried_by(normalized) for o in case.obligations):
        found.append(
            case.violation(
                OBLIGATION_LOST,
                f"{normalized.title!r} no longer states a source obligation",
            )
        )
    found += _content_violations(case, [normalized])
    required = case.process.required_findings if case.process else frozenset()
    return found + _finding_violations(case, required, {f.kind for f in findings})


def review_violations(
    case: AbstractionCase, asserted: frozenset[FindingKind]
) -> list[Violation]:
    """What a Standard Review gets wrong about `case`, given what it asserted."""
    scenario = case.review
    required = scenario.required_findings if scenario else frozenset()
    found = _finding_violations(case, required, asserted)
    if scenario and scenario.expects_no_defect:
        found += [
            case.violation(
                FINDING_UNWARRANTED, f"{kind.value} asserted on valid content"
            )
            for kind in sorted(asserted - case.never_findings)
        ]
    return found


def asserted_kinds(
    process_kinds: Sequence[FindingKind],
    verifications: Sequence[FindingVerification],
    new_findings: Sequence[NewFinding],
) -> frozenset[FindingKind]:
    """The defects a review asserts: confirmed Process claims and its own."""
    confirmed = {
        process_kinds[v.process_finding_index]
        for v in verifications
        if v.outcome is VerificationOutcome.CONFIRMED
    }
    return frozenset(confirmed | {f.kind for f in new_findings})


def _content_violations(
    case: AbstractionCase, statements: Sequence[Statement]
) -> list[Violation]:
    what = " ".join(_text(s, WHAT_SECTIONS) for s in statements)
    deciding = " ".join(_text(s, DECIDING_SECTIONS) for s in statements)
    mandates = " ".join(_text(s, MANDATE_SECTIONS) for s in statements)
    questions = " ".join(s.open_questions.lower() for s in statements)
    acceptance = " ".join(s.acceptance_verification.lower() for s in statements)

    found = [
        case.violation(
            IMPLEMENTATION_PROMOTED, f"{detail!r} is stated as Requirement truth"
        )
        for detail in case.implementation_detail
        if detail.lower() in what
    ]
    found += [
        case.violation(
            MANDATE_DROPPED, f"{term!r} is no longer a Requirement or constraint"
        )
        for term in case.mandated
        if term.lower() not in mandates
    ]
    question = case.open_question
    if question is not None:
        if not question.is_in(questions):
            found.append(
                case.violation(
                    QUESTION_CLOSED, f"{question.label!r} is no longer an open question"
                )
            )
        if question.is_in(deciding):
            found.append(
                case.violation(
                    ANSWER_INVENTED,
                    f"{question.label!r} is settled outside Open Questions",
                )
            )
    if case.invented_answer is not None and case.invented_answer.is_in(deciding):
        found.append(
            case.violation(
                ANSWER_INVENTED,
                f"{case.invented_answer.label!r} answers the open product question",
            )
        )
    architecture = case.architecture_question
    if architecture is not None and architecture.is_in(f"{what} {questions}"):
        found.append(
            case.violation(
                ARCHITECTURE_UPSTREAM,
                f"{architecture.label!r} is carried as Requirement content",
            )
        )
    found += [
        case.violation(ACCEPTANCE_LOST, f"acceptance no longer shows {concept.label!r}")
        for concept in case.acceptance
        if not concept.is_in(acceptance)
    ]
    found += [
        case.violation(TEST_MECHANICS, f"{mechanic!r} is stated as Requirement content")
        for mechanic in case.test_mechanics
        if mechanic.lower() in what
    ]
    return found


def _finding_violations(
    case: AbstractionCase,
    required: frozenset[FindingKind],
    asserted: frozenset[FindingKind] | set[FindingKind],
) -> list[Violation]:
    found = [
        case.violation(FINDING_MISSING, f"{kind.value} is not reported")
        for kind in sorted(required - asserted)
    ]
    return found + [
        case.violation(
            FINDING_UNWARRANTED, f"{kind.value} is reported on valid content"
        )
        for kind in sorted(case.never_findings & asserted)
    ]


def _text(statement: Statement, sections: Sequence[str]) -> str:
    return " ".join(getattr(statement, section) for section in sections).lower()


def _candidate(
    category: Category, title: str, requirement: str, **sections: str
) -> dict[str, str]:
    return {
        "category": category.value,
        "title": title,
        "requirement": requirement,
        **sections,
    }


def _decomposition(*candidates: dict[str, str]) -> dict[str, object]:
    return {"candidates": list(candidates), "findings": []}


# -- shared source material ------------------------------------------------------

TIMEOUT_TITLE = "Bound provider execution time"
TIMEOUT_REQUIREMENT = (
    "Provider execution must stop within the configured execution time limit "
    "and report the timeout outcome to the caller."
)
TIMEOUT_ACCEPTANCE = (
    "An execution that exceeds the configured limit ends, and its caller "
    "observes a timeout outcome for that request."
)
TIMEOUT_OBLIGATION = Obligation(
    (
        any_of(
            "time limit",
            "maximum duration",
            "duration limit",
            "bounded duration",
            "execution limit",
        ),
        any_of(
            "timeout",
            "timed out",
            "deadline exceeded",
            "deadline-exceeded",
            "over-duration",
        ),
    ),
    Category.FUNCTIONAL,
)

ARGV = "Provider execution must use argv and must never use a shell."
ARGV_TITLE = "Execute providers through argv without a shell"

REWORK_TITLE = "Reset the processing outcome on rework"
REWORK_REQUIREMENT = (
    "When a Ready Requirement is sent back for rework, its previous processing "
    "outcome is no longer presented as the outcome of the new cycle."
)
REWORK_ACCEPTANCE = (
    "After rework, the new cycle exposes its own eventual success or failure, "
    "and the previous outcome is not shown as its result."
)
REWORK_TEST_MECHANICS = (
    "Create fixture `ready_requirement`, patch `FiberyAdapter.write` with a mock, "
    "run `worker.process()` under pytest and assert `processing_status` equals "
    "`PENDING`."
)

OVERRIDE_TITLE = "Return failed Reviews to the human"
OVERRIDE_REQUIREMENT = (
    "A failed Review returns the Requirement to the human with its failure reasons."
)
OVERRIDE_QUESTION = (
    "May an operator override a failed Review decision? The source leaves this "
    "undecided."
)

CREDENTIAL_TITLE = "Keep credentials out of initialization output"
CREDENTIAL_REQUIREMENT = (
    "Normal project initialization completes without exposing stored "
    "credentials to project artifacts or user-visible diagnostics."
)

API_KEY_TITLE = "Hold no provider API keys"
API_KEY_REQUIREMENT = (
    "The application never holds provider API keys; model execution uses the "
    "operator's locally authenticated session."
)

NOT_A_REQUIREMENT_DEFECT = frozenset(
    {
        FindingKind.INCOMPLETE,
        FindingKind.MISSING_CONSTRAINT,
        FindingKind.MISSING_EDGE_CASE,
        FindingKind.NOT_TESTABLE,
    }
)


# -- the ten cases ----------------------------------------------------------------

CORPUS = (
    AbstractionCase(
        case_id="C01_one_capability_many_implementation_details",
        abstraction_class=(
            "one product capability with multiple technical implementation details"
        ),
        source="""\
# Provider execution

## Requirements and Expected Behavior

Provider execution must stop within the configured execution time limit and
report the timeout outcome to the caller.

Implementation notes for the current design:

- `run_model()` starts the provider in a subprocess.
- A watchdog thread sends SIGTERM, waits five seconds, then SIGKILLs the
  process group.
- The deadline is stored in a new `ModelRequest.deadline` field.
- `ExecutionStatus.TIMEOUT` is returned when the watchdog fires.
""",
        obligations=(TIMEOUT_OBLIGATION,),
        implementation_detail=(
            "run_model",
            "subprocess",
            "watchdog",
            "SIGKILL",
            "ModelRequest",
            "ExecutionStatus",
        ),
        decomposition=_decomposition(
            _candidate(
                Category.FUNCTIONAL,
                TIMEOUT_TITLE,
                TIMEOUT_REQUIREMENT,
                acceptance_verification=TIMEOUT_ACCEPTANCE,
            )
        ),
        notes=(
            (
                "Exactly one candidate because the source states one capability; "
                "this is fixture truth, not a count heuristic."
            ),
        ),
    ),
    AbstractionCase(
        case_id="C02_two_independent_obligations_one_source",
        abstraction_class="two truly independent obligations in one RAW source",
        source="""\
# Reporting

## Requirements and Expected Behavior

Users can export any report they can view as a CSV file, and every export is
recorded in the audit log with the requesting user and the time of export.
Both are implemented by the shared `ExportService`.
""",
        obligations=(
            Obligation(
                (any_of("export", "download"), any_of("csv", "comma-separated")),
                Category.FUNCTIONAL,
            ),
            Obligation((any_of("audit"),), Category.FUNCTIONAL),
        ),
        implementation_detail=("ExportService",),
        notes=(
            (
                "Two candidates because export and auditing can be accepted, "
                "rejected and changed independently; sharing a paragraph and an "
                "implementation does not make one a facet of the other."
            ),
        ),
        decomposition=_decomposition(
            _candidate(
                Category.FUNCTIONAL,
                "Export viewable reports as CSV",
                "A user can export any report they can view as a CSV file.",
            ),
            _candidate(
                Category.FUNCTIONAL,
                "Audit every report export",
                "Every report export is recorded in the audit log with the "
                "requesting user and the time of export.",
            ),
        ),
    ),
    AbstractionCase(
        case_id="C03_source_mandated_technical_constraint",
        abstraction_class="an explicit source-mandated technical constraint",
        source="""\
# Provider execution safety

## Constraints

- Provider execution must use argv and must never use a shell.
""",
        # The mandate is an identity: its concepts are the mechanism words.
        obligations=(
            Obligation((any_of("argv"), any_of("shell")), Category.CONSTRAINT),
        ),
        mandated=("argv", "shell"),
        never_findings=frozenset({FindingKind.IMPLEMENTATION_LEAKAGE}),
        decomposition=_decomposition(
            _candidate(
                Category.CONSTRAINT,
                ARGV_TITLE,
                "Provider execution must pass its command as an argv vector and "
                "must never use a shell.",
            )
        ),
        process=ProcessScenario(
            draft={"requirement": ARGV},
            reference={
                "normalized_requirement": {"title": ARGV_TITLE, "requirement": ARGV},
                "findings": [],
            },
        ),
        review=ReviewScenario(
            root={"requirement": ARGV},
            process_findings=(
                (FindingKind.IMPLEMENTATION_LEAKAGE, "argv is a technical mechanism."),
            ),
            reference={
                "finding_verifications": [
                    {
                        "process_finding_index": 0,
                        "outcome": "REJECTED",
                        "reason": "The originating RAW source explicitly mandates "
                        "argv and no shell.",
                    }
                ]
            },
            expects_no_defect=True,
        ),
    ),
    AbstractionCase(
        case_id="C04_technical_suggestion_not_mandatory",
        abstraction_class="a technical suggestion that is not a mandatory Requirement",
        source="""\
# Failure notification

## Desired Outcomes

- An operator is notified whenever automated processing of a Requirement fails.

## Context

Suggested approach: push failures onto a Redis queue consumed by a notifier
worker, or poll the job table every 30 seconds.
""",
        obligations=(
            Obligation(
                (
                    any_of("notified", "notification", "alerted", "informed"),
                    any_of("fails", "failure", "failed"),
                ),
                Category.FUNCTIONAL,
            ),
        ),
        implementation_detail=(
            "redis",
            "queue",
            "notifier worker",
            "poll",
            "job table",
        ),
        decomposition=_decomposition(
            _candidate(
                Category.FUNCTIONAL,
                "Notify operators of processing failures",
                "An operator is notified whenever automated processing of a "
                "Requirement fails.",
            )
        ),
    ),
    AbstractionCase(
        case_id="C05_acceptance_evidence_not_test_implementation",
        abstraction_class="acceptance evidence vs exact test implementation",
        source=f"""\
# Rework cycles

## Requirements and Expected Behavior

When a human sends a Ready Requirement back for rework, the previous
processing outcome must no longer be presented as the outcome of the new
cycle.

## Acceptance

After rework, the new cycle exposes its own eventual success or failure, and
the previous outcome is not shown as the new cycle's result.

## Test plan

{REWORK_TEST_MECHANICS}
""",
        obligations=(
            Obligation(
                (
                    any_of("rework", "sent back", "returned for more work"),
                    any_of("outcome", "result"),
                ),
                Category.FUNCTIONAL,
            ),
        ),
        acceptance=(
            any_of(
                "new cycle", "next cycle", "new processing cycle", "following cycle"
            ),
            any_of(
                "success or failure",
                "succeeded or failed",
                "succeeds or fails",
                "whether it succeeded",
            ),
        ),
        test_mechanics=(
            "ready_requirement",
            "FiberyAdapter",
            "mock",
            "worker.process",
            "pytest",
            "processing_status",
        ),
        decomposition=_decomposition(
            _candidate(
                Category.FUNCTIONAL,
                REWORK_TITLE,
                REWORK_REQUIREMENT,
                acceptance_verification=REWORK_ACCEPTANCE,
            )
        ),
        process=ProcessScenario(
            draft={
                "requirement": REWORK_REQUIREMENT,
                "acceptance_verification": f"{REWORK_ACCEPTANCE} {REWORK_TEST_MECHANICS}",
            },
            reference={
                "normalized_requirement": {
                    "title": REWORK_TITLE,
                    "requirement": REWORK_REQUIREMENT,
                    "acceptance_verification": REWORK_ACCEPTANCE,
                },
                "findings": [
                    {
                        "kind": "IMPLEMENTATION_LEAKAGE",
                        "detail": "Acceptance prescribed a pytest fixture and a "
                        "mocked adapter; only the observable acceptance was kept.",
                    }
                ],
            },
            required_findings=frozenset({FindingKind.IMPLEMENTATION_LEAKAGE}),
        ),
        review=ReviewScenario(
            root={
                "requirement": REWORK_REQUIREMENT,
                "acceptance_verification": f"{REWORK_ACCEPTANCE} {REWORK_TEST_MECHANICS}",
            },
            reference={
                "new_findings": [
                    {
                        "kind": "IMPLEMENTATION_LEAKAGE",
                        "severity": "WARNING",
                        "detail": "Acceptance / Verification prescribes pytest, a "
                        "fixture and a mocked adapter.",
                    }
                ]
            },
            required_findings=frozenset({FindingKind.IMPLEMENTATION_LEAKAGE}),
        ),
    ),
    AbstractionCase(
        case_id="C06_unresolved_product_decision",
        abstraction_class="an unresolved product decision",
        source="""\
# Review override

## Requirements and Expected Behavior

- A failed Review returns the Requirement to the human with its failure reasons.

## Open Questions

- May an operator override a failed Review decision? Not decided yet.
""",
        obligations=(
            Obligation(
                (
                    any_of("failed review", "review fails", "rejected review"),
                    any_of("human", "person"),
                ),
                Category.FUNCTIONAL,
            ),
        ),
        open_question=any_of("override", "overrule", "bypass", "set aside"),
        invented_answer=any_of(
            "an operator can override",
            "operators can override",
            "an operator cannot override",
            "operators cannot override",
            "override is allowed",
            "override is not allowed",
            "can be overridden",
            "cannot be overridden",
            "an operator can bypass",
            "an operator cannot bypass",
            "can be bypassed",
            "cannot be bypassed",
        ),
        never_findings=frozenset({FindingKind.INCOMPLETE}),
        decomposition=_decomposition(
            _candidate(
                Category.FUNCTIONAL,
                OVERRIDE_TITLE,
                OVERRIDE_REQUIREMENT,
                open_questions=OVERRIDE_QUESTION,
            )
        ),
        process=ProcessScenario(
            draft={
                "requirement": OVERRIDE_REQUIREMENT,
                "open_questions": "Can an operator override a failed Review?",
            },
            reference={
                "normalized_requirement": {
                    "title": OVERRIDE_TITLE,
                    "requirement": OVERRIDE_REQUIREMENT,
                    "open_questions": OVERRIDE_QUESTION,
                },
                "findings": [],
            },
        ),
        review=ReviewScenario(
            root={
                "requirement": OVERRIDE_REQUIREMENT,
                "open_questions": OVERRIDE_QUESTION,
            },
            reference={},
            expects_no_defect=True,
        ),
    ),
    AbstractionCase(
        case_id="C07_unresolved_architecture_decision",
        abstraction_class="an unresolved architecture decision",
        source="""\
# Provider execution

## Requirements and Expected Behavior

Provider execution must stop within the configured execution time limit and
report the timeout outcome to the caller.

## Open Questions

- Which cancellation mechanism enforces the limit is left to the architects.
""",
        obligations=(TIMEOUT_OBLIGATION,),
        architecture_question=any_of(
            "cancellation mechanism",
            "cancellation strategy",
            "enforcement mechanism",
            "how the limit is enforced",
            "which mechanism enforces",
        ),
        never_findings=NOT_A_REQUIREMENT_DEFECT,
        decomposition=_decomposition(
            _candidate(
                Category.FUNCTIONAL,
                TIMEOUT_TITLE,
                TIMEOUT_REQUIREMENT,
                acceptance_verification=TIMEOUT_ACCEPTANCE,
            )
        ),
        process=ProcessScenario(
            draft={
                "requirement": TIMEOUT_REQUIREMENT,
                "open_questions": "Which cancellation mechanism enforces the limit?",
            },
            reference={
                "normalized_requirement": {
                    "title": TIMEOUT_TITLE,
                    "requirement": TIMEOUT_REQUIREMENT,
                    "acceptance_verification": TIMEOUT_ACCEPTANCE,
                },
                "findings": [],
            },
        ),
        review=ReviewScenario(
            root={
                "requirement": TIMEOUT_REQUIREMENT,
                "acceptance_verification": TIMEOUT_ACCEPTANCE,
            },
            reference={},
            expects_no_defect=True,
        ),
    ),
    AbstractionCase(
        case_id="C08_field_detail_without_independent_meaning",
        abstraction_class="field-level detail that is not independently meaningful",
        source="""\
# Request traceability

## Requirements and Expected Behavior

Every processing attempt must be traceable to its originating request.

## Context

Suggested/current implementation: `ModelRequest.request_id: UUID`, set by
`build_request()`.
""",
        obligations=(
            Obligation(
                (
                    any_of("traceable", "trace", "correlate"),
                    any_of(
                        "originating request", "original request", "initiating request"
                    ),
                ),
                Category.FUNCTIONAL,
            ),
        ),
        implementation_detail=("request_id", "ModelRequest", "UUID", "build_request"),
        decomposition=_decomposition(
            _candidate(
                Category.FUNCTIONAL,
                "Trace each processing attempt to its request",
                "Every processing attempt is traceable to its originating request.",
            )
        ),
    ),
    AbstractionCase(
        case_id="C09_legitimate_non_functional_requirement",
        abstraction_class="a legitimate non-functional Requirement",
        source="""\
# Credential safety

## Requirements and Expected Behavior

Normal project initialization must complete without exposing stored
credentials to project artifacts or user-visible diagnostics.

## Context

Current implementation idea: filter `os.environ` through `redact_secrets()`
before logging.
""",
        obligations=(
            Obligation(
                (
                    any_of("credential", "secret"),
                    any_of("diagnostics", "error output", "log output"),
                ),
                Category.NON_FUNCTIONAL,
            ),
        ),
        implementation_detail=("os.environ", "redact_secrets"),
        never_findings=frozenset({FindingKind.IMPLEMENTATION_LEAKAGE}),
        decomposition=_decomposition(
            _candidate(
                Category.NON_FUNCTIONAL, CREDENTIAL_TITLE, CREDENTIAL_REQUIREMENT
            )
        ),
        review=ReviewScenario(
            root={"requirement": CREDENTIAL_REQUIREMENT},
            reference={},
            expects_no_defect=True,
        ),
    ),
    AbstractionCase(
        case_id="C10_legitimate_system_constraint",
        abstraction_class="a legitimate system constraint",
        source="""\
# Model access

## Constraints

- The application must never hold provider API keys; model execution uses the
  operator's locally authenticated session.

## Context

Current design: an `AuthPreflight` class calls a `KeychainReader` module
before each run.
""",
        obligations=(
            Obligation(
                (
                    any_of("api key", "provider key", "provider credential"),
                    any_of("locally authenticated", "local login", "own session"),
                ),
                Category.CONSTRAINT,
            ),
        ),
        implementation_detail=("AuthPreflight", "KeychainReader"),
        never_findings=frozenset({FindingKind.IMPLEMENTATION_LEAKAGE}),
        decomposition=_decomposition(
            _candidate(Category.CONSTRAINT, API_KEY_TITLE, API_KEY_REQUIREMENT)
        ),
        review=ReviewScenario(
            root={"requirement": API_KEY_REQUIREMENT},
            reference={},
            expects_no_defect=True,
        ),
    ),
)

CASES = {case.case_id: case for case in CORPUS}
