"""RW-R04: Standard Review judges the Requirement at the corrected abstraction.

Whether a Requirement leaks HOW, invents semantics, is a fragment, or is a valid
high-level obligation is a semantic judgement the reviewer makes under the
Review prompt, with the originating RAW source as read-only evidence. Through
the real Review stage with bounded fake-model output, these tests pin what
deterministic code owns: the prompt states each rule, the RAW source reaches
the reviewer only on a path that invokes it, the existing finding kinds carry
every judgement, the verdict is still derived, and Review still writes nothing
but its Review Result and the Ready transition. No live model runs.
"""

from types import SimpleNamespace

from processor_fake import FakeModelRuntime
from review_fake import (
    build_review_workspace,
    confirm,
    finding,
    new_finding,
    reject,
    relation,
    review_output,
    review_results,
    stored_review,
    verify_relation,
)
from sdlc.fibery_workspace import FiberyError, RequirementRecord
from sdlc.raw_processing import MISSING_INFORMATION, NO_OPEN_QUESTIONS
from sdlc.results import StandardReviewResultCode
from sdlc.review_prompt import INSTRUCTIONS
from sdlc.standard_analysis import FindingKind, RelationKind
from sdlc.standard_reviewer import review_standard_requirement
from standard_fake import RAW_ID, set_state

RAW_HEADING = "# Originating RAW requirement source"
PROMPT = " ".join(INSTRUCTIONS.split())
UNESTABLISHED = (
    "detailed_behavior",
    "rationale",
    "acceptance_verification",
    "constraints_edge_cases",
    "non_goals",
)
PERMITTED_MUTATIONS = (
    "create_child_document",
    "write_content",
    "set_requirement_state",
)


def root_holding(requirement, **sections):
    """A Root holding only what its source establishes, as Process left it."""
    content = {key: MISSING_INFORMATION for key in UNESTABLISHED}
    return {
        **content,
        "open_questions": NO_OPEN_QUESTIONS,
        "requirement": requirement,
        **sections,
    }


def review(
    requirement,
    source,
    output,
    findings=(),
    relations=(),
    others=(),
    has_raw=True,
    **sections,
):
    """Review a Root derived from `source`, answered by one bounded response."""
    ws, std, root, _ = build_review_workspace(
        findings=findings,
        relations=relations,
        others=others,
        normalized_changes=root_holding(requirement, **sections),
    )
    if has_raw:
        ws.content["raw-secret"] = source
    else:
        del ws.derived_from_ids[std.id]
    before = SimpleNamespace(
        root=ws.content[root.secret],
        requirements=dict(ws.requirements),
        depends_on={k: list(v) for k, v in ws.depends_on_ids.items()},
        affects={k: list(v) for k, v in ws.affects_ids.items()},
        mutations=len(ws.mutations),
    )
    model = FakeModelRuntime([output])

    result = review_standard_requirement(ws, model, std.id)

    return SimpleNamespace(
        ws=ws,
        std=std,
        root=root,
        result=result,
        model=model,
        before=before,
        mutations=ws.mutations[before.mutations :],
        context=model.calls[0]["context"] if model.calls else "",
    )


def reviewed(run):
    """Assert a successful review wrote only its Result and Ready; return it."""
    assert run.result.code is StandardReviewResultCode.REQUIREMENT_REVIEWED, run.result
    ws, std = run.ws, run.std
    assert ws.content[run.root.secret] == run.before.root, "Root never rewritten"
    assert all(m.startswith(PERMITTED_MUTATIONS) for m in run.mutations)
    assert f"write_content {run.root.secret}" not in run.mutations
    assert [m for m in run.mutations if m.startswith("set_requirement_state")] == [
        f"set_requirement_state {std.id} Ready"
    ]
    for entity_id, record in run.before.requirements.items():
        if entity_id != std.id:
            assert ws.requirements[entity_id] == record, "no other Requirement moves"
    assert ws.requirements[std.id].revision == run.before.requirements[std.id].revision
    assert ws.depends_on_ids == run.before.depends_on
    assert ws.affects_ids == run.before.affects
    return stored_review(ws)


def raw_section(run):
    """The RAW evidence section; the RAW document carries headings of its own."""
    after = run.context.split(RAW_HEADING, 1)[1]
    return after.split("# Findings claimed by the earlier analysis", 1)[0]


def new_kinds(stored):
    return [(f.kind, f.severity.value, f.requirement_id) for f in stored.new_findings]


TIMEOUT_SOURCE = """\
# Provider execution

## Requirements and Expected Behavior

Provider execution must stop within the configured execution time limit and
report the timeout outcome to the caller.
"""

TIMEOUT_REQUIREMENT = (
    "Provider execution must stop within the configured execution time limit "
    "and report the timeout outcome to the caller."
)
LEAKED_BEHAVIOR = (
    "`run_model()` starts the provider in a subprocess; a watchdog thread sends "
    "SIGTERM, waits five seconds, then SIGKILLs the process group."
)

ARGV_SOURCE = """\
# Provider execution safety

## Constraints

Provider execution must use argv and must never use a shell.
"""

ARGV = "Provider execution must use argv and must never use a shell."

PEER_ID = "SDLC-FR-0041"
PEER = RequirementRecord(
    id="std-peer",
    public_id="41",
    requirement_id=PEER_ID,
    title="Stop provider execution at the limit",
    type_name="Standard",
    state="Ready",
    revision=2,
    project_id="p-1",
    source_fingerprint=None,
)


# -- 1. a valid high-level Requirement --------------------------------------


def test_a_valid_high_level_requirement_is_not_penalized_and_passes():
    run = review(TIMEOUT_REQUIREMENT, TIMEOUT_SOURCE, review_output())

    stored = reviewed(run)
    assert stored.verdict.value == "PASS"
    assert stored.new_findings == ()
    assert "Missing downstream design is not a defect." in PROMPT
    assert "A valid high-level Requirement may deserve no finding at all." in PROMPT
    assert "Do not require test design for a Requirement to pass." in PROMPT


# -- 2. independent verification of a Process leakage claim -----------------


def test_review_confirms_a_process_leakage_finding():
    run = review(
        TIMEOUT_REQUIREMENT,
        TIMEOUT_SOURCE,
        review_output(finding_verifications=[confirm(0, "WARNING")]),
        findings=[
            finding(
                FindingKind.IMPLEMENTATION_LEAKAGE,
                "Detailed Behavior prescribes a watchdog thread and SIGKILL.",
            )
        ],
        detailed_behavior=LEAKED_BEHAVIOR,
    )

    stored = reviewed(run)
    assert "[0] IMPLEMENTATION_LEAKAGE:" in run.context
    assert stored.finding_verifications[0].outcome.value == "CONFIRMED"
    assert stored.verdict.value == "NEEDS_WORK"


def test_review_rejects_a_leakage_claim_when_the_source_mandates_it():
    run = review(
        ARGV,
        ARGV_SOURCE,
        review_output(
            finding_verifications=[
                reject(0, "The originating RAW source explicitly mandates argv.")
            ]
        ),
        findings=[finding(FindingKind.IMPLEMENTATION_LEAKAGE, "argv is a mechanism.")],
    )

    stored = reviewed(run)
    assert ARGV in raw_section(run), "the mandate is in the reviewer's evidence"
    assert stored.finding_verifications[0].outcome.value == "REJECTED"
    assert stored.verdict.value == "PASS"
    assert (
        "A technical mechanism the source explicitly mandates is legitimate "
        "Requirement content, not leakage" in PROMPT
    )


# -- 3. leakage Process missed ------------------------------------------------


def test_review_reports_leakage_the_process_missed():
    detail = "Detailed Behavior prescribes a watchdog thread and SIGKILL escalation."
    run = review(
        TIMEOUT_REQUIREMENT,
        TIMEOUT_SOURCE,
        review_output(
            new_findings=[new_finding("IMPLEMENTATION_LEAKAGE", "WARNING", detail)]
        ),
        detailed_behavior=LEAKED_BEHAVIOR,
    )

    stored = reviewed(run)
    assert new_kinds(stored) == [(FindingKind.IMPLEMENTATION_LEAKAGE, "WARNING", None)]
    assert stored.verdict.value == "NEEDS_WORK"
    assert "The earlier analysis is a set of claims, not a conclusion." in PROMPT
    assert "do not simply agree with it, and look for what it missed." in PROMPT


# -- 4. Task/test mechanics disguised as acceptance --------------------------

TEST_MECHANICS = (
    "Run pytest with fixture `ready_requirement`, patch `FiberyAdapter.write` "
    "with a mock and assert `processing_status == 'PENDING'`."
)


def test_test_mechanics_in_acceptance_are_reported_as_leakage():
    run = review(
        TIMEOUT_REQUIREMENT,
        TIMEOUT_SOURCE,
        review_output(
            new_findings=[
                new_finding(
                    "IMPLEMENTATION_LEAKAGE",
                    "WARNING",
                    "Acceptance / Verification prescribes pytest, a fixture and a mock.",
                )
            ]
        ),
        acceptance_verification=TEST_MECHANICS,
    )

    stored = reviewed(run)
    assert new_kinds(stored) == [(FindingKind.IMPLEMENTATION_LEAKAGE, "WARNING", None)]
    assert (
        "This includes Task or test mechanics disguised as Acceptance / "
        "Verification: test commands, mocks, fixtures, internal function calls"
        in PROMPT
    )


# -- 5. a source-mandated technical constraint ---------------------------------


def test_a_source_mandated_constraint_is_not_flagged():
    run = review(ARGV, ARGV_SOURCE, review_output())

    stored = reviewed(run)
    assert stored.verdict.value == "PASS"
    assert ARGV in raw_section(run)
    assert (
        '"Current implementation uses argv" or "Suggested approach: use argv" '
        "does not make argv Requirement truth." in PROMPT
    )


# -- 6. source invention -------------------------------------------------------

INVENTED = "A timed-out execution is retried three times before the caller is told."


def test_source_invention_is_reported_as_inconsistent_with_the_source():
    detail = (
        "The retry-three-times obligation is unsupported by the originating "
        f"source {RAW_ID}, which requires only a bounded execution and a timeout."
    )
    run = review(
        TIMEOUT_REQUIREMENT,
        TIMEOUT_SOURCE,
        review_output(new_findings=[new_finding("INCONSISTENT", "WARNING", detail)]),
        constraints_edge_cases=INVENTED,
    )

    stored = reviewed(run)
    assert f"<!-- RAW {RAW_ID} -->" in raw_section(run)
    assert "must stop within the configured execution time limit" in raw_section(run)
    assert new_kinds(stored) == [(FindingKind.INCONSISTENT, "WARNING", None)]
    assert "unsupported by the originating source" in stored.new_findings[0].detail
    assert (
        "Say in the detail that the statement is unsupported by, or inconsistent "
        "with, the originating source." in PROMPT
    )
    assert "A paraphrase that keeps the source's meaning is not invention." in PROMPT


# -- 7. unjustified fragmentation ----------------------------------------------


def test_a_fragment_of_one_source_obligation_is_incomplete_not_non_atomic():
    detail = (
        "Fragment of one source obligation: the source requires execution to stop "
        "within the limit and report the timeout; this Requirement keeps only the "
        f"reporting half, and peer {PEER_ID} holds the rest."
    )
    run = review(
        "The caller receives a timeout outcome when execution times out.",
        TIMEOUT_SOURCE,
        review_output(new_findings=[new_finding("INCOMPLETE", "WARNING", detail)]),
        others=[PEER],
    )

    stored = reviewed(run)
    assert new_kinds(stored) == [(FindingKind.INCOMPLETE, "WARNING", None)]
    assert PEER_ID in stored.new_findings[0].detail, "a peer is cited in detail"
    assert (
        "INCOMPLETE for unjustified fragmentation: the Requirement is only a "
        "fragment of one source-established obligation" in PROMPT
    )
    assert "NON_ATOMIC only for the opposite shape" in PROMPT
    assert "Never use it for a fragment" in PROMPT


# -- 8. genuine non-atomicity ----------------------------------------------------


def test_independent_product_obligations_are_still_non_atomic():
    run = review(
        "A user can export any report they can view as a CSV file, and every "
        "export is recorded in the audit log with the requesting user.",
        "Users can export reports as CSV. Every export is audited.",
        review_output(
            new_findings=[
                new_finding(
                    "NON_ATOMIC",
                    "WARNING",
                    "CSV export and export auditing are independent obligations.",
                )
            ]
        ),
    )

    stored = reviewed(run)
    assert new_kinds(stored) == [(FindingKind.NON_ATOMIC, "WARNING", None)]
    assert (
        "never demand one Requirement per sentence, field, parameter, error case, "
        "status or technical detail." in PROMPT
    )


# -- 9. a product open question --------------------------------------------------

OVERRIDE_SOURCE = """\
# Review override

## Requirements and Expected Behavior

A failed Review returns the Requirement to the human with its failure reasons.

## Open Questions

May an operator override a failed Review decision? Not decided yet.
"""


def test_an_open_product_question_is_not_a_defect_merely_for_being_open():
    run = review(
        "A failed Review returns the Requirement to the human with its failure "
        "reasons.",
        OVERRIDE_SOURCE,
        review_output(),
        open_questions="May an operator override a failed Review decision?",
    )

    stored = reviewed(run)
    assert stored.verdict.value == "PASS"
    assert "do not report it merely because it is unresolved." in PROMPT


# -- 10. an architecture-only question -------------------------------------------


def test_a_missing_architecture_decision_is_not_incomplete():
    source = TIMEOUT_SOURCE + (
        "\nWhich cancellation mechanism enforces the limit is for the architects.\n"
    )
    run = review(TIMEOUT_REQUIREMENT, source, review_output())

    stored = reviewed(run)
    assert stored.new_findings == ()
    assert stored.verdict.value == "PASS"
    assert (
        "An unanswered architecture question is not missing Requirement content"
        in PROMPT
    )


# -- 11. genuine source gaps and contradictions ----------------------------------

RUNTIME_SOURCE = TIMEOUT_SOURCE + "\nThe limit applies to every configured runtime.\n"


def test_genuine_source_gaps_and_contradictions_are_still_caught():
    run = review(
        TIMEOUT_REQUIREMENT,
        RUNTIME_SOURCE,
        review_output(
            new_findings=[
                new_finding(
                    "MISSING_CONSTRAINT",
                    "WARNING",
                    "The source applies the limit to every configured runtime.",
                ),
                new_finding(
                    "INCONSISTENT",
                    "BLOCKING",
                    "Limiting it to the default runtime contradicts the source.",
                ),
            ]
        ),
        constraints_edge_cases="The limit applies to the default runtime only.",
    )

    stored = reviewed(run)
    assert new_kinds(stored) == [
        (FindingKind.MISSING_CONSTRAINT, "WARNING", None),
        (FindingKind.INCONSISTENT, "BLOCKING", None),
    ]
    assert stored.verdict.value == "BLOCKING"
    assert run.ws.requirements[run.std.id].state == "Ready", "BLOCKING reaches Ready"
    assert "A gap must be a Requirement-level gap, not an undecided HOW." in PROMPT


# -- 12. peer comparison -----------------------------------------------------------


def test_peer_comparison_findings_are_verified_and_reported_without_mutation():
    run = review(
        TIMEOUT_REQUIREMENT,
        TIMEOUT_SOURCE,
        review_output(
            finding_verifications=[confirm(0, "WARNING")],
            new_findings=[
                {
                    "kind": "POSSIBLE_CONFLICT",
                    "severity": "INFO",
                    "requirement_id": PEER_ID,
                    "detail": f"{PEER_ID} stops execution without reporting it.",
                }
            ],
        ),
        findings=[
            finding(
                FindingKind.POSSIBLE_DUPLICATE,
                "The peer states the stop half.",
                requirement_id=PEER_ID,
            )
        ],
        others=[PEER],
    )
    [peer_root] = run.ws.documents_attached_to_requirement(PEER.public_id)

    stored = reviewed(run)
    assert new_kinds(stored) == [(FindingKind.POSSIBLE_CONFLICT, "INFO", PEER_ID)]
    assert run.ws.content[peer_root.secret].startswith(f"# {PEER_ID} — ")
    assert f"# {PEER_ID} — {PEER.title}" in run.context, "peer Root is evidence"


# -- 13. relation verification -----------------------------------------------------


def test_relation_verifications_stay_evidence_and_are_never_written():
    run = review(
        TIMEOUT_REQUIREMENT,
        TIMEOUT_SOURCE,
        review_output(
            relation_verifications=[
                verify_relation("DEPENDS_ON", PEER_ID, "CONFIRMED"),
                verify_relation(
                    "AFFECTS", "SDLC-NFR-0012", "REJECTED", "No shared behavior."
                ),
            ]
        ),
        relations=[
            relation(RelationKind.DEPENDS_ON, PEER_ID),
            relation(RelationKind.AFFECTS, "SDLC-NFR-0012"),
        ],
        others=[PEER],
    )

    stored = reviewed(run)
    assert [(r.kind, r.requirement_id) for r in stored.confirmed_relations] == [
        (RelationKind.DEPENDS_ON, PEER_ID)
    ]
    assert not any(
        m.startswith(("add_depends_on", "add_affects")) for m in run.mutations
    )


# -- 14. a RAW source read failure -------------------------------------------------


def test_a_raw_source_read_failure_refuses_before_the_model_and_any_write():
    ws, std, _root, _ = build_review_workspace(
        normalized_changes=root_holding(TIMEOUT_REQUIREMENT)
    )
    ws.failures["derived_from"] = FiberyError("Fibery read timed out")
    mutations = len(ws.mutations)
    model = FakeModelRuntime([review_output()])

    result = review_standard_requirement(ws, model, std.id)

    assert result.code is StandardReviewResultCode.FIBERY_READ_FAILED
    assert "originating RAW Requirement" in result.message
    assert not model.was_invoked and not result.model_invoked
    assert review_results(ws) == []
    assert ws.mutations[mutations:] == []
    assert ws.requirements[std.id].state == "Review"


# -- 15. no RAW ancestry -------------------------------------------------------------


def test_a_requirement_without_raw_ancestry_is_still_reviewable():
    run = review(TIMEOUT_REQUIREMENT, "", review_output(), has_raw=False)

    stored = reviewed(run)
    assert f"{RAW_HEADING}\n(none)" in run.context
    assert stored.verdict.value == "PASS"
    assert (
        "When no RAW source is supplied, reach no source-fidelity conclusion from "
        "its absence" in PROMPT
    )


# -- 16. evidence integrity: RAW is read only when the reviewer runs ---------------


def test_a_no_change_review_neither_reads_nor_binds_the_raw_source():
    run = review(TIMEOUT_REQUIREMENT, TIMEOUT_SOURCE, review_output())
    reviewed(run)
    [result_node] = review_results(run.ws)
    assert "must stop within the configured" not in run.ws.content[result_node.secret]

    ws, std = run.ws, run.std
    set_state(ws, std, "Review")
    ws.content["raw-secret"] = "# Provider execution\n\nThe source was edited.\n"
    ws.failures["derived_from"] = FiberyError("would fail if it were read")
    calls = len(ws.calls)
    model = FakeModelRuntime([review_output()])

    again = review_standard_requirement(ws, model, std.id)

    assert again.code is StandardReviewResultCode.NO_CHANGES_TO_REVIEW
    assert not model.was_invoked
    assert "derived_from" not in ws.calls[calls:]
    assert len(review_results(ws)) == 1


# -- the contract itself -------------------------------------------------------------


def test_the_finding_vocabulary_is_unchanged():
    assert [kind.value for kind in FindingKind] == [
        "INCOMPLETE",
        "AMBIGUOUS",
        "NON_ATOMIC",
        "INCONSISTENT",
        "NOT_TESTABLE",
        "MISSING_CONSTRAINT",
        "MISSING_EDGE_CASE",
        "IMPLEMENTATION_LEAKAGE",
        "POSSIBLE_DUPLICATE",
        "POSSIBLE_CONFLICT",
        "POSSIBLE_CHANGE",
        "POSSIBLE_SUPERSESSION",
    ]


def test_the_review_prompt_states_the_what_how_boundary_and_its_evidence():
    assert "A Standard Requirement states WHAT must be true." in PROMPT
    assert "Review the Requirement at that level." in PROMPT
    assert (
        "The originating RAW requirement source is read-only evidence of what the "
        "source actually established." in PROMPT
    )
    assert "IMPLEMENTATION_LEAKAGE: downstream HOW presented as Requirement truth" in (
        PROMPT
    )


def test_the_review_prompt_stays_structured_verdictless_and_non_prescriptive():
    assert "Return ONLY a single JSON object." in PROMPT
    assert "no explanation of your reasoning" in PROMPT
    assert "Do not state an overall verdict" in PROMPT
    assert (
        "do not recommend an implementation, a design or replacement wording." in PROMPT
    )
