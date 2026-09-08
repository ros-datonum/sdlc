import pytest

from raw_fixtures import TITLE, VALID_SOURCE
from requirement_fake import FakeRequirementWorkspace, planned_project
from sdlc.fibery_workspace import ProjectRecord, RequirementRecord
from sdlc.raw_source import parse_raw_requirement
from sdlc.requirement_add import (
    INITIAL_REVISION,
    REQUIREMENT_INITIAL_STATE,
    REQUIREMENT_TYPE_RAW,
    add_raw_requirement,
    requirement_document_name,
)
from sdlc.requirement_id import raw_requirement_id
from sdlc.results import AddResultCode


def workspace_with_project(**kwargs):
    project = planned_project(**kwargs)
    return FakeRequirementWorkspace(projects=[project]), project


# -- happy path ------------------------------------------------------------


def test_ingests_a_conforming_artifact():
    workspace, _ = workspace_with_project()

    result = add_raw_requirement(workspace, "SDLC", VALID_SOURCE)

    assert result.code is AddResultCode.RAW_REQUIREMENT_ADDED
    assert result.requirement_id == "SDLC-RAW-0001"
    assert result.title == TITLE


def test_created_requirement_carries_the_specified_initial_values():
    workspace, project = workspace_with_project()

    add_raw_requirement(workspace, "SDLC", VALID_SOURCE)

    [record] = workspace.requirements.values()
    assert record.requirement_id == "SDLC-RAW-0001"
    assert record.title == TITLE
    assert record.type_name == REQUIREMENT_TYPE_RAW
    assert record.state == REQUIREMENT_INITIAL_STATE
    assert record.revision == INITIAL_REVISION
    assert record.project_id == project.id
    assert record.source_fingerprint == parse_raw_requirement(VALID_SOURCE).fingerprint


def test_root_document_is_contained_by_the_requirement_with_no_folder():
    """Placement is Type = Raw on the Requirement, never a Document folder."""
    workspace, _ = workspace_with_project()

    add_raw_requirement(workspace, "SDLC", VALID_SOURCE)

    [document] = workspace.documents
    [record] = workspace.requirements.values()
    assert document.folder_id is None
    assert document.entity_public_id == record.public_id
    assert document.name == requirement_document_name("SDLC-RAW-0001", TITLE)


def test_exactly_one_root_document_is_attached_to_the_requirement():
    workspace, _ = workspace_with_project()

    add_raw_requirement(workspace, "SDLC", VALID_SOURCE)

    [record] = workspace.requirements.values()
    attached = workspace.documents_attached_to_requirement(record.public_id)
    assert len(attached) == 1


def test_document_is_attached_using_the_requirement_public_id_not_its_uuid():
    """Fibery rejects the uuid with parent-entity-not-found."""
    workspace, _ = workspace_with_project()

    add_raw_requirement(workspace, "SDLC", VALID_SOURCE)

    [record] = workspace.requirements.values()
    [document] = workspace.documents
    assert document.entity_public_id == record.public_id
    assert document.entity_public_id != record.id


def test_source_content_is_written_without_semantic_rewriting():
    workspace, _ = workspace_with_project()

    add_raw_requirement(workspace, "SDLC", VALID_SOURCE)

    [document] = workspace.documents
    assert (
        workspace.content[document.secret] == parse_raw_requirement(VALID_SOURCE).body
    )


def test_no_analysis_relations_are_populated():
    workspace, _ = workspace_with_project()

    add_raw_requirement(workspace, "SDLC", VALID_SOURCE)

    assert not any(
        word in mutation.lower()
        for mutation in workspace.mutations
        for word in ("produces", "derived", "depends", "blocks", "affects", "category")
    )


# -- project resolution ----------------------------------------------------


def test_project_is_resolved_by_code_first():
    workspace, _ = workspace_with_project(name="Design System", code="SDLC")

    result = add_raw_requirement(workspace, "SDLC", VALID_SOURCE)

    assert result.code is AddResultCode.RAW_REQUIREMENT_ADDED
    assert workspace.calls[0] == "find_project_by_code"


def test_project_falls_back_to_exact_name():
    workspace, _ = workspace_with_project(name="SDLC", code="OTHER")

    result = add_raw_requirement(workspace, "SDLC", VALID_SOURCE)

    assert result.code is AddResultCode.RAW_REQUIREMENT_ADDED
    assert result.project_code == "OTHER"


def test_missing_project_is_reported_without_creating_anything():
    workspace, _ = workspace_with_project()

    result = add_raw_requirement(workspace, "NOPE", VALID_SOURCE)

    assert result.code is AddResultCode.PROJECT_NOT_FOUND
    assert workspace.mutations == []


def test_ambiguous_project_name_is_never_guessed():
    project = planned_project(project_id="p1", name="SDLC", code="AAA")
    twin = ProjectRecord(id="p2", name="SDLC", code="BBB", state="Planned")
    workspace = FakeRequirementWorkspace(projects=[project, twin])

    result = add_raw_requirement(workspace, "SDLC", VALID_SOURCE)

    assert result.code is AddResultCode.PROJECT_AMBIGUOUS
    assert workspace.mutations == []


def test_the_command_never_creates_a_project():
    workspace = FakeRequirementWorkspace()

    add_raw_requirement(workspace, "SDLC", VALID_SOURCE)

    assert workspace.projects == []


# -- project structure -----------------------------------------------------


def test_no_folder_structure_is_read_created_or_required():
    """The Project entity is the whole structure; no Raw/Draft/Approved tree."""
    workspace, _ = workspace_with_project()

    result = add_raw_requirement(workspace, "SDLC", VALID_SOURCE)

    assert result.code is AddResultCode.RAW_REQUIREMENT_ADDED
    assert not any("folder" in call.lower() for call in workspace.calls)
    assert not any("folder" in mutation.lower() for mutation in workspace.mutations)


def test_the_result_names_the_root_document_not_a_folder_path():
    workspace, _ = workspace_with_project()

    result = add_raw_requirement(workspace, "SDLC", VALID_SOURCE)

    assert result.document_name == requirement_document_name("SDLC-RAW-0001", TITLE)
    assert "/" not in result.document_name


# -- source validation -----------------------------------------------------


def test_invalid_source_is_rejected_before_any_mutation():
    workspace, _ = workspace_with_project()

    result = add_raw_requirement(workspace, "SDLC", "# Title only\n")

    assert result.code is AddResultCode.INVALID_REQUIREMENT_SOURCE
    assert workspace.mutations == []


def test_unsupported_format_version_has_its_own_result():
    workspace, _ = workspace_with_project()
    text = VALID_SOURCE.replace("- Format Version: `0.1`", "- Format Version: `9.9`")

    result = add_raw_requirement(workspace, "SDLC", text)

    assert result.code is AddResultCode.UNSUPPORTED_REQUIREMENTS_FORMAT
    assert workspace.mutations == []


@pytest.mark.parametrize("selector", ["", "   "])
def test_blank_project_selector_is_invalid_input(selector):
    workspace, _ = workspace_with_project()

    result = add_raw_requirement(workspace, selector, VALID_SOURCE)

    assert result.code is AddResultCode.INVALID_INPUT
    assert workspace.calls == []


# -- duplicates ------------------------------------------------------------


def test_reingesting_the_same_artifact_changes_nothing():
    workspace, _ = workspace_with_project()
    first = add_raw_requirement(workspace, "SDLC", VALID_SOURCE)
    mutations = list(workspace.mutations)

    second = add_raw_requirement(workspace, "SDLC", VALID_SOURCE)

    assert second.code is AddResultCode.REQUIREMENT_ALREADY_ADDED
    assert second.requirement_id == first.requirement_id
    assert workspace.mutations == mutations
    assert len(workspace.requirements) == 1
    assert len(workspace.documents) == 1


def test_duplicate_detection_ignores_the_export_timestamp():
    workspace, _ = workspace_with_project()
    add_raw_requirement(workspace, "SDLC", VALID_SOURCE)
    later = VALID_SOURCE.replace("`2026-08-31T10:00:00Z`", "`2027-05-05T00:00:00Z`")

    result = add_raw_requirement(workspace, "SDLC", later)

    assert result.code is AddResultCode.REQUIREMENT_ALREADY_ADDED


def test_a_different_artifact_is_not_a_duplicate():
    workspace, _ = workspace_with_project()
    add_raw_requirement(workspace, "SDLC", VALID_SOURCE)
    other = VALID_SOURCE.replace(TITLE, "A Different Requirement")

    result = add_raw_requirement(workspace, "SDLC", other)

    assert result.code is AddResultCode.RAW_REQUIREMENT_ADDED
    assert result.requirement_id == "SDLC-RAW-0002"


def test_the_same_artifact_in_another_project_is_not_a_duplicate():
    a = planned_project(project_id="p1", name="A", code="AAA")
    b = planned_project(project_id="p2", name="B", code="BBB")
    workspace = FakeRequirementWorkspace(projects=[a, b])
    add_raw_requirement(workspace, "AAA", VALID_SOURCE)

    result = add_raw_requirement(workspace, "BBB", VALID_SOURCE)

    assert result.code is AddResultCode.RAW_REQUIREMENT_ADDED
    assert result.requirement_id.startswith("BBB-RAW-")


# -- id allocation ---------------------------------------------------------


def test_ids_increment_within_the_project():
    workspace, _ = workspace_with_project()
    ids = []
    for index in range(3):
        text = VALID_SOURCE.replace(TITLE, f"{TITLE} {index}")
        ids.append(add_raw_requirement(workspace, "SDLC", text).requirement_id)

    assert ids == ["SDLC-RAW-0001", "SDLC-RAW-0002", "SDLC-RAW-0003"]


def test_ids_come_from_the_fibery_public_id_not_from_counting():
    """Gaps are expected: the number is Fibery's, not a per-project counter."""
    workspace, _ = workspace_with_project()
    workspace.next_public_ids = ["137"]

    result = add_raw_requirement(workspace, "SDLC", VALID_SOURCE)

    assert result.requirement_id == "SDLC-RAW-0137"


def test_existing_requirements_do_not_influence_allocation():
    project = planned_project()
    existing = RequirementRecord(
        id="r-old",
        public_id="99",
        requirement_id="SDLC-RAW-0099",
        title="Older",
        type_name="Raw",
        state="Draft",
        revision=1,
        project_id=project.id,
        source_fingerprint="other",
    )
    workspace = FakeRequirementWorkspace(projects=[project], requirements=[existing])
    workspace.next_public_ids = ["5"]

    result = add_raw_requirement(workspace, "SDLC", VALID_SOURCE)

    assert result.requirement_id == "SDLC-RAW-0005"


def test_a_large_public_id_is_not_truncated():
    workspace, _ = workspace_with_project()
    workspace.next_public_ids = ["12045"]

    result = add_raw_requirement(workspace, "SDLC", VALID_SOURCE)

    assert result.requirement_id == "SDLC-RAW-12045"


def test_requirement_id_is_written_after_creation():
    workspace, _ = workspace_with_project()

    add_raw_requirement(workspace, "SDLC", VALID_SOURCE)

    order = [m.split()[0] for m in workspace.mutations]
    assert order.index("create_requirement") < order.index("set_requirement_id")
    [record] = workspace.requirements.values()
    assert record.requirement_id == "SDLC-RAW-0001"


# -- concurrency ------------------------------------------------------------


def test_concurrent_writers_cannot_derive_the_same_requirement_id():
    """The interleaving that broke the previous allocator.

    Both writers read the Project state before either has written. The old
    allocator counted existing RAW ids and both chose SDLC-RAW-0001. Deriving
    from the public id Fibery allocates makes that impossible.
    """
    project = planned_project()
    workspace = FakeRequirementWorkspace(projects=[project])
    workspace.next_public_ids = ["101", "102"]

    first = add_raw_requirement(workspace, "SDLC", VALID_SOURCE)
    second = add_raw_requirement(
        workspace, "SDLC", VALID_SOURCE.replace(TITLE, "A Second Requirement")
    )

    assert first.code is AddResultCode.RAW_REQUIREMENT_ADDED
    assert second.code is AddResultCode.RAW_REQUIREMENT_ADDED
    assert first.requirement_id == "SDLC-RAW-0101"
    assert second.requirement_id == "SDLC-RAW-0102"
    assert first.requirement_id != second.requirement_id


def test_no_two_requirements_ever_share_a_requirement_id():
    project = planned_project()
    workspace = FakeRequirementWorkspace(projects=[project])
    workspace.next_public_ids = [str(n) for n in range(200, 210)]

    for index in range(10):
        add_raw_requirement(
            workspace, "SDLC", VALID_SOURCE.replace(TITLE, f"{TITLE} {index}")
        )

    ids = [r.requirement_id for r in workspace.requirements.values()]
    assert len(ids) == 10
    assert len(set(ids)) == 10


def test_allocation_does_not_depend_on_reading_other_requirements():
    """No read-then-write window exists to lose."""
    workspace, _ = workspace_with_project()

    add_raw_requirement(workspace, "SDLC", VALID_SOURCE)

    assert "requirement_ids_in_project" not in workspace.calls
    assert "count_requirements_with_requirement_id" not in workspace.calls


def test_interleaved_writers_cannot_collide_even_when_both_create_first():
    """The exact interleaving that produced two durable SDLC-RAW-0001 entities.

    Both entities exist before either Requirement ID is written. The old
    allocator counted existing ids and both writers read zero, so both chose
    0001. Deriving from the public id removes the read entirely.
    """
    project = planned_project()
    workspace = FakeRequirementWorkspace(projects=[project])
    workspace.next_public_ids = ["101", "102"]

    a = workspace.create_requirement(project.id, "A", 1, "fp-a")
    b = workspace.create_requirement(project.id, "B", 1, "fp-b")
    assert a.requirement_id is None and b.requirement_id is None

    id_a = raw_requirement_id(project.code, a.public_id)
    id_b = raw_requirement_id(project.code, b.public_id)
    workspace.set_requirement_id(a.id, id_a)
    workspace.set_requirement_id(b.id, id_b)

    assert id_a != id_b
    stored = [r.requirement_id for r in workspace.requirements.values()]
    assert len(set(stored)) == len(stored)
