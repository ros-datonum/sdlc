import pytest

from fibery_fake import FakeFiberyWorkspace, planned_project
from sdlc.fibery_workspace import FolderNode
from sdlc.project_code import COLLISION_SUFFIX_LIMIT, candidate_project_codes
from sdlc.project_init import (
    PROJECT_INITIAL_STATE,
    REQUIREMENT_STAGE_FOLDER_NAMES,
    REQUIREMENTS_FOLDER_NAME,
    folder_display_paths,
    initialize_project,
    project_folder_tree,
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
EXPECTED_FOLDER_NAMES = ("SDLC", "Requirements", "Raw", "Draft", "Approved")


def only(folders):
    """The single Folder matching a name/parent, asserting there is exactly one."""
    assert len(folders) == 1, f"expected exactly 1 folder, got {len(folders)}"
    return folders[0]


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


def test_documents_root_folder_id_references_the_root_folder():
    workspace = FakeFiberyWorkspace()

    initialize_project(workspace, PROJECT_NAME)

    [record] = workspace.projects.values()
    root = only(workspace.folder_named(PROJECT_NAME, None))
    assert record.documents_root_folder_id == root.id
    assert root.parent_id is None


def test_folders_are_created_parent_before_child():
    workspace = FakeFiberyWorkspace()

    initialize_project(workspace, PROJECT_NAME)

    created = [
        mutation.split()[1]
        for mutation in workspace.mutations
        if mutation.startswith("create_folder ")
    ]
    assert tuple(created) == EXPECTED_FOLDER_NAMES


def test_folders_are_really_nested_not_slash_named():
    """Fibery nests Folders through Parent Folder; names carry no path."""
    workspace = FakeFiberyWorkspace()

    initialize_project(workspace, PROJECT_NAME)

    root = only(workspace.folder_named(PROJECT_NAME, None))
    requirements = only(workspace.folder_named("Requirements", root.id))
    assert requirements.parent_id == root.id
    for stage in ("Raw", "Draft", "Approved"):
        assert (
            only(workspace.folder_named(stage, requirements.id)).parent_id
            == requirements.id
        )
    assert all("/" not in folder.name for folder in workspace.folders)


def test_folder_tree_nests_every_stage_under_requirements():
    tree = project_folder_tree("Design System")
    assert tree[0] == ("Design System", None)
    assert tree[1] == ("Requirements", 0)
    assert [name for name, _ in tree[2:]] == ["Raw", "Draft", "Approved"]
    assert {parent for _, parent in tree[2:]} == {1}


def test_display_paths_are_for_output_only():
    assert folder_display_paths("Design System")[2] == (
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


def test_existing_project_is_not_repaired_when_folders_are_missing():
    workspace = FakeFiberyWorkspace(
        projects=[planned_project(documents_root_folder_id=None)], folders=[]
    )

    result = initialize_project(workspace, PROJECT_NAME)

    assert result.code is ResultCode.PROJECT_ALREADY_EXISTS
    assert workspace.mutations == []
    assert workspace.folders == []


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
def test_a_slash_in_the_project_name_is_no_longer_special(name):
    """Real Folders removed the reason to reject separators in names."""
    workspace = FakeFiberyWorkspace()

    result = initialize_project(workspace, name)

    assert result.code is ResultCode.PROJECT_INITIALIZED
    assert only(workspace.folder_named(name, None)).parent_id is None


def test_two_projects_do_not_share_folders_even_with_colliding_names():
    workspace = FakeFiberyWorkspace()
    initialize_project(workspace, PROJECT_NAME)

    result = initialize_project(workspace, "SDLC/Requirements")

    assert result.code is ResultCode.PROJECT_INITIALIZED
    root = only(workspace.folder_named(PROJECT_NAME, None))
    other = only(workspace.folder_named("SDLC/Requirements", None))
    assert root.id != other.id
    assert only(workspace.folder_named("Requirements", root.id)).id != (
        only(workspace.folder_named("Requirements", other.id)).id
    )


# -- regression: sibling folders may share a name --------------------------


def test_preexisting_root_folder_with_the_same_name_does_not_break_init():
    """The defect this guards against.

    Fibery allows sibling Folders with identical names. The workspace already
    held a hand-made top-level 'SDLC' folder, so validating by (name, parent)
    resolved that older folder instead of the one this run created and
    reported a false VALIDATION_FAILED.
    """
    preexisting = FolderNode(id="preexisting-root", name=PROJECT_NAME, parent_id=None)
    workspace = FakeFiberyWorkspace(folders=[preexisting])

    result = initialize_project(workspace, PROJECT_NAME)

    assert result.code is ResultCode.PROJECT_INITIALIZED

    roots = workspace.folder_named(PROJECT_NAME, None)
    assert len(roots) == 2, "the run must add its own root, not reuse the old one"
    created_root = next(folder for folder in roots if folder.id != preexisting.id)

    [record] = workspace.projects.values()
    assert record.documents_root_folder_id == created_root.id


def test_preexisting_sibling_is_left_untouched():
    preexisting = FolderNode(id="preexisting-root", name=PROJECT_NAME, parent_id=None)
    workspace = FakeFiberyWorkspace(folders=[preexisting])

    initialize_project(workspace, PROJECT_NAME)

    assert preexisting in workspace.folders
    assert not any(
        mutation.startswith(("update_folder", "delete_folder"))
        for mutation in workspace.mutations
    )
    # Nothing was created under the pre-existing root.
    assert workspace.folder_named(REQUIREMENTS_FOLDER_NAME, preexisting.id) == []


def test_nested_tree_hangs_off_the_newly_created_root():
    preexisting = FolderNode(id="preexisting-root", name=PROJECT_NAME, parent_id=None)
    workspace = FakeFiberyWorkspace(folders=[preexisting])

    initialize_project(workspace, PROJECT_NAME)

    created_root = next(
        folder
        for folder in workspace.folder_named(PROJECT_NAME, None)
        if folder.id != preexisting.id
    )
    requirements = only(
        workspace.folder_named(REQUIREMENTS_FOLDER_NAME, created_root.id)
    )
    for stage in REQUIREMENT_STAGE_FOLDER_NAMES:
        assert only(workspace.folder_named(stage, requirements.id)).parent_id == (
            requirements.id
        )


def test_validation_resolves_created_folders_by_id_not_by_name():
    """Read-back must ask for the created id, never a name lookup."""
    preexisting = FolderNode(id="preexisting-root", name=PROJECT_NAME, parent_id=None)
    workspace = FakeFiberyWorkspace(folders=[preexisting])

    initialize_project(workspace, PROJECT_NAME)

    resolved = [call for call in workspace.calls if call == "resolve_folder"]
    assert len(resolved) == len(project_folder_tree(PROJECT_NAME))
    assert "find_folder" not in workspace.calls
