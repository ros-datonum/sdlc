import pytest

from fibery_fake import FakeFiberyWorkspace, planned_project
from sdlc.project_code import COLLISION_SUFFIX_LIMIT, candidate_project_codes
from sdlc.project_init import PROJECT_INITIAL_STATE, initialize_project
from sdlc.results import ResultCode

PROJECT_NAME = "SDLC"


def taken_projects(codes):
    return [
        planned_project(project_id=f"taken-{index}", name=f"Other {index}", code=code)
        for index, code in enumerate(codes)
    ]


# -- creating a new Project ------------------------------------------------


def test_creates_the_project_entity_and_reports_initialized():
    workspace = FakeFiberyWorkspace()

    result = initialize_project(workspace, PROJECT_NAME)

    assert result.code is ResultCode.PROJECT_INITIALIZED
    assert result.project_code == "SDLC"
    assert result.created == (
        "Project entity project-1",
        "Project State = Planned",
    )


def test_created_project_is_planned_and_carries_the_generated_code():
    workspace = FakeFiberyWorkspace()

    initialize_project(workspace, PROJECT_NAME)

    [record] = workspace.projects.values()
    assert record.name == PROJECT_NAME
    assert record.code == "SDLC"
    assert record.state == PROJECT_INITIAL_STATE


def test_no_folder_tree_is_created_or_read():
    """Lifecycle placement is Requirement Type + State; no Document folders.

    Human navigation is a workspace-level Smart Folder configured once in the
    Fibery UI, never created or validated here.
    """
    workspace = FakeFiberyWorkspace()

    initialize_project(workspace, PROJECT_NAME)

    assert not any("folder" in mutation.lower() for mutation in workspace.mutations)
    assert not any("folder" in call.lower() for call in workspace.calls)
    assert workspace.mutations == [
        "create_project SDLC SDLC",
        "set_project_state project-1 Planned",
    ]


def test_the_project_record_carries_no_documents_root_folder():
    workspace = FakeFiberyWorkspace()

    initialize_project(workspace, PROJECT_NAME)

    [record] = workspace.projects.values()
    assert not hasattr(record, "documents_root_folder_id")


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


@pytest.mark.parametrize("name", ["SDLC/Requirements", "A/B", "Team / Project"])
def test_a_slash_in_the_project_name_is_not_special(name):
    """Names carry no path: nothing is addressed by a slash-delimited name."""
    workspace = FakeFiberyWorkspace()

    result = initialize_project(workspace, name)

    assert result.code is ResultCode.PROJECT_INITIALIZED
    [record] = workspace.projects.values()
    assert record.name == name
