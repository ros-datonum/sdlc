"""In-memory ArchitectureWorkspace for deterministic TSA adapter tests.

Models the Fibery identity behaviour that actually bites, and nothing else:

- a Project has an entity uuid AND a separate public id; a contained Document's
  container-entity-id carries the PUBLIC id;
- `container-entity-type` carries the Project **Database's** type id, which is
  neither the Database name nor any entity id;
- a TSA Document is created at the id the caller supplies, never a generated
  one;
- a nested Document carries `parent-page-id` and no Project container of its
  own;
- an unset container field stays unset and is never inferred.

Transport and state simulation only. It models no cycle, no manifest, no
recovery, no Architect or Reviewer, and no human decision: those belong to later
work items and a fake that knew about them would let a test pass for the wrong
reason.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, replace

from sdlc.fibery_workspace import (
    DocumentNode,
    DocumentPlacement,
    FiberyError,
    ProjectRecord,
)

PROJECT_TYPE_ID = "7c9f1b5e-2a44-4c8d-9f31-0b6e5d2a4c10"
OTHER_DATABASE_TYPE_ID = "11111111-2222-4333-8444-555555555555"
WORKSPACE_IDENTITY = "example.fibery.io/0f0e0d0c-0b0a-4908-8706-050403020100"


@dataclass
class StoredDocument:
    """One Document exactly as the Views API would report it."""

    document_id: str
    name: str
    secret: str
    container_entity_type: str | None = None
    container_entity_id: str | None = None
    parent_document_id: str | None = None


class FakeArchitectureWorkspace:
    """Records every call and mutation so tests can assert on both."""

    def __init__(
        self,
        projects: list[ProjectRecord] | None = None,
        project_type_id: str = PROJECT_TYPE_ID,
    ) -> None:
        self.projects = {project.id: project for project in projects or []}
        self.project_type_id = project_type_id
        self.documents: dict[str, StoredDocument] = {}
        self.content: dict[str, str] = {}
        self.calls: list[str] = []
        self.mutations: list[str] = []
        self.failures: dict[str, FiberyError] = {}
        # Set to drop the created Document, so a caller can exercise the
        # read-back failure the real adapter raises on.
        self.swallow_creates = False
        self._secrets = itertools.count(1)

    # -- identity -------------------------------------------------------

    @property
    def lock_scope(self) -> str:
        return WORKSPACE_IDENTITY

    def read_project(self, project_id: str) -> ProjectRecord | None:
        self._record("read_project")
        return self.projects.get(project_id)

    # -- creates --------------------------------------------------------

    def create_project_document(
        self, document_id: str, name: str, project_public_id: str
    ) -> DocumentNode:
        self._record("create_project_document")
        return self._create(
            document_id,
            name,
            container_entity_type=self.project_type_id,
            container_entity_id=project_public_id,
        )

    def create_tsa_child_document(
        self, document_id: str, name: str, parent_document_id: str
    ) -> DocumentNode:
        self._record("create_tsa_child_document")
        if parent_document_id not in self.documents:
            raise FiberyError(f"No Document {parent_document_id!r} to nest under.")
        return self._create(document_id, name, parent_document_id=parent_document_id)

    def create_child_document(self, name: str, parent_document_id: str) -> DocumentNode:
        """The legacy creator: generates its own id, as the real one does."""
        self._record("create_child_document")
        if parent_document_id not in self.documents:
            raise FiberyError(f"No Document {parent_document_id!r} to nest under.")
        return self._create(
            f"generated-{next(self._secrets)}",
            name,
            parent_document_id=parent_document_id,
        )

    def child_documents(self, parent_document_id: str) -> list[DocumentNode]:
        self._record("child_documents")
        return [
            _to_node(stored)
            for stored in self.documents.values()
            if stored.parent_document_id == parent_document_id
        ]

    def _create(
        self, document_id: str, name: str, **placement: str | None
    ) -> DocumentNode:
        if document_id in self.documents:
            # Live-confirmed by P-1 (I03): `create-views` rejects a duplicate
            # caller-supplied `fibery/id` and leaves the existing Document
            # untouched — name, placement and content all unchanged. That is
            # what makes a retry at a deterministic id safe after an unknown
            # write outcome. Evidence:
            # docs/specs/TSA-C01-I03-P1-Live-Evidence-v0.1.md
            raise FiberyError(f"Document {document_id!r} already exists.")
        self.mutations.append(f"create:{document_id}")
        if self.swallow_creates:
            raise FiberyError(f"The created Document {name!r} could not be read back.")
        stored = StoredDocument(
            document_id=document_id,
            name=name,
            secret=f"secret-{next(self._secrets)}",
            **placement,
        )
        self.documents[document_id] = stored
        self.content[stored.secret] = ""
        return _to_node(stored)

    # -- placement reads ------------------------------------------------

    def documents_attached_to_project(
        self, project_public_id: str
    ) -> list[DocumentPlacement]:
        self._record("documents_attached_to_project")
        return [
            _to_placement(stored)
            for stored in self.documents.values()
            if stored.container_entity_id == project_public_id
            and stored.container_entity_type == self.project_type_id
        ]

    def child_placements(self, parent_document_id: str) -> list[DocumentPlacement]:
        self._record("child_placements")
        return [
            _to_placement(stored)
            for stored in self.documents.values()
            if stored.parent_document_id == parent_document_id
        ]

    def resolve_placement(self, document_id: str) -> DocumentPlacement | None:
        self._record("resolve_placement")
        stored = self.documents.get(document_id)
        return _to_placement(stored) if stored else None

    def resolve_document(self, document_id: str) -> DocumentNode | None:
        self._record("resolve_document")
        stored = self.documents.get(document_id)
        return _to_node(stored) if stored else None

    # -- content --------------------------------------------------------

    def read_document_content(self, secret: str) -> str:
        self._record("read_document_content")
        if secret not in self.content:
            raise FiberyError(f"No Document content at secret {secret!r}.")
        return self.content[secret]

    def write_document_content(self, secret: str, markdown: str) -> None:
        self._record("write_document_content")
        if secret not in self.content:
            raise FiberyError(f"No Document content at secret {secret!r}.")
        self.mutations.append(f"write:{secret}")
        self.content[secret] = markdown

    # -- test helpers ---------------------------------------------------

    def place_foreign_document(self, document_id: str, **placement: str | None) -> None:
        """Seed a Document with arbitrary placement, including a foreign one."""
        stored = StoredDocument(
            document_id=document_id,
            name=document_id,
            secret=f"secret-{next(self._secrets)}",
            **placement,
        )
        self.documents[document_id] = stored
        self.content[stored.secret] = ""

    def _record(self, call: str) -> None:
        self.calls.append(call)
        failure = self.failures.get(call)
        if failure is not None:
            raise failure


def _to_node(stored: StoredDocument) -> DocumentNode:
    return DocumentNode(
        id=stored.document_id,
        name=stored.name,
        folder_id=None,
        entity_public_id=stored.container_entity_id,
        secret=stored.secret,
        parent_document_id=stored.parent_document_id,
    )


def _to_placement(stored: StoredDocument) -> DocumentPlacement:
    return DocumentPlacement(
        document_id=stored.document_id,
        secret=stored.secret,
        name=stored.name,
        container_entity_type=stored.container_entity_type,
        container_entity_id=stored.container_entity_id,
        parent_document_id=stored.parent_document_id,
    )


def project(
    project_id: str = "project-1",
    public_id: str = "7",
    name: str = "SDLC",
    code: str = "SDLC",
) -> ProjectRecord:
    """A Project whose uuid and public id are deliberately different values."""
    return ProjectRecord(
        id=project_id, name=name, code=code, state="Planned", public_id=public_id
    )


def with_public_id(record: ProjectRecord, public_id: str) -> ProjectRecord:
    return replace(record, public_id=public_id)
