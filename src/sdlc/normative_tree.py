"""The normative Document tree of a Requirement, read and bound the same way
by every consumer.

Implements Requirement-Normative-Tree-Binding-v0.1. A Requirement's normative
content is its single directly associated Root Document plus every Document
nested under it at any depth, except the process-control artifacts the
capabilities themselves write. This module owns that classification, the
traversal with its admission limits, the canonical manifest that identifies
an observed tree, and the rendering that puts the hierarchy in front of a
model with its identity boundaries visible.

The manifest is an observation made through several reads, not an atomic
database snapshot, and its content identity is equivalence under the frozen
`canonical_markdown` policy, not a byte-exact hash.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, replace

from sdlc.fibery_workspace import DocumentNode, FiberyError, RequirementRecord
from sdlc.raw_source import canonical_markdown, fingerprint_of

# Manifest v2 fingerprints each Document as SHA-256 over the exact UTF-8 bytes of
# canonical_markdown(content). v1 (audit A8) hashed through fingerprint_of,
# whose second normalization erased trailing whitespace and Unicode form
# differences inside fenced blocks; v1 manifests stay readable as history and
# are never rewritten or reinterpreted.
NORMATIVE_TREE_VERSION = 2
LEGACY_NORMATIVE_TREE_VERSION = 1
SUPPORTED_NORMATIVE_TREE_VERSIONS = frozenset(
    {NORMATIVE_TREE_VERSION, LEGACY_NORMATIVE_TREE_VERSION}
)

# Admission limits: early application checks on the tree itself. The final
# bound on the complete assembled model input still applies afterwards.
NORMATIVE_TREE_MAX_DEPTH = 16  # parent edges from the Root; the Root is depth 0
NORMATIVE_TREE_MAX_DOCUMENTS = 100  # including the Root
NORMATIVE_TREE_MAX_TEXT_CHARS = 400_000  # sum of len(name) + len(body), code points

VERSION_KEY = "normative_tree_version"
REQUIREMENT_ID_KEY = "requirement_id"
ROOT_KEY = "root_document_id"
DOCUMENTS_KEY = "documents"
FINGERPRINT_KEY = "normative_tree_fingerprint"
DOCUMENT_ID_KEY = "document_id"
PARENT_KEY = "parent_document_id"
NAME_KEY = "name"
CONTENT_FINGERPRINT_KEY = "content_fingerprint"

ARTIFACT_PROCESS = "Process Result"
ARTIFACT_REVIEW = "Review Result"
ARTIFACT_PROCESSING = "Processing Result"
# The established artifact names: `<Requirement ID> — Process Result 0001`,
# `<Requirement ID> — Review Result 0001`, `<Requirement ID> — Processing Result`.
ARTIFACT_NAME_PATTERN = re.compile(
    r"^(?P<owner>.+) — (?P<kind>Process Result|Review Result)(?: \d{4,})$"
    r"|^(?P<raw_owner>.+) — (?P<raw_kind>Processing Result)$"
)

ROOT_LABEL = "root"


class NormativeTreeError(Exception):
    """The tree could not be established completely and unambiguously.

    `read_failed` is True when Fibery could not be read; otherwise the tree
    itself is invalid or unsupported. Details name Documents by id and name,
    never their content.
    """

    def __init__(
        self, message: str, details: tuple[str, ...] = (), read_failed: bool = False
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details
        self.read_failed = read_failed


class InvalidTreeManifest(ValueError):
    """A persisted manifest is malformed or contradicts itself."""


def document_fingerprint(content: str) -> str:
    """The current document fingerprint: SHA-256 of the exact canonical bytes.

    canonical_markdown already defines the supported equivalence (Fibery's
    prose re-serialization absorbed, fenced content literal). Its output is
    hashed as is: no second strip, collapse, NFC or line-ending pass, so two
    documents fingerprint equal exactly when content_equivalent says so.
    """
    return hashlib.sha256(canonical_markdown(content).encode("utf-8")).hexdigest()


def legacy_document_fingerprint(content: str) -> str:
    """The manifest v1 / Result 0.2 algorithm, kept only to verify history.

    It normalized the canonical form a second time and therefore collided on
    fenced trailing whitespace and Unicode form (audit A8). Never used for
    new evidence.
    """
    return fingerprint_of(canonical_markdown(content))


def classify_artifact_name(name: str) -> tuple[str, str] | None:
    """(owner Requirement ID, artifact kind) when `name` is an artifact name."""
    match = ARTIFACT_NAME_PATTERN.match(name.strip())
    if match is None:
        return None
    if match.group("owner") is not None:
        return match.group("owner"), match.group("kind")
    return match.group("raw_owner"), match.group("raw_kind")


@dataclass(frozen=True)
class TreeEntry:
    """One included Document as the manifest identifies it."""

    document_id: str
    parent_document_id: str | None
    name: str
    content_fingerprint: str


@dataclass(frozen=True)
class TreeManifest:
    """The canonical identity of one observed normative tree."""

    requirement_id: str
    root_document_id: str
    entries: tuple[TreeEntry, ...]
    version: int = NORMATIVE_TREE_VERSION

    @property
    def is_current(self) -> bool:
        """Whether the content fingerprints follow the current algorithm."""
        return self.version == NORMATIVE_TREE_VERSION

    @property
    def root_entry(self) -> TreeEntry:
        return next(e for e in self.entries if e.document_id == self.root_document_id)

    @property
    def document_ids(self) -> frozenset[str]:
        return frozenset(entry.document_id for entry in self.entries)

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(_canonical_bytes(self)).hexdigest()

    def with_root_fingerprint(self, content_fingerprint: str) -> TreeManifest:
        """The same tree with only the Root's content changed: Process's
        intended output, which is authorized to normalize the Root alone."""
        return replace(
            self,
            entries=tuple(
                replace(entry, content_fingerprint=content_fingerprint)
                if entry.document_id == self.root_document_id
                else entry
                for entry in self.entries
            ),
        )

    def to_payload(self) -> dict[str, object]:
        return {**_payload_without_fingerprint(self), FINGERPRINT_KEY: self.fingerprint}

    @classmethod
    def from_payload(cls, payload: object) -> TreeManifest:
        """Parse and validate a persisted manifest; never consults Fibery."""
        if not isinstance(payload, dict):
            raise InvalidTreeManifest("The normative tree manifest must be an object.")
        version = payload.get(VERSION_KEY)
        if (
            not isinstance(version, int)
            or isinstance(version, bool)
            or version not in SUPPORTED_NORMATIVE_TREE_VERSIONS
        ):
            raise InvalidTreeManifest(
                f"Normative tree manifest version {version!r} is not supported; "
                f"versions {sorted(SUPPORTED_NORMATIVE_TREE_VERSIONS)} are read."
            )
        requirement_id = _require_text(
            payload.get(REQUIREMENT_ID_KEY), REQUIREMENT_ID_KEY
        )
        root_id = _require_text(payload.get(ROOT_KEY), ROOT_KEY)
        raw_entries = payload.get(DOCUMENTS_KEY)
        if not isinstance(raw_entries, list) or not raw_entries:
            raise InvalidTreeManifest("The manifest must list at least the Root.")
        entries = tuple(sorted((_read_entry(e) for e in raw_entries), key=_entry_key))
        manifest = cls(
            requirement_id=requirement_id,
            root_document_id=root_id,
            entries=entries,
            version=version,
        )
        _validate_structure(manifest)
        declared = payload.get(FINGERPRINT_KEY)
        if declared != manifest.fingerprint:
            raise InvalidTreeManifest(
                "The declared normative tree fingerprint does not match the manifest."
            )
        return manifest


def describe_drift(expected: TreeManifest, observed: TreeManifest) -> tuple[str, ...]:
    """Name exactly what differs, by Document id and name, never by content."""
    if expected.fingerprint == observed.fingerprint:
        return ()
    drift: list[str] = []
    if expected.root_document_id != observed.root_document_id:
        drift.append(
            f"the Root Document changed from {expected.root_document_id} to "
            f"{observed.root_document_id}"
        )
    before = {e.document_id: e for e in expected.entries}
    after = {e.document_id: e for e in observed.entries}
    for document_id in sorted(after.keys() - before.keys()):
        drift.append(f"Document {after[document_id].name!r} ({document_id}) was added")
    for document_id in sorted(before.keys() - after.keys()):
        drift.append(
            f"Document {before[document_id].name!r} ({document_id}) was removed"
        )
    for document_id in sorted(before.keys() & after.keys()):
        old, new = before[document_id], after[document_id]
        if old.parent_document_id != new.parent_document_id:
            drift.append(f"Document {new.name!r} ({document_id}) was re-parented")
        if old.name != new.name:
            drift.append(
                f"Document {document_id} was renamed from {old.name!r} to {new.name!r}"
            )
        if old.content_fingerprint != new.content_fingerprint:
            drift.append(f"Document {new.name!r} ({document_id}) content changed")
    return tuple(drift) or ("the normative tree changed",)


@dataclass(frozen=True)
class NormativeDocument:
    """One included Document with its body, for rendering."""

    node: DocumentNode
    parent_document_id: str | None
    depth: int
    body: str


@dataclass(frozen=True)
class NormativeTree:
    """One complete observation: manifest, bodies in render order, artifacts."""

    manifest: TreeManifest
    documents: tuple[NormativeDocument, ...]
    artifacts: tuple[DocumentNode, ...]

    @property
    def root(self) -> NormativeDocument:
        return self.documents[0]

    @property
    def descendants(self) -> tuple[NormativeDocument, ...]:
        return self.documents[1:]


class TreeWorkspace:
    """The two reads traversal needs; every workspace protocol has them."""

    def child_documents(
        self, parent_document_id: str
    ) -> list[DocumentNode]:  # pragma: no cover
        ...

    def read_document_content(self, secret: str) -> str:  # pragma: no cover
        ...


def read_normative_tree(
    workspace: TreeWorkspace, requirement: RequirementRecord, root: DocumentNode
) -> NormativeTree:
    """Traverse from the resolved Root, breadth-first, siblings by Document id.

    Refuses rather than hides: a foreign or misplaced artifact name, anything
    nested beneath an artifact, a Document listed twice, a cycle, a missing
    secret, an unreadable body, or an exceeded limit. A traversal that stopped
    early is never returned as a tree.
    """
    owner = requirement.requirement_id or ""
    visited = {root.id}
    documents: list[NormativeDocument] = []
    artifacts: list[DocumentNode] = []
    entries: list[TreeEntry] = []
    text_chars = 0
    queue: list[tuple[DocumentNode, str | None, int]] = [(root, None, 0)]
    while queue:
        node, parent_id, depth = queue.pop(0)
        body = _read_body(workspace, node)
        text_chars += len(node.name) + len(body)
        if text_chars > NORMATIVE_TREE_MAX_TEXT_CHARS:
            raise NormativeTreeError(
                f"The normative tree of {owner} exceeds "
                f"{NORMATIVE_TREE_MAX_TEXT_CHARS} characters of names and bodies "
                f"(at least {text_chars}); it was not truncated.",
            )
        documents.append(NormativeDocument(node, parent_id, depth, body))
        entries.append(
            TreeEntry(node.id, parent_id, node.name, document_fingerprint(body))
        )
        for child in _children(workspace, node, owner):
            artifact = classify_artifact_name(child.name)
            if artifact is not None:
                _admit_artifact(workspace, node, root, child, artifact, owner)
                artifacts.append(child)
                continue
            if child.id in visited:
                raise NormativeTreeError(
                    f"Document {child.name!r} ({child.id}) is listed more than once "
                    f"in the tree of {owner}; the hierarchy is ambiguous.",
                    (child.id,),
                )
            visited.add(child.id)
            if depth + 1 > NORMATIVE_TREE_MAX_DEPTH:
                raise NormativeTreeError(
                    f"Document {child.name!r} ({child.id}) sits deeper than "
                    f"{NORMATIVE_TREE_MAX_DEPTH} levels below the Root of {owner}.",
                    (child.id,),
                )
            if len(visited) > NORMATIVE_TREE_MAX_DOCUMENTS:
                raise NormativeTreeError(
                    f"The normative tree of {owner} has more than "
                    f"{NORMATIVE_TREE_MAX_DOCUMENTS} Documents (at least "
                    f"{len(visited)}); it was not truncated.",
                )
            queue.append((child, node.id, depth + 1))
    manifest = TreeManifest(
        requirement_id=owner,
        root_document_id=root.id,
        entries=tuple(sorted(entries, key=_entry_key)),
    )
    return NormativeTree(
        manifest=manifest, documents=tuple(documents), artifacts=tuple(artifacts)
    )


def render_descendants(tree: NormativeTree) -> str:
    """The normative children in traversal order, each behind an identity marker."""
    return "\n\n".join(_render_document(document) for document in tree.descendants)


def render_normative_tree(tree: NormativeTree) -> str:
    """The Root and every normative descendant, hierarchy visible."""
    return "\n\n".join(_render_document(document) for document in tree.documents)


# -- internals -------------------------------------------------------------


def _render_document(document: NormativeDocument) -> str:
    parent = document.parent_document_id or ROOT_LABEL
    return (
        f"<!-- document: {document.node.name} | id: {document.node.id} | "
        f"parent: {parent} | depth: {document.depth} -->\n{document.body}"
    )


def _read_body(workspace: TreeWorkspace, node: DocumentNode) -> str:
    if not node.secret:
        raise NormativeTreeError(
            f"Document {node.name!r} ({node.id}) exposes no content secret.",
            (node.id,),
        )
    try:
        return workspace.read_document_content(node.secret)
    except FiberyError as error:
        raise NormativeTreeError(
            f"Could not read Document {node.name!r} ({node.id}).",
            (node.id, type(error).__name__),
            read_failed=True,
        ) from error


def _children(
    workspace: TreeWorkspace, node: DocumentNode, owner: str
) -> list[DocumentNode]:
    try:
        children = workspace.child_documents(node.id)
    except FiberyError as error:
        raise NormativeTreeError(
            f"Could not list the children of Document {node.name!r} ({node.id}) "
            f"of {owner}.",
            (node.id, type(error).__name__),
            read_failed=True,
        ) from error
    return sorted(children, key=lambda child: child.id)


def _admit_artifact(
    workspace: TreeWorkspace,
    parent: DocumentNode,
    root: DocumentNode,
    child: DocumentNode,
    artifact: tuple[str, str],
    owner: str,
) -> None:
    artifact_owner, kind = artifact
    if artifact_owner != owner:
        raise NormativeTreeError(
            f"Document {child.name!r} ({child.id}) carries the {kind} artifact name "
            f"of {artifact_owner!r} under the tree of {owner}; unsupported placement.",
            (child.id,),
        )
    if parent.id != root.id:
        raise NormativeTreeError(
            f"{kind} Document {child.name!r} ({child.id}) is nested under "
            f"{parent.name!r} ({parent.id}) instead of directly under the Root; "
            "unsupported placement.",
            (child.id,),
        )
    nested = _children(workspace, child, owner)
    if nested:
        raise NormativeTreeError(
            f"{kind} Document {child.name!r} ({child.id}) has {len(nested)} nested "
            "Document(s); content beneath a control artifact is unsupported.",
            tuple(node.id for node in nested),
        )


def _entry_key(entry: TreeEntry) -> str:
    return entry.document_id


def _payload_without_fingerprint(manifest: TreeManifest) -> dict[str, object]:
    return {
        VERSION_KEY: manifest.version,
        REQUIREMENT_ID_KEY: manifest.requirement_id,
        ROOT_KEY: manifest.root_document_id,
        DOCUMENTS_KEY: [
            {
                DOCUMENT_ID_KEY: entry.document_id,
                PARENT_KEY: entry.parent_document_id,
                NAME_KEY: entry.name,
                CONTENT_FINGERPRINT_KEY: entry.content_fingerprint,
            }
            for entry in sorted(manifest.entries, key=_entry_key)
        ],
    }


def _canonical_bytes(manifest: TreeManifest) -> bytes:
    return json.dumps(
        _payload_without_fingerprint(manifest),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidTreeManifest(f"The manifest has no {field}.")
    return value


def _read_entry(raw: object) -> TreeEntry:
    if not isinstance(raw, dict):
        raise InvalidTreeManifest("Each manifest document must be an object.")
    parent = raw.get(PARENT_KEY)
    if parent is not None and (not isinstance(parent, str) or not parent):
        raise InvalidTreeManifest("A manifest parent id must be a string or null.")
    name = raw.get(NAME_KEY)
    if not isinstance(name, str):
        raise InvalidTreeManifest("A manifest document name must be a string.")
    return TreeEntry(
        document_id=_require_text(raw.get(DOCUMENT_ID_KEY), DOCUMENT_ID_KEY),
        parent_document_id=parent,
        name=name,
        content_fingerprint=_require_text(
            raw.get(CONTENT_FINGERPRINT_KEY), CONTENT_FINGERPRINT_KEY
        ),
    )


def _validate_structure(manifest: TreeManifest) -> None:
    ids = [entry.document_id for entry in manifest.entries]
    if len(set(ids)) != len(ids):
        raise InvalidTreeManifest("The manifest lists a Document id more than once.")
    roots = [entry for entry in manifest.entries if entry.parent_document_id is None]
    if len(roots) != 1 or roots[0].document_id != manifest.root_document_id:
        raise InvalidTreeManifest(
            "The manifest must have exactly one Root entry, and it must be the "
            "declared Root Document."
        )
    by_id = {entry.document_id: entry for entry in manifest.entries}
    for entry in manifest.entries:
        seen: set[str] = set()
        current: TreeEntry | None = entry
        while current is not None and current.parent_document_id is not None:
            if current.parent_document_id not in by_id or current.document_id in seen:
                raise InvalidTreeManifest(
                    f"Document {entry.document_id} has an unknown or cyclic parent chain."
                )
            seen.add(current.document_id)
            current = by_id[current.parent_document_id]


def manifest_of(
    entries: Sequence[TreeEntry], requirement_id: str, root_id: str
) -> TreeManifest:
    """Build a manifest from entries; a convenience for tests and fixtures."""
    return TreeManifest(
        requirement_id=requirement_id,
        root_document_id=root_id,
        entries=tuple(sorted(entries, key=_entry_key)),
    )
