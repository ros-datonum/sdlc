import pytest

from fibery_fake import FakeFiberyWorkspace, planned_project
from sdlc.project_code import COLLISION_SUFFIX_LIMIT, candidate_project_codes
from sdlc.project_init import (
    PROJECT_INITIAL_STATE,
    initialize_project,
    project_document_paths,
)
from sdlc.results import ResultCode

PROJECT_NAME = "SDLC"
EXPECTED_PATHS = (
    "SDLC",
    "SDLC/Requirements",
    "SDLC/Requirements/Raw",
    "SDLC/Requirements/Draft",
    "SDLC/Requirements/Approved",
)


def taken_projects(codes):
    return [
        planned_project(project_id=f"taken-{index}", name=f"Other {index}", code=code)
        for index, code in enumerate(codes)
    ]


# -- creating a new Project ------------------------------------------------


def test_creates_project_document_structure_and_reports_initialized():
    workspace = FakeFiberyWorkspace()

    result = initialize_project(workspace, PROJECT_NAME)

    assert result.code is ResultCode.PROJECT_INITIALIZED
    assert result.project_code == "SDLC"
    assert result.documents == EXPECTED_PATHS


def test_created_project_is_planned_and_carries_the_generated_code():
    workspace = FakeFiberyWorkspace()

    initialize_project(workspace, PROJECT_NAME)

    [record] = workspace.projects.values()
    assert record.name == PROJECT_NAME
    assert record.code == "SDLC"
    assert record.state == PROJECT_INITIAL_STATE


def test_documents_root_references_the_project_root_document():
    workspace = FakeFiberyWorkspace()

    initialize_project(workspace, PROJECT_NAME)

    [record] = workspace.projects.values()
    root = workspace.documents[PROJECT_NAME]
    assert record.documents_root == root.id


def test_document_structure_is_created_parent_before_child():
    workspace = FakeFiberyWorkspace()

    initialize_project(workspace, PROJECT_NAME)

    created = [
        mutation.removeprefix("create_document ")
        for mutation in workspace.mutations
        if mutation.startswith("create_document ")
    ]
    assert tuple(created) == EXPECTED_PATHS


def test_document_paths_are_derived_from_the_project_name():
    assert project_document_paths("Design System")[0] == "Design System"
    assert project_document_paths("Design System")[2] == (
        "Design System/Requirements/Raw"
    )


def test_supplied_code_is_used_instead_of_a_derived_one():
    workspace = FakeFiberyWorkspace()

    result = initialize_project(workspace, "Design System", code="des")

    assert result.code is ResultCode.PROJECT_INITIALIZED
    assert result.project_code == "DES"


def test_description_is_written_only_when_supplied():
    without = FakeFiberyWorkspace()
    initialize_project(without, PROJECT_NAME)
    assert without.descriptions == {}

    with_description = FakeFiberyWorkspace()
    initialize_project(with_description, PROJECT_NAME, description="Bootstrap.")
    assert list(with_description.descriptions.values()) == ["Bootstrap."]


def test_no_project_phases_or_requirements_are_created():
    workspace = FakeFiberyWorkspace()

    initialize_project(workspace, PROJECT_NAME)

    assert not any(
        keyword in mutation
        for mutation in workspace.mutations
        for keyword in ("phase", "requirement", "milestone", "epic", "task")
    )


# -- existing Project ------------------------------------------------------


def test_existing_project_returns_already_exists_without_mutating():
    workspace = FakeFiberyWorkspace(projects=[planned_project()])

    result = initialize_project(workspace, PROJECT_NAME)

    assert result.code is ResultCode.PROJECT_ALREADY_EXISTS
    assert workspace.mutations == []


def test_existing_project_is_not_repaired_when_documents_are_missing():
    workspace = FakeFiberyWorkspace(
        projects=[planned_project(documents_root=None)], documents=[]
    )

    result = initialize_project(workspace, PROJECT_NAME)

    assert result.code is ResultCode.PROJECT_ALREADY_EXISTS
    assert workspace.mutations == []
    assert workspace.documents == {}


def test_existing_project_keeps_its_code():
    workspace = FakeFiberyWorkspace(projects=[planned_project(code="OLD")])

    result = initialize_project(workspace, PROJECT_NAME)

    assert result.project_code == "OLD"
    assert workspace.projects["existing-1"].code == "OLD"


def test_a_differently_named_project_does_not_count_as_existing():
    workspace = FakeFiberyWorkspace(
        projects=[planned_project(name="Other", code="OTH")]
    )

    result = initialize_project(workspace, PROJECT_NAME)

    assert result.code is ResultCode.PROJECT_INITIALIZED


# -- Project Code validation and collisions --------------------------------


@pytest.mark.parametrize("supplied", ["1SDLC", "SD-LC", "SD LC", "   "])
def test_invalid_supplied_code_is_rejected_before_any_mutation(supplied):
    workspace = FakeFiberyWorkspace()

    result = initialize_project(workspace, PROJECT_NAME, code=supplied)

    assert result.code is ResultCode.INVALID_PROJECT_CODE
    assert workspace.mutations == []


def test_supplied_code_already_in_use_is_a_collision_not_a_rename():
    workspace = FakeFiberyWorkspace(projects=taken_projects(["SDLC"]))

    result = initialize_project(workspace, PROJECT_NAME, code="SDLC")

    assert result.code is ResultCode.PROJECT_CODE_COLLISION
    assert workspace.mutations == []


def test_generated_code_skips_codes_that_are_already_taken():
    workspace = FakeFiberyWorkspace(projects=taken_projects(["SDLC", "SDLC2"]))

    result = initialize_project(workspace, PROJECT_NAME)

    assert result.code is ResultCode.PROJECT_INITIALIZED
    assert result.project_code == "SDLC3"


def test_exhausting_every_candidate_code_reports_a_collision():
    workspace = FakeFiberyWorkspace(
        projects=taken_projects(candidate_project_codes(PROJECT_NAME))
    )

    result = initialize_project(workspace, PROJECT_NAME)

    assert result.code is ResultCode.PROJECT_CODE_COLLISION
    assert workspace.mutations == []
    assert len(workspace.projects) == COLLISION_SUFFIX_LIMIT - 1


# -- input validation ------------------------------------------------------


@pytest.mark.parametrize("name", ["", "   "])
def test_blank_project_name_is_invalid_input(name):
    workspace = FakeFiberyWorkspace()

    result = initialize_project(workspace, name)

    assert result.code is ResultCode.INVALID_INPUT
    assert workspace.calls == []


def test_project_name_without_letters_is_invalid_input():
    workspace = FakeFiberyWorkspace()

    result = initialize_project(workspace, "2024")

    assert result.code is ResultCode.INVALID_INPUT
    assert workspace.mutations == []


@pytest.mark.parametrize("name", ["SDLC/Requirements", "A/B", "/SDLC", "SDLC/"])
def test_project_name_containing_the_path_separator_is_invalid_input(name):
    """A name with a separator would address another Project's document nodes.

    Fibery cannot nest Documents, so the section 9 hierarchy is encoded as a
    path in the document name.
    """
    workspace = FakeFiberyWorkspace()

    result = initialize_project(workspace, name)

    assert result.code is ResultCode.INVALID_INPUT
    assert workspace.mutations == []
    assert workspace.calls == []


def test_a_project_cannot_hijack_another_projects_document_subtree():
    workspace = FakeFiberyWorkspace()
    initialize_project(workspace, PROJECT_NAME)
    documents_before = dict(workspace.documents)

    result = initialize_project(workspace, "SDLC/Requirements")

    assert result.code is ResultCode.INVALID_INPUT
    assert workspace.documents == documents_before
