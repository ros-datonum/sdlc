"""The shared normative-tree reader, manifest v1 and the 0.2 result formats.

Spec: docs/specs/Requirement-Normative-Tree-Binding-v0.1.md.
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from processor_fake import reserialize_like_fibery
from review_fake import (
    build_review_workspace,
    review_output,
    stored_review,
    tree_bound_process_result,
    tree_manifest,
)
from sdlc.fibery_workspace import FiberyError
from sdlc.normative_tree import (
    NORMATIVE_TREE_MAX_DEPTH,
    NORMATIVE_TREE_MAX_DOCUMENTS,
    NORMATIVE_TREE_MAX_TEXT_CHARS,
    InvalidTreeManifest,
    NormativeTreeError,
    TreeEntry,
    TreeManifest,
    classify_artifact_name,
    describe_drift,
    document_fingerprint,
    read_normative_tree,
    render_descendants,
    render_normative_tree,
)
from sdlc.process_result import (
    InvalidProcessResult,
    parse_process_result,
    render_process_result,
)
from sdlc.review_result import (
    InvalidReviewResult,
    parse_review_result,
    render_review_result,
)
from sdlc.standard_analysis import (
    AnalysisResult,
    NormalizedRequirement,
    parse_analysis_output,
)
from standard_fake import REQUIREMENT_ID, build_standard_workspace, normalized
from test_review_result import root_only_manifest
from tree_fake import add_child, chain, edit, remove_node, replace_node


def read(ws, requirement, root):
    return read_normative_tree(ws, requirement, root)


def analysis(**changes):
    return AnalysisResult(
        normalized=NormalizedRequirement(**normalized(**changes)),
        analysis={},
        findings=(),
        proposed_relations=(),
    )


# -- traversal ---------------------------------------------------------------


def test_a_root_alone_is_a_one_document_tree():
    ws, requirement, root = build_standard_workspace()
    tree = read(ws, requirement, root)
    assert tree.root.node == root and tree.root.depth == 0
    assert tree.descendants == () and tree.artifacts == ()
    assert tree.manifest.document_ids == {root.id}
    assert tree.manifest.root_entry.content_fingerprint == document_fingerprint(
        tree.root.body
    )


def test_descendants_are_read_breadth_first_with_siblings_by_id():
    ws, requirement, root = build_standard_workspace()
    b = add_child(ws, root, "B", "b\n", document_id="child-b")
    a = add_child(ws, root, "A", "a\n", document_id="child-a")
    deep = add_child(ws, b, "Deep", "deep\n", document_id="child-b-1")
    tree = read(ws, requirement, root)
    assert [d.node.id for d in tree.descendants] == [a.id, b.id, deep.id]
    assert [d.depth for d in tree.descendants] == [1, 1, 2]
    assert [d.parent_document_id for d in tree.descendants] == [root.id, root.id, b.id]


def test_rendering_carries_an_identity_marker_per_document():
    ws, requirement, root = build_standard_workspace()
    child = add_child(ws, root, "Child", "Child body.\n", document_id="c1")
    grandchild = add_child(ws, child, "Grand", "Grand body.\n", document_id="c1-1")
    tree = read(ws, requirement, root)
    text = render_normative_tree(tree)
    assert (
        f"<!-- document: {root.name} | id: {root.id} | parent: root | depth: 0 -->"
        in text
    )
    assert (
        f"<!-- document: Child | id: {child.id} | parent: {root.id} | depth: 1 -->"
        in text
    )
    assert (
        f"<!-- document: Grand | id: {grandchild.id} | parent: {child.id} | depth: 2 -->"
        in text
    )
    assert "Child body." in text and "Grand body." in text
    descendants = render_descendants(tree)
    assert root.name not in descendants and "Child body." in descendants


# -- artifact exclusion is by contract, never by suffix ------------------------


@pytest.mark.parametrize(
    "name, expected",
    [
        ("SDLC-FR-0031 — Process Result 0001", ("SDLC-FR-0031", "Process Result")),
        ("SDLC-FR-0031 — Review Result 0012", ("SDLC-FR-0031", "Review Result")),
        ("SDLC-RAW-0007 — Processing Result", ("SDLC-RAW-0007", "Processing Result")),
        ("SDLC-FR-0031 — Process Result", None),
        ("SDLC-FR-0031 — Process Result 1", None),
        ("Process Result 0001", None),
        ("SDLC-FR-0031 — Notes on the Process Result 0001", None),
        ("SDLC-FR-0031 — Processing Result 0001", None),
    ],
)
def test_artifact_names_are_classified_exactly(name, expected):
    assert classify_artifact_name(name) == expected


def test_own_artifacts_directly_under_the_root_are_excluded_from_the_tree():
    ws, requirement, root = build_standard_workspace()
    process = add_child(ws, root, f"{REQUIREMENT_ID} — Process Result 0001", "x")
    review = add_child(ws, root, f"{REQUIREMENT_ID} — Review Result 0001", "x")
    content = add_child(ws, root, "Design notes", "Normative detail.\n")
    tree = read(ws, requirement, root)
    assert {a.id for a in tree.artifacts} == {process.id, review.id}
    assert tree.manifest.document_ids == {root.id, content.id}
    assert "Normative detail." in render_normative_tree(tree)
    assert "Process Result" not in render_descendants(tree)


def test_a_foreign_artifact_name_under_the_root_is_refused():
    ws, requirement, root = build_standard_workspace()
    add_child(ws, root, "SDLC-FR-0099 — Process Result 0003", "x", document_id="f")
    with pytest.raises(NormativeTreeError, match="SDLC-FR-0099") as raised:
        read(ws, requirement, root)
    assert raised.value.details == ("f",) and not raised.value.read_failed


def test_a_raw_processing_result_name_under_a_standard_root_is_refused():
    ws, requirement, root = build_standard_workspace()
    add_child(ws, root, "SDLC-RAW-0007 — Processing Result", "x")
    with pytest.raises(NormativeTreeError, match="Processing Result"):
        read(ws, requirement, root)


def test_an_own_artifact_nested_below_a_child_is_refused():
    ws, requirement, root = build_standard_workspace()
    child = add_child(ws, root, "Child", "c\n")
    add_child(ws, child, f"{REQUIREMENT_ID} — Process Result 0002", "x")
    with pytest.raises(NormativeTreeError, match="instead of directly under the Root"):
        read(ws, requirement, root)


def test_a_document_beneath_an_artifact_is_refused():
    ws, requirement, root = build_standard_workspace()
    artifact = add_child(ws, root, f"{REQUIREMENT_ID} — Review Result 0001", "x")
    add_child(ws, artifact, "Hidden", "Nothing should live here.\n", document_id="h")
    with pytest.raises(
        NormativeTreeError, match="beneath a control artifact"
    ) as raised:
        read(ws, requirement, root)
    assert raised.value.details == ("h",)


# -- ambiguity and unreadable nodes refuse ------------------------------------


def test_a_document_listed_twice_is_refused():
    ws, requirement, root = build_standard_workspace()
    a = add_child(ws, root, "A", "a\n", document_id="dup")
    b = add_child(ws, root, "B", "b\n", document_id="b")
    add_child(ws, b, "A again", "a\n", document_id=a.id, secret="other")
    with pytest.raises(NormativeTreeError, match="listed more than once"):
        read(ws, requirement, root)


def test_a_cycle_back_to_the_root_is_refused():
    ws, requirement, root = build_standard_workspace()
    child = add_child(ws, root, "Child", "c\n", document_id="c")
    add_child(ws, child, root.name, "loop", document_id=root.id, secret="loop")
    with pytest.raises(NormativeTreeError, match="listed more than once"):
        read(ws, requirement, root)


def test_an_unreadable_child_is_a_read_failure_never_a_partial_tree():
    ws, requirement, root = build_standard_workspace()
    child = add_child(ws, root, "Child", "c\n", document_id="c")
    ws.failures["read_document_content"] = FiberyError("timeout")
    with pytest.raises(NormativeTreeError) as raised:
        read(ws, requirement, root)
    assert raised.value.read_failed
    assert "timeout" not in raised.value.message
    assert child.id in raised.value.details or root.id in raised.value.details


def test_a_child_without_a_secret_is_refused():
    ws, requirement, root = build_standard_workspace()
    node = add_child(ws, root, "Child", "c\n", document_id="c")
    replace_node(ws, node, secret=None)
    with pytest.raises(NormativeTreeError, match="exposes no content secret"):
        read(ws, requirement, root)


# -- limits refuse at the boundary; nothing is truncated ----------------------


def test_depth_sixteen_is_admitted_and_seventeen_is_refused():
    ws, requirement, root = build_standard_workspace()
    nodes = chain(ws, root, NORMATIVE_TREE_MAX_DEPTH)
    assert read(ws, requirement, root).descendants[-1].depth == NORMATIVE_TREE_MAX_DEPTH
    add_child(ws, nodes[-1], "too-deep", "x", document_id="too-deep")
    with pytest.raises(NormativeTreeError, match="deeper than 16 levels") as raised:
        read(ws, requirement, root)
    assert raised.value.details == ("too-deep",)


def test_one_hundred_documents_are_admitted_and_one_more_is_refused():
    ws, requirement, root = build_standard_workspace()
    for number in range(NORMATIVE_TREE_MAX_DOCUMENTS - 1):
        add_child(ws, root, f"n{number:03d}", "x", document_id=f"n{number:03d}")
    assert (
        len(read(ws, requirement, root).manifest.entries)
        == NORMATIVE_TREE_MAX_DOCUMENTS
    )
    add_child(ws, root, "one-more", "x", document_id="zzz")
    with pytest.raises(NormativeTreeError, match="more than 100 Documents"):
        read(ws, requirement, root)


def test_text_is_bounded_in_code_points_over_names_and_bodies():
    ws, requirement, root = build_standard_workspace()
    ws.reserializes = False
    used = len(root.name) + len(ws.content[root.secret])
    child = add_child(ws, root, "é", "", document_id="c")
    room = NORMATIVE_TREE_MAX_TEXT_CHARS - used - len(child.name)
    edit(ws, child, "é" * room)
    assert len(read(ws, requirement, root).descendants[0].body) == room
    edit(ws, child, "é" * (room + 1))
    with pytest.raises(NormativeTreeError, match="exceeds 400000 characters") as raised:
        read(ws, requirement, root)
    assert "é" * 10 not in raised.value.message and raised.value.details == ()


# -- manifest identity ------------------------------------------------------


def test_the_manifest_is_canonical_regardless_of_listing_order():
    ws, requirement, root = build_standard_workspace()
    add_child(ws, root, "B", "b\n", document_id="b")
    add_child(ws, root, "A", "a\n", document_id="a")
    first = read(ws, requirement, root).manifest
    ws.documents.reverse()
    second = read(ws, requirement, root).manifest
    assert first == second and first.fingerprint == second.fingerprint
    assert [e.document_id for e in first.entries] == sorted(
        e.document_id for e in first.entries
    )


def test_the_fingerprint_is_sha256_of_the_canonical_json_without_itself():
    import hashlib

    ws, requirement, root = build_standard_workspace()
    add_child(ws, root, "A", "a\n", document_id="a")
    manifest = read(ws, requirement, root).manifest
    payload = manifest.to_payload()
    digest = payload.pop("normative_tree_fingerprint")
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    assert digest == hashlib.sha256(canonical).hexdigest() == manifest.fingerprint
    assert set(payload) == {
        "normative_tree_version",
        "requirement_id",
        "root_document_id",
        "documents",
    }
    assert set(payload["documents"][0]) == {
        "document_id",
        "parent_document_id",
        "name",
        "content_fingerprint",
    }


@pytest.mark.parametrize(
    "change",
    ["content", "name", "parent", "add", "remove"],
)
def test_every_normative_change_moves_the_fingerprint(change):
    ws, requirement, root = build_standard_workspace()
    a = add_child(ws, root, "A", "a\n", document_id="a")
    b = add_child(ws, root, "B", "b\n", document_id="b")
    before = read(ws, requirement, root).manifest
    if change == "content":
        edit(ws, a, "a changed\n")
    elif change == "name":
        replace_node(ws, a, name="A renamed")
    elif change == "parent":
        replace_node(ws, a, parent_document_id=b.id)
    elif change == "add":
        add_child(ws, b, "C", "c\n", document_id="c")
    else:
        remove_node(ws, a)
    after = read(ws, requirement, root).manifest
    assert after.fingerprint != before.fingerprint
    assert describe_drift(before, after) != ()


def test_folder_secret_and_serialization_are_not_identity():
    ws, requirement, root = build_standard_workspace()
    a = add_child(ws, root, "A", "a\n", document_id="a")
    before = read(ws, requirement, root).manifest
    ws.relocate_legacy_folder(root.id, "f-approved")
    replace_node(ws, a, secret="rotated")
    ws.content["rotated"] = "a\n"
    assert read(ws, requirement, root).manifest.fingerprint == before.fingerprint
    ws.content["rotated"] = "a  \n\n"  # Fibery re-serializes; canonical form equal
    assert read(ws, requirement, root).manifest.fingerprint == before.fingerprint


def test_drift_is_described_by_identity_never_by_content():
    ws, requirement, root = build_standard_workspace()
    a = add_child(ws, root, "A", "a\n", document_id="a")
    b = add_child(ws, root, "B", "b\n", document_id="b")
    before = read(ws, requirement, root).manifest
    edit(ws, a, "SECRET-BODY-9f1\n")
    replace_node(ws, b, name="B renamed", parent_document_id=a.id)
    add_child(ws, root, "C", "c\n", document_id="c")
    after = read(ws, requirement, root).manifest
    drift = describe_drift(before, after)
    assert "Document 'A' (a) content changed" in drift
    assert "Document 'B renamed' (b) was re-parented" in drift
    assert "Document b was renamed from 'B' to 'B renamed'" in drift
    assert "Document 'C' (c) was added" in drift
    assert not any("SECRET-BODY" in line for line in drift)
    assert describe_drift(before, before) == ()


def test_with_root_fingerprint_changes_only_the_root_entry():
    ws, requirement, root = build_standard_workspace()
    add_child(ws, root, "A", "a\n", document_id="a")
    manifest = read(ws, requirement, root).manifest
    moved = manifest.with_root_fingerprint("other")
    assert moved.root_entry.content_fingerprint == "other"
    assert [e for e in moved.entries if e.document_id != root.id] == [
        e for e in manifest.entries if e.document_id != root.id
    ]
    assert moved.fingerprint != manifest.fingerprint


def test_a_manifest_round_trips_through_its_payload():
    ws, requirement, root = build_standard_workspace()
    add_child(ws, root, "A", "a\n", document_id="a")
    manifest = read(ws, requirement, root).manifest
    assert TreeManifest.from_payload(json.loads(json.dumps(manifest.to_payload()))) == (
        manifest
    )


def _payload(**changes):
    manifest = TreeManifest(
        requirement_id=REQUIREMENT_ID,
        root_document_id="r",
        entries=(
            TreeEntry("r", None, "Root", "fp-r"),
            TreeEntry("c", "r", "Child", "fp-c"),
        ),
    )
    payload = manifest.to_payload()
    payload.update(changes)
    return payload


@pytest.mark.parametrize(
    "broken",
    [
        {"normative_tree_fingerprint": "0" * 64},
        {"normative_tree_version": 3},
        {"normative_tree_version": "1"},
        {"requirement_id": ""},
        {"root_document_id": "c"},
        {"documents": []},
        {
            "documents": [
                {
                    "document_id": "r",
                    "parent_document_id": None,
                    "name": "R",
                    "content_fingerprint": "x",
                }
            ]
            * 2
        },
        {
            "documents": [
                {
                    "document_id": "r",
                    "parent_document_id": "ghost",
                    "name": "R",
                    "content_fingerprint": "x",
                }
            ]
        },
        {
            "documents": [
                {
                    "document_id": "r",
                    "parent_document_id": None,
                    "name": "R",
                    "content_fingerprint": "",
                }
            ]
        },
        {
            "documents": [
                {
                    "document_id": "r",
                    "parent_document_id": None,
                    "name": 3,
                    "content_fingerprint": "x",
                }
            ]
        },
        {
            "documents": [
                {
                    "document_id": "r",
                    "parent_document_id": None,
                    "name": "R",
                    "content_fingerprint": "x",
                },
                {
                    "document_id": "c",
                    "parent_document_id": "d",
                    "name": "C",
                    "content_fingerprint": "x",
                },
                {
                    "document_id": "d",
                    "parent_document_id": "c",
                    "name": "D",
                    "content_fingerprint": "x",
                },
            ]
        },
        {
            "documents": [
                {
                    "document_id": "r",
                    "parent_document_id": None,
                    "name": "R",
                    "content_fingerprint": "x",
                },
                {
                    "document_id": "c",
                    "parent_document_id": None,
                    "name": "C",
                    "content_fingerprint": "x",
                },
            ]
        },
    ],
    ids=[
        "digest",
        "version",
        "version-type",
        "owner",
        "root-not-a-root",
        "no-documents",
        "duplicate-id",
        "unknown-parent",
        "empty-fingerprint",
        "name-type",
        "cycle",
        "two-roots",
    ],
)
def test_a_malformed_manifest_payload_is_rejected(broken):
    payload = _payload(**broken)
    if "normative_tree_fingerprint" not in broken:
        # Re-sign so the structural rule, not the digest, is what fails.
        payload["normative_tree_fingerprint"] = _sign(payload)
    with pytest.raises(InvalidTreeManifest):
        TreeManifest.from_payload(payload)


def _sign(payload):
    import hashlib

    unsigned = {k: v for k, v in payload.items() if k != "normative_tree_fingerprint"}
    canonical = json.dumps(
        unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@pytest.mark.parametrize("value", [None, [], "text", 7])
def test_a_non_object_manifest_is_rejected(value):
    with pytest.raises(InvalidTreeManifest):
        TreeManifest.from_payload(value)


# -- Process Result 0.2 --------------------------------------------------------


def _process_payload(text):
    return json.loads(text.split("```json\n")[1].split("\n```")[0])


def _with_payload(text, payload):
    start = text.index("```json\n") + len("```json\n")
    end = text.index("\n```", start)
    return text[:start] + json.dumps(payload, indent=2) + text[end:]


def _tree_bound(ws, root, **changes):
    return tree_bound_process_result(
        ws, root, iteration=1, analysis=analysis(**changes)
    )


def test_a_process_result_binds_its_input_and_intended_output_trees():
    ws, _, root = build_standard_workspace()
    add_child(ws, root, "A", "a\n", document_id="a")
    current = tree_manifest(ws, root)
    result = _tree_bound(ws, root)
    assert result.version == "0.3" and result.is_tree_bound and result.is_current
    assert result.input_tree == current.with_root_fingerprint("input-1")
    assert result.output_tree == current.with_root_fingerprint(
        result.output_fingerprint
    )
    payload = _process_payload(render_process_result(result))
    assert payload["process_result_version"] == "0.3"
    assert payload["normative_input_tree"]["normative_tree_version"] == 2
    assert payload["normative_input_tree"]["documents"][0]["document_id"] == "a"
    assert parse_process_result(render_process_result(result)) == result


def test_a_schema_rendered_product_level_root_binds_as_a_valid_tree():
    """The Document Schema's abstraction amendment left rendering unchanged:
    a valid document is read, fingerprinted and bound exactly as before."""
    product_level = parse_analysis_output(
        json.dumps(
            {
                "normalized_requirement": {
                    "title": "Bound provider execution time",
                    "requirement": (
                        "Provider execution must stop within the configured "
                        "execution time limit and report the timeout outcome "
                        "to the caller."
                    ),
                    "acceptance_verification": (
                        "An execution that exceeds the configured limit ends, "
                        "and its caller observes a timeout outcome."
                    ),
                }
            }
        )
    )
    document = product_level.normalized.document(REQUIREMENT_ID)
    ws, requirement, root = build_standard_workspace()
    ws.content[root.secret] = reserialize_like_fibery(document)

    tree = read(ws, requirement, root)
    result = tree_bound_process_result(ws, root, iteration=1, analysis=product_level)

    assert tree.manifest.root_entry.content_fingerprint == document_fingerprint(
        document
    )
    assert TreeManifest.from_payload(tree.manifest.to_payload()) == tree.manifest
    assert result.output_tree == tree.manifest
    assert parse_process_result(render_process_result(result)) == result


def test_a_process_result_cannot_be_built_over_a_tree_that_disagrees_with_its_input():
    ws, _, root = build_standard_workspace()
    manifest = tree_manifest(ws, root)
    from sdlc.process_result import build_process_result

    with pytest.raises(InvalidProcessResult, match="disagrees with input_fingerprint"):
        build_process_result(
            requirement_id=REQUIREMENT_ID,
            iteration=1,
            input_fingerprint="input-1",
            analysis=analysis(),
            input_tree=manifest.with_root_fingerprint("something-else"),
        )


def test_a_legacy_process_result_parses_as_root_only_and_is_never_synthesized():
    ws, _, root = build_standard_workspace()
    result = _tree_bound(ws, root)
    legacy = replace(result, version="0.1", input_tree=None, output_tree=None)
    text = render_process_result(legacy)
    assert "normative_input_tree" not in text
    parsed = parse_process_result(text)
    assert parsed.version == "0.1" and not parsed.is_tree_bound
    assert parsed.input_tree is None and parsed.output_tree is None
    assert parsed.output_fingerprint == result.output_fingerprint


def test_a_legacy_process_result_carrying_tree_keys_is_invalid():
    ws, _, root = build_standard_workspace()
    result = _tree_bound(ws, root)
    text = render_process_result(result)
    payload = _process_payload(text)
    payload["process_result_version"] = "0.1"
    with pytest.raises(InvalidProcessResult, match="0.1 Process Result cannot carry"):
        parse_process_result(_with_payload(text, payload))


@pytest.mark.parametrize("missing", ["normative_input_tree", "normative_output_tree"])
def test_a_0_2_process_result_without_both_trees_is_invalid(missing):
    ws, _, root = build_standard_workspace()
    text = render_process_result(_tree_bound(ws, root))
    payload = _process_payload(text)
    del payload[missing]
    with pytest.raises(InvalidProcessResult, match="Invalid normative tree binding"):
        parse_process_result(_with_payload(text, payload))


def test_process_tree_bindings_must_agree_with_the_retained_fingerprints():
    ws, _, root = build_standard_workspace()
    text = render_process_result(_tree_bound(ws, root))
    payload = _process_payload(text)
    payload["input_fingerprint"] = "moved"
    with pytest.raises(InvalidProcessResult, match="disagrees with input_fingerprint"):
        parse_process_result(_with_payload(text, payload))
    payload = _process_payload(text)
    payload["output_fingerprint"] = "moved"
    with pytest.raises(InvalidProcessResult, match="disagrees with output_fingerprint"):
        parse_process_result(_with_payload(text, payload))


def test_a_process_output_tree_may_change_only_the_root_content():
    ws, _, root = build_standard_workspace()
    add_child(ws, root, "A", "a\n", document_id="a")
    result = _tree_bound(ws, root)
    text = render_process_result(result)
    payload = _process_payload(text)
    altered = TreeManifest.from_payload(payload["normative_output_tree"])
    altered = replace(
        altered,
        entries=tuple(
            replace(e, content_fingerprint="rewritten") if e.document_id == "a" else e
            for e in altered.entries
        ),
    )
    payload["normative_output_tree"] = altered.to_payload()
    with pytest.raises(InvalidProcessResult, match="changes more than the Root"):
        parse_process_result(_with_payload(text, payload))


def test_process_tree_bindings_of_another_requirement_are_invalid():
    ws, _, root = build_standard_workspace()
    text = render_process_result(_tree_bound(ws, root))
    payload = _process_payload(text)
    foreign = replace(
        TreeManifest.from_payload(payload["normative_input_tree"]),
        requirement_id="SDLC-FR-0099",
    )
    payload["normative_input_tree"] = foreign.to_payload()
    with pytest.raises(InvalidProcessResult, match="belongs to 'SDLC-FR-0099'"):
        parse_process_result(_with_payload(text, payload))


# -- Review Result 0.2 ---------------------------------------------------------


def test_a_review_result_binds_the_reviewed_tree():
    ws, requirement, root, _ = build_review_workspace()
    from processor_fake import FakeModelRuntime
    from sdlc.standard_reviewer import review_standard_requirement

    review_standard_requirement(ws, FakeModelRuntime([review_output()]), requirement.id)
    review = stored_review(ws)
    assert review.version == "0.3" and review.is_tree_bound and review.is_current
    assert review.reviewed_tree == tree_manifest(ws, root)
    assert review.reviews_tree(tree_manifest(ws, root).fingerprint)
    payload = _process_payload(render_review_result(review))
    assert payload["reviewed_normative_tree"]["root_document_id"] == root.id


def test_a_review_result_cannot_bind_a_tree_whose_root_disagrees():
    from sdlc.review_result import build_review_result
    from sdlc.standard_review import parse_review_output

    with pytest.raises(InvalidReviewResult, match="Root fingerprint disagrees"):
        build_review_result(
            requirement_id=REQUIREMENT_ID,
            iteration=1,
            reviewed_document_fingerprint="doc-fp",
            reviewed_process_iteration=1,
            reviewed_process_output_fingerprint="out-fp",
            review=parse_review_output(review_output(), (), ()),
            reviewed_tree=root_only_manifest("other-fp"),
        )


def test_a_legacy_review_result_parses_as_root_only():
    ws, requirement, root, _ = build_review_workspace()
    from processor_fake import FakeModelRuntime
    from sdlc.standard_reviewer import review_standard_requirement

    review_standard_requirement(ws, FakeModelRuntime([review_output()]), requirement.id)
    review = stored_review(ws)
    text = render_review_result(replace(review, version="0.1", reviewed_tree=None))
    assert "reviewed_normative_tree" not in text
    parsed = parse_review_result(text)
    assert parsed.version == "0.1" and not parsed.is_tree_bound
    assert not parsed.reviews_tree(tree_manifest(ws, root).fingerprint)

    payload = _process_payload(render_review_result(review))
    payload["review_result_version"] = "0.1"
    with pytest.raises(InvalidReviewResult, match="0.1 Review Result cannot carry"):
        parse_review_result(_with_payload(render_review_result(review), payload))


def test_a_0_2_review_result_needs_a_coherent_tree():
    ws, requirement, _, _ = build_review_workspace()
    from processor_fake import FakeModelRuntime
    from sdlc.standard_reviewer import review_standard_requirement

    review_standard_requirement(ws, FakeModelRuntime([review_output()]), requirement.id)
    text = render_review_result(stored_review(ws))
    payload = _process_payload(text)
    del payload["reviewed_normative_tree"]
    with pytest.raises(InvalidReviewResult, match="Invalid normative tree binding"):
        parse_review_result(_with_payload(text, payload))
    payload = _process_payload(text)
    payload["reviewed_document_fingerprint"] = "moved"
    with pytest.raises(InvalidReviewResult, match="Root entry disagrees"):
        parse_review_result(_with_payload(text, payload))
    payload = _process_payload(text)
    payload["reviewed_normative_tree"]["requirement_id"] = "SDLC-FR-0099"
    with pytest.raises(InvalidReviewResult):
        parse_review_result(_with_payload(text, payload))
