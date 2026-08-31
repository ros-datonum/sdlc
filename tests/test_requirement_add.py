import pytest

from raw_fixtures import TITLE, VALID_SOURCE
from requirement_fake import FakeRequirementWorkspace, project_with_structure
from sdlc.fibery_workspace import FolderNode, ProjectRecord, RequirementRecord
from sdlc.raw_source import parse_raw_requirement
from sdlc.requirement_add import (
    INITIAL_REVISION,
    REQUIREMENT_INITIAL_STATE,
    REQUIREMENT_TYPE_RAW,
    add_raw_requirement,
    requirement_document_name,
)
from sdlc.results import AddResultCode

RAW_FOLDER_ID = "folder-raw"


def workspace_with_project(**kwargs):
    project, folders = project_with_structure(**kwargs)
    return FakeRequirementWorkspace(projects=[project], folders=folders), project


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


def test_root_document_is_created_in_the_raw_folder():
    workspace, _ = workspace_with_project()

    add_raw_requirement(workspace, "SDLC", VALID_SOURCE)

    [document] = workspace.documents
    assert document.folder_id == RAW_FOLDER_ID
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
    project, folders = project_with_structure(project_id="p1", name="SDLC", code="AAA")
    twin = ProjectRecord(
        id="p2",
        name="SDLC",
        code="BBB",
        state="Planned",
        documents_root_folder_id="folder-root",
    )
    workspace = FakeRequirementWorkspace(projects=[project, twin], folders=folders)

    result = add_raw_requirement(workspace, "SDLC", VALID_SOURCE)

    assert result.code is AddResultCode.PROJECT_AMBIGUOUS
    assert workspace.mutations == []


def test_the_command_never_creates_a_project():
    workspace = FakeRequirementWorkspace()

    add_raw_requirement(workspace, "SDLC", VALID_SOURCE)

    assert workspace.projects == []


# -- project structure -----------------------------------------------------


@pytest.mark.parametrize("missing", ["Raw", "Draft", "Approved", "Requirements"])
def test_missing_stage_folder_is_an_invalid_structure(missing):
    project, folders = project_with_structure()
    workspace = FakeRequirementWorkspace(
        projects=[project], folders=[f for f in folders if f.name != missing]
    )

    result = add_raw_requirement(workspace, "SDLC", VALID_SOURCE)

    assert result.code is AddResultCode.PROJECT_STRUCTURE_INVALID
    assert workspace.mutations == []


def test_missing_documents_root_folder_id_is_an_invalid_structure():
    _, folders = project_with_structure()
    project = ProjectRecord(
        id="p1",
        name="SDLC",
        code="SDLC",
        state="Planned",
        documents_root_folder_id=None,
    )
    workspace = FakeRequirementWorkspace(projects=[project], folders=folders)

    result = add_raw_requirement(workspace, "SDLC", VALID_SOURCE)

    assert result.code is AddResultCode.PROJECT_STRUCTURE_INVALID


def test_duplicate_sibling_folder_names_make_the_structure_ambiguous():
    """Fibery permits sibling Folders sharing a name; do not guess."""
    project, folders = project_with_structure()
    folders.append(
        FolderNode(id="folder-raw-2", name="Raw", parent_id="folder-requirements")
    )
    workspace = FakeRequirementWorkspace(projects=[project], folders=folders)

    result = add_raw_requirement(workspace, "SDLC", VALID_SOURCE)

    assert result.code is AddResultCode.PROJECT_STRUCTURE_INVALID
    assert "ambiguous" in result.message
    assert workspace.mutations == []


def test_the_command_never_repairs_missing_folders():
    project, folders = project_with_structure()
    workspace = FakeRequirementWorkspace(
        projects=[project], folders=[f for f in folders if f.name != "Draft"]
    )
    before = list(workspace.folders)

    add_raw_requirement(workspace, "SDLC", VALID_SOURCE)

    assert workspace.folders == before


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
    a, folders_a = project_with_structure(project_id="p1", name="A", code="AAA")
    b_root = FolderNode(id="b-root", name="B", parent_id=None)
    b_req = FolderNode(id="b-req", name="Requirements", parent_id=b_root.id)
    b_stages = [
        FolderNode(id=f"b-{s.lower()}", name=s, parent_id=b_req.id)
        for s in ("Raw", "Draft", "Approved")
    ]
    b = ProjectRecord(
        id="p2",
        name="B",
        code="BBB",
        state="Planned",
        documents_root_folder_id=b_root.id,
    )
    workspace = FakeRequirementWorkspace(
        projects=[a, b], folders=[*folders_a, b_root, b_req, *b_stages]
    )
    add_raw_requirement(workspace, "AAA", VALID_SOURCE)

    result = add_raw_requirement(workspace, "BBB", VALID_SOURCE)

    assert result.code is AddResultCode.RAW_REQUIREMENT_ADDED
    assert result.requirement_id == "BBB-RAW-0001"


# -- id allocation ---------------------------------------------------------


def test_ids_increment_within_the_project():
    workspace, _ = workspace_with_project()
    ids = []
    for index in range(3):
        text = VALID_SOURCE.replace(TITLE, f"{TITLE} {index}")
        ids.append(add_raw_requirement(workspace, "SDLC", text).requirement_id)

    assert ids == ["SDLC-RAW-0001", "SDLC-RAW-0002", "SDLC-RAW-0003"]


def test_allocation_continues_past_gaps_and_never_reuses_an_id():
    project, folders = project_with_structure()
    existing = RequirementRecord(
        id="r-old",
        public_id="99",
        requirement_id="SDLC-RAW-0007",
        title="Older",
        type_name="Raw",
        state="Draft",
        revision=1,
        project_id=project.id,
        source_fingerprint="other",
    )
    workspace = FakeRequirementWorkspace(
        projects=[project], folders=folders, requirements=[existing]
    )

    result = add_raw_requirement(workspace, "SDLC", VALID_SOURCE)

    assert result.requirement_id == "SDLC-RAW-0008"


def test_allocation_ignores_ids_belonging_to_other_projects():
    workspace, _ = workspace_with_project(code="SDLC")
    workspace.requirements["foreign"] = RequirementRecord(
        id="foreign",
        public_id="50",
        requirement_id="OTHER-RAW-0042",
        title="Elsewhere",
        type_name="Raw",
        state="Draft",
        revision=1,
        project_id="another-project",
        source_fingerprint="x",
    )

    result = add_raw_requirement(workspace, "SDLC", VALID_SOURCE)

    assert result.requirement_id == "SDLC-RAW-0001"
