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
    documents_root: str | None


@dataclass(frozen=True)
class DocumentNode:
    """One node of the Project document structure."""

    id: str
    path: str


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

    def create_document(self, path: str) -> DocumentNode:
        """Create one document structure node addressed by its path."""

    def find_document(self, path: str) -> DocumentNode | None:
        """Return the document structure node at this path, or None."""

    def set_documents_root(self, project_id: str, document_id: str) -> None:
        """Store the document root reference on the Project."""

    def read_project(self, project_id: str) -> ProjectRecord | None:
        """Read a Project entity back by id."""

    def resolve_document(self, document_id: str) -> DocumentNode | None:
        """Resolve a stored document reference back to its node, or None."""
