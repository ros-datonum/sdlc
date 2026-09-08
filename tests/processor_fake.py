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
import re

from sdlc.comparison_context import COMPARISON_RECORD_LIMIT
from sdlc.fibery_workspace import (
    DocumentNode,
    FiberyError,
    ProjectRecord,
    RequirementRecord,
    RequirementRelations,
)
from sdlc.model_runtime import ModelResponse
from sdlc.raw_source import FENCED_BLOCK_PATTERN

# Fibery re-serializes stored Markdown (Fibery-API-Constraints constraint 11).
# Modelled narrowly so post-write validation is exercised against what Fibery
# actually returns, not what was written. Every behaviour below was verified
# against the live workspace by writing the case and reading it back.
BULLET_WRITTEN = re.compile(r"^(\s*)-\s", re.MULTILINE)
BULLET_STORED = r"\1* "
# A block boundary Fibery separates with a blank line: a list item or a heading.
BLOCK_START = r"(?:[-*+>]\s|#{1,6}\s|\d+\.\s|```)"
# A paragraph directly followed by a list, or a heading directly followed by
# anything, gains a blank line between them.
PARAGRAPH_THEN_LIST = re.compile(
    rf"^(?![ \t]*{BLOCK_START})(?P<paragraph>.*\S)\n(?=[ \t]*{BLOCK_START})",
    re.MULTILINE,
)
HEADING_THEN_TEXT = re.compile(
    r"^(?P<heading>[ \t]*#{1,6}\s.*\S)\n(?=[ \t]*\S)", re.MULTILINE
)
# A soft line break inside a paragraph or a list item is stored as a literal
# <br>, so text wrapped across source lines is read back as one line, and the
# indent of the wrapped continuation is dropped with it. [ \t]* rather than \s*
# so a blank line - a real paragraph break - is never crossed.
# A fenced block is returned exactly as written, so it is split out and left
# alone. Both the Process Result and the Review Result store their payload in
# one, and mangling it would make every artifact round trip unrealistic. The
# fence boundary is the production one, so the fake and the canonicalizer can
# never disagree about where literal content begins.
FENCED_BLOCK = FENCED_BLOCK_PATTERN
SOFT_BREAK = re.compile(
    rf"^(?![ \t]*(?:#{{1,6}}\s|```))(?P<line>[ \t]*\S.*\S|[ \t]*\S)"
    rf"\n(?![ \t]*{BLOCK_START})[ \t]*(?=\S)",
    re.MULTILINE,
)


def reserialize_like_fibery(markdown: str) -> str:
    """What Fibery returns for content written to a Document.

    Four behaviours, all verified live:

    - a `-` bullet is returned as `*`;
    - a blank line is inserted before a list that follows a paragraph, and
      after a heading that is followed directly by anything;
    - a soft line break inside a paragraph or a list item is returned as a
      literal `<br>`, and the continuation's leading indent is dropped;
    - the trailing newline is stripped.

    A fenced code block is returned verbatim, which is what makes the JSON
    payload of a Process or Review Result survive a round trip intact.
    """
    return "".join(
        segment if _is_fenced(segment) else _reserialize_prose(segment)
        for segment in FENCED_BLOCK.split(markdown)
    ).rstrip("\n")


def _is_fenced(segment: str) -> bool:
    return segment.startswith("```")


def _reserialize_prose(markdown: str) -> str:
    # Wrapped lines are joined first: a continuation line is part of the item
    # or paragraph above it, not a paragraph of its own that a list follows.
    joined = _join_wrapped_paragraphs(markdown)
    spaced = PARAGRAPH_THEN_LIST.sub(r"\g<paragraph>\n\n", joined)
    spaced = HEADING_THEN_TEXT.sub(r"\g<heading>\n\n", spaced)
    return BULLET_WRITTEN.sub(BULLET_STORED, spaced)


def _join_wrapped_paragraphs(markdown: str) -> str:
    """Replace every intra-paragraph newline with a literal <br>."""
    while True:
        joined = SOFT_BREAK.sub(r"\g<line><br>", markdown, count=1)
        if joined == markdown:
            return markdown
        markdown = joined


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

    def __init__(self, project: ProjectRecord, requirements=None):
        self.project = project
        self.requirements = {r.id: r for r in (requirements or [])}
        self.documents: list[DocumentNode] = []
        self.content: dict[str, str] = {}
        self.derived_from_ids: dict[str, list[str]] = {}
        # Existing Depends On / Affects edges, by entity id. Fibery maintains
        # the inverse sides itself, so only the forward ones are stored.
        self.depends_on_ids: dict[str, list[str]] = {}
        self.affects_ids: dict[str, list[str]] = {}
        self.mutations: list[str] = []
        self.calls: list[str] = []
        self.failures: dict[str, FiberyError] = {}
        # Fibery always re-serializes; a test may disable it to isolate a case.
        self.reserializes = True
        # The per-RAW execution lock scope a real workspace derives from its
        # host and Space id.
        self.lock_scope = "fake.fibery.io/space-1"
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

    def find_requirements_by_requirement_id(self, requirement_id):
        """Bounded to two rows, as the live query is: enough to see ambiguity."""
        self._record("find_requirements_by_requirement_id")
        matches = [
            r for r in self.requirements.values() if r.requirement_id == requirement_id
        ]
        return matches[:2]

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
        stored = self.content.get(secret, "")
        return reserialize_like_fibery(stored) if self.reserializes else stored

    def derived_from(self, entity_id):
        self._record("derived_from")
        return [
            self.requirements[r]
            for r in self.derived_from_ids.get(entity_id, [])
            if r in self.requirements
        ]

    def requirement_relations(self, entity_id):
        self._record("requirement_relations")
        return RequirementRelations(
            depends_on=self._relation_ids(self.depends_on_ids.get(entity_id, [])),
            affects=self._relation_ids(self.affects_ids.get(entity_id, [])),
        )

    def _relation_ids(self, entity_ids):
        """Entity ids resolved to Requirement IDs, as the real adapter does."""
        return tuple(
            self.requirements[value].requirement_id
            for value in entity_ids
            if value in self.requirements and self.requirements[value].requirement_id
        )

    def standard_requirements_in_project(self, project_id):
        """Bounded exactly as the live query is: two rows past the corpus limit."""
        self._record("standard_requirements_in_project")
        return [
            r
            for r in self.requirements.values()
            if r.project_id == project_id and r.type_name == "Standard"
        ][: COMPARISON_RECORD_LIMIT + 2]

    def resolve_document(self, document_id):
        self._record("resolve_document")
        return next((d for d in self.documents if d.id == document_id), None)

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
            category=category,
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

    def add_depends_on(self, entity_id, target_entity_id):
        """Constraint 26: membership is a set; a repeated add is a no-op."""
        self._record("add_depends_on")
        self.mutations.append(f"add_depends_on {entity_id} -> {target_entity_id}")
        self._add_member(self.depends_on_ids, entity_id, target_entity_id)

    def add_affects(self, entity_id, target_entity_id):
        """Constraint 26: membership is a set; a repeated add is a no-op."""
        self._record("add_affects")
        self.mutations.append(f"add_affects {entity_id} -> {target_entity_id}")
        self._add_member(self.affects_ids, entity_id, target_entity_id)

    def relocate_legacy_folder(self, document_id, folder_id):
        """Test helper, not a protocol method: change a Document's legacy Folder.

        Models a human or an old SDLC moving a Document between the retired
        Raw/Draft/Approved folders. Presentation metadata only: the Document
        keeps its id, secret, children and content.
        """
        self.mutations.append(f"relocate_legacy_folder {document_id} {folder_id}")
        current = next(d for d in self.documents if d.id == document_id)
        self.documents[self.documents.index(current)] = DocumentNode(
            id=current.id,
            name=current.name,
            folder_id=folder_id,
            entity_public_id=current.entity_public_id,
            secret=current.secret,
            parent_document_id=current.parent_document_id,
        )

    def inverse_relations(self, entity_id):
        """The Fibery-maintained inverse sides: who Blocks and who Impacts."""
        blocks = [
            s for s, targets in self.depends_on_ids.items() if entity_id in targets
        ]
        impacted_by = [
            s for s, targets in self.affects_ids.items() if entity_id in targets
        ]
        return RequirementRelations(
            depends_on=self._relation_ids(blocks),
            affects=self._relation_ids(impacted_by),
        )

    def _add_member(self, collection, entity_id, item_id):
        if entity_id not in self.requirements or item_id not in self.requirements:
            raise FiberyError("entity not found")
        members = collection.setdefault(entity_id, [])
        if item_id not in members:
            members.append(item_id)

    def add_derived_from(self, entity_id, raw_entity_id):
        self._record("add_derived_from")
        self.mutations.append(f"add_derived_from {entity_id} -> {raw_entity_id}")
        self.derived_from_ids.setdefault(entity_id, [])
        if raw_entity_id not in self.derived_from_ids[entity_id]:
            self.derived_from_ids[entity_id].append(raw_entity_id)

    def create_requirement_document(self, name, requirement_public_id):
        self._record("create_requirement_document")
        known = {r.public_id for r in self.requirements.values()}
        if requirement_public_id not in known:
            raise FiberyError("specified parent entity was not found")
        node = DocumentNode(
            id=f"doc-{next(self._ids)}",
            name=name,
            folder_id=None,
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
        return [e for e, raws in self.derived_from_ids.items() if raw_entity_id in raws]

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
            category=current.category,
        )


# Legacy folder ids: Documents created before the Type/State navigation model
# still carry one of these in `fibery/Folder`. Fixtures use them to prove the
# lifecycle ignores them; new Documents carry None.
LEGACY_RAW_FOLDER = "f-raw"
LEGACY_DRAFT_FOLDER = "f-draft"
LEGACY_APPROVED_FOLDER = "f-approved"


def build_workspace(
    raw_state="Process", raw_type="Raw", standards=(), legacy_folders=True
):
    """A Project, one RAW and its Root Document.

    `legacy_folders=True` gives the fixture Documents the `fibery/Folder`
    metadata the pre-navigation-model SDLC wrote (fixture B); False models
    Documents created after it, with no Folder (fixture A).
    """
    project = ProjectRecord(id="p-1", name="SDLC", code="SDLC", state="Planned")
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
    ws = FakeProcessorWorkspace(project, [raw, *standards])
    attach_peer_roots(ws, standards, legacy_folders)
    doc = DocumentNode(
        id="raw-doc-1",
        name="SDLC-RAW-0007 — Initial SDLC Requirements",
        folder_id=LEGACY_RAW_FOLDER if legacy_folders else None,
        entity_public_id=raw.public_id,
        secret="raw-secret",
    )
    ws.documents.append(doc)
    ws.content["raw-secret"] = "# Initial SDLC Requirements\n\nThe CLI must be fast.\n"
    return ws, raw, doc


def attach_peer_roots(ws, records, legacy_folders=True):
    """Give every peer Standard fixture the Root Document a real one has.

    Comparison context refuses a Standard without exactly one readable,
    non-empty Root, so a fixture that wants that failure removes the Document
    or empties its content explicitly.
    """
    for record in records:
        if record.type_name != "Standard" or any(
            d.entity_public_id == record.public_id for d in ws.documents
        ):
            continue
        secret = f"peer-secret-{record.public_id}"
        ws.documents.append(
            DocumentNode(
                id=f"peer-doc-{record.public_id}",
                name=f"{record.requirement_id} — {record.title}",
                folder_id=LEGACY_DRAFT_FOLDER if legacy_folders else None,
                entity_public_id=record.public_id,
                secret=secret,
            )
        )
        ws.content[secret] = (
            f"# {record.requirement_id} — {record.title}\n\n## Requirement\n\n"
            f"{record.title}.\n"
        )


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
