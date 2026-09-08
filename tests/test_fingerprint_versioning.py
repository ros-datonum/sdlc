"""Audit A8: exact canonical-document hashing with explicit persisted versions.

Current evidence (Process/Review 0.3, manifest v2) fingerprints every
Document as SHA-256 over the exact UTF-8 bytes of canonical_markdown. Older
evidence (0.1 Root-only; 0.2 with manifest v1 under the second-normalizing
algorithm) stays readable history under its own semantics and is never
replayed, certified, applied or rewritten.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import replace

import pytest

from legacy_evidence import (
    LEGACY_CHILD_BODY,
    LEGACY_PROCESS_RESULT_0_2,
    LEGACY_REVIEW_RESULT_0_2,
    LEGACY_ROOT_INPUT_FINGERPRINT,
    LEGACY_SAMPLE_CONTENT,
    LEGACY_SAMPLE_FINGERPRINT,
)
from processor_fake import FakeModelRuntime, reserialize_like_fibery
from review_fake import review_output, stored_review, tree_manifest
from sdlc.normative_tree import (
    LEGACY_NORMATIVE_TREE_VERSION,
    NORMATIVE_TREE_VERSION,
    InvalidTreeManifest,
    TreeManifest,
    document_fingerprint,
    legacy_document_fingerprint,
    read_normative_tree,
)
from sdlc.process_result import (
    InvalidProcessResult,
    build_process_result,
    parse_process_result,
    render_process_result,
)
from sdlc.raw_source import canonical_markdown, content_equivalent, fingerprint_of
from sdlc.ready_decision import approve_standard_requirement
from sdlc.requirement_apply import apply_standard_requirement
from sdlc.results import ApplyResultCode, ReadyDecisionResultCode
from sdlc.results import StandardProcessResultCode as ProcessCode
from sdlc.results import StandardReviewResultCode as ReviewCode
from sdlc.review_result import (
    InvalidReviewResult,
    parse_review_result,
    render_review_result,
)
from sdlc.standard_analysis import AnalysisResult, NormalizedRequirement
from sdlc.standard_processor import process_standard_requirement
from sdlc.standard_reviewer import review_standard_requirement
from standard_fake import (
    REQUIREMENT_ID,
    analysis_output,
    build_standard_workspace,
    normalized,
    process_results,
    rendered_document,
    set_state,
)
from test_empty_result_recovery import PROCESS, REVIEW, leave_a_shell, model_for
from tree_fake import add_child, edit

NFC = unicodedata.normalize("NFC", "café")
NFD = unicodedata.normalize("NFD", "café")
FENCED_A = "# T\n\n```text\nline\n```\n"
FENCED_TRAILING_SPACE = "# T\n\n```text\nline   \n```\n"
FENCED_NFC = f"# T\n\n```text\n{NFC}\n```\n"
FENCED_NFD = f"# T\n\n```text\n{NFD}\n```\n"


def payload_of(text):
    return json.loads(text.split("```json\n")[1].split("\n```")[0])


def with_payload(text, payload):
    start = text.index("```json\n") + len("```json\n")
    end = text.index("\n```", start)
    return text[:start] + json.dumps(payload, indent=2) + text[end:]


# -- the current algorithm ------------------------------------------------------


def test_the_current_fingerprint_is_sha256_of_the_exact_canonical_bytes():
    content = "# T\n\n- a\n  wrapped\n\n```text\nline   \n  é\n```\n"
    expected = hashlib.sha256(canonical_markdown(content).encode("utf-8")).hexdigest()
    assert document_fingerprint(content) == expected
    assert document_fingerprint(content) != fingerprint_of(canonical_markdown(content))


def test_supported_prose_equivalence_still_fingerprints_equal():
    written = "Intro:\n- item,\n  wrapped\n\n```\n  literal\n```\n\nafter a\nwrap\n"
    stored = "Intro:\n\n* item,<br>wrapped\n\n```\n  literal\n```\n\nafter a<br>wrap"
    assert content_equivalent(stored, written)
    assert document_fingerprint(stored) == document_fingerprint(written)
    assert document_fingerprint("a\n") == document_fingerprint("a  \n\n")  # prose


@pytest.mark.parametrize(
    "a, b",
    [
        (FENCED_A, FENCED_TRAILING_SPACE),
        (FENCED_NFC, FENCED_NFD),
        ("# T\n\n```text\nline\n```\n", "# T\n\n```text\nline\n\n```\n"),
        ("# T\n\n```text\n  two\n```\n", "# T\n\n```text\n    four\n```\n"),
    ],
    ids=["trailing-space", "unicode-form", "blank-line", "indentation"],
)
def test_literal_fenced_differences_survive_the_current_hash(a, b):
    assert canonical_markdown(a) != canonical_markdown(b)
    assert not content_equivalent(a, b)
    assert document_fingerprint(a) != document_fingerprint(b)


@pytest.mark.parametrize(
    "a, b", [(FENCED_A, FENCED_TRAILING_SPACE), (FENCED_NFC, FENCED_NFD)]
)
def test_the_legacy_algorithm_collided_on_those_differences(a, b):
    """Pinned so the old semantics stay reproducible for history."""
    assert legacy_document_fingerprint(a) == legacy_document_fingerprint(b)


def test_the_canonical_output_is_not_normalized_a_second_time():
    canonical = canonical_markdown(FENCED_NFD)
    assert unicodedata.normalize("NFC", canonical) != canonical
    assert (
        document_fingerprint(FENCED_NFD)
        == hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    )


def test_the_reader_fingerprints_every_document_with_the_current_algorithm():
    ws, requirement, root = build_standard_workspace()
    ws.reserializes = False
    child = add_child(ws, root, "C", FENCED_TRAILING_SPACE, document_id="c")
    tree = read_normative_tree(ws, requirement, root)
    assert tree.manifest.version == NORMATIVE_TREE_VERSION and tree.manifest.is_current
    by_id = {e.document_id: e for e in tree.manifest.entries}
    assert by_id[child.id].content_fingerprint == document_fingerprint(
        FENCED_TRAILING_SPACE
    )
    assert by_id[root.id].content_fingerprint == document_fingerprint(
        ws.content[root.secret]
    )
    edit(ws, child, FENCED_A)
    assert (
        read_normative_tree(ws, requirement, root).manifest.fingerprint
        != tree.manifest.fingerprint
    )


# -- historical compatibility ----------------------------------------------------


def test_pinned_0_2_evidence_still_parses_under_its_own_semantics():
    process = parse_process_result(LEGACY_PROCESS_RESULT_0_2)
    review = parse_review_result(LEGACY_REVIEW_RESULT_0_2)
    assert process.version == "0.2" and process.is_tree_bound and not process.is_current
    assert process.input_tree.version == LEGACY_NORMATIVE_TREE_VERSION
    assert process.input_fingerprint == LEGACY_ROOT_INPUT_FINGERPRINT
    assert review.version == "0.2" and review.is_tree_bound and not review.is_current
    assert review.reviewed_tree.version == LEGACY_NORMATIVE_TREE_VERSION
    assert review.reviewed_tree == process.output_tree
    # Round trip preserves the old text exactly: history is never rewritten.
    assert render_process_result(process) == LEGACY_PROCESS_RESULT_0_2
    assert render_review_result(review) == LEGACY_REVIEW_RESULT_0_2


def test_pinned_legacy_digests_remain_identical():
    assert (
        legacy_document_fingerprint(LEGACY_SAMPLE_CONTENT) == LEGACY_SAMPLE_FINGERPRINT
    )
    assert document_fingerprint(LEGACY_SAMPLE_CONTENT) != LEGACY_SAMPLE_FINGERPRINT
    root_input = (
        "# SDLC-FR-0031 — Reject unauthenticated model execution\n\n"
        "## Requirement\n\nA draft statement.\n"
    )
    assert legacy_document_fingerprint(root_input) == LEGACY_ROOT_INPUT_FINGERPRINT
    child_entry = next(
        e
        for e in parse_process_result(LEGACY_PROCESS_RESULT_0_2).input_tree.entries
        if e.document_id == "c1"
    )
    assert child_entry.content_fingerprint == legacy_document_fingerprint(
        LEGACY_CHILD_BODY
    )


def test_a_legacy_manifest_digest_is_still_verified_not_recomputed_from_documents():
    payload = payload_of(LEGACY_PROCESS_RESULT_0_2)
    payload["normative_input_tree"]["documents"][0]["content_fingerprint"] = "x" * 64
    with pytest.raises(
        InvalidProcessResult, match="declared normative tree fingerprint"
    ):
        parse_process_result(with_payload(LEGACY_PROCESS_RESULT_0_2, payload))


@pytest.mark.parametrize(
    "result_version, manifest_version",
    [("0.3", 1), ("0.2", 2)],
    ids=["0.3-with-v1", "0.2-with-v2"],
)
def test_mixed_result_and_manifest_versions_are_rejected(
    result_version, manifest_version
):
    ws, _, root = build_standard_workspace()
    manifest = replace(tree_manifest(ws, root), version=manifest_version)
    if manifest_version == 1:
        # Build a genuine 0.3 body, then declare v1 manifests inside it.
        text = render_process_result(
            build_process_result(
                requirement_id=REQUIREMENT_ID,
                iteration=1,
                input_fingerprint=tree_manifest(
                    ws, root
                ).root_entry.content_fingerprint,
                analysis=AnalysisResult(
                    normalized=NormalizedRequirement(**normalized()),
                    analysis={},
                    findings=(),
                    proposed_relations=(),
                ),
                input_tree=tree_manifest(ws, root),
            )
        )
        payload = payload_of(text)
        for key in ("normative_input_tree", "normative_output_tree"):
            tree = replace(TreeManifest.from_payload(payload[key]), version=1)
            payload[key] = tree.to_payload()
    else:
        text = LEGACY_PROCESS_RESULT_0_2
        payload = payload_of(text)
        for key in ("normative_input_tree", "normative_output_tree"):
            tree = replace(TreeManifest.from_payload(payload[key]), version=2)
            payload[key] = tree.to_payload()
    payload["process_result_version"] = result_version
    with pytest.raises(InvalidProcessResult, match="mixes fingerprint algorithms"):
        parse_process_result(with_payload(text, payload))
    assert manifest.version == manifest_version  # the fixture was built as intended


def test_a_mixed_version_review_result_is_rejected():
    payload = payload_of(LEGACY_REVIEW_RESULT_0_2)
    payload["review_result_version"] = "0.3"
    with pytest.raises(InvalidReviewResult, match="mixes fingerprint algorithms"):
        parse_review_result(with_payload(LEGACY_REVIEW_RESULT_0_2, payload))


@pytest.mark.parametrize("version", [3, 0, "2", True])
def test_unknown_manifest_versions_are_rejected(version):
    ws, _, root = build_standard_workspace()
    payload = tree_manifest(ws, root).to_payload()
    payload["normative_tree_version"] = version
    with pytest.raises(InvalidTreeManifest, match="not supported"):
        TreeManifest.from_payload(payload)


def test_current_builders_refuse_a_legacy_manifest():
    ws, _, root = build_standard_workspace()
    legacy = replace(tree_manifest(ws, root), version=1)
    with pytest.raises(InvalidProcessResult, match="binds manifest version 2"):
        build_process_result(
            requirement_id=REQUIREMENT_ID,
            iteration=1,
            input_fingerprint=legacy.root_entry.content_fingerprint,
            analysis=AnalysisResult(
                normalized=NormalizedRequirement(**normalized()),
                analysis={},
                findings=(),
                proposed_relations=(),
            ),
            input_tree=legacy,
        )


# -- older evidence at the stages -------------------------------------------------


def legacy_0_2_fixture(state):
    """The pinned 0.2 history under the Root it was produced over."""
    ws, requirement, root = build_standard_workspace(state=state)
    add_child(ws, root, "Retry budget", LEGACY_CHILD_BODY, document_id="c1")
    ws.content[root.secret] = rendered_document()  # the old output, applied
    process = add_child(
        ws, root, f"{REQUIREMENT_ID} — Process Result 0001", LEGACY_PROCESS_RESULT_0_2
    )
    review = add_child(
        ws, root, f"{REQUIREMENT_ID} — Review Result 0001", LEGACY_REVIEW_RESULT_0_2
    )
    return ws, requirement, root, process, review


def test_process_upgrades_0_2_history_with_a_fresh_iteration_and_no_edit():
    ws, requirement, _root, process, review = legacy_0_2_fixture("Process")
    ws.documents.remove(review)
    old_body = ws.content[process.secret]
    model = FakeModelRuntime([analysis_output({"title": "Fresh"})])
    result = process_standard_requirement(ws, model, requirement.id)
    assert result.code is ProcessCode.REQUIREMENT_PROCESSED, result
    assert result.iteration == 2 and model.was_invoked
    assert "Older-format Process Result 1 (version 0.2)" in result.message
    assert ws.content[process.secret] == old_body
    stored = parse_process_result(
        reserialize_like_fibery(ws.content[process_results(ws)[-1].secret])
    )
    assert stored.version == "0.3" and stored.is_current
    assert stored.input_tree.version == NORMATIVE_TREE_VERSION


def test_process_never_matches_0_2_evidence_as_no_change_or_resume():
    """The applied old output matches the Root, but under a different algorithm."""
    ws, requirement, _root, process, review = legacy_0_2_fixture("Process")
    ws.documents.remove(review)
    for option in ("resume_result", "new_iteration_after"):
        before = len(ws.mutations)
        model = FakeModelRuntime([analysis_output()])
        refused = process_standard_requirement(
            ws, model, requirement.id, **{option: process.id}
        )
        assert refused.code is ProcessCode.NORMATIVE_TREE_EVIDENCE_REQUIRED, refused
        assert "older format (version 0.2)" in refused.message
        assert not model.was_invoked and ws.mutations[before:] == []


def test_review_refuses_0_2_process_evidence():
    ws, requirement, _root, _process, review = legacy_0_2_fixture("Review")
    ws.documents.remove(review)
    before = len(ws.mutations)
    model = FakeModelRuntime([review_output()])
    result = review_standard_requirement(ws, model, requirement.id)
    assert result.code is ReviewCode.NORMATIVE_TREE_EVIDENCE_REQUIRED, result
    assert "older format (version 0.2)" in result.message
    assert not model.was_invoked and ws.mutations[before:] == []


def test_review_over_current_process_and_0_2_review_history_is_a_fresh_review():
    ws, requirement, root, _process, review = legacy_0_2_fixture("Process")
    ws.documents.remove(review)
    assert (
        process_standard_requirement(
            ws, FakeModelRuntime([analysis_output()]), requirement.id
        ).code
        is ProcessCode.REQUIREMENT_PROCESSED
    )
    old_review = add_child(
        ws, root, f"{REQUIREMENT_ID} — Review Result 0001", LEGACY_REVIEW_RESULT_0_2
    )
    old_body = ws.content[old_review.secret]
    model = FakeModelRuntime([review_output()])
    result = review_standard_requirement(ws, model, requirement.id)
    assert result.code is ReviewCode.REQUIREMENT_REVIEWED, result
    assert result.iteration == 2 and model.was_invoked
    assert ws.content[old_review.secret] == old_body
    assert stored_review(ws).version == "0.3" and stored_review(ws).is_current


@pytest.mark.parametrize("entry", ["approve", "apply"])
def test_approval_and_application_refuse_0_2_evidence_before_any_mutation(entry):
    ws, requirement, _root, _process, _review = legacy_0_2_fixture(
        "Ready" if entry == "approve" else "Apply"
    )
    before = len(ws.mutations)
    if entry == "approve":
        result = approve_standard_requirement(ws, requirement.id)
        assert result.code is ReadyDecisionResultCode.NORMATIVE_TREE_EVIDENCE_REQUIRED
    else:
        result = apply_standard_requirement(ws, requirement.id)
        assert result.code is ApplyResultCode.NORMATIVE_TREE_EVIDENCE_REQUIRED
    assert "older-format evidence" in result.message and "version 0.2" in result.message
    assert ws.mutations[before:] == []
    assert ws.requirements[requirement.id].state == (
        "Ready" if entry == "approve" else "Apply"
    )


def test_state_only_idempotent_paths_ignore_old_history():
    ws, requirement, _root, _process, _review = legacy_0_2_fixture("Apply")
    assert approve_standard_requirement(ws, requirement.id).code is (
        ReadyDecisionResultCode.REQUIREMENT_ALREADY_APPROVED
    )
    set_state(ws, requirement, "Applied")
    snapshot = dict(ws.content)
    before = len(ws.mutations)
    assert apply_standard_requirement(ws, requirement.id).code is (
        ApplyResultCode.REQUIREMENT_ALREADY_APPLIED
    )
    assert ws.mutations[before:] == [] and dict(ws.content) == snapshot


# -- the current lifecycle detects literal differences ------------------------------


def current_chain():
    ws, requirement, root = build_standard_workspace()
    ws.reserializes = False
    child = add_child(
        ws, root, "Retry budget", "```text\nthree\n```\n", document_id="c1"
    )
    grandchild = add_child(
        ws, child, "Backoff", "```text\n" + NFC + "\n```\n", document_id="c1-1"
    )
    processed = process_standard_requirement(
        ws, FakeModelRuntime([analysis_output()]), requirement.id
    )
    assert processed.code is ProcessCode.REQUIREMENT_PROCESSED
    reviewed = review_standard_requirement(
        ws, FakeModelRuntime([review_output()]), requirement.id
    )
    assert reviewed.code is ReviewCode.REQUIREMENT_REVIEWED
    assert ws.requirements[requirement.id].state == "Ready"
    return ws, requirement, root, child, grandchild


def test_a_current_format_chain_reaches_applied_and_the_root_is_untouched():
    ws, requirement, root, _child, _grandchild = current_chain()
    assert stored_review(ws).is_current
    before = tree_manifest(ws, root)
    assert approve_standard_requirement(ws, requirement.id).code is (
        ReadyDecisionResultCode.REQUIREMENT_APPROVED
    )
    applied = apply_standard_requirement(ws, requirement.id)
    assert applied.code is ApplyResultCode.REQUIREMENT_APPLIED, applied
    stored = next(d for d in ws.documents if d.id == root.id)
    assert stored == root, "same Document, same legacy Folder, nothing moved"
    assert (
        read_normative_tree(ws, ws.requirements[requirement.id], stored).manifest
        == before
    )


def test_current_evidence_bound_to_a_legacy_folder_root_survives_a_folder_change():
    """AMR compatibility: 0.3/v2 evidence written against an old Root that
    carries `fibery/Folder` stays current when the Folder later changes or is
    cleared, because placement was never part of the evidence."""
    ws, requirement, root, _child, _grandchild = current_chain()
    assert root.folder_id == "f-draft"
    before = tree_manifest(ws, root)
    ws.relocate_legacy_folder(root.id, None)
    assert stored_review(ws).is_current
    assert tree_manifest(ws, root) == before
    assert approve_standard_requirement(ws, requirement.id).code is (
        ReadyDecisionResultCode.REQUIREMENT_APPROVED
    )
    assert apply_standard_requirement(ws, requirement.id).code is (
        ApplyResultCode.REQUIREMENT_APPLIED
    )


@pytest.mark.parametrize(
    "target, content",
    [
        ("root", "trailing-space"),
        ("child", "trailing-space"),
        ("grandchild", "unicode-form"),
    ],
)
def test_a_literal_fenced_edit_after_review_is_stale_at_approve_and_apply(
    target, content
):
    ws, requirement, root, child, grandchild = current_chain()
    node = {"root": root, "child": child, "grandchild": grandchild}[target]
    original = ws.content[node.secret]
    if content == "trailing-space":
        edited = (
            original.replace("three\n", "three   \n").replace(
                "## Requirement\n", "## Requirement\n\n```text\nx   \n```\n"
            )
            if target == "root"
            else original.replace("three\n", "three   \n")
        )
    else:
        edited = original.replace(NFC, NFD)
    assert edited != original and canonical_markdown(edited) != canonical_markdown(
        original
    )
    assert (
        legacy_document_fingerprint(edited) == legacy_document_fingerprint(original)
        or target == "root"
    )
    ws.content[node.secret] = edited
    before = len(ws.mutations)
    result = approve_standard_requirement(ws, requirement.id)
    assert result.code is ReadyDecisionResultCode.REVIEW_RESULT_STALE, result
    assert ws.mutations[before:] == []
    set_state(ws, requirement, "Apply")
    applied = apply_standard_requirement(ws, requirement.id)
    assert applied.code is ApplyResultCode.REVIEW_RESULT_STALE, applied
    assert ws.mutations[before:] == []


def test_a_literal_fenced_child_edit_is_a_new_process_iteration():
    ws, requirement, _root, child, _grandchild = current_chain()
    set_state(ws, requirement, "Process")
    edit(ws, child, "```text\nthree   \n```\n")
    model = FakeModelRuntime([analysis_output({"title": "Again"})])
    result = process_standard_requirement(ws, model, requirement.id)
    assert result.code is ProcessCode.REQUIREMENT_PROCESSED and result.iteration == 2
    assert model.was_invoked


def test_a_literal_fenced_edit_during_review_is_stale():
    ws, requirement, root = build_standard_workspace()
    ws.reserializes = False
    child = add_child(ws, root, "C", "```text\nthree\n```\n", document_id="c1")
    assert (
        process_standard_requirement(
            ws, FakeModelRuntime([analysis_output()]), requirement.id
        ).code
        is ProcessCode.REQUIREMENT_PROCESSED
    )

    class EditsChild:
        def __init__(self):
            self.calls = []

        def run(self, prompt, context=""):
            from sdlc.model_runtime import ModelResponse

            self.calls.append(1)
            edit(ws, child, "```text\nthree \n```\n")
            return ModelResponse(text=review_output(), runtime="fake", model=None)

    result = review_standard_requirement(ws, EditsChild(), requirement.id)
    assert result.code is ReviewCode.REVIEW_RESULT_STALE, result
    assert ws.requirements[requirement.id].state == "Review"


# -- A3 recovery writes current-format evidence ------------------------------------


@pytest.mark.parametrize("stage", [PROCESS, REVIEW], ids=repr)
def test_recovery_fills_the_shell_with_current_format_evidence(stage):
    ws, record, _root, shell, _ = leave_a_shell(stage)
    ws.failures.clear()
    result = stage.run(ws, record, model_for(stage), recover=shell.id)
    assert result.code is stage.codes["ok"], result
    parsed = stage.parser(reserialize_like_fibery(ws.content[shell.secret]))
    assert parsed.version == "0.3" and parsed.is_current
    assert [d.id for d in ws.documents if d.id == shell.id] == [shell.id]


def test_review_shell_recovery_needs_current_process_evidence():
    ws, record, _root, shell, _ = leave_a_shell(REVIEW)
    ws.failures.clear()
    node = process_results(ws)[-1]
    legacy = parse_process_result(reserialize_like_fibery(ws.content[node.secret]))
    ws.content[node.secret] = render_process_result(
        replace(legacy, version="0.1", input_tree=None, output_tree=None)
    )
    before = len(ws.mutations)
    result = review_standard_requirement(
        ws, model_for(REVIEW), record.id, recover_empty_result=shell.id
    )
    assert result.code is ReviewCode.NORMATIVE_TREE_EVIDENCE_REQUIRED
    assert ws.mutations[before:] == [] and ws.content[shell.secret] == ""


# -- RAW transport identity is untouched -------------------------------------------


def test_raw_source_fingerprint_algorithm_is_unchanged():
    from raw_fixtures import VALID_SOURCE
    from sdlc.raw_source import normalize_for_fingerprint, parse_raw_requirement

    parsed = parse_raw_requirement(VALID_SOURCE)
    assert (
        parsed.fingerprint
        == hashlib.sha256(
            normalize_for_fingerprint(parsed.body).encode("utf-8")
        ).hexdigest()
    )
    assert (
        parsed.fingerprint
        == "2cecafa381611176273a6d4fbefbbdee71f35d583f411aa19247dc9d3ff33d4f"
    )
    assert fingerprint_of("a  \n") == fingerprint_of("a\n")
