"""In-memory doubles for RAW processing tests.

Models the Fibery behaviour that actually constrains the design:
- a second create at the same fibery/id is rejected;
- collections cannot be written during entity creation;
- documents nest under documents;
- documents attach to entities by public id.
"""

from __future__ import annotations

import itertools
import json

from sdlc.fibery_workspace import (
    DocumentNode,
    FiberyError,
    FolderNode,
    ProjectRecord,
    RequirementRecord,
)
from sdlc.model_runtime import ModelResponse

KNOWN_TYPES = ("Raw", "Standard")
KNOWN_STATES = ("Draft", "Process", "Review", "Ready", "Apply", "Applied")


class FakeModelRuntime:
    """Returns canned model output and records every invocation."""

    def __init__(self, responses=None, error: Exception | None = None):
        self.responses = list(responses or [])
        self.error = error
        self.calls: list[dict[str, str]] = []

    def run(self, prompt: str, context: str = "") -> ModelResponse:
        self.calls.append({"prompt": prompt, "context": context})
        if self.error is not None:
            raise self.error
        text = self.responses.pop(0) if self.responses else "{}"
        return ModelResponse(text=text, runtime="fake", model=None)

    @property
    def was_invoked(self) -> bool:
        return bool(self.calls)


class FakeProcessorWorkspace:
    """Records calls and mutations so tests can assert on both."""

    def __init__(self, project: ProjectRecord, folders, requirements=None):
        self.project = project
        self.folders = list(folders)
        self.requirements = {r.id: r for r in (requirements or [])}
        self.documents: list[DocumentNode] = []
        self.content: dict[str, str] = {}
        self.derived_from: dict[str, list[str]] = {}
        self.mutations: list[str] = []
        self.calls: list[str] = []
        self.failures: dict[str, FiberyError] = {}
        self._ids = itertools.count(1)
        self._public = itertools.count(30)

    # -- reads ----------------------------------------------------------

    def read_requirement(self, entity_id):
        self._record("read_requirement")
        return self.requirements.get(entity_id)

    def find_requirement_by_requirement_id(self, requirement_id):
        self._record("find_requirement_by_requirement_id")
        return next(
            (
                r
                for r in self.requirements.values()
                if r.requirement_id == requirement_id
            ),
            None,
        )

    def read_project(self, project_id):
        self._record("read_project")
        return self.project if self.project.id == project_id else None

    def documents_attached_to_requirement(self, public_id):
        self._record("documents_attached_to_requirement")
        return [d for d in self.documents if d.entity_public_id == public_id]

    def child_documents(self, parent_document_id):
        self._record("child_documents")
        return [d for d in self.documents if d.parent_document_id == parent_document_id]

    def read_document_content(self, secret):
        self._record("read_document_content")
        return self.content.get(secret, "")

    def standard_requirements_in_project(self, project_id):
        self._record("standard_requirements_in_project")
        return [
            r
            for r in self.requirements.values()
            if r.project_id == project_id and r.type_name == "Standard"
        ]

    def resolve_document(self, document_id):
        self._record("resolve_document")
        return next((d for d in self.documents if d.id == document_id), None)

    def resolve_folder(self, folder_id):
        self._record("resolve_folder")
        return next((f for f in self.folders if f.id == folder_id), None)

    def child_folders(self, parent_id):
        self._record("child_folders")
        return [f for f in self.folders if f.parent_id == parent_id]

    # -- writes ---------------------------------------------------------

    def write_document_content(self, secret, markdown):
        self._record("write_document_content")
        self.mutations.append(f"write_content {secret}")
        self.content[secret] = markdown

    def create_child_document(self, name, parent_document_id):
        self._record("create_child_document")
        node = DocumentNode(
            id=f"doc-{next(self._ids)}",
            name=name,
            folder_id=None,
            entity_public_id=None,
            secret=f"secret-{next(self._ids)}",
            parent_document_id=parent_document_id,
        )
        self.documents.append(node)
        self.content[node.secret] = ""
        self.mutations.append(f"create_child_document {name}")
        return node

    def create_requirement_with_id(
        self, entity_id, project_id, title, revision, category
    ):
        self._record("create_requirement_with_id")
        if entity_id in self.requirements:
            # Exactly how Fibery refuses a duplicate fibery/id.
            raise FiberyError(
                f'"SDLC/Requirement" DB has entities with "fibery/id" field '
                f'having same "{entity_id}" value.'
            )
        record = RequirementRecord(
            id=entity_id,
            public_id=str(next(self._public)),
            requirement_id=None,
            title=title,
            type_name=None,
            state="Draft",
            revision=revision,
            project_id=project_id,
            source_fingerprint=None,
        )
        self.requirements[entity_id] = record
        self.categories = getattr(self, "categories", {})
        self.categories[entity_id] = category
        self.mutations.append(f"create_requirement {entity_id} {category}")
        return record

    def set_requirement_id(self, entity_id, requirement_id):
        self._record("set_requirement_id")
        self.mutations.append(f"set_requirement_id {requirement_id}")
        self._replace(entity_id, requirement_id=requirement_id)

    def set_requirement_type(self, entity_id, type_name):
        self._record("set_requirement_type")
        if type_name not in KNOWN_TYPES:
            raise FiberyError(f"Unknown Type {type_name!r}.")
        self.mutations.append(f"set_requirement_type {entity_id} {type_name}")
        self._replace(entity_id, type_name=type_name)

    def set_requirement_state(self, entity_id, state):
        self._record("set_requirement_state")
        if state not in KNOWN_STATES:
            raise FiberyError(f"Unknown state {state!r}.")
        self.mutations.append(f"set_requirement_state {entity_id} {state}")
        self._replace(entity_id, state=state)

    def add_derived_from(self, entity_id, raw_entity_id):
        self._record("add_derived_from")
        self.mutations.append(f"add_derived_from {entity_id} -> {raw_entity_id}")
        self.derived_from.setdefault(entity_id, [])
        if raw_entity_id not in self.derived_from[entity_id]:
            self.derived_from[entity_id].append(raw_entity_id)

    def create_requirement_document(self, name, folder_id, requirement_public_id):
        self._record("create_requirement_document")
        known = {r.public_id for r in self.requirements.values()}
        if requirement_public_id not in known:
            raise FiberyError("specified parent entity was not found")
        node = DocumentNode(
            id=f"doc-{next(self._ids)}",
            name=name,
            folder_id=folder_id,
            entity_public_id=requirement_public_id,
            secret=f"secret-{next(self._ids)}",
        )
        self.documents.append(node)
        self.content[node.secret] = ""
        self.mutations.append(f"create_requirement_document {name}")
        return node

    # -- helpers --------------------------------------------------------

    def produces(self, raw_entity_id):
        """The inverse relation Fibery maintains automatically."""
        return [e for e, raws in self.derived_from.items() if raw_entity_id in raws]

    def _record(self, method):
        self.calls.append(method)
        failure = self.failures.pop(method, None)
        if failure is not None:
            raise failure

    def _replace(self, entity_id, **changes):
        current = self.requirements[entity_id]
        self.requirements[entity_id] = RequirementRecord(
            id=current.id,
            public_id=current.public_id,
            requirement_id=changes.get("requirement_id", current.requirement_id),
            title=current.title,
            type_name=changes.get("type_name", current.type_name),
            state=changes.get("state", current.state),
            revision=current.revision,
            project_id=current.project_id,
            source_fingerprint=current.source_fingerprint,
        )


def build_workspace(raw_state="Process", raw_type="Raw", standards=()):
    """A Project with the frozen folder tree, one RAW and its Root Document."""
    root = FolderNode(id="f-root", name="SDLC", parent_id=None)
    reqs = FolderNode(id="f-reqs", name="Requirements", parent_id=root.id)
    stages = [
        FolderNode(id=f"f-{s.lower()}", name=s, parent_id=reqs.id)
        for s in ("Raw", "Draft", "Approved")
    ]
    project = ProjectRecord(
        id="p-1",
        name="SDLC",
        code="SDLC",
        state="Planned",
        documents_root_folder_id=root.id,
    )
    raw = RequirementRecord(
        id="raw-uuid-1",
        public_id="7",
        requirement_id="SDLC-RAW-0007",
        title="Initial SDLC Requirements",
        type_name=raw_type,
        state=raw_state,
        revision=1,
        project_id=project.id,
        source_fingerprint="fp",
    )
    ws = FakeProcessorWorkspace(project, [root, reqs, *stages], [raw, *standards])
    doc = DocumentNode(
        id="raw-doc-1",
        name="SDLC-RAW-0007 — Initial SDLC Requirements",
        folder_id="f-raw",
        entity_public_id=raw.public_id,
        secret="raw-secret",
    )
    ws.documents.append(doc)
    ws.content["raw-secret"] = "# Initial SDLC Requirements\n\nThe CLI must be fast.\n"
    return ws, raw, doc


def model_output(candidates, findings=(), reason=None):
    body = {"candidates": list(candidates), "findings": list(findings)}
    if reason:
        body["no_candidate_reason"] = reason
    return json.dumps(body)


def candidate(category="FUNCTIONAL", title="A candidate", **changes):
    base = {
        "category": category,
        "title": title,
        "requirement": "The system must do the thing.",
        "detailed_behavior": "It does the thing when asked.",
        "rationale": "The source asked for it.",
        "acceptance_verification": "Asking produces the thing.",
        "constraints_edge_cases": "Only when authenticated.",
        "non_goals": "Does not do the other thing.",
        "open_questions": "None.",
    }
    return {**base, **changes}
