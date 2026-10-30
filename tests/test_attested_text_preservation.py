"""Attested-Text-Preservation-v0.1: an attested text in the input comes back verbatim.

The live case is ARP1 Gate 3L3: FR-0129's Root held the operator-attested
D6-A paragraph, and Process 4's normalization split its last sentence ("…
segments, does not permit …" became "… segments. It does not permit …"). The
output still passed every check, so a paraphrase of a human decision became
the Requirement's text. Code now compares the input with the normalized output
and refuses before anything is written.
"""

from __future__ import annotations

import pytest

from processor_fake import FakeModelRuntime
from review_fake import review_output
from sdlc.autonomy_policy import DISABLED, AutonomyPolicies
from sdlc.human_attestation import HumanAttestation, HumanAttestations
from sdlc.process_result import parse_process_result
from sdlc.results import StandardProcessResultCode as ProcessCode
from sdlc.standard_processor import process_standard_requirement
from sdlc.standard_reviewer import review_standard_requirement
from standard_fake import REQUIREMENT_ID, analysis_output, rendered_document, set_state
from test_autonomous_resolution import artifacts, latest_process, scene
from test_human_attestation import (
    DECISION,
    human_decision_at_ready,
    human_edit,
    open_question_reviewed,
    second_process,
)

ENTITY = "std-uuid-1"
# The approved ARP1 D6-A text, byte for byte (Gate 3L1).
D6A = (
    "For GET /v1/uppercase, rejection before application-handler dispatch because "
    "the encoded request-target exceeds the deployment's single effective maximum "
    "supported request-target length, which must be at least 8,000 octets, is a "
    "protocol-level length failure outside this Requirement's HTTP 200 JSON response "
    "guarantee. Such a request may receive HTTP 414 URI Too Long even when its query "
    "parameters would otherwise satisfy this Requirement's valid-request definition "
    "under the WHATWG application/x-www-form-urlencoded parsing algorithm. This "
    "clarification does not change the valid-request definition, including the "
    "treatment of empty ampersand-delimited segments, does not permit HTTP 414 for "
    "request-targets at or below the effective maximum solely because of their "
    "length, and does not weaken the HTTP 200 guarantee for valid requests that "
    "reach the application handler."
)
# Exactly what Gate 3L3's Process 4 wrote in its place.
D6A_AS_NORMALIZED = D6A.replace(
    "segments, does not permit", "segments. It does not permit"
).replace("length, and does not weaken", "length. It does not weaken")
D1 = (
    "The HTTP 200 JSON response guarantee applies to syntactically well-formed HTTP "
    "requests that reach the application handler."
)
FIRST = "Value length boundaries are 1 and 32 characters inclusive."
CONSTRAINTS = f"{FIRST}\n\n{D1}\n\n{D6A}"


def attested(*texts, entity=ENTITY, requirement_id=REQUIREMENT_ID):
    """A TEST-ONLY attestation snapshot; never configuration."""
    return AutonomyPolicies(
        attestations=HumanAttestations(
            tuple(
                HumanAttestation("SDLC", requirement_id, entity, text, "Operator")
                for text in texts
            )
        )
    )


D6A_ONLY = attested(D6A)
BOTH = attested(D1, D6A)


def rooted(constraints=CONSTRAINTS, **sections):
    """A Requirement in Process whose Root already holds the given sections."""
    ws, requirement, root = scene()
    ws.content[root.secret] = rendered_document(
        constraints_edge_cases=constraints, **sections
    )
    return ws, requirement, root


def run(ws, record, policies, /, **sections):
    model = FakeModelRuntime([analysis_output(normalized_changes=sections)])
    result = process_standard_requirement(ws, model, record.id, policies=policies)
    return result, model


def refused(policies, /, **sections):
    """Run once against CONSTRAINTS; require a refusal that wrote nothing."""
    ws, requirement, _ = rooted()
    before = (dict(ws.content), list(ws.documents), dict(ws.requirements))
    mutations = list(ws.mutations)
    result, model = run(ws, requirement, policies, **sections)
    assert result.code is ProcessCode.INVALID_MODEL_OUTPUT, result
    assert len(model.calls) == 1
    assert ws.mutations == mutations
    assert (dict(ws.content), list(ws.documents), dict(ws.requirements)) == before
    assert artifacts(ws, "Process Result") == []
    assert ws.requirements[requirement.id].state == "Process"
    return " ".join(result.details)


def processed(policies, constraints=CONSTRAINTS, /, **sections):
    ws, requirement, root = rooted(constraints)
    result, _ = run(ws, requirement, policies, **sections)
    assert result.code is ProcessCode.REQUIREMENT_PROCESSED, result
    return ws, requirement, root


def snapshot(ws):
    return (
        dict(ws.content),
        list(ws.documents),
        dict(ws.requirements),
        list(ws.mutations),
    )


def unchanged(root):
    """The output sections that return `root`'s sections as they are, except
    the ones a test names itself."""
    return {
        "constraints_edge_cases" if key == "constraints" else key: value
        for key, value in root.items()
    }


def refused_from(policies, root, /, **sections):
    """Run once from a Root holding `root`; require a refusal that wrote nothing."""
    ws, requirement, _ = rooted(**root)
    before = snapshot(ws)
    result, model = run(ws, requirement, policies, **(unchanged(root) | sections))
    assert result.code is ProcessCode.INVALID_MODEL_OUTPUT, result
    assert len(model.calls) == 1 and snapshot(ws) == before
    assert artifacts(ws, "Process Result") == []
    return " ".join(result.details)


def processed_from(policies, root, /, **sections):
    ws, requirement, document = rooted(**root)
    result, _ = run(ws, requirement, policies, **(unchanged(root) | sections))
    assert result.code is ProcessCode.REQUIREMENT_PROCESSED, result
    return ws.content[document.secret]


def fingerprint(policies, index=0):
    return policies.attestations.attestations[index].fingerprint[:12]


# -- the Gate 3L3 regression ---------------------------------------------------


def test_the_gate_3l3_punctuation_change_is_refused_before_anything_is_written():
    detail = refused(
        D6A_ONLY,
        constraints_edge_cases=f"{FIRST}\n\n{D1}\n\n{D6A_AS_NORMALIZED}",
    )
    fingerprint = D6A_ONLY.attestations.attestations[0].fingerprint[:12]
    assert (
        f"attestation {fingerprint} ALTERED_OR_DELETED (Constraints & Edge Cases)"
        in detail
    )
    assert REQUIREMENT_ID in detail
    # Diagnostics name the attestation and section, never the text.
    assert D6A not in detail and D6A_AS_NORMALIZED not in detail


def test_the_exact_d6a_still_produces_a_valid_process_result():
    ws, requirement, root = processed(D6A_ONLY, constraints_edge_cases=CONSTRAINTS)
    assert ws.requirements[requirement.id].state == "Review"
    assert ws.content[root.secret].count(D6A) == 1
    _, result = latest_process(ws)
    assert result.iteration == 1 and D6A in result.normalized.constraints_edge_cases


# -- what counts as a change ---------------------------------------------------


@pytest.mark.parametrize(
    ("constraints", "category"),
    [
        (
            f"{FIRST}\n\n{D1}\n\n{D6A.replace('dispatch because', 'dispatch since')}",
            "ALTERED_OR_DELETED",
        ),  # an equivalent paraphrase
        (
            f"{FIRST}\n\n{D1}\n\n{D6A.rsplit(' This clarification', 1)[0]}",
            "ALTERED_OR_DELETED",
        ),  # shortened
        (f"{FIRST}\n\n{D1}", "ALTERED_OR_DELETED"),  # deleted
        (f"{FIRST}\n\n{D1}\n\n{D6A}\n\n{D6A}", "DUPLICATED"),
        (
            f"{FIRST}\n\n{D1}\n\n{D6A} Proxies may also answer 431.",
            "PARAGRAPH_CHANGED",
        ),  # extended within its paragraph
        (f"{FIRST}\n\n{D1} {D6A}", "PARAGRAPH_CHANGED"),  # merged into D1's paragraph
    ],
    ids=["paraphrased", "shortened", "deleted", "duplicated", "extended", "merged"],
)
def test_any_change_to_the_attested_paragraph_is_refused(constraints, category):
    detail = refused(D6A_ONLY, constraints_edge_cases=constraints)
    assert f"{category} (Constraints & Edge Cases)" in detail


def test_moving_it_to_another_section_is_refused():
    detail = refused(
        D6A_ONLY,
        constraints_edge_cases=f"{FIRST}\n\n{D1}",
        detailed_behavior=f"Preflight runs the auth check before any call.\n\n{D6A}",
    )
    assert "MOVED (Constraints & Edge Cases, Detailed Behavior)" in detail


def test_unattested_wording_around_it_is_still_normalized():
    ws, _, root = processed(
        D6A_ONLY,
        constraints_edge_cases=f"Values are 1 to 32 characters long.\n\n{D1}\n\n{D6A}",
        requirement="The service must answer every valid request.",
    )
    assert "Values are 1 to 32 characters long." in ws.content[root.secret]
    assert ws.content[root.secret].count(D6A) == 1


def test_two_attestations_in_one_section_are_protected_independently():
    processed(BOTH, constraints_edge_cases=CONSTRAINTS)
    detail = refused(
        BOTH, constraints_edge_cases=f"{FIRST}\n\n{D1}\n\n{D6A_AS_NORMALIZED}"
    )
    d1, d6a = (a.fingerprint[:12] for a in BOTH.attestations.attestations)
    assert f"attestation {d6a} ALTERED_OR_DELETED" in detail and d1 not in detail
    detail = refused(BOTH, constraints_edge_cases=f"{FIRST}\n\n{D6A}")
    assert f"attestation {d1} ALTERED_OR_DELETED" in detail and d6a not in detail


# -- scope -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "policies",
    [
        attested(D6A, entity="std-uuid-2"),  # another entity, same Requirement ID
        attested(D6A, requirement_id="SDLC-FR-0032"),  # same entity, another ID
        DISABLED,  # nothing attested
    ],
    ids=["other-entity", "other-requirement", "none"],
)
def test_text_attested_for_no_one_here_is_ordinary_wording(policies):
    ws, _, root = processed(
        policies, constraints_edge_cases=f"{FIRST}\n\n{D1}\n\n{D6A_AS_NORMALIZED}"
    )
    assert D6A_AS_NORMALIZED in ws.content[root.secret]


def test_an_attestation_absent_from_the_input_is_not_injected():
    ws, _, root = processed(
        D6A_ONLY,
        f"{FIRST}\n\n{D1}",
        constraints_edge_cases=f"{FIRST}\n\n{D1}",
    )
    assert D6A not in ws.content[root.secret]


def test_the_model_may_not_insert_an_attestation_the_input_lacks():
    ws, requirement, root = rooted(f"{FIRST}\n\n{D1}")
    content = ws.content[root.secret]
    result, _ = run(
        ws, requirement, D6A_ONLY, constraints_edge_cases=f"{FIRST}\n\n{D1}\n\n{D6A}"
    )
    assert result.code is ProcessCode.INVALID_MODEL_OUTPUT
    assert "INSERTED (Constraints & Edge Cases)" in " ".join(result.details)
    assert ws.content[root.secret] == content


# -- the authority rules are unchanged -------------------------------------------


def test_a_material_answer_citing_the_preserved_attested_text_still_passes():
    ws, requirement, _, _ = human_decision_at_ready()
    assert ws.requirements[requirement.id].state == "Ready"


def test_a_material_answer_citing_unattested_text_is_still_refused_as_before():
    ws, requirement, root = open_question_reviewed()
    human_edit(ws, root)
    result, _ = second_process(ws, requirement, policies=DISABLED)
    assert result.code is ProcessCode.INVALID_MODEL_OUTPUT
    assert "Unattested items: R0001.Q0" in " ".join(result.details)


def test_a_rework_that_alters_the_attested_decision_leaves_history_untouched():
    ws, requirement, root = open_question_reviewed()
    human_edit(ws, root)
    history = {
        d.secret: ws.content[d.secret] for d in ws.documents if d.secret != root.secret
    }
    content, documents, mutations = (
        ws.content[root.secret],
        list(ws.documents),
        list(ws.mutations),
    )
    result, model = second_process(
        ws,
        requirement,
        normalized_changes={
            "constraints_edge_cases": DECISION.replace(", whether", "; whether")
        },
    )
    assert result.code is ProcessCode.INVALID_MODEL_OUTPUT
    assert "ALTERED_OR_DELETED" in " ".join(result.details)
    assert len(model.calls) == 1 and ws.mutations == mutations
    assert ws.content[root.secret] == content and ws.documents == documents
    assert {s: ws.content[s] for s in history} == history
    assert len(artifacts(ws, "Process Result")) == 1
    second_process(ws, requirement)  # the verbatim answer still goes through
    assert len(artifacts(ws, "Process Result")) == 2


def test_an_earlier_result_that_paraphrased_an_attested_text_stays_readable():
    """History is never re-certified: a Process Result persisted before the text
    was attested, or before this rule, parses exactly as it did."""
    ws, _, _ = processed(
        DISABLED, constraints_edge_cases=f"{FIRST}\n\n{D1}\n\n{D6A_AS_NORMALIZED}"
    )
    node, result = latest_process(ws)
    assert result.iteration == 1
    assert parse_process_result(ws.content[node.secret]).normalized == result.normalized


# -- Gate 3L5 F01: a replay applies its output now, so it is checked now ---------

PARAPHRASED = f"{FIRST}\n\n{D1}\n\n{D6A_AS_NORMALIZED}"


def persisted_then_reverted(constraints, reviewed=False):
    """A Result whose output holds `constraints`, persisted while nothing was
    protected (as before this rule), and then its input restored: the one
    snapshot `--resume-result` applies to."""
    ws, requirement, root = rooted()
    restored = ws.content[root.secret]
    result, _ = run(ws, requirement, DISABLED, constraints_edge_cases=constraints)
    assert result.code is ProcessCode.REQUIREMENT_PROCESSED, result
    if reviewed:
        reviewer = FakeModelRuntime([review_output()])
        assert review_standard_requirement(ws, reviewer, requirement.id).is_normal
    ws.content[root.secret] = restored
    set_state(ws, requirement, "Process")
    [node] = artifacts(ws, "Process Result")
    return ws, requirement, root, node


def resume(ws, requirement, node, policies):
    model = FakeModelRuntime([])
    result = process_standard_requirement(
        ws, model, requirement.id, resume_result=node.id, policies=policies
    )
    return result, model


def test_a_replay_that_paraphrases_the_attested_text_is_refused_without_a_model():
    ws, requirement, root, node = persisted_then_reverted(PARAPHRASED)
    before = snapshot(ws)
    result, model = resume(ws, requirement, node, D6A_ONLY)
    assert result.code is ProcessCode.PROCESSING_STATE_CONFLICT, result
    assert not model.was_invoked and result.model_invoked is False
    assert result.created == ()
    # No Root rewrite, no State change, no new artifact, history untouched.
    assert snapshot(ws) == before
    assert ws.requirements[requirement.id].state == "Process"
    assert D6A in ws.content[root.secret]
    assert len(artifacts(ws, "Process Result")) == 1
    assert "Replaying" in result.message and "no model was run" in result.message
    assert f"--new-iteration-after {node.id}" in result.message
    detail = " ".join((result.message, *result.details))
    assert (
        f"attestation {fingerprint(D6A_ONLY)} ALTERED_OR_DELETED "
        "(Constraints & Edge Cases)" in detail
    )
    assert D6A not in detail and D6A_AS_NORMALIZED not in detail


def test_the_refused_replay_leaves_nothing_for_review_to_consume():
    ws, requirement, _, node = persisted_then_reverted(PARAPHRASED)
    resume(ws, requirement, node, D6A_ONLY)
    # Review admits only State Review; the Requirement never left Process.
    assert ws.requirements[requirement.id].state == "Process"


def test_a_replay_that_preserves_the_attested_text_is_applied_as_before():
    preserving = f"Values are 1 to 32 characters long.\n\n{D1}\n\n{D6A}"
    ws, requirement, root, node = persisted_then_reverted(preserving)
    history = ws.content[node.secret]
    result, model = resume(ws, requirement, node, D6A_ONLY)
    assert result.code is ProcessCode.REQUIREMENT_PROCESSED, result
    assert not model.was_invoked and result.iteration == 1
    assert ws.requirements[requirement.id].state == "Review"
    assert "Values are 1 to 32 characters long." in ws.content[root.secret]
    assert ws.content[root.secret].count(D6A) == 1
    assert ws.content[node.secret] == history


def test_a_replay_with_nothing_attested_for_it_is_unchanged():
    ws, requirement, root, node = persisted_then_reverted(PARAPHRASED)
    result, _ = resume(ws, requirement, node, attested(D6A, entity="std-uuid-2"))
    assert result.code is ProcessCode.REQUIREMENT_PROCESSED, result
    assert D6A_AS_NORMALIZED in ws.content[root.secret]


def test_the_existing_replay_guards_still_run_first():
    """A reviewed iteration is refused for that reason, exactly as before."""
    ws, requirement, _, node = persisted_then_reverted(PARAPHRASED, reviewed=True)
    before = snapshot(ws)
    result, model = resume(ws, requirement, node, D6A_ONLY)
    assert result.code is ProcessCode.PROCESSING_STATE_CONFLICT
    assert "already reviewed iteration 1" in result.message
    assert not model.was_invoked and snapshot(ws) == before


# -- Gate 3L5 F02/F06: structure is the parser's, labels are the schema's -------

FAKE_SECTION = "## Constraints & Edge Cases"


@pytest.mark.parametrize("fence", ["```", "````"])
def test_a_heading_inside_fenced_code_does_not_open_a_section(fence):
    detail = refused(
        D6A_ONLY,
        constraints_edge_cases=PARAPHRASED,
        non_goals=f"{fence}\n{FAKE_SECTION}\n\n{D6A}\n{fence}",
    )
    assert (
        f"attestation {fingerprint(D6A_ONLY)} MOVED "
        "(Constraints & Edge Cases, Non-Goals)" in detail
    )
    assert D6A not in detail


def test_a_tilde_fenced_heading_is_refused_by_the_reserved_heading_rule():
    """The schema check reads only backtick fences as literal, so a tilde fence
    holding a section heading is refused before preservation is judged."""
    detail = refused(
        D6A_ONLY,
        constraints_edge_cases=PARAPHRASED,
        non_goals=f"~~~\n{FAKE_SECTION}\n\n{D6A}\n~~~",
    )
    assert "heading levels 1 and 2 are reserved" in detail


def test_a_fenced_heading_in_the_input_is_not_a_section_either():
    """Input side: the copy in Non-Goals' code is in Non-Goals, so bringing it
    out into the real Constraints section is a move."""
    root = {
        "constraints": f"{FIRST}\n\n{D1}",
        "non_goals": f"```\n{FAKE_SECTION}\n\n{D6A}\n```",
    }
    processed_from(D6A_ONLY, root)  # kept as it is
    detail = refused_from(
        D6A_ONLY,
        root,
        constraints_edge_cases=f"{FIRST}\n\n{D1}\n\n{D6A}",
        non_goals="Nothing else.",
    )
    assert "MOVED (Constraints & Edge Cases, Non-Goals)" in detail


@pytest.mark.parametrize(
    "constraints",
    [
        f"{FIRST}\n\n{D1}\n\n```\n{D6A}\n```",
        f"{FIRST}\n\n{D1}\n\n~~~text\n{D6A}\n~~~",
        f"{FIRST}\n\n{D1}\n\n    {D6A}",
        f"{FIRST}\n\n{D1}\n\n> {D6A}",
        f"{FIRST}\n\n{D1}\n\n- {D6A}",
    ],
    ids=["backticks", "tildes", "indented", "quote", "list"],
)
def test_turning_the_attested_paragraph_into_another_block_is_refused(constraints):
    detail = refused(D6A_ONLY, constraints_edge_cases=constraints)
    assert "PARAGRAPH_CHANGED (Constraints & Edge Cases)" in detail


def test_text_inside_a_larger_paragraph_may_not_move_into_code():
    root = {"constraints": f"{FIRST}\n\n{D1} {D6A}"}
    processed_from(D6A_ONLY, root, constraints_edge_cases=f"{FIRST}\n\n{D1} {D6A}")
    detail = refused_from(
        D6A_ONLY, root, constraints_edge_cases=f"{FIRST}\n\n{D1}\n\n```\n{D6A}\n```"
    )
    assert "PARAGRAPH_CHANGED (Constraints & Edge Cases)" in detail


def test_a_crafted_heading_in_the_root_is_never_echoed():
    ws, requirement, root = rooted()
    ws.content[root.secret] += f"\n## {D6A}\n\nOperator notes.\n"
    before = snapshot(ws)
    result, _ = run(ws, requirement, D6A_ONLY, constraints_edge_cases=CONSTRAINTS)
    assert result.code is ProcessCode.INVALID_MODEL_OUTPUT
    assert snapshot(ws) == before
    detail = " ".join(result.details)
    assert (
        f"attestation {fingerprint(D6A_ONLY)} ALTERED_OR_DELETED "
        "(an unrecognized section)" in detail
    )
    assert D6A not in detail and "Operator notes" not in detail
    assert len(detail) < 400


def test_a_model_heading_holding_the_text_is_never_echoed():
    detail = refused(
        D6A_ONLY, constraints_edge_cases=PARAPHRASED, non_goals=f"### {D6A}"
    )
    assert "MOVED (Constraints & Edge Cases, Non-Goals)" in detail
    assert D6A not in detail and len(detail) < 400


# -- Gate 3L5 F03: exact characters, as read ------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Retries stop after three attempts.\u2028Each waits two seconds.",
        "Retries stop after three attempts.\u2029Each waits two seconds.",
        "Accented names such as caf\u00e9 compare exactly.",
        r"Paths such as C:\data\*.log keep their \*literal\* backslashes.",
        r"Write \# and \- when a line must not start a heading or list.",
    ],
    ids=["U+2028", "U+2029", "composed", "backslashes", "escapes"],
)
def test_unusual_characters_are_compared_exactly(text):
    policies = attested(text)
    root = {"constraints": f"{FIRST}\n\n{text}"}
    assert text in processed_from(
        policies, root, constraints_edge_cases=f"{FIRST}\n\n{text}"
    )
    detail = refused_from(policies, root, constraints_edge_cases=FIRST)
    assert "ALTERED_OR_DELETED (Constraints & Edge Cases)" in detail


def test_a_decomposed_rewrite_of_a_composed_character_is_refused():
    text = "Accented names such as caf\u00e9 compare exactly."
    detail = refused_from(
        attested(text),
        {"constraints": f"{FIRST}\n\n{text}"},
        constraints_edge_cases=f"{FIRST}\n\n{text.replace('\u00e9', 'e\u0301')}",
    )
    assert "ALTERED_OR_DELETED" in detail


def test_unescaping_markdown_is_a_change():
    text = r"Write \# and \- when a line must not start a heading or list."
    detail = refused_from(
        attested(text),
        {"constraints": f"{FIRST}\n\n{text}"},
        constraints_edge_cases=f"{FIRST}\n\n{text.replace(chr(92), '')}",
    )
    assert "ALTERED_OR_DELETED" in detail


@pytest.mark.parametrize("ending", ["\r\n", "\n"])
def test_a_line_ending_inside_fenced_content_is_compared_exactly(ending):
    text = f"retry_limit = 3{ending}retry_wait = 2"
    policies = attested(text)
    root = {"constraints": f"{FIRST}\n\n```\n{text}\n```"}
    processed_from(
        policies, root, constraints_edge_cases=f"{FIRST}\n\n```\n{text}\n```"
    )
    detail = refused_from(policies, root, constraints_edge_cases=FIRST)
    assert "ALTERED_OR_DELETED (Constraints & Edge Cases)" in detail


def test_crlf_rewritten_as_lf_is_a_change():
    text = "retry_limit = 3\r\nretry_wait = 2"
    detail = refused_from(
        attested(text),
        {"constraints": f"{FIRST}\n\n```\n{text}\n```"},
        constraints_edge_cases=f"{FIRST}\n\n```\n{text.replace(chr(13), '')}\n```",
    )
    assert "ALTERED_OR_DELETED" in detail


# -- Gate 3L5 F04: Markdown paragraph boundaries --------------------------------


@pytest.mark.parametrize("blank", ["  ", "\t", " \t ", ""])
def test_blank_lines_holding_whitespace_still_bound_the_paragraph(blank):
    root = {"constraints": f"{FIRST}\n{blank}\n{D6A}\n{blank}\n{D1}"}
    kept = processed_from(
        D6A_ONLY,
        root,
        constraints_edge_cases=f"Values are 1 to 32 characters long.\n{blank}\n{D6A}\n{blank}\n{D1}",
    )
    assert D6A in kept
    for changed, category in [
        (
            f"{FIRST}\n{blank}\n{D6A} Proxies may also answer 431.\n{blank}\n{D1}",
            "PARAGRAPH_CHANGED",
        ),
        (f"{FIRST}\n{blank}\n{D6A}\n{D1}", "PARAGRAPH_CHANGED"),  # merged
        (f"{FIRST}\n{blank}\n{D1}\n{D6A}", "PARAGRAPH_CHANGED"),  # merged before
        (
            f"{FIRST}\n{blank}\n{D6A.replace(' This clarification', chr(10) * 2 + 'This clarification')}\n{blank}\n{D1}",
            "ALTERED_OR_DELETED",
        ),  # split into two paragraphs
    ]:
        detail = refused_from(D6A_ONLY, root, constraints_edge_cases=changed)
        assert f"{category} (Constraints & Edge Cases)" in detail


# -- Gate 3L5 F05: every occurrence counts, overlapping ones too ----------------

QZQ = attested("QZQ")


def test_an_overlapping_second_occurrence_is_a_duplicate():
    root = {"constraints": "Marker x QZQ y."}
    processed_from(QZQ, root, constraints_edge_cases="Marker x QZQ y, kept.")
    detail = refused_from(QZQ, root, constraints_edge_cases="Marker x QZQZQ y.")
    assert (
        f"attestation {fingerprint(QZQ)} DUPLICATED (Constraints & Edge Cases)"
        in detail
    )


def test_repeated_occurrences_are_counted_per_section():
    root = {
        "constraints": "First QZQ.\n\nSecond QZQ.",
        "rationale": "Why QZQ.",
    }
    processed_from(
        QZQ,
        root,
        constraints_edge_cases="1st QZQ.\n\n2nd QZQ.",
        rationale="Because QZQ.",
    )
    detail = refused_from(QZQ, root, constraints_edge_cases="First QZQ.")
    assert "ALTERED_OR_DELETED (Constraints & Edge Cases)" in detail
    detail = refused_from(
        QZQ, root, constraints_edge_cases="First QZQ.\n\nSecond QZQ.\n\nThird QZQ."
    )
    assert "DUPLICATED (Constraints & Edge Cases)" in detail
    detail = refused_from(
        QZQ,
        root,
        rationale="Why it matters.",
        detailed_behavior="Why QZQ.",
    )
    assert "MOVED (Detailed Behavior, Rationale)" in detail


def test_a_duplicate_in_another_block_of_the_same_section_is_refused():
    detail = refused_from(
        QZQ,
        {"constraints": "Marker QZQ."},
        constraints_edge_cases="Marker QZQ.\n\n```\nQZQ\n```",
    )
    assert "DUPLICATED (Constraints & Edge Cases)" in detail


def test_overlapping_attestations_are_judged_independently():
    policies = attested("alpha beta", "beta gamma")
    root = {"constraints": "Order: alpha beta gamma."}
    processed_from(policies, root, constraints_edge_cases="Order: alpha beta gamma!")
    detail = refused_from(
        policies, root, constraints_edge_cases="Order: alpha beta, gamma."
    )
    assert f"attestation {fingerprint(policies, 1)} ALTERED_OR_DELETED" in detail
    assert fingerprint(policies, 0) not in detail


# -- a structure the parser cannot vouch for -------------------------------------


def test_an_unreadable_structure_refuses_when_attested_text_is_involved(monkeypatch):
    monkeypatch.setattr("sdlc.standard_processor.block_token_types", lambda _: None)
    detail = refused(D6A_ONLY, constraints_edge_cases=CONSTRAINTS)
    assert f"attestation {fingerprint(D6A_ONLY)} STRUCTURE_UNREADABLE" in detail


def test_nothing_is_parsed_when_no_attested_text_is_involved(monkeypatch):
    monkeypatch.setattr("sdlc.standard_processor.block_token_types", lambda _: None)
    processed(DISABLED, constraints_edge_cases=PARAPHRASED)
    processed(
        attested("Text that appears nowhere."), constraints_edge_cases=PARAPHRASED
    )
