#!/usr/bin/env python
"""P-3D: the bounded I-3 follow-up to P-3's 4 MiB HTTP 500.

P-3 observed a 2 MiB fenced JSON payload succeed and a 4 MiB write fail with
HTTP 500, leaving its fresh Document empty. A 500 does not state its cause.
This diagnostic attempts exactly two further samples, each in its own fresh
probe-owned Document of the scratch Project, with one write attempt each:

1. 3 MiB; read back and classify;
2. 4 MiB, only if 3 MiB succeeded with a validated durable read-back.

It then stops. Nothing above 4 MiB is ever attempted.

Each write is classified as SUCCESS (validated read-back), a confirmed HTTP 413
size refusal, an unattributed HTTP 500, a timeout/unknown outcome, or another
server refusal; a write that returned without a validated read-back is kept
apart from all of them. The durable aftermath is always read back, never
inferred from the exception, and each sample is recorded incrementally, so a
failing lookup after a failed write still leaves its record.

The guarded Project/ownership checks, the caps (2 creates, 2 writes, no
delete path), payload generation and the total-size bound are P-3's,
imported unchanged; so are P-2's redaction and record helpers.

    # Offline preflight (default): failure injection and every guard refusal.
    uv run --frozen python scripts/tsa_p3d_fibery_size_diagnostic.py

    # Live (only with separate authorization).
    uv run --frozen --env-file <env> python \\
        scripts/tsa_p3d_fibery_size_diagnostic.py --live --project-id <id> \\
        --expect-code <code> --expect-public-id <id> \\
        [--confirm-live-mutation] [--evidence-out <file>]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tsa_p2_fibery_probe import (
    ProbeRefused,
    extract_json_fence,
    placement_dict,
    project_dict,
    register_secret,
    sanitize,
    scrub,
)
from tsa_p3_fibery_size_probe import (
    MAX_CREATES,
    MAX_MARKDOWN_BYTES,
    MAX_SAMPLE_BYTES,
    MAX_WRITES,
    MIB,
    PROBE_PREFIX,
    STATE_COMPLETE,
    SizeProbe,
    carrier,
    classify_durable,
    content_record,
    size_fence,
)

from sdlc.config import ConfigurationError, load_fibery_settings
from sdlc.fibery_client import FiberyClient
from sdlc.fibery_http import FiberyArchitectureWorkspace
from sdlc.fibery_workspace import FiberyError
from sdlc.normative_tree import document_fingerprint

#: The two samples, in the order attempted. Nothing larger is ever attempted.
SIZE_SAMPLES = (3 * MIB, 4 * MIB)
NAME_TAG = "DIAG"

SIZE_REFUSAL_STATUS = 413
UNATTRIBUTED_SERVER_ERROR_STATUS = 500
HTTP_STATUS_PATTERN = re.compile(r"\(HTTP (\d{3})\)")

OUTCOME_SUCCESS = "SUCCESS"
OUTCOME_SIZE_REFUSAL = "CONFIRMED_SIZE_REFUSAL_HTTP_413"
OUTCOME_HTTP_500 = "HTTP_500_UNATTRIBUTED"
OUTCOME_UNKNOWN = "TIMEOUT_OR_UNKNOWN_OUTCOME"
OUTCOME_OTHER_REFUSAL = "OTHER_SERVER_REFUSAL"
OUTCOME_RETURNED_UNVALIDATED = "RETURNED_WITHOUT_VALIDATED_READ_BACK"
OUTCOME_NOT_EXECUTED = "NOT_EXECUTED"

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_BLOCKED = 2


def classify_write_failure(message: str) -> tuple[str, int | None]:
    """Attribute a sanitized write failure; only HTTP 413 means size."""
    match = HTTP_STATUS_PATTERN.search(message)
    if match is None:
        # No server status: a timeout, a connection failure or an unreadable
        # response. The write may or may not have been applied.
        return OUTCOME_UNKNOWN, None
    status = int(match.group(1))
    if status == SIZE_REFUSAL_STATUS:
        return OUTCOME_SIZE_REFUSAL, status
    if status == UNATTRIBUTED_SERVER_ERROR_STATUS:
        return OUTCOME_HTTP_500, status
    return OUTCOME_OTHER_REFUSAL, status


def lookup(probe: SizeProbe, document_id: str) -> dict[str, Any]:
    """The Document's placement, or the sanitized failure to look it up."""
    try:
        return placement_dict(probe.workspace.resolve_placement(document_id))
    except FiberyError as error:
        return {"lookup_error": sanitize(error)}


def record_read_back(record: dict[str, Any], durable: str, fence: str) -> None:
    read_fence = extract_json_fence(durable)
    record["read_markdown"] = content_record(durable)
    record["read_fingerprint"] = document_fingerprint(durable)
    record["fingerprint_equal"] = (
        record["read_fingerprint"] == (record["emitted_fingerprint"])
    )
    record["read_fence"] = None if read_fence is None else content_record(read_fence)
    record["fence_exact"] = read_fence == fence
    try:
        record["fence_json_valid"] = (
            read_fence is not None
            and json.loads(read_fence)["sample_bytes"] == record["sample_bytes"]
        )
    except (ValueError, KeyError, TypeError):
        record["fence_json_valid"] = False


def measure_sample(probe: SizeProbe, sample: int, record: dict[str, Any]) -> None:
    """Fill `record` step by step, so a later failure keeps what came before."""
    name = f"{PROBE_PREFIX} {NAME_TAG} SIZE {sample} {probe.run_id}"
    fence = size_fence(sample)
    markdown = carrier(name, fence)
    record.update(
        {
            "name": name,
            "fence": content_record(fence),
            "emitted_markdown": content_record(markdown),
            "emitted_fingerprint": document_fingerprint(markdown),
            "request_body_bytes_estimate": len(
                json.dumps({"content": markdown}).encode("utf-8")
            ),
        }
    )
    document_id = probe.create(name)
    record["document_id"] = document_id
    record["placement_before_write"] = lookup(probe, document_id)
    original = probe.read_durable(document_id)
    record["original"] = None if original is None else content_record(original)
    try:
        probe.write(document_id, markdown)
        record["write"] = "RETURNED"
    except FiberyError as error:
        message = sanitize(error)
        record["write"] = "RAISED"
        record["write_error"] = message
        record["outcome"], record["http_status"] = classify_write_failure(message)
    durable = probe.read_durable(document_id)
    record["placement_after_write"] = lookup(probe, document_id)
    record["durable_state"] = classify_durable(durable, original or "", fence)
    record["durable_equals_original"] = durable is not None and durable == (
        original or ""
    )
    if durable is not None:
        record_read_back(record, durable, fence)
    if record["write"] == "RETURNED":
        is_validated = (
            record["durable_state"] == STATE_COMPLETE
            and record.get("fence_exact") is True
            and record.get("fence_json_valid") is True
        )
        record["outcome"] = (
            OUTCOME_SUCCESS if is_validated else OUTCOME_RETURNED_UNVALIDATED
        )


def summarize(samples: list[dict[str, Any]]) -> dict[str, Any]:
    """Only what was observed in this run; the gate is decided elsewhere."""
    succeeded = [s["sample_bytes"] for s in samples if s["outcome"] == OUTCOME_SUCCESS]
    attempted = [s for s in samples if s["outcome"] != OUTCOME_NOT_EXECUTED]
    failures = [s for s in attempted if s["outcome"] != OUTCOME_SUCCESS]
    refusals = [s for s in failures if s["outcome"] == OUTCOME_SIZE_REFUSAL]
    return {
        "largest_observed_success_bytes": max(succeeded) if succeeded else None,
        "observed_failures": [
            {
                "sample_bytes": s["sample_bytes"],
                "outcome": s["outcome"],
                "http_status": s.get("http_status"),
                "durable_state": s.get("durable_state"),
            }
            for s in failures
        ],
        "smallest_confirmed_size_refusal_bytes": (
            min(s["sample_bytes"] for s in refusals) if refusals else None
        ),
        "partial_or_malformed_observed": any(
            s.get("durable_state") == "PARTIAL_OR_MALFORMED" for s in failures
        ),
    }


def run(probe: SizeProbe, evidence: dict[str, Any], mutate: bool) -> int:
    probe.baseline = probe.resolve_scratch_project()
    evidence["project"] = project_dict(probe.baseline)
    if not mutate:
        evidence["blocked"] = "read-only: --confirm-live-mutation not given"
        return EXIT_BLOCKED
    samples: list[dict[str, Any]] = evidence["samples"]
    for sample in SIZE_SAMPLES:
        if samples and samples[-1]["outcome"] != OUTCOME_SUCCESS:
            samples.append({"sample_bytes": sample, "outcome": OUTCOME_NOT_EXECUTED})
            continue
        record: dict[str, Any] = {"sample_bytes": sample, "outcome": None}
        samples.append(record)
        measure_sample(probe, sample, record)
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
            "samples_bytes": list(SIZE_SAMPLES),
            "largest_fence_bytes": MAX_SAMPLE_BYTES,
            "largest_markdown_bytes": MAX_MARKDOWN_BYTES,
            "write_retries": 0,
        },
        "samples": [],
    }


def finish(probe: SizeProbe, evidence: dict[str, Any]) -> None:
    evidence["owned_documents"] = [
        {"document_id": document_id, "name": name}
        for document_id, name in probe.owned.items()
    ]
    evidence["counters"] = {"creates": probe.creates, "writes": probe.writes}
    evidence["finished_utc"] = _now()


# ---------------------------------------------------------------------------
# Offline preflight: failure injection over the in-memory fake
# ---------------------------------------------------------------------------


def _http_failure(status: int) -> FiberyError:
    return FiberyError(
        f"Fibery not replayable PUT documents request failed (HTTP {status}) on "
        "attempt 1; the server's response is not reported."
    )


TIMEOUT_FAILURE = (
    "Could not reach Fibery (PUT documents): the connection timed out; the "
    "request was attempted once."
)


class _InjectedWrite:
    """The fake, except one sample's write ends with a chosen aftermath."""

    def __init__(
        self,
        fake: Any,
        sample: int,
        applied: str,
        error: FiberyError | None,
        reads_fail_after: bool = False,
    ) -> None:
        self._fake = fake
        self._sample = sample
        self._applied = applied
        self._error = error
        self._reads_fail_after = reads_fail_after
        self._reads_failing = False

    def __getattr__(self, attribute: str) -> Any:
        return getattr(self._fake, attribute)

    def resolve_placement(self, document_id: str) -> Any:
        if self._reads_failing:
            raise timeout_failure()
        return self._fake.resolve_placement(document_id)

    def read_document_content(self, secret: str) -> str:
        if self._reads_failing:
            raise timeout_failure()
        return self._fake.read_document_content(secret)

    def write_document_content(self, secret: str, markdown: str) -> None:
        if f"SIZE {self._sample} " not in markdown.split("\n", 1)[0]:
            return self._fake.write_document_content(secret, markdown)
        if self._applied == "partial":
            self._fake.write_document_content(secret, markdown[: len(markdown) // 2])
        elif self._applied == "full":
            self._fake.write_document_content(secret, markdown)
        self._reads_failing = self._reads_fail_after
        if self._error is not None:
            raise self._error


def timeout_failure() -> FiberyError:
    return FiberyError(TIMEOUT_FAILURE)


def _expect_refusal(action: Any, what: str) -> None:
    try:
        action()
    except ProbeRefused:
        return
    raise AssertionError(f"not refused: {what}")


def preflight() -> int:
    """Failure injection and guard refusals; makes no network call."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
    from architecture_fake import PROJECT_TYPE_ID, FakeArchitectureWorkspace
    from sdlc.fibery_workspace import ProjectRecord

    assert classify_write_failure("x (HTTP 413) y") == (OUTCOME_SIZE_REFUSAL, 413)
    assert classify_write_failure("x (HTTP 500) y") == (OUTCOME_HTTP_500, 500)
    assert classify_write_failure("x (HTTP 503) y") == (OUTCOME_OTHER_REFUSAL, 503)
    assert classify_write_failure("x (HTTP 429) y") == (OUTCOME_OTHER_REFUSAL, 429)
    assert classify_write_failure(TIMEOUT_FAILURE) == (OUTCOME_UNKNOWN, None)
    for sample in SIZE_SAMPLES:
        assert len(size_fence(sample).encode("utf-8")) == sample
    _expect_refusal(lambda: size_fence(MAX_SAMPLE_BYTES + 1), "a sample over 4 MiB")
    register_secret("preflight-secret-value")
    assert "preflight-secret-value" not in scrub("x preflight-secret-value")

    scratch = ProjectRecord(
        "scratch-entity", "TSA P-3D SCRATCH — DO NOT USE", "TSAP3D", "Planned", "99"
    )
    identity = ("scratch-entity", "TSAP3D", "99")
    three, four = SIZE_SAMPLES

    def fake() -> Any:
        return FakeArchitectureWorkspace([scratch], PROJECT_TYPE_ID)

    scenarios = [
        ("all succeed", fake(), ["SUCCESS:COMPLETE", "SUCCESS:COMPLETE"]),
        (
            "4 MiB 413, nothing applied",
            _InjectedWrite(fake(), four, "none", _http_failure(413)),
            ["SUCCESS:COMPLETE", f"{OUTCOME_SIZE_REFUSAL}:EMPTY"],
        ),
        (
            "4 MiB 500, nothing applied",
            _InjectedWrite(fake(), four, "none", _http_failure(500)),
            ["SUCCESS:COMPLETE", f"{OUTCOME_HTTP_500}:EMPTY"],
        ),
        (
            "4 MiB 503",
            _InjectedWrite(fake(), four, "none", _http_failure(503)),
            ["SUCCESS:COMPLETE", f"{OUTCOME_OTHER_REFUSAL}:EMPTY"],
        ),
        (
            "4 MiB timeout, partially applied",
            _InjectedWrite(fake(), four, "partial", timeout_failure()),
            ["SUCCESS:COMPLETE", f"{OUTCOME_UNKNOWN}:PARTIAL_OR_MALFORMED"],
        ),
        (
            "4 MiB timeout, fully applied",
            _InjectedWrite(fake(), four, "full", timeout_failure()),
            ["SUCCESS:COMPLETE", f"{OUTCOME_UNKNOWN}:COMPLETE"],
        ),
        (
            "4 MiB 500, then reads fail",
            _InjectedWrite(fake(), four, "none", _http_failure(500), True),
            ["SUCCESS:COMPLETE", f"{OUTCOME_HTTP_500}:UNREADABLE"],
        ),
        (
            "4 MiB returned, nothing stored",
            _InjectedWrite(fake(), four, "none", None),
            ["SUCCESS:COMPLETE", f"{OUTCOME_RETURNED_UNVALIDATED}:EMPTY"],
        ),
        (
            "3 MiB 500 stops the run",
            _InjectedWrite(fake(), three, "none", _http_failure(500)),
            [f"{OUTCOME_HTTP_500}:EMPTY", f"{OUTCOME_NOT_EXECUTED}:None"],
        ),
    ]
    print("PREFLIGHT OK (in-memory fake; no network)")
    for label, workspace, expected in scenarios:
        probe = SizeProbe(workspace, *identity, _run_id())
        evidence = new_evidence("preflight", probe.run_id)
        assert run(probe, evidence, mutate=True) == EXIT_OK
        finish(probe, evidence)
        observed = [
            f"{s['outcome']}:{s.get('durable_state')}" for s in evidence["samples"]
        ]
        assert observed == expected, (label, observed)
        assert probe.creates <= MAX_CREATES and probe.writes <= MAX_WRITES
        assert not [m for m in workspace.mutations if m.startswith("delete")]
        print(f"  {label}: {observed}")

    probe = SizeProbe(fake(), *identity, _run_id())
    run(probe, new_evidence("preflight", probe.run_id), mutate=True)
    _expect_refusal(lambda: probe.write("not-owned", "x"), "a non-probe write")
    _expect_refusal(lambda: probe.create(f"{PROBE_PREFIX} x {probe.run_id}"), "cap")
    owned = next(iter(probe.owned))
    _expect_refusal(lambda: probe.write(owned, "x"), "the write cap")
    for project, wrong in [
        (
            ProjectRecord("p", "Real Project", "REAL", "Planned", "1"),
            ("p", "REAL", "1"),
        ),
        (scratch, ("other-entity", "TSAP3D", "99")),
        (scratch, ("scratch-entity", "XX", "99")),
        (scratch, ("scratch-entity", "TSAP3D", "98")),
    ]:
        workspace = FakeArchitectureWorkspace([project], PROJECT_TYPE_ID)
        probe = SizeProbe(workspace, *wrong, _run_id())
        _expect_refusal(
            lambda probe=probe: run(probe, new_evidence("preflight", "r"), True),
            f"Project {wrong}",
        )
        assert not workspace.mutations
    print(
        f"  guards: wrong/non-scratch Project refused; non-probe write refused; "
        f"caps creates {MAX_CREATES}, writes {MAX_WRITES}, deletes 0; samples "
        f"{list(SIZE_SAMPLES)}; Markdown <= {MAX_MARKDOWN_BYTES} bytes"
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
