"""RW-R02: RAW decomposition yields Requirement-level candidates.

Which source statements are Requirement-level obligations is a semantic
decision the model makes under the decomposition prompt. For representative
sources these tests pin what deterministic code owns: the prompt states the
rule that governs the case, and a bounded, conforming decomposition reaches
Fibery exactly as decided, never split, merged, completed or counted by code.
No live model is involved.
"""

import re

from processor_fake import FakeModelRuntime, build_workspace, model_output
from sdlc.fibery_workspace import RequirementRecord
from sdlc.raw_processing import CANDIDATE_KEYS, MISSING_INFORMATION
from sdlc.raw_processor import process_raw_requirement
from sdlc.raw_prompt import INSTRUCTIONS
from sdlc.results import ProcessResultCode


def obligation(category, title, requirement, **sections):
    """A candidate carrying only the sections its source establishes."""
    return {
        "category": category,
        "title": title,
        "requirement": requirement,
        **sections,
    }


def decompose(source, decomposition, standards=()):
    """Process a RAW whose Root Document is `source`, answered by `decomposition`."""
    ws, raw, _ = build_workspace(standards=standards)
    ws.content["raw-secret"] = source
    model = FakeModelRuntime([decomposition])

    result = process_raw_requirement(ws, model, raw.id)

    assert result.code is ProcessResultCode.RAW_REQUIREMENT_PROCESSED
    assert ws.content["raw-secret"] == source, "the RAW source is preserved"
    return ws, raw, model, result


def produced(ws, raw):
    """Each Standard the RAW produced, with its Root Document text."""
    documents = []
    for entity_id in ws.produces(raw.id):
        record = ws.requirements[entity_id]
        [root] = ws.documents_attached_to_requirement(record.public_id)
        documents.append((record, ws.content[root.secret]))
    return documents


def section(document, heading):
    body = document.split(f"## {heading}\n\n", 1)[1]
    return body.split("\n\n## ", 1)[0].strip()


def instructed(model):
    """The instructions the model received, whitespace-normalized."""
    return " ".join(model.calls[0]["prompt"].split())


# -- 1. one capability, many implementation details --------------------------

TIMEOUT_SOURCE = """\
# Provider execution

## Requirements and Expected Behavior

Provider execution must stop within the configured execution time limit and
report the timeout outcome to the caller.

Implementation notes for the current design:

- `run_model()` starts the provider in a subprocess.
- A watchdog thread sends SIGTERM, waits five seconds, then SIGKILLs the
  process group.
- The deadline is stored in a new `ModelRequest.deadline` field.
- The exit is mapped to `ExecutionStatus.TIMEOUT`.
"""

TIMEOUT_OBLIGATION = obligation(
    "FUNCTIONAL",
    "Bound provider execution time",
    "Provider execution must stop within the configured execution time limit "
    "and report the timeout outcome to the caller.",
    acceptance_verification=(
        "An execution that exceeds the configured limit ends, and its caller "
        "observes a timeout outcome for that request."
    ),
)

TIMEOUT_DETAILS = ("run_model", "watchdog", "SIGKILL", "ModelRequest", "TIMEOUT")


def test_one_capability_with_many_implementation_details_is_one_candidate():
    ws, raw, model, result = decompose(
        TIMEOUT_SOURCE, model_output([TIMEOUT_OBLIGATION])
    )

    [(record, document)] = produced(ws, raw)
    assert result.candidates == (record.requirement_id,)
    assert not any(detail in document for detail in TIMEOUT_DETAILS)
    context = model.calls[0]["context"]
    assert all(detail in context for detail in TIMEOUT_DETAILS), "source context"
    assert (
        "When the source describes one capability together with many technical "
        "details of one proposed implementation, produce one candidate for the "
        "capability." in instructed(model)
    )


# -- 2. two genuinely independent obligations -------------------------------

EXPORT_SOURCE = """\
# Reporting

## Requirements and Expected Behavior

Users can export any report they can view as a CSV file, and every export is
recorded in the audit log with the requesting user and the time of export.
"""


def test_two_independent_obligations_in_one_paragraph_stay_two_candidates():
    ws, raw, model, result = decompose(
        EXPORT_SOURCE,
        model_output(
            [
                obligation(
                    "FUNCTIONAL",
                    "Export viewable reports as CSV",
                    "A user can export any report they can view as a CSV file.",
                ),
                obligation(
                    "FUNCTIONAL",
                    "Audit every report export",
                    "Every report export is recorded in the audit log with the "
                    "requesting user and the time of export.",
                ),
            ]
        ),
    )

    documents = produced(ws, raw)
    assert {record.title for record, _ in documents} == {
        "Export viewable reports as CSV",
        "Audit every report export",
    }
    assert len(set(result.candidates)) == 2
    for record, _ in documents:
        assert ws.derived_from_ids[record.id] == [raw.id]
    assert (
        "Do not merge independent obligations because they share a paragraph, "
        "a source section or an implementation." in instructed(model)
    )


# -- 3. an implementation suggestion ----------------------------------------

NOTIFY_SOURCE = """\
# Failure notification

## Desired Outcomes

- An operator is notified whenever automated processing of a Requirement fails.

## Context

Suggested approach: push failures onto a Redis queue consumed by a notifier
worker, or poll the job table every 30 seconds.
"""


def test_an_implementation_suggestion_does_not_become_a_candidate():
    ws, raw, model, _ = decompose(
        NOTIFY_SOURCE,
        model_output(
            [
                obligation(
                    "FUNCTIONAL",
                    "Notify operators of processing failures",
                    "An operator is notified whenever automated processing of a "
                    "Requirement fails.",
                )
            ]
        ),
    )

    [(_, document)] = produced(ws, raw)
    assert not any(word in document for word in ("Redis", "notifier", "poll"))
    assert "Redis queue" in model.calls[0]["context"]
    prompt = instructed(model)
    assert (
        "A mechanism is not mandatory merely because it appears in an example, "
        "the current implementation, background discussion, an existing "
        "architecture or a suggested approach." in prompt
    )
    assert "It stays in the RAW source as context for later Architecture" in prompt


# -- 4. an explicitly source-mandated mechanism -----------------------------

ARGV_SOURCE = """\
# Provider execution safety

## Constraints

- Provider execution must use argv and must never use a shell.
"""

ARGV_REQUIREMENT = (
    "Provider execution must pass its command as an argv vector and must never "
    "invoke a shell."
)


def test_an_explicitly_mandated_mechanism_remains_a_constraint():
    ws, raw, model, result = decompose(
        ARGV_SOURCE,
        model_output(
            [
                obligation(
                    "CONSTRAINT",
                    "Execute providers through argv without a shell",
                    ARGV_REQUIREMENT,
                )
            ]
        ),
    )

    [(_, document)] = produced(ws, raw)
    assert result.candidates[0].startswith("SDLC-CON-")
    assert section(document, "Requirement") == ARGV_REQUIREMENT
    prompt = instructed(model)
    assert (
        "A technical mechanism is Requirement content only when the source "
        "explicitly makes that exact mechanism mandatory." in prompt
    )
    assert (
        '"provider execution must use argv and must never use a shell" '
        "explicitly mandates the mechanism, so it may remain a CONSTRAINT." in prompt
    )
    assert (
        "When the mandate is unclear, record that uncertainty in open_questions "
        "instead of promoting the mechanism." in prompt
    )


INJECTION_SOURCE = """\
# Provider execution safety

## Requirements and Expected Behavior

- Caller-controlled input must never be interpreted as shell command syntax.
"""


def test_an_unmandated_mechanism_leaves_only_the_outcome():
    ws, raw, model, result = decompose(
        INJECTION_SOURCE,
        model_output(
            [
                obligation(
                    "NON_FUNCTIONAL",
                    "Never interpret caller input as command syntax",
                    "Caller-controlled input must not be interpreted as "
                    "executable command syntax during provider execution.",
                )
            ]
        ),
    )

    [(_, document)] = produced(ws, raw)
    assert result.candidates[0].startswith("SDLC-NFR-")
    assert "argv" not in document
    assert "the process invocation design is left to Architecture" in instructed(model)


# -- 5. acceptance versus test implementation -------------------------------

REWORK_SOURCE = """\
# Rework cycles

## Requirements and Expected Behavior

When a human sends a Ready Requirement back for rework, the previous
processing outcome must no longer be presented as the outcome of the new
cycle.

## Test plan

Create fixture `ready_requirement`, patch `FiberyAdapter.write` with a mock,
run `worker.process()` under pytest and assert `processing_status` equals
`PENDING`.
"""

REWORK_ACCEPTANCE = (
    "When a Ready Requirement is sent back for rework, the prior processing "
    "outcome is no longer presented as the result of the new cycle, and the new "
    "cycle exposes its own eventual success or failure."
)


def test_acceptance_is_observable_evidence_not_test_mechanics():
    ws, raw, model, _ = decompose(
        REWORK_SOURCE,
        model_output(
            [
                obligation(
                    "FUNCTIONAL",
                    "Reset the processing outcome on rework",
                    "When a Ready Requirement is sent back for rework, its "
                    "previous processing outcome is no longer presented as the "
                    "outcome of the new cycle.",
                    acceptance_verification=REWORK_ACCEPTANCE,
                )
            ]
        ),
    )

    [(_, document)] = produced(ws, raw)
    assert section(document, "Acceptance / Verification") == REWORK_ACCEPTANCE
    mechanics = ("ready_requirement", "mock", "pytest", "worker.process", "PENDING")
    assert not any(word in document for word in mechanics)
    prompt = instructed(model)
    assert (
        "Never unit-test instructions, implementation-specific test cases, "
        "fixtures, mocks, function calls or a test framework." in prompt
    )
    assert (
        "Never add architecture or test mechanics to make a candidate look more "
        "testable." in prompt
    )


# -- 6. field detail without independent meaning ----------------------------

TRACE_SOURCE = """\
# Request traceability

## Requirements and Expected Behavior

- Every processing attempt must have a stable identity that lets the user
  trace its result to the originating request.
- Add a `request_id: UUID` field to class `ModelRequest`.
"""


def test_a_field_without_independent_meaning_is_no_standalone_candidate():
    ws, raw, model, _ = decompose(
        TRACE_SOURCE,
        model_output(
            [
                obligation(
                    "FUNCTIONAL",
                    "Trace each processing attempt to its request",
                    "Every processing attempt has a stable identity that lets the "
                    "user trace its result to the originating request.",
                )
            ]
        ),
    )

    [(_, document)] = produced(ws, raw)
    assert "request_id" not in document and "ModelRequest" not in document
    prompt = instructed(model)
    assert "an internal field or flag with no independent product/system meaning" in (
        prompt
    )
    assert (
        "A field or parameter is Requirement content only when it carries an "
        "independently meaningful obligation" in prompt
    )


# -- 7. a legitimate non-functional requirement -----------------------------

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


def test_a_legitimate_non_functional_requirement_stays_requirement_level():
    ws, raw, model, result = decompose(
        CREDENTIAL_SOURCE,
        model_output(
            [
                obligation(
                    "NON_FUNCTIONAL",
                    "Keep credentials out of initialization output",
                    CREDENTIAL_REQUIREMENT,
                )
            ]
        ),
    )

    [(_, document)] = produced(ws, raw)
    assert result.candidates[0].startswith("SDLC-NFR-")
    assert section(document, "Requirement") == CREDENTIAL_REQUIREMENT
    assert (
        "NON_FUNCTIONAL is a required quality or operating property of the "
        "delivered system" in instructed(model)
    )


# -- 8. a legitimate system constraint --------------------------------------

KEY_SOURCE = """\
# Model access

## Constraints

- The application must never hold provider API keys; every model call runs
  under the operator's own locally authenticated session.
"""


def test_a_legitimate_system_constraint_stays_requirement_level():
    ws, raw, model, result = decompose(
        KEY_SOURCE,
        model_output(
            [
                obligation(
                    "CONSTRAINT",
                    "Hold no provider API keys",
                    "The application never holds provider API keys; every model "
                    "call runs under the operator's own locally authenticated "
                    "session.",
                )
            ]
        ),
    )

    [(record, _)] = produced(ws, raw)
    assert result.candidates == (record.requirement_id,)
    assert record.requirement_id.startswith("SDLC-CON-")
    assert (
        "CONSTRAINT is a mandatory boundary on valid solutions or operation"
        in instructed(model)
    )


# -- 9. a source gap stays open ---------------------------------------------

OVERRIDE_SOURCE = """\
# Review override

## Requirements and Expected Behavior

- A failed Review returns the Requirement to the human with its failure reasons.

## Open Questions

- May an operator override a failed Review decision? Not decided yet.
- Which queue library should deliver the failure notice?
"""

OVERRIDE_QUESTION = (
    "May an operator override a failed Review decision? The source leaves this "
    "undecided."
)


def test_an_unresolved_source_decision_stays_open_and_is_not_answered():
    ws, raw, model, _ = decompose(
        OVERRIDE_SOURCE,
        model_output(
            [
                obligation(
                    "FUNCTIONAL",
                    "Return failed Reviews to the human",
                    "A failed Review returns the Requirement to the human with its "
                    "failure reasons.",
                    open_questions=OVERRIDE_QUESTION,
                )
            ]
        ),
    )

    [(_, document)] = produced(ws, raw)
    assert section(document, "Open Questions") == OVERRIDE_QUESTION
    for unestablished in ("Detailed Behavior", "Rationale", "Non-Goals"):
        assert section(document, unestablished) == MISSING_INFORMATION
    assert "queue library" not in document, "architecture questions stay downstream"
    prompt = instructed(model)
    assert "Preserve each as a question and never answer it." in prompt
    assert (
        "A question about HOW to satisfy an already understood obligation is an "
        "architecture question" in prompt
    )


# -- 10. no candidate warranted ---------------------------------------------

BACKGROUND_SOURCE = """\
# Worker notes

## Context

Background on the current worker pool: four processes share one SQLite file,
and the scheduler module is `sdlc.jobs.cron`.
"""

NO_OBLIGATION = (
    "The source only describes the current implementation; it states no product "
    "or system obligation."
)


def test_no_candidate_warranted_is_zero_candidates_with_a_reason():
    ws, raw, model, result = decompose(
        BACKGROUND_SOURCE, model_output([], reason=NO_OBLIGATION)
    )

    assert result.candidates == ()
    assert result.no_candidate_reason == NO_OBLIGATION
    assert ws.produces(raw.id) == []
    assert ws.requirements[raw.id].state == "Review"
    assert "There is no target number of candidates." in instructed(model)


# -- peer findings ----------------------------------------------------------

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


def test_a_finding_about_a_non_applied_peer_stays_an_observation():
    ws, raw, _ = build_workspace(standards=[PEER])
    ws.content["raw-secret"] = TIMEOUT_SOURCE
    [peer_root] = ws.documents_attached_to_requirement(PEER.public_id)
    peer_document = ws.content[peer_root.secret]
    finding = {
        "kind": "POSSIBLE_DUPLICATE",
        "requirement_id": PEER.requirement_id,
        "detail": "The candidate restates the peer's timeout obligation.",
    }
    model = FakeModelRuntime([model_output([TIMEOUT_OBLIGATION], [finding])])

    result = process_raw_requirement(ws, model, raw.id)

    assert any("POSSIBLE_DUPLICATE" in f for f in result.findings)
    assert ws.requirements[PEER.id] == PEER
    assert ws.content[peer_root.secret] == peer_document
    assert PEER.id not in ws.derived_from_ids
    assert PEER.id not in ws.produces(raw.id)
    assert PEER.requirement_id in model.calls[0]["context"]
    prompt = instructed(model)
    assert "They never modify them." in prompt
    assert (
        "one that is not Applied is a candidate under review, not approved "
        "authority." in prompt
    )


# -- the prompt itself ------------------------------------------------------

PROMPT = " ".join(INSTRUCTIONS.split())

LEAKAGE_MECHANISMS = (
    (
        "a class, function, module, package, library, framework, programming "
        "language or source file"
    ),
    "an internal field or flag with no independent product/system meaning",
    "an algorithm or internal execution sequence",
    "a worker or process topology",
    "a queue, webhook, polling loop, scheduler or other internal triggering mechanism",
    "a persistence, storage or serialization mechanism",
    "test code, fixtures, mocks or a test framework",
    "a deployment mechanism",
    "an implementation-specific edge case",
)


def test_the_prompt_states_the_anti_implementation_leakage_rule():
    assert "Anti-implementation-leakage rule:" in PROMPT
    assert "Never create a candidate merely because the source mentions:" in PROMPT
    for mechanism in LEAKAGE_MECHANISMS:
        assert mechanism in PROMPT


def test_the_prompt_encodes_no_candidate_count():
    assert "Zero, one or many are all valid" in PROMPT
    assert not re.search(
        r"(?:at least|at most|exactly|up to|no more than) \w+ candidates?", PROMPT
    )


def test_the_prompt_keeps_structured_output_without_reasoning():
    assert "Return ONLY a single JSON object." in PROMPT
    assert "no explanation of your reasoning" in PROMPT
    assert "decide silently; never report these decisions" in PROMPT


def test_the_prompt_states_the_document_structure_rules():
    assert "The title is a single line" in PROMPT
    assert "must not contain a level-1 or level-2 Markdown heading" in PROMPT


def test_the_prompt_shape_lists_exactly_the_candidate_contract_fields():
    shape = INSTRUCTIONS.split('"candidates": [', 1)[1].split('"findings"', 1)[0]

    assert set(re.findall(r'"(\w+)":', shape)) == CANDIDATE_KEYS
