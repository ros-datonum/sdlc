"""The boundary between deterministic `project init` behaviour and Fibery.

Everything the command needs from Fibery is expressed here. `project_init`
depends only on this protocol, so its behaviour is testable without a live
workspace.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class FiberyError(Exception):
    """Any failure while talking to Fibery."""


@dataclass(frozen=True)
class ProjectRecord:
    """A Project entity as read back from Fibery."""

    id: str
    name: str
    code: str | None
    state: str | None
    documents_root_folder_id: str | None


@dataclass(frozen=True)
class RequirementRecord:
    """A Requirement entity as read back from Fibery."""

    id: str
    public_id: str
    requirement_id: str | None
    title: str | None
    type_name: str | None
    state: str | None
    revision: int | None
    project_id: str | None
    source_fingerprint: str | None


@dataclass(frozen=True)
class DocumentNode:
    """One Fibery Document (a View of type "document").

    `folder_id` is the Folder it sits in; `entity_public_id` is the public id of
    the entity it is attached to, which is how Fibery models the Documents
    field. Both are None when Fibery has not set them.
    """

    id: str
    name: str
    folder_id: str | None
    entity_public_id: str | None
    secret: str | None = None
    parent_document_id: str | None = None


@dataclass(frozen=True)
class FolderNode:
    """One Fibery Folder in the Project document structure.

    Folders are the real hierarchy: a Folder nests under another through
    `fibery/Parent Folder`, and `parent_id` is None at the Project root.
    """

    id: str
    name: str
    parent_id: str | None


class FiberyWorkspace(Protocol):
    """Operations `project init` performs against a Fibery workspace."""

    def find_project_by_name(self, name: str) -> ProjectRecord | None:
        """Return the Project with this exact Name, or None."""

    def count_projects_with_code(self, code: str) -> int:
        """Count Projects carrying this Code.

        Implementations may saturate the count: callers only distinguish
        none, exactly one, and more than one.
        """

    def create_project(self, name: str, code: str) -> str:
        """Create the Project entity and return its id."""

    def set_project_state(self, project_id: str, state: str) -> None:
        """Set the Project workflow state by state name."""

    def set_project_description(self, project_id: str, description: str) -> None:
        """Replace the Project Description rich text with Markdown."""

    def create_folder(self, name: str, parent_id: str | None) -> FolderNode:
        """Create one Folder, nested under parent_id when it is not None."""

    def resolve_folder(self, folder_id: str) -> FolderNode | None:
        """Read one Folder back by its own id, or None if it is gone.

        Fibery allows sibling Folders with identical names, so this is the
        only unambiguous way to verify a Folder this run created. Name-based
        lookup is for discovery, never for read-back.
        """

    def set_documents_root_folder(self, project_id: str, folder_id: str) -> None:
        """Store the root Folder id on the Project."""

    def read_project(self, project_id: str) -> ProjectRecord | None:
        """Read a Project entity back by id."""


class RequirementWorkspace(Protocol):
    """Operations `project requirement add` performs against Fibery.

    Kept separate from FiberyWorkspace so the frozen `project init` contract
    stays exactly as reviewed.
    """

    def find_project_by_code(self, code: str) -> ProjectRecord | None:
        """Return the Project with this exact Code, or None."""

    def find_projects_by_name(self, name: str) -> list[ProjectRecord]:
        """Every Project with this exact Name, so ambiguity can be detected."""

    def resolve_folder(self, folder_id: str) -> FolderNode | None:
        """Read one Folder back by its own id, or None if it is gone."""

    def child_folders(self, parent_id: str) -> list[FolderNode]:
        """Every Folder directly under this parent.

        Returns all of them rather than one match by name: Fibery permits
        sibling Folders sharing a name, and the caller must treat that as an
        invalid structure rather than silently picking one.
        """

    def find_requirement_by_fingerprint(
        self, project_id: str, fingerprint: str
    ) -> RequirementRecord | None:
        """The Requirement already ingested from this source, if any."""

    def create_requirement(
        self, project_id: str, title: str, revision: int, fingerprint: str
    ) -> RequirementRecord:
        """Create the Requirement entity and return it, including its public id.

        The Requirement ID is not supplied: it is derived from the public id
        Fibery allocates here, then written by set_requirement_id.
        """

    def set_requirement_id(self, entity_id: str, requirement_id: str) -> None:
        """Write the derived Requirement ID onto the created entity."""

    def set_requirement_type(self, requirement_id: str, type_name: str) -> None:
        """Set the Type single-select by option name."""

    def set_requirement_state(self, requirement_id: str, state: str) -> None:
        """Set the Requirement workflow state by state name."""

    def read_requirement(self, requirement_id: str) -> RequirementRecord | None:
        """Read a Requirement entity back by id."""

    def create_requirement_document(
        self, name: str, folder_id: str, requirement_public_id: str
    ) -> DocumentNode:
        """Create the Root Document in a Folder, attached to the Requirement."""

    def resolve_document(self, document_id: str) -> DocumentNode | None:
        """Read one Document back by its own id, or None."""

    def documents_attached_to_requirement(self, public_id: str) -> list[DocumentNode]:
        """Every Document attached to this Requirement, for the count-of-1 check."""

    def write_document_content(self, secret: str, markdown: str) -> None:
        """Replace a Document's Markdown content."""

    def read_document_content(self, secret: str) -> str:
        """Read a Document's Markdown content back."""


class RawProcessorWorkspace(Protocol):
    """Operations the RAW Requirement Processor performs against Fibery.

    Kept separate from the frozen capabilities' protocols so their reviewed
    contracts stay exactly as they are.
    """

    def read_requirement(self, entity_id: str) -> RequirementRecord | None:
        """Read one Requirement entity by id."""

    def find_requirement_by_requirement_id(
        self, requirement_id: str
    ) -> RequirementRecord | None:
        """Resolve a Requirement by its human Requirement ID."""

    def read_project(self, project_id: str) -> ProjectRecord | None:
        """Read the Project a Requirement belongs to."""

    def documents_attached_to_requirement(self, public_id: str) -> list[DocumentNode]:
        """Documents attached to this Requirement entity."""

    def child_documents(self, parent_document_id: str) -> list[DocumentNode]:
        """Documents nested directly under this Document."""

    def read_document_content(self, secret: str) -> str:
        """Read a Document's Markdown content."""

    def write_document_content(self, secret: str, markdown: str) -> None:
        """Replace a Document's Markdown content."""

    def create_child_document(self, name: str, parent_document_id: str) -> DocumentNode:
        """Create a Document nested under another Document."""

    def standard_requirements_in_project(
        self, project_id: str
    ) -> list[RequirementRecord]:
        """Existing Standard Requirements, for duplicate/conflict findings."""

    def create_requirement_with_id(
        self,
        entity_id: str,
        project_id: str,
        title: str,
        revision: int,
        category: str,
    ) -> RequirementRecord:
        """Create a Standard Requirement at an exact, caller-chosen entity id.

        Fibery rejects a second create at the same id, which is what makes a
        retry safe.
        """

    def set_requirement_id(self, entity_id: str, requirement_id: str) -> None:
        """Write the derived Requirement ID onto the entity."""

    def set_requirement_type(self, entity_id: str, type_name: str) -> None:
        """Set the Type single-select by option name."""

    def set_requirement_state(self, entity_id: str, state: str) -> None:
        """Set the Requirement workflow state by state name."""

    def add_derived_from(self, entity_id: str, raw_entity_id: str) -> None:
        """Link a Standard Requirement to the RAW it came from.

        Fibery populates the inverse `Produces` automatically. Collections
        cannot be written during entity creation, so this is a separate call.
        """

    def create_requirement_document(
        self, name: str, folder_id: str, requirement_public_id: str
    ) -> DocumentNode:
        """Create a Root Document in a Folder, attached to a Requirement."""

    def resolve_document(self, document_id: str) -> DocumentNode | None:
        """Read one Document back by id."""

    def resolve_folder(self, folder_id: str) -> FolderNode | None:
        """Read one Folder back by id."""

    def child_folders(self, parent_id: str) -> list[FolderNode]:
        """Folders directly under this parent."""
