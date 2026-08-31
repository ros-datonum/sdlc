"""In-memory FiberyWorkspace used to test deterministic `project init` behaviour."""

from __future__ import annotations

import itertools

from sdlc.fibery_workspace import DocumentNode, FiberyError, ProjectRecord

PLANNED_STATE = "Planned"


class FakeFiberyWorkspace:
    """Records every call and mutation so tests can assert on both."""

    def __init__(
        self,
        projects: list[ProjectRecord] | None = None,
        documents: list[DocumentNode] | None = None,
        known_states: tuple[str, ...] = (PLANNED_STATE,),
    ) -> None:
        self.projects = {record.id: record for record in projects or []}
        self.documents = {node.path: node for node in documents or []}
        self.descriptions: dict[str, str] = {}
        self.known_states = known_states
        self.mutations: list[str] = []
        self.calls: list[str] = []

        # Fault injection.
        self.failures: dict[str, FiberyError] = {}
        self.failing_document_paths: set[str] = set()
        # Simulate a write that silently did not take effect.
        self.ignore_state_writes = False

        self._ids = itertools.count(1)

    # -- reads ---------------------------------------------------------

    def find_project_by_name(self, name: str) -> ProjectRecord | None:
        self._record_call("find_project_by_name")
        return next(
            (record for record in self.projects.values() if record.name == name), None
        )

    def count_projects_with_code(self, code: str) -> int:
        self._record_call("count_projects_with_code")
        return sum(1 for record in self.projects.values() if record.code == code)

    def read_project(self, project_id: str) -> ProjectRecord | None:
        self._record_call("read_project")
        return self.projects.get(project_id)

    def find_document(self, path: str) -> DocumentNode | None:
        self._record_call("find_document")
        return self.documents.get(path)

    def resolve_document(self, document_id: str) -> DocumentNode | None:
        self._record_call("resolve_document")
        return next(
            (node for node in self.documents.values() if node.id == document_id), None
        )

    # -- writes --------------------------------------------------------

    def create_project(self, name: str, code: str) -> str:
        self._record_call("create_project")
        project_id = f"project-{next(self._ids)}"
        self.projects[project_id] = ProjectRecord(
            id=project_id, name=name, code=code, state=None, documents_root=None
        )
        self.mutations.append(f"create_project {name} {code}")
        return project_id

    def set_project_state(self, project_id: str, state: str) -> None:
        self._record_call("set_project_state")
        if state not in self.known_states:
            raise FiberyError(f"Unknown state {state!r}.")
        self.mutations.append(f"set_project_state {project_id} {state}")
        if self.ignore_state_writes:
            return
        self._replace(project_id, state=state)

    def set_project_description(self, project_id: str, description: str) -> None:
        self._record_call("set_project_description")
        self.mutations.append(f"set_project_description {project_id}")
        self.descriptions[project_id] = description

    def create_document(self, path: str) -> DocumentNode:
        self._record_call("create_document")
        if path in self.failing_document_paths:
            raise FiberyError(f"Refusing to create {path!r}.")
        node = DocumentNode(id=f"document-{next(self._ids)}", path=path)
        self.documents[path] = node
        self.mutations.append(f"create_document {path}")
        return node

    def set_documents_root(self, project_id: str, document_id: str) -> None:
        self._record_call("set_documents_root")
        self.mutations.append(f"set_documents_root {project_id} {document_id}")
        self._replace(project_id, documents_root=document_id)

    # -- helpers -------------------------------------------------------

    def _record_call(self, method: str) -> None:
        self.calls.append(method)
        failure = self.failures.pop(method, None)
        if failure is not None:
            raise failure

    def _replace(self, project_id: str, **changes: object) -> None:
        current = self.projects[project_id]
        self.projects[project_id] = ProjectRecord(
            id=current.id,
            name=changes.get("name", current.name),
            code=changes.get("code", current.code),
            state=changes.get("state", current.state),
            documents_root=changes.get("documents_root", current.documents_root),
        )


def planned_project(
    project_id: str = "existing-1",
    name: str = "SDLC",
    code: str = "SDLC",
    documents_root: str | None = "document-root",
) -> ProjectRecord:
    return ProjectRecord(
        id=project_id,
        name=name,
        code=code,
        state=PLANNED_STATE,
        documents_root=documents_root,
    )
