"""Attested-Text-Preservation-v0.1: an attested text in the input comes back verbatim.

The live case is ARP1 Gate 3L3: FR-0129's Root held the operator-attested
D6-A paragraph, and Process 4's normalization split its last sentence ("…
segments, does not permit …" became "… segments. It does not permit …"). The
output still passed every check, so a paraphrase of a human decision became
the Requirement's text. Code now compares the input with the normalized output
and refuses before anything is written.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from markdown_it import MarkdownIt
from markdown_it.token import Token

from processor_fake import FakeModelRuntime
from review_fake import review_output
from sdlc.autonomy_policy import DISABLED, AutonomyPolicies
from sdlc.human_attestation import HumanAttestation, HumanAttestations
from sdlc.process_result import parse_process_result
from sdlc.raw_processing import reserved_heading
from sdlc.ready_decision import read_ready_evidence, rework_standard_requirement
from sdlc.results import StandardProcessResultCode as ProcessCode
from sdlc.review_result import parse_review_result
from sdlc.standard_processor import process_standard_requirement
from sdlc.standard_reviewer import review_standard_requirement
from sdlc.tsa_markdown import block_tokens
from standard_fake import REQUIREMENT_ID, analysis_output, rendered_document, set_state
from test_autonomous_resolution import artifacts, latest_process, scene
from test_human_attestation import (
    DECISION,
    human_decision_at_ready,
    human_edit,
    open_question_reviewed,
    second_process,
)
from test_requirement_dispatcher import dispatch_current, real_workers

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


@pytest.mark.parametrize(
    ("fence", "category"),
    [("```", "MOVED"), ("````", "SECTIONS_AMBIGUOUS")],
    ids=["closed-backticks", "four-backticks"],
)
def test_a_fenced_heading_cannot_carry_the_attested_text_out(fence, category):
    """Gate 3M1: inside a closed backtick fence the heading is example text to
    both readers, so the exact text is judged where it is, in Non-Goals. The
    schema's fence grammar never closes a four-backtick fence, CommonMark does,
    so the two readers disagree and the sections are not established."""
    detail = refused(
        D6A_ONLY,
        constraints_edge_cases=PARAPHRASED,
        non_goals=f"{fence}\n{FAKE_SECTION}\n\n{D6A}\n{fence}",
    )
    assert f"attestation {fingerprint(D6A_ONLY)} {category}" in detail
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


def test_a_fenced_heading_and_text_in_the_input_are_kept_as_they_are():
    root = {
        "constraints": f"{FIRST}\n\n{D1}",
        "non_goals": f"```\n{FAKE_SECTION}\n\n{D6A}\n```",
    }
    kept = processed_from(D6A_ONLY, root)  # kept as it is
    assert kept.count(FAKE_SECTION) == 2 and kept.count(D6A) == 1


@pytest.mark.parametrize(
    ("fence", "category"),
    [("```", "MOVED"), ("~~~", "SECTIONS_AMBIGUOUS")],
    ids=["backticks", "tildes"],
)
def test_attested_text_in_a_fenced_example_may_not_move_out(fence, category):
    """The schema reads only backtick fences as literal, so a tilde-fenced
    heading is a heading to it and not to CommonMark: no established sections."""
    detail = refused_from(
        D6A_ONLY,
        {
            "constraints": f"{FIRST}\n\n{D1}",
            "non_goals": f"{fence}\n{FAKE_SECTION}\n\n{D6A}\n{fence}",
        },
        constraints_edge_cases=f"{FIRST}\n\n{D1}\n\n{D6A}",
        non_goals="Nothing else.",
    )
    assert f"{category} (" in detail


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
        f"attestation {fingerprint(D6A_ONLY)} SECTIONS_AMBIGUOUS "
        "(the whole document)" in detail
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


# -- Gate 3L7 G7-01: one structural reading, unique schema sections -------------

# The reviewer's reproduction: CommonMark rejects an info string holding a
# backtick, so this is no fence for it, while the field validator's fence
# pattern hides the heading inside it.
MALFORMED_FENCE = "```bad`info"


def schema_accepts(text):
    """The production field validator's verdict, asserted independently of the
    preservation parser: no reserved heading outside its fences."""
    return reserved_heading(text) is None


def test_the_malformed_fence_reproduction_is_refused_before_anything_is_written():
    non_goals = f"{MALFORMED_FENCE}\n\n{FAKE_SECTION}\n\n{D6A}\n\n```"
    assert schema_accepts(non_goals)  # the field validator sees no section here
    detail = refused(D6A_ONLY, constraints_edge_cases=PARAPHRASED, non_goals=non_goals)
    assert (
        f"attestation {fingerprint(D6A_ONLY)} SECTIONS_AMBIGUOUS "
        "(the whole document)" in detail
    )
    assert D6A not in detail and len(detail) < 400


def test_a_malformed_fence_without_a_heading_still_splits_the_two_readers():
    """Gate 3M1: the schema's fence grammar opens a fence at the malformed line
    and, finding no closing line, runs it over Open Questions; CommonMark reads
    no fence at all. The readers disagree, so nothing is established."""
    non_goals = f"{MALFORMED_FENCE}\n\n{D6A}\n\n{MALFORMED_FENCE}"
    assert schema_accepts(non_goals)
    detail = refused(
        D6A_ONLY, constraints_edge_cases=f"{FIRST}\n\n{D1}", non_goals=non_goals
    )
    assert "SECTIONS_AMBIGUOUS (the whole document)" in detail


def test_an_unclosed_fence_may_not_swallow_the_next_section_heading():
    """The field validator reads each field alone, so an open fence at the end
    of one field and a heading hidden by a fence in the next both pass it; the
    rendered document then has its real Non-Goals heading inside code and a
    copy of it after the attested text, which CommonMark puts in Constraints."""
    constraints = f"{FIRST}\n\n{D1}\n\n```"
    non_goals = f"```\n\n{D6A}\n\n## Non-Goals\n\nNothing else."
    assert schema_accepts(constraints) and schema_accepts(non_goals)
    detail = refused(D6A_ONLY, constraints_edge_cases=constraints, non_goals=non_goals)
    assert "SECTIONS_AMBIGUOUS (the whole document)" in detail


@pytest.mark.parametrize(
    "extra",
    [
        f"{FAKE_SECTION}\n\nMore constraints.",  # the same section twice
        "## Rationale\n\nA second rationale.",  # another known section twice
        "## Notes\n\nOne.\n\n## Appendix\n\nTwo.",  # two unknown sections
        "## constraints & edge cases\n\nCase differs.",  # near a known label
        f"{FAKE_SECTION} ##\n\nClosing hashes.",  # same label, other form
        "# A second title\n\nText.",
    ],
    ids=[
        "repeated",
        "repeated-other",
        "two-unknown",
        "unknown-collides",
        "closing-hashes",
        "second-title",
    ],
)
def test_a_root_whose_sections_are_not_exactly_the_schema_is_refused(extra):
    ws, requirement, root = rooted()
    ws.content[root.secret] += f"\n{extra}\n"
    before = snapshot(ws)
    result, model = run(ws, requirement, D6A_ONLY, constraints_edge_cases=CONSTRAINTS)
    assert result.code is ProcessCode.INVALID_MODEL_OUTPUT, result
    assert len(model.calls) == 1 and snapshot(ws) == before
    detail = " ".join(result.details)
    assert "SECTIONS_AMBIGUOUS (the whole document)" in detail
    assert "Case differs" not in detail and "Appendix" not in detail


def test_sections_in_another_order_are_refused():
    ws, requirement, root = rooted()
    content = ws.content[root.secret]
    ws.content[root.secret] = (
        content.replace("## Rationale", "## Swap")
        .replace("## Detailed Behavior", "## Rationale")
        .replace("## Swap", "## Detailed Behavior")
    )
    result, _ = run(ws, requirement, D6A_ONLY, constraints_edge_cases=CONSTRAINTS)
    assert result.code is ProcessCode.INVALID_MODEL_OUTPUT
    assert "SECTIONS_AMBIGUOUS" in " ".join(result.details)


@pytest.mark.parametrize(
    ("non_goals", "accepted_by_schema"),
    [
        (f"> {FAKE_SECTION}\n>\n> {D6A}", True),
        (f"- {FAKE_SECTION}\n\n  {D6A}", True),
    ],
    ids=["quote", "list"],
)
def test_a_heading_inside_a_quote_or_list_opens_no_section(
    non_goals, accepted_by_schema
):
    assert schema_accepts(non_goals) is accepted_by_schema
    detail = refused(D6A_ONLY, constraints_edge_cases=PARAPHRASED, non_goals=non_goals)
    assert "MOVED (Constraints & Edge Cases, Non-Goals)" in detail


def test_an_ordinary_seven_section_document_with_every_section_changed_passes():
    ws, _, root = processed(
        D6A_ONLY,
        requirement="The service must answer every valid request.",
        detailed_behavior="Each request is parsed once.\n\n### Parsing\n\nStrict.",
        rationale="Clients need one rule.",
        acceptance_verification="- a valid word returns 200\n- an invalid one 400",
        constraints_edge_cases=f"Values are 1 to 32 characters.\n\n{D1}\n\n{D6A}",
        non_goals="> No caching.",
        open_questions="None.",
    )
    assert ws.content[root.secret].count(D6A) == 1


# -- Gate 3L7 G7-02: every block an attested text touches keeps its identity -----

TWO = "First approved sentence.\n\nSecond approved sentence."
TWO_ONLY = attested(TWO)
TWO_ROOT = {"constraints": f"{FIRST}\n\n{TWO}"}


def test_a_multi_paragraph_attestation_kept_whole_passes_and_neighbours_normalize():
    kept = processed_from(
        TWO_ONLY, TWO_ROOT, constraints_edge_cases=f"Values are 1 to 32.\n\n{TWO}"
    )
    assert TWO in kept and "Values are 1 to 32." in kept


@pytest.mark.parametrize(
    "first",
    [
        "> First approved sentence.",
        "* First approved sentence.",
        "    First approved sentence.",
        "```\nFirst approved sentence.\n```",
        "<div>\nFirst approved sentence.",
    ],
    ids=["quote", "list", "indented-code", "fence", "html"],
)
def test_moving_only_the_first_paragraph_into_another_block_is_refused(first):
    changed = f"{FIRST}\n\n{first}\n\nSecond approved sentence."
    if "```" not in first:  # the exact characters are still there
        assert TWO in changed
    detail = refused_from(TWO_ONLY, TWO_ROOT, constraints_edge_cases=changed)
    category = "ALTERED_OR_DELETED" if "```" in first else "PARAGRAPH_CHANGED"
    assert f"{category} (Constraints & Edge Cases)" in detail


@pytest.mark.parametrize(
    "second",
    [
        "> Second approved sentence.",
        "* Second approved sentence.",
        "    Second approved sentence.",
    ],
    ids=["quote", "list", "indented-code"],
)
def test_moving_only_the_second_paragraph_into_another_block_is_refused(second):
    """A marker before the second paragraph lies inside the attested text, so
    the exact characters themselves are gone."""
    detail = refused_from(
        TWO_ONLY,
        TWO_ROOT,
        constraints_edge_cases=f"{FIRST}\n\nFirst approved sentence.\n\n{second}",
    )
    assert "ALTERED_OR_DELETED (Constraints & Edge Cases)" in detail


def test_extending_only_the_last_paragraph_is_refused():
    detail = refused_from(
        TWO_ONLY, TWO_ROOT, constraints_edge_cases=f"{FIRST}\n\n{TWO} And more."
    )
    assert "PARAGRAPH_CHANGED (Constraints & Edge Cases)" in detail


def test_splitting_the_paragraphs_across_sections_is_refused():
    detail = refused_from(
        TWO_ONLY,
        TWO_ROOT,
        constraints_edge_cases=f"{FIRST}\n\nFirst approved sentence.",
        non_goals="Second approved sentence.",
    )
    assert "ALTERED_OR_DELETED" in detail


def test_the_order_of_component_blocks_is_part_of_the_placement():
    """Whole-then-partial and partial-then-whole are the same blocks as a set;
    the sequence differs, so it is refused."""
    same = attested("Same line.\n\nSame line.")
    root = {"constraints": "Same line.\n\nSame line. Extra."}
    detail = refused_from(
        same, root, constraints_edge_cases="Extra. Same line.\n\nSame line."
    )
    assert "PARAGRAPH_CHANGED (Constraints & Edge Cases)" in detail


def test_a_mixed_paragraph_and_quote_attestation_is_preserved_as_it_is():
    mixed = "First approved sentence.\n\n> Second approved sentence."
    policies = attested(mixed)
    root = {"constraints": f"{FIRST}\n\n{mixed}"}
    assert mixed in processed_from(
        policies, root, constraints_edge_cases=f"Values are 1 to 32.\n\n{mixed}"
    )
    detail = refused_from(
        policies, root, constraints_edge_cases=f"{FIRST}\n\n> {mixed}"
    )
    assert "PARAGRAPH_CHANGED (Constraints & Edge Cases)" in detail


@pytest.mark.parametrize(
    ("held", "changed"),
    [
        ("> > First approved sentence.", "> First approved sentence."),
        ("- - First approved sentence.", "- First approved sentence."),
        ("> - First approved sentence.", "- > First approved sentence."),
    ],
    ids=["quote-depth", "list-depth", "quote-list-order"],
)
def test_changing_the_nesting_around_one_paragraph_is_refused(held, changed):
    root = {"constraints": f"{held}\n\nSecond approved sentence."}
    processed_from(TWO_ONLY, root)
    detail = refused_from(
        TWO_ONLY,
        root,
        constraints_edge_cases=f"{changed}\n\nSecond approved sentence.",
    )
    assert "PARAGRAPH_CHANGED (Constraints & Edge Cases)" in detail


def test_attestations_sharing_a_section_stay_independent_across_blocks():
    policies = attested(TWO, D1)
    root = {"constraints": f"{FIRST}\n\n{TWO}\n\n{D1}"}
    processed_from(policies, root)
    detail = refused_from(
        policies,
        root,
        constraints_edge_cases=f"{FIRST}\n\n> First approved sentence.\n\n"
        f"Second approved sentence.\n\n{D1}",
    )
    assert f"attestation {fingerprint(policies, 0)} PARAGRAPH_CHANGED" in detail
    assert fingerprint(policies, 1) not in detail


# -- Gate 3L7 G7-03: one parse, and every parser failure is a refusal ------------


@pytest.mark.parametrize("failing", [1, 2], ids=["input", "output"])
def test_a_parser_exception_is_a_refusal_without_its_text(monkeypatch, failing):
    """Every parse in the process, wherever it runs, goes through the pinned
    parser; the numbered one raises with attested text in its message."""
    calls = []
    parse = MarkdownIt.parse

    def numbered(parser, text, env=None):
        calls.append(text)
        if len(calls) == failing:
            raise ValueError(f"parser failed on {D6A}")
        return parse(parser, text, env)

    monkeypatch.setattr(MarkdownIt, "parse", numbered)
    detail = refused(D6A_ONLY, constraints_edge_cases=CONSTRAINTS)
    assert f"attestation {fingerprint(D6A_ONLY)} STRUCTURE_UNREADABLE" in detail
    assert "parser failed" not in detail and D6A not in detail
    assert len(calls) == 2  # one parse per document, no more


def test_a_parse_reporting_lines_the_document_lacks_is_a_refusal(monkeypatch):
    calls = []

    def stretched(text):
        tokens = block_tokens(text)
        calls.append(text)
        if len(calls) == 2:
            for token in tokens:
                if token.map:
                    token.map = [token.map[0], 10**6]
        return tokens

    monkeypatch.setattr("sdlc.standard_processor.block_tokens", stretched)
    detail = refused(D6A_ONLY, constraints_edge_cases=CONSTRAINTS)
    assert "STRUCTURE_UNREADABLE (the whole document)" in detail


def test_an_unreadable_structure_refuses_when_attested_text_is_involved(monkeypatch):
    monkeypatch.setattr("sdlc.standard_processor.block_tokens", lambda _: None)
    detail = refused(D6A_ONLY, constraints_edge_cases=CONSTRAINTS)
    assert f"attestation {fingerprint(D6A_ONLY)} STRUCTURE_UNREADABLE" in detail


def test_nesting_the_guard_cannot_vouch_for_is_refused():
    deep = "> " * 25 + "Deeply quoted aside."
    assert schema_accepts(deep)
    detail = refused(D6A_ONLY, constraints_edge_cases=CONSTRAINTS, non_goals=deep)
    assert "STRUCTURE_UNREADABLE (the whole document)" in detail and len(detail) < 400


def test_nothing_is_parsed_when_no_attested_text_is_involved(monkeypatch):
    def never(_):
        raise AssertionError("parsed")

    monkeypatch.setattr("sdlc.standard_processor.block_tokens", never)
    processed(DISABLED, constraints_edge_cases=PARAPHRASED)
    processed(
        attested("Text that appears nowhere."), constraints_edge_cases=PARAPHRASED
    )


# -- Gate 3L7 replay: the same boundary for a persisted Result --------------------


def persisted_from(root, **sections):
    """A Result persisted while nothing was protected, then its input restored."""
    ws, requirement, document = rooted(**root)
    restored = ws.content[document.secret]
    result, _ = run(ws, requirement, DISABLED, **(unchanged(root) | sections))
    assert result.code is ProcessCode.REQUIREMENT_PROCESSED, result
    ws.content[document.secret] = restored
    set_state(ws, requirement, "Process")
    [node] = artifacts(ws, "Process Result")
    return ws, requirement, document, node


@pytest.mark.parametrize(
    ("root", "policies", "sections", "category"),
    [
        (
            {"constraints": CONSTRAINTS},
            D6A_ONLY,
            {
                "constraints_edge_cases": PARAPHRASED,
                "non_goals": f"{MALFORMED_FENCE}\n\n{FAKE_SECTION}\n\n{D6A}\n\n```",
            },
            "SECTIONS_AMBIGUOUS",
        ),
        (
            {"constraints": CONSTRAINTS},
            D6A_ONLY,
            {
                "constraints_edge_cases": f"{FIRST}\n\n{D1}\n\n```",
                "non_goals": f"```\n\n{D6A}\n\n## Non-Goals\n\nNothing else.",
            },
            "SECTIONS_AMBIGUOUS",
        ),
        (
            TWO_ROOT,
            TWO_ONLY,
            {"constraints_edge_cases": f"{FIRST}\n\n> {TWO}"},
            "PARAGRAPH_CHANGED",
        ),
    ],
    ids=["malformed-fence", "swallowed-heading", "multi-block-quote"],
)
def test_a_structural_bypass_is_refused_on_replay_without_a_model(
    root, policies, sections, category
):
    ws, requirement, _, node = persisted_from(root, **sections)
    history = ws.content[node.secret]
    before = snapshot(ws)
    result, model = resume(ws, requirement, node, policies)
    assert result.code is ProcessCode.PROCESSING_STATE_CONFLICT, result
    assert not model.was_invoked and result.model_invoked is False
    assert result.created == () and snapshot(ws) == before
    assert ws.requirements[requirement.id].state == "Process"
    assert ws.content[node.secret] == history
    assert category in " ".join(result.details)


def test_a_compliant_multi_block_replay_is_still_applied():
    ws, requirement, document, node = persisted_from(
        TWO_ROOT, constraints_edge_cases=f"Values are 1 to 32.\n\n{TWO}"
    )
    result, model = resume(ws, requirement, node, TWO_ONLY)
    assert result.code is ProcessCode.REQUIREMENT_PROCESSED, result
    assert not model.was_invoked
    assert "Values are 1 to 32." in ws.content[document.secret]


# -- Gate 3L7 downstream: nothing reaches Review -----------------------------------


@pytest.mark.parametrize(
    ("root", "policies", "sections"),
    [
        (
            {"constraints": CONSTRAINTS},
            D6A_ONLY,
            {
                "constraints_edge_cases": PARAPHRASED,
                "non_goals": f"{MALFORMED_FENCE}\n\n{FAKE_SECTION}\n\n{D6A}\n\n```",
            },
        ),
        (TWO_ROOT, TWO_ONLY, {"constraints_edge_cases": f"{FIRST}\n\n> {TWO}"}),
    ],
    ids=["malformed-fence", "multi-block-quote"],
)
def test_a_refused_bypass_leaves_review_nothing_to_admit(root, policies, sections):
    ws, requirement, _ = rooted(**root)
    result, _ = run(ws, requirement, policies, **(unchanged(root) | sections))
    assert result.code is ProcessCode.INVALID_MODEL_OUTPUT
    assert artifacts(ws, "Process Result") == []
    reviewer = FakeModelRuntime([review_output()])
    review = review_standard_requirement(
        ws, reviewer, requirement.id, policies=policies
    )
    assert not review.is_normal and not reviewer.was_invoked
    assert artifacts(ws, "Review Result") == []
    assert ws.requirements[requirement.id].state == "Process"


# -- Gate 3M1 G9-01: a heading in a closed backtick example is example text -----

EXAMPLE = f"```markdown\n{FAKE_SECTION}\n\nAn example section.\n```"
EXAMPLE_ROOT = {
    "constraints": CONSTRAINTS,
    "acceptance_verification": f"Example:\n\n{EXAMPLE}",
}


def unchanged_example(document):
    assert document.count(FAKE_SECTION) == 2 and document.count(D6A) == 1


@pytest.mark.parametrize(
    "section",
    ["acceptance_verification", "detailed_behavior", "non_goals"],
    ids=["acceptance", "detailed-behavior", "non-goals"],
)
def test_a_closed_backtick_example_holding_a_section_heading_is_accepted(section):
    assert schema_accepts(EXAMPLE)
    ws, requirement, root = processed(
        D6A_ONLY, constraints_edge_cases=CONSTRAINTS, **{section: EXAMPLE}
    )
    unchanged_example(ws.content[root.secret])
    assert ws.requirements[requirement.id].state == "Review"
    _, result = latest_process(ws)
    assert result.output_fingerprint and D6A in result.normalized.constraints_edge_cases


def test_a_closed_backtick_example_in_the_input_is_kept_or_dropped_freely():
    unchanged_example(processed_from(D6A_ONLY, EXAMPLE_ROOT))
    dropped = processed_from(
        D6A_ONLY, EXAMPLE_ROOT, acceptance_verification="No example."
    )
    assert FAKE_SECTION in dropped and dropped.count(FAKE_SECTION) == 1
    assert dropped.count(D6A) == 1


@pytest.mark.parametrize(
    "example",
    [
        f"Quote the line `{FAKE_SECTION}` as written.",
        f"The heading reads {FAKE_SECTION} in the document.",
        f"> {FAKE_SECTION}\n>\n> A quoted example.",
        f"- {FAKE_SECTION}\n\n  A listed example.",
        f"Example:\n\n    {FAKE_SECTION}",
    ],
    ids=["inline-code", "prose", "quote", "list", "indented-code"],
)
def test_a_heading_line_that_no_reader_takes_as_a_section_is_content(example):
    assert schema_accepts(example)
    ws, _, root = processed(
        D6A_ONLY, constraints_edge_cases=CONSTRAINTS, non_goals=example
    )
    assert ws.content[root.secret].count(D6A) == 1


@pytest.mark.parametrize(
    "example",
    [
        f"~~~\n{FAKE_SECTION}\n~~~",
        f"````\n{FAKE_SECTION}\n````",
        f"<div>\n{FAKE_SECTION}\n</div>",
        f"{MALFORMED_FENCE}\n{FAKE_SECTION}\n```",
    ],
    ids=["tildes", "four-backticks", "html", "malformed"],
)
def test_a_root_whose_readers_disagree_about_a_heading_is_refused(example):
    """Each is a heading to one reader and not to the other. The output drops
    it, which the output's own check would refuse first for some of them."""
    detail = refused_from(
        D6A_ONLY,
        {"constraints": CONSTRAINTS, "non_goals": example},
        non_goals="Nothing else.",
    )
    assert "SECTIONS_AMBIGUOUS (the whole document)" in detail


def test_the_swallowed_heading_is_refused_although_both_readers_agree():
    """Reading the whole document, both readers put the real Non-Goals heading
    inside the fence and take the copy as the section; the renderer wrote
    Non-Goals where the fence now is, so the sections are not where it put them."""
    constraints = f"{FIRST}\n\n{D1}\n\n```"
    non_goals = f"```\n\n{D6A}\n\n## Non-Goals\n\nNothing else."
    detail = refused(
        D6A_ONLY,
        constraints_edge_cases=f"{constraints}\n\n{D6A}",
        non_goals=non_goals.replace(f"{D6A}\n\n", ""),
    )
    assert "SECTIONS_AMBIGUOUS (the whole document)" in detail


def test_a_requirement_with_a_fenced_example_requalifies_through_rework():
    ws, requirement, root = processed(
        D6A_ONLY, constraints_edge_cases=CONSTRAINTS, acceptance_verification=EXAMPLE
    )
    reviewer = FakeModelRuntime([review_output(new_findings=[INFO_FINDING])])
    assert review_standard_requirement(
        ws, reviewer, requirement.id, policies=D6A_ONLY
    ).is_normal
    assert rework_standard_requirement(ws, requirement.id).is_normal
    model = FakeModelRuntime(
        [
            analysis_output(
                normalized_changes={
                    "constraints_edge_cases": CONSTRAINTS,
                    "acceptance_verification": EXAMPLE,
                },
                rework=[answered("R0001.N0")],
            )
        ]
    )
    result = process_standard_requirement(
        ws, model, requirement.id, policies=D6A_ONLY, authorized_new_cycle=True
    )
    assert result.code is ProcessCode.REQUIREMENT_PROCESSED, result
    assert latest_process(ws)[1].iteration == 2
    unchanged_example(ws.content[root.secret])


def test_a_compliant_replay_of_a_fenced_example_is_applied():
    ws, requirement, document, node = persisted_from(
        EXAMPLE_ROOT, requirement="The service must answer every valid request."
    )
    result, model = resume(ws, requirement, node, D6A_ONLY)
    assert result.code is ProcessCode.REQUIREMENT_PROCESSED, result
    assert not model.was_invoked
    unchanged_example(ws.content[document.secret])
    assert ws.requirements[requirement.id].state == "Review"


# -- Gate 3M1 G9-02: every component an attested text touches is placed ---------

HR_D6A = f"---\n\n{D6A}"
HR_ONLY = attested(HR_D6A)
HR_ROOT = {"constraints": f"{FIRST}\n\n{D1}\n\n{HR_D6A}"}


def test_an_attested_thematic_break_kept_in_place_passes():
    kept = processed_from(
        HR_ONLY,
        HR_ROOT,
        constraints_edge_cases=f"Values are 1 to 32.\n\n{D1}\n\n{HR_D6A}",
    )
    assert HR_D6A in kept and "Values are 1 to 32." in kept


@pytest.mark.parametrize(
    "changed",
    [
        f"> {HR_D6A}",  # the break quoted, the paragraph not (lazy lines aside)
        f"* {HR_D6A}",  # the break inside a list item
        f"    {HR_D6A}",  # the break as indented code
        f"```\n{HR_D6A}\n```",  # both in one fence: two components become one
    ],
    ids=["quote", "list", "indented-code", "fence-one-component"],
)
def test_moving_the_thematic_break_into_another_block_is_refused(changed):
    if changed.startswith("> "):
        changed = f"> ---\n\n{D6A}"
    output = f"{FIRST}\n\n{D1}\n\n{changed}"
    assert HR_D6A in output  # the exact characters are all still there
    detail = refused_from(HR_ONLY, HR_ROOT, constraints_edge_cases=output)
    assert "PARAGRAPH_CHANGED (Constraints & Edge Cases)" in detail
    assert D6A not in detail


def test_removing_the_thematic_break_is_refused():
    detail = refused_from(
        HR_ONLY, HR_ROOT, constraints_edge_cases=f"{FIRST}\n\n{D1}\n\n{D6A}"
    )
    assert "ALTERED_OR_DELETED (Constraints & Edge Cases)" in detail


REFERENCE = "[spec]: https://example.com/spec"


def test_a_line_no_block_holds_is_still_part_of_the_placement():
    """A link reference definition yields no token; it is placed as a line in
    no block, within whatever container holds it."""
    policies = attested(f"{REFERENCE}\n\n{D6A}")
    root = {"constraints": f"{FIRST}\n\n{D1}\n\n{REFERENCE}\n\n{D6A}"}
    processed_from(policies, root)
    detail = refused_from(
        policies,
        root,
        constraints_edge_cases=f"{FIRST}\n\n{D1}\n\n> {REFERENCE}\n\n{D6A}",
    )
    assert "PARAGRAPH_CHANGED (Constraints & Edge Cases)" in detail


def test_quote_markers_between_attested_paragraphs_are_placed():
    quoted = "> First approved sentence.\n>\n> Second approved sentence."
    policies = attested(quoted)
    root = {"constraints": f"{FIRST}\n\n{quoted}"}
    assert quoted in processed_from(policies, root)


def test_every_block_token_of_the_pinned_parser_is_known():
    """The bounded audit: a document using every enabled block rule yields
    only token types the placement reading names."""
    from sdlc import standard_processor as processor

    document = (
        "# T\n\nSetext\n---\n\npara\n\n> q\n>\n> r\n\n- a\n-\n1. b\n\n***\n\n"
        "    code\n\n```\nf\n```\n\n<div>\nh\n</div>\n\n[r]: /u\n"
    )
    known = (
        set(processor.LEAF_BLOCKS)
        | set(processor.CONTAINER_BLOCKS)
        | processor.CONTAINER_CLOSINGS
        | processor.LEAF_PARTS
    )
    assert {token.type for token in block_tokens(document)} <= known
    assert set(MarkdownIt("commonmark").block.ruler.get_active_rules()) == {
        "blockquote",
        "code",
        "fence",
        "heading",
        "hr",
        "html_block",
        "lheading",
        "list",
        "paragraph",
        "reference",
    }


def test_a_block_token_the_reading_does_not_know_is_a_refusal(monkeypatch):
    def with_table(text):
        table = Token("table_open", "table", 1)
        table.map = [0, 1]
        return (*block_tokens(text), table)

    monkeypatch.setattr("sdlc.standard_processor.block_tokens", with_table)
    detail = refused(D6A_ONLY, constraints_edge_cases=CONSTRAINTS)
    assert "STRUCTURE_UNREADABLE (the whole document)" in detail


def test_a_replay_that_quotes_the_thematic_break_is_refused_without_a_model():
    ws, requirement, _, node = persisted_from(
        HR_ROOT, constraints_edge_cases=f"{FIRST}\n\n{D1}\n\n> ---\n\n{D6A}"
    )
    history = ws.content[node.secret]
    before = snapshot(ws)
    result, model = resume(ws, requirement, node, HR_ONLY)
    assert result.code is ProcessCode.PROCESSING_STATE_CONFLICT, result
    assert not model.was_invoked and result.created == ()
    assert snapshot(ws) == before and ws.content[node.secret] == history
    assert ws.requirements[requirement.id].state == "Process"
    assert "PARAGRAPH_CHANGED" in " ".join(result.details)


def test_a_compliant_replay_keeping_the_thematic_break_is_applied():
    ws, requirement, document, node = persisted_from(
        HR_ROOT, constraints_edge_cases=f"Values are 1 to 32.\n\n{D1}\n\n{HR_D6A}"
    )
    result, model = resume(ws, requirement, node, HR_ONLY)
    assert result.code is ProcessCode.REQUIREMENT_PROCESSED, result
    assert not model.was_invoked and HR_D6A in ws.content[document.secret]


def test_a_refused_thematic_break_change_leaves_review_nothing_to_admit():
    ws, requirement, _ = rooted(**HR_ROOT)
    result, _ = run(
        ws,
        requirement,
        HR_ONLY,
        **(
            unchanged(HR_ROOT)
            | {"constraints_edge_cases": f"{FIRST}\n\n{D1}\n\n> ---\n\n{D6A}"}
        ),
    )
    assert result.code is ProcessCode.INVALID_MODEL_OUTPUT
    assert artifacts(ws, "Process Result") == []
    reviewer = FakeModelRuntime([review_output()])
    review = review_standard_requirement(ws, reviewer, requirement.id, policies=HR_ONLY)
    assert not review.is_normal and not reviewer.was_invoked
    assert artifacts(ws, "Review Result") == []
    assert ws.requirements[requirement.id].state == "Process"


# -- ARP1 recovery: the exact FR-0129 history shape, offline ---------------------

INFO_FINDING = {
    "kind": "AMBIGUOUS",
    "severity": "INFO",
    "detail": "Which runtimes are meant is unclear.",
}
P4_FIRST = "Values are 1 to 32 ASCII letters."


def answered(ref):
    return {"item": ref, "outcome": "RESOLVED", "explanation": "Settled by source."}


def confirmed(ref):
    return {"item": ref, "outcome": "CONFIRMED", "reason": "Answered."}


def arp1_shape():
    """Process 1-4, Review 1-3, Process 4 unreviewed and paraphrasing D6-A as
    the pre-rule code let it (nothing protected), Requirement in Review."""
    ws, requirement, root = rooted()
    model = FakeModelRuntime(
        [analysis_output(normalized_changes={"constraints_edge_cases": CONSTRAINTS})]
    )
    assert process_standard_requirement(
        ws, model, requirement.id, policies=D6A_ONLY
    ).is_normal
    previous = None
    for review in (1, 2, 3):
        reviewer = FakeModelRuntime(
            [
                review_output(
                    new_findings=[INFO_FINDING],
                    rework_verifications=[confirmed(previous)] if previous else [],
                )
            ]
        )
        assert review_standard_requirement(
            ws, reviewer, requirement.id, policies=D6A_ONLY
        ).is_normal
        assert rework_standard_requirement(ws, requirement.id).is_normal
        previous = f"R000{review}.N0"
        constraints = (
            f"{P4_FIRST}\n\n{D1}\n\n{D6A_AS_NORMALIZED}" if review == 3 else CONSTRAINTS
        )
        model = FakeModelRuntime(
            [
                analysis_output(
                    normalized_changes={"constraints_edge_cases": constraints},
                    rework=[answered(previous)],
                )
            ]
        )
        assert process_standard_requirement(
            ws,
            model,
            requirement.id,
            policies=DISABLED if review == 3 else D6A_ONLY,
            authorized_new_cycle=True,
        ).is_normal
    return ws, requirement, root


def test_the_arp1_recovery_lineage_creates_process_5_and_review_4():
    ws, requirement, root = arp1_shape()
    assert len(artifacts(ws, "Process Result")) == 4
    assert len(artifacts(ws, "Review Result")) == 3
    assert ws.requirements[requirement.id].state == "Review"
    p4_node, p4 = latest_process(ws)
    assert p4.iteration == 4 and D6A not in ws.content[root.secret]
    history = {d.secret: ws.content[d.secret] for d in ws.documents if d != root}

    # 1-2. Operator: Review -> Process, then restore only the D6-A paragraph.
    set_state(ws, requirement, "Process")
    ws.content[root.secret] = ws.content[root.secret].replace(D6A_AS_NORMALIZED, D6A)
    # 3. The tree is neither Process 4's output nor its input.
    assert P4_FIRST in ws.content[root.secret]
    assert ws.content[root.secret] != p4.normalized.document(p4.requirement_id)
    assert ws.content[root.secret].count(D6A) == 1

    # 4. The production dispatcher's ordinary route creates exactly Process 5.
    model = FakeModelRuntime(
        [
            analysis_output(
                normalized_changes={
                    "constraints_edge_cases": f"{P4_FIRST}\n\n{D1}\n\n{D6A}"
                },
                rework=[answered("R0003.N0")],
            )
        ]
    )
    workers = replace(
        real_workers(ws),
        process_standard=lambda entity, **options: process_standard_requirement(
            ws, model, entity, policies=D6A_ONLY, **options
        ),
    )
    outcome = dispatch_current(ws, workers, requirement.id)
    assert outcome.worker_result.code is ProcessCode.REQUIREMENT_PROCESSED, outcome
    assert len(artifacts(ws, "Process Result")) == 5
    _, p5 = latest_process(ws)
    assert p5.iteration == 5 and p5.rework_brief.source

    # 5. An independent Review creates Review 4, bound to Process 5.
    reviewer = FakeModelRuntime(
        [review_output(rework_verifications=[confirmed("R0003.N0")])]
    )
    assert review_standard_requirement(
        ws, reviewer, requirement.id, policies=D6A_ONLY
    ).is_normal
    reviews = artifacts(ws, "Review Result")
    assert len(reviews) == 4
    review = parse_review_result(ws.content[reviews[-1].secret])
    assert (review.iteration, review.reviewed_process_iteration) == (4, 5)

    # 6. History unchanged, Process 4 included.
    assert {s: ws.content[s] for s in history} == history
    assert ws.content[p4_node.secret] == history[p4_node.secret]
    # 7. Current Ready evidence.
    assert ws.requirements[requirement.id].state == "Ready"
    evidence = read_ready_evidence(ws, requirement.id, D6A_ONLY)
    assert evidence.latest_review.iteration == 4
    assert evidence.latest_process.iteration == 5
