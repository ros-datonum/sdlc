"""Dogfood blocker: self findings that cite a peer must not carry requirement_id.

The consumer contract is unchanged and strict: a finding ABOUT THIS Requirement
carries no `requirement_id` (a peer mentioned as evidence lives in `detail`);
a finding ABOUT ANOTHER Requirement names it in `requirement_id`. What changed
is the producer contract: both model prompts now state the distinction with
positive examples and an explicit negative instruction, so a model that reads
the instructions produces output the strict parser accepts.
"""

from __future__ import annotations

import json
import re

import pytest

from processor_fake import FakeModelRuntime
from review_fake import build_review_workspace, review_output, stored_review
from sdlc.fibery_workspace import RequirementRecord
from sdlc.process_result import parse_process_result
from sdlc.results import StandardProcessResultCode as ProcessCode
from sdlc.results import StandardReviewResultCode as ReviewCode
from sdlc.review_prompt import INSTRUCTIONS as REVIEW_INSTRUCTIONS
from sdlc.standard_analysis import (
    FindingKind,
    InvalidAnalysisOutput,
    parse_analysis_output,
)
from sdlc.standard_processor import process_standard_requirement
from sdlc.standard_prompt import INSTRUCTIONS as PROCESS_INSTRUCTIONS
from sdlc.standard_prompt import build_analysis_prompt
from sdlc.standard_review import InvalidReviewOutput, parse_review_output
from sdlc.standard_reviewer import review_standard_requirement
from standard_fake import analysis_output, build_standard_workspace, process_results

PEER_ID = "SDLC-FR-0002"
PEER = RequirementRecord(
    id="std-peer-2",
    public_id="2",
    requirement_id=PEER_ID,
    title="Structured log fields",
    type_name="Standard",
    state="Applied",
    revision=1,
    project_id="p-1",
    source_fingerprint=None,
)
# The observed dogfood shape: a self finding whose detail cites a peer.
DOGFOOD_DETAIL = (
    f"Neither this Requirement nor {PEER_ID} defines whether the child process "
    "environment is configuration-owned or caller-influenceable."
)
SELF_KINDS = [k for k in FindingKind if not k.is_about_another_requirement]
CROSS_KINDS = [k for k in FindingKind if k.is_about_another_requirement]


def self_finding(**extra):
    return {"kind": "MISSING_CONSTRAINT", "detail": DOGFOOD_DETAIL, **extra}


def cross_finding():
    return {
        "kind": "POSSIBLE_CONFLICT",
        "detail": f"{PEER_ID} enumerates a status set that omits INVALID_REQUEST.",
        "requirement_id": PEER_ID,
    }


def run_process(findings):
    ws, requirement, _root = build_standard_workspace(others=[PEER])
    model = FakeModelRuntime([analysis_output(findings=findings)])
    result = process_standard_requirement(ws, model, requirement.id)
    return ws, model, result


def run_review(new_findings):
    ws, requirement, _root, _ = build_review_workspace(others=[PEER])
    model = FakeModelRuntime(
        [
            review_output(
                new_findings=[{"severity": "WARNING", **f} for f in new_findings]
            )
        ]
    )
    result = review_standard_requirement(ws, model, requirement.id)
    return ws, model, result


# -- Standard Process, through the real stage boundary --------------------------


def test_process_accepts_a_self_finding_that_cites_a_peer_in_its_detail():
    ws, model, result = run_process([self_finding()])
    assert result.code is ProcessCode.REQUIREMENT_PROCESSED, result
    assert PEER_ID in model.calls[0]["context"], "the peer is in the model input"
    stored = parse_process_result(ws.content[process_results(ws)[0].secret])
    [finding] = stored.findings
    assert finding.kind is FindingKind.MISSING_CONSTRAINT
    assert finding.requirement_id is None and finding.detail == DOGFOOD_DETAIL
    assert result.findings == (f"MISSING_CONSTRAINT: {DOGFOOD_DETAIL}",)


def test_process_accepts_an_explicit_null_requirement_id_on_a_self_finding():
    _ws, _model, result = run_process([self_finding(requirement_id=None)])
    assert result.code is ProcessCode.REQUIREMENT_PROCESSED, result


def test_process_still_rejects_the_dogfood_shape_with_the_peer_as_target():
    ws, _model, result = run_process([self_finding(requirement_id=PEER_ID)])
    assert result.code is ProcessCode.INVALID_MODEL_OUTPUT
    assert "must not name another one" in " ".join(result.details)
    assert process_results(ws) == []  # nothing persisted from a rejected output


def test_process_still_accepts_a_genuine_cross_requirement_finding():
    ws, _model, result = run_process([cross_finding(), self_finding()])
    assert result.code is ProcessCode.REQUIREMENT_PROCESSED, result
    stored = parse_process_result(ws.content[process_results(ws)[0].secret])
    assert [(f.kind.value, f.requirement_id) for f in stored.findings] == [
        ("POSSIBLE_CONFLICT", PEER_ID),
        ("MISSING_CONSTRAINT", None),
    ]


def test_process_still_rejects_a_cross_finding_without_its_target():
    _ws, _model, result = run_process([{"kind": "POSSIBLE_DUPLICATE", "detail": "x"}])
    assert result.code is ProcessCode.INVALID_MODEL_OUTPUT
    assert "must name the Requirement it is about" in " ".join(result.details)


def test_an_unknown_cross_target_passes_process_as_an_observation_and_is_refused_at_review():
    """Existing semantics, unchanged: Process records comparison findings as
    observations; Review requires every claimed target to resolve to a real
    same-Project Standard before the reviewer runs."""
    from review_fake import finding

    ws, model, result = run_process(
        [{**cross_finding(), "requirement_id": "SDLC-FR-0999"}]
    )
    assert result.code is ProcessCode.REQUIREMENT_PROCESSED
    ws, requirement, _, _ = build_review_workspace(
        others=[PEER],
        findings=[
            finding(FindingKind.POSSIBLE_CONFLICT, "x", requirement_id="SDLC-FR-0999")
        ],
    )
    model = FakeModelRuntime([review_output()])
    reviewed = review_standard_requirement(ws, model, requirement.id)
    assert reviewed.code is ReviewCode.COMPARISON_CONTEXT_INCOMPLETE
    assert not model.was_invoked


# -- Standard Review, through the real stage boundary ----------------------------


def test_review_accepts_a_self_new_finding_that_cites_a_peer_in_its_detail():
    ws, model, result = run_review([self_finding()])
    assert result.code is ReviewCode.REQUIREMENT_REVIEWED, result
    assert PEER_ID in model.calls[0]["context"]
    [finding] = stored_review(ws).new_findings
    assert finding.requirement_id is None and finding.detail == DOGFOOD_DETAIL


def test_review_still_rejects_the_dogfood_shape_with_the_peer_as_target():
    ws, _model, result = run_review([self_finding(requirement_id=PEER_ID)])
    assert result.code is ReviewCode.INVALID_MODEL_OUTPUT
    assert "must not name another one" in " ".join(result.details)
    assert [d for d in ws.documents if "Review Result" in d.name] == []


def test_review_still_accepts_a_genuine_cross_new_finding():
    ws, _model, result = run_review([cross_finding()])
    assert result.code is ReviewCode.REQUIREMENT_REVIEWED, result
    [finding] = stored_review(ws).new_findings
    assert finding.requirement_id == PEER_ID


def test_review_still_rejects_a_cross_new_finding_without_its_target():
    _ws, _model, result = run_review([{"kind": "POSSIBLE_DUPLICATE", "detail": "x"}])
    assert result.code is ReviewCode.INVALID_MODEL_OUTPUT


# -- the parsers themselves stay strict ------------------------------------------


@pytest.mark.parametrize("kind", [k.value for k in SELF_KINDS])
def test_every_self_kind_rejects_a_requirement_id(kind):
    with pytest.raises(InvalidAnalysisOutput, match="must not name another"):
        parse_analysis_output(
            analysis_output(
                findings=[{"kind": kind, "detail": "x", "requirement_id": PEER_ID}]
            )
        )
    with pytest.raises(InvalidReviewOutput, match="must not name another"):
        parse_review_output(
            review_output(
                new_findings=[
                    {
                        "kind": kind,
                        "severity": "INFO",
                        "detail": "x",
                        "requirement_id": PEER_ID,
                    }
                ]
            ),
            (),
            (),
        )


@pytest.mark.parametrize("kind", [k.value for k in CROSS_KINDS])
def test_every_cross_kind_requires_a_requirement_id(kind):
    with pytest.raises(InvalidAnalysisOutput, match="must name the Requirement"):
        parse_analysis_output(analysis_output(findings=[{"kind": kind, "detail": "x"}]))
    with pytest.raises(InvalidReviewOutput, match="must name the Requirement"):
        parse_review_output(
            review_output(
                new_findings=[{"kind": kind, "severity": "INFO", "detail": "x"}]
            ),
            (),
            (),
        )


def test_unknown_kinds_and_fields_are_still_rejected():
    with pytest.raises(InvalidAnalysisOutput):
        parse_analysis_output(
            analysis_output(findings=[{"kind": "SLOPPY", "detail": "x"}])
        )
    with pytest.raises(InvalidAnalysisOutput):
        parse_analysis_output(
            analysis_output(
                findings=[{**self_finding(), "cited_requirement_ids": [PEER_ID]}]
            )
        )


# -- the producer contract in both prompts ----------------------------------------


def listed_kinds(instructions: str, label: str) -> list[str]:
    """The kinds the prompt lists under 'ABOUT THIS' or 'ABOUT ANOTHER'."""
    match = re.search(rf"ABOUT {label} Requirement \(([^)]*)\)", instructions)
    assert match, f"the prompt no longer states which kinds are ABOUT {label}"
    return [k.strip() for k in match.group(1).replace("\n", " ").split(",")]


@pytest.mark.parametrize(
    "instructions",
    [PROCESS_INSTRUCTIONS, REVIEW_INSTRUCTIONS],
    ids=["process", "review"],
)
def test_the_prompt_partitions_the_finding_kinds_exactly_as_the_parser_does(
    instructions,
):
    assert listed_kinds(instructions, "THIS") == [k.value for k in SELF_KINDS]
    assert listed_kinds(instructions, "ANOTHER") == [k.value for k in CROSS_KINDS]


@pytest.mark.parametrize(
    "instructions",
    [PROCESS_INSTRUCTIONS, REVIEW_INSTRUCTIONS],
    ids=["process", "review"],
)
def test_the_prompt_shows_a_self_example_citing_a_peer_in_detail_and_a_cross_example(
    instructions,
):
    examples = re.findall(r"\{[^{}]*\"kind\"[^{}]*\}", instructions)
    parsed = []
    for text in examples:
        try:
            parsed.append(json.loads(re.sub(r"\s+", " ", text)))
        except ValueError:
            continue
    self_examples = [e for e in parsed if e.get("kind") == "MISSING_CONSTRAINT"]
    cross_examples = [e for e in parsed if e.get("kind") == "POSSIBLE_CONFLICT"]
    assert self_examples and cross_examples, "both examples must be valid JSON"
    [self_example], [cross_example] = self_examples, cross_examples
    assert self_example["requirement_id"] is None and PEER_ID in self_example["detail"]
    assert cross_example["requirement_id"] == PEER_ID
    assert "never in `requirement_id`" in instructions
    assert "rejected as a whole" in instructions
    assert "only for findings about another Requirement" not in instructions


def test_the_examples_in_the_prompts_parse_under_the_strict_contracts():
    process_examples = [
        json.loads(re.sub(r"\s+", " ", t))
        for t in re.findall(
            r"\{[^{}]*\"kind\": \"(?:MISSING_CONSTRAINT|POSSIBLE_CONFLICT)\"[^{}]*\}",
            PROCESS_INSTRUCTIONS,
        )
    ]
    parsed = parse_analysis_output(analysis_output(findings=process_examples))
    assert [(f.kind.value, f.requirement_id) for f in parsed.findings] == [
        ("MISSING_CONSTRAINT", None),
        ("POSSIBLE_CONFLICT", PEER_ID),
    ]
    review_examples = [
        json.loads(re.sub(r"\s+", " ", t))
        for t in re.findall(
            r"\{[^{}]*\"kind\": \"(?:MISSING_CONSTRAINT|POSSIBLE_CONFLICT)\"[^{}]*\}",
            REVIEW_INSTRUCTIONS,
        )
    ]
    parsed = parse_review_output(review_output(new_findings=review_examples), (), ())
    assert [(f.kind.value, f.requirement_id) for f in parsed.new_findings] == [
        ("MISSING_CONSTRAINT", None),
        ("POSSIBLE_CONFLICT", PEER_ID),
    ]


def test_the_built_prompts_carry_the_rule_and_the_peer_context():
    ws, requirement, _root = build_standard_workspace(others=[PEER])
    from sdlc.comparison_context import assemble_comparison_context

    comparison = assemble_comparison_context(ws, "p-1", requirement.id, [PEER])
    prompt, context = build_analysis_prompt(
        requirement=requirement,
        project_name="SDLC",
        root_content="# x",
        child_content="",
        raw_ancestry="",
        comparison=comparison,
    )
    assert "ABOUT THIS Requirement" in prompt and PEER_ID in context


# -- IMPLEMENTATION_LEAKAGE (RW-R03) is a self finding in both stages ------------

LEAKAGE_DETAIL = (
    "Detailed Behavior prescribes a watchdog thread; the source requires only "
    f"bounded execution, and {PEER_ID} states no mechanism either."
)


def leakage_finding(**extra):
    return {"kind": "IMPLEMENTATION_LEAKAGE", "detail": LEAKAGE_DETAIL, **extra}


def test_implementation_leakage_is_pinned_as_a_self_finding():
    kind = FindingKind.IMPLEMENTATION_LEAKAGE
    assert kind in SELF_KINDS and kind not in CROSS_KINDS
    assert not kind.is_about_another_requirement


def test_process_persists_implementation_leakage_without_a_requirement_id():
    ws, _model, result = run_process([leakage_finding()])
    assert result.code is ProcessCode.REQUIREMENT_PROCESSED, result
    stored = parse_process_result(ws.content[process_results(ws)[0].secret])
    [finding] = stored.findings
    assert finding.kind is FindingKind.IMPLEMENTATION_LEAKAGE
    assert finding.requirement_id is None and finding.detail == LEAKAGE_DETAIL


def test_process_rejects_implementation_leakage_that_names_a_peer():
    ws, _model, result = run_process([leakage_finding(requirement_id=PEER_ID)])
    assert result.code is ProcessCode.INVALID_MODEL_OUTPUT
    assert "must not name another one" in " ".join(result.details)
    assert process_results(ws) == []


def test_review_ingests_and_verifies_a_process_leakage_finding():
    from review_fake import confirm, finding

    ws, requirement, _root, _ = build_review_workspace(
        others=[PEER],
        findings=[finding(FindingKind.IMPLEMENTATION_LEAKAGE, LEAKAGE_DETAIL)],
    )
    model = FakeModelRuntime([review_output(finding_verifications=[confirm(0)])])
    result = review_standard_requirement(ws, model, requirement.id)
    assert result.code is ReviewCode.REQUIREMENT_REVIEWED, result
    assert "IMPLEMENTATION_LEAKAGE" in model.calls[0]["context"]
