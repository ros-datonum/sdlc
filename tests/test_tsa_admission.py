"""I05 — Requirement and UX admission, the Input Manifest and its acceptance.

Driven entirely by in-memory workspaces. Requirement evidence is the real
Process and Review Results the frozen chain writes, read back through the real
parsers; nothing here stubs "evidence valid". Nothing calls live Fibery or a
model, so every claim below is D-class only.
"""

from __future__ import annotations

import inspect
import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime

import pytest

from apply_fake import (
    build_apply_workspace,
    process_result_nodes,
    review_result_nodes,
    rewrite_payload,
)
from architecture_fake import OTHER_DATABASE_TYPE_ID, PROJECT_TYPE_ID
from legacy_evidence import LEGACY_PROCESS_RESULT_0_2, LEGACY_REVIEW_RESULT_0_2
from processor_fake import FakeProcessorWorkspace
from review_fake import add_process_iteration, tree_bound_process_result, tree_manifest
from sdlc import tsa_admission
from sdlc.fibery_workspace import (
    DocumentNode,
    FiberyError,
    ProjectRecord,
    RequirementRecord,
)
from sdlc.normative_tree import document_fingerprint, read_normative_tree
from sdlc.process_result import process_result_name, render_process_result
from sdlc.requirement_apply import apply_standard_requirement
from sdlc.review_result import (
    build_review_result,
    render_review_result,
    review_result_name,
)
from sdlc.standard_analysis import AnalysisResult, NormalizedRequirement
from sdlc.standard_review import ReviewOutput
from sdlc.tsa_admission import (
    MANIFEST_CREATE_ATTEMPTS,
    MANIFEST_PROSE,
    SELECTION_LIMIT,
    AdmissionRefused,
    AdmissionResultCode,
    RequirementEvidenceWorkspace,
    StartInputs,
    UxApplicable,
    UxNotApplicable,
    normalize_selection,
    start_input_manifest,
)
from sdlc.tsa_artifacts import (
    INPUT_MANIFEST,
    TsaArtifact,
    extract_artifact_payload,
    manifest_digest,
    requirement_input_digest,
    sealed_artifact,
    start_input_digest,
    validate_artifact,
)
from sdlc.tsa_cycle import (
    BootstrapContext,
    CycleOutcome,
    CycleResultCode,
    build_bootstrap_artifact,
    discover_cycle,
    render_bootstrap_carrier,
)
from standard_fake import REQUIREMENT_ID, normalized
from test_tsa_artifacts import (
    SPEC_START_DIGEST_APPLICABLE,
    SPEC_START_DIGEST_NOT_APPLICABLE,
)
from test_tsa_cycle import WORKSPACE, ScriptedWorkspace, fixed_clock

PROJECT_ID = "p-1"
PUBLIC_ID = "7"
PROJECT_CODE = "SDLC"
CYCLE = "arch-2026-09-a"
SECOND_ID = "SDLC-FR-0040"
SECOND_ENTITY = "std-uuid-40"
READY_ID = "SDLC-FR-0002"
RAW_ID = "SDLC-RAW-0007"
UX_DOCUMENT_ID = "ux-doc-1"
UX_CONTENT = "# Checkout flow\n\nThe user confirms the order on one screen.\n"
UX_REASON = "No user-facing surface."
CREATED_AT = "2026-10-10T12:00:00Z"

CONTEXT = BootstrapContext(
    workspace_identity=WORKSPACE,
    project_type_id=PROJECT_TYPE_ID,
    project_entity_id=PROJECT_ID,
    project_public_id=PUBLIC_ID,
    project_code=PROJECT_CODE,
    cycle_id=CYCLE,
)
ARCHITECTURE_ID = CONTEXT.architecture_document_id
MANIFEST_ID = CONTEXT.input_manifest_document_id

NOT_APPLICABLE = UxNotApplicable(UX_REASON)
APPLICABLE = UxApplicable(UX_DOCUMENT_ID, (REQUIREMENT_ID,))


class TsaWorkspace(ScriptedWorkspace):
    """The I04 scripted fake, with the two calls I05 adds logged and scriptable."""

    def __init__(self) -> None:
        super().__init__(
            ProjectRecord(
                id=PROJECT_ID,
                name="SDLC",
                code=PROJECT_CODE,
                state="Planned",
                public_id=PUBLIC_ID,
            )
        )

    def create_tsa_child_document(self, document_id, name, parent_document_id):
        parent = super()
        return self._run(
            "create_tsa_child_document",
            document_id,
            lambda: parent.create_tsa_child_document(
                document_id, name, parent_document_id
            ),
        )

    def resolve_document(self, document_id):
        parent = super()
        return self._run(
            "resolve_document",
            document_id,
            lambda: parent.resolve_document(document_id),
        )

    def seed_ux(self, content: str = UX_CONTENT, document_id=UX_DOCUMENT_ID) -> None:
        """A UX Document outside the cycle: only its id and content matter."""
        self.place_foreign_document(
            document_id,
            container_entity_type=OTHER_DATABASE_TYPE_ID,
            container_entity_id="99",
        )
        self.set_content(document_id, content)


@dataclass
class World:
    """Both sides of one `start`: the TSA workspace and the Requirement one."""

    tsa: TsaWorkspace
    req: FakeProcessorWorkspace

    @property
    def root(self) -> DocumentNode:
        return next(d for d in self.req.documents if d.id == "std-doc-1")


def applied_requirements() -> FakeProcessorWorkspace:
    """One Standard Requirement carried to Applied by the real frozen chain."""
    ws, requirement, _, _ = build_apply_workspace()
    applied = apply_standard_requirement(ws, requirement.id)
    assert applied.code.value == "REQUIREMENT_APPLIED", applied
    ws.calls.clear()
    return ws


def bootstrap_carrier() -> str:
    return render_bootstrap_carrier(
        CONTEXT, build_bootstrap_artifact(CONTEXT, CREATED_AT)
    )


def world(architecture: str = "bootstrapped") -> World:
    tsa = TsaWorkspace()
    if architecture == "bootstrapped":
        tsa.seed_root(ARCHITECTURE_ID, bootstrap_carrier())
    elif architecture == "empty shell":
        tsa.seed_root(ARCHITECTURE_ID)
    else:
        assert architecture == "absent"
    tsa.seed_ux()
    return World(tsa=tsa, req=applied_requirements())


ARCHITECTURES = ("absent", "empty shell", "bootstrapped")


def add_applied_requirement(
    ws: FakeProcessorWorkspace,
    requirement_id: str = SECOND_ID,
    entity_id: str = SECOND_ENTITY,
    public_id: str = "40",
    project_id: str = PROJECT_ID,
) -> RequirementRecord:
    """A second Applied Requirement whose evidence the real builders wrote."""
    record = RequirementRecord(
        id=entity_id,
        public_id=public_id,
        requirement_id=requirement_id,
        title="Second requirement",
        type_name="Standard",
        state="Applied",
        revision=1,
        project_id=project_id,
        source_fingerprint=None,
    )
    ws.requirements[entity_id] = record
    content = NormalizedRequirement(**normalized(title="Second requirement"))
    root = DocumentNode(
        id=f"root-{public_id}",
        name=f"{requirement_id} — Second requirement",
        folder_id=None,
        entity_public_id=public_id,
        secret=f"root-secret-{public_id}",
    )
    ws.documents.append(root)
    ws.content[root.secret] = content.document(requirement_id)
    process = tree_bound_process_result(
        ws,
        root,
        iteration=1,
        analysis=AnalysisResult(content, {"clarity": "adequate"}, (), ()),
        requirement_id=requirement_id,
    )
    _add_child(ws, root, process_result_name(requirement_id, 1), public_id, "process")
    ws.content[f"process-secret-{public_id}"] = render_process_result(process)
    reviewed = tree_manifest(ws, root, requirement_id)
    review = build_review_result(
        requirement_id,
        1,
        reviewed.root_entry.content_fingerprint,
        1,
        process.output_fingerprint,
        ReviewOutput((), (), (), {"clarity": "adequate"}),
        reviewed,
        reviewed_product_questions=process.product_questions,
    )
    _add_child(ws, root, review_result_name(requirement_id, 1), public_id, "review")
    ws.content[f"review-secret-{public_id}"] = render_review_result(review)
    return record


def _add_child(ws, root, name, public_id, kind, content="") -> DocumentNode:
    node = DocumentNode(
        id=f"{kind}-doc-{public_id}",
        name=name,
        folder_id=None,
        entity_public_id=None,
        secret=f"{kind}-secret-{public_id}",
        parent_document_id=root.id,
    )
    ws.documents.append(node)
    ws.content[node.secret] = content
    return node


def start_inputs(**changes) -> StartInputs:
    base = {
        "requirement_ids": (REQUIREMENT_ID,),
        "ux": NOT_APPLICABLE,
        "accept_inputs": True,
        "accept_ux": True,
    }
    return StartInputs(**{**base, **changes})


def start(scene: World, *, clock=fixed_clock, cycle=CYCLE, **changes):
    return start_input_manifest(
        scene.tsa, scene.req, PROJECT_ID, cycle, start_inputs(**changes), clock=clock
    )


def refusal(scene: World, **changes) -> AdmissionRefused:
    """A refusal that wrote no Requirement, whatever else it did."""
    before = list(scene.req.mutations)
    with pytest.raises(AdmissionRefused) as caught:
        start(scene, **changes)
    assert scene.req.mutations == before
    return caught.value


def clean_refusal(scene: World, **changes) -> AdmissionRefused:
    """A refusal that mutated nothing on either side."""
    before = list(scene.tsa.mutations)
    error = refusal(scene, **changes)
    assert scene.tsa.mutations == before
    assert scene.tsa.count("create_project_document") == 0
    assert scene.tsa.count("create_tsa_child_document") == 0
    assert scene.tsa.count("write_document_content") == 0
    return error


def manifest_payload(scene: World) -> dict:
    return extract_artifact_payload(scene.tsa.content_of(MANIFEST_ID))


def manifest_body(scene: World) -> dict:
    return manifest_payload(scene)["body"]["manifest_body"]


def accepted_manifest_carrier(**changes) -> str:
    """The carrier a successful `start` writes for these inputs, from scratch."""
    scene = world()
    start(scene, **changes)
    return scene.tsa.content_of(MANIFEST_ID)


def carrier_of(payload: dict) -> str:
    return f"# TSA {CYCLE} — Input Manifest\n\nProse.\n\n```json\n{json.dumps(payload)}\n```\n"


def fail(message: str = "connection reset"):
    def effect() -> None:
        raise FiberyError(message)

    return effect


def later_clock() -> datetime:
    return datetime(2027, 1, 2, 3, 4, 5, tzinfo=UTC)


# --------------------------------------------------------------------------
# Selection: normalisation, order, duplicates, size (spec 7.2, 12.1, 15)
# --------------------------------------------------------------------------


def test_selection_is_trimmed_upper_cased_and_sorted():
    assert normalize_selection([" sdlc-fr-0040 ", "SDLC-FR-0031"]) == (
        "SDLC-FR-0031",
        "SDLC-FR-0040",
    )


def test_an_empty_selection_is_refused_before_any_fibery_call():
    scene = world()
    error = clean_refusal(scene, requirement_ids=())
    assert error.code is AdmissionResultCode.SELECTION_EMPTY
    assert scene.tsa.calls == [] and scene.req.calls == []


@pytest.mark.parametrize(
    "selection",
    [
        (REQUIREMENT_ID, REQUIREMENT_ID),
        (REQUIREMENT_ID, f" {REQUIREMENT_ID} "),
        (REQUIREMENT_ID, REQUIREMENT_ID.lower()),
    ],
)
def test_a_duplicate_requirement_id_is_reported_not_collapsed(selection):
    scene = world()
    error = clean_refusal(scene, requirement_ids=selection)
    assert error.code is AdmissionResultCode.SELECTION_DUPLICATE
    assert scene.tsa.calls == [] and scene.req.calls == []


def test_two_requirement_ids_resolving_to_one_entity_are_a_duplicate(monkeypatch):
    """Unreachable through coherent evidence, so it is driven at the row level."""
    monkeypatch.setattr(
        tsa_admission,
        "_admit_requirement",
        lambda evidence, context, requirement_id: (
            {"requirement_id": requirement_id, "entity_id": "std-uuid-1"},
            frozenset(),
        ),
    )
    scene = world()
    error = clean_refusal(scene, requirement_ids=(REQUIREMENT_ID, SECOND_ID))
    assert error.code is AdmissionResultCode.SELECTION_DUPLICATE
    assert "std-uuid-1" in str(error)


def test_a_selection_over_the_limit_is_refused_never_truncated():
    scene = world()
    selection = tuple(f"SDLC-FR-{n:04d}" for n in range(SELECTION_LIMIT + 1))
    error = clean_refusal(scene, requirement_ids=selection)
    assert error.code is AdmissionResultCode.INPUT_TOO_LARGE
    assert scene.tsa.calls == []


def test_a_selection_at_the_limit_is_not_refused_for_its_size():
    selection = [f"SDLC-FR-{n:04d}" for n in range(SELECTION_LIMIT)]
    assert len(normalize_selection(selection)) == SELECTION_LIMIT


@pytest.mark.parametrize("blank", ["", "   ", None, 7])
def test_a_value_that_is_no_requirement_id_is_refused(blank):
    error = clean_refusal(world(), requirement_ids=(REQUIREMENT_ID, blank))
    assert error.code is AdmissionResultCode.REQUIREMENT_NOT_ADMISSIBLE


def test_argument_order_and_case_do_not_change_the_manifest():
    first, second = world(), world()
    for scene in (first, second):
        add_applied_requirement(scene.req)
    start(first, requirement_ids=(REQUIREMENT_ID, SECOND_ID))
    start(second, requirement_ids=(SECOND_ID.lower(), f" {REQUIREMENT_ID}"))
    assert manifest_payload(first) == manifest_payload(second)


# --------------------------------------------------------------------------
# Explicit acceptance (contract 3.3, 4; spec 12.1) — rows 2, 28, 46
# --------------------------------------------------------------------------


@pytest.mark.parametrize("architecture", ARCHITECTURES)
@pytest.mark.parametrize(
    "flags",
    [
        {"accept_inputs": False},
        {"accept_ux": False},
        {"accept_inputs": False, "accept_ux": False},
        {"accept_inputs": 1},
        {"accept_ux": "yes"},
        {"accept_inputs": None},
    ],
)
def test_missing_acceptance_is_refused_with_nothing_written(architecture, flags):
    scene = world(architecture)
    error = clean_refusal(scene, **flags)
    assert error.code is AdmissionResultCode.HUMAN_ACCEPTANCE_REQUIRED
    assert scene.tsa.calls == []


@pytest.mark.parametrize("ux", [APPLICABLE, NOT_APPLICABLE])
def test_an_unapproved_ux_is_refused_before_any_write(ux):
    error = clean_refusal(world("absent"), ux=ux, accept_ux=False)
    assert error.code is AdmissionResultCode.HUMAN_ACCEPTANCE_REQUIRED


def test_acceptance_is_not_inferred_from_an_applied_state():
    scene = world()
    assert scene.req.requirements["std-uuid-1"].state == "Applied"
    error = clean_refusal(scene, accept_inputs=False)
    assert error.code is AdmissionResultCode.HUMAN_ACCEPTANCE_REQUIRED


def hand_set_applied() -> World:
    """`Applied` written by hand: the Apply stage never ran for it."""
    ws, requirement, _, _ = build_apply_workspace()
    ws._replace(requirement.id, state="Applied")
    ws.calls.clear()
    scene = world()
    scene.req = ws
    return scene


def test_a_hand_set_applied_is_admitted_only_on_explicit_acceptance():
    error = clean_refusal(hand_set_applied(), accept_inputs=False)
    assert error.code is AdmissionResultCode.HUMAN_ACCEPTANCE_REQUIRED
    scene = hand_set_applied()
    result = start(scene)
    assert result.is_newly_written
    assert result.artifact.body["acceptance"]["accepted"] is True


def test_no_output_or_artifact_claims_a_historical_apply():
    scene = hand_set_applied()
    start(scene)
    carrier = scene.tsa.content_of(MANIFEST_ID)
    assert "not evidence of how any Requirement was applied" in MANIFEST_PROSE
    assert MANIFEST_PROSE in carrier
    payload = manifest_payload(scene)
    assert set(payload["body"]) == {"acceptance", "manifest_body", "manifest_digest"}
    assert set(payload["body"]["acceptance"]) == {
        "accepted",
        "manifest_digest",
        "recorded_at",
    }
    assert set(manifest_body(scene)["requirements"][0]) == {
        "entity_id",
        "process_result",
        "requirement_id",
        "review_result",
        "tree_fingerprint",
        "tree_manifest",
    }


# --------------------------------------------------------------------------
# Requirement admission: one negative per check (contract 2.1) — rows 4, 5, 27
# --------------------------------------------------------------------------


def unknown_requirement(scene: World) -> None:
    del scene.req.requirements["std-uuid-1"]


def ambiguous_requirement_id(scene: World) -> None:
    record = scene.req.requirements["std-uuid-1"]
    scene.req.requirements["std-uuid-twin"] = replace(record, id="std-uuid-twin")


def entity_reads_back_as_another(scene: World) -> None:
    record = scene.req.requirements["std-uuid-1"]
    scene.req.read_requirement = lambda entity_id: replace(
        record, requirement_id="SDLC-FR-9999"
    )


def entity_vanishes_on_read_back(scene: World) -> None:
    scene.req.read_requirement = lambda entity_id: None


def another_project(scene: World) -> None:
    record = scene.req.requirements["std-uuid-1"]
    scene.req.requirements["std-uuid-1"] = replace(record, project_id="p-2")


def raw_type(scene: World) -> None:
    record = scene.req.requirements["std-uuid-1"]
    scene.req.requirements["std-uuid-1"] = replace(record, type_name="Raw")


def no_root_document(scene: World) -> None:
    scene.req.documents = [d for d in scene.req.documents if d.id != "std-doc-1"]


def two_root_documents(scene: World) -> None:
    scene.req.documents.append(
        DocumentNode("extra-root", "Extra", None, "31", "extra-secret")
    )
    scene.req.content["extra-secret"] = "# Extra\n"


def foreign_artifact_under_the_root(scene: World) -> None:
    _add_child(scene.req, scene.root, "SDLC-FR-9999 — Process Result 0001", "x", "p")


def root_without_a_secret(scene: World) -> None:
    scene.req.documents = [
        replace(d, secret=None) if d.id == "std-doc-1" else d
        for d in scene.req.documents
    ]


def no_process_result(scene: World) -> None:
    gone = {node.id for node in process_result_nodes(scene.req)}
    scene.req.documents = [d for d in scene.req.documents if d.id not in gone]


def legacy_process_result(scene: World) -> None:
    node = process_result_nodes(scene.req)[0]
    scene.req.content[node.secret] = LEGACY_PROCESS_RESULT_0_2


def malformed_process_result(scene: World) -> None:
    node = process_result_nodes(scene.req)[0]
    scene.req.content[node.secret] = "# Heading\n\n```json\n{not json\n```\n"


def newer_empty_process_shell(scene: World) -> None:
    _add_child(
        scene.req, scene.root, process_result_name(REQUIREMENT_ID, 2), "s", "process"
    )


def duplicate_process_iteration(scene: World) -> None:
    node = process_result_nodes(scene.req)[0]
    _add_child(
        scene.req,
        scene.root,
        node.name,
        "dup",
        "process",
        scene.req.content[node.secret],
    )


def process_named_for_another_iteration(scene: World) -> None:
    rewrite_payload(scene.req, process_result_nodes(scene.req)[0], iteration=7)


def no_review_result(scene: World) -> None:
    gone = {node.id for node in review_result_nodes(scene.req)}
    scene.req.documents = [d for d in scene.req.documents if d.id not in gone]


def legacy_review_result(scene: World) -> None:
    node = review_result_nodes(scene.req)[0]
    scene.req.content[node.secret] = LEGACY_REVIEW_RESULT_0_2


def malformed_review_result(scene: World) -> None:
    node = review_result_nodes(scene.req)[0]
    scene.req.content[node.secret] = "human notes, no payload"


def newer_empty_review_shell(scene: World) -> None:
    _add_child(
        scene.req, scene.root, review_result_name(REQUIREMENT_ID, 2), "s", "review"
    )


def root_edited_after_review(scene: World) -> None:
    scene.req.content[scene.root.secret] += "\n\nAn unreviewed sentence.\n"


def child_added_after_review(scene: World) -> None:
    child = scene.req.create_child_document("Retry budget", scene.root.id)
    scene.req.content[child.secret] = "Three attempts.\n"


def process_ran_again_after_review(scene: World) -> None:
    add_process_iteration(scene.req, scene.root, iteration=2)


def review_of_another_process_output(scene: World) -> None:
    rewrite_payload(
        scene.req,
        review_result_nodes(scene.req)[0],
        reviewed_process_output_fingerprint="0" * 64,
    )


def review_of_another_process_iteration(scene: World) -> None:
    rewrite_payload(
        scene.req, review_result_nodes(scene.req)[0], reviewed_process_iteration=9
    )


INADMISSIBLE = {
    "1 identity: unknown Requirement ID": unknown_requirement,
    "1 identity: Requirement ID names two entities": ambiguous_requirement_id,
    "1 identity: entity reads back as another": entity_reads_back_as_another,
    "1 identity: entity vanishes on read-back": entity_vanishes_on_read_back,
    "2 project: another Project": another_project,
    "3 type: not Standard": raw_type,
    "5 tree: no Root Document": no_root_document,
    "5 tree: two Root Documents": two_root_documents,
    "5 tree: foreign artifact under the Root": foreign_artifact_under_the_root,
    "5 tree: Root exposes no content": root_without_a_secret,
    "6 process: none": no_process_result,
    "6 process: legacy 0.2 with manifest v1": legacy_process_result,
    "6 process: malformed": malformed_process_result,
    "6 process: newer empty shell, older not substituted": newer_empty_process_shell,
    "6 process: two for one iteration": duplicate_process_iteration,
    "6 process: payload names another iteration": process_named_for_another_iteration,
    "7 review: none": no_review_result,
    "7 review: legacy 0.2 with manifest v1": legacy_review_result,
    "7 review: malformed": malformed_review_result,
    "7 review: newer empty shell, older not substituted": newer_empty_review_shell,
    "8 bindings: Root edited after review": root_edited_after_review,
    "8 bindings: child added after review": child_added_after_review,
    "8 bindings: Process ran again after review": process_ran_again_after_review,
    "8 bindings: Review of another Process output": review_of_another_process_output,
    "8 bindings: Review of another Process iteration": (
        review_of_another_process_iteration
    ),
}


@pytest.mark.parametrize("architecture", ARCHITECTURES)
@pytest.mark.parametrize("label", sorted(INADMISSIBLE))
def test_each_failed_admission_check_refuses_with_nothing_written(architecture, label):
    scene = world(architecture)
    INADMISSIBLE[label](scene)
    error = clean_refusal(scene)
    assert error.code is AdmissionResultCode.REQUIREMENT_NOT_ADMISSIBLE, error
    assert scene.tsa.resolve_placement(MANIFEST_ID) is None


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (legacy_process_result, "latest Process Result 1 is version 0.2"),
        (legacy_review_result, "latest Review Result 1 is version 0.2"),
        (process_named_for_another_iteration, "describes 'SDLC-FR-0031' iteration 7"),
    ],
)
def test_legacy_or_misnamed_evidence_is_refused_for_what_it_is(mutate, reason):
    """The version check decides, not a later binding that happens to differ."""
    scene = world()
    mutate(scene)
    error = clean_refusal(scene)
    assert error.code is AdmissionResultCode.REQUIREMENT_NOT_ADMISSIBLE
    assert reason in str(error)


@pytest.mark.parametrize("state", ["Draft", "Process", "Review", "Ready", "Apply"])
def test_a_requirement_that_is_not_applied_is_refused(state):
    scene = world("absent")
    scene.req._replace("std-uuid-1", state=state)
    scene.req.mutations.clear()
    error = clean_refusal(scene)
    assert error.code is AdmissionResultCode.REQUIREMENT_NOT_ADMISSIBLE
    assert state in str(error)


@pytest.mark.parametrize("other", [READY_ID, RAW_ID])
def test_one_inadmissible_member_refuses_the_whole_selection(other):
    scene = world("absent")
    error = clean_refusal(scene, requirement_ids=(REQUIREMENT_ID, other))
    assert error.code is AdmissionResultCode.REQUIREMENT_NOT_ADMISSIBLE
    assert other in str(error)


def test_a_selection_spanning_two_projects_is_refused():
    scene = world("absent")
    add_applied_requirement(scene.req, project_id="p-2")
    error = clean_refusal(scene, requirement_ids=(REQUIREMENT_ID, SECOND_ID))
    assert error.code is AdmissionResultCode.REQUIREMENT_NOT_ADMISSIBLE
    assert "p-2" in str(error)


@pytest.mark.parametrize(
    "call",
    [
        "find_requirements_by_requirement_id",
        "read_requirement",
        "documents_attached_to_requirement",
        "child_documents",
        "read_document_content",
    ],
)
def test_a_failed_requirement_read_is_fibery_read_failed(call):
    scene = world("absent")
    scene.req.failures[call] = FiberyError("timeout")
    error = clean_refusal(scene)
    assert error.code is CycleResultCode.FIBERY_READ_FAILED


def test_inadmissible_evidence_is_never_backfilled_or_reprocessed():
    scene = world()
    legacy_process_result(scene)
    documents = list(scene.req.documents)
    content = dict(scene.req.content)
    clean_refusal(scene)
    assert scene.req.documents == documents and scene.req.content == content
    writes = {"write_document_content", "create_child_document"}
    assert not writes & set(scene.req.calls)


def test_the_evidence_protocol_offers_no_write_and_the_module_no_model():
    methods = {
        name
        for name, member in vars(RequirementEvidenceWorkspace).items()
        if callable(member) and not name.startswith("_")
    }
    assert methods == {
        "child_documents",
        "documents_attached_to_requirement",
        "find_requirements_by_requirement_id",
        "read_document_content",
        "read_requirement",
        "requirement_relations",
    }
    source = inspect.getsource(tsa_admission)
    assert "model_runtime" not in source and "set_requirement" not in source


# --------------------------------------------------------------------------
# The Input Manifest: content, two digest layers, one atomic artifact (spec 7)
# --------------------------------------------------------------------------


def test_start_in_state_b_writes_one_accepted_manifest():
    scene = world()
    result = start(scene)
    assert result.is_newly_written
    assert result.artifact.artifact_type == INPUT_MANIFEST
    assert scene.tsa.mutations == [
        f"create:{MANIFEST_ID}",
        f"write:{scene.tsa.documents[MANIFEST_ID].secret}",
    ]
    assert discover_cycle(scene.tsa, PROJECT_ID, CYCLE).outcome is CycleOutcome.D


def test_the_manifest_is_a_child_of_the_architecture_at_its_derived_id():
    scene = world()
    start(scene)
    stored = scene.tsa.documents[MANIFEST_ID]
    assert stored.parent_document_id == ARCHITECTURE_ID
    assert stored.name == f"TSA {CYCLE} — Input Manifest"
    assert ("create_tsa_child_document", MANIFEST_ID) in scene.tsa.log


def test_the_manifest_body_records_the_trusted_context():
    scene = world()
    start(scene)
    body = manifest_body(scene)
    assert body["workspace_identity"] == WORKSPACE
    assert body["project_entity_id"] == PROJECT_ID
    assert body["project_code"] == PROJECT_CODE
    assert body["cycle_id"] == CYCLE
    assert body["created_at"] == CREATED_AT


def test_the_requirement_row_is_the_evidence_actually_read():
    scene = world()
    start(scene)
    row = manifest_body(scene)["requirements"][0]
    record = scene.req.requirements["std-uuid-1"]
    tree = read_normative_tree(scene.req, record, scene.root).manifest
    process, review = (
        process_result_nodes(scene.req)[0],
        review_result_nodes(scene.req)[0],
    )
    assert row["requirement_id"] == REQUIREMENT_ID and row["entity_id"] == "std-uuid-1"
    assert row["tree_manifest"] == tree.to_payload()
    assert row["tree_manifest"]["normative_tree_version"] == 2
    assert row["tree_fingerprint"] == tree.root_entry.content_fingerprint
    assert row["process_result"] == {
        "document_id": process.id,
        "iteration": 1,
        "payload_digest": document_fingerprint(
            scene.req.read_document_content(process.secret)
        ),
    }
    assert row["review_result"] == {
        "document_id": review.id,
        "payload_digest": document_fingerprint(
            scene.req.read_document_content(review.secret)
        ),
    }


def test_only_the_selected_ids_enter_the_manifest():
    scene = world()
    add_applied_requirement(scene.req)
    start(scene)
    assert [r["requirement_id"] for r in manifest_body(scene)["requirements"]] == [
        REQUIREMENT_ID
    ]
    carrier = scene.tsa.content_of(MANIFEST_ID)
    assert SECOND_ID not in carrier and READY_ID not in carrier


def test_every_selected_id_enters_the_manifest_in_ascending_order():
    scene = world()
    add_applied_requirement(scene.req)
    start(scene, requirement_ids=(SECOND_ID, REQUIREMENT_ID))
    rows = manifest_body(scene)["requirements"]
    assert [row["requirement_id"] for row in rows] == [REQUIREMENT_ID, SECOND_ID]
    assert [row["entity_id"] for row in rows] == ["std-uuid-1", SECOND_ENTITY]


def test_manifest_digest_covers_the_body_and_not_the_acceptance():
    scene = world()
    start(scene)
    body = manifest_payload(scene)["body"]
    assert body["manifest_digest"] == manifest_digest(body["manifest_body"])
    assert "acceptance" not in body["manifest_body"]
    assert body["acceptance"] == {
        "manifest_digest": body["manifest_digest"],
        "accepted": True,
        "recorded_at": CREATED_AT,
    }


def test_artifact_digest_covers_the_acceptance():
    scene = world()
    start(scene)
    payload = manifest_payload(scene)
    tampered = json.loads(json.dumps(payload))
    tampered["body"]["acceptance"]["recorded_at"] = "2030-01-01T00:00:00Z"
    assert (
        manifest_digest(tampered["body"]["manifest_body"])
        == (payload["body"]["manifest_digest"])
    )
    with pytest.raises(ValueError, match="artifact_digest"):
        validate_artifact(tampered)


@pytest.mark.parametrize(
    "tamper",
    [
        lambda body: body["manifest_body"].__setitem__("project_code", "OTHER"),
        lambda body: body["manifest_body"]["requirements"][0].__setitem__(
            "entity_id", "another-entity"
        ),
        lambda body: body["manifest_body"]["ux"].__setitem__("reason", "Changed."),
    ],
)
def test_a_tampered_manifest_body_no_longer_matches_its_digest(tamper):
    scene = world()
    start(scene)
    payload = manifest_payload(scene)
    tamper(payload["body"])
    with pytest.raises(ValueError):
        validate_artifact(payload)


def test_manifest_and_acceptance_are_one_write_never_two():
    scene = world()
    start(scene)
    secret = scene.tsa.documents[MANIFEST_ID].secret
    writes = [entry for entry in scene.tsa.log if entry[0] == "write_document_content"]
    assert writes == [("write_document_content", secret)]
    assert len(scene.tsa.written) == 1
    written = extract_artifact_payload(scene.tsa.written[0])
    assert written["body"]["acceptance"]["accepted"] is True


def test_one_start_reads_the_clock_once_for_every_manifest_timestamp():
    scene = world()
    reads = []

    def counting_clock() -> datetime:
        reads.append(1)
        return fixed_clock()

    start(scene, ux=APPLICABLE, clock=counting_clock)
    body = manifest_payload(scene)["body"]
    assert len(reads) == 1
    assert {
        body["manifest_body"]["created_at"],
        body["manifest_body"]["ux"]["approval"]["recorded_at"],
        body["acceptance"]["recorded_at"],
    } == {CREATED_AT}


def test_the_read_back_accepts_fibery_dropping_the_final_newline():
    scene = world()
    scene.tsa.store_as = lambda markdown: markdown.rstrip("\n")
    assert start(scene).is_newly_written


def test_the_returned_artifact_is_the_one_read_back():
    scene = world()
    result = start(scene)
    assert result.artifact == validate_artifact(manifest_payload(scene))
    assert result.context == CONTEXT


@pytest.mark.parametrize("architecture", ["absent", "empty shell"])
def test_start_bootstraps_the_architecture_then_writes_the_manifest(architecture):
    scene = world(architecture)
    result = start(scene)
    assert result.is_newly_written
    architecture_secret = scene.tsa.documents[ARCHITECTURE_ID].secret
    expected = [
        f"write:{architecture_secret}",
        f"create:{MANIFEST_ID}",
        f"write:{scene.tsa.documents[MANIFEST_ID].secret}",
    ]
    if architecture == "absent":
        expected.insert(0, f"create:{ARCHITECTURE_ID}")
    assert scene.tsa.mutations == expected
    assert discover_cycle(scene.tsa, PROJECT_ID, CYCLE).outcome is CycleOutcome.D


def test_admission_completes_before_the_first_bootstrap_mutation():
    scene = world("absent")
    reads_before_create = []
    scene.tsa.before(
        "create_project_document",
        1,
        lambda: reads_before_create.append(scene.req.calls.count("read_requirement")),
    )
    start(scene)
    assert reads_before_create == [1]


def requirement_reads_at(scene: World, call: str) -> list[int]:
    """How many times the Requirement had been read when `call` first ran."""
    reads: list[int] = []
    scene.tsa.before(
        call, 1, lambda: reads.append(scene.req.calls.count("read_requirement"))
    )
    return reads


def test_admission_is_repeated_after_the_bootstrap_mutation():
    scene = world("absent")
    reads_before_create = requirement_reads_at(scene, "create_tsa_child_document")
    start(scene)
    assert reads_before_create == [2]


def test_state_b_admits_once_then_runs_the_gate_immediately_before_the_create():
    scene = world()
    reads_before_create = requirement_reads_at(scene, "create_tsa_child_document")
    start(scene)
    assert reads_before_create == [1]
    calls = [name for name, _ in scene.tsa.log]
    create = calls.index("create_tsa_child_document")
    assert calls[create - 1] == "resolve_placement"
    assert "write_document_content" not in calls[:create]


# --------------------------------------------------------------------------
# UX admission (contract 4, spec 7.3) — rows 2, 3, 29, 37, 38
# --------------------------------------------------------------------------


def test_applicable_binds_the_document_id_digest_scope_and_approval():
    scene = world()
    start(scene, ux=APPLICABLE)
    assert manifest_body(scene)["ux"] == {
        "kind": "APPLICABLE",
        "document_id": UX_DOCUMENT_ID,
        "content_digest": document_fingerprint(UX_CONTENT),
        "scope_requirement_ids": [REQUIREMENT_ID],
        "approval": {"accepted": True, "recorded_at": CREATED_AT},
    }


def test_applicable_scope_is_a_sorted_subset_of_the_selection():
    scene = world()
    add_applied_requirement(scene.req)
    start(
        scene,
        requirement_ids=(REQUIREMENT_ID, SECOND_ID),
        ux=UxApplicable(UX_DOCUMENT_ID, (SECOND_ID.lower(), REQUIREMENT_ID)),
    )
    assert manifest_body(scene)["ux"]["scope_requirement_ids"] == [
        REQUIREMENT_ID,
        SECOND_ID,
    ]


def ux_document_missing(scene: World) -> None:
    del scene.tsa.documents[UX_DOCUMENT_ID]


def ux_document_unresolvable(scene: World) -> None:
    scene.tsa.before("resolve_document", 1, fail("query failed"))


def ux_document_unreadable(scene: World) -> None:
    secret = scene.tsa.documents[UX_DOCUMENT_ID].secret
    del scene.tsa.content[secret]


def ux_document_without_a_secret(scene: World) -> None:
    scene.tsa.documents[UX_DOCUMENT_ID].secret = None


def ux_document_empty(scene: World) -> None:
    scene.tsa.set_content(UX_DOCUMENT_ID, " \n")


UX_INVALID = {
    "missing or deleted": ux_document_missing,
    "cannot be resolved": ux_document_unresolvable,
    "content unreadable": ux_document_unreadable,
    "no content secret": ux_document_without_a_secret,
    "no content": ux_document_empty,
}


@pytest.mark.parametrize("architecture", ARCHITECTURES)
@pytest.mark.parametrize("label", sorted(UX_INVALID))
def test_unusable_applicable_evidence_is_refused_before_any_write(architecture, label):
    scene = world(architecture)
    UX_INVALID[label](scene)
    error = clean_refusal(scene, ux=APPLICABLE)
    assert error.code is AdmissionResultCode.UX_EVIDENCE_INVALID


@pytest.mark.parametrize(
    "reference",
    ["Checkout flow", "https://example.fibery.io/ux/Checkout-flow-12", "v3"],
)
def test_a_name_url_or_version_label_is_not_ux_identity(reference):
    scene = world()
    scene.tsa.documents[UX_DOCUMENT_ID].name = reference
    error = clean_refusal(scene, ux=UxApplicable(reference, (REQUIREMENT_ID,)))
    assert error.code is AdmissionResultCode.UX_EVIDENCE_INVALID


def test_a_scope_outside_the_selection_is_ux_scope_foreign():
    scene = world("absent")
    add_applied_requirement(scene.req)
    error = clean_refusal(scene, ux=UxApplicable(UX_DOCUMENT_ID, (SECOND_ID,)))
    assert error.code is AdmissionResultCode.UX_SCOPE_FOREIGN
    assert scene.tsa.calls == []


@pytest.mark.parametrize("scope", [(), (REQUIREMENT_ID, REQUIREMENT_ID.lower()), None])
def test_an_empty_or_repeated_scope_is_refused(scope):
    error = clean_refusal(world(), ux=UxApplicable(UX_DOCUMENT_ID, scope))
    assert error.code is AdmissionResultCode.UX_EVIDENCE_INVALID


@pytest.mark.parametrize("architecture", ["absent", "empty shell"])
def test_ux_content_replaced_during_the_command_is_a_digest_mismatch(architecture):
    scene = world(architecture)
    scene.tsa.after(
        "write_document_content",
        1,
        lambda: scene.tsa.set_content(UX_DOCUMENT_ID, "# Another document\n"),
    )
    error = refusal(scene, ux=APPLICABLE)
    assert error.code is AdmissionResultCode.UX_EVIDENCE_INVALID
    assert scene.tsa.resolve_placement(MANIFEST_ID) is None
    assert scene.tsa.count("create_tsa_child_document") == 0


def test_ux_document_deleted_during_the_command_is_refused():
    scene = world("absent")
    scene.tsa.after("write_document_content", 1, lambda: ux_document_missing(scene))
    error = refusal(scene, ux=APPLICABLE)
    assert error.code is AdmissionResultCode.UX_EVIDENCE_INVALID
    assert scene.tsa.count("create_tsa_child_document") == 0


def test_not_applicable_records_the_decision_reason_and_input_binding():
    scene = world()
    start(scene)
    body = manifest_body(scene)
    assert body["ux"] == {
        "kind": "NOT_APPLICABLE",
        "reason": UX_REASON,
        "requirement_input_digest": requirement_input_digest(body["requirements"]),
        "decision": {"accepted": True, "recorded_at": CREATED_AT},
    }
    assert {"document_id", "content_digest", "scope_requirement_ids"}.isdisjoint(
        body["ux"]
    )


@pytest.mark.parametrize("architecture", ARCHITECTURES)
def test_not_applicable_reads_no_ux_document_and_needs_none(architecture):
    scene = world(architecture)
    del scene.tsa.documents[UX_DOCUMENT_ID]
    assert start(scene).is_newly_written
    assert scene.tsa.count("resolve_document") == 0
    assert discover_cycle(scene.tsa, PROJECT_ID, CYCLE).outcome is CycleOutcome.D


@pytest.mark.parametrize("reason", ["", "  \n", None])
def test_not_applicable_without_a_reason_is_refused(reason):
    error = clean_refusal(world(), ux=UxNotApplicable(reason))
    assert error.code is AdmissionResultCode.UX_EVIDENCE_INVALID


MODEL_AUTHORED_UX = [
    {
        "kind": "NOT_APPLICABLE",
        "reason": "The system has no user interface.",
        "requirement_input_digest": "a" * 64,
        "decision": {"accepted": True, "recorded_at": CREATED_AT},
    },
    {
        "kind": "APPLICABLE",
        "document_id": UX_DOCUMENT_ID,
        "content_digest": "b" * 64,
        "scope_requirement_ids": [REQUIREMENT_ID],
        "approval": {"accepted": True, "recorded_at": CREATED_AT},
    },
    json.dumps({"kind": "NOT_APPLICABLE", "reason": "No UI."}),
    "NOT_APPLICABLE",
    None,
]


@pytest.mark.parametrize("authored", MODEL_AUTHORED_UX)
@pytest.mark.parametrize("accept_ux", [True, False])
def test_a_ux_value_not_given_as_caller_input_is_never_recorded(authored, accept_ux):
    scene = world("absent")
    error = clean_refusal(scene, ux=authored, accept_ux=accept_ux)
    assert error.code in (
        AdmissionResultCode.UX_EVIDENCE_INVALID,
        AdmissionResultCode.HUMAN_ACCEPTANCE_REQUIRED,
    )
    assert (error.code is AdmissionResultCode.HUMAN_ACCEPTANCE_REQUIRED) == (
        not accept_ux
    )


def test_the_recorded_ux_acceptance_is_the_callers_flag_and_nothing_else():
    scene = world()
    start(scene, ux=APPLICABLE)
    approval = manifest_body(scene)["ux"]["approval"]
    assert approval == {"accepted": True, "recorded_at": CREATED_AT}


# --------------------------------------------------------------------------
# Repeated start (spec 13.7-2) — row 12
# --------------------------------------------------------------------------


def persisted_artifact(ux: dict) -> tuple[BootstrapContext, TsaArtifact]:
    project = "11111111-2222-3333-4444-555555555555"
    context = replace(CONTEXT, project_entity_id=project, cycle_id="tsa-2026-001")
    body = {
        "manifest_body": {
            "created_at": "2026-09-29T18:00:00Z",
            "requirements": [
                {"requirement_id": "SDLC-FR-0001"},
                {"requirement_id": "SDLC-NFR-0002"},
            ],
            "ux": ux,
        },
        "acceptance": {"accepted": True, "recorded_at": "2026-09-29T18:00:00Z"},
    }
    artifact = TsaArtifact(
        INPUT_MANIFEST,
        1,
        WORKSPACE,
        project,
        PROJECT_CODE,
        "tsa-2026-001",
        None,
        body,
        "",
    )
    return context, artifact


def test_persisted_projection_reproduces_vector_s1():
    context, artifact = persisted_artifact(
        {
            "kind": "APPLICABLE",
            "document_id": "doc-ux-1",
            "content_digest": "b" * 64,
            "scope_requirement_ids": ["SDLC-FR-0001"],
            "approval": {"accepted": True, "recorded_at": "2026-09-29T18:00:00Z"},
        }
    )
    projection = tsa_admission._persisted_projection(context, artifact)
    assert start_input_digest(projection) == SPEC_START_DIGEST_APPLICABLE


def test_persisted_projection_reproduces_vector_s2():
    context, artifact = persisted_artifact(
        {
            "kind": "NOT_APPLICABLE",
            "reason": "No user-facing surface",
            "requirement_input_digest": "c" * 64,
            "decision": {"accepted": True, "recorded_at": "2031-01-01T00:00:00Z"},
        }
    )
    projection = tsa_admission._persisted_projection(context, artifact)
    assert start_input_digest(projection) == SPEC_START_DIGEST_NOT_APPLICABLE


def test_no_timestamp_or_generated_value_enters_the_projection():
    context, artifact = persisted_artifact(
        {
            "kind": "NOT_APPLICABLE",
            "reason": "No user-facing surface",
            "requirement_input_digest": "c" * 64,
            "decision": {"accepted": True, "recorded_at": "2031-01-01T00:00:00Z"},
        }
    )
    projection = tsa_admission._persisted_projection(context, artifact)
    assert set(projection) == {
        "accept_inputs",
        "accept_ux",
        "cycle_id",
        "project_entity_id",
        "requirement_ids",
        "ux",
    }
    assert projection["ux"] == {
        "kind": "NOT_APPLICABLE",
        "reason": "No user-facing surface",
    }


@pytest.mark.parametrize("ux", [APPLICABLE, NOT_APPLICABLE])
def test_the_same_inputs_at_a_later_time_reuse_the_manifest_unchanged(ux):
    scene = world()
    first = start(scene, ux=ux)
    stored = scene.tsa.content_of(MANIFEST_ID)
    mutations = list(scene.tsa.mutations)
    again = start(scene, ux=ux, clock=later_clock)
    assert not again.is_newly_written
    assert again.artifact == first.artifact
    assert scene.tsa.content_of(MANIFEST_ID) == stored
    assert scene.tsa.mutations == mutations
    assert manifest_body(scene)["created_at"] == CREATED_AT


def test_a_repeat_never_reads_the_clock():
    scene = world()
    start(scene)

    def forbidden_clock() -> datetime:
        raise AssertionError("a repeated start must not generate a timestamp")

    assert not start(scene, clock=forbidden_clock).is_newly_written


def test_a_repeat_in_another_argument_order_and_case_is_the_same_inputs():
    scene = world()
    add_applied_requirement(scene.req)
    start(scene, requirement_ids=(REQUIREMENT_ID, SECOND_ID))
    again = start(scene, requirement_ids=(SECOND_ID.lower(), f"{REQUIREMENT_ID} "))
    assert not again.is_newly_written


def test_a_not_applicable_repeat_reads_no_ux_document():
    scene = world()
    start(scene)
    start(scene)
    assert scene.tsa.count("resolve_document") == 0


def changed_selection() -> dict:
    return {"requirement_ids": (REQUIREMENT_ID, SECOND_ID)}


CONFLICTING_REPEATS = {
    "a Requirement added": (APPLICABLE, changed_selection()),
    "another Requirement": (NOT_APPLICABLE, {"requirement_ids": (SECOND_ID,)}),
    "another UX Document": (
        APPLICABLE,
        {"ux": UxApplicable("ux-doc-2", (REQUIREMENT_ID,))},
    ),
    "UX branch switched to not applicable": (APPLICABLE, {"ux": NOT_APPLICABLE}),
    "UX branch switched to applicable": (NOT_APPLICABLE, {"ux": APPLICABLE}),
    "another not-applicable reason": (
        NOT_APPLICABLE,
        {"ux": UxNotApplicable("A different reason.")},
    ),
}


@pytest.mark.parametrize("label", sorted(CONFLICTING_REPEATS))
def test_different_inputs_against_an_accepted_manifest_are_a_conflict(label):
    original, changes = CONFLICTING_REPEATS[label]
    scene = world()
    add_applied_requirement(scene.req)
    scene.tsa.seed_ux(document_id="ux-doc-2")
    start(scene, ux=original)
    stored = scene.tsa.content_of(MANIFEST_ID)
    mutations = list(scene.tsa.mutations)
    with pytest.raises(AdmissionRefused) as caught:
        start(scene, **{"ux": original, **changes})
    assert caught.value.code is AdmissionResultCode.MANIFEST_INPUTS_CONFLICT
    assert "new cycle id" in str(caught.value)
    assert scene.tsa.content_of(MANIFEST_ID) == stored
    assert scene.tsa.mutations == mutations


def test_a_wider_ux_scope_against_an_accepted_manifest_is_a_conflict():
    scene = world()
    add_applied_requirement(scene.req)
    selection = (REQUIREMENT_ID, SECOND_ID)
    start(scene, requirement_ids=selection, ux=APPLICABLE)
    mutations = list(scene.tsa.mutations)
    with pytest.raises(AdmissionRefused) as caught:
        start(
            scene,
            requirement_ids=selection,
            ux=UxApplicable(UX_DOCUMENT_ID, selection),
        )
    assert caught.value.code is AdmissionResultCode.MANIFEST_INPUTS_CONFLICT
    assert scene.tsa.mutations == mutations


def test_changed_ux_content_against_an_accepted_manifest_is_a_conflict():
    scene = world()
    start(scene, ux=APPLICABLE)
    scene.tsa.set_content(UX_DOCUMENT_ID, "# Rewritten\n\nAnother flow.\n")
    mutations = list(scene.tsa.mutations)
    with pytest.raises(AdmissionRefused) as caught:
        start(scene, ux=APPLICABLE)
    assert caught.value.code is AdmissionResultCode.MANIFEST_INPUTS_CONFLICT
    assert scene.tsa.mutations == mutations


def test_a_repeat_without_acceptance_is_still_refused():
    scene = world()
    start(scene)
    mutations = list(scene.tsa.mutations)
    with pytest.raises(AdmissionRefused) as caught:
        start(scene, accept_inputs=False)
    assert caught.value.code is AdmissionResultCode.HUMAN_ACCEPTANCE_REQUIRED
    assert scene.tsa.mutations == mutations


def test_an_accepted_manifest_is_never_written_twice():
    scene = world()
    start(scene)
    for _ in range(3):
        start(scene, clock=later_clock)
    assert scene.tsa.count("create_tsa_child_document") == 1
    assert scene.tsa.count("write_document_content") == 1


# --------------------------------------------------------------------------
# The I04 gate: E and D permit no bootstrap or Manifest mutation (contract 14.1.2)
# --------------------------------------------------------------------------


def manifest_missing_acceptance() -> str:
    payload = extract_artifact_payload(accepted_manifest_carrier())
    del payload["body"]["acceptance"]
    return carrier_of(payload)


def manifest_with_acceptance_mismatch() -> str:
    payload = extract_artifact_payload(accepted_manifest_carrier())
    payload["body"]["acceptance"]["manifest_digest"] = "0" * 64
    return carrier_of(payload)


def refusing_manifests() -> dict[str, tuple[str, CycleResultCode]]:
    return {
        "empty shell": ("", CycleResultCode.MANIFEST_SHELL_UNRECOVERABLE),
        "whitespace shell": (" \n", CycleResultCode.MANIFEST_SHELL_UNRECOVERABLE),
        "no fence": ("human notes", CycleResultCode.ARTIFACT_MALFORMED),
        "missing acceptance": (
            manifest_missing_acceptance(),
            CycleResultCode.ARTIFACT_MALFORMED,
        ),
        "acceptance bound to another digest": (
            manifest_with_acceptance_mismatch(),
            CycleResultCode.MANIFEST_ACCEPTANCE_MISMATCH,
        ),
    }


REFUSING_MANIFESTS = sorted(refusing_manifests())


@pytest.mark.parametrize("architecture", ["empty shell", "bootstrapped"])
@pytest.mark.parametrize("label", REFUSING_MANIFESTS)
def test_a_refusing_manifest_child_permits_no_write_at_all(architecture, label):
    content, code = refusing_manifests()[label]
    scene = world(architecture)
    scene.tsa.seed_child(MANIFEST_ID, ARCHITECTURE_ID, content)
    error = clean_refusal(scene)
    assert error.code is code
    assert scene.tsa.content_of(MANIFEST_ID) == content
    assert scene.req.calls.count("read_requirement") == 0


@pytest.mark.parametrize("label", [*REFUSING_MANIFESTS, "valid accepted"])
def test_a_manifest_document_without_an_architecture_creates_nothing(label):
    content = (
        accepted_manifest_carrier()
        if label == "valid accepted"
        else refusing_manifests()[label][0]
    )
    scene = world("absent")
    scene.tsa.seed_child(MANIFEST_ID, ARCHITECTURE_ID, content)
    error = clean_refusal(scene)
    assert error.code is CycleResultCode.CYCLE_FOREIGN_PROJECT


def test_an_accepted_manifest_over_an_empty_architecture_repairs_nothing():
    scene = world("empty shell")
    scene.tsa.seed_child(MANIFEST_ID, ARCHITECTURE_ID, accepted_manifest_carrier())
    result = start(scene)
    assert not result.is_newly_written
    assert scene.tsa.mutations == []
    assert scene.tsa.content_of(ARCHITECTURE_ID) == ""


def test_an_accepted_manifest_for_other_inputs_over_an_empty_architecture_conflicts():
    scene = world("empty shell")
    scene.tsa.seed_child(MANIFEST_ID, ARCHITECTURE_ID, accepted_manifest_carrier())
    error = clean_refusal(scene, ux=UxNotApplicable("Another reason."))
    assert error.code is AdmissionResultCode.MANIFEST_INPUTS_CONFLICT
    assert scene.tsa.content_of(ARCHITECTURE_ID) == ""


def test_a_manifest_outside_the_architecture_root_is_foreign():
    scene = world()
    scene.tsa.place_foreign_document(MANIFEST_ID, parent_document_id="elsewhere")
    scene.tsa.set_content(MANIFEST_ID, accepted_manifest_carrier())
    error = clean_refusal(scene)
    assert error.code is CycleResultCode.CYCLE_FOREIGN_PROJECT


def test_a_malformed_architecture_refuses_before_admission():
    scene = world("absent")
    scene.tsa.seed_root(ARCHITECTURE_ID, "human notes")
    error = clean_refusal(scene)
    assert error.code is CycleResultCode.ARTIFACT_MALFORMED
    assert scene.req.calls.count("read_requirement") == 0


def test_a_foreign_architecture_placement_refuses():
    scene = world("absent")
    scene.tsa.place_foreign_document(
        ARCHITECTURE_ID,
        container_entity_type=OTHER_DATABASE_TYPE_ID,
        container_entity_id=PUBLIC_ID,
    )
    assert clean_refusal(scene).code is CycleResultCode.CYCLE_FOREIGN_PROJECT


def test_an_invalid_cycle_id_is_refused_before_any_fibery_call():
    scene = world()
    with pytest.raises(AdmissionRefused) as caught:
        start(scene, cycle="x")
    assert caught.value.code is CycleResultCode.INVALID_CYCLE_ID
    assert scene.tsa.calls == []


def test_a_failed_bootstrap_carrier_write_leaves_no_manifest():
    scene = world("absent")
    scene.tsa.store_as = lambda markdown: ""
    error = refusal(scene)
    assert error.code is CycleResultCode.FIBERY_WRITE_FAILED
    assert scene.tsa.count("create_tsa_child_document") == 0


# --------------------------------------------------------------------------
# Unknown Manifest create outcome (spec 3.5): both levels, then classify
# --------------------------------------------------------------------------


def test_an_absent_child_after_an_unknown_create_is_retried_at_the_same_id():
    scene = world()
    scene.tsa.before("create_tsa_child_document", 1, fail())
    result = start(scene)
    assert result.is_newly_written
    creates = [e for e in scene.tsa.log if e[0] == "create_tsa_child_document"]
    assert creates == [("create_tsa_child_document", MANIFEST_ID)] * 2
    assert scene.tsa.mutations[0] == f"create:{MANIFEST_ID}"
    assert len(scene.tsa.written) == 1


def test_the_retry_follows_a_cycle_level_rediscovery_and_a_fresh_admission():
    scene = world()
    scene.tsa.before("create_tsa_child_document", 1, fail())
    start(scene)
    calls = [name for name, _ in scene.tsa.log]
    first, second = (
        index for index, name in enumerate(calls) if name == "create_tsa_child_document"
    )
    between = calls[first + 1 : second]
    assert "documents_attached_to_project" in between
    assert between.count("read_project") >= 2


def test_the_retried_create_is_preceded_by_a_fresh_admission():
    scene = world()
    reads_before_create: list[int] = []

    def note_reads() -> None:
        reads_before_create.append(scene.req.calls.count("read_requirement"))

    def note_reads_then_fail() -> None:
        note_reads()
        raise FiberyError("connection reset")

    scene.tsa.before("create_tsa_child_document", 1, note_reads_then_fail)
    scene.tsa.before("create_tsa_child_document", 2, note_reads)
    start(scene)
    assert reads_before_create == [1, 2]


def test_a_create_that_never_lands_stops_after_the_bounded_retry():
    scene = world()
    for occurrence in range(1, MANIFEST_CREATE_ATTEMPTS + 2):
        scene.tsa.before("create_tsa_child_document", occurrence, fail())
    error = refusal(scene)
    assert error.code is CycleResultCode.FIBERY_WRITE_FAILED
    assert scene.tsa.count("create_tsa_child_document") == MANIFEST_CREATE_ATTEMPTS
    assert scene.tsa.mutations == []
    assert discover_cycle(scene.tsa, PROJECT_ID, CYCLE).outcome is CycleOutcome.B


def test_evidence_that_moved_before_the_retry_refuses_it():
    scene = world()

    def fail_after_drift() -> None:
        root_edited_after_review(scene)
        raise FiberyError("connection reset")

    scene.tsa.before("create_tsa_child_document", 1, fail_after_drift)
    error = refusal(scene)
    assert error.code is AdmissionResultCode.REQUIREMENT_NOT_ADMISSIBLE
    assert scene.tsa.count("create_tsa_child_document") == 1
    assert scene.tsa.mutations == []


def test_an_unknown_create_that_landed_empty_is_an_unrecoverable_shell():
    scene = world()
    scene.tsa.after("create_tsa_child_document", 1, fail())
    error = refusal(scene)
    assert error.code is CycleResultCode.MANIFEST_SHELL_UNRECOVERABLE
    assert scene.tsa.count("create_tsa_child_document") == 1
    assert scene.tsa.count("write_document_content") == 0
    assert scene.tsa.content_of(MANIFEST_ID) == ""


def landed_with(scene: World, content: str):
    def effect() -> None:
        scene.tsa.set_content(MANIFEST_ID, content)
        raise FiberyError("connection reset")

    return effect


@pytest.mark.parametrize(
    "label", ["no fence", "missing acceptance", "acceptance bound to another digest"]
)
def test_an_unknown_create_that_landed_non_conforming_is_never_overwritten(label):
    content, code = refusing_manifests()[label]
    scene = world()
    scene.tsa.after("create_tsa_child_document", 1, landed_with(scene, content))
    error = refusal(scene)
    assert error.code is code
    assert scene.tsa.content_of(MANIFEST_ID) == content
    assert scene.tsa.count("write_document_content") == 0


def test_an_unknown_create_that_landed_valid_and_accepted_is_adopted():
    content = accepted_manifest_carrier()
    scene = world()
    scene.tsa.after("create_tsa_child_document", 1, landed_with(scene, content))
    result = start(scene, clock=later_clock)
    assert not result.is_newly_written
    assert scene.tsa.content_of(MANIFEST_ID) == content
    assert scene.tsa.count("write_document_content") == 0
    assert result.artifact.body["manifest_body"]["created_at"] == CREATED_AT


def test_an_adopted_manifest_for_other_inputs_is_a_conflict_not_a_rewrite():
    content = accepted_manifest_carrier(ux=UxNotApplicable("Another reason."))
    scene = world()
    scene.tsa.after("create_tsa_child_document", 1, landed_with(scene, content))
    error = refusal(scene)
    assert error.code is AdmissionResultCode.MANIFEST_INPUTS_CONFLICT
    assert scene.tsa.content_of(MANIFEST_ID) == content


def move_architecture_root(scene: World):
    def effect() -> None:
        scene.tsa.documents[ARCHITECTURE_ID].container_entity_id = "another-project"

    return effect


def reparent_manifest(scene: World):
    def effect() -> None:
        scene.tsa.documents[MANIFEST_ID].parent_document_id = "elsewhere"

    return effect


def test_an_unknown_create_revalidates_the_cycle_before_the_child():
    scene = world()

    def root_moves_then_fails() -> None:
        move_architecture_root(scene)()
        raise FiberyError("connection reset")

    scene.tsa.before("create_tsa_child_document", 1, root_moves_then_fails)
    error = refusal(scene)
    assert error.code is CycleResultCode.CYCLE_FOREIGN_PROJECT
    assert scene.tsa.count("create_tsa_child_document") == 1


# --------------------------------------------------------------------------
# The body write: fresh placement, unknown outcome, read-back (spec 14.1)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("drift", [move_architecture_root, reparent_manifest])
def test_placement_drift_after_the_create_refuses_the_body_write(drift):
    scene = world()
    scene.tsa.after("create_tsa_child_document", 1, drift(scene))
    error = refusal(scene)
    assert error.code is CycleResultCode.CYCLE_FOREIGN_PROJECT
    assert scene.tsa.count("write_document_content") == 0
    assert scene.tsa.content_of(MANIFEST_ID) == ""


def calls_from_create_to_write(scene: World) -> list[tuple[str, str]]:
    log = scene.tsa.log
    create = log.index(("create_tsa_child_document", MANIFEST_ID))
    write = next(i for i, e in enumerate(log) if e[0] == "write_document_content")
    return log[create + 1 : write]


@pytest.mark.parametrize("ux", [NOT_APPLICABLE, APPLICABLE])
def test_the_final_placement_pair_is_the_last_remote_read_before_the_write(ux):
    scene = world()
    reads_at_write = requirement_reads_at(scene, "write_document_content")
    start(scene, ux=ux)
    between = calls_from_create_to_write(scene)
    assert between[-2:] == [
        ("resolve_placement", MANIFEST_ID),
        ("resolve_placement", ARCHITECTURE_ID),
    ]
    earlier = [name for name, _ in between[:-2]]
    assert "read_document_content" in earlier
    assert reads_at_write == [scene.req.calls.count("read_requirement")]


def last_content_read_before_the_write(**changes) -> int:
    """Which `read_document_content` is the last one before the body write."""
    reference = world()
    start(reference, **changes)
    calls = [name for name, _ in reference.tsa.log]
    return calls[: calls.index("write_document_content")].count("read_document_content")


def test_a_shell_that_is_no_longer_empty_is_not_overwritten():
    content = accepted_manifest_carrier()
    scene = world()
    scene.tsa.after(
        "create_tsa_child_document",
        1,
        lambda: scene.tsa.set_content(MANIFEST_ID, content),
    )
    result = start(scene, clock=later_clock)
    assert not result.is_newly_written
    assert scene.tsa.count("write_document_content") == 0
    assert scene.tsa.content_of(MANIFEST_ID) == content


def test_a_created_child_that_cannot_be_observed_is_a_failed_write():
    scene = world()
    scene.tsa.after(
        "create_tsa_child_document", 1, lambda: scene.tsa.documents.pop(MANIFEST_ID)
    )
    error = refusal(scene)
    assert error.code is CycleResultCode.FIBERY_WRITE_FAILED
    assert scene.tsa.count("write_document_content") == 0
    assert scene.tsa.count("create_tsa_child_document") == 1


def test_an_unknown_write_that_did_not_land_leaves_an_unrecoverable_shell():
    scene = world()
    scene.tsa.before("write_document_content", 1, fail())
    error = refusal(scene)
    assert error.code is CycleResultCode.MANIFEST_SHELL_UNRECOVERABLE
    assert scene.tsa.count("write_document_content") == 1
    assert scene.tsa.content_of(MANIFEST_ID) == ""


def test_an_unknown_write_that_landed_is_adopted_without_a_second_write():
    scene = world()
    scene.tsa.after("write_document_content", 1, fail())
    result = start(scene)
    assert not result.is_newly_written
    assert scene.tsa.count("write_document_content") == 1
    assert result.artifact == validate_artifact(manifest_payload(scene))


def test_a_write_that_returns_but_stores_nothing_is_not_success():
    scene = world()
    scene.tsa.store_as = lambda markdown: ""
    error = refusal(scene)
    assert error.code is CycleResultCode.MANIFEST_SHELL_UNRECOVERABLE
    assert scene.tsa.count("write_document_content") == 1


def test_a_read_back_that_no_longer_parses_is_malformed_and_not_repaired():
    scene = world()
    scene.tsa.store_as = lambda markdown: markdown.replace('"accepted":true', "")
    error = refusal(scene)
    assert error.code is CycleResultCode.ARTIFACT_MALFORMED
    assert scene.tsa.count("write_document_content") == 1


def test_a_read_back_of_a_different_valid_manifest_is_a_failed_write():
    other = accepted_manifest_carrier(ux=UxNotApplicable("Another reason."))
    scene = world()
    scene.tsa.store_as = lambda markdown: other
    error = refusal(scene)
    assert error.code is CycleResultCode.FIBERY_WRITE_FAILED
    assert scene.tsa.count("write_document_content") == 1
    assert scene.tsa.content_of(MANIFEST_ID) == other


def test_a_failed_read_back_is_not_success():
    scene = world()
    scene.tsa.after(
        "write_document_content",
        1,
        lambda: scene.tsa.failures.__setitem__(
            "read_document_content", FiberyError("timeout")
        ),
    )
    error = refusal(scene)
    assert error.code is CycleResultCode.FIBERY_READ_FAILED
    assert scene.tsa.count("write_document_content") == 1


@pytest.mark.parametrize("drift", [move_architecture_root, reparent_manifest])
def test_placement_drift_at_read_back_is_a_refusal(drift):
    scene = world()
    scene.tsa.after("write_document_content", 1, drift(scene))
    error = refusal(scene)
    assert error.code is CycleResultCode.CYCLE_FOREIGN_PROJECT


def test_a_manifest_removed_before_read_back_is_a_failed_write():
    scene = world()
    scene.tsa.after(
        "write_document_content", 1, lambda: scene.tsa.documents.pop(MANIFEST_ID)
    )
    error = refusal(scene)
    assert error.code is CycleResultCode.FIBERY_WRITE_FAILED


def test_evidence_that_broke_across_the_bootstrap_refuses_the_manifest():
    scene = world("absent")
    scene.tsa.after(
        "create_project_document",
        1,
        lambda: scene.req.documents.__setitem__(
            scene.req.documents.index(scene.root),
            replace(scene.root, name=f"{REQUIREMENT_ID} — Renamed"),
        ),
    )
    error = refusal(scene)
    assert error.code is AdmissionResultCode.REQUIREMENT_NOT_ADMISSIBLE
    assert scene.tsa.count("create_tsa_child_document") == 0


def test_evidence_replaced_by_other_valid_evidence_mid_command_is_stale():
    scene = world("absent")
    add_applied_requirement(scene.req)

    def rewrite_review() -> None:
        node = next(d for d in scene.req.documents if d.id == "review-doc-40")
        scene.req.content[node.secret] = scene.req.content[node.secret].replace(
            '"clarity": "adequate"', '"clarity": "reworded"'
        )

    scene.tsa.after("create_project_document", 1, rewrite_review)
    error = refusal(scene, requirement_ids=(SECOND_ID,))
    assert error.code is AdmissionResultCode.INPUTS_STALE
    assert scene.tsa.count("create_tsa_child_document") == 0
    assert scene.tsa.resolve_placement(MANIFEST_ID) is None


# --------------------------------------------------------------------------
# Review F1: inputs are revalidated after a known create, before the body write
# --------------------------------------------------------------------------


def valid_review_rewritten(scene: World):
    """The second Requirement's Review Result changes but stays valid evidence."""

    def effect() -> None:
        node = next(d for d in scene.req.documents if d.id == "review-doc-40")
        before = scene.req.content[node.secret]
        after = before.replace('"clarity": "adequate"', '"clarity": "reworded"')
        assert after != before
        scene.req.content[node.secret] = after

    return effect


def root_drifts(scene: World):
    return lambda: root_edited_after_review(scene)


def ux_drifts(scene: World):
    return lambda: scene.tsa.set_content(UX_DOCUMENT_ID, "# Another document\n")


INPUT_DRIFT = {
    "requirement root": (
        root_drifts,
        {},
        AdmissionResultCode.REQUIREMENT_NOT_ADMISSIBLE,
    ),
    "valid review result content": (
        valid_review_rewritten,
        {"requirement_ids": (SECOND_ID,)},
        AdmissionResultCode.INPUTS_STALE,
    ),
    "applicable ux document": (
        ux_drifts,
        {"ux": APPLICABLE},
        AdmissionResultCode.UX_EVIDENCE_INVALID,
    ),
}


def assert_shell_left_unwritten(scene: World, creates: int = 1) -> None:
    """The Document create happened; no body write did, and nothing repaired it."""
    assert scene.tsa.count("write_document_content") == 0
    assert scene.tsa.written == []
    assert scene.tsa.mutations == [f"create:{MANIFEST_ID}"]
    assert scene.tsa.count("create_tsa_child_document") == creates
    assert scene.tsa.content_of(MANIFEST_ID) == ""


@pytest.mark.parametrize("label", sorted(INPUT_DRIFT))
def test_input_drift_after_a_known_create_stops_the_body_write(label):
    drift, changes, code = INPUT_DRIFT[label]
    scene = world()
    add_applied_requirement(scene.req)
    scene.tsa.after("create_tsa_child_document", 1, drift(scene))
    error = refusal(scene, **changes)
    assert error.code is code
    assert_shell_left_unwritten(scene)


def test_a_refusal_after_the_create_says_the_document_was_created():
    scene = world()
    scene.tsa.after("create_tsa_child_document", 1, root_drifts(scene))
    error = refusal(scene)
    assert MANIFEST_ID in str(error)
    assert "created" in str(error)


@pytest.mark.parametrize("label", sorted(INPUT_DRIFT))
def test_input_drift_after_the_retried_create_stops_the_body_write(label):
    drift, changes, code = INPUT_DRIFT[label]
    scene = world()
    add_applied_requirement(scene.req)
    scene.tsa.before("create_tsa_child_document", 1, fail())
    scene.tsa.after("create_tsa_child_document", 2, drift(scene))
    error = refusal(scene, **changes)
    assert error.code is code
    assert_shell_left_unwritten(scene, creates=2)


@pytest.mark.parametrize("ux", [NOT_APPLICABLE, APPLICABLE])
def test_unchanged_inputs_after_the_create_get_the_one_initial_body_write(ux):
    scene = world()
    reads_at_create = requirement_reads_at(scene, "create_tsa_child_document")
    reads_at_write = requirement_reads_at(scene, "write_document_content")
    requirement_writes = list(scene.req.mutations)
    result = start(scene, ux=ux)
    assert result.is_newly_written
    assert reads_at_create == [1]
    assert reads_at_write == [2]
    assert scene.tsa.count("write_document_content") == 1
    assert scene.tsa.count("create_tsa_child_document") == 1
    assert scene.req.mutations == requirement_writes


def test_a_rediscovered_empty_manifest_is_not_given_the_initial_write():
    scene = world()
    scene.tsa.seed_child(MANIFEST_ID, ARCHITECTURE_ID, "")
    error = clean_refusal(scene)
    assert error.code is CycleResultCode.MANIFEST_SHELL_UNRECOVERABLE
    assert scene.req.calls.count("read_requirement") == 0


# --------------------------------------------------------------------------
# Review F2: an unknown body write is confirmed against the intended Manifest
# --------------------------------------------------------------------------


def with_another_process_digest(carrier: str) -> str:
    """Another schema-valid accepted Manifest for the same caller inputs.

    One Process Result binding differs; every dependent digest and the
    acceptance are recomputed, so nothing about it is malformed.
    """
    payload = extract_artifact_payload(carrier)
    body = payload["body"]
    rows = body["manifest_body"]["requirements"]
    rows[0]["process_result"]["payload_digest"] = "f" * 64
    body["manifest_body"]["ux"]["requirement_input_digest"] = requirement_input_digest(
        rows
    )
    body["manifest_digest"] = manifest_digest(body["manifest_body"])
    body["acceptance"]["manifest_digest"] = body["manifest_digest"]
    return carrier_of(sealed_artifact(payload))


def test_the_substituted_manifest_is_valid_and_differs_only_in_its_bindings():
    intended = accepted_manifest_carrier()
    intended_artifact = validate_artifact(extract_artifact_payload(intended))
    other = validate_artifact(
        extract_artifact_payload(with_another_process_digest(intended))
    )
    assert other.artifact_type == INPUT_MANIFEST
    assert other.artifact_digest != intended_artifact.artifact_digest
    assert other.body["manifest_digest"] != intended_artifact.body["manifest_digest"]
    assert other.body["acceptance"]["manifest_digest"] == other.body["manifest_digest"]
    assert start_input_digest(
        tsa_admission._persisted_projection(CONTEXT, other)
    ) == start_input_digest(
        tsa_admission._persisted_projection(CONTEXT, intended_artifact)
    )
    scene = world()
    scene.tsa.seed_child(
        MANIFEST_ID, ARCHITECTURE_ID, with_another_process_digest(intended)
    )
    assert discover_cycle(scene.tsa, PROJECT_ID, CYCLE).outcome is CycleOutcome.D


@pytest.mark.parametrize("is_response_lost", [True, False])
def test_another_valid_manifest_after_the_body_write_is_a_failed_write(
    is_response_lost,
):
    scene = world()
    scene.tsa.store_as = with_another_process_digest
    if is_response_lost:
        scene.tsa.after("write_document_content", 1, fail())
    error = refusal(scene)
    assert error.code is CycleResultCode.FIBERY_WRITE_FAILED
    assert scene.tsa.count("write_document_content") == 1
    assert scene.tsa.count("create_tsa_child_document") == 1
    stored = scene.tsa.content_of(MANIFEST_ID)
    assert stored == with_another_process_digest(scene.tsa.written[0])
    assert discover_cycle(scene.tsa, PROJECT_ID, CYCLE).outcome is CycleOutcome.D


@pytest.mark.parametrize(
    "store_as", [None, lambda markdown: markdown.rstrip("\n")], ids=["exact", "trimmed"]
)
def test_the_intended_manifest_after_a_lost_response_is_confirmed_once(store_as):
    scene = world()
    scene.tsa.store_as = store_as
    scene.tsa.after("write_document_content", 1, fail())
    result = start(scene)
    assert not result.is_newly_written
    assert scene.tsa.count("write_document_content") == 1
    emitted = validate_artifact(extract_artifact_payload(scene.tsa.written[0]))
    assert result.artifact == emitted
    assert result.artifact == validate_artifact(manifest_payload(scene))


@pytest.mark.parametrize(
    "label", ["no fence", "missing acceptance", "acceptance bound to another digest"]
)
def test_an_unknown_write_that_landed_non_conforming_keeps_its_own_code(label):
    content, code = refusing_manifests()[label]
    scene = world()
    scene.tsa.store_as = lambda markdown: content
    scene.tsa.after("write_document_content", 1, fail())
    error = refusal(scene)
    assert error.code is code
    assert scene.tsa.count("write_document_content") == 1
    assert scene.tsa.content_of(MANIFEST_ID) == content


@pytest.mark.parametrize("drift", [move_architecture_root, reparent_manifest])
def test_an_unknown_write_with_placement_drift_keeps_the_cycle_refusal(drift):
    scene = world()

    def drift_then_fail() -> None:
        drift(scene)()
        raise FiberyError("connection reset")

    scene.tsa.after("write_document_content", 1, drift_then_fail)
    error = refusal(scene)
    assert error.code is CycleResultCode.CYCLE_FOREIGN_PROJECT
    assert scene.tsa.count("write_document_content") == 1


def test_a_repeat_still_compares_caller_inputs_and_not_bindings():
    other = with_another_process_digest(accepted_manifest_carrier())
    scene = world()
    scene.tsa.seed_child(MANIFEST_ID, ARCHITECTURE_ID, other)
    result = start(scene, clock=later_clock)
    assert not result.is_newly_written
    assert scene.tsa.mutations == []
    assert scene.tsa.content_of(MANIFEST_ID) == other
    assert scene.req.calls.count("read_requirement") == 0


# --------------------------------------------------------------------------
# Review F3: nothing is read between the final placement pair and the write
# --------------------------------------------------------------------------


@pytest.mark.parametrize("ux", [NOT_APPLICABLE, APPLICABLE], ids=["no ux", "ux"])
@pytest.mark.parametrize("drift", [reparent_manifest, move_architecture_root])
def test_placement_drift_during_the_last_content_read_stops_the_write(drift, ux):
    scene = world()
    scene.tsa.after(
        "read_document_content",
        last_content_read_before_the_write(ux=ux),
        drift(scene),
    )
    error = refusal(scene, ux=ux)
    assert error.code is CycleResultCode.CYCLE_FOREIGN_PROJECT
    assert_shell_left_unwritten(scene)
