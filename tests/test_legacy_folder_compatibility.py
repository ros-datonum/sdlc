"""Fixture A (no Folder) and fixture B (legacy Raw/Draft/Approved Folder) behave
identically under every lifecycle stage.

Documents created before the Type/State navigation model carry
`fibery/Folder`; Documents created after it carry none. Lifecycle placement is
the Requirement's Type and State, and the Folder is inert presentation
metadata: it is never read, checked, moved or stripped. Every test here runs
the same stage against both fixtures and requires the same outcome, the same
normative writes and the same evidence.
"""

from __future__ import annotations

import pytest

from apply_fake import build_apply_workspace, normative_writes, proposal
from processor_fake import (
    LEGACY_DRAFT_FOLDER,
    LEGACY_RAW_FOLDER,
    FakeModelRuntime,
    build_workspace,
    candidate,
    model_output,
)
from review_fake import build_review_workspace, review_output, tree_manifest
from sdlc.fibery_workspace import FiberyError
from sdlc.model_runtime import ModelResponse
from sdlc.raw_processor import process_raw_requirement
from sdlc.ready_decision import approve_standard_requirement
from sdlc.requirement_apply import apply_standard_requirement
from sdlc.results import ApplyResultCode
from sdlc.results import ProcessResultCode as RawCode
from sdlc.results import ReadyDecisionResultCode as ReadyCode
from sdlc.results import StandardProcessResultCode as ProcessCode
from sdlc.results import StandardReviewResultCode as ReviewCode
from sdlc.review_result import parse_review_result
from sdlc.standard_processor import process_standard_requirement
from sdlc.standard_reviewer import review_standard_requirement
from standard_fake import analysis_output, build_standard_workspace

FIXTURES = [
    pytest.param(False, id="A-no-folder"),
    pytest.param(True, id="B-legacy-folder"),
]
RAW_OUTPUT = model_output([candidate(title="One"), candidate(title="Two")])


def normative(ws, before):
    """Every mutation except the ids the fake allocates, in order."""
    return [m for m in ws.mutations[before:] if not m.startswith("relocate")]


# -- the fixtures really differ only in fibery/Folder -------------------------


@pytest.mark.parametrize("legacy", FIXTURES)
def test_the_raw_fixture_differs_only_in_the_root_folder(legacy):
    ws, _raw, root = build_workspace(legacy_folders=legacy)
    assert root.folder_id == (LEGACY_RAW_FOLDER if legacy else None)
    assert [d.folder_id for d in ws.documents if d.id != root.id] == []


@pytest.mark.parametrize("legacy", FIXTURES)
def test_the_standard_fixture_differs_only_in_the_root_folder(legacy):
    _ws, _std, root = build_standard_workspace(legacy_folders=legacy)
    assert root.folder_id == (LEGACY_DRAFT_FOLDER if legacy else None)


# -- RAW Process --------------------------------------------------------------


def raw_run(legacy):
    ws, raw, _ = build_workspace(legacy_folders=legacy)
    before = len(ws.mutations)
    result = process_raw_requirement(ws, FakeModelRuntime([RAW_OUTPUT]), raw.id)
    return ws, result, normative(ws, before)


def test_raw_process_creates_the_same_folderless_candidates_for_both_fixtures():
    ws_a, result_a, writes_a = raw_run(False)
    ws_b, result_b, writes_b = raw_run(True)
    assert result_a.code is result_b.code is RawCode.RAW_REQUIREMENT_PROCESSED
    assert result_a.candidates == result_b.candidates
    assert writes_a == writes_b
    for ws in (ws_a, ws_b):
        roots = [
            d
            for d in ws.documents
            if d.entity_public_id is not None
            and d.name.startswith("SDLC-")
            and not d.name.startswith("SDLC-RAW")
        ]
        assert len(roots) == 2
        assert all(d.folder_id is None for d in roots)


# -- A3: empty-result recovery ------------------------------------------------


@pytest.mark.parametrize("legacy", FIXTURES)
def test_raw_empty_result_recovery_works_for_both_fixtures(legacy):
    ws, raw, _ = build_workspace(legacy_folders=legacy)
    ws.failures["write_document_content"] = FiberyError("body write failed")
    failed = process_raw_requirement(ws, FakeModelRuntime([RAW_OUTPUT]), raw.id)
    assert failed.code is not RawCode.RAW_REQUIREMENT_PROCESSED
    [shell] = [d for d in ws.documents if d.name.endswith("Processing Result")]
    assert ws.content[shell.secret] == ""

    result = process_raw_requirement(
        ws, FakeModelRuntime([RAW_OUTPUT]), raw.id, recover_empty_result=shell.id
    )

    assert result.code is RawCode.RAW_REQUIREMENT_PROCESSED, result
    assert ws.content[shell.secret] != ""
    assert len([r for r in ws.requirements.values() if r.type_name == "Standard"]) == 2


@pytest.mark.parametrize("legacy", FIXTURES)
def test_standard_empty_result_recovery_works_for_both_fixtures(legacy):
    ws, std, root = build_standard_workspace(legacy_folders=legacy)
    ws.failures["write_document_content"] = FiberyError("body write failed")
    failed = process_standard_requirement(
        ws, FakeModelRuntime([analysis_output()]), std.id
    )
    assert failed.code is not ProcessCode.REQUIREMENT_PROCESSED
    [shell] = [d for d in ws.documents if "Process Result" in d.name]

    result = process_standard_requirement(
        ws, FakeModelRuntime([analysis_output()]), std.id, recover_empty_result=shell.id
    )

    assert result.code is ProcessCode.REQUIREMENT_PROCESSED, result
    assert ws.requirements[std.id].state == "Review"
    assert next(d for d in ws.documents if d.id == root.id).folder_id == root.folder_id


@pytest.mark.parametrize("legacy", FIXTURES)
def test_recovery_still_refuses_a_type_or_state_change(legacy):
    """Removing the folder check weakens nothing else: identity guards stay."""
    ws, std, _ = build_standard_workspace(legacy_folders=legacy)
    ws.failures["write_document_content"] = FiberyError("body write failed")
    process_standard_requirement(ws, FakeModelRuntime([analysis_output()]), std.id)
    [shell] = [d for d in ws.documents if "Process Result" in d.name]
    ws.set_requirement_state(std.id, "Ready")

    result = process_standard_requirement(
        ws, FakeModelRuntime([analysis_output()]), std.id, recover_empty_result=shell.id
    )

    assert result.code is ProcessCode.REQUIREMENT_NOT_IN_PROCESS
    assert ws.content[shell.secret] == ""


# -- Standard Process and Review ----------------------------------------------


def standard_run(legacy):
    ws, std, root = build_standard_workspace(legacy_folders=legacy)
    before = len(ws.mutations)
    result = process_standard_requirement(
        ws, FakeModelRuntime([analysis_output()]), std.id
    )
    return ws, std, root, result, normative(ws, before)


def test_standard_process_produces_identical_results_for_both_fixtures():
    ws_a, _, root_a, result_a, writes_a = standard_run(False)
    ws_b, _, root_b, result_b, writes_b = standard_run(True)
    assert result_a.code is result_b.code is ProcessCode.REQUIREMENT_PROCESSED
    assert writes_a == writes_b
    assert ws_a.content[root_a.secret] == ws_b.content[root_b.secret]
    [pr_a] = [d for d in ws_a.documents if "Process Result" in d.name]
    [pr_b] = [d for d in ws_b.documents if "Process Result" in d.name]
    assert ws_a.content[pr_a.secret] == ws_b.content[pr_b.secret]


class EditingModelRuntime:
    """Edits the Root while the model 'runs', as a concurrent human would."""

    def __init__(self, response, ws, root):
        self.response, self.ws, self.root = response, ws, root
        self.calls = []

    @property
    def was_invoked(self):
        return bool(self.calls)

    def run(self, prompt, context=""):
        self.calls.append(prompt)
        self.ws.content[self.root.secret] += "\nEdited by hand.\n"
        return ModelResponse(text=self.response, runtime="fake", model=None)


@pytest.mark.parametrize("legacy", FIXTURES)
def test_content_drift_is_still_detected_for_both_fixtures(legacy):
    ws, std, root = build_standard_workspace(legacy_folders=legacy)
    result = process_standard_requirement(
        ws, EditingModelRuntime(analysis_output(), ws, root), std.id
    )
    assert result.code is ProcessCode.PROCESSING_STATE_CONFLICT


def test_review_evidence_is_identical_for_both_fixtures():
    manifests = {}
    for legacy in (False, True):
        ws, requirement, root, _ = build_review_workspace(legacy_folders=legacy)
        result = review_standard_requirement(
            ws, FakeModelRuntime([review_output()]), requirement.id
        )
        assert result.code is ReviewCode.REQUIREMENT_REVIEWED
        [review] = [d for d in ws.documents if "Review Result" in d.name]
        parsed = parse_review_result(ws.content[review.secret])
        manifests[legacy] = (
            tree_manifest(ws, root),
            parsed.reviewed_document_fingerprint,
            parsed.reviewed_tree.fingerprint,
        )
    assert manifests[False] == manifests[True]


# -- A5 / A8: the manifest ignores the Folder ---------------------------------


def test_tree_manifest_and_fingerprint_do_not_depend_on_the_folder():
    _, _, root_a, _ = build_review_workspace(legacy_folders=False)
    _, _, root_b, _ = build_review_workspace(legacy_folders=True)
    ws_a, _, _, _ = build_review_workspace(legacy_folders=False)
    ws_b, _, _, _ = build_review_workspace(legacy_folders=True)
    assert root_a.folder_id is None and root_b.folder_id == LEGACY_DRAFT_FOLDER
    assert tree_manifest(ws_a, root_a) == tree_manifest(ws_b, root_b)


# -- Ready and Apply ----------------------------------------------------------


def test_ready_and_apply_are_identical_for_both_fixtures():
    outcomes = {}
    for legacy in (False, True):
        ws, requirement, root, _ = build_apply_workspace(
            proposals=(proposal(),), legacy_folders=legacy
        )
        before = len(ws.mutations)
        result = apply_standard_requirement(ws, requirement.id)
        assert result.code is ApplyResultCode.REQUIREMENT_APPLIED
        stored = next(d for d in ws.documents if d.id == root.id)
        assert stored == root, "the Root is never written or moved"
        outcomes[legacy] = (result.created, normative_writes(ws, before))
    assert outcomes[False] == outcomes[True]


@pytest.mark.parametrize("legacy", FIXTURES)
def test_ready_decision_is_state_based_for_both_fixtures(legacy):
    ws, requirement, _, _ = build_review_workspace(legacy_folders=legacy)
    review_standard_requirement(ws, FakeModelRuntime([review_output()]), requirement.id)
    assert ws.requirements[requirement.id].state == "Ready"
    assert approve_standard_requirement(ws, requirement.id).code is (
        ReadyCode.REQUIREMENT_APPROVED
    )
    assert ws.requirements[requirement.id].state == "Apply"
