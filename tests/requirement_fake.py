"""In-memory RequirementWorkspace for deterministic `requirement add` tests.

Models the Fibery identity behaviour that actually bites:
- Documents attach to an entity by its PUBLIC ID, not its uuid;
- sibling Folders may share a name;
- Requirement Name is a read-only formula, so it is derived here too.
"""

from __future__ import annotations

import itertools

from sdlc.fibery_workspace import (
    DocumentNode,
    FiberyError,
    FolderNode,
    ProjectRecord,
    RequirementRecord,
)

RAW_TYPE = "Raw"
DRAFT_STATE = "Draft"
KNOWN_TYPES = ("Raw", "Standard")
KNOWN_STATES = ("Draft", "Process", "Review", "Ready", "Apply", "Applied")


class FakeRequirementWorkspace:
    """Records every call and mutation so tests can assert on both."""

    def __init__(
        self,
        projects: list[ProjectRecord] | None = None,
        folders: list[FolderNode] | None = None,
        requirements: list[RequirementRecord] | None = None,
    ) -> None:
        self.projects = list(projects or [])
        self.folders = list(folders or [])
        self.requirements = {r.id: r for r in requirements or []}
        self.documents: list[DocumentNode] = []
        self.content: dict[str, str] = {}
        self.mutations: list[str] = []
        self.calls: list[str] = []

        self.failures: dict[str, FiberyError] = {}
        # Simulate Fibery rejecting a uuid where a public id is required.
        self.reject_uuid_attachment = True

        self._ids = itertools.count(1)

    # -- projects and folders ------------------------------------------

    def find_project_by_code(self, code: str) -> ProjectRecord | None:
        self._record("find_project_by_code")
        return next((p for p in self.projects if p.code == code), None)

    def find_projects_by_name(self, name: str) -> list[ProjectRecord]:
        self._record("find_projects_by_name")
        return [p for p in self.projects if p.name == name]

    def resolve_folder(self, folder_id: str) -> FolderNode | None:
        self._record("resolve_folder")
        return next((f for f in self.folders if f.id == folder_id), None)

    def child_folders(self, parent_id: str) -> list[FolderNode]:
        self._record("child_folders")
        return [f for f in self.folders if f.parent_id == parent_id]

    # -- requirements ---------------------------------------------------

    def find_requirement_by_fingerprint(
        self, project_id: str, fingerprint: str
    ) -> RequirementRecord | None:
        self._record("find_requirement_by_fingerprint")
        return next(
            (
                r
                for r in self.requirements.values()
                if r.project_id == project_id and r.source_fingerprint == fingerprint
            ),
            None,
        )

    def requirement_ids_in_project(self, project_id: str) -> list[str]:
        self._record("requirement_ids_in_project")
        return [
            r.requirement_id
            for r in self.requirements.values()
            if r.project_id == project_id and r.requirement_id
        ]

    def count_requirements_with_requirement_id(self, requirement_id: str) -> int:
        self._record("count_requirements_with_requirement_id")
        return sum(
            1 for r in self.requirements.values() if r.requirement_id == requirement_id
        )

    def create_requirement(
        self,
        project_id: str,
        requirement_id: str,
        title: str,
        revision: int,
        fingerprint: str,
    ) -> RequirementRecord:
        self._record("create_requirement")
        number = next(self._ids)
        record = RequirementRecord(
            id=f"requirement-{number}",
            public_id=str(number),
            requirement_id=requirement_id,
            title=title,
            type_name=None,
            state=DRAFT_STATE,
            revision=revision,
            project_id=project_id,
            source_fingerprint=fingerprint,
        )
        self.requirements[record.id] = record
        self.mutations.append(f"create_requirement {requirement_id}")
        return record

    def set_requirement_type(self, requirement_id: str, type_name: str) -> None:
        self._record("set_requirement_type")
        if type_name not in KNOWN_TYPES:
            raise FiberyError(f"Unknown Type {type_name!r}.")
        self.mutations.append(f"set_requirement_type {type_name}")
        self._replace(requirement_id, type_name=type_name)

    def set_requirement_state(self, requirement_id: str, state: str) -> None:
        self._record("set_requirement_state")
        if state not in KNOWN_STATES:
            raise FiberyError(f"Unknown state {state!r}.")
        self.mutations.append(f"set_requirement_state {state}")
        self._replace(requirement_id, state=state)

    def read_requirement(self, requirement_id: str) -> RequirementRecord | None:
        self._record("read_requirement")
        return self.requirements.get(requirement_id)

    # -- documents ------------------------------------------------------

    def create_requirement_document(
        self, name: str, folder_id: str, requirement_public_id: str
    ) -> DocumentNode:
        self._record("create_requirement_document")
        known_public = {r.public_id for r in self.requirements.values()}
        if self.reject_uuid_attachment and requirement_public_id not in known_public:
            # Exactly how Fibery fails when handed a uuid.
            raise FiberyError("specified parent entity was not found")
        number = next(self._ids)
        document = DocumentNode(
            id=f"document-{number}",
            name=name,
            folder_id=folder_id,
            entity_public_id=requirement_public_id,
            secret=f"secret-{number}",
        )
        self.documents.append(document)
        self.content[document.secret] = ""
        self.mutations.append(f"create_document {name} folder={folder_id}")
        return document

    def resolve_document(self, document_id: str) -> DocumentNode | None:
        self._record("resolve_document")
        return next((d for d in self.documents if d.id == document_id), None)

    def documents_attached_to_requirement(self, public_id: str) -> list[DocumentNode]:
        self._record("documents_attached_to_requirement")
        return [d for d in self.documents if d.entity_public_id == public_id]

    def write_document_content(self, secret: str, markdown: str) -> None:
        self._record("write_document_content")
        self.mutations.append(f"write_document_content {secret}")
        self.content[secret] = markdown

    def read_document_content(self, secret: str) -> str:
        self._record("read_document_content")
        return self.content.get(secret, "")

    # -- helpers ---------------------------------------------------------

    def folder_named(self, name: str, parent_id: str | None) -> list[FolderNode]:
        return [f for f in self.folders if f.name == name and f.parent_id == parent_id]

    def _record(self, method: str) -> None:
        self.calls.append(method)
        failure = self.failures.pop(method, None)
        if failure is not None:
            raise failure

    def _replace(self, requirement_id: str, **changes: object) -> None:
        current = self.requirements[requirement_id]
        self.requirements[requirement_id] = RequirementRecord(
            id=current.id,
            public_id=current.public_id,
            requirement_id=current.requirement_id,
            title=current.title,
            type_name=changes.get("type_name", current.type_name),
            state=changes.get("state", current.state),
            revision=current.revision,
            project_id=current.project_id,
            source_fingerprint=current.source_fingerprint,
        )


def project_with_structure(
    project_id: str = "project-1",
    name: str = "SDLC",
    code: str = "SDLC",
) -> tuple[ProjectRecord, list[FolderNode]]:
    """A Project plus the real folder tree `project init` would have created."""
    root = FolderNode(id="folder-root", name=name, parent_id=None)
    requirements = FolderNode(
        id="folder-requirements", name="Requirements", parent_id=root.id
    )
    stages = [
        FolderNode(id=f"folder-{stage.lower()}", name=stage, parent_id=requirements.id)
        for stage in ("Raw", "Draft", "Approved")
    ]
    project = ProjectRecord(
        id=project_id,
        name=name,
        code=code,
        state="Planned",
        documents_root_folder_id=root.id,
    )
    return project, [root, requirements, *stages]
