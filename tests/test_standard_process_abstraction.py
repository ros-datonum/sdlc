"""RW-R03: Standard Process normalizes and analyzes at the Requirement level.

Whether a Requirement leaks HOW, is itself HOW, or is a valid high-level
obligation is a semantic judgement the model makes under the Process prompt.
Through the real Process stage boundary, with bounded fake-model output, these
tests pin what deterministic code owns: the prompt states the rule for each
case, IMPLEMENTATION_LEAKAGE is accepted as a finding about this Requirement,
and the Root Document is rewritten from exactly the validated normalization,
never deepened, completed, split or multiplied by code. No live model runs.
"""

import json
import re
from types import SimpleNamespace

from processor_fake import FakeModelRuntime
from sdlc.fibery_workspace import RequirementRecord
from sdlc.process_result import parse_process_result
from sdlc.raw_processing import (
    DOCUMENT_SECTIONS,
    MISSING_INFORMATION,
    NO_OPEN_QUESTIONS,
)
from sdlc.results import StandardProcessResultCode
from sdlc.standard_analysis import (
    ANALYSIS_KEYS,
    NORMALIZED_KEYS,
    FindingKind,
    parse_analysis_output,
)
from sdlc.standard_processor import process_standard_requirement
from sdlc.standard_prompt import INSTRUCTIONS
from standard_fake import (
    REQUIREMENT_ID,
    analysis_output,
    build_standard_workspace,
    process_results,
)

LEAKAGE = FindingKind.IMPLEMENTATION_LEAKAGE
ANALYSIS = {key: "Assessed at the Requirement level." for key in sorted(ANALYSIS_KEYS)}


def document(title, **sections):
    """A current Root Document in the approved schema, as Draft left it."""
    lines = [f"# {REQUIREMENT_ID} — {title}", ""]
    for key, heading in DOCUMENT_SECTIONS:
        absent = NO_OPEN_QUESTIONS if key == "open_questions" else MISSING_INFORMATION
        lines += [f"## {heading}", "", sections.get(key, absent), ""]
    return "\n".join(lines).rstrip("\n") + "\n"


def process(current, source, normalized, findings=(), relations=(), others=()):
    """Run Standard Process on `current`, answered by one bounded normalization."""
    ws, std, _ = build_standard_workspace(others=others)
    ws.content["std-secret"] = current
    ws.content["raw-secret"] = source
    before = set(ws.requirements)
    body = {
        "normalized_requirement": normalized,
        "analysis": ANALYSIS,
        "findings": list(findings),
        "proposed_relations": list(relations),
    }
    model = FakeModelRuntime([json.dumps(body)])

    result = process_standard_requirement(ws, model, std.id)

    assert result.code is StandardProcessResultCode.REQUIREMENT_PROCESSED, result
    assert set(ws.requirements) == before, "Process creates and splits nothing"
    assert len(ws.documents_attached_to_requirement(std.public_id)) == 1
    assert ws.requirements[std.id].state == "Review"
    [result_node] = process_results(ws)
    return SimpleNamespace(
        ws=ws,
        std=std,
        result=result,
        root=ws.content["std-secret"],
        stored=parse_process_result(ws.content[result_node.secret]),
        prompt=" ".join(model.calls[0]["prompt"].split()),
    )


def section(text, heading):
    body = text.split(f"## {heading}\n\n", 1)[1]
    return body.split("\n\n## ", 1)[0].strip()


def kinds(run):
    return [(finding.kind, finding.requirement_id) for finding in run.stored.findings]


TIMEOUT_SOURCE = """\
# Provider execution

## Requirements and Expected Behavior

Provider execution must stop within the configured execution time limit and
report the timeout outcome to the caller.
"""

TIMEOUT_TITLE = "Bound provider execution time"
TIMEOUT_REQUIREMENT = (
    "Provider execution must stop within the configured execution time limit "
    "and report the timeout outcome to the caller."
)
TIMEOUT_MECHANISMS = ("watchdog", "SIGKILL", "run_model", "subprocess")


# -- 1. a valid high-level Requirement --------------------------------------


def test_a_valid_high_level_requirement_stays_high_level():
    run = process(
        document(
            TIMEOUT_TITLE,
            requirement=(
                "Provider execution is stopped when it runs past the configured "
                "limit, and the caller is told it timed out."
            ),
        ),
        TIMEOUT_SOURCE,
        {"title": TIMEOUT_TITLE, "requirement": TIMEOUT_REQUIREMENT},
    )

    assert section(run.root, "Requirement") == TIMEOUT_REQUIREMENT
    for heading in ("Detailed Behavior", "Constraints & Edge Cases"):
        assert section(run.root, heading) == MISSING_INFORMATION
    assert not any(word in run.root for word in TIMEOUT_MECHANISMS)
    assert run.stored.findings == ()
    assert "Keep a valid high-level Requirement high-level." in run.prompt
    assert (
        "never add technical design, mechanisms or detail to make it more "
        "concrete" in run.prompt
    )


# -- 2. partial implementation leakage --------------------------------------

LEAKED_BEHAVIOR = (
    "`run_model()` starts the provider in a subprocess; a watchdog thread sends "
    "SIGTERM, waits five seconds, then SIGKILLs the process group."
)


def test_partial_leakage_keeps_the_what_and_reports_the_how():
    detail = (
        "Detailed Behavior prescribed a subprocess started by run_model() and "
        "watchdog SIGTERM/SIGKILL escalation; the source requires only that "
        "execution stops within the limit, so the mechanism was omitted."
    )
    run = process(
        document(
            TIMEOUT_TITLE,
            requirement=TIMEOUT_REQUIREMENT,
            detailed_behavior=LEAKED_BEHAVIOR,
        ),
        TIMEOUT_SOURCE,
        {"title": TIMEOUT_TITLE, "requirement": TIMEOUT_REQUIREMENT},
        findings=[{"kind": "IMPLEMENTATION_LEAKAGE", "detail": detail}],
    )

    assert section(run.root, "Requirement") == TIMEOUT_REQUIREMENT
    assert section(run.root, "Detailed Behavior") == MISSING_INFORMATION
    assert not any(word in run.root for word in TIMEOUT_MECHANISMS), "not moved"
    assert kinds(run) == [(LEAKAGE, None)]
    assert "watchdog" in run.stored.findings[0].detail, "described in the finding"
    assert run.result.findings == (f"IMPLEMENTATION_LEAKAGE: {detail}",)
    assert "remove or omit the HOW from the normalized sections" in run.prompt
    assert (
        "Do not move the HOW into another section, and do not turn an "
        "implementation choice into a new product constraint." in run.prompt
    )


# -- 3. the entire candidate is Architecture / Task detail -------------------

TASK_SOURCE = """\
# Model request refactor

## Context

Implementation notes: add a `request_id: UUID` field to class `ModelRequest`
and persist it in the `requests` SQLite table.
"""

TASK_STATEMENT = (
    "Add a `request_id: UUID` field to class `ModelRequest` and persist it in the "
    "`requests` SQLite table."
)


def test_a_candidate_that_is_entirely_how_is_reported_not_rescued():
    detail = (
        "The Requirement is entirely Task-level: a field on class ModelRequest and "
        "its SQLite persistence. The originating RAW establishes no product or "
        "system obligation behind it."
    )
    title = "Add request_id to ModelRequest"
    run = process(
        document(title, requirement=TASK_STATEMENT),
        TASK_SOURCE,
        {"title": title, "requirement": TASK_STATEMENT},
        findings=[{"kind": "IMPLEMENTATION_LEAKAGE", "detail": detail}],
    )

    assert section(run.root, "Requirement") == TASK_STATEMENT, "no fabricated WHAT"
    assert "trace" not in run.root.lower()
    assert kinds(run) == [(LEAKAGE, None)]
    assert "Do not invent a higher-level Requirement to rescue it" in run.prompt
    assert "it stays defective and goes to Review carrying the finding" in run.prompt


# -- 4. a source-mandated technical constraint -------------------------------

ARGV_SOURCE = """\
# Provider execution safety

## Constraints

- Provider execution must use argv and must never use a shell.
"""

ARGV = "Provider execution must use argv and must never use a shell."


def test_a_source_mandated_constraint_stays_intact_and_is_not_leakage():
    title = "Execute providers through argv without a shell"
    run = process(
        document(title, requirement=ARGV),
        ARGV_SOURCE,
        {"title": title, "requirement": ARGV},
    )

    assert section(run.root, "Requirement") == ARGV
    assert run.stored.findings == ()
    assert (
        '"Provider execution must use argv and must never use a shell" is such a '
        "mandate. Do not report it as leakage merely because it is technical."
        in run.prompt
    )
    assert (
        '"current implementation uses argv" or "suggested solution: use argv" '
        "does not make argv a Requirement." in run.prompt
    )


# -- 5. acceptance versus test implementation --------------------------------

REWORK_SOURCE = """\
# Rework cycles

## Requirements and Expected Behavior

When a human sends a Ready Requirement back for rework, the previous
processing outcome must no longer be presented as the outcome of the new
cycle, and the new cycle must expose its own success or failure.
"""

REWORK_TITLE = "Reset the processing outcome on rework"
REWORK_REQUIREMENT = (
    "When a Ready Requirement is sent back for rework, its previous processing "
    "outcome is no longer presented as the outcome of the new cycle."
)
OBSERVABLE_ACCEPTANCE = (
    "When a Ready Requirement is sent back for rework, the prior processing "
    "outcome is no longer presented as the result of the new cycle, and the new "
    "cycle exposes its own eventual success or failure."
)
TEST_MECHANICS = (
    "Create fixture `ready_requirement`, patch `FiberyAdapter.write` with a mock "
    "and assert `processing_status == 'PENDING'` under pytest."
)
TEST_WORDS = ("ready_requirement", "FiberyAdapter", "mock", "pytest", "PENDING")


def test_observable_acceptance_is_kept_and_test_mechanics_are_not():
    run = process(
        document(
            REWORK_TITLE,
            requirement=REWORK_REQUIREMENT,
            acceptance_verification=f"{OBSERVABLE_ACCEPTANCE}\n\n{TEST_MECHANICS}",
        ),
        REWORK_SOURCE,
        {
            "title": REWORK_TITLE,
            "requirement": REWORK_REQUIREMENT,
            "acceptance_verification": OBSERVABLE_ACCEPTANCE,
        },
        findings=[
            {
                "kind": "IMPLEMENTATION_LEAKAGE",
                "detail": "Acceptance prescribed a pytest fixture, a mocked "
                "FiberyAdapter.write and an internal status assertion.",
            }
        ],
    )

    assert section(run.root, "Acceptance / Verification") == OBSERVABLE_ACCEPTANCE
    assert not any(word in run.root for word in TEST_WORDS)
    assert kinds(run) == [(LEAKAGE, None)]
    assert (
        "Never unit or integration test instructions, mocks, fixtures, a test "
        "framework, internal function calls or an implementation-specific "
        "verification path." in run.prompt
    )


def test_test_mechanics_alone_are_omitted_not_turned_into_acceptance():
    run = process(
        document(
            REWORK_TITLE,
            requirement=REWORK_REQUIREMENT,
            acceptance_verification=TEST_MECHANICS,
        ),
        REWORK_SOURCE,
        {"title": REWORK_TITLE, "requirement": REWORK_REQUIREMENT},
        findings=[
            {
                "kind": "IMPLEMENTATION_LEAKAGE",
                "detail": "Acceptance held only test mechanics; they were omitted.",
            }
        ],
    )

    assert section(run.root, "Acceptance / Verification") == MISSING_INFORMATION
    assert not any(word in run.root for word in TEST_WORDS)
    assert (
        "If the only material is test mechanics, omit it rather than converting "
        "it into invented acceptance criteria" in run.prompt
    )


# -- 6. an open product decision ---------------------------------------------

OVERRIDE_SOURCE = """\
# Review override

## Requirements and Expected Behavior

- A failed Review returns the Requirement to the human with its failure reasons.

## Open Questions

- May an operator override a failed Review decision? Not decided yet.
"""

OVERRIDE_TITLE = "Return failed Reviews to the human"
OVERRIDE_REQUIREMENT = (
    "A failed Review returns the Requirement to the human with its failure reasons."
)
OVERRIDE_QUESTION = (
    "May an operator override a failed Review decision? The source leaves this "
    "undecided."
)


def test_an_open_product_decision_stays_open_and_unanswered():
    run = process(
        document(
            OVERRIDE_TITLE,
            requirement=OVERRIDE_REQUIREMENT,
            open_questions="Can an operator override a failed Review?",
        ),
        OVERRIDE_SOURCE,
        {
            "title": OVERRIDE_TITLE,
            "requirement": OVERRIDE_REQUIREMENT,
            "open_questions": OVERRIDE_QUESTION,
        },
    )

    assert section(run.root, "Open Questions") == OVERRIDE_QUESTION
    answered = run.root.split("## Open Questions", 1)[0]
    assert "override" not in answered, "no answer elsewhere in the document"
    assert "Preserve each as a question and never answer it." in run.prompt


# -- 7. an architecture-only question -----------------------------------------


def test_an_architecture_only_question_is_not_missing_requirement_content():
    run = process(
        document(
            OVERRIDE_TITLE,
            requirement=OVERRIDE_REQUIREMENT,
            open_questions="Which queue library should deliver the failure notice?",
        ),
        OVERRIDE_SOURCE.split("## Open Questions", 1)[0],
        {"title": OVERRIDE_TITLE, "requirement": OVERRIDE_REQUIREMENT},
    )

    assert section(run.root, "Open Questions") == NO_OPEN_QUESTIONS
    assert "queue library" not in run.root
    assert run.stored.findings == (), "not INCOMPLETE for a missing HOW decision"
    assert (
        "A missing architecture decision is not a product gap unless the source "
        "makes that decision part of WHAT" in run.prompt
    )


# -- 8. atomicity -------------------------------------------------------------

EXPORT_SOURCE = """\
# Reporting

## Requirements and Expected Behavior

Users can export any report they can view as a CSV file, and every export is
recorded in the audit log with the requesting user and the time of export.
"""

EXPORT_REQUIREMENT = (
    "A user can export any report they can view as a CSV file, and every export "
    "is recorded in the audit log with the requesting user and the time of "
    "export."
)


def test_independent_obligations_yield_non_atomic_without_a_split():
    run = process(
        document("Export and audit reports", requirement=EXPORT_REQUIREMENT),
        EXPORT_SOURCE,
        {"title": "Export and audit reports", "requirement": EXPORT_REQUIREMENT},
        findings=[
            {
                "kind": "NON_ATOMIC",
                "detail": "CSV export and export auditing can be accepted, "
                "rejected and changed independently.",
            }
        ],
    )

    assert kinds(run) == [(FindingKind.NON_ATOMIC, None)]
    assert section(run.root, "Requirement") == EXPORT_REQUIREMENT, "not split"


def test_technical_facets_of_one_obligation_are_not_non_atomic():
    facets = (
        "The limit applies to each execution attempt, and a timed-out attempt is "
        "reported as a timeout, not as a generic failure."
    )
    run = process(
        document(
            TIMEOUT_TITLE,
            requirement=TIMEOUT_REQUIREMENT,
            constraints_edge_cases=facets,
        ),
        TIMEOUT_SOURCE,
        {
            "title": TIMEOUT_TITLE,
            "requirement": TIMEOUT_REQUIREMENT,
            "constraints_edge_cases": facets,
        },
    )

    assert FindingKind.NON_ATOMIC not in [kind for kind, _ in kinds(run)]
    assert section(run.root, "Constraints & Edge Cases") == facets
    assert (
        "Report NON_ATOMIC only when the Requirement holds more than one genuinely "
        "independent obligation, never for technical facets of one obligation."
        in run.prompt
    )


# -- 9. testability -----------------------------------------------------------

CREDENTIAL_SOURCE = """\
# Credential safety

## Requirements and Expected Behavior

Normal project initialization must complete without exposing stored
credentials to project artifacts or user-visible diagnostics.
"""

CREDENTIAL_REQUIREMENT = (
    "Normal project initialization completes without exposing stored "
    "credentials to project artifacts or user-visible diagnostics."
)


def test_an_observable_requirement_is_not_penalized_for_absent_test_design():
    title = "Keep credentials out of initialization output"
    run = process(
        document(title, requirement=CREDENTIAL_REQUIREMENT),
        CREDENTIAL_SOURCE,
        {"title": title, "requirement": CREDENTIAL_REQUIREMENT},
    )

    assert run.stored.findings == ()
    assert section(run.root, "Requirement") == CREDENTIAL_REQUIREMENT
    assert (
        "Do not report NOT_TESTABLE merely because no test implementation or "
        "verification design exists." in run.prompt
    )
    assert (
        "Report INCOMPLETE, MISSING_CONSTRAINT or MISSING_EDGE_CASE only for a "
        "product/system obligation, boundary or case the source establishes"
        in run.prompt
    )


# -- 10. peer comparison and relation proposals ------------------------------

PEER = RequirementRecord(
    id="std-peer",
    public_id="41",
    requirement_id="SDLC-FR-0041",
    title="Bound provider execution time",
    type_name="Standard",
    state="Ready",
    revision=2,
    project_id="p-1",
    source_fingerprint=None,
)


def test_peer_findings_and_relation_proposals_stay_non_mutating():
    ws, _, _ = build_standard_workspace(others=[PEER])
    [peer_root] = ws.documents_attached_to_requirement(PEER.public_id)
    peer_document = ws.content[peer_root.secret]

    run = process(
        document(TIMEOUT_TITLE, requirement=TIMEOUT_REQUIREMENT),
        TIMEOUT_SOURCE,
        {"title": TIMEOUT_TITLE, "requirement": TIMEOUT_REQUIREMENT},
        findings=[
            {
                "kind": "POSSIBLE_DUPLICATE",
                "requirement_id": PEER.requirement_id,
                "detail": "The peer states the same timeout obligation.",
            }
        ],
        relations=[
            {
                "kind": "DEPENDS_ON",
                "requirement_id": PEER.requirement_id,
                "rationale": "Shares the configured execution limit.",
            }
        ],
        others=[PEER],
    )

    assert kinds(run) == [(FindingKind.POSSIBLE_DUPLICATE, PEER.requirement_id)]
    assert [r.requirement_id for r in run.stored.proposed_relations] == [
        PEER.requirement_id
    ]
    assert run.ws.requirements[PEER.id] == PEER
    [peer_root] = run.ws.documents_attached_to_requirement(PEER.public_id)
    assert run.ws.content[peer_root.secret] == peer_document
    assert not any(
        m.startswith(("add_depends_on", "add_affects")) for m in run.ws.mutations
    ), "relation proposals are never written"
    assert (
        "one that is not Applied is a candidate under review, not approved "
        "authority." in run.prompt
    )


# -- the contract itself -------------------------------------------------------


def test_implementation_leakage_is_a_finding_about_this_requirement():
    assert not LEAKAGE.is_about_another_requirement
    listed = re.search(r"ABOUT THIS Requirement \(([^)]*)\)", INSTRUCTIONS)
    assert "IMPLEMENTATION_LEAKAGE" in listed.group(1)


def test_the_prompt_leakage_example_parses_as_a_self_finding():
    [example] = [
        json.loads(re.sub(r"\s+", " ", text))
        for text in re.findall(
            r"\{[^{}]*\"kind\": \"IMPLEMENTATION_LEAKAGE\"[^{}]*\}", INSTRUCTIONS
        )
    ]

    [finding] = parse_analysis_output(analysis_output(findings=[example])).findings
    assert (finding.kind, finding.requirement_id) == (LEAKAGE, None)


def test_the_prompt_asks_for_no_reasoning_and_no_severity():
    prompt = " ".join(INSTRUCTIONS.split())
    assert "no explanation of your reasoning" in prompt
    assert "Do not rate severity; Review does that." in prompt
    assert '"severity"' not in INSTRUCTIONS


def test_the_prompt_states_the_document_structure_rules():
    prompt = " ".join(INSTRUCTIONS.split())
    assert "The title is a single line" in prompt
    assert "must not contain a level-1 or level-2 Markdown heading" in prompt


def test_the_prompt_shape_is_the_unchanged_closed_contract():
    normalized = INSTRUCTIONS.split('"normalized_requirement": {', 1)[1]
    normalized = normalized.split("}", 1)[0]
    analysis = INSTRUCTIONS.split('"analysis": {', 1)[1].split("}", 1)[0]

    assert set(re.findall(r'"(\w+)":', normalized)) == NORMALIZED_KEYS
    assert set(re.findall(r'"(\w+)":', analysis)) == ANALYSIS_KEYS
