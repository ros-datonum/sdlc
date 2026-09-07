"""Audit finding A6: comparison evidence and Category metadata in prompts.

The model was shown the other Standard Requirements as an ID/title index
capped at 100 and told the target's Type as its Category. Every scenario
here drives the real entry points with a recording fake runtime and asserts
on the context the model actually received: the evidence must be present,
labelled truthfully and never silently cut.
"""

from __future__ import annotations

import pytest

from processor_fake import (
    FakeModelRuntime,
    build_workspace,
    candidate,
    model_output,
)
from review_fake import build_review_workspace, finding, relation, review_output
from sdlc.comparison_context import (
    COMPARISON_INPUT_LIMIT_CHARACTERS,
    COMPARISON_RECORD_LIMIT,
    MAX_ASSEMBLED_INPUT_CHARS,
    STANDING_APPROVED,
    STANDING_CANDIDATE,
)
from sdlc.fibery_workspace import DocumentNode, FiberyError, RequirementRecord
from sdlc.model_runtime import assemble_model_input
from sdlc.raw_processor import process_raw_requirement
from sdlc.results import ProcessResultCode as RawCode
from sdlc.results import StandardProcessResultCode as ProcessCode
from sdlc.results import StandardReviewResultCode as ReviewCode
from sdlc.standard_analysis import FindingKind
from sdlc.standard_processor import process_standard_requirement
from sdlc.standard_reviewer import review_standard_requirement
from standard_fake import analysis_output, build_standard_workspace, set_state

CONSTRAINT = "must never exceed 250 milliseconds at the 99th percentile"
RAW_OUTPUT = model_output([candidate()])


def peer(
    number,
    title="Fast responses",
    state="Applied",
    category="NON_FUNCTIONAL",
    **changes,
):
    values = {
        "id": f"std-peer-{number}",
        "public_id": str(number),
        "requirement_id": f"SDLC-FR-{number:04d}",
        "title": title,
        "type_name": "Standard",
        "state": state,
        "revision": 1,
        "project_id": "p-1",
        "source_fingerprint": None,
        "category": category,
    }
    return RequirementRecord(**{**values, **changes})


def with_root(ws, record, body=None):
    """Attach a distinctive, multi-section Root Document to a peer."""
    body = body or (
        f"# {record.requirement_id} — {record.title}\n\n"
        f"## Requirement\n\nEvery response {CONSTRAINT} (peer {record.public_id}).\n\n"
        f"## Constraints & Edge Cases\n\nMeasured at the API boundary (peer {record.public_id}).\n\n"
        f"## Non-Goals\n\nBatch jobs are excluded (peer {record.public_id}).\n"
    )
    ws.documents = [d for d in ws.documents if d.entity_public_id != record.public_id]
    ws.documents.append(
        DocumentNode(
            id=f"peer-doc-{record.public_id}",
            name=f"{record.requirement_id} — {record.title}",
            folder_id="f-approved" if record.state == "Applied" else "f-draft",
            entity_public_id=record.public_id,
            secret=f"peer-secret-{record.public_id}",
        )
    )
    ws.content[f"peer-secret-{record.public_id}"] = body
    return f"peer-secret-{record.public_id}"


# -- one adapter per stage ---------------------------------------------------


class Stage:
    def __init__(self, name, build, run, codes, ok_output):
        self.name, self.build, self.run, self.codes, self.ok_output = (
            name,
            build,
            run,
            codes,
            ok_output,
        )

    def __repr__(self):
        return self.name


def _raw_build(peers):
    ws, raw, _ = build_workspace(standards=list(peers))
    return ws, raw


def _process_build(peers):
    ws, std, _ = build_standard_workspace(others=list(peers))
    return ws, std


def _review_build(peers, findings=(), relations=()):
    ws, req, _, _ = build_review_workspace(
        others=list(peers), findings=findings, relations=relations
    )
    return ws, req


RAW = Stage(
    "raw",
    _raw_build,
    lambda ws, r, m, **kw: process_raw_requirement(ws, m, r.id, **kw),
    {
        "ok": RawCode.RAW_REQUIREMENT_PROCESSED,
        "context": RawCode.COMPARISON_CONTEXT_INCOMPLETE,
    },
    RAW_OUTPUT,
)
PROCESS = Stage(
    "process",
    _process_build,
    lambda ws, r, m, **kw: process_standard_requirement(ws, m, r.id, **kw),
    {
        "ok": ProcessCode.REQUIREMENT_PROCESSED,
        "context": ProcessCode.COMPARISON_CONTEXT_INCOMPLETE,
    },
    analysis_output(),
)
REVIEW = Stage(
    "review",
    _review_build,
    lambda ws, r, m, **kw: review_standard_requirement(ws, m, r.id, **kw),
    {
        "ok": ReviewCode.REQUIREMENT_REVIEWED,
        "context": ReviewCode.COMPARISON_CONTEXT_INCOMPLETE,
    },
    review_output(),
)
STAGES = [RAW, PROCESS, REVIEW]


def run_with_peers(stage, peers, bodies=None):
    ws, target = stage.build(peers)
    for record in peers:
        with_root(ws, record, (bodies or {}).get(record.id))
    model = FakeModelRuntime([stage.ok_output])
    before = len(ws.mutations)
    result = stage.run(ws, target, model)
    return ws, target, model, result, before


def context_of(model):
    return model.calls[0]["context"]


# -- the audited defect: title-only comparison, Type as Category ------------


@pytest.mark.parametrize("stage", STAGES, ids=repr)
def test_distinctive_peer_text_reaches_the_model(stage):
    _, _, model, result, _ = run_with_peers(stage, [peer(41)])

    assert result.code is stage.codes["ok"], result
    context = context_of(model)
    assert "SDLC-FR-0041" in context and "Fast responses" in context
    assert CONSTRAINT in context, "the peer's obligation, not only its title"


@pytest.mark.parametrize("stage", STAGES, ids=repr)
def test_all_root_sections_of_a_peer_are_preserved(stage):
    _, _, model, _, _ = run_with_peers(stage, [peer(41)])

    context = context_of(model)
    for section in ("## Requirement", "## Constraints & Edge Cases", "## Non-Goals"):
        assert section in context
    assert "Batch jobs are excluded (peer 41)" in context


@pytest.mark.parametrize("stage", STAGES, ids=repr)
def test_same_title_peers_with_different_obligations_stay_distinct(stage):
    first = peer(41, title="Latency")
    second = peer(42, title="Latency")
    bodies = {
        first.id: "# SDLC-FR-0041 — Latency\n\n## Requirement\n\nReads answer within 100 ms.\n",
        second.id: "# SDLC-FR-0042 — Latency\n\n## Requirement\n\nWrites answer within 900 ms.\n",
    }
    _, _, model, _, _ = run_with_peers(stage, [first, second], bodies)

    context = context_of(model)
    assert "within 100 ms" in context and "within 900 ms" in context
    assert context.index("## SDLC-FR-0041 — Latency") < context.index(
        "## SDLC-FR-0042 — Latency"
    )


@pytest.mark.parametrize("stage", [PROCESS, REVIEW], ids=repr)
def test_the_target_receives_its_actual_category_not_its_type(stage):
    ws, target = stage.build([])
    ws.requirements[target.id] = RequirementRecord(
        **{**target.__dict__, "category": "CONSTRAINT"}
    )
    model = FakeModelRuntime([stage.ok_output])

    stage.run(ws, ws.requirements[target.id], model)

    lines = context_of(model).splitlines()
    assert "Type: Standard" in lines
    assert "Category: CONSTRAINT" in lines
    assert "Category: Standard" not in lines


@pytest.mark.parametrize("stage", [PROCESS, REVIEW], ids=repr)
def test_an_absent_target_category_is_unspecified_not_inferred(stage):
    ws, target = stage.build([])
    model = FakeModelRuntime([stage.ok_output])

    stage.run(ws, target, model)

    lines = context_of(model).splitlines()
    assert "Category: unspecified" in lines
    assert "Category: Standard" not in lines and "Category: FUNCTIONAL" not in lines


@pytest.mark.parametrize("stage", STAGES, ids=repr)
@pytest.mark.parametrize(
    "category", ["FUNCTIONAL", "NON_FUNCTIONAL", "CONSTRAINT", None]
)
def test_peers_carry_their_actual_category_and_state(stage, category):
    _, _, model, _, _ = run_with_peers(
        stage, [peer(41, category=category, state="Draft")]
    )

    block = context_of(model).split("## SDLC-FR-0041")[1]
    assert f"Category: {category or 'unspecified'}" in block
    assert "State: Draft" in block and "Type: Standard" in block


@pytest.mark.parametrize("stage", STAGES, ids=repr)
def test_only_applied_peers_are_labelled_approved(stage):
    _, _, model, _, _ = run_with_peers(
        stage, [peer(41, state="Applied"), peer(42, state="Draft")]
    )

    context = context_of(model)
    applied = context.split("## SDLC-FR-0041")[1].split("## SDLC-FR-0042")[0]
    draft = context.split("## SDLC-FR-0042")[1]
    assert STANDING_APPROVED in applied and STANDING_CANDIDATE not in applied
    assert STANDING_CANDIDATE in draft and STANDING_APPROVED not in draft


# -- the corpus: exclusions, order, completeness -----------------------------


@pytest.mark.parametrize("stage", [PROCESS, REVIEW], ids=repr)
def test_the_target_is_not_listed_among_its_own_peers(stage):
    _, target, model, _, _ = run_with_peers(stage, [peer(41)])

    context = context_of(model)
    assert f"## {target.requirement_id}" not in context


@pytest.mark.parametrize("stage", STAGES, ids=repr)
def test_raw_records_and_foreign_projects_are_not_comparison_material(stage):
    ws, target = stage.build([peer(41)])
    with_root(ws, peer(41))
    foreign = peer(77, project_id="p-2", title="Foreign")
    raw = peer(78, type_name="Raw", title="Another RAW")
    ws.requirements[foreign.id] = foreign
    ws.requirements[raw.id] = raw
    with_root(ws, foreign)
    with_root(ws, raw)
    model = FakeModelRuntime([stage.ok_output])

    result = stage.run(ws, target, model)

    assert result.code is stage.codes["ok"], result
    context = context_of(model)
    assert "SDLC-FR-0077" not in context and "SDLC-FR-0078" not in context


@pytest.mark.parametrize("stage", STAGES, ids=repr)
def test_peer_order_is_deterministic_regardless_of_server_order(stage):
    peers = [peer(43), peer(41), peer(42)]  # the fake returns insertion order
    _, _, model, _, _ = run_with_peers(stage, peers)

    context = context_of(model)
    positions = [context.index(f"## SDLC-FR-00{n}") for n in (41, 42, 43)]
    assert positions == sorted(positions)


@pytest.mark.parametrize("stage", STAGES, ids=repr)
def test_a_corpus_exactly_at_the_limit_is_admitted(stage):
    peers = [peer(1000 + n) for n in range(COMPARISON_RECORD_LIMIT)]
    _, _, model, result, _ = run_with_peers(stage, peers)

    assert result.code is stage.codes["ok"], result
    context = context_of(model)
    assert all(
        f"## SDLC-FR-{1000 + n}" in context for n in range(COMPARISON_RECORD_LIMIT)
    )
    assert (
        "more"
        not in context.split("# Other Standard Requirements")[1].split("# Allowed")[0]
    )


@pytest.mark.parametrize("stage", STAGES, ids=repr)
def test_one_peer_above_the_limit_refuses_instead_of_dropping_it(stage):
    peers = [peer(1000 + n) for n in range(COMPARISON_RECORD_LIMIT + 1)]
    ws, _, model, result, before = run_with_peers(stage, peers)

    assert result.code is stage.codes["context"], result
    assert "more than 100" in result.message and "at least 101" in result.message
    assert not model.was_invoked
    assert ws.mutations[before:] == []


@pytest.mark.parametrize("stage", STAGES, ids=repr)
def test_a_query_level_cut_cannot_pass_as_a_complete_corpus(stage):
    """The fake caps its query like the live one: limit + 1 rows, never fewer."""
    peers = [peer(1000 + n) for n in range(COMPARISON_RECORD_LIMIT + 40)]
    ws, target = stage.build(peers)
    for record in peers:
        with_root(ws, record)
    assert (
        len(ws.standard_requirements_in_project("p-1")) == COMPARISON_RECORD_LIMIT + 2
    )
    model = FakeModelRuntime([stage.ok_output])

    result = stage.run(ws, target, model)

    assert result.code is stage.codes["context"]
    assert "at least" in result.message, "a lower bound, not an exact total"
    assert not model.was_invoked


@pytest.mark.parametrize("stage", STAGES, ids=repr)
def test_an_oversized_corpus_refuses_without_truncation(stage):
    huge = "# SDLC-FR-0041 — Fast responses\n\n## Requirement\n\n" + (
        "x" * COMPARISON_INPUT_LIMIT_CHARACTERS
    )
    ws, _, model, result, before = run_with_peers(
        stage, [peer(41)], {"std-peer-41": huge}
    )

    assert result.code is stage.codes["context"], result
    assert "input budget" in result.message and "not truncated" in result.message
    assert not model.was_invoked
    assert ws.mutations[before:] == []


# -- missing or ambiguous evidence ------------------------------------------


@pytest.mark.parametrize("stage", STAGES, ids=repr)
def test_a_peer_without_a_root_document_refuses_rather_than_becoming_a_title(stage):
    ws, target = stage.build([peer(41)])
    ws.documents = [d for d in ws.documents if d.entity_public_id != "41"]
    model = FakeModelRuntime([stage.ok_output])
    before = len(ws.mutations)

    result = stage.run(ws, target, model)

    assert result.code is stage.codes["context"], result
    assert "SDLC-FR-0041" in result.message and "0 attached" in result.message
    assert not model.was_invoked and ws.mutations[before:] == []


@pytest.mark.parametrize("stage", STAGES, ids=repr)
def test_a_peer_with_an_empty_root_refuses(stage):
    ws, _, model, result, before = run_with_peers(
        stage, [peer(41)], {"std-peer-41": "   \n"}
    )

    assert result.code is stage.codes["context"]
    assert "empty" in result.message and "SDLC-FR-0041" in result.message
    assert not model.was_invoked and ws.mutations[before:] == []


@pytest.mark.parametrize("stage", STAGES, ids=repr)
def test_an_unreadable_peer_root_refuses_and_is_never_silently_dropped(stage):
    ws, target = stage.build([peer(41)])
    secret = with_root(ws, peer(41))
    original = ws.read_document_content

    def failing(value):
        if value == secret:
            raise FiberyError("induced")
        return original(value)

    ws.read_document_content = failing
    model = FakeModelRuntime([stage.ok_output])
    before = len(ws.mutations)

    result = stage.run(ws, target, model)

    assert result.code is stage.codes["context"], result
    assert "SDLC-FR-0041" in result.message
    assert "induced" not in " ".join((result.message, *result.details))
    assert not model.was_invoked and ws.mutations[before:] == []


@pytest.mark.parametrize("stage", STAGES, ids=repr)
def test_ambiguous_or_unidentified_peers_refuse(stage):
    duplicate = peer(42, requirement_id="SDLC-FR-0041")
    unidentified = peer(43, requirement_id=None)
    ws, _, model, result, before = run_with_peers(
        stage, [peer(41), duplicate, unidentified]
    )

    assert result.code is stage.codes["context"]
    assert any("ambiguous" in d for d in result.details)
    assert any("no Requirement ID" in d for d in result.details)
    assert not model.was_invoked and ws.mutations[before:] == []


def test_a_peer_with_two_attached_roots_refuses():
    ws, target = PROCESS.build([peer(41)])
    with_root(ws, peer(41))
    ws.documents.append(
        DocumentNode(
            id="second-root",
            name="x",
            folder_id=None,
            entity_public_id="41",
            secret="s2",
        )
    )
    model = FakeModelRuntime([analysis_output()])

    result = PROCESS.run(ws, target, model)

    assert result.code is ProcessCode.COMPARISON_CONTEXT_INCOMPLETE
    assert "2 attached" in result.message and not model.was_invoked


# -- Review: every claimed target must be evidence ----------------------------


def test_a_relation_targets_actual_text_reaches_the_reviewer():
    ws, req = _review_build(
        [peer(41)], relations=[relation(requirement_id="SDLC-FR-0041")]
    )
    with_root(ws, peer(41))
    model = FakeModelRuntime(
        [
            review_output(
                relation_verifications=[
                    {
                        "kind": "DEPENDS_ON",
                        "requirement_id": "SDLC-FR-0041",
                        "outcome": "CONFIRMED",
                        "reason": "ok",
                    }
                ]
            )
        ]
    )

    result = review_standard_requirement(ws, model, req.id)

    assert result.code is ReviewCode.REQUIREMENT_REVIEWED, result
    assert CONSTRAINT in context_of(model)


def test_a_comparison_findings_target_reaches_the_reviewer():
    claim = finding(
        FindingKind.POSSIBLE_DUPLICATE, "Looks alike.", requirement_id="SDLC-FR-0041"
    )
    ws, req = _review_build([peer(41)], findings=[claim])
    with_root(ws, peer(41))
    model = FakeModelRuntime(
        [
            review_output(
                finding_verifications=[
                    {
                        "process_finding_index": 0,
                        "outcome": "REJECTED",
                        "reason": "Different obligations.",
                    }
                ]
            )
        ]
    )

    result = review_standard_requirement(ws, model, req.id)

    assert result.code is ReviewCode.REQUIREMENT_REVIEWED, result
    assert CONSTRAINT in context_of(model)


@pytest.mark.parametrize(
    ("label", "peers"),
    [
        ("unknown", []),
        ("foreign", [peer(41, project_id="p-2")]),
        ("raw", [peer(41, type_name="Raw")]),
        ("ambiguous", [peer(41), peer(42, requirement_id="SDLC-FR-0041")]),
    ],
)
def test_a_claimed_target_without_same_project_evidence_refuses_before_the_model(
    label, peers
):
    ws, req = _review_build(peers, relations=[relation(requirement_id="SDLC-FR-0041")])
    for auto in [
        r.id for r in ws.requirements.values() if r.id.startswith("std-target-")
    ]:
        del ws.requirements[
            auto
        ]  # the fixture's convenience target; this test wants none
    for record in peers:
        with_root(ws, record)
    model = FakeModelRuntime([review_output()])
    before = len(ws.mutations)

    result = review_standard_requirement(ws, model, req.id)

    assert result.code is ReviewCode.COMPARISON_CONTEXT_INCOMPLETE, (label, result)
    assert not model.was_invoked
    assert ws.mutations[before:] == []
    assert ws.requirements[req.id].state == "Review"


def test_a_claimed_target_with_an_unreadable_root_is_not_verified_by_title():
    ws, req = _review_build(
        [peer(41)], relations=[relation(requirement_id="SDLC-FR-0041")]
    )
    ws.documents = [d for d in ws.documents if d.entity_public_id != "41"]
    model = FakeModelRuntime([review_output()])

    result = review_standard_requirement(ws, model, req.id)

    assert result.code is ReviewCode.COMPARISON_CONTEXT_INCOMPLETE
    assert not model.was_invoked


# -- no-model paths never hydrate the corpus ----------------------------------


def peer_reads(ws, secret):
    reads = []
    original = ws.read_document_content

    def recording(value):
        if value == secret:
            reads.append(value)
        return original(value)

    ws.read_document_content = recording
    return reads


def test_a_valid_persisted_raw_result_resumes_without_reading_peers():
    ws, raw = _raw_build([peer(41)])
    secret = with_root(ws, peer(41))
    first = process_raw_requirement(ws, FakeModelRuntime([RAW_OUTPUT]), raw.id)
    assert first.code is RawCode.RAW_REQUIREMENT_PROCESSED
    set_state(ws, raw, "Process")
    reads = peer_reads(ws, secret)
    model = FakeModelRuntime([RAW_OUTPUT])

    resumed = process_raw_requirement(ws, model, raw.id)

    assert resumed.code is RawCode.RAW_REQUIREMENT_PROCESSED
    assert not model.was_invoked and reads == []


def test_a_no_change_standard_process_reads_no_peers():
    ws, std = _process_build([peer(41)])
    secret = with_root(ws, peer(41))
    first = process_standard_requirement(
        ws, FakeModelRuntime([analysis_output()]), std.id
    )
    assert first.code is ProcessCode.REQUIREMENT_PROCESSED
    set_state(ws, std, "Process")
    reads = peer_reads(ws, secret)
    model = FakeModelRuntime([analysis_output()])

    again = process_standard_requirement(ws, model, std.id)

    assert again.code is ProcessCode.NO_CHANGES_TO_PROCESS
    assert not model.was_invoked and reads == []


def test_a_no_change_review_reads_no_peers():
    ws, req = _review_build([peer(41)])
    secret = with_root(ws, peer(41))
    first = review_standard_requirement(ws, FakeModelRuntime([review_output()]), req.id)
    assert first.code is ReviewCode.REQUIREMENT_REVIEWED
    set_state(ws, req, "Review")
    reads = peer_reads(ws, secret)
    model = FakeModelRuntime([review_output()])

    again = review_standard_requirement(ws, model, req.id)

    assert again.code is ReviewCode.NO_CHANGES_TO_REVIEW
    assert not model.was_invoked and reads == []


@pytest.mark.parametrize("stage", STAGES, ids=repr)
def test_an_eligible_empty_shell_regeneration_receives_the_comparison_context(stage):
    ws, target = stage.build([peer(41)])
    with_root(ws, peer(41))
    ws.failures["write_document_content"] = FiberyError("body write failed")
    stage.run(ws, target, FakeModelRuntime([stage.ok_output]))
    suffix = {
        "raw": "Processing Result",
        "process": "Process Result 0001",
        "review": "Review Result 0001",
    }[stage.name]
    [shell] = [d for d in ws.documents if d.name.endswith(suffix)]
    model = FakeModelRuntime([stage.ok_output])

    result = stage.run(ws, target, model, recover_empty_result=shell.id)

    assert result.code is stage.codes["ok"], result
    assert CONSTRAINT in context_of(model)


@pytest.mark.parametrize("stage", STAGES, ids=repr)
def test_a_refused_recovery_reads_no_peers(stage):
    ws, target = stage.build([peer(41)])
    secret = with_root(ws, peer(41))
    reads = peer_reads(ws, secret)
    model = FakeModelRuntime([stage.ok_output])

    result = stage.run(ws, target, model, recover_empty_result="not-a-shell")

    assert result.code is not stage.codes["ok"]
    assert not model.was_invoked and reads == []


# -- the complete assembled input is bounded, not only the peer section -------


PRIVATE_LINE = "PRIVATE-SOURCE-LINE-4c1d"
PADDING_SECTION = "\n\n## Padding\n\n"


def _target_root(ws, target, stage):
    """The target's Root Document secret, whichever stage built the fixture."""
    [document] = [d for d in ws.documents if d.entity_public_id == target.public_id]
    return document.secret


def pad_target(ws, target, stage, filler):
    """Append a padding section to the target's Root; the fake stops
    re-serializing so the assembled length moves exactly with the padding."""
    ws.reserializes = False
    secret = _target_root(ws, target, stage)
    ws.content[secret] = (
        ws.content[secret].rstrip("\n") + PADDING_SECTION + filler + "\n"
    )
    return secret


def assembled_of(model):
    call = model.calls[0]
    return assemble_model_input(call["prompt"], call["context"])


def run_padded(stage, filler, peers=(), bodies=None):
    ws, target = stage.build(list(peers))
    for record in peers:
        with_root(ws, record, (bodies or {}).get(record.id))
    pad_target(ws, target, stage, filler)
    model = FakeModelRuntime([stage.ok_output])
    before = len(ws.mutations)
    result = stage.run(ws, ws.requirements[target.id], model)
    return ws, model, result, before


def assert_refused_whole(stage, ws, model, result, before, label):
    assert result.code is stage.codes["context"], (label, result)
    assert not model.was_invoked
    assert result.model_invoked is False
    assert ws.mutations[before:] == []
    assert (
        not [d for d in ws.documents if "Result" in d.name and d.name.endswith("0001")]
        or stage is REVIEW
    )
    text = " ".join((result.message, *result.details))
    assert (
        "complete assembled model input" in text
        and str(MAX_ASSEMBLED_INPUT_CHARS) in text
    )
    assert "without truncation" in text
    assert PRIVATE_LINE not in text and "x" * 50 not in text


@pytest.mark.parametrize("stage", STAGES, ids=repr)
def test_an_oversized_target_with_a_small_peer_section_is_refused_whole(stage):
    filler = PRIVATE_LINE + "x" * (MAX_ASSEMBLED_INPUT_CHARS + 1)
    ws, model, result, before = run_padded(stage, filler, peers=[peer(41)])

    assert_refused_whole(stage, ws, model, result, before, "oversized target")
    assert "characters, above the" in result.message


@pytest.mark.parametrize("stage", STAGES, ids=repr)
def test_sections_each_below_the_limit_but_together_above_it_are_refused(stage):
    half = MAX_ASSEMBLED_INPUT_CHARS // 2 + 10_000
    peer_body = "# SDLC-FR-0041 — T\n\n## Requirement\n\n" + "p" * half + "\n"
    ws, model, result, before = run_padded(
        stage, "x" * half, peers=[peer(41)], bodies={"std-peer-41": peer_body}
    )

    assert_refused_whole(stage, ws, model, result, before, "combined sections")


def test_a_review_enlarged_by_its_bound_process_claims_is_refused_whole():
    claims = [finding(FindingKind.AMBIGUOUS, "c" * 100_000) for _ in range(3)]
    ws, req = _review_build([peer(41)], findings=claims)
    with_root(
        ws, peer(41), "# SDLC-FR-0041 — T\n\n## Requirement\n\n" + "p" * 120_000 + "\n"
    )
    ws.reserializes = False
    model = FakeModelRuntime([review_output()])
    before = len(ws.mutations)

    result = review_standard_requirement(ws, model, req.id)

    assert_refused_whole(REVIEW, ws, model, result, before, "review claims")


@pytest.mark.parametrize("stage", STAGES, ids=repr)
@pytest.mark.parametrize("unit", ["x", "é"], ids=["ascii", "two-byte-code-point"])
def test_exactly_the_limit_is_admitted_and_one_more_is_refused(stage, unit):
    probe = 1_000
    _, model, result, _ = run_padded(stage, unit * probe, peers=[peer(41)])
    assert result.code is stage.codes["ok"], result
    delta = MAX_ASSEMBLED_INPUT_CHARS - len(assembled_of(model))

    _, model, result, _ = run_padded(stage, unit * (probe + delta), peers=[peer(41)])
    assert result.code is stage.codes["ok"], result
    text = assembled_of(model)
    assert len(text) == MAX_ASSEMBLED_INPUT_CHARS, "counted in code points"
    if unit != "x":
        assert len(text.encode("utf-8")) > MAX_ASSEMBLED_INPUT_CHARS, (
            "bytes are not the unit"
        )
    assert text.startswith("# Project") and unit * (probe + delta) in text

    ws, model, result, before = run_padded(
        stage, unit * (probe + delta + 1), peers=[peer(41)]
    )
    assert_refused_whole(stage, ws, model, result, before, "one above")
    assert str(MAX_ASSEMBLED_INPUT_CHARS + 1) in result.message


@pytest.mark.parametrize("stage", STAGES, ids=repr)
def test_an_admitted_input_reaches_the_runtime_exactly_as_measured(stage):
    _, model, result, _ = run_padded(stage, "x" * 5_000, peers=[peer(41)])

    assert result.code is stage.codes["ok"]
    call = model.calls[0]
    assert assembled_of(model) == f"{call['context']}\n\n{call['prompt']}"
    assert "x" * 5_000 in call["context"] and CONSTRAINT in call["context"]


# -- explicit recovery under the same bound ------------------------------------


@pytest.mark.parametrize("stage", STAGES, ids=repr)
def test_an_oversized_regeneration_input_refuses_and_leaves_the_shell_untouched(stage):
    ws, target = stage.build([peer(41)])
    with_root(ws, peer(41))
    ws.failures["write_document_content"] = FiberyError("body write failed")
    stage.run(ws, target, FakeModelRuntime([stage.ok_output]))
    suffix = {
        "raw": "Processing Result",
        "process": "Process Result 0001",
        "review": "Review Result 0001",
    }[stage.name]
    [shell] = [d for d in ws.documents if d.name.endswith(suffix)]
    assert ws.content[shell.secret] == ""
    pad_target(ws, target, stage, "x" * (MAX_ASSEMBLED_INPUT_CHARS + 1))
    model = FakeModelRuntime([stage.ok_output])
    before = len(ws.mutations)
    documents_before = [(d.id, d.name, d.parent_document_id) for d in ws.documents]

    result = stage.run(
        ws, ws.requirements[target.id], model, recover_empty_result=shell.id
    )

    assert result.code is stage.codes["context"], result
    assert not model.was_invoked and result.model_invoked is False
    assert ws.mutations[before:] == []
    assert ws.content[shell.secret] == ""
    assert [
        (d.id, d.name, d.parent_document_id) for d in ws.documents
    ] == documents_before


# -- no-model paths never assemble or budget a new prompt --------------------


def test_a_valid_raw_resume_ignores_an_oversized_target_and_peers():
    ws, raw = _raw_build([peer(41)])
    with_root(ws, peer(41))
    assert (
        process_raw_requirement(ws, FakeModelRuntime([RAW_OUTPUT]), raw.id).code
        is RawCode.RAW_REQUIREMENT_PROCESSED
    )
    set_state(ws, raw, "Process")
    pad_target(ws, raw, RAW, "x" * (MAX_ASSEMBLED_INPUT_CHARS + 1))
    with_root(
        ws,
        peer(41),
        "# SDLC-FR-0041 — T\n\n## Requirement\n\n"
        + "p" * (MAX_ASSEMBLED_INPUT_CHARS + 1),
    )
    model = FakeModelRuntime([RAW_OUTPUT])

    resumed = process_raw_requirement(ws, model, ws.requirements[raw.id].id)

    assert resumed.code is RawCode.RAW_REQUIREMENT_PROCESSED
    assert not model.was_invoked


@pytest.mark.parametrize("stage", [PROCESS, REVIEW], ids=repr)
def test_a_no_change_path_ignores_oversized_peer_data(stage):
    ws, target = stage.build([peer(41)])
    with_root(ws, peer(41))
    first = stage.run(ws, target, FakeModelRuntime([stage.ok_output]))
    assert first.code is stage.codes["ok"], first
    set_state(ws, target, "Process" if stage is PROCESS else "Review")
    with_root(
        ws,
        peer(41),
        "# SDLC-FR-0041 — T\n\n## Requirement\n\n"
        + "p" * (MAX_ASSEMBLED_INPUT_CHARS + 1),
    )
    model = FakeModelRuntime([stage.ok_output])

    again = stage.run(ws, ws.requirements[target.id], model)

    expected = (
        ProcessCode.NO_CHANGES_TO_PROCESS
        if stage is PROCESS
        else ReviewCode.NO_CHANGES_TO_REVIEW
    )
    assert again.code is expected
    assert not model.was_invoked
