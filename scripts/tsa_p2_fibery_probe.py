#!/usr/bin/env python
"""P-2: live Fibery measurements for TSA-C01 gates I-2 and I-3.

This is a probe instrument, not part of the `sdlc` capability. It measures:

- I-2: a UX Document's identity under content replacement, a second Document
  with the same name, and (separately confirmed) deletion of a probe-owned
  Document — and whether the production I05 UX read (`admit_ux`) then treats
  the originally bound UX as no longer current;
- I-3: the practical size of a fenced JSON payload in one Fibery Document, for
  fixed samples up to 1 MiB, and what a refused or unknown write leaves behind.

Every Fibery call goes through the existing `FiberyArchitectureWorkspace` and
`FiberyClient`. The one deletion uses the documented Views method `delete-views`
(API constraint 23) through the client's existing `views_rpc`, on a Document
this run created; no production method is added.

    # Offline preflight (default): the whole flow against the in-memory fake.
    uv run python scripts/tsa_p2_fibery_probe.py --preflight

    # Live, read-only resolution of the scratch Project, then stop.
    uv run python scripts/tsa_p2_fibery_probe.py --live --project-id <id> \\
        --expect-code <code> --expect-public-id <public id>

    # Live mutations (and, only with the extra flag, the one deletion).
    uv run python scripts/tsa_p2_fibery_probe.py --live --project-id <id> \\
        --expect-code <code> --expect-public-id <public id> \\
        --confirm-live-mutation [--confirm-probe-deletion] --evidence-out <file>

Secrets are never printed or recorded: the token and every Document secret are
registered and scrubbed, errors are reduced to their sanitized public message,
and large content is recorded only as hashes and byte counts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sdlc.config import ConfigurationError, load_fibery_settings
from sdlc.fibery_client import FiberyClient
from sdlc.fibery_http import FiberyArchitectureWorkspace
from sdlc.fibery_workspace import (
    DocumentPlacement,
    FiberyError,
    ProjectRecord,
    is_valid_root_placement,
)
from sdlc.normative_tree import document_fingerprint
from sdlc.tsa_admission import AdmissionRefused, UxApplicable, admit_ux
from sdlc.tsa_artifacts import canonical_json

PROBE_PREFIX = "TSA-P2-PROBE"
SCRATCH_MARKER = "SCRATCH"
#: Fixed I-3 samples: fenced JSON payload sizes in bytes. Probe samples, not
#: asserted limits. Nothing above 1 MiB is ever attempted automatically.
SIZE_SAMPLES = (8 * 1024, 64 * 1024, 256 * 1024, 512 * 1024, 1024 * 1024)
MAX_SAMPLE_BYTES = 1024 * 1024
#: Hard caps on live mutations for one run.
MAX_CREATES = 2 + len(SIZE_SAMPLES)
MAX_WRITES = 3 + len(SIZE_SAMPLES)
MAX_DELETES = 1
DELETE_VIEWS_METHOD = "delete-views"
#: A synthetic Requirement id for the UX scope of the I05 read. Never resolved.
SYNTHETIC_SCOPE = ("TSAP2-FR-0001",)
JSON_FENCE_OPENER = "```json"
FENCE_MARKER = "```"
REDACTED = "<redacted>"
FILLER_ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789"

VERIFIED = "VERIFIED"
FAILED = "FAILED"
INCOMPLETE = "INCOMPLETE"
NOT_EXECUTED = "NOT_EXECUTED"

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_BLOCKED = 2

_SECRETS: set[str] = set()


class ProbeRefused(Exception):
    """A safety guard refused an operation; nothing was mutated by it."""


def register_secret(value: str | None) -> None:
    if value:
        _SECRETS.add(value)


def scrub(text: str) -> str:
    for secret in _SECRETS:
        text = text.replace(secret, REDACTED)
    return text


def sanitize(error: BaseException) -> str:
    """The type and sanitized public message only; never the cause chain."""
    return scrub(f"{type(error).__name__}: {error}")


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def extract_json_fence(markdown: str) -> str | None:
    """The exact text between the one ```json opener and its closing fence."""
    lines = markdown.split("\n")
    openers = [i for i, line in enumerate(lines) if line.strip() == JSON_FENCE_OPENER]
    if len(openers) != 1:
        return None
    start = openers[0]
    closing = next(
        (i for i in range(start + 1, len(lines)) if lines[i].strip() == FENCE_MARKER),
        None,
    )
    if closing is None:
        return None
    return "\n".join(lines[start + 1 : closing])


def placement_dict(placement: DocumentPlacement | None) -> dict[str, Any]:
    if placement is None:
        return {"present": False}
    register_secret(placement.secret)
    return {
        "present": True,
        "document_id": placement.document_id,
        "name": placement.name,
        "container_entity_type": placement.container_entity_type,
        "container_entity_id": placement.container_entity_id,
        "parent_document_id": placement.parent_document_id,
        "secret_present": placement.secret is not None,
    }


def project_dict(project: ProjectRecord) -> dict[str, Any]:
    return {
        "entity_id": project.id,
        "name": project.name,
        "code": project.code,
        "public_id": project.public_id,
        "state": project.state,
    }


# ---------------------------------------------------------------------------
# Payloads (deterministic, synthetic)
# ---------------------------------------------------------------------------


def size_fence(sample_bytes: int) -> str:
    """Canonical JSON of exactly `sample_bytes` UTF-8 bytes, all ASCII."""
    if sample_bytes > MAX_SAMPLE_BYTES:
        raise ProbeRefused(f"sample {sample_bytes} exceeds the 1 MiB cap")
    empty = canonical_json(
        {"filler": "", "probe": "tsa-p2", "sample_bytes": sample_bytes}
    )
    pad = sample_bytes - len(empty.encode("utf-8"))
    if pad < 0:
        raise ProbeRefused(f"sample {sample_bytes} is smaller than the envelope")
    filler = (FILLER_ALPHABET * (pad // len(FILLER_ALPHABET) + 1))[:pad]
    fence = canonical_json(
        {"filler": filler, "probe": "tsa-p2", "sample_bytes": sample_bytes}
    )
    assert len(fence.encode("utf-8")) == sample_bytes
    return fence


def carrier(name: str, fence: str) -> str:
    return (
        f"# {name}\n\nSynthetic TSA-C01 P-2 probe content. Not an artifact of any "
        f"cycle and not a requirement.\n\n{JSON_FENCE_OPENER}\n{fence}\n"
        f"{FENCE_MARKER}\n"
    )


def ux_content(label: str, run_id: str) -> str:
    return (
        f"# Synthetic UX {label}\n\nTSA-C01 P-2 probe UX Document, variant "
        f"{label}, run {run_id}. The user confirms a synthetic action on one "
        "screen.\n"
    )


# ---------------------------------------------------------------------------
# The guarded backend: every mutation passes the same checks
# ---------------------------------------------------------------------------


@dataclass
class Counters:
    creates: int = 0
    writes: int = 0
    deletes: int = 0


@dataclass
class Evidence:
    mode: str
    started_utc: str
    run_id: str
    adapter: str = "FiberyArchitectureWorkspace over FiberyClient"
    workspace_identity: str | None = None
    project: dict[str, Any] = field(default_factory=dict)
    confirmations: dict[str, bool] = field(default_factory=dict)
    owned_documents: list[dict[str, Any]] = field(default_factory=list)
    i2: dict[str, Any] = field(default_factory=dict)
    i3: list[dict[str, Any]] = field(default_factory=list)
    project_unchanged: bool | None = None
    counters: dict[str, int] = field(default_factory=dict)
    finished_utc: str | None = None
    blocked: str | None = None


class Probe:
    """Owns the run: the scratch Project check and every guarded mutation."""

    def __init__(
        self,
        workspace: Any,
        delete_documents: Callable[[list[str]], None],
        project_id: str,
        expect_code: str,
        expect_public_id: str,
        allow_delete: bool,
        evidence: Evidence,
    ) -> None:
        self.workspace = workspace
        self._delete_documents = delete_documents
        self.project_id = project_id
        self.expect_code = expect_code
        self.expect_public_id = expect_public_id
        self.allow_delete = allow_delete
        self.evidence = evidence
        self.counters = Counters()
        self.owned: dict[str, str] = {}
        self.baseline: ProjectRecord | None = None

    # -- the scratch Project ------------------------------------------------

    def resolve_scratch_project(self) -> ProjectRecord:
        project = self.workspace.read_project(self.project_id)
        if project is None:
            raise ProbeRefused(f"no Project at entity id {self.project_id!r}")
        if SCRATCH_MARKER not in (project.name or "").upper():
            raise ProbeRefused("the Project name does not designate it as scratch")
        if project.code != self.expect_code:
            raise ProbeRefused("the Project Code is not the expected scratch code")
        if project.public_id != self.expect_public_id:
            raise ProbeRefused("the Project public id is not the expected one")
        return project

    def _require_project_unchanged(self) -> ProjectRecord:
        project = self.resolve_scratch_project()
        if self.baseline is not None and project_dict(project) != project_dict(
            self.baseline
        ):
            raise ProbeRefused("the scratch Project changed during the run")
        return project

    # -- guarded mutations --------------------------------------------------

    def _require_owned_root(self, document_id: str) -> DocumentPlacement:
        if document_id not in self.owned:
            raise ProbeRefused(f"{document_id!r} was not created by this run")
        project = self._require_project_unchanged()
        placement = self.workspace.resolve_placement(document_id)
        if placement is None:
            raise ProbeRefused(f"{document_id!r} does not resolve")
        register_secret(placement.secret)
        if placement.name != self.owned[document_id]:
            raise ProbeRefused(f"{document_id!r} no longer carries the probe name")
        if not is_valid_root_placement(
            placement, self.workspace.project_type_id, project.public_id
        ):
            raise ProbeRefused(f"{document_id!r} is not a root of the scratch Project")
        return placement

    def create(self, name: str) -> str:
        if self.counters.creates >= MAX_CREATES:
            raise ProbeRefused("the create cap is reached")
        if not name.startswith(f"{PROBE_PREFIX} ") or self.evidence.run_id not in name:
            raise ProbeRefused("a probe Document must carry the probe prefix and run")
        project = self._require_project_unchanged()
        document_id = str(uuid.uuid4())
        if self.workspace.resolve_placement(document_id) is not None:
            raise ProbeRefused("the fresh probe id is already occupied")
        self.counters.creates += 1
        self.owned[document_id] = name
        self.evidence.owned_documents.append(
            {"document_id": document_id, "name": name, "deleted": False}
        )
        node = self.workspace.create_project_document(
            document_id, name, project.public_id
        )
        register_secret(node.secret)
        return document_id

    def write(self, document_id: str, markdown: str) -> None:
        if self.counters.writes >= MAX_WRITES:
            raise ProbeRefused("the write cap is reached")
        placement = self._require_owned_root(document_id)
        if not placement.secret:
            raise ProbeRefused(f"{document_id!r} exposes no content secret")
        self.counters.writes += 1
        self.workspace.write_document_content(placement.secret, markdown)

    def delete(self, document_id: str) -> None:
        if not self.allow_delete:
            raise ProbeRefused("deletion needs --confirm-probe-deletion")
        if self.counters.deletes >= MAX_DELETES:
            raise ProbeRefused("the delete cap is reached")
        self._require_owned_root(document_id)
        self.counters.deletes += 1
        self._delete_documents([document_id])
        for owned in self.evidence.owned_documents:
            if owned["document_id"] == document_id:
                owned["deleted"] = True

    # -- reads ----------------------------------------------------------------

    def read(self, document_id: str) -> str:
        placement = self.workspace.resolve_placement(document_id)
        if placement is None or not placement.secret:
            raise ProbeRefused(f"{document_id!r} has no readable content")
        register_secret(placement.secret)
        return self.workspace.read_document_content(placement.secret)

    def listing(self) -> list[DocumentPlacement]:
        placements = self.workspace.documents_attached_to_project(
            self.baseline.public_id
        )
        for placement in placements:
            register_secret(placement.secret)
        return placements

    def ux_binding(self, document_id: str) -> dict[str, Any]:
        """The production I05 UX read of this Document, or its refusal."""
        try:
            evidence = admit_ux(
                self.workspace, UxApplicable(document_id, SYNTHETIC_SCOPE)
            )
        except AdmissionRefused as refused:
            return {"refused": str(refused.code), "message": scrub(str(refused))}
        return {"content_digest": evidence["content_digest"]}


# ---------------------------------------------------------------------------
# I-2
# ---------------------------------------------------------------------------


def _listed(probe: Probe, document_id: str) -> int:
    return sum(1 for p in probe.listing() if p.document_id == document_id)


def run_i2(probe: Probe) -> None:
    run_id = probe.evidence.run_id
    shared_name = f"{PROBE_PREFIX} UX {run_id}"
    i2: dict[str, Any] = probe.evidence.i2

    # A. UX-A, bound as an APPLICABLE UX would be.
    a_id = probe.create(shared_name)
    a_content = ux_content("A", run_id)
    probe.write(a_id, a_content)
    a_read = probe.read(a_id)
    bound = probe.ux_binding(a_id)
    i2["A_initial"] = {
        "document_id": a_id,
        "placement": placement_dict(probe.workspace.resolve_placement(a_id)),
        "listed_times": _listed(probe, a_id),
        "emitted_fingerprint": document_fingerprint(a_content),
        "read_fingerprint": document_fingerprint(a_read),
        "i05_binding": bound,
    }

    # B/C. UX-B with the same name; identity, not name, distinguishes them.
    b_id = probe.create(shared_name)
    b_content = ux_content("B", run_id)
    probe.write(b_id, b_content)
    a_after_b = probe.read(a_id)
    same_name = [p.document_id for p in probe.listing() if p.name == shared_name]
    i2["B_same_name"] = {
        "document_id": b_id,
        "ids_distinct": a_id != b_id,
        "placement": placement_dict(probe.workspace.resolve_placement(b_id)),
        "listed_times": _listed(probe, b_id),
        "same_name_documents_listed": len(same_name),
        "a_unchanged": document_fingerprint(a_after_b)
        == i2["A_initial"]["read_fingerprint"],
        "b_read_fingerprint": document_fingerprint(probe.read(b_id)),
        "i05_binding_a_still": probe.ux_binding(a_id),
    }

    # D/E. Content replacement at UX-A's own id.
    a2_content = ux_content("A2", run_id)
    probe.write(a_id, a2_content)
    a2_read = probe.read(a_id)
    rebound = probe.ux_binding(a_id)
    i2["D_content_replaced"] = {
        "identity_unchanged": probe.workspace.resolve_placement(a_id) is not None,
        "placement": placement_dict(probe.workspace.resolve_placement(a_id)),
        "listed_times": _listed(probe, a_id),
        "read_fingerprint": document_fingerprint(a2_read),
        "fingerprint_changed": document_fingerprint(a2_read)
        != i2["A_initial"]["read_fingerprint"],
        "i05_binding": rebound,
        "original_binding_no_longer_current": rebound.get("content_digest")
        != bound.get("content_digest"),
    }

    # F. Deletion of UX-A, only with the separate confirmation.
    if not probe.allow_delete:
        i2["F_deleted"] = {"status": NOT_EXECUTED, "reason": "not confirmed"}
        return
    probe.delete(a_id)
    i2["F_deleted"] = {
        "deleted_id": a_id,
        "rediscovered_by_id": probe.workspace.resolve_placement(a_id) is not None,
        "listed_times_after": _listed(probe, a_id),
        "b_listed_times_after": _listed(probe, b_id),
        "b_unchanged": document_fingerprint(probe.read(b_id))
        == i2["B_same_name"]["b_read_fingerprint"],
        "i05_binding_deleted_id": probe.ux_binding(a_id),
        "same_name_documents_listed_after": sum(
            1 for p in probe.listing() if p.name == shared_name
        ),
    }


def classify_i2(i2: dict[str, Any]) -> dict[str, str]:
    a, b, d = i2.get("A_initial"), i2.get("B_same_name"), i2.get("D_content_replaced")
    f = i2.get("F_deleted", {})
    result = {}
    if a is None:
        return {"all": INCOMPLETE}
    result["direct_id_rediscovery"] = (
        VERIFIED
        if a["placement"]["present"]
        and a["placement"]["document_id"] == a["document_id"]
        else FAILED
    )
    result["project_listing"] = VERIFIED if a["listed_times"] == 1 else FAILED
    result["fingerprint_currentness"] = (
        VERIFIED
        if "content_digest" in a["i05_binding"]
        and a["i05_binding"]["content_digest"] == a["read_fingerprint"]
        else FAILED
    )
    if b is not None:
        result["replacement_by_other_identity_original_present"] = (
            VERIFIED
            if b["ids_distinct"]
            and b["a_unchanged"]
            and b["listed_times"] == 1
            and b["same_name_documents_listed"] == 2
            and b["i05_binding_a_still"] == a["i05_binding"]
            else FAILED
        )
    if d is not None:
        result["content_modification"] = (
            VERIFIED
            if d["identity_unchanged"]
            and d["fingerprint_changed"]
            and d["listed_times"] == 1
            else FAILED
        )
        result["original_binding_invalidation_by_modification"] = (
            VERIFIED if d["original_binding_no_longer_current"] else FAILED
        )
    if f.get("status") == NOT_EXECUTED:
        result["deletion"] = NOT_EXECUTED
        result["original_binding_invalidation_by_deletion"] = NOT_EXECUTED
    elif f:
        result["deletion"] = (
            VERIFIED
            if not f["rediscovered_by_id"]
            and f["listed_times_after"] == 0
            and f["b_listed_times_after"] == 1
            and f["b_unchanged"]
            else FAILED
        )
        result["original_binding_invalidation_by_deletion"] = (
            VERIFIED
            if f["i05_binding_deleted_id"].get("refused") == "UX_EVIDENCE_INVALID"
            else FAILED
        )
    return result


# ---------------------------------------------------------------------------
# I-3
# ---------------------------------------------------------------------------


def durable_state(probe: Probe, document_id: str, emitted_fence: str) -> str:
    try:
        content = probe.read(document_id)
    except (FiberyError, ProbeRefused):
        return "UNREADABLE"
    if not content.strip():
        return "EMPTY"
    fence = extract_json_fence(content)
    if fence == emitted_fence:
        return "COMPLETE_NEW"
    return "PARTIAL_OR_MALFORMED"


def run_i3(probe: Probe) -> None:
    for sample in SIZE_SAMPLES:
        name = f"{PROBE_PREFIX} SIZE {sample} {probe.evidence.run_id}"
        fence = size_fence(sample)
        markdown = carrier(name, fence)
        record: dict[str, Any] = {
            "sample_bytes": sample,
            "fence_bytes": len(fence.encode("utf-8")),
            "fence_code_points": len(fence),
            "fence_sha256": sha256(fence),
            "emitted_markdown_bytes": len(markdown.encode("utf-8")),
            "emitted_markdown_sha256": sha256(markdown),
            "emitted_fingerprint": document_fingerprint(markdown),
        }
        probe.evidence.i3.append(record)
        document_id = probe.create(name)
        record["document_id"] = document_id
        record["placement_before_write"] = placement_dict(
            probe.workspace.resolve_placement(document_id)
        )
        try:
            probe.write(document_id, markdown)
            record["write"] = "RETURNED"
        except FiberyError as error:
            record["write"] = "RAISED"
            record["write_error"] = sanitize(error)
        record["durable_state"] = durable_state(probe, document_id, fence)
        if record["durable_state"] in ("COMPLETE_NEW", "PARTIAL_OR_MALFORMED"):
            read = probe.read(document_id)
            read_fence = extract_json_fence(read)
            record["read_markdown_bytes"] = len(read.encode("utf-8"))
            record["read_markdown_sha256"] = sha256(read)
            record["read_fingerprint"] = document_fingerprint(read)
            record["fingerprint_equal"] = (
                record["read_fingerprint"] == record["emitted_fingerprint"]
            )
            record["whole_markdown_equal"] = read == markdown
            record["read_fence_bytes"] = (
                None if read_fence is None else len(read_fence.encode("utf-8"))
            )
            record["fence_exact"] = read_fence == fence
            try:
                record["fence_json_valid"] = (
                    read_fence is not None
                    and json.loads(read_fence)["sample_bytes"] == sample
                )
            except (ValueError, KeyError, TypeError):
                record["fence_json_valid"] = False
        record["classification"] = (
            "SUCCESS"
            if record["write"] == "RETURNED"
            and record["durable_state"] == "COMPLETE_NEW"
            and record.get("fence_exact")
            else "NOT_SUCCESS"
        )
        if record["classification"] != "SUCCESS":
            break  # one attempt per sample, and no larger sample after a failure


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------


def execute(probe: Probe, mutate: bool) -> int:
    evidence = probe.evidence
    project = probe.resolve_scratch_project()
    probe.baseline = project
    evidence.project = project_dict(project)
    if not mutate:
        evidence.blocked = "read-only: --confirm-live-mutation not given"
        return EXIT_BLOCKED
    run_i2(probe)
    evidence.i2["classification"] = classify_i2(evidence.i2)
    run_i3(probe)
    evidence.project_unchanged = project_dict(
        probe.resolve_scratch_project()
    ) == project_dict(project)
    return EXIT_OK


def preflight() -> int:
    """The whole flow against the in-memory fake, plus the guards' refusals."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
    from architecture_fake import PROJECT_TYPE_ID, FakeArchitectureWorkspace

    for sample in SIZE_SAMPLES:
        fence = size_fence(sample)
        assert len(fence.encode("utf-8")) == sample == len(fence)
        assert json.loads(fence)["sample_bytes"] == sample
        assert extract_json_fence(carrier("x", fence)) == fence
    try:
        size_fence(MAX_SAMPLE_BYTES + 1)
    except ProbeRefused:
        pass
    else:
        raise AssertionError("the 1 MiB cap was not enforced")
    register_secret("preflight-secret-value")
    assert REDACTED in scrub("token=preflight-secret-value")

    results = {}
    for allow_delete in (False, True):
        project = ProjectRecord(
            id="scratch-entity",
            name="TSA P-2 SCRATCH — DO NOT USE",
            code="TSAP2",
            state="Planned",
            public_id="99",
        )
        fake = FakeArchitectureWorkspace([project], PROJECT_TYPE_ID)

        def delete(ids: list[str], fake=fake) -> None:
            for document_id in ids:
                fake.documents.pop(document_id)

        evidence = Evidence("preflight", _now(), _run_id())
        probe = Probe(
            fake, delete, "scratch-entity", "TSAP2", "99", allow_delete, evidence
        )
        assert execute(probe, mutate=True) == EXIT_OK
        results[allow_delete] = evidence
        assert probe.counters.creates <= MAX_CREATES
        assert probe.counters.writes <= MAX_WRITES
        assert probe.counters.deletes == (1 if allow_delete else 0)
        try:
            probe.delete(next(iter(probe.owned)))
        except ProbeRefused:
            pass
        else:
            raise AssertionError("a second or unconfirmed deletion was allowed")
        try:
            probe.write("not-owned", "x")
        except ProbeRefused:
            pass
        else:
            raise AssertionError("a write to a non-probe Document was allowed")

    for wrong in (("other-entity", "TSAP2", "99"), ("scratch-entity", "XX", "99")):
        fake = FakeArchitectureWorkspace(
            [
                ProjectRecord(
                    "scratch-entity", "TSA P-2 SCRATCH", "TSAP2", "Planned", "99"
                )
            ],
            PROJECT_TYPE_ID,
        )
        probe = Probe(
            fake,
            lambda ids: None,
            *wrong,
            False,
            Evidence("preflight", _now(), _run_id()),
        )
        try:
            execute(probe, mutate=True)
        except ProbeRefused:
            pass
        else:
            raise AssertionError(f"an unexpected Project was accepted: {wrong}")
    not_scratch = FakeArchitectureWorkspace(
        [ProjectRecord("p", "Real Project", "REAL", "Planned", "1")], PROJECT_TYPE_ID
    )
    try:
        execute(
            Probe(
                not_scratch,
                lambda ids: None,
                "p",
                "REAL",
                "1",
                False,
                Evidence("preflight", _now(), _run_id()),
            ),
            mutate=True,
        )
    except ProbeRefused:
        pass
    else:
        raise AssertionError("a Project not designated scratch was accepted")

    print("PREFLIGHT OK (in-memory fake; no network)")
    for allow_delete, evidence in results.items():
        print(
            f"  deletion confirmed={allow_delete}: I-2 {evidence.i2['classification']}"
        )
        print(
            "  I-3 "
            + ", ".join(
                f"{r['sample_bytes']}:{r['classification']}" for r in evidence.i3
            )
        )
    print(
        f"  caps: creates {MAX_CREATES}, writes {MAX_WRITES}, deletes {MAX_DELETES}, "
        f"largest sample {MAX_SAMPLE_BYTES} bytes"
    )
    return EXIT_OK


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _run_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def live(arguments: argparse.Namespace) -> int:
    try:
        settings = load_fibery_settings()
    except ConfigurationError as error:
        print(f"BLOCKED: {error}", file=sys.stderr)
        return EXIT_BLOCKED
    register_secret(settings.token)
    client = FiberyClient(settings)
    client.resolve_space_id()
    workspace = FiberyArchitectureWorkspace(client, settings.space)

    def delete(ids: list[str]) -> None:
        client.views_rpc(DELETE_VIEWS_METHOD, {"ids": ids})

    evidence = Evidence("live", _now(), _run_id())
    evidence.workspace_identity = client.workspace_identity
    evidence.confirmations = {
        "confirm_live_mutation": arguments.confirm_live_mutation,
        "confirm_probe_deletion": arguments.confirm_probe_deletion,
    }
    probe = Probe(
        workspace,
        delete,
        arguments.project_id,
        arguments.expect_code,
        arguments.expect_public_id,
        arguments.confirm_probe_deletion,
        evidence,
    )
    status = EXIT_FAILED
    try:
        status = execute(probe, arguments.confirm_live_mutation)
    except ProbeRefused as refused:
        evidence.blocked = f"refused: {scrub(str(refused))}"
        status = EXIT_BLOCKED
    except FiberyError as error:
        evidence.blocked = f"stopped: {sanitize(error)}"
        status = EXIT_FAILED
    finally:
        evidence.counters = asdict(probe.counters)
        evidence.finished_utc = _now()
        payload = scrub(json.dumps(asdict(evidence), indent=2, sort_keys=True))
        if arguments.evidence_out:
            Path(arguments.evidence_out).write_text(payload + "\n", encoding="utf-8")
            print(f"Evidence written to {arguments.evidence_out}")
        else:
            print(payload)
    print(f"status {status}; counters {asdict(probe.counters)}")
    return status


def parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--preflight", action="store_true", help="Offline (default).")
    mode.add_argument("--live", action="store_true")
    parser.add_argument("--project-id", help="Exact scratch Project entity id.")
    parser.add_argument("--expect-code", help="The scratch Project's Code.")
    parser.add_argument("--expect-public-id", help="The scratch Project's public id.")
    parser.add_argument("--confirm-live-mutation", action="store_true")
    parser.add_argument("--confirm-probe-deletion", action="store_true")
    parser.add_argument("--evidence-out")
    arguments = parser.parse_args(argv)
    if arguments.live and not (
        arguments.project_id and arguments.expect_code and arguments.expect_public_id
    ):
        parser.error("--live needs --project-id, --expect-code and --expect-public-id")
    if arguments.confirm_probe_deletion and not arguments.confirm_live_mutation:
        parser.error("--confirm-probe-deletion needs --confirm-live-mutation")
    return arguments


def main(argv: list[str] | None = None) -> int:
    arguments = parse_arguments(argv)
    if arguments.live:
        return live(arguments)
    return preflight()


if __name__ == "__main__":
    raise SystemExit(main())
