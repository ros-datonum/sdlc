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
