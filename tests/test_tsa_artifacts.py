"""I01 — canonical JSON, digests, envelope and the five closed TSA schemas.

Every expected digest below is transcribed literally from
`docs/specs/TSA-C01-Implementation-Spec-v0.1.md` sections 5.3, 5.5 and 13.7-2.
None is produced by the code under test.
"""

from __future__ import annotations

import copy
import hashlib
import json

import pytest

from sdlc.normative_tree import InvalidTreeManifest, TreeEntry, TreeManifest
from sdlc.tsa_artifacts import (
    ARCHITECTURE,
    ARCHITECTURE_APPLIED_KEYS,
    ARCHITECTURE_SECTION_KEYS,
    HUMAN_DECISION,
    INPUT_MANIFEST,
    PROCESS_RESULT,
    REVIEW_RESULT,
    EmptyTsaCarrier,
    InvalidTsaArtifact,
    _canonical_json,
    _digest,
    _reused_paths_for,
    artifact_digest,
    canonical_bytes,
    canonical_cycle_id,
    canonical_json,
    compute_artifact_digest,
    extract_architecture_envelope,
    extract_artifact_payload,
    manifest_digest,
    parse_reference,
    reference_allows_collection,
    require_canonical_cycle_id,
    requirement_input_digest,
    sealed_artifact,
    start_input_digest,
    start_input_projection,
    sub_digest,
    ux_evidence_digest,
    validate_artifact,
    validate_manifest_body,
    validate_reused_tree_manifest,
    validate_structural_lineage,
)

# --------------------------------------------------------------------------
# Literal expectations from the frozen specification
# --------------------------------------------------------------------------

SPEC_ARTIFACT_VECTORS = [
    (
        INPUT_MANIFEST,
        {},
        "5abac6256c44bab88f54fc5c50fb57b7ff1a42c70f9efa107636c7eebd986804",
    ),
    (
        INPUT_MANIFEST,
        {"a": 2, "b": 1},
        "2835effdc8d98d1141a39359f44c011669ac9cfc2dc8a0ce683febbceb0c5eb3",
    ),
    (
        PROCESS_RESULT,
        {"a": {"b": "c", "y": "x"}, "z": [3, 1, 2]},
        "9da4e049c9c7b5d784bd6d9183cb9cd2589209a658b2d6c24a6a2fbdce6a53ac",
    ),
    (
        HUMAN_DECISION,
        {"reason": "架構 — é"},
        "e4b95ef40323909ad1a38301cc50c708eab33931a58a6984cf2ba349c37bef2d",
    ),
    (
        REVIEW_RESULT,
        {"count": 0, "iteration": 1},
        "1f0dcaa550973d78da0b70ae6799dd7b20bb94c7b356d06c765ecf84ec767a26",
    ),
]

SPEC_VECTOR_6_DIGEST = (
    "fe4a508fa8056d4030e2fa4d1dc64752e460ed29b6de8714f0cd783bd6518ddf"
)
SPEC_TREE_FINGERPRINT = (
    "2e8e2d81a31883d9e7abb953e600934c31e1278938150cc66856224636226cb1"
)
SPEC_REQUIREMENT_INPUT_DIGEST = (
    "8d993bb0938335a8897a5f22b8af9311187bb003d0704f189b73675abdd0b605"
)
SPEC_UX_APPLICABLE_DIGEST = (
    "f8b222d6839d0ffe725ba59f95353067f0d2bc01e0c6d304b0414a6a484ad378"
)
SPEC_UX_NOT_APPLICABLE_DIGEST = (
    "d2fc5ebd736ab831a3161c0d73d5280f6329e07bae0a0450c358691c7beac67a"
)
SPEC_MANIFEST_DIGEST = (
    "15bc34b97823e3e2e443267c347b474abfa00242226cfa886bd971ff8083daba"
)
SPEC_START_DIGEST_APPLICABLE = (
    "ce3f939e346c905768851348b390b8dab12c84ea24cfdaeca0c7f7e3b8518f0d"
)
SPEC_START_DIGEST_NOT_APPLICABLE = (
    "0613eac534aeee827192771f221d32b4ccd776322eae74a94dc7209aa5af66ef"
)

TIMESTAMP = "2026-09-29T18:00:00Z"
CYCLE_ID = "arch-2026-09-a"
DIGEST_A = "a" * 64
DIGEST_B = "b" * 64
DIGEST_C = "c" * 64
DIGEST_D = "d" * 64
DIGEST_E = "e" * 64
REVIEW_DOCUMENT_ID = "rev-doc-1"


# --------------------------------------------------------------------------
# Fixtures built exactly as the specification's 5.3 and 5.5 fixtures describe
# --------------------------------------------------------------------------


def spec_tree_manifest_payload() -> dict[str, object]:
    """The vector-6 manifest: a null root parent and a decomposed `e` + U+0301."""
    return TreeManifest(
        requirement_id="SDLC-FR-0007",
        root_document_id="doc-root",
        entries=(
            TreeEntry("doc-root", None, "Café design", DIGEST_A),
            TreeEntry("doc-child", "doc-root", "Child", DIGEST_B),
        ),
    ).to_payload()


def spec_requirements() -> list[dict[str, object]]:
    return [
        {
            "requirement_id": "SDLC-FR-0007",
            "entity_id": "e-1",
            "tree_manifest": spec_tree_manifest_payload(),
            "tree_fingerprint": DIGEST_A,
            "process_result": {
                "document_id": "p-1",
                "iteration": 3,
                "payload_digest": DIGEST_C,
            },
            "review_result": {"document_id": "r-1", "payload_digest": DIGEST_D},
        }
    ]


def requirement_row(requirement_id: str, entity_id: str) -> dict[str, object]:
    """A coherent row: the embedded v2 manifest agrees with both bindings."""
    root_fingerprint = hashlib.sha256(requirement_id.encode()).hexdigest()
    manifest = TreeManifest(
        requirement_id=requirement_id,
        root_document_id=f"root-{entity_id}",
        entries=(TreeEntry(f"root-{entity_id}", None, "Root", root_fingerprint),),
    )
    return {
        "requirement_id": requirement_id,
        "entity_id": entity_id,
        "tree_manifest": manifest.to_payload(),
        "tree_fingerprint": root_fingerprint,
        "process_result": {
            "document_id": f"p-{entity_id}",
            "iteration": 1,
            "payload_digest": DIGEST_C,
        },
        "review_result": {"document_id": f"r-{entity_id}", "payload_digest": DIGEST_D},
    }


def spec_ux_applicable() -> dict[str, object]:
    return {
        "kind": "APPLICABLE",
        "document_id": "ux-1",
        "content_digest": DIGEST_E,
        "scope_requirement_ids": ["SDLC-FR-0007"],
        "approval": {"accepted": True, "recorded_at": TIMESTAMP},
    }


def spec_ux_not_applicable() -> dict[str, object]:
    return {
        "kind": "NOT_APPLICABLE",
        "reason": "No user-facing surface.",
        "requirement_input_digest": SPEC_REQUIREMENT_INPUT_DIGEST,
        "decision": {"accepted": True, "recorded_at": TIMESTAMP},
    }


def spec_manifest_body(ux: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "workspace_identity": (
            "example.fibery.io/11111111-2222-4333-8444-555555555555"
        ),
        "project_code": "SDLC",
        "project_entity_id": "proj-1",
        "cycle_id": CYCLE_ID,
        "created_at": TIMESTAMP,
        "requirements": spec_requirements(),
        "ux": ux if ux is not None else spec_ux_applicable(),
    }


def envelope(artifact_type: str, body: dict[str, object], **extra: object) -> dict:
    """Build a payload and seal its digest WITHOUT validating.

    Deliberately not `sealed_artifact`: several tests need a deliberately
    invalid fixture whose refusal is asserted at the call under test, not at
    construction. `sealed_artifact` has its own tests at the end of this file.
    """
    payload: dict[str, object] = {
        "artifact_type": artifact_type,
        "schema_version": 1,
        "workspace_identity": "example.fibery.io/11111111-2222-4333-8444-555555555555",
        "project_entity_id": "proj-1",
        "project_code": "SDLC",
        "cycle_id": CYCLE_ID,
        "body": body,
        **extra,
    }
    return {**payload, "artifact_digest": compute_artifact_digest(payload)}


def sections() -> dict[str, str]:
    return {key: f"prose for {key}" for key in ARCHITECTURE_SECTION_KEYS}


def traceability_rows() -> list[dict[str, object]]:
    return [
        {
            "requirement_id": "SDLC-FR-0007",
            "anchors": ["tsa-s03", "tsa-s05"],
            "how_satisfied": "Described in Solution Structure.",
            "constraints": ["Runs on the existing runtime."],
            "gaps": [],
        }
    ]


def intended_output() -> dict[str, object]:
    return {
        "sections": sections(),
        "traceability": traceability_rows(),
        "assumptions": ["The Fibery workspace is reachable."],
        "risks": [{"detail": "Schema drift.", "impact": "MEDIUM"}],
        "open_architecture_questions": ["Which cache tier?"],
        "product_questions": [
            {
                "detail": "Is offline supported?",
                "requirement_id": "SDLC-FR-0007",
                "material": False,
            }
        ],
    }


def architect_response() -> dict[str, object]:
    output = intended_output()
    return {
        "architecture": output.pop("sections"),
        **output,
    }


def input_manifest_artifact(ux: dict[str, object] | None = None) -> dict:
    body = spec_manifest_body(ux)
    digest = manifest_digest(body)
    return envelope(
        INPUT_MANIFEST,
        {
            "manifest_body": body,
            "manifest_digest": digest,
            "acceptance": {
                "manifest_digest": digest,
                "accepted": True,
                "recorded_at": TIMESTAMP,
            },
        },
    )


def applied_group(**overrides: object) -> dict[str, object]:
    """The complete applied-output group of 4.6.1: all eight keys together."""
    return {
        "manifest_digest": SPEC_MANIFEST_DIGEST,
        "content_fingerprint": DIGEST_B,
        "current_iteration": 1,
        "traceability": traceability_rows(),
        "assumptions": [],
        "risks": [],
        "open_architecture_questions": [],
        "product_questions": [],
        **overrides,
    }


def architecture_artifact(**body_extra: object) -> dict:
    return envelope(
        ARCHITECTURE, {"cycle_id": CYCLE_ID, "created_at": TIMESTAMP, **body_extra}
    )


def carrier(payload: dict[str, object]) -> str:
    """The frozen immutable-artifact carrier of 4.1, built exactly."""
    return (
        "# SDLC Architecture — Input Manifest\n"
        "\n"
        "Immutable TSA artifact written by the Architecture cycle.\n"
        "\n"
        f"```json\n{json.dumps(payload)}\n```\n"
    )


def process_result_artifact(iteration: int = 1, **body_extra: object) -> dict:
    return envelope(
        PROCESS_RESULT,
        {
            "manifest_digest": SPEC_MANIFEST_DIGEST,
            "architecture_document_id": "arch-doc-1",
            "input_fingerprint": DIGEST_A,
            "intended_output": intended_output(),
            "architect_response": architect_response(),
            "runtime": {"role": "tsa_architect"},
            "created_at": TIMESTAMP,
            **body_extra,
        },
        iteration=iteration,
    )


def reviewer_response(claim_ref: str) -> dict[str, object]:
    return {
        "claim_verifications": [
            {
                "claim_ref": claim_ref,
                "outcome": "CONFIRMED",
                "severity": "WARNING",
                "reason": "The risk is real.",
            }
        ],
        "traceability_verification": {
            "outcome": "CONFIRMED",
            "reason": "Every Requirement is anchored.",
        },
        "new_findings": [],
        "material_unresolved_what": [],
        "assessment": {
            "completeness": "Complete.",
            "internal_consistency": "Consistent.",
            "source_fidelity": "Faithful.",
            "traceability": "Covered.",
            "implementability": "Implementable.",
        },
    }


def review_result_artifact(
    process_digest: str, iteration: int = 1, **body_extra: object
) -> dict:
    return envelope(
        REVIEW_RESULT,
        {
            "manifest_digest": SPEC_MANIFEST_DIGEST,
            "process_result_document_id": "proc-doc-1",
            "process_result_digest": process_digest,
            "architecture_document_id": "arch-doc-1",
            "architecture_fingerprint": DIGEST_B,
            "reviewer_response": reviewer_response(f"{process_digest}#risks/0"),
            "derived_status": "REVIEW_NEEDS_WORK",
            "runtime": {"role": "tsa_reviewer"},
            "created_at": TIMESTAMP,
            **body_extra,
        },
        iteration=iteration,
    )


def human_decision_artifact(
    review_digest: str, process_digest: str, iteration: int = 1, **body_extra: object
) -> dict:
    return envelope(
        HUMAN_DECISION,
        {
            "decision": "APPROVE",
            "target": {
                "iteration": iteration,
                "review_result_document_id": "rev-doc-1",
                "review_result_digest": review_digest,
            },
            "architecture_document_id": "arch-doc-1",
            "architecture_fingerprint": DIGEST_B,
            "manifest_digest": SPEC_MANIFEST_DIGEST,
            "ux_evidence_digest": SPEC_UX_APPLICABLE_DIGEST,
            "process_result": {
                "document_id": "proc-doc-1",
                "payload_digest": process_digest,
            },
            "review_result": {
                "document_id": "rev-doc-1",
                "payload_digest": review_digest,
            },
            "accepted_dispositions": [
                {"ref": f"{process_digest}#risks/0", "reason": "Accepted for now."}
            ],
            "recorded_at": TIMESTAMP,
            **body_extra,
        },
        iteration=iteration,
    )


# ==========================================================================
# Canonical JSON (5.1)
# ==========================================================================


def test_keys_are_sorted_ascending():
    assert canonical_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'


def test_nested_objects_sort_and_arrays_keep_order():
    assert (
        canonical_json({"z": [3, 1, 2], "a": {"y": "x", "b": "c"}})
        == '{"a":{"b":"c","y":"x"},"z":[3,1,2]}'
    )


def test_strings_are_nfc_normalised_and_emitted_as_utf8():
    decomposed = "Café"
    assert canonical_json({"name": decomposed}) == '{"name":"Café"}'


def test_non_ascii_is_not_escaped():
    assert canonical_json({"reason": "架構"}) == '{"reason":"架構"}'


def test_booleans_are_emitted_as_json_literals():
    assert canonical_json({"accepted": True, "material": False}) == (
        '{"accepted":true,"material":false}'
    )


def test_zero_is_emitted_not_omitted():
    assert canonical_json({"count": 0}) == '{"count":0}'


def test_float_is_rejected():
    with pytest.raises(InvalidTsaArtifact, match="floating-point"):
        canonical_json({"ratio": 1.5})


def test_integral_float_is_still_rejected():
    with pytest.raises(InvalidTsaArtifact, match="floating-point"):
        canonical_json({"count": 2.0})


def test_null_is_rejected_for_a_tsa_owned_value():
    with pytest.raises(InvalidTsaArtifact, match="null"):
        canonical_json({"reason": None})


def test_uppercase_key_is_rejected():
    with pytest.raises(InvalidTsaArtifact, match="outside"):
        canonical_json({"Reason": "x"})


def test_key_starting_with_a_digit_is_rejected():
    with pytest.raises(InvalidTsaArtifact, match="outside"):
        canonical_json({"1st": "x"})


def test_key_with_a_hyphen_is_rejected():
    with pytest.raises(InvalidTsaArtifact, match="outside"):
        canonical_json({"cycle-id": "x"})


def test_non_ascii_key_is_rejected():
    with pytest.raises(InvalidTsaArtifact, match="outside"):
        canonical_json({"причина": "x"})


def test_unsupported_type_is_rejected():
    with pytest.raises(InvalidTsaArtifact, match="not JSON"):
        canonical_json({"when": {1, 2}})


def test_separators_carry_no_whitespace():
    assert " " not in canonical_json({"a": 1, "b": [1, 2]})


def test_canonical_json_does_not_mutate_the_caller_structure():
    value = {"name": "Café", "rows": [{"name": "Café"}]}
    before = copy.deepcopy(value)
    canonical_json(value)
    assert value == before


# ==========================================================================
# Reused subtree boundary (5.1.1)
# ==========================================================================


def test_reused_subtree_keeps_null_and_decomposed_unicode():
    body = {"tree_manifest": spec_tree_manifest_payload()}
    serialized = _canonical_json(body, (("tree_manifest",),))
    assert '"parent_document_id":null' in serialized
    assert "Café" in serialized
    assert "Café" not in serialized


def test_tsa_owned_sibling_is_still_normalised_beside_a_reused_subtree():
    body = {"tree_manifest": spec_tree_manifest_payload(), "note": "Café"}
    serialized = _canonical_json(body, (("tree_manifest",),))
    assert '"note":"Café"' in serialized


def test_reused_subtree_round_trips_through_tree_manifest():
    payload = spec_tree_manifest_payload()
    manifest = TreeManifest.from_payload(payload)
    assert manifest.fingerprint == SPEC_TREE_FINGERPRINT
    assert manifest.to_payload() == payload


def test_reused_subtree_keeps_its_fingerprint_after_canonical_serialization():
    payload = spec_tree_manifest_payload()
    _canonical_json({"tree_manifest": payload}, (("tree_manifest",),))
    assert TreeManifest.from_payload(payload).fingerprint == SPEC_TREE_FINGERPRINT


def test_serializing_a_manifest_as_tsa_owned_is_refused_outright():
    """Why the boundary is mandatory rather than stylistic (5.1.1).

    Without the reused declaration the root entry's `parent_document_id: null`
    hits rule 3 of 5.1 and the value never serializes at all.
    """
    payload = spec_tree_manifest_payload()
    with pytest.raises(InvalidTsaArtifact, match="null"):
        canonical_json({"tree_manifest": payload})


def test_nfc_normalising_a_reused_manifest_would_destroy_it():
    """The concrete damage 5.1.1 exists to prevent, shown on the real code."""
    import unicodedata

    payload = spec_tree_manifest_payload()
    normalised = {
        **payload,
        "documents": [
            {**doc, "name": unicodedata.normalize("NFC", doc["name"])}
            for doc in payload["documents"]
        ],
    }
    with pytest.raises(InvalidTreeManifest, match="fingerprint"):
        TreeManifest.from_payload(normalised)


def test_invalid_reused_manifest_is_refused():
    broken = spec_tree_manifest_payload()
    broken["normative_tree_fingerprint"] = DIGEST_A
    with pytest.raises(InvalidTsaArtifact, match="normative tree manifest"):
        validate_reused_tree_manifest(broken)


def test_reused_subtree_float_is_still_refused():
    with pytest.raises(InvalidTsaArtifact, match="floating-point"):
        _canonical_json({"tree_manifest": {"x": 1.5}}, (("tree_manifest",),))


# ==========================================================================
# Normative digest vectors (5.3, 5.5, 13.7-2)
# ==========================================================================


@pytest.mark.parametrize(("artifact_type", "body", "expected"), SPEC_ARTIFACT_VECTORS)
def test_spec_artifact_vectors(artifact_type, body, expected):
    assert artifact_digest(artifact_type, 1, body) == expected


def test_spec_vector_6_reused_subtree():
    body = {
        "requirement_id": "SDLC-FR-0007",
        "tree_fingerprint": DIGEST_A,
        "tree_manifest": spec_tree_manifest_payload(),
    }
    # The frozen vector digests a bare body with `("tree_manifest",)` declared
    # reused. The public API derives that path from the artifact type instead,
    # so the vector is reproduced through the private helper it derives into.
    prefix = f"sdlc.tsa.v1\n{INPUT_MANIFEST}\n1\n"
    assert _digest(prefix, body, (("tree_manifest",),)) == SPEC_VECTOR_6_DIGEST


def test_spec_requirement_input_digest_vector():
    assert requirement_input_digest(spec_requirements()) == (
        SPEC_REQUIREMENT_INPUT_DIGEST
    )


def test_spec_ux_evidence_digest_applicable_vector():
    assert ux_evidence_digest(spec_ux_applicable()) == SPEC_UX_APPLICABLE_DIGEST


def test_spec_ux_evidence_digest_not_applicable_vector():
    assert ux_evidence_digest(spec_ux_not_applicable()) == (
        SPEC_UX_NOT_APPLICABLE_DIGEST
    )


def test_the_two_ux_branches_digest_differently():
    assert SPEC_UX_APPLICABLE_DIGEST != SPEC_UX_NOT_APPLICABLE_DIGEST


def test_spec_manifest_digest_vector():
    assert manifest_digest(spec_manifest_body()) == SPEC_MANIFEST_DIGEST


def test_spec_start_input_digest_applicable_vector():
    projection = start_input_projection(
        cycle_id="tsa-2026-001",
        project_entity_id="11111111-2222-3333-4444-555555555555",
        requirement_ids=["SDLC-NFR-0002", "SDLC-FR-0001"],
        ux={
            "kind": "APPLICABLE",
            "document_id": "doc-ux-1",
            "content_digest": DIGEST_B,
            "scope_requirement_ids": ["SDLC-FR-0001"],
        },
        accept_inputs=True,
        accept_ux=True,
    )
    assert start_input_digest(projection) == SPEC_START_DIGEST_APPLICABLE


def test_spec_start_input_digest_not_applicable_vector():
    projection = start_input_projection(
        cycle_id="tsa-2026-001",
        project_entity_id="11111111-2222-3333-4444-555555555555",
        requirement_ids=["SDLC-FR-0001", "SDLC-NFR-0002"],
        ux={"kind": "NOT_APPLICABLE", "reason": "No user-facing surface"},
        accept_inputs=True,
        accept_ux=True,
    )
    assert start_input_digest(projection) == SPEC_START_DIGEST_NOT_APPLICABLE


def test_start_projection_is_independent_of_argument_order():
    kwargs = {
        "cycle_id": "tsa-2026-001",
        "project_entity_id": "p-1",
        "ux": {"kind": "NOT_APPLICABLE", "reason": "None."},
        "accept_inputs": True,
        "accept_ux": True,
    }
    first = start_input_projection(requirement_ids=["b-2", "a-1"], **kwargs)
    second = start_input_projection(requirement_ids=["a-1", "b-2", "a-1"], **kwargs)
    assert start_input_digest(first) == start_input_digest(second)


# ==========================================================================
# Digest domain separation (5.2, 5.4)
# ==========================================================================


def test_same_body_under_two_types_digests_differently():
    body = {"a": 1}
    assert artifact_digest(PROCESS_RESULT, 1, body) != artifact_digest(
        REVIEW_RESULT, 1, body
    )


def test_same_body_under_two_versions_digests_differently():
    body = {"a": 1}
    assert artifact_digest(PROCESS_RESULT, 1, body) != artifact_digest(
        PROCESS_RESULT, 2, body
    )


def test_artifact_digest_refuses_an_unknown_type():
    with pytest.raises(InvalidTsaArtifact, match="artifact_type"):
        artifact_digest("tsa.invented", 1, {"a": 1})


def test_artifact_digest_excludes_only_itself():
    body = {"a": 1}
    with_digest = {**body, "artifact_digest": DIGEST_A}
    assert artifact_digest(PROCESS_RESULT, 1, with_digest) == artifact_digest(
        PROCESS_RESULT, 1, body
    )


def test_artifact_digest_covers_every_other_field():
    assert artifact_digest(PROCESS_RESULT, 1, {"a": 1}) != artifact_digest(
        PROCESS_RESULT, 1, {"a": 2}
    )


def test_manifest_digest_is_not_the_generic_sub_digest_shape():
    reused = (("requirements", "tree_manifest"),)
    body = spec_manifest_body()
    generic = _digest("sdlc.tsa.v1\nsdlc.tsa.manifest.v1\n1\n", body, reused)
    assert manifest_digest(body) != generic


def test_manifest_digest_does_not_use_the_envelope_artifact_type_as_a_domain():
    reused = (("requirements", "tree_manifest"),)
    body = spec_manifest_body()
    wrong_domain = _digest(f"sdlc.tsa.v1\n{INPUT_MANIFEST}\n1\n", body, reused)
    assert manifest_digest(body) != wrong_domain


def test_requirement_input_and_ux_digests_do_not_collide_on_equal_bytes():
    value = {"a": 1}
    assert sub_digest("tsa.requirement_input", value) != sub_digest(
        "tsa.ux_evidence", value
    )


def test_start_input_digest_differs_from_manifest_digest_on_equal_bytes():
    value = {"a": 1}
    assert start_input_digest(value) != manifest_digest(value)


# ==========================================================================
# Envelope (4.2, 4.4, 4.5)
# ==========================================================================


def test_each_of_the_five_types_validates():
    process = process_result_artifact()
    review = review_result_artifact(process["artifact_digest"])
    for artifact in (
        architecture_artifact(),
        input_manifest_artifact(),
        process,
        review,
        human_decision_artifact(review["artifact_digest"], process["artifact_digest"]),
    ):
        assert validate_artifact(artifact).artifact_type == artifact["artifact_type"]


@pytest.mark.parametrize(
    "artifact_type", [PROCESS_RESULT, REVIEW_RESULT, HUMAN_DECISION]
)
def test_iterated_types_require_iteration(artifact_type):
    process = process_result_artifact()
    review = review_result_artifact(process["artifact_digest"])
    built = {
        PROCESS_RESULT: process,
        REVIEW_RESULT: review,
        HUMAN_DECISION: human_decision_artifact(
            review["artifact_digest"], process["artifact_digest"]
        ),
    }[artifact_type]
    assert validate_artifact(built).iteration == 1
    stripped = {k: v for k, v in built.items() if k != "iteration"}
    stripped["artifact_digest"] = compute_artifact_digest(stripped)
    with pytest.raises(InvalidTsaArtifact, match="missing"):
        validate_artifact(stripped)


@pytest.mark.parametrize("artifact_type", [ARCHITECTURE, INPUT_MANIFEST])
def test_non_iterated_types_refuse_iteration(artifact_type):
    built = (
        architecture_artifact()
        if artifact_type == ARCHITECTURE
        else input_manifest_artifact()
    )
    assert validate_artifact(built).iteration is None
    leaked = {**built, "iteration": 1}
    leaked["artifact_digest"] = compute_artifact_digest(leaked)
    with pytest.raises(InvalidTsaArtifact, match="unknown keys"):
        validate_artifact(leaked)


def test_iteration_zero_is_refused():
    artifact = dict(process_result_artifact())
    artifact["iteration"] = 0
    artifact["artifact_digest"] = compute_artifact_digest(artifact)
    with pytest.raises(InvalidTsaArtifact, match="at least 1"):
        validate_artifact(artifact)


def test_iteration_beyond_the_limit_is_refused():
    artifact = dict(process_result_artifact())
    artifact["iteration"] = 1000
    artifact["artifact_digest"] = compute_artifact_digest(artifact)
    with pytest.raises(InvalidTsaArtifact) as error:
        validate_artifact(artifact)
    assert error.value.code == "ITERATION_LIMIT"


def test_boolean_iteration_is_not_accepted_as_an_integer():
    artifact = dict(process_result_artifact())
    artifact["iteration"] = True
    artifact["artifact_digest"] = compute_artifact_digest(artifact)
    with pytest.raises(InvalidTsaArtifact, match="must be an integer"):
        validate_artifact(artifact)


def test_schema_version_two_is_refused():
    artifact = dict(architecture_artifact())
    artifact["schema_version"] = 2
    with pytest.raises(InvalidTsaArtifact, match="schema_version"):
        validate_artifact(artifact)


def test_unknown_artifact_type_is_refused():
    artifact = dict(architecture_artifact())
    artifact["artifact_type"] = "tsa.something_else"
    with pytest.raises(InvalidTsaArtifact, match="artifact_type"):
        validate_artifact(artifact)


def test_unknown_envelope_key_is_refused():
    artifact = dict(architecture_artifact())
    artifact["author"] = "someone"
    artifact["artifact_digest"] = compute_artifact_digest(artifact)
    with pytest.raises(InvalidTsaArtifact, match="unknown keys"):
        validate_artifact(artifact)


def test_unknown_nested_body_key_is_refused():
    artifact = architecture_artifact()
    artifact["body"]["surprise"] = "x"
    artifact["artifact_digest"] = compute_artifact_digest(artifact)
    with pytest.raises(InvalidTsaArtifact, match="unknown keys"):
        validate_artifact(artifact)


def test_unknown_deeply_nested_key_is_refused():
    artifact = process_result_artifact()
    artifact["body"]["intended_output"]["risks"][0]["likelihood"] = "HIGH"
    artifact["artifact_digest"] = compute_artifact_digest(artifact)
    with pytest.raises(InvalidTsaArtifact, match="unknown keys"):
        validate_artifact(artifact)


def test_malformed_stored_digest_is_refused():
    artifact = dict(architecture_artifact())
    artifact["artifact_digest"] = "not-a-digest"
    with pytest.raises(InvalidTsaArtifact, match="lowercase hex"):
        validate_artifact(artifact)


def test_wrong_stored_digest_is_refused():
    artifact = dict(architecture_artifact())
    artifact["artifact_digest"] = DIGEST_A
    with pytest.raises(InvalidTsaArtifact, match="digests to"):
        validate_artifact(artifact)


def test_tampered_body_with_a_stale_digest_is_refused():
    artifact = architecture_artifact()
    artifact["body"]["created_at"] = "2030-01-01T00:00:00Z"
    with pytest.raises(InvalidTsaArtifact, match="digests to"):
        validate_artifact(artifact)


def test_missing_envelope_field_is_refused():
    artifact = {k: v for k, v in architecture_artifact().items() if k != "project_code"}
    with pytest.raises(InvalidTsaArtifact, match="missing"):
        validate_artifact(artifact)


def test_payload_must_be_an_object():
    with pytest.raises(InvalidTsaArtifact, match="must be an object"):
        validate_artifact([1, 2, 3])


# ==========================================================================
# Cycle id (3.1)
# ==========================================================================


def test_cycle_id_is_trimmed_and_lowercased():
    assert canonical_cycle_id("  ARCH-2026-09-A  ") == "arch-2026-09-a"


def test_cycle_id_too_short_is_refused():
    with pytest.raises(InvalidTsaArtifact) as error:
        canonical_cycle_id("ab")
    assert error.value.code == "INVALID_CYCLE_ID"


def test_cycle_id_with_a_trailing_hyphen_is_refused():
    with pytest.raises(InvalidTsaArtifact, match="outside"):
        canonical_cycle_id("arch-")


def test_cycle_id_with_an_underscore_is_refused():
    with pytest.raises(InvalidTsaArtifact, match="outside"):
        canonical_cycle_id("arch_2026")


# ==========================================================================
# Architecture body (4.6.1)
# ==========================================================================


def test_bootstrap_architecture_carries_only_cycle_and_created_at():
    assert validate_artifact(architecture_artifact()).body.keys() == {
        "cycle_id",
        "created_at",
    }


def test_valid_post_apply_architecture():
    artifact = architecture_artifact(**applied_group())
    assert validate_artifact(artifact).body["product_questions"] == []


@pytest.mark.parametrize("dropped", sorted(ARCHITECTURE_APPLIED_KEYS))
def test_every_partial_applied_group_is_refused(dropped):
    group = applied_group()
    del group[dropped]
    artifact = architecture_artifact(**group)
    with pytest.raises(InvalidTsaArtifact, match="absent together or present together"):
        validate_artifact(artifact)


def test_binding_fields_without_the_renderer_arrays_are_refused():
    artifact = architecture_artifact(
        manifest_digest=SPEC_MANIFEST_DIGEST,
        content_fingerprint=DIGEST_B,
        current_iteration=1,
    )
    with pytest.raises(InvalidTsaArtifact, match="absent together or present together"):
        validate_artifact(artifact)


def test_renderer_arrays_without_the_binding_fields_are_refused():
    artifact = architecture_artifact(
        traceability=traceability_rows(),
        assumptions=[],
        risks=[],
        open_architecture_questions=[],
        product_questions=[],
    )
    with pytest.raises(InvalidTsaArtifact, match="absent together or present together"):
        validate_artifact(artifact)


def test_architecture_fingerprint_must_be_a_digest():
    artifact = architecture_artifact(**applied_group(content_fingerprint="short"))
    with pytest.raises(InvalidTsaArtifact, match="lowercase hex"):
        validate_artifact(artifact)


def test_architecture_timestamp_must_be_rfc3339_utc():
    artifact = dict(architecture_artifact())
    artifact["body"] = {"cycle_id": CYCLE_ID, "created_at": "2026-09-29 18:00:00"}
    artifact["artifact_digest"] = compute_artifact_digest(artifact)
    with pytest.raises(InvalidTsaArtifact, match="RFC-3339"):
        validate_artifact(artifact)


def test_impossible_timestamp_is_refused():
    artifact = dict(architecture_artifact())
    artifact["body"] = {"cycle_id": CYCLE_ID, "created_at": "2026-02-30T00:00:00Z"}
    artifact["artifact_digest"] = compute_artifact_digest(artifact)
    with pytest.raises(InvalidTsaArtifact, match="not a real instant"):
        validate_artifact(artifact)


def test_bad_impact_enum_is_refused():
    artifact = architecture_artifact(
        **applied_group(risks=[{"detail": "x", "impact": "CRITICAL"}])
    )
    with pytest.raises(InvalidTsaArtifact, match="must be one of"):
        validate_artifact(artifact)


def test_material_must_be_a_boolean_not_a_string():
    artifact = architecture_artifact(
        **applied_group(
            product_questions=[
                {"detail": "x", "requirement_id": "SDLC-FR-0007", "material": "true"}
            ]
        )
    )
    with pytest.raises(InvalidTsaArtifact, match="must be a boolean"):
        validate_artifact(artifact)


def test_empty_anchors_list_is_refused():
    rows = traceability_rows()
    rows[0]["anchors"] = []
    artifact = architecture_artifact(**applied_group(traceability=rows))
    with pytest.raises(InvalidTsaArtifact, match="at least 1"):
        validate_artifact(artifact)


# ==========================================================================
# Input Manifest body (4.6.2, 7.2, 7.3, 7.4)
# ==========================================================================


def test_input_manifest_validates_with_both_ux_branches():
    for ux in (spec_ux_applicable(), spec_ux_not_applicable()):
        assert validate_artifact(input_manifest_artifact(ux)).iteration is None


def test_manifest_digest_mismatch_is_refused():
    artifact = input_manifest_artifact()
    artifact["body"]["manifest_digest"] = DIGEST_A
    artifact["body"]["acceptance"]["manifest_digest"] = DIGEST_A
    artifact["artifact_digest"] = compute_artifact_digest(artifact)
    with pytest.raises(InvalidTsaArtifact, match="does not match the manifest body"):
        validate_artifact(artifact)


def test_acceptance_digest_mismatch_is_refused():
    artifact = input_manifest_artifact()
    artifact["body"]["acceptance"]["manifest_digest"] = DIGEST_A
    artifact["artifact_digest"] = compute_artifact_digest(artifact)
    with pytest.raises(InvalidTsaArtifact) as error:
        validate_artifact(artifact)
    assert error.value.code == "MANIFEST_ACCEPTANCE_MISMATCH"


def test_acceptance_must_be_true():
    artifact = input_manifest_artifact()
    artifact["body"]["acceptance"]["accepted"] = False
    artifact["artifact_digest"] = compute_artifact_digest(artifact)
    with pytest.raises(InvalidTsaArtifact, match="must be true"):
        validate_artifact(artifact)


def test_not_applicable_branch_may_not_carry_applicable_fields():
    ux = spec_ux_not_applicable()
    ux["document_id"] = "ux-1"
    artifact = input_manifest_artifact(ux)
    with pytest.raises(InvalidTsaArtifact, match="unknown keys"):
        validate_artifact(artifact)


def test_not_applicable_requirement_input_digest_is_recomputed():
    ux = spec_ux_not_applicable()
    ux["requirement_input_digest"] = DIGEST_A
    artifact = input_manifest_artifact(ux)
    with pytest.raises(InvalidTsaArtifact, match="does not cover"):
        validate_artifact(artifact)


def test_ux_scope_outside_the_selection_is_refused():
    ux = spec_ux_applicable()
    ux["scope_requirement_ids"] = ["SDLC-FR-9999"]
    artifact = input_manifest_artifact(ux)
    with pytest.raises(InvalidTsaArtifact) as error:
        validate_artifact(artifact)
    assert error.value.code == "UX_SCOPE_FOREIGN"


def test_unknown_ux_kind_is_refused():
    artifact = input_manifest_artifact({"kind": "MAYBE"})
    with pytest.raises(InvalidTsaArtifact, match="kind must be"):
        validate_artifact(artifact)


def test_empty_requirement_selection_is_refused():
    body = spec_manifest_body()
    body["requirements"] = []
    with pytest.raises(InvalidTsaArtifact) as error:
        validate_manifest_body(body)
    assert error.value.code == "SELECTION_EMPTY"


def test_duplicate_requirement_id_is_refused():
    body = spec_manifest_body()
    body["requirements"] = spec_requirements() + spec_requirements()
    with pytest.raises(InvalidTsaArtifact) as error:
        validate_manifest_body(body)
    assert error.value.code == "SELECTION_DUPLICATE"


def test_requirements_out_of_order_are_refused():
    body = spec_manifest_body()
    body["requirements"] = [
        *spec_requirements(),
        requirement_row("SDLC-FR-0001", "e-2"),
    ]
    with pytest.raises(InvalidTsaArtifact, match="ordered by requirement_id"):
        validate_manifest_body(body)


def test_manifest_with_a_broken_tree_manifest_is_refused():
    body = spec_manifest_body()
    body["requirements"][0]["tree_manifest"]["normative_tree_fingerprint"] = DIGEST_B
    with pytest.raises(InvalidTsaArtifact, match="normative tree manifest"):
        validate_manifest_body(body)


# ==========================================================================
# Process and Review bodies (4.6.3, 4.6.3.1, 4.6.4)
# ==========================================================================


def test_intended_output_missing_a_key_is_refused():
    artifact = process_result_artifact()
    del artifact["body"]["intended_output"]["product_questions"]
    artifact["artifact_digest"] = compute_artifact_digest(artifact)
    with pytest.raises(InvalidTsaArtifact, match="missing"):
        validate_artifact(artifact)


def test_intended_output_missing_a_section_is_refused():
    artifact = process_result_artifact()
    del artifact["body"]["intended_output"]["sections"]["observability"]
    artifact["artifact_digest"] = compute_artifact_digest(artifact)
    with pytest.raises(InvalidTsaArtifact, match="missing"):
        validate_artifact(artifact)


def test_architect_response_has_no_findings_array():
    artifact = process_result_artifact()
    artifact["body"]["architect_response"]["findings"] = []
    artifact["artifact_digest"] = compute_artifact_digest(artifact)
    with pytest.raises(InvalidTsaArtifact, match="unknown keys"):
        validate_artifact(artifact)


def test_process_runtime_role_is_fixed():
    artifact = process_result_artifact()
    artifact["body"]["runtime"]["role"] = "tsa_reviewer"
    artifact["artifact_digest"] = compute_artifact_digest(artifact)
    with pytest.raises(InvalidTsaArtifact, match="role must be"):
        validate_artifact(artifact)


def test_process_runtime_model_is_optional():
    artifact = process_result_artifact()
    artifact["body"]["runtime"]["model"] = "claude-opus-5"
    artifact["artifact_digest"] = compute_artifact_digest(artifact)
    assert validate_artifact(artifact).body["runtime"]["model"] == "claude-opus-5"


def test_confirmed_verification_requires_severity():
    process = process_result_artifact()
    artifact = review_result_artifact(process["artifact_digest"])
    del artifact["body"]["reviewer_response"]["claim_verifications"][0]["severity"]
    artifact["artifact_digest"] = compute_artifact_digest(artifact)
    with pytest.raises(InvalidTsaArtifact, match="must carry"):
        validate_artifact(artifact)


def test_rejected_verification_forbids_severity():
    process = process_result_artifact()
    artifact = review_result_artifact(process["artifact_digest"])
    artifact["body"]["reviewer_response"]["claim_verifications"][0]["outcome"] = (
        "REJECTED"
    )
    artifact["artifact_digest"] = compute_artifact_digest(artifact)
    with pytest.raises(InvalidTsaArtifact, match="must not carry a severity"):
        validate_artifact(artifact)


def test_reviewer_response_has_no_verdict_field():
    process = process_result_artifact()
    artifact = review_result_artifact(process["artifact_digest"])
    artifact["body"]["reviewer_response"]["verdict"] = "APPROVE"
    artifact["artifact_digest"] = compute_artifact_digest(artifact)
    with pytest.raises(InvalidTsaArtifact, match="unknown keys"):
        validate_artifact(artifact)


def test_bad_derived_status_is_refused():
    process = process_result_artifact()
    artifact = review_result_artifact(process["artifact_digest"])
    artifact["body"]["derived_status"] = "REVIEW_OK"
    artifact["artifact_digest"] = compute_artifact_digest(artifact)
    with pytest.raises(InvalidTsaArtifact, match="must be one of"):
        validate_artifact(artifact)


def test_claim_ref_outside_the_grammar_is_refused():
    process = process_result_artifact()
    artifact = review_result_artifact(process["artifact_digest"])
    artifact["body"]["reviewer_response"]["claim_verifications"][0]["claim_ref"] = (
        "risks/0"
    )
    artifact["artifact_digest"] = compute_artifact_digest(artifact)
    with pytest.raises(InvalidTsaArtifact) as error:
        validate_artifact(artifact)
    assert error.value.code == "DISPOSITION_UNKNOWN_REFERENCE"


# ==========================================================================
# Human Decision body (4.6.5) and reference grammar (6.1, 6.2)
# ==========================================================================


def test_reference_grammar_parses():
    reference = parse_reference(f"{DIGEST_A}#risks/0")
    assert (reference.digest, reference.collection, reference.index) == (
        DIGEST_A,
        "risks",
        0,
    )


@pytest.mark.parametrize(
    "raw",
    [
        f"{DIGEST_A}#risks/00",
        f"{DIGEST_A}#risks/-1",
        f"{DIGEST_A}#risks/1.0",
        f"{'A' * 64}#risks/0",
        f"{DIGEST_A}#nonsense/0",
        f"{DIGEST_A}risks/0",
    ],
)
def test_bad_references_are_refused(raw):
    with pytest.raises(InvalidTsaArtifact) as error:
        parse_reference(raw)
    assert error.value.code == "DISPOSITION_UNKNOWN_REFERENCE"


def test_collections_are_bound_to_their_source_artifact_type():
    assert reference_allows_collection(PROCESS_RESULT, "risks")
    assert not reference_allows_collection(REVIEW_RESULT, "risks")
    assert reference_allows_collection(REVIEW_RESULT, "new_findings")
    assert not reference_allows_collection(PROCESS_RESULT, "new_findings")


def test_material_unresolved_what_is_not_waivable():
    process = process_result_artifact()
    review = review_result_artifact(process["artifact_digest"])
    artifact = human_decision_artifact(
        review["artifact_digest"], process["artifact_digest"]
    )
    artifact["body"]["accepted_dispositions"] = [
        {
            "ref": f"{review['artifact_digest']}#material_unresolved_what/0",
            "reason": "Accepting.",
        }
    ]
    artifact["artifact_digest"] = compute_artifact_digest(artifact)
    with pytest.raises(InvalidTsaArtifact) as error:
        validate_artifact(artifact)
    assert error.value.code == "DISPOSITION_NOT_WAIVABLE"


def test_duplicate_disposition_reference_is_refused():
    process = process_result_artifact()
    review = review_result_artifact(process["artifact_digest"])
    artifact = human_decision_artifact(
        review["artifact_digest"], process["artifact_digest"]
    )
    reference = {"ref": f"{process['artifact_digest']}#risks/0", "reason": "Twice."}
    artifact["body"]["accepted_dispositions"] = [reference, dict(reference)]
    artifact["artifact_digest"] = compute_artifact_digest(artifact)
    with pytest.raises(InvalidTsaArtifact) as error:
        validate_artifact(artifact)
    assert error.value.code == "DISPOSITION_DUPLICATE_REFERENCE"


def test_bad_decision_enum_is_refused():
    process = process_result_artifact()
    review = review_result_artifact(process["artifact_digest"])
    artifact = human_decision_artifact(
        review["artifact_digest"], process["artifact_digest"]
    )
    artifact["body"]["decision"] = "MAYBE"
    artifact["artifact_digest"] = compute_artifact_digest(artifact)
    with pytest.raises(InvalidTsaArtifact, match="must be one of"):
        validate_artifact(artifact)


def test_decision_reason_is_optional():
    process = process_result_artifact()
    review = review_result_artifact(process["artifact_digest"])
    artifact = human_decision_artifact(
        review["artifact_digest"], process["artifact_digest"], reason="Ship it."
    )
    assert validate_artifact(artifact).body["reason"] == "Ship it."


# ==========================================================================
# Carrier boundary (4.1, 12)
# ==========================================================================


def test_empty_carrier_is_not_malformed():
    with pytest.raises(EmptyTsaCarrier):
        extract_artifact_payload("   \n  ")


def test_payload_round_trips_out_of_the_frozen_carrier():
    artifact = input_manifest_artifact()
    assert validate_artifact(extract_artifact_payload(carrier(artifact))).cycle_id == (
        CYCLE_ID
    )


@pytest.mark.parametrize(
    ("label", "text"),
    [
        ("no fence", "# T\n\nProse but no payload.\n"),
        (
            "two fences",
            '# T\n\nProse.\n\n```json\n{"a":1}\n```\n\n```json\n{"b":2}\n```\n',
        ),
        (
            "trailing prose",
            '# T\n\nProse.\n\n```json\n{"a":1}\n```\n\nAnd more prose.\n',
        ),
        (
            "second incomplete fence",
            '# T\n\nProse.\n\n```json\n{"a":1}\n```\n\n```json\n{"b":2}\n',
        ),
        ("incomplete fence", '# T\n\nProse.\n\n```json\n{"a":1}\n'),
        ("no heading", 'Prose.\n\n```json\n{"a":1}\n```\n'),
        ("wrong heading level", '## T\n\nProse.\n\n```json\n{"a":1}\n```\n'),
        ("no prose paragraph", '# T\n\n```json\n{"a":1}\n```\n'),
        ("fence before the heading", '```json\n{"a":1}\n```\n\n# T\n\nProse.\n'),
    ],
)
def test_carrier_shapes_that_are_malformed(label, text):
    with pytest.raises(InvalidTsaArtifact):
        extract_artifact_payload(text)


def test_valid_carrier_with_unparseable_payload_is_malformed():
    """The shape is right, the JSON is not: still a controlled refusal."""
    with pytest.raises(InvalidTsaArtifact, match="does not parse"):
        extract_artifact_payload("# T\n\nProse.\n\n```json\n{not json}\n```\n")


def test_carrier_payload_must_be_an_object():
    with pytest.raises(InvalidTsaArtifact, match="must be an object"):
        extract_artifact_payload("# T\n\nProse.\n\n```json\n[1, 2]\n```\n")


def test_duplicate_json_key_is_refused():
    text = '# T\n\nProse.\n\n```json\n{"a": 1, "a": 2}\n```\n'
    with pytest.raises(InvalidTsaArtifact, match="more than once"):
        extract_artifact_payload(text)


def test_duplicate_json_key_is_refused_at_any_depth():
    text = '# T\n\nProse.\n\n```json\n{"outer": {"b": 1, "b": 2}}\n```\n'
    with pytest.raises(InvalidTsaArtifact, match="more than once"):
        extract_artifact_payload(text)


def test_architecture_envelope_allows_rendered_markdown_before_the_fence():
    artifact = architecture_artifact(**applied_group())
    text = (
        "# Architecture\n\n## 1. Scope & Inputs\n\nProse.\n\n"
        "## 2. Solution Structure\n\nMore prose.\n\n"
        f"```json\n{json.dumps(artifact)}\n```\n"
    )
    assert validate_artifact(extract_architecture_envelope(text)).cycle_id == CYCLE_ID


def test_architecture_envelope_refuses_content_after_the_fence():
    artifact = architecture_artifact()
    text = (
        f"# Architecture\n\nProse.\n\n```json\n{json.dumps(artifact)}\n```\n\nMore.\n"
    )
    with pytest.raises(InvalidTsaArtifact, match="content after the closing fence"):
        extract_architecture_envelope(text)


def test_architecture_envelope_refuses_an_empty_carrier():
    with pytest.raises(EmptyTsaCarrier):
        extract_architecture_envelope("\n\n  ")


# ==========================================================================
# Pure lineage invariants (4.6.5)
# ==========================================================================


def lineage_set():
    architecture = validate_artifact(architecture_artifact(**applied_group()))
    manifest = validate_artifact(input_manifest_artifact())
    process = validate_artifact(process_result_artifact())
    review = validate_artifact(review_result_artifact(process.artifact_digest))
    decision = validate_artifact(
        human_decision_artifact(review.artifact_digest, process.artifact_digest)
    )
    return architecture, manifest, process, review, decision


def test_a_consistent_lineage_passes():
    architecture, manifest, process, review, decision = lineage_set()
    validate_structural_lineage(
        architecture=architecture,
        input_manifest=manifest,
        process_result=process,
        review_result=review,
        human_decision=decision,
        review_document_id=REVIEW_DOCUMENT_ID,
    )


def test_foreign_cycle_is_refused():
    architecture, manifest, process, _, _ = lineage_set()
    other = validate_artifact(
        envelope(
            PROCESS_RESULT,
            dict(process.body),
            iteration=1,
            cycle_id="arch-2026-09-b",
        )
    )
    with pytest.raises(InvalidTsaArtifact, match="carries cycle_id"):
        validate_structural_lineage(
            architecture=architecture, input_manifest=manifest, process_result=other
        )


def test_review_of_another_iteration_is_refused():
    architecture, manifest, process, _, _ = lineage_set()
    review = validate_artifact(
        review_result_artifact(process.artifact_digest, iteration=2)
    )
    with pytest.raises(InvalidTsaArtifact, match="iteration"):
        validate_structural_lineage(
            architecture=architecture,
            input_manifest=manifest,
            process_result=process,
            review_result=review,
        )


def test_review_naming_another_process_digest_is_refused():
    architecture, manifest, process, _, _ = lineage_set()
    review = validate_artifact(review_result_artifact(DIGEST_C))
    with pytest.raises(InvalidTsaArtifact, match="process_result_digest"):
        validate_structural_lineage(
            architecture=architecture,
            input_manifest=manifest,
            process_result=process,
            review_result=review,
        )


def test_decision_naming_another_review_digest_is_refused():
    architecture, manifest, process, review, _ = lineage_set()
    decision = validate_artifact(
        human_decision_artifact(DIGEST_D, process.artifact_digest)
    )
    with pytest.raises(InvalidTsaArtifact, match="review_result_digest"):
        validate_structural_lineage(
            architecture=architecture,
            input_manifest=manifest,
            process_result=process,
            review_result=review,
            human_decision=decision,
            review_document_id=REVIEW_DOCUMENT_ID,
        )


def test_foreign_manifest_binding_is_refused():
    architecture, manifest, _, _, _ = lineage_set()
    drifted = validate_artifact(process_result_artifact(manifest_digest=DIGEST_A))
    with pytest.raises(InvalidTsaArtifact, match="binds manifest_digest"):
        validate_structural_lineage(
            architecture=architecture,
            input_manifest=manifest,
            process_result=drifted,
        )


# ==========================================================================
# Sealing
# ==========================================================================


def test_sealed_artifact_replaces_a_caller_supplied_digest():
    artifact = architecture_artifact()
    tampered = {**artifact, "artifact_digest": DIGEST_A}
    assert sealed_artifact(tampered)["artifact_digest"] == artifact["artifact_digest"]


def test_sealed_artifact_refuses_an_invalid_body():
    with pytest.raises(InvalidTsaArtifact):
        sealed_artifact(
            {
                "artifact_type": ARCHITECTURE,
                "schema_version": 1,
                "workspace_identity": "host/space",
                "project_entity_id": "p",
                "project_code": "SDLC",
                "cycle_id": CYCLE_ID,
                "body": {"cycle_id": CYCLE_ID},
            }
        )


# ==========================================================================
# H1 — Human Decision iteration lineage and duplicated Review bindings
# ==========================================================================


def test_decision_envelope_iteration_must_equal_the_target_iteration():
    architecture, manifest, process, review, _ = lineage_set()
    decision = validate_artifact(
        human_decision_artifact(
            review.artifact_digest, process.artifact_digest, iteration=2
        )
    )
    # The envelope says 2, the target says 2, but the Review is iteration 1.
    with pytest.raises(InvalidTsaArtifact, match="names a Review Result of iteration"):
        validate_structural_lineage(
            architecture=architecture,
            input_manifest=manifest,
            process_result=process,
            review_result=review,
            human_decision=decision,
            review_document_id=REVIEW_DOCUMENT_ID,
        )


def test_decision_envelope_iteration_two_with_target_iteration_one_is_refused():
    architecture, manifest, process, review, _ = lineage_set()
    artifact = human_decision_artifact(
        review.artifact_digest, process.artifact_digest, iteration=1
    )
    artifact["iteration"] = 2
    artifact["artifact_digest"] = compute_artifact_digest(artifact)
    decision = validate_artifact(artifact)
    with pytest.raises(InvalidTsaArtifact, match="envelope carries iteration 2"):
        validate_structural_lineage(
            architecture=architecture,
            input_manifest=manifest,
            process_result=process,
            review_result=review,
            human_decision=decision,
            review_document_id=REVIEW_DOCUMENT_ID,
        )


def test_target_iteration_one_against_review_iteration_two_is_refused():
    architecture, manifest, _, _, _ = lineage_set()
    process = validate_artifact(process_result_artifact(iteration=2))
    review = validate_artifact(
        review_result_artifact(process.artifact_digest, iteration=2)
    )
    decision = validate_artifact(
        human_decision_artifact(
            review.artifact_digest, process.artifact_digest, iteration=1
        )
    )
    with pytest.raises(
        InvalidTsaArtifact, match="names a Review Result of iteration 2"
    ):
        validate_structural_lineage(
            architecture=architecture,
            input_manifest=manifest,
            process_result=process,
            review_result=review,
            human_decision=decision,
            review_document_id=REVIEW_DOCUMENT_ID,
        )


def test_target_review_document_id_must_equal_the_nested_one():
    _, _, process, review, _ = lineage_set()
    artifact = human_decision_artifact(review.artifact_digest, process.artifact_digest)
    artifact["body"]["target"]["review_result_document_id"] = "rev-doc-OTHER"
    artifact["artifact_digest"] = compute_artifact_digest(artifact)
    with pytest.raises(InvalidTsaArtifact, match="duplicated identity must agree"):
        validate_artifact(artifact)


def test_target_review_digest_must_equal_the_nested_one():
    _, _, process, review, _ = lineage_set()
    artifact = human_decision_artifact(review.artifact_digest, process.artifact_digest)
    artifact["body"]["review_result"]["payload_digest"] = DIGEST_C
    artifact["artifact_digest"] = compute_artifact_digest(artifact)
    with pytest.raises(InvalidTsaArtifact, match="duplicated identity must agree"):
        validate_artifact(artifact)


# ==========================================================================
# H2 — TreeManifest v2 and root-fingerprint binding
# ==========================================================================


def test_valid_v2_requirement_row_is_accepted():
    body = spec_manifest_body()
    body["requirements"] = [requirement_row("SDLC-FR-0001", "e-1")]
    body["ux"]["scope_requirement_ids"] = ["SDLC-FR-0001"]
    validate_manifest_body(body)


def test_legacy_v1_tree_manifest_is_rejected():
    row = requirement_row("SDLC-FR-0001", "e-1")
    legacy = TreeManifest(
        requirement_id="SDLC-FR-0001",
        root_document_id="root-e-1",
        entries=(TreeEntry("root-e-1", None, "Root", row["tree_fingerprint"]),),
        version=1,
    )
    row["tree_manifest"] = legacy.to_payload()
    body = spec_manifest_body()
    body["requirements"] = [row]
    body["ux"]["scope_requirement_ids"] = ["SDLC-FR-0001"]
    with pytest.raises(InvalidTsaArtifact, match="requires v2"):
        validate_manifest_body(body)


def test_embedded_requirement_id_must_equal_the_outer_one():
    row = requirement_row("SDLC-FR-0001", "e-1")
    row["requirement_id"] = "SDLC-FR-0002"
    body = spec_manifest_body()
    body["requirements"] = [row]
    body["ux"]["scope_requirement_ids"] = ["SDLC-FR-0002"]
    with pytest.raises(InvalidTsaArtifact, match="duplicated identity must agree"):
        validate_manifest_body(body)


def test_tree_fingerprint_must_equal_the_root_content_fingerprint():
    row = requirement_row("SDLC-FR-0001", "e-1")
    row["tree_fingerprint"] = DIGEST_C
    body = spec_manifest_body()
    body["requirements"] = [row]
    body["ux"]["scope_requirement_ids"] = ["SDLC-FR-0001"]
    with pytest.raises(InvalidTsaArtifact, match="duplicated identity must agree"):
        validate_manifest_body(body)


def test_the_decomposed_unicode_vector_still_validates_unchanged():
    """The 5.5 fixture uses `tree_fingerprint = "a"*64`, which is the vector-6
    manifest's Root content fingerprint, so H2's binding holds on it."""
    validate_manifest_body(spec_manifest_body())
    assert manifest_digest(spec_manifest_body()) == SPEC_MANIFEST_DIGEST


# ==========================================================================
# H3 — persisted identity is validated as stored, never normalised
# ==========================================================================


@pytest.mark.parametrize(
    "stored",
    [" arch-2026-09-a", "arch-2026-09-a ", "ARCH-2026-09-A", " ARCH-2026-09-A "],
)
def test_noncanonical_persisted_cycle_id_is_refused(stored):
    with pytest.raises(InvalidTsaArtifact) as error:
        require_canonical_cycle_id(stored, ("x",))
    assert error.value.code == "INVALID_CYCLE_ID"


def test_canonical_persisted_cycle_id_is_returned_unchanged():
    assert require_canonical_cycle_id(CYCLE_ID, ("x",)) == CYCLE_ID


def test_noncanonical_envelope_cycle_id_is_refused():
    artifact = dict(architecture_artifact())
    artifact["cycle_id"] = " ARCH-2026-09-A "
    artifact["body"]["cycle_id"] = " ARCH-2026-09-A "
    artifact["artifact_digest"] = compute_artifact_digest(artifact)
    with pytest.raises(InvalidTsaArtifact, match="never normalised on read"):
        validate_artifact(artifact)


def test_validation_does_not_rewrite_the_stored_cycle_id():
    artifact = architecture_artifact()
    before = copy.deepcopy(artifact)
    validate_artifact(artifact)
    assert artifact == before


def test_architecture_body_cycle_id_must_equal_the_envelope():
    artifact = dict(architecture_artifact())
    artifact["body"] = {"cycle_id": "arch-2026-09-b", "created_at": TIMESTAMP}
    artifact["artifact_digest"] = compute_artifact_digest(artifact)
    with pytest.raises(InvalidTsaArtifact, match="duplicated identity must agree"):
        validate_artifact(artifact)


@pytest.mark.parametrize(
    ("field", "wrong"),
    [
        ("cycle_id", "arch-2026-09-b"),
        ("project_entity_id", "proj-OTHER"),
        ("project_code", "OTHER"),
        ("workspace_identity", "other.fibery.io/11111111-2222-4333-8444-555555555555"),
    ],
)
def test_manifest_body_identity_must_equal_the_envelope(field, wrong):
    artifact = input_manifest_artifact()
    body = artifact["body"]["manifest_body"]
    body[field] = wrong
    artifact["body"]["manifest_digest"] = manifest_digest(body)
    artifact["body"]["acceptance"]["manifest_digest"] = artifact["body"][
        "manifest_digest"
    ]
    artifact["artifact_digest"] = compute_artifact_digest(artifact)
    with pytest.raises(InvalidTsaArtifact, match="duplicated identity must agree"):
        validate_artifact(artifact)


def test_manifest_body_cycle_id_must_itself_be_canonical():
    body = spec_manifest_body()
    body["cycle_id"] = "ARCH-2026-09-A"
    with pytest.raises(InvalidTsaArtifact, match="never normalised on read"):
        validate_manifest_body(body)


# ==========================================================================
# M1 — no caller-controlled reused-path escape hatch
# ==========================================================================


def test_public_canonical_json_takes_no_reused_paths():
    import inspect

    assert list(inspect.signature(canonical_json).parameters) == ["value"]
    assert list(inspect.signature(canonical_bytes).parameters) == ["value"]


def test_public_artifact_digest_takes_no_reused_paths():
    import inspect

    assert list(inspect.signature(artifact_digest).parameters) == [
        "artifact_type",
        "schema_version",
        "payload",
    ]
    assert list(inspect.signature(sub_digest).parameters) == ["tag", "value"]


def test_a_caller_cannot_admit_null_by_naming_a_fake_reused_path():
    with pytest.raises(TypeError):
        canonical_json({"anything": None}, (("anything",),))
    with pytest.raises(InvalidTsaArtifact, match="null"):
        canonical_json({"anything": None})


def test_whole_payload_reuse_cannot_be_requested():
    with pytest.raises(TypeError):
        canonical_json({"a": None}, ((),))


def test_only_the_input_manifest_receives_the_exception():
    assert _reused_paths_for(INPUT_MANIFEST) == (
        ("body", "manifest_body", "requirements", "tree_manifest"),
    )
    for artifact_type in (ARCHITECTURE, PROCESS_RESULT, REVIEW_RESULT, HUMAN_DECISION):
        assert _reused_paths_for(artifact_type) == ()


def test_null_elsewhere_in_a_manifest_payload_is_still_refused():
    """The exemption is a path, not a whole artifact type."""
    body = spec_manifest_body()
    body["requirements"][0]["process_result"]["document_id"] = None
    with pytest.raises(InvalidTsaArtifact, match="null"):
        manifest_digest(body)


def test_sub_digest_grants_no_exemption():
    with pytest.raises(InvalidTsaArtifact, match="null"):
        sub_digest("tsa.ux_evidence", {"tree_manifest": {"parent": None}})


# ==========================================================================
# M2 — whole-token matching
# ==========================================================================


def test_key_with_a_trailing_newline_is_refused():
    with pytest.raises(InvalidTsaArtifact, match="outside"):
        canonical_json({"reason\n": "x"})


def test_digest_with_a_trailing_newline_is_refused():
    artifact = dict(architecture_artifact())
    artifact["artifact_digest"] = DIGEST_A + "\n"
    with pytest.raises(InvalidTsaArtifact, match="exactly 64 lowercase hex"):
        validate_artifact(artifact)


def test_reference_with_a_trailing_newline_is_refused():
    with pytest.raises(InvalidTsaArtifact) as error:
        parse_reference(f"{DIGEST_A}#risks/0\n")
    assert error.value.code == "DISPOSITION_UNKNOWN_REFERENCE"


def test_persisted_cycle_id_with_a_trailing_newline_is_refused():
    """Caller argv is trimmed by design (3.1); persisted identity is not."""
    assert canonical_cycle_id("arch-2026-09-a\n") == CYCLE_ID
    with pytest.raises(InvalidTsaArtifact, match="never normalised on read"):
        require_canonical_cycle_id("arch-2026-09-a\n", ("x",))


def test_cycle_id_with_an_inner_newline_is_refused():
    with pytest.raises(InvalidTsaArtifact, match="outside"):
        canonical_cycle_id("arch\n2026")


def test_timestamp_with_a_trailing_newline_is_refused():
    artifact = dict(architecture_artifact())
    artifact["body"] = {"cycle_id": CYCLE_ID, "created_at": TIMESTAMP + "\n"}
    artifact["artifact_digest"] = compute_artifact_digest(artifact)
    with pytest.raises(InvalidTsaArtifact, match="RFC-3339"):
        validate_artifact(artifact)


def test_every_whole_token_pattern_is_used_with_fullmatch():
    """No `.match(` on a whole-token grammar anywhere in the module."""
    import pathlib

    import sdlc.tsa_artifacts as module

    source = pathlib.Path(module.__file__).read_text(encoding="utf-8")
    for name in (
        "KEY_PATTERN",
        "DIGEST_PATTERN",
        "TIMESTAMP_PATTERN",
        "CYCLE_ID_PATTERN",
        "REFERENCE_PATTERN",
    ):
        assert f"{name}.match(" not in source
        assert f"{name}.search(" not in source


# ==========================================================================
# M4 — controlled refusals for hostile JSON values
# ==========================================================================


@pytest.mark.parametrize(
    ("field", "value"),
    [("artifact_type", []), ("schema_version", [])],
)
def test_unhashable_envelope_values_are_controlled(field, value):
    artifact = dict(architecture_artifact())
    artifact[field] = value
    with pytest.raises(InvalidTsaArtifact):
        validate_artifact(artifact)


def test_unhashable_derived_status_is_controlled():
    process = process_result_artifact()
    artifact = review_result_artifact(process["artifact_digest"])
    artifact["body"]["derived_status"] = []
    artifact["artifact_digest"] = compute_artifact_digest(artifact)
    with pytest.raises(InvalidTsaArtifact, match="must be a string naming one of"):
        validate_artifact(artifact)


def test_unhashable_decision_is_controlled():
    process = process_result_artifact()
    review = review_result_artifact(process["artifact_digest"])
    artifact = human_decision_artifact(
        review["artifact_digest"], process["artifact_digest"]
    )
    artifact["body"]["decision"] = []
    artifact["artifact_digest"] = compute_artifact_digest(artifact)
    with pytest.raises(InvalidTsaArtifact, match="must be a string naming one of"):
        validate_artifact(artifact)


def test_unhashable_impact_is_controlled():
    artifact = architecture_artifact(
        **applied_group(risks=[{"detail": "x", "impact": []}])
    )
    with pytest.raises(InvalidTsaArtifact, match="must be a string naming one of"):
        validate_artifact(artifact)


def test_lone_surrogate_is_controlled():
    with pytest.raises(InvalidTsaArtifact, match="not encodable as"):
        canonical_json({"reason": "bad \ud800 value"})


def test_lone_surrogate_in_a_key_is_controlled():
    with pytest.raises(InvalidTsaArtifact, match="outside"):
        canonical_json({"bad\ud800key": "x"})


def test_lone_surrogate_inside_a_reused_subtree_is_controlled():
    with pytest.raises(InvalidTsaArtifact, match="not encodable as"):
        _canonical_json({"tree_manifest": {"n": "\ud800"}}, (("tree_manifest",),))


def test_huge_integer_is_controlled():
    with pytest.raises(InvalidTsaArtifact, match="too wide to serialize"):
        canonical_json({"count": 10**5000})


def test_huge_integer_in_an_iteration_field_is_controlled():
    artifact = dict(process_result_artifact())
    artifact["iteration"] = 10**5000
    with pytest.raises(InvalidTsaArtifact, match="too wide to serialize"):
        validate_artifact(artifact)


def test_ordinary_integers_still_serialize():
    assert canonical_json({"count": 10**100}).startswith('{"count":1')


# ==========================================================================
# M6 — the lineage API states exactly what it validates
# ==========================================================================


def test_lineage_docstring_names_the_deferred_invariants():
    doc = validate_structural_lineage.__doc__ or ""
    assert "1-5 only" in doc
    assert "I11" in doc and "I06" in doc
    assert "NOT checked here" in doc


def test_the_module_exposes_no_function_claiming_full_lineage():
    import sdlc.tsa_artifacts as module

    assert not hasattr(module, "validate_lineage")


# ==========================================================================
# Seal -> validate holds for all five valid fixtures
# ==========================================================================


def test_seal_then_validate_for_every_artifact_type():
    process = sealed_artifact(process_result_artifact())
    review = sealed_artifact(review_result_artifact(process["artifact_digest"]))
    decision = sealed_artifact(
        human_decision_artifact(review["artifact_digest"], process["artifact_digest"])
    )
    sealed = [
        sealed_artifact(architecture_artifact(**applied_group())),
        sealed_artifact(input_manifest_artifact()),
        process,
        review,
        decision,
    ]
    assert {item["artifact_type"] for item in sealed} == {
        ARCHITECTURE,
        INPUT_MANIFEST,
        PROCESS_RESULT,
        REVIEW_RESULT,
        HUMAN_DECISION,
    }
    for item in sealed:
        assert validate_artifact(item).artifact_digest == item["artifact_digest"]


# ==========================================================================
# H1 — the Decision must name the Review Document that actually exists
# ==========================================================================


def decision_lineage(**overrides):
    """A coherent Architecture/Manifest/Process/Review set plus a Decision."""
    architecture, manifest, process, review, _ = lineage_set()
    artifact = human_decision_artifact(review.artifact_digest, process.artifact_digest)
    for path, value in overrides.items():
        section, key = path.split("__")
        artifact["body"][section][key] = value
    artifact["artifact_digest"] = compute_artifact_digest(artifact)
    return architecture, manifest, process, review, artifact


def test_correct_actual_review_id_digest_and_iteration_pass():
    architecture, manifest, process, review, artifact = decision_lineage()
    validate_structural_lineage(
        architecture=architecture,
        input_manifest=manifest,
        process_result=process,
        review_result=review,
        human_decision=validate_artifact(artifact),
        review_document_id=REVIEW_DOCUMENT_ID,
    )


def test_both_review_ids_changed_to_the_same_wrong_id_is_refused():
    """Self-consistency is not identity: both spellings can be wrong together."""
    architecture, manifest, process, review, artifact = decision_lineage(
        target__review_result_document_id="rev-doc-WRONG",
        review_result__document_id="rev-doc-WRONG",
    )
    with pytest.raises(InvalidTsaArtifact, match="actually lives at"):
        validate_structural_lineage(
            architecture=architecture,
            input_manifest=manifest,
            process_result=process,
            review_result=review,
            human_decision=validate_artifact(artifact),
            review_document_id=REVIEW_DOCUMENT_ID,
        )


def test_nested_review_id_wrong_alone_is_refused_at_schema_time():
    """The intra-artifact agreement of 4.6.5 catches a single wrong spelling."""
    _, _, process, review, _ = lineage_set()
    artifact = human_decision_artifact(review.artifact_digest, process.artifact_digest)
    artifact["body"]["review_result"]["document_id"] = "rev-doc-WRONG"
    artifact["artifact_digest"] = compute_artifact_digest(artifact)
    with pytest.raises(InvalidTsaArtifact, match="duplicated identity must agree"):
        validate_artifact(artifact)


def test_target_review_id_wrong_alone_is_refused_at_schema_time():
    _, _, process, review, _ = lineage_set()
    artifact = human_decision_artifact(review.artifact_digest, process.artifact_digest)
    artifact["body"]["target"]["review_result_document_id"] = "rev-doc-WRONG"
    artifact["artifact_digest"] = compute_artifact_digest(artifact)
    with pytest.raises(InvalidTsaArtifact, match="duplicated identity must agree"):
        validate_artifact(artifact)


def test_missing_review_document_id_fails_closed():
    architecture, manifest, process, review, artifact = decision_lineage()
    with pytest.raises(InvalidTsaArtifact, match="requires the Review Document"):
        validate_structural_lineage(
            architecture=architecture,
            input_manifest=manifest,
            process_result=process,
            review_result=review,
            human_decision=validate_artifact(artifact),
        )


def test_review_document_id_is_not_required_without_a_decision():
    architecture, manifest, process, review, _ = lineage_set()
    validate_structural_lineage(
        architecture=architecture,
        input_manifest=manifest,
        process_result=process,
        review_result=review,
    )


def test_nested_review_digest_must_also_name_the_supplied_review():
    """Both digest spellings are bound to the Review artifact, not just one."""
    architecture, manifest, process, review, _ = lineage_set()
    artifact = human_decision_artifact(review.artifact_digest, process.artifact_digest)
    artifact["body"]["target"]["review_result_digest"] = DIGEST_C
    artifact["body"]["review_result"]["payload_digest"] = DIGEST_C
    artifact["artifact_digest"] = compute_artifact_digest(artifact)
    with pytest.raises(InvalidTsaArtifact, match="does not name the"):
        validate_structural_lineage(
            architecture=architecture,
            input_manifest=manifest,
            process_result=process,
            review_result=review,
            human_decision=validate_artifact(artifact),
            review_document_id=REVIEW_DOCUMENT_ID,
        )


def test_decision_to_process_binding_is_still_deferred_to_i11():
    """A wrong Decision->Process digest is NOT this function's business."""
    architecture, manifest, process, review, _ = lineage_set()
    artifact = human_decision_artifact(review.artifact_digest, process.artifact_digest)
    artifact["body"]["process_result"]["payload_digest"] = DIGEST_C
    artifact["artifact_digest"] = compute_artifact_digest(artifact)
    validate_structural_lineage(
        architecture=architecture,
        input_manifest=manifest,
        process_result=process,
        review_result=review,
        human_decision=validate_artifact(artifact),
        review_document_id=REVIEW_DOCUMENT_ID,
    )


# ==========================================================================
# M3 — the prefix may not swallow a fence
# ==========================================================================


def test_immutable_carrier_refuses_a_fence_hidden_in_the_prose():
    text = '# T\n\n```json\n{"hidden":1}\n```\n\n```json\n{"a":1}\n```\n'
    with pytest.raises(InvalidTsaArtifact, match="2 ```json fences"):
        extract_artifact_payload(text)


def test_immutable_carrier_refuses_a_fence_inside_the_prose_paragraph():
    text = '# T\n\nProse with ```json inline.\n\n```json\n{"a":1}\n```\n'
    with pytest.raises(InvalidTsaArtifact, match="prose paragraph carries a fence"):
        extract_artifact_payload(text)


def test_immutable_carrier_refuses_a_non_json_fence_in_the_prose():
    text = '# T\n\nProse.\n```\ncode\n```\n\n```json\n{"a":1}\n```\n'
    with pytest.raises(InvalidTsaArtifact, match="fence"):
        extract_artifact_payload(text)


def test_architecture_refuses_two_complete_json_envelopes():
    first = json.dumps(architecture_artifact())
    second = json.dumps(architecture_artifact())
    text = (
        f"# A\n\nProse.\n\n```json\n{first}\n```\n\nMore.\n\n```json\n{second}\n```\n"
    )
    with pytest.raises(InvalidTsaArtifact, match="2 ```json fences"):
        extract_architecture_envelope(text)


def test_architecture_refuses_an_earlier_envelope_the_prefix_would_swallow():
    text = '```json\n{"hidden":1}\n```\n\n# A\n\nProse.\n\n```json\n{"a":1}\n```\n'
    with pytest.raises(InvalidTsaArtifact, match="2 ```json fences"):
        extract_architecture_envelope(text)


def test_architecture_allows_an_illustrative_diagram_fence_in_the_prose():
    """9.1 permits illustrative diagrams, so a non-JSON fence is not a defect."""
    artifact = architecture_artifact(**applied_group())
    text = (
        "# Architecture\n\n## 3. Solution Structure\n\n"
        "```text\nA --> B\n```\n\nProse.\n\n"
        f"```json\n{json.dumps(artifact)}\n```\n"
    )
    assert validate_artifact(extract_architecture_envelope(text)).cycle_id == CYCLE_ID


def test_architecture_refuses_an_envelope_that_does_not_end_the_document():
    artifact = architecture_artifact()
    text = f"# A\n\nProse.\n\n```json\n{json.dumps(artifact)}\n```\n\n## Appendix\n"
    with pytest.raises(InvalidTsaArtifact, match="content after the closing fence"):
        extract_architecture_envelope(text)


def test_architecture_refuses_a_document_that_is_only_an_envelope():
    text = '```json\n{"a":1}\n```\n'
    with pytest.raises(InvalidTsaArtifact, match="carries none"):
        extract_architecture_envelope(text)


def test_unclosed_fence_is_refused_for_both_carriers():
    text = '# T\n\nProse.\n\n```json\n{"a":1}\n'
    for reader in (extract_artifact_payload, extract_architecture_envelope):
        with pytest.raises(InvalidTsaArtifact, match="never closed"):
            reader(text)


# ==========================================================================
# M4 — decoder and producer failures become controlled refusals
# ==========================================================================


def test_huge_integer_inside_a_carrier_is_controlled():
    text = '# T\n\nProse.\n\n```json\n{"n": ' + ("1" * 5001) + "}\n```\n"
    with pytest.raises(InvalidTsaArtifact, match="the decoder refuses"):
        extract_artifact_payload(text)


def test_huge_integer_through_direct_validation_is_controlled():
    with pytest.raises(InvalidTsaArtifact, match="too wide to serialize"):
        canonical_json({"n": 10**5000})


def test_lone_surrogate_inside_a_persisted_tree_manifest_is_controlled():
    payload = TreeManifest(
        requirement_id="SDLC-FR-0001",
        root_document_id="root",
        entries=(TreeEntry("root", None, "ok", DIGEST_A),),
    ).to_payload()
    payload["documents"][0]["name"] = "bad \ud800 name"
    with pytest.raises(InvalidTsaArtifact, match="not encodable as"):
        validate_reused_tree_manifest(payload)


def test_lone_surrogate_in_a_manifest_body_is_controlled():
    body = spec_manifest_body()
    body["requirements"][0]["tree_manifest"]["documents"][0]["name"] = "\ud800"
    with pytest.raises(InvalidTsaArtifact, match="not encodable as|normative tree"):
        validate_manifest_body(body)


def test_ordinary_malformed_tree_manifest_is_still_controlled():
    payload = spec_tree_manifest_payload()
    payload["normative_tree_fingerprint"] = DIGEST_C
    with pytest.raises(InvalidTsaArtifact, match="normative tree manifest"):
        validate_reused_tree_manifest(payload)


def test_the_decomposed_unicode_manifest_still_validates():
    manifest = validate_reused_tree_manifest(spec_tree_manifest_payload())
    assert manifest.fingerprint == SPEC_TREE_FINGERPRINT


def test_duplicate_key_refusal_survives_the_decoder_wrapper():
    """The hook's controlled error must not be rewrapped as a decode failure."""
    text = '# T\n\nProse.\n\n```json\n{"a": 1, "a": 2}\n```\n'
    with pytest.raises(InvalidTsaArtifact, match="more than once"):
        extract_artifact_payload(text)
