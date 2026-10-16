#!/usr/bin/env python
"""P-3: bounded live measurement of Fibery Document payload size (gate I-3).

P-2 established that a fenced canonical-JSON payload of up to 1 MiB survives a
Fibery Document write byte-exact. This probe measures two larger samples,
2 MiB and 4 MiB, each in its own fresh probe-owned Document of the scratch
Project, with exactly one write attempt and no retry. For each sample it
records whether the write returned, what the Document durably holds afterwards
(re-discovered and read back, never inferred from an exception), and how a
failure is attributable: a verified size refusal (HTTP 413) is kept apart from
any other HTTP status and from an unknown transport outcome.

The pure helpers (redaction, hashing, fence extraction, record shapes) are
reused from the P-2 probe; the guarded mutations are this probe's own, with
P-3's stricter caps. There is no deletion path at all.

    # Offline preflight (default): fake-backed flows and every guard refusal.
    uv run --frozen python scripts/tsa_p3_fibery_size_probe.py --preflight

    # Live, read-only Project verification, then stop.
    uv run --frozen --env-file <env> python scripts/tsa_p3_fibery_size_probe.py \\
        --live --project-id <id> --expect-code <code> --expect-public-id <id>

    # Live measurement.
    uv run --frozen --env-file <env> python scripts/tsa_p3_fibery_size_probe.py \\
        --live --project-id <id> --expect-code <code> --expect-public-id <id> \\
        --confirm-live-mutation --evidence-out <file>
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tsa_p2_fibery_probe import (
    FENCE_MARKER,
    FILLER_ALPHABET,
    JSON_FENCE_OPENER,
    SCRATCH_MARKER,
    ProbeRefused,
    extract_json_fence,
    placement_dict,
    project_dict,
    register_secret,
    sanitize,
    scrub,
    sha256,
)

from sdlc.config import ConfigurationError, load_fibery_settings
from sdlc.fibery_client import FiberyClient
from sdlc.fibery_http import FiberyArchitectureWorkspace
from sdlc.fibery_workspace import FiberyError, ProjectRecord, is_valid_root_placement
from sdlc.normative_tree import document_fingerprint
from sdlc.tsa_artifacts import canonical_json

PROBE_PREFIX = "TSA-P3-PROBE"
MIB = 1024 * 1024
#: The two I-3 samples: fenced JSON payload sizes in bytes, smallest first.
SIZE_SAMPLES = (2 * MIB, 4 * MIB)
MAX_SAMPLE_BYTES = 4 * MIB
#: Heading, prose and fence lines around the payload never exceed this.
CARRIER_ALLOWANCE_BYTES = 4096
MAX_MARKDOWN_BYTES = MAX_SAMPLE_BYTES + CARRIER_ALLOWANCE_BYTES
#: Hard caps on live mutations for one invocation. There is no delete path.
MAX_CREATES = len(SIZE_SAMPLES)
MAX_WRITES = len(SIZE_SAMPLES)

#: Only HTTP 413 is attributed to payload size; nothing else is.
SIZE_REFUSAL_STATUS = 413
RATE_LIMIT_STATUS = 429
HTTP_STATUS_PATTERN = re.compile(r"\(HTTP (\d{3})\)")
TRANSPORT_FAILURE_PREFIX = "Could not reach Fibery"

WRITE_RETURNED = "RETURNED"
WRITE_RAISED = "RAISED"
FAILURE_SIZE_REFUSAL = "SIZE_REFUSAL_HTTP_413"
FAILURE_RATE_LIMITED = "RATE_LIMITED_HTTP_429"
FAILURE_HTTP_UNATTRIBUTED = "HTTP_REJECTION_UNATTRIBUTED"
FAILURE_TRANSPORT_UNKNOWN = "TRANSPORT_OUTCOME_UNKNOWN"
FAILURE_OTHER = "OTHER"

STATE_EMPTY = "EMPTY"
STATE_ORIGINAL = "ORIGINAL"
STATE_COMPLETE = "COMPLETE"
STATE_PARTIAL = "PARTIAL_OR_MALFORMED"
STATE_UNREADABLE = "UNREADABLE"

SAMPLE_SUCCESS = "SUCCESS"
SAMPLE_NOT_SUCCESS = "NOT_SUCCESS"
SAMPLE_NOT_EXECUTED = "NOT_EXECUTED"
SUPPORTED_AT_LEAST_4_MIB = "SUPPORTED_AT_LEAST_4_MIB"

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_BLOCKED = 2


# ---------------------------------------------------------------------------
# Payloads
# ---------------------------------------------------------------------------


def size_fence(sample_bytes: int) -> str:
    """Canonical ASCII JSON of exactly `sample_bytes` bytes, at most 4 MiB."""
    if sample_bytes > MAX_SAMPLE_BYTES:
        raise ProbeRefused(f"sample {sample_bytes} exceeds the 4 MiB cap")
    envelope = {"filler": "", "probe": "tsa-p3", "sample_bytes": sample_bytes}
    pad = sample_bytes - len(canonical_json(envelope).encode("utf-8"))
    if pad < 0:
        raise ProbeRefused(f"sample {sample_bytes} is smaller than the envelope")
    envelope["filler"] = (FILLER_ALPHABET * (pad // len(FILLER_ALPHABET) + 1))[:pad]
    fence = canonical_json(envelope)
    if len(fence.encode("utf-8")) != sample_bytes:
        raise ProbeRefused(f"sample {sample_bytes} could not be sized exactly")
    return fence


def carrier(name: str, fence: str) -> str:
    """The Document Markdown, refused above the explicit total-size bound."""
    markdown = (
        f"# {name}\n\nSynthetic TSA-C01 P-3 probe content. Not an artifact of any "
        f"cycle and not a requirement.\n\n{JSON_FENCE_OPENER}\n{fence}\n"
        f"{FENCE_MARKER}\n"
    )
    if len(markdown.encode("utf-8")) > MAX_MARKDOWN_BYTES:
        raise ProbeRefused("the Document Markdown exceeds its total-size bound")
    return markdown


def content_record(content: str) -> dict[str, Any]:
    return {"bytes": len(content.encode("utf-8")), "sha256": sha256(content)}


# ---------------------------------------------------------------------------
# Classification (pure)
# ---------------------------------------------------------------------------


def classify_failure(message: str) -> str:
    """Attribute a sanitized write failure; only HTTP 413 means size."""
    match = HTTP_STATUS_PATTERN.search(message)
    if match is not None:
        status = int(match.group(1))
        if status == SIZE_REFUSAL_STATUS:
            return FAILURE_SIZE_REFUSAL
        if status == RATE_LIMIT_STATUS:
            return FAILURE_RATE_LIMITED
        return FAILURE_HTTP_UNATTRIBUTED
    if TRANSPORT_FAILURE_PREFIX in message:
        return FAILURE_TRANSPORT_UNKNOWN
    return FAILURE_OTHER


def classify_durable(content: str | None, original: str, emitted_fence: str) -> str:
    if content is None:
        return STATE_UNREADABLE
    if not content.strip():
        return STATE_EMPTY
    if content == original:
        return STATE_ORIGINAL
    if extract_json_fence(content) == emitted_fence:
        return STATE_COMPLETE
    return STATE_PARTIAL


def summarize(samples: list[dict[str, Any]]) -> dict[str, Any]:
    """Limit items A-D from what was observed; never more."""
    succeeded = [s["sample_bytes"] for s in samples if s["result"] == SAMPLE_SUCCESS]
    failed = [s for s in samples if s["result"] == SAMPLE_NOT_SUCCESS]
    refused = [s for s in failed if s.get("failure_kind") == FAILURE_SIZE_REFUSAL]
    summary: dict[str, Any] = {
        "A_largest_success_bytes": max(succeeded) if succeeded else None,
        "B_smallest_verified_size_refusal_bytes": (
            min(s["sample_bytes"] for s in refused) if refused else None
        ),
        "C_refusal_behaviour": [
            {
                "sample_bytes": s["sample_bytes"],
                "write": s["write"],
                "failure_kind": s.get("failure_kind"),
                "durable_state": s["durable_state"],
            }
            for s in failed
        ],
        "D_true_maximum": "unknown",
    }
    if len(succeeded) == len(SIZE_SAMPLES):
        summary["result"] = SUPPORTED_AT_LEAST_4_MIB
    return summary


# ---------------------------------------------------------------------------
# The guarded run
# ---------------------------------------------------------------------------


class SizeProbe:
    """The scratch Project check and P-3's two guarded mutation kinds."""

    def __init__(
        self,
        workspace: Any,
        project_id: str,
        expect_code: str,
        expect_public_id: str,
        run_id: str,
    ) -> None:
        self.workspace = workspace
        self.project_id = project_id
        self.expect_code = expect_code
        self.expect_public_id = expect_public_id
        self.run_id = run_id
        self.creates = 0
        self.writes = 0
        self.owned: dict[str, str] = {}
        self.baseline: ProjectRecord | None = None

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
        if self.baseline is not None and project_dict(project) != project_dict(
            self.baseline
        ):
            raise ProbeRefused("the scratch Project changed during the run")
        return project

    def create(self, name: str) -> str:
        if self.creates >= MAX_CREATES:
            raise ProbeRefused("the create cap is reached")
        if not name.startswith(f"{PROBE_PREFIX} ") or self.run_id not in name:
            raise ProbeRefused("a probe Document must carry the probe prefix and run")
        project = self.resolve_scratch_project()
        document_id = str(uuid.uuid4())
        if self.workspace.resolve_placement(document_id) is not None:
            raise ProbeRefused("the fresh probe id is already occupied")
        self.creates += 1
        self.owned[document_id] = name
        node = self.workspace.create_project_document(
            document_id, name, project.public_id
        )
        register_secret(node.secret)
        return document_id

    def owned_secret(self, document_id: str) -> str:
        """The content secret of a Document this run created, still in place."""
        if document_id not in self.owned:
            raise ProbeRefused(f"{document_id!r} was not created by this run")
        project = self.resolve_scratch_project()
        placement = self.workspace.resolve_placement(document_id)
        if placement is None or not placement.secret:
            raise ProbeRefused(f"{document_id!r} does not resolve with content")
        register_secret(placement.secret)
        if placement.name != self.owned[document_id]:
            raise ProbeRefused(f"{document_id!r} no longer carries the probe name")
        if not is_valid_root_placement(
            placement, self.workspace.project_type_id, project.public_id
        ):
            raise ProbeRefused(f"{document_id!r} is not a root of the scratch Project")
        return placement.secret

    def write(self, document_id: str, markdown: str) -> None:
        if self.writes >= MAX_WRITES:
            raise ProbeRefused("the write cap is reached")
        if len(markdown.encode("utf-8")) > MAX_MARKDOWN_BYTES:
            raise ProbeRefused("the Document Markdown exceeds its total-size bound")
        secret = self.owned_secret(document_id)
        self.writes += 1
        self.workspace.write_document_content(secret, markdown)

    def read_durable(self, document_id: str) -> str | None:
        """Re-discover the Document and read it; None when that fails."""
        try:
            placement = self.workspace.resolve_placement(document_id)
            if placement is None or not placement.secret:
                return None
            register_secret(placement.secret)
            return self.workspace.read_document_content(placement.secret)
        except FiberyError:
            return None


def measure_sample(probe: SizeProbe, sample: int) -> dict[str, Any]:
    name = f"{PROBE_PREFIX} SIZE {sample} {probe.run_id}"
    fence = size_fence(sample)
    markdown = carrier(name, fence)
    record: dict[str, Any] = {
        "sample_bytes": sample,
        "fence": content_record(fence),
        "emitted_markdown": content_record(markdown),
        "emitted_fingerprint": document_fingerprint(markdown),
        "request_body_bytes": len(json.dumps({"content": markdown}).encode("utf-8")),
    }
    document_id = probe.create(name)
    record["document_id"] = document_id
    record["placement_before_write"] = placement_dict(
        probe.workspace.resolve_placement(document_id)
    )
    original = probe.read_durable(document_id)
    record["original"] = None if original is None else content_record(original)
    try:
        probe.write(document_id, markdown)
        record["write"] = WRITE_RETURNED
    except FiberyError as error:
        message = sanitize(error)
        record["write"] = WRITE_RAISED
        record["write_error"] = message
        record["failure_kind"] = classify_failure(message)
    durable = probe.read_durable(document_id)
    record["placement_after_write"] = placement_dict(
        probe.workspace.resolve_placement(document_id)
    )
    record["durable_state"] = classify_durable(durable, original or "", fence)
    if durable is not None:
        read_fence = extract_json_fence(durable)
        record["read_markdown"] = content_record(durable)
        record["read_fingerprint"] = document_fingerprint(durable)
        record["fingerprint_equal"] = (
            record["read_fingerprint"] == record["emitted_fingerprint"]
        )
        record["read_fence"] = (
            None if read_fence is None else content_record(read_fence)
        )
        record["fence_exact"] = read_fence == fence
        try:
            record["fence_json_valid"] = (
                read_fence is not None
                and json.loads(read_fence)["sample_bytes"] == sample
            )
        except (ValueError, KeyError, TypeError):
            record["fence_json_valid"] = False
    is_success = (
        record["write"] == WRITE_RETURNED
        and record["durable_state"] == STATE_COMPLETE
        and record.get("fence_exact") is True
    )
    record["result"] = SAMPLE_SUCCESS if is_success else SAMPLE_NOT_SUCCESS
    return record


def run(probe: SizeProbe, evidence: dict[str, Any], mutate: bool) -> int:
    probe.baseline = probe.resolve_scratch_project()
    evidence["project"] = project_dict(probe.baseline)
    if not mutate:
        evidence["blocked"] = "read-only: --confirm-live-mutation not given"
        return EXIT_BLOCKED
    samples: list[dict[str, Any]] = evidence["samples"]
    for sample in SIZE_SAMPLES:
        if samples and samples[-1]["result"] != SAMPLE_SUCCESS:
            samples.append({"sample_bytes": sample, "result": SAMPLE_NOT_EXECUTED})
            continue
        samples.append(measure_sample(probe, sample))
    evidence["summary"] = summarize(samples)
    evidence["project_unchanged"] = project_dict(
        probe.resolve_scratch_project()
    ) == project_dict(probe.baseline)
    return EXIT_OK


def new_evidence(mode: str, run_id: str) -> dict[str, Any]:
    return {
        "mode": mode,
        "run_id": run_id,
        "started_utc": _now(),
        "adapter": "FiberyArchitectureWorkspace over FiberyClient",
        "caps": {
            "creates": MAX_CREATES,
            "writes": MAX_WRITES,
            "deletes": 0,
            "largest_fence_bytes": MAX_SAMPLE_BYTES,
            "largest_markdown_bytes": MAX_MARKDOWN_BYTES,
            "write_retries": 0,
        },
        "samples": [],
        "owned_documents": [],
    }


def finish(probe: SizeProbe, evidence: dict[str, Any]) -> None:
    evidence["owned_documents"] = [
        {"document_id": document_id, "name": name}
        for document_id, name in probe.owned.items()
    ]
    evidence["counters"] = {"creates": probe.creates, "writes": probe.writes}
    evidence["finished_utc"] = _now()


# ---------------------------------------------------------------------------
# Offline preflight
# ---------------------------------------------------------------------------


class _FakeWriteOutcome:
    """Wraps the fake so one sample's write fails with a chosen aftermath."""

    def __init__(self, fake: Any, failing_sample: int, aftermath: str) -> None:
        self._fake = fake
        self._failing_sample = failing_sample
        self._aftermath = aftermath

    def __getattr__(self, attribute: str) -> Any:
        return getattr(self._fake, attribute)

    def write_document_content(self, secret: str, markdown: str) -> None:
        if f"SIZE {self._failing_sample} " not in markdown.split("\n", 1)[0]:
            return self._fake.write_document_content(secret, markdown)
        if self._aftermath == "refused":
            raise FiberyError(
                "Fibery not replayable PUT documents request failed (HTTP 413) on "
                "attempt 1; the server's response is not reported."
            )
        if self._aftermath == "partial":
            self._fake.write_document_content(secret, markdown[: len(markdown) // 2])
        else:
            self._fake.write_document_content(secret, markdown)
        raise FiberyError(
            "Could not reach Fibery (PUT documents): the connection timed out; "
            "the request was attempted once."
        )


def _expect_refusal(action: Any, what: str) -> None:
    try:
        action()
    except ProbeRefused:
        return
    raise AssertionError(f"not refused: {what}")


def _preflight_run(workspace: Any, project: tuple[str, str, str]) -> dict[str, Any]:
    probe = SizeProbe(workspace, *project, _run_id())
    evidence = new_evidence("preflight", probe.run_id)
    assert run(probe, evidence, mutate=True) == EXIT_OK
    finish(probe, evidence)
    assert probe.creates <= MAX_CREATES and probe.writes <= MAX_WRITES
    assert not [m for m in workspace.mutations if m.startswith("delete")]
    _expect_refusal(lambda: probe.write("not-owned", "x"), "a non-probe write")
    probe.creates, probe.writes = MAX_CREATES, MAX_WRITES
    _expect_refusal(lambda: probe.create(f"{PROBE_PREFIX} x {probe.run_id}"), "cap")
    owned = next(iter(probe.owned))
    _expect_refusal(lambda: probe.write(owned, "x"), "the write cap")
    return evidence


def preflight() -> int:
    """Fake-backed flows and every guard refusal; makes no network call."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
    from architecture_fake import PROJECT_TYPE_ID, FakeArchitectureWorkspace

    for sample in SIZE_SAMPLES:
        fence = size_fence(sample)
        assert len(fence.encode("utf-8")) == sample == len(fence)
        assert json.loads(fence)["sample_bytes"] == sample
        assert extract_json_fence(carrier("x", fence)) == fence
    _expect_refusal(lambda: size_fence(MAX_SAMPLE_BYTES + 1), "a sample over 4 MiB")
    _expect_refusal(lambda: carrier("x" * 5000, size_fence(MAX_SAMPLE_BYTES)), "md")
    register_secret("preflight-secret-value")
    assert "preflight-secret-value" not in scrub("token=preflight-secret-value")
    assert classify_failure("x (HTTP 413) y") == FAILURE_SIZE_REFUSAL
    assert classify_failure("x (HTTP 400) y") == FAILURE_HTTP_UNATTRIBUTED
    assert classify_failure("x (HTTP 429) y") == FAILURE_RATE_LIMITED
    assert (
        classify_failure("Could not reach Fibery (PUT x)") == FAILURE_TRANSPORT_UNKNOWN
    )

    scratch = ProjectRecord(
        "scratch-entity", "TSA P-3 SCRATCH — DO NOT USE", "TSAP3", "Planned", "99"
    )
    identity = ("scratch-entity", "TSAP3", "99")

    def fake() -> Any:
        return FakeArchitectureWorkspace([scratch], PROJECT_TYPE_ID)

    scenarios = {
        "all succeed": fake(),
        "4 MiB refused (413)": _FakeWriteOutcome(fake(), 4 * MIB, "refused"),
        "4 MiB partial, then timeout": _FakeWriteOutcome(fake(), 4 * MIB, "partial"),
        "4 MiB applied, then timeout": _FakeWriteOutcome(fake(), 4 * MIB, "applied"),
        "2 MiB refused (413)": _FakeWriteOutcome(fake(), 2 * MIB, "refused"),
    }
    expected = {
        "all succeed": [("SUCCESS", "COMPLETE"), ("SUCCESS", "COMPLETE")],
        "4 MiB refused (413)": [("SUCCESS", "COMPLETE"), ("NOT_SUCCESS", "EMPTY")],
        "4 MiB partial, then timeout": [
            ("SUCCESS", "COMPLETE"),
            ("NOT_SUCCESS", "PARTIAL_OR_MALFORMED"),
        ],
        "4 MiB applied, then timeout": [
            ("SUCCESS", "COMPLETE"),
            ("NOT_SUCCESS", "COMPLETE"),
        ],
        "2 MiB refused (413)": [("NOT_SUCCESS", "EMPTY"), ("NOT_EXECUTED", None)],
    }
    print("PREFLIGHT OK (in-memory fake; no network)")
    for label, workspace in scenarios.items():
        evidence = _preflight_run(workspace, identity)
        observed = [(s["result"], s.get("durable_state")) for s in evidence["samples"]]
        assert observed == expected[label], (label, observed)
        print(f"  {label}: {observed}; summary {evidence['summary']}")

    refusals = [
        (
            ProjectRecord("p", "Real Project", "REAL", "Planned", "1"),
            ("p", "REAL", "1"),
        ),
        (scratch, ("other-entity", "TSAP3", "99")),
        (scratch, ("scratch-entity", "XX", "99")),
        (scratch, ("scratch-entity", "TSAP3", "98")),
    ]
    for project, wrong in refusals:
        workspace = FakeArchitectureWorkspace([project], PROJECT_TYPE_ID)
        probe = SizeProbe(workspace, *wrong, _run_id())
        _expect_refusal(
            lambda probe=probe: run(probe, new_evidence("preflight", "r"), True),
            f"Project {wrong}",
        )
        assert not workspace.mutations
    print(
        f"  guards: wrong/non-scratch Project refused; caps creates {MAX_CREATES}, "
        f"writes {MAX_WRITES}, deletes 0; fence <= {MAX_SAMPLE_BYTES} bytes, "
        f"Markdown <= {MAX_MARKDOWN_BYTES} bytes"
    )
    return EXIT_OK


# ---------------------------------------------------------------------------
# Live
# ---------------------------------------------------------------------------


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
    probe = SizeProbe(
        workspace,
        arguments.project_id,
        arguments.expect_code,
        arguments.expect_public_id,
        _run_id(),
    )
    evidence = new_evidence("live", probe.run_id)
    evidence["workspace_identity"] = client.workspace_identity
    evidence["timeout_seconds"] = settings.timeout_seconds
    evidence["confirm_live_mutation"] = arguments.confirm_live_mutation
    status = EXIT_FAILED
    try:
        status = run(probe, evidence, arguments.confirm_live_mutation)
    except ProbeRefused as refused:
        evidence["blocked"] = f"refused: {scrub(str(refused))}"
        status = EXIT_BLOCKED
    except FiberyError as error:
        evidence["blocked"] = f"stopped: {sanitize(error)}"
    finally:
        finish(probe, evidence)
        payload = scrub(json.dumps(evidence, indent=2, sort_keys=True))
        if arguments.evidence_out:
            Path(arguments.evidence_out).write_text(payload + "\n", encoding="utf-8")
            print(f"Evidence written to {arguments.evidence_out}")
        else:
            print(payload)
    print(f"status {status}; counters {evidence['counters']}")
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
    parser.add_argument("--evidence-out")
    arguments = parser.parse_args(argv)
    if arguments.live and not (
        arguments.project_id and arguments.expect_code and arguments.expect_public_id
    ):
        parser.error("--live needs --project-id, --expect-code and --expect-public-id")
    if arguments.confirm_live_mutation and not arguments.live:
        parser.error("--confirm-live-mutation needs --live")
    return arguments


def main(argv: list[str] | None = None) -> int:
    arguments = parse_arguments(argv)
    if arguments.live:
        return live(arguments)
    return preflight()


if __name__ == "__main__":
    raise SystemExit(main())
