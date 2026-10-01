#!/usr/bin/env python
"""P-1: the live Fibery probe for TSA-C01 work item I03.

This is a probe instrument, not part of the `sdlc` capability. Unlike
`fibery_document_probe.py` it **writes**, so it refuses to run without an
explicit scratch Project entity id and an explicit mutation confirmation.

It answers the live questions the frozen implementation specification leaves
open for I03 (`docs/specs/TSA-C01-Implementation-Spec-v0.1.md`):

- `I-1` — whether a Project-contained Document takes the Project's **public id**
  or its entity uuid as `fibery/container-entity-id`;
- `I-4` — whether `document_fingerprint` over a Document containing a JSON fence
  survives Fibery's re-serialization;
- F row 23 — Project containment, nesting, rediscovery and content read-back;
- F row 22 — detection of an external placement edit at fresh revalidation;
- the duplicate caller-supplied `fibery/id` behaviour the I02 fake currently
  assumes rather than knows.

Every call goes through the real `FiberyArchitectureWorkspace`, so what is
measured is the adapter I04+ will consume, not a reimplementation of it.

    uv run python scripts/tsa_p1_probe.py \
        --project-id <scratch Project entity id> \
        --confirm-live-mutation

Secrets are never printed. A Document content secret is used internally for the
content round trip and is redacted from every line of output and from the
evidence payload.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import sys
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from sdlc.config import ConfigurationError, load_fibery_settings
from sdlc.fibery_client import FiberyClient
from sdlc.fibery_http import FiberyArchitectureWorkspace
from sdlc.fibery_workspace import (
    DocumentNode,
    DocumentPlacement,
    FiberyError,
    ProjectRecord,
    is_valid_child_placement,
    is_valid_root_placement,
)
from sdlc.normative_tree import document_fingerprint

#: Every Document this probe creates carries this prefix, so leftover state is
#: unmistakable in the workspace and can be removed by hand.
DEFAULT_PROBE_PREFIX = "TSA-P1-PROBE"

#: The deterministic payload of section 9: a heading, one paragraph, and one
#: JSON fence. The fence is the part `I-4` is about, because a fenced block is
#: the one thing Fibery returns verbatim (API constraint 11).
PROBE_PAYLOAD = (
    "# TSA P-1 Probe\n"
    "\n"
    "Probe payload.\n"
    "\n"
    "```json\n"
    '{"probe":"tsa-p1","version":1}\n'
    "```\n"
)

REDACTED = "<redacted>"

#: Values that must never appear in any output, collected as they become known.
#: The API token is registered as soon as settings load and a Document content
#: secret as soon as one is read, so the top-level handler can scrub a message
#: it did not produce.
_SECRETS: set[str] = set()

#: Failures a probe run can expect: a Fibery or transport error, missing
#: configuration, or a socket/urllib problem (`URLError` is an `OSError`).
#: `KeyboardInterrupt` and `SystemExit` derive from `BaseException` and are
#: deliberately not caught by any handler here.
EXPECTED_FAILURES = (FiberyError, ConfigurationError, OSError)

#: Failures writing the evidence file: a bad path, a full disk, an encoding
#: problem. Reporting a failure must survive all of them.
EXPECTED_OUTPUT_FAILURES = (OSError, TypeError, ValueError)

#: Classifications for a second create at an id that already exists. Each is
#: decided from a complete before/after snapshot of the durable observable
#: state, never from whether the call raised: an exception alone proves nothing
#: about what the call left behind.
DUPLICATE_REJECTED = "REJECTED"
DUPLICATE_IDEMPOTENT = "IDEMPOTENT"
DUPLICATE_MUTATED_EXISTING = "MUTATED_EXISTING"
DUPLICATE_OTHER = "OTHER_UNKNOWN_OUTCOME"

#: Live P-1 observed REJECTED, so any other classification contradicts both the
#: measured behaviour and the fake, and must fail the run rather than be
#: recorded as a curiosity.
DUPLICATE_EXPECTED = DUPLICATE_REJECTED

#: What the duplicate create attempt itself did, decided before any durable
#: state is compared. An exception is not evidence of rejection: a timeout or a
#: reset connection leaves it unknown whether Fibery processed the mutation.
OUTCOME_CONFIRMED_REJECTION = "CONFIRMED_REJECTION"
OUTCOME_SUCCESS = "SUCCESS"
OUTCOME_UNKNOWN_TRANSPORT = "UNKNOWN_TRANSPORT_OUTCOME"

#: A sanitized `FiberyError` proves the **create** was rejected only when it
#: names both the method and a server answer. `FiberyClient` phrases a JSON-RPC
#: failure as `Views method '<method>' failed: Fibery returned a JSON-RPC error
#: (code N); ...`, so a `query-views` failure during read-back carries the same
#: JSON-RPC marker while proving nothing about the preceding mutation. Both
#: markers are required. Classification reads only the sanitized public message
#: and never the cause chain, which can carry secrets.
CREATE_METHOD_MARKER = "Views method 'create-views' failed"
SERVER_RESPONSE_MARKER = "returned a JSON-RPC error"
FAILURE_DUPLICATE_UNEXPECTED = "duplicate_view_id_unexpected_behavior"
FAILURE_DUPLICATE_STATE_CHANGED = "duplicate_view_id_state_changed"
FAILURE_DUPLICATE_UNKNOWN = "duplicate_view_id_outcome_unknown"

CONTAINER_KIND_PUBLIC_ID = "PUBLIC_ID"
CONTAINER_KIND_CONTRADICTS = "CONTRADICTS_FROZEN_SPEC"

DRIFT_NOT_EXECUTED = "NOT_EXECUTED_SAFE_MUTATION_UNAVAILABLE"

#: The frozen acceptance criterion of §2.3 is byte equality **inside** the
#: ```json fence, not over the whole Markdown. API constraint 11 records, live
#: and verified, that Fibery re-serializes ordinary Markdown — it drops the
#: trailing newline, rewrites bullets, inserts blank lines and turns a soft line
#: break into `<br>` — while returning fenced content verbatim. Whole-document
#: byte inequality is therefore expected behaviour: recorded for the record, and
#: never a failure on its own.
FULL_MARKDOWN_EQUAL = "PASS"
FULL_MARKDOWN_RESERIALIZED = "DIFFERENT_DUE_TO_FIBERY_RESERIALIZATION"
PASS = "PASS"
FAIL = "FAIL"

JSON_FENCE_OPENER = "```json"
FENCE_MARKER = "```"

#: `I-1` is not first-ever evidence: API constraint 8 already records live
#: verification that `SDLC/Project` container-entity-id accepts the Project's
#: public id and rejects its entity uuid with `parent-entity-not-found`. What
#: P-1 adds is whether the new I02 adapter reproduces that through its own code
#: path, which is what I04+ will actually depend on.
EXISTING_EVIDENCE_NOTE = (
    "API constraint 8 (docs/fibery/Fibery-API-Constraints-v0.1.md) already "
    "records live verification that SDLC/Project container-entity-id accepts "
    "the Project public id and rejects the entity uuid."
)

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_BLOCKED = 2


class EvidenceOutputFailed(Exception):
    """The evidence write itself failed.

    Carried to the top level so the reporter knows not to try writing again:
    once a write has failed there is no second attempt during the handling of
    that failure. `message` is already sanitized.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass
class Evidence:
    """Everything the evidence document needs, and nothing sensitive."""

    started_at: str
    workspace_identity: str = ""
    project: dict[str, Any] = field(default_factory=dict)
    root: dict[str, Any] = field(default_factory=dict)
    child: dict[str, Any] = field(default_factory=dict)
    content: dict[str, Any] = field(default_factory=dict)
    fingerprint: dict[str, Any] = field(default_factory=dict)
    duplicate: dict[str, Any] = field(default_factory=dict)
    drift: dict[str, Any] = field(default_factory=dict)
    checks: dict[str, bool] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)
    completed: bool = False
    failure: str | None = None

    def record(self, name: str, passed: bool, detail: str = "") -> bool:
        self.checks[name] = passed
        if not passed:
            self.failures.append(f"{name}: {detail}" if detail else name)
        return passed


def register_secret(value: str | None) -> None:
    """Remember a value that must never be printed."""
    if value:
        _SECRETS.add(value)


def register_document_secret(node: DocumentNode | None) -> DocumentNode | None:
    """Register a returned Document's secret, then hand the Document back.

    Returns its argument so a call site can wrap the adapter result inline and
    make it impossible for anything to run in between.
    """
    if node is not None:
        register_secret(node.secret)
    return node


def register_placement_secret(
    placement: DocumentPlacement | None,
) -> DocumentPlacement | None:
    """Register a returned placement's secret, then hand the placement back."""
    if placement is not None:
        register_secret(placement.secret)
    return placement


def register_document_collection_secrets(
    nodes: list[DocumentNode],
) -> list[DocumentNode]:
    """Register every Document secret in a listing before the list is used."""
    for node in nodes:
        register_secret(node.secret)
    return nodes


def register_placement_collection_secrets(
    placements: list[DocumentPlacement],
) -> list[DocumentPlacement]:
    """Register every placement secret in a listing before the list is used."""
    for placement in placements:
        register_secret(placement.secret)
    return placements


def scrub(text: str) -> str:
    """The text with every registered secret replaced."""
    for secret in _SECRETS:
        text = text.replace(secret, REDACTED)
    return text


def sanitize(error: BaseException, secrets: tuple[str, ...] = ()) -> str:
    """One error line with every known secret removed.

    Deliberately `str(error)` and the type name only. The cause chain is never
    walked: `FiberyClient` sanitizes its own message but keeps the original
    transport exception as `__cause__`, and that original can carry a token or a
    document secret. Formatting it — or letting a traceback print it — is
    exactly the leak this avoids.
    """
    message = f"{type(error).__name__}: {error}"
    for secret in secrets:
        if secret:
            message = message.replace(secret, REDACTED)
    return scrub(message)


def placement_dict(placement: DocumentPlacement | None) -> dict[str, Any]:
    """A placement as evidence, with the content secret reduced to a flag."""
    if placement is None:
        return {"present": False}
    return {
        "present": True,
        "document_id": placement.document_id,
        "name": placement.name,
        "container_entity_type": placement.container_entity_type,
        "container_entity_id": placement.container_entity_id,
        "parent_document_id": placement.parent_document_id,
        "secret_present": placement.secret is not None,
    }


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def extract_json_fence(markdown: str) -> str | None:
    """The exact text between the one ```json opener and its closing fence.

    Returned verbatim: the fence markers are excluded and nothing inside them is
    normalised, canonicalised or re-indented, because this is the byte-exact
    comparison frozen §2.3 asks for. `None` when the document does not carry
    exactly one complete fence.
    """
    lines = markdown.split("\n")
    openers = [
        index for index, line in enumerate(lines) if line.strip() == JSON_FENCE_OPENER
    ]
    if len(openers) != 1:
        return None
    start = openers[0]
    closing = next(
        (
            index
            for index in range(start + 1, len(lines))
            if lines[index].strip() == FENCE_MARKER
        ),
        None,
    )
    if closing is None:
        return None
    return "\n".join(lines[start + 1 : closing])


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="TSA-C01 I03 live probe P-1 (writes to a scratch Project).",
    )
    parser.add_argument(
        "--project-id",
        required=True,
        help="Exact Fibery entity id of the scratch Project. Never a name.",
    )
    parser.add_argument(
        "--probe-prefix",
        default=DEFAULT_PROBE_PREFIX,
        help="Name prefix for every Document this probe creates.",
    )
    parser.add_argument(
        "--confirm-live-mutation",
        action="store_true",
        help="Required. Without it the probe reads and then stops.",
    )
    parser.add_argument(
        "--evidence-out",
        help="Where to write the evidence JSON. Printed to stdout when omitted.",
    )
    return parser.parse_args(argv)


def resolve_scratch_project(
    workspace: FiberyArchitectureWorkspace, project_id: str
) -> ProjectRecord | None:
    """Resolve the scratch Project by exact entity id, never by name."""
    return workspace.read_project(project_id)


def probe_root(
    workspace: FiberyArchitectureWorkspace,
    evidence: Evidence,
    project: ProjectRecord,
    name: str,
) -> tuple[str, DocumentPlacement | None]:
    """Create the Project-contained root Document and verify its placement."""
    requested_id = str(uuid.uuid4())
    node = workspace.create_project_document(requested_id, name, project.public_id)
    # Registered before anything else runs: from here on a failure anywhere can
    # carry this secret into a chained exception, and the scrubber must already
    # know it.
    register_document_secret(node)
    evidence.root = {
        "name": name,
        "requested_id": requested_id,
        "returned_id": node.id,
        "returned_parent_document_id": node.parent_document_id,
        "returned_entity_public_id": node.entity_public_id,
        "secret_present": node.secret is not None,
    }
    evidence.record(
        "root_caller_id_preserved",
        node.id == requested_id,
        f"returned {node.id!r}",
    )
    evidence.record("root_secret_present", node.secret is not None)

    resolved = register_document_secret(workspace.resolve_document(requested_id))
    evidence.record(
        "root_resolve_document", resolved is not None and resolved.id == requested_id
    )

    placement = register_placement_secret(workspace.resolve_placement(requested_id))
    evidence.root["placement"] = placement_dict(placement)
    if placement is None:
        evidence.record("root_resolve_placement", False, "no placement")
        return requested_id, None

    project_type_id = workspace.project_type_id
    evidence.project["live_project_type_id"] = project_type_id
    evidence.record("root_resolve_placement", True)
    evidence.record(
        "root_container_type_is_project_database",
        placement.container_entity_type == project_type_id,
        f"{placement.container_entity_type!r} != {project_type_id!r}",
    )
    evidence.record(
        "root_container_id_is_project_public_id",
        placement.container_entity_id == project.public_id,
        f"{placement.container_entity_id!r} != public id {project.public_id!r}",
    )
    evidence.record(
        "root_container_id_is_not_entity_id",
        placement.container_entity_id != project.id,
    )
    evidence.record("root_has_no_parent", placement.parent_document_id is None)
    evidence.record(
        "root_predicate_accepts",
        is_valid_root_placement(placement, project_type_id, project.public_id),
    )
    confirmed = placement.container_entity_id == project.public_id
    evidence.project["container_id_kind"] = (
        CONTAINER_KIND_PUBLIC_ID if confirmed else CONTAINER_KIND_CONTRADICTS
    )
    # P-1 is not the first evidence that Project containment uses the public id;
    # it confirms the new adapter reproduces the already-recorded behaviour
    # through the code path I04+ will consume.
    evidence.project["i1_existing_repository_evidence"] = EXISTING_EVIDENCE_NOTE
    evidence.project["i1_p1_adapter_confirmation"] = PASS if confirmed else FAIL
    return requested_id, placement


def probe_rediscovery(
    workspace: FiberyArchitectureWorkspace,
    evidence: Evidence,
    project: ProjectRecord,
    root_id: str,
    root_placement: DocumentPlacement,
) -> None:
    """Confirm the new root is listed under the Project exactly once."""
    attached = register_placement_collection_secrets(
        workspace.documents_attached_to_project(project.public_id)
    )
    matches = [item for item in attached if item.document_id == root_id]
    evidence.root["rediscovery"] = {
        "documents_attached_to_project_total": len(attached),
        "probe_root_matches": len(matches),
        "placement": placement_dict(matches[0]) if matches else {"present": False},
    }
    evidence.record(
        "root_rediscovered_exactly_once", len(matches) == 1, f"{len(matches)} matches"
    )
    if matches:
        evidence.record(
            "root_listing_matches_direct_resolve", matches[0] == root_placement
        )


def probe_child(
    workspace: FiberyArchitectureWorkspace,
    evidence: Evidence,
    project: ProjectRecord,
    root_id: str,
    root_placement: DocumentPlacement,
    name: str,
) -> None:
    """Create a deterministic child under the root and verify its nesting."""
    requested_id = str(uuid.uuid4())
    node = workspace.create_tsa_child_document(requested_id, name, root_id)
    register_document_secret(node)  # before any further operation
    evidence.child = {
        "name": name,
        "requested_id": requested_id,
        "returned_id": node.id,
        "returned_parent_document_id": node.parent_document_id,
    }
    evidence.record(
        "child_caller_id_preserved",
        node.id == requested_id,
        f"returned {node.id!r}",
    )
    evidence.record(
        "child_parent_is_root",
        node.parent_document_id == root_id,
        f"{node.parent_document_id!r} != {root_id!r}",
    )

    placement = register_placement_secret(workspace.resolve_placement(requested_id))
    evidence.child["placement"] = placement_dict(placement)
    evidence.record("child_resolve_placement", placement is not None)

    resolved = register_document_secret(workspace.resolve_document(requested_id))
    evidence.record("child_resolve_document", resolved is not None)

    placements = register_placement_collection_secrets(
        workspace.child_placements(root_id)
    )
    nodes = register_document_collection_secrets(workspace.child_documents(root_id))
    evidence.child["child_placements_matches"] = sum(
        1 for item in placements if item.document_id == requested_id
    )
    evidence.child["child_documents_matches"] = sum(
        1 for item in nodes if item.id == requested_id
    )
    evidence.record(
        "child_in_child_placements_once",
        evidence.child["child_placements_matches"] == 1,
    )
    evidence.record(
        "child_in_child_documents_once",
        evidence.child["child_documents_matches"] == 1,
    )

    if placement is not None:
        evidence.record(
            "child_predicate_accepts_through_root",
            is_valid_child_placement(
                placement,
                root_placement,
                root_id,
                workspace.project_type_id,
                project.public_id,
            ),
        )
    fresh_root = register_placement_secret(workspace.resolve_placement(root_id))
    evidence.record(
        "root_placement_still_valid_after_child",
        fresh_root is not None
        and is_valid_root_placement(
            fresh_root, workspace.project_type_id, project.public_id
        ),
    )


def probe_content(
    workspace: FiberyArchitectureWorkspace,
    evidence: Evidence,
    secret: str,
) -> str:
    """Write the deterministic payload, read it back, and measure both."""
    before = PROBE_PAYLOAD
    workspace.write_document_content(secret, before)
    after = workspace.read_document_content(secret)

    written_fence = extract_json_fence(before)
    read_fence = extract_json_fence(after)
    fence_equal = (
        written_fence is not None
        and read_fence is not None
        and written_fence == read_fence
    )

    evidence.content = {
        # --- observational: the whole-Markdown figures ---
        "written_bytes": len(before.encode("utf-8")),
        "read_bytes": len(after.encode("utf-8")),
        "written_sha256": sha256(before),
        "read_sha256": sha256(after),
        "full_markdown_byte_equality": (
            FULL_MARKDOWN_EQUAL if before == after else FULL_MARKDOWN_RESERIALIZED
        ),
        "full_markdown_is_observational_only": True,
        # --- the frozen criterion: byte equality INSIDE the fence (§2.3) ---
        "written_fence_present": written_fence is not None,
        "read_fence_present": read_fence is not None,
        "written_fence_bytes": (
            len(written_fence.encode("utf-8")) if written_fence is not None else None
        ),
        "read_fence_bytes": (
            len(read_fence.encode("utf-8")) if read_fence is not None else None
        ),
        "written_fence_sha256": (
            sha256(written_fence) if written_fence is not None else None
        ),
        "read_fence_sha256": sha256(read_fence) if read_fence is not None else None,
        "json_fence_byte_equality": PASS if fence_equal else FAIL,
    }
    # Only the fenced payload gates the content criterion. A whole-document byte
    # difference outside the fence is API constraint 11 behaviour, not a failure.
    evidence.record(
        "json_fence_byte_exact",
        fence_equal,
        f"written {written_fence!r} != read {read_fence!r}",
    )
    before_fingerprint = document_fingerprint(before)
    after_fingerprint = document_fingerprint(after)
    evidence.fingerprint = {
        "before": before_fingerprint,
        "after": after_fingerprint,
        "equal": before_fingerprint == after_fingerprint,
        # Reported separately from both byte measurements: `canonical_markdown`
        # absorbs the re-serialization of constraint 11, so this can pass while
        # whole-document bytes differ. That combination is a successful result.
        "document_fingerprint_equality": (
            PASS if before_fingerprint == after_fingerprint else FAIL
        ),
    }
    evidence.record(
        "document_fingerprint_stable",
        before_fingerprint == after_fingerprint,
        f"{before_fingerprint} != {after_fingerprint}",
    )
    return after


def snapshot_durable_state(
    workspace: FiberyArchitectureWorkspace, root_id: str, secret: str
) -> dict[str, Any]:
    """The observable durable state of one Document: placement and content.

    **Total for expected read failures.** A placement read or a content read that
    fails produces an UNREADABLE snapshot rather than an exception, because the
    duplicate classifier must still be able to run and report that the state
    could not be established. An unreadable snapshot is never evidence that
    nothing changed. A programmer error still propagates to the top-level safe
    handler.

    The content secret is never part of the snapshot — `placement_dict` reduces
    it to a `secret_present` flag — so two snapshots can be compared without a
    secret entering the comparison or the evidence. Nothing is fabricated: an
    unread value stays `None`.
    """
    state: dict[str, Any] = {
        "placement": {"present": False},
        "name": None,
        "content_sha256": None,
        "readable": False,
        "sanitized_error": None,
    }
    try:
        placement = register_placement_secret(workspace.resolve_placement(root_id))
    except EXPECTED_FAILURES as error:
        state["sanitized_error"] = sanitize(error, (secret,))
        return state
    if placement is None:
        state["sanitized_error"] = "the Document could not be resolved"
        return state
    state["placement"] = placement_dict(placement)
    state["name"] = placement.name
    try:
        state["content_sha256"] = sha256(workspace.read_document_content(secret))
    except EXPECTED_FAILURES as error:
        state["sanitized_error"] = sanitize(error, (secret,))
        return state
    state["readable"] = True
    return state


def classify_create_outcome(error: BaseException | None) -> str:
    """What the duplicate create attempt itself did.

    Decided from the sanitized public message only, and it must identify **the
    create method itself**. `Views method 'create-views' failed: ... returned a
    JSON-RPC error ...` is Fibery answering a create and refusing it. The same
    JSON-RPC wording from `query-views` is a read-back failure and proves
    nothing about the preceding mutation. Everything else — a timeout, a reset
    connection, a DNS failure, a bare `OSError`, a generic message — leaves it
    unknown whether the mutation was applied server side.
    """
    if error is None:
        return OUTCOME_SUCCESS
    if not isinstance(error, FiberyError):
        return OUTCOME_UNKNOWN_TRANSPORT
    message = str(error)
    # BOTH markers. A `query-views` JSON-RPC error carries the second one while
    # saying nothing about whether the create was applied.
    if CREATE_METHOD_MARKER in message and SERVER_RESPONSE_MARKER in message:
        return OUTCOME_CONFIRMED_REJECTION
    return OUTCOME_UNKNOWN_TRANSPORT


def classify_duplicate(
    outcome: str, before: dict[str, Any], after: dict[str, Any]
) -> str:
    """Classify a duplicate-create attempt from the outcome and the snapshots.

    Precedence matters. An observed durable mutation outranks everything: it is
    `MUTATED_EXISTING` even when the transport outcome is unknown, because the
    damage is established whatever the call reported. Only when nothing changed
    does the transport outcome decide, and an unknown outcome can never become
    `REJECTED` — a timeout with unchanged state means we do not know whether the
    create was applied, not that it was refused.
    """
    if not before["readable"] or not after["readable"]:
        return DUPLICATE_OTHER
    unchanged = (
        before["placement"] == after["placement"]
        and before["name"] == after["name"]
        and before["content_sha256"] == after["content_sha256"]
    )
    if not unchanged:
        return DUPLICATE_MUTATED_EXISTING
    if outcome == OUTCOME_CONFIRMED_REJECTION:
        return DUPLICATE_REJECTED
    if outcome == OUTCOME_SUCCESS:
        return DUPLICATE_IDEMPOTENT
    return DUPLICATE_OTHER


def probe_duplicate_id(
    workspace: FiberyArchitectureWorkspace,
    evidence: Evidence,
    project: ProjectRecord,
    root_id: str,
    root_name: str,
    secret: str,
) -> None:
    """Attempt a second create at an existing id, classify it, and gate on it."""
    duplicate_name = f"{root_name} DUPLICATE ATTEMPT"
    before = snapshot_durable_state(workspace, root_id, secret)

    failure: BaseException | None = None
    try:
        # The return is registered rather than discarded: on the IDEMPOTENT path
        # the call succeeds and can hand back a Document carrying a new secret.
        register_document_secret(
            workspace.create_project_document(
                root_id, duplicate_name, project.public_id
            )
        )
    except EXPECTED_FAILURES as error:
        failure = error

    create_outcome = classify_create_outcome(failure)
    after = snapshot_durable_state(workspace, root_id, secret)
    classification = classify_duplicate(create_outcome, before, after)

    evidence.duplicate = {
        "attempted_id": root_id,
        "attempted_name": duplicate_name,
        "raised": failure is not None,
        "create_outcome": create_outcome,
        "error": sanitize(failure, (secret,)) if failure is not None else None,
        "state_before": before,
        "state_after": after,
        "placement_unchanged": before["placement"] == after["placement"],
        "name_unchanged": before["name"] == after["name"],
        "content_unchanged": (
            before["content_sha256"] is not None
            and before["content_sha256"] == after["content_sha256"]
        ),
        "name_after": after["name"],
        "classification": classification,
        "expected": DUPLICATE_EXPECTED,
    }

    # Anything but the live-confirmed behaviour is a discrepancy that fails the
    # run. A duplicate outcome is never informational-only.
    if classification == DUPLICATE_EXPECTED:
        return
    label = {
        DUPLICATE_IDEMPOTENT: FAILURE_DUPLICATE_UNEXPECTED,
        DUPLICATE_MUTATED_EXISTING: FAILURE_DUPLICATE_STATE_CHANGED,
        DUPLICATE_OTHER: FAILURE_DUPLICATE_UNKNOWN,
    }[classification]
    evidence.record(
        label,
        False,
        f"classified {classification}, expected {DUPLICATE_EXPECTED}",
    )


def record_drift_not_executed(evidence: Evidence) -> None:
    """F row 22 needs an out-of-band placement edit; nothing here can do one.

    The repository wraps exactly two Views methods, `query-views` and
    `create-views`. `create-views` sets placement only at create time, and there
    is no `update-views` or `delete-views` wrapper. Inducing live placement
    drift would mean adding a new Fibery write capability, which is outside I03
    and is exactly what the frozen work item forbids. The row is therefore not
    executed rather than forced or fabricated.
    """
    evidence.drift = {
        "result": DRIFT_NOT_EXECUTED,
        "reason": (
            "No safe reversible placement-mutation mechanism exists: the client "
            "wraps query-views and create-views only, create-views sets "
            "placement at create time, and no update-views or delete-views "
            "wrapper exists. Adding one would be a new write capability outside "
            "I03."
        ),
        "method": None,
    }


def run(arguments: argparse.Namespace, evidence: Evidence) -> int:
    try:
        settings = load_fibery_settings()
    except ConfigurationError as error:
        print(f"BLOCKED: {error}", file=sys.stderr)
        return EXIT_BLOCKED
    register_secret(settings.token)

    client = FiberyClient(settings)
    client.resolve_space_id()
    workspace = FiberyArchitectureWorkspace(client, settings.space)
    evidence.workspace_identity = client.workspace_identity

    project = resolve_scratch_project(workspace, arguments.project_id)
    if project is None:
        print(
            "BLOCKED_NEEDS_SCRATCH_PROJECT: no Project at entity id "
            f"{arguments.project_id!r}.",
            file=sys.stderr,
        )
        return EXIT_BLOCKED
    if not project.public_id:
        print(
            "BLOCKED_NEEDS_SCRATCH_PROJECT: the Project carries no public id.",
            file=sys.stderr,
        )
        return EXIT_BLOCKED

    evidence.project.update(
        {
            "name": project.name,
            "entity_id": project.id,
            "public_id": project.public_id,
            "code": project.code,
            "state": project.state,
        }
    )
    print("Scratch Project resolved by exact entity id:")
    print(f"  name      : {project.name}")
    print(f"  entity id : {project.id}")
    print(f"  public id : {project.public_id}")

    if not arguments.confirm_live_mutation:
        print(
            "\nStopping before any mutation: rerun with --confirm-live-mutation "
            "once the Project above is confirmed to be the scratch Project.",
        )
        _emit_once(evidence, arguments.evidence_out)
        return EXIT_BLOCKED

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    root_name = f"{arguments.probe_prefix} ROOT {stamp}"
    child_name = f"{arguments.probe_prefix} CHILD {stamp}"

    root_id, root_placement = probe_root(workspace, evidence, project, root_name)
    if root_placement is None:
        _emit_once(evidence, arguments.evidence_out)
        return EXIT_FAILED

    probe_rediscovery(workspace, evidence, project, root_id, root_placement)
    probe_child(workspace, evidence, project, root_id, root_placement, child_name)

    secret = root_placement.secret
    if secret is None:
        evidence.record("root_secret_usable", False, "no secret to write content with")
        _emit_once(evidence, arguments.evidence_out)
        return EXIT_FAILED
    probe_content(workspace, evidence, secret)
    probe_duplicate_id(workspace, evidence, project, root_id, root_name, secret)
    record_drift_not_executed(evidence)

    evidence.completed = True
    _emit_once(evidence, arguments.evidence_out)
    return EXIT_OK if not evidence.failures else EXIT_FAILED


def _emit_once(evidence: Evidence, destination: str | None) -> None:
    """Write the evidence exactly once, converting any failure to a marker.

    The marker is what makes the "no second write" invariant structural rather
    than a convention: a caller that receives `EvidenceOutputFailed` cannot
    retry through the generic reporter, because the reporter is told the write
    already happened and failed.

    **This is the only place `_emit` may be called.** Every path that writes
    evidence — the final emission, each early return, and the reporter's own
    partial write — goes through here, so there is exactly one guarded writer
    and no path can acquire its own error handling. A structural test asserts
    no other call site exists.
    """
    try:
        _emit(evidence, destination)
    except EXPECTED_OUTPUT_FAILURES as error:
        raise EvidenceOutputFailed(
            f"partial evidence not written: {sanitize(error)}"
        ) from None
    except Exception:  # noqa: BLE001 - an output bug must not leak either
        # Deliberately message-free: an unexpected exception here is not known
        # to be sanitized, and no diagnostic is worth risking a leak.
        raise EvidenceOutputFailed(
            "evidence not written: unexpected output failure"
        ) from None


def _emit(evidence: Evidence, destination: str | None) -> None:
    payload = json.dumps(asdict(evidence), indent=2, sort_keys=True, ensure_ascii=False)
    if destination:
        with open(destination, "w", encoding="utf-8") as handle:
            handle.write(payload + "\n")
        print(f"\nEvidence written to {destination}")
    else:
        print("\n" + payload)
    if evidence.failures:
        print("\nFAILED CHECKS:", file=sys.stderr)
        for failure in evidence.failures:
            print(f"  - {failure}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    """The probe proper. May raise; `cli` is the safe boundary around it."""
    arguments = parse_arguments(argv)
    evidence = Evidence(started_at=datetime.now(UTC).isoformat(timespec="seconds"))
    return run(arguments, evidence)


def cli(argv: list[str] | None = None) -> int:
    """The entry point. No expected failure reaches the default traceback.

    Python's default handler prints the whole cause chain, and
    `FiberyClient` raises its sanitized `FiberyError` with `from error`, so the
    original transport exception — which can carry a token or a document
    secret — would be printed verbatim. Nothing here formats a traceback, a
    `repr`, a `__cause__` or a `__context__`: only the sanitized public message.
    """
    arguments: argparse.Namespace | None = None
    evidence = Evidence(started_at=datetime.now(UTC).isoformat(timespec="seconds"))
    try:
        arguments = parse_arguments(argv)
        return run(arguments, evidence)
    except EvidenceOutputFailed as output_error:
        # The write already happened and failed. Report it and stop: no second
        # attempt, and no path back into the generic reporter.
        _safe_stderr(f"FAILED: {output_error.message}")
        return EXIT_FAILED
    except EXPECTED_FAILURES as error:
        return _report_failure(evidence, arguments, sanitize(error))
    except Exception as error:  # noqa: BLE001 - a bug must not leak either
        # An unexpected exception's message is not known to be sanitized, so it
        # is scrubbed against the registry like any other.
        return _report_failure(
            evidence, arguments, f"unexpected failure: {sanitize(error)}"
        )


def _safe_stderr(message: str) -> None:
    """One sanitized line to stderr, and never an exception of its own.

    The failure reporter calls this, so it must not be able to fail: a broken
    stream while reporting a failure must not become a second unhandled error.
    """
    # Suppressed deliberately: there is no further channel to report a failure
    # of the failure channel, and raising here would hand control back to the
    # default traceback printer.
    with contextlib.suppress(Exception):
        print(scrub(message), file=sys.stderr)


def _report_failure(
    evidence: Evidence, arguments: argparse.Namespace | None, message: str
) -> int:
    """Record a sanitized failure, keep safe partial evidence, exit nonzero.

    **This function never raises.** It is the handler of last resort, so an
    error while reporting — a bad `--evidence-out` path, a full disk, a closed
    stream — must not escape and let the default traceback printer run. Each
    step is independently guarded, and the recovery path never re-enters this
    reporter.
    """
    evidence.completed = False
    evidence.failure = message
    evidence.failures.append(f"run_failed: {message}")
    _safe_stderr(f"FAILED: {message}")

    destination = getattr(arguments, "evidence_out", None) if arguments else None
    if not (destination and _has_partial_evidence(evidence)):
        return EXIT_FAILED
    # Exactly one attempt. `_emit_once` converts any failure into a marker
    # carrying a sanitized message, which is reported and never retried.
    try:
        _emit_once(evidence, destination)
    except EvidenceOutputFailed as output_error:
        _safe_stderr(output_error.message)
    return EXIT_FAILED


def _has_partial_evidence(evidence: Evidence) -> bool:
    """Whether anything was measured before the failure."""
    return bool(evidence.project or evidence.root or evidence.child or evidence.checks)


if __name__ == "__main__":
    raise SystemExit(cli())
