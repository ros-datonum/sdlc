"""Failure, validation and partial-initialization behaviour of `project init`."""

from fibery_fake import FakeFiberyWorkspace
from sdlc.fibery_workspace import FiberyError
from sdlc.project_init import initialize_project, project_document_paths
from sdlc.results import ResultCode

PROJECT_NAME = "SDLC"
RAW_PATH = "SDLC/Requirements/Raw"


# -- failures before anything durable exists -------------------------------


def test_existence_check_failure_is_a_read_failure():
    workspace = FakeFiberyWorkspace()
    workspace.failures["find_project_by_name"] = FiberyError("offline")

    result = initialize_project(workspace, PROJECT_NAME)

    assert result.code is ResultCode.FIBERY_READ_FAILED
    assert workspace.mutations == []
    assert "offline" in " ".join(result.details)


def test_code_uniqueness_check_failure_is_a_read_failure():
    workspace = FakeFiberyWorkspace()
    workspace.failures["count_projects_with_code"] = FiberyError("offline")

    result = initialize_project(workspace, PROJECT_NAME)

    assert result.code is ResultCode.FIBERY_READ_FAILED
    assert workspace.mutations == []


def test_project_creation_failure_is_a_write_failure_not_a_partial_init():
    workspace = FakeFiberyWorkspace()
    workspace.failures["create_project"] = FiberyError("denied")

    result = initialize_project(workspace, PROJECT_NAME)

    assert result.code is ResultCode.FIBERY_WRITE_FAILED
    assert result.created == ()
    assert workspace.mutations == []


# -- partial initialization ------------------------------------------------


def test_document_failure_after_the_project_exists_is_a_partial_init():
    workspace = FakeFiberyWorkspace()
    workspace.failing_document_paths = {RAW_PATH}

    result = initialize_project(workspace, PROJECT_NAME)

    assert result.code is ResultCode.PARTIAL_INIT
    assert ResultCode.DOCUMENT_STRUCTURE_CREATE_FAILED.value in result.failed


def test_partial_init_reports_exactly_what_became_durable():
    workspace = FakeFiberyWorkspace()
    workspace.failing_document_paths = {RAW_PATH}

    result = initialize_project(workspace, PROJECT_NAME)

    assert result.created == (
        "Project entity project-1",
        "Project State = Planned",
        "Document SDLC",
        "Document SDLC/Requirements",
    )


def test_partial_init_deletes_nothing():
    workspace = FakeFiberyWorkspace()
    workspace.failing_document_paths = {RAW_PATH}

    initialize_project(workspace, PROJECT_NAME)

    assert len(workspace.projects) == 1
    assert set(workspace.documents) == {"SDLC", "SDLC/Requirements"}


def test_partial_init_does_not_report_success():
    workspace = FakeFiberyWorkspace()
    workspace.failures["set_documents_root"] = FiberyError("denied")

    result = initialize_project(workspace, PROJECT_NAME)

    assert not result.is_normal
    assert result.code is ResultCode.PARTIAL_INIT
    assert len(workspace.documents) == len(project_document_paths(PROJECT_NAME))


def test_state_write_failure_is_a_partial_init():
    workspace = FakeFiberyWorkspace(known_states=())

    result = initialize_project(workspace, PROJECT_NAME)

    assert result.code is ResultCode.PARTIAL_INIT
    assert result.created == ("Project entity project-1",)


def test_description_write_failure_is_a_partial_init():
    workspace = FakeFiberyWorkspace()
    workspace.failures["set_project_description"] = FiberyError("denied")

    result = initialize_project(workspace, PROJECT_NAME, description="Bootstrap.")

    assert result.code is ResultCode.PARTIAL_INIT
    assert workspace.documents == {}


# -- post-create validation ------------------------------------------------


def test_state_that_did_not_take_effect_fails_validation():
    workspace = FakeFiberyWorkspace()
    workspace.ignore_state_writes = True

    result = initialize_project(workspace, PROJECT_NAME)

    assert result.code is ResultCode.VALIDATION_FAILED
    assert any("State" in detail for detail in result.details)


def test_unresolvable_documents_root_fails_validation():
    workspace = FakeFiberyWorkspace()
    workspace.failures["resolve_document"] = FiberyError("gone")

    result = initialize_project(workspace, PROJECT_NAME)

    assert result.code is ResultCode.VALIDATION_FAILED


def test_missing_document_fails_validation():
    workspace = FakeFiberyWorkspace()
    original_find = workspace.find_document

    def forget_raw(path):
        return None if path == RAW_PATH else original_find(path)

    workspace.find_document = forget_raw

    result = initialize_project(workspace, PROJECT_NAME)

    assert result.code is ResultCode.VALIDATION_FAILED
    assert any(RAW_PATH in detail for detail in result.details)


def test_code_that_is_not_globally_unique_fails_validation():
    workspace = FakeFiberyWorkspace()
    original_count = workspace.count_projects_with_code
    calls = {"n": 0}

    def duplicate_after_creation(code):
        calls["n"] += 1
        return original_count(code) if calls["n"] == 1 else 2

    workspace.count_projects_with_code = duplicate_after_creation

    result = initialize_project(workspace, PROJECT_NAME)

    assert result.code is ResultCode.VALIDATION_FAILED
    assert any("globally" in d or "expected exactly 1" in d for d in result.details)


def test_validation_read_failure_does_not_report_success():
    workspace = FakeFiberyWorkspace()
    workspace.failures["read_project"] = FiberyError("offline")

    result = initialize_project(workspace, PROJECT_NAME)

    assert result.code is ResultCode.VALIDATION_FAILED
    assert result.created


def test_validation_failure_still_reports_what_was_created():
    workspace = FakeFiberyWorkspace()
    workspace.ignore_state_writes = True

    result = initialize_project(workspace, PROJECT_NAME)

    assert "Project entity project-1" in result.created
    assert result.documents == tuple(project_document_paths(PROJECT_NAME))
