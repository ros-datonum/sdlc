"""Failure, validation and partial-add behaviour of `project requirement add`."""

from raw_fixtures import VALID_SOURCE
from requirement_fake import FakeRequirementWorkspace, project_with_structure
from sdlc.fibery_workspace import DocumentNode, FiberyError, RequirementRecord
from sdlc.raw_source import parse_raw_requirement
from sdlc.requirement_add import add_raw_requirement
from sdlc.results import AddResultCode


def workspace_with_project():
    project, folders = project_with_structure()
    return FakeRequirementWorkspace(projects=[project], folders=folders), project


# -- failures before anything durable exists -------------------------------


def test_project_lookup_failure_is_a_read_failure():
    workspace, _ = workspace_with_project()
    workspace.failures["find_project_by_code"] = FiberyError("offline")

    result = add_raw_requirement(workspace, "SDLC", VALID_SOURCE)

    assert result.code is AddResultCode.FIBERY_READ_FAILED
    assert workspace.mutations == []


def test_duplicate_check_failure_is_a_read_failure():
    workspace, _ = workspace_with_project()
    workspace.failures["find_requirement_by_fingerprint"] = FiberyError("offline")

    result = add_raw_requirement(workspace, "SDLC", VALID_SOURCE)

    assert result.code is AddResultCode.FIBERY_READ_FAILED
    assert workspace.mutations == []


def test_id_allocation_read_failure_has_its_own_result():
    workspace, _ = workspace_with_project()
    workspace.failures["requirement_ids_in_project"] = FiberyError("offline")

    result = add_raw_requirement(workspace, "SDLC", VALID_SOURCE)

    assert result.code is AddResultCode.REQUIREMENT_ID_ALLOCATION_FAILED
    assert workspace.mutations == []


def test_requirement_create_failure_is_not_a_partial_add():
    workspace, _ = workspace_with_project()
    workspace.failures["create_requirement"] = FiberyError("denied")

    result = add_raw_requirement(workspace, "SDLC", VALID_SOURCE)

    assert result.code is AddResultCode.FIBERY_WRITE_FAILED
    assert result.created == ()
    assert workspace.mutations == []


# -- partial add -----------------------------------------------------------


def test_document_create_failure_after_the_requirement_exists_is_a_partial_add():
    workspace, _ = workspace_with_project()
    workspace.failures["create_requirement_document"] = FiberyError("denied")

    result = add_raw_requirement(workspace, "SDLC", VALID_SOURCE)

    assert result.code is AddResultCode.PARTIAL_ADD
    assert AddResultCode.DOCUMENT_CREATE_FAILED.value in result.failed


def test_partial_add_reports_exactly_what_became_durable():
    workspace, _ = workspace_with_project()
    workspace.failures["create_requirement_document"] = FiberyError("denied")

    result = add_raw_requirement(workspace, "SDLC", VALID_SOURCE)

    assert result.created == (
        "Requirement entity SDLC-RAW-0001 (requirement-1)",
        "Requirement Type = Raw",
        "Requirement State = Draft",
    )


def test_partial_add_deletes_nothing():
    workspace, _ = workspace_with_project()
    workspace.failures["write_document_content"] = FiberyError("denied")

    result = add_raw_requirement(workspace, "SDLC", VALID_SOURCE)

    assert result.code is AddResultCode.PARTIAL_ADD
    assert len(workspace.requirements) == 1
    assert len(workspace.documents) == 1


def test_content_write_failure_has_its_own_failure_class():
    workspace, _ = workspace_with_project()
    workspace.failures["write_document_content"] = FiberyError("denied")

    result = add_raw_requirement(workspace, "SDLC", VALID_SOURCE)

    assert AddResultCode.CONTENT_WRITE_FAILED.value in result.failed


def test_type_write_failure_is_a_partial_add():
    workspace, _ = workspace_with_project()
    workspace.failures["set_requirement_type"] = FiberyError("denied")

    result = add_raw_requirement(workspace, "SDLC", VALID_SOURCE)

    assert result.code is AddResultCode.PARTIAL_ADD
    assert result.created == ("Requirement entity SDLC-RAW-0001 (requirement-1)",)


def test_attachment_to_the_wrong_entity_is_an_attachment_failure():
    workspace, _ = workspace_with_project()
    original = workspace.create_requirement_document

    def attach_elsewhere(name, folder_id, requirement_public_id):
        document = original(name, folder_id, requirement_public_id)
        wrong = DocumentNode(
            id=document.id,
            name=document.name,
            folder_id=document.folder_id,
            entity_public_id="999",
            secret=document.secret,
        )
        workspace.documents[-1] = wrong
        return wrong

    workspace.create_requirement_document = attach_elsewhere

    result = add_raw_requirement(workspace, "SDLC", VALID_SOURCE)

    assert result.code is AddResultCode.PARTIAL_ADD
    assert AddResultCode.DOCUMENT_ATTACHMENT_FAILED.value in result.failed


# -- post-write validation -------------------------------------------------


def test_type_that_did_not_take_effect_fails_validation():
    workspace, _ = workspace_with_project()
    workspace.set_requirement_type = lambda *_: None

    result = add_raw_requirement(workspace, "SDLC", VALID_SOURCE)

    assert result.code is AddResultCode.VALIDATION_FAILED
    assert any("Type" in detail for detail in result.details)


def test_state_that_did_not_take_effect_fails_validation():
    workspace, _ = workspace_with_project()
    workspace.set_requirement_state = lambda *_: None
    workspace.requirements = {}
    project, folders = project_with_structure()
    workspace.projects = [project]
    workspace.folders = folders
    original = workspace.create_requirement

    def created_in_wrong_state(**kwargs):
        record = original(**kwargs)
        workspace.requirements[record.id] = RequirementRecord(
            **{**record.__dict__, "state": "Applied"}
        )
        return workspace.requirements[record.id]

    workspace.create_requirement = created_in_wrong_state

    result = add_raw_requirement(workspace, "SDLC", VALID_SOURCE)

    assert result.code is AddResultCode.VALIDATION_FAILED
    assert any("State" in detail for detail in result.details)


def test_content_that_did_not_persist_fails_validation():
    workspace, _ = workspace_with_project()
    workspace.write_document_content = lambda secret, markdown: None

    result = add_raw_requirement(workspace, "SDLC", VALID_SOURCE)

    assert result.code is AddResultCode.VALIDATION_FAILED
    assert any("content" in detail for detail in result.details)


def test_requirement_id_that_is_not_unique_fails_validation():
    workspace, _ = workspace_with_project()
    workspace.count_requirements_with_requirement_id = lambda _: 2

    result = add_raw_requirement(workspace, "SDLC", VALID_SOURCE)

    assert result.code is AddResultCode.VALIDATION_FAILED
    assert any("expected exactly 1" in detail for detail in result.details)


def test_document_in_the_wrong_folder_fails_validation():
    workspace, _ = workspace_with_project()
    original = workspace.resolve_document

    def moved(document_id):
        found = original(document_id)
        return DocumentNode(
            id=found.id,
            name=found.name,
            folder_id="folder-draft",
            entity_public_id=found.entity_public_id,
            secret=found.secret,
        )

    workspace.resolve_document = moved

    result = add_raw_requirement(workspace, "SDLC", VALID_SOURCE)

    assert result.code is AddResultCode.VALIDATION_FAILED
    assert any("Requirements/Raw" in detail for detail in result.details)


def test_more_than_one_attached_document_fails_validation():
    """The Requirement document invariant is exactly one Root Document."""
    workspace, _ = workspace_with_project()
    original = workspace.documents_attached_to_requirement

    def two(public_id):
        found = original(public_id)
        return [*found, DocumentNode("extra", "Extra", "folder-raw", public_id, "s")]

    workspace.documents_attached_to_requirement = two

    result = add_raw_requirement(workspace, "SDLC", VALID_SOURCE)

    assert result.code is AddResultCode.VALIDATION_FAILED
    assert any("Documents" in detail for detail in result.details)


def test_validation_read_failure_does_not_report_success():
    workspace, _ = workspace_with_project()
    workspace.failures["read_requirement"] = FiberyError("offline")

    result = add_raw_requirement(workspace, "SDLC", VALID_SOURCE)

    assert result.code is AddResultCode.VALIDATION_FAILED
    assert result.created


def test_validation_failure_still_reports_what_was_created():
    workspace, _ = workspace_with_project()
    workspace.write_document_content = lambda secret, markdown: None

    result = add_raw_requirement(workspace, "SDLC", VALID_SOURCE)

    assert not result.is_normal
    assert any("Requirement entity" in item for item in result.created)


def test_fingerprint_mismatch_fails_validation():
    workspace, _ = workspace_with_project()
    original = workspace.read_requirement

    def wrong_fingerprint(requirement_id):
        found = original(requirement_id)
        return RequirementRecord(**{**found.__dict__, "source_fingerprint": "tampered"})

    workspace.read_requirement = wrong_fingerprint

    result = add_raw_requirement(workspace, "SDLC", VALID_SOURCE)

    assert result.code is AddResultCode.VALIDATION_FAILED
    assert any("Fingerprint" in detail for detail in result.details)


def test_stored_body_is_what_the_fingerprint_covers():
    workspace, _ = workspace_with_project()

    add_raw_requirement(workspace, "SDLC", VALID_SOURCE)

    [record] = workspace.requirements.values()
    [document] = workspace.documents
    parsed = parse_raw_requirement(VALID_SOURCE)
    assert workspace.content[document.secret] == parsed.body
    assert record.source_fingerprint == parsed.fingerprint
