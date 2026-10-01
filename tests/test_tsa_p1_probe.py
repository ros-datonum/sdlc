"""Narrow tests for the P-1 probe's safety rails and output classification.

These do NOT constitute P-1. A mocked run is not live evidence: I03 requires an
actual execution against a live scratch Project. What is tested here is only
that the probe refuses to mutate without explicit confirmation, that it never
leaks a secret, and that it classifies a duplicate-id outcome correctly — the
parts that must be right *before* the live run, not instead of it.
"""

from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import tsa_p1_probe as probe

from architecture_fake import FakeArchitectureWorkspace, project
from sdlc.fibery_workspace import DocumentPlacement, FiberyError

SECRET = "super-secret-document-key"
ROOT_ID = "0576efe5-1d70-515e-b587-0a39f85ce6f2"
CHILD_ID = "3800ce1f-893d-5324-8539-d2e2e842ad55"


# ==========================================================================
# Safety rails
# ==========================================================================


def test_project_id_is_required():
    with pytest.raises(SystemExit):
        probe.parse_arguments([])


def test_mutation_confirmation_defaults_to_off():
    arguments = probe.parse_arguments(["--project-id", "p-1"])
    assert arguments.confirm_live_mutation is False


def test_mutation_confirmation_is_explicit():
    arguments = probe.parse_arguments(
        ["--project-id", "p-1", "--confirm-live-mutation"]
    )
    assert arguments.confirm_live_mutation is True


def test_the_probe_hard_codes_no_project_and_no_credentials():
    source = Path(probe.__file__).read_text(encoding="utf-8")
    assert "FIBERY_TOKEN" not in source
    assert "fibery.io" not in source
    # The scratch Project arrives as an argument, never as a literal.
    assert "--project-id" in source
    assert "default=None" not in source.replace("default=DEFAULT_PROBE_PREFIX", "")


def test_the_probe_resolves_the_project_by_exact_entity_id():
    """Never by fuzzy name matching."""
    source = Path(probe.__file__).read_text(encoding="utf-8")
    assert "read_project(project_id)" in source
    assert "find_project_by_name" not in source
    assert "find_projects_by_name" not in source


def test_a_missing_scratch_project_is_a_block_not_a_mutation():
    workspace = FakeArchitectureWorkspace()
    assert probe.resolve_scratch_project(workspace, "does-not-exist") is None
    assert workspace.mutations == []


def test_the_probe_creates_no_lifecycle_module():
    """I03 adds a probe and evidence, never a TSA lifecycle module."""
    source = Path(probe.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "tsa_cycle",
        "tsa_admission",
        "tsa_architecture",
        "tsa_architect",
        "tsa_reviewer",
        "tsa_recovery",
        "tsa_decision",
    ):
        assert forbidden not in source


# ==========================================================================
# No secret may reach any output
# ==========================================================================


def test_sanitize_removes_a_secret_from_an_error():
    error = FiberyError(f"request to /api/documents/{SECRET} failed")
    message = probe.sanitize(error, (SECRET,))
    assert SECRET not in message
    assert probe.REDACTED in message


def test_sanitize_keeps_the_exception_type():
    assert "FiberyError" in probe.sanitize(FiberyError("x"), (SECRET,))


def test_sanitize_tolerates_an_empty_secret():
    assert "boom" in probe.sanitize(FiberyError("boom"), ("",))


def test_placement_evidence_reduces_the_secret_to_a_flag():
    placement = DocumentPlacement(
        document_id=ROOT_ID,
        secret=SECRET,
        name="root",
        container_entity_type="t",
        container_entity_id="7",
        parent_document_id=None,
    )

    recorded = probe.placement_dict(placement)

    assert SECRET not in repr(recorded)
    assert recorded["secret_present"] is True


def test_placement_evidence_handles_absence():
    assert probe.placement_dict(None) == {"present": False}


# ==========================================================================
# Duplicate-id classification
# ==========================================================================


def duplicate_evidence(workspace) -> probe.Evidence:
    """Run the duplicate probe and hand back the whole evidence, failures included."""
    evidence = probe.Evidence(started_at="now")
    probe.probe_duplicate_id(
        workspace,
        evidence,
        project(public_id="7"),
        ROOT_ID,
        "ROOT",
        workspace.documents[ROOT_ID].secret,
    )
    return evidence


def duplicate_outcome(workspace) -> dict:
    return duplicate_evidence(workspace).duplicate


#: Exactly how `FiberyClient` phrases a JSON-RPC error, and what live P-1 saw.
LIVE_REJECTION = (
    "Views method 'create-views' failed: Fibery returned a JSON-RPC error "
    "(code -32000); the server's response is not reported."
)


def rejecting_fake() -> FakeArchitectureWorkspace:
    """A fake whose duplicate create refuses the way live Fibery did.

    The fake's own `already exists` message is deliberately NOT used here: it
    does not claim a server answered, and the probe is right to treat such a
    message as an unknown outcome. A test for the live-confirmed REJECTED path
    must present the live error shape.
    """
    workspace = seeded_fake()

    def refusing(document_id, name, project_public_id):
        raise FiberyError(LIVE_REJECTION)

    workspace.create_project_document = refusing  # type: ignore[method-assign]
    return workspace


def seeded_fake() -> FakeArchitectureWorkspace:
    workspace = FakeArchitectureWorkspace(projects=[project(public_id="7")])
    workspace.create_project_document(ROOT_ID, "ROOT", "7")
    workspace.write_document_content(workspace.documents[ROOT_ID].secret, "original")
    return workspace


# --- A: the live-confirmed behaviour. Refused, nothing changed. ------------


def test_a_confirmed_rejection_with_unchanged_state_is_rejected():
    evidence = duplicate_evidence(rejecting_fake())

    assert evidence.duplicate["create_outcome"] == probe.OUTCOME_CONFIRMED_REJECTION
    assert evidence.duplicate["classification"] == probe.DUPLICATE_REJECTED
    assert evidence.duplicate["raised"] is True
    assert evidence.duplicate["placement_unchanged"] is True
    assert evidence.duplicate["name_unchanged"] is True
    assert evidence.duplicate["content_unchanged"] is True
    # The expected outcome, so nothing fails.
    assert evidence.failures == []


# --- B: accepted silently, nothing changed. Unexpected, so it must fail. ---


def test_a_silently_accepting_create_is_idempotent_and_fails_the_run():
    workspace = seeded_fake()
    workspace.create_project_document = (  # type: ignore[method-assign]
        lambda document_id, name, project_public_id: None
    )

    evidence = duplicate_evidence(workspace)

    assert evidence.duplicate["classification"] == probe.DUPLICATE_IDEMPOTENT
    assert probe.FAILURE_DUPLICATE_UNEXPECTED in evidence.checks
    assert evidence.failures


# --- C/G: raised, but the placement moved. Never REJECTED. -----------------


def test_a_raising_create_that_moves_the_placement_is_not_rejected():
    workspace = seeded_fake()

    def reparenting(document_id, name, project_public_id):
        workspace.documents[document_id].parent_document_id = "some-other-doc"
        raise FiberyError(LIVE_REJECTION)

    workspace.create_project_document = reparenting  # type: ignore[method-assign]

    evidence = duplicate_evidence(workspace)

    assert evidence.duplicate["classification"] != probe.DUPLICATE_REJECTED
    assert evidence.duplicate["classification"] == probe.DUPLICATE_MUTATED_EXISTING
    assert evidence.duplicate["placement_unchanged"] is False
    assert probe.FAILURE_DUPLICATE_STATE_CHANGED in evidence.checks
    assert evidence.failures


def test_an_exception_alone_is_never_enough_for_rejected():
    """Rejection means refused AND provably untouched."""
    workspace = seeded_fake()

    def reparenting(document_id, name, project_public_id):
        workspace.documents[document_id].container_entity_id = "999"
        raise FiberyError(LIVE_REJECTION)

    workspace.create_project_document = reparenting  # type: ignore[method-assign]

    evidence = duplicate_evidence(workspace)

    assert evidence.duplicate["raised"] is True
    assert evidence.duplicate["classification"] == probe.DUPLICATE_MUTATED_EXISTING


# --- D: accepted and renamed. ---------------------------------------------


def test_a_renaming_create_is_mutated_existing_and_fails_the_run():
    workspace = seeded_fake()

    def renaming(document_id, name, project_public_id):
        workspace.documents[document_id].name = name

    workspace.create_project_document = renaming  # type: ignore[method-assign]

    evidence = duplicate_evidence(workspace)

    assert evidence.duplicate["classification"] == probe.DUPLICATE_MUTATED_EXISTING
    assert evidence.duplicate["name_after"] == "ROOT DUPLICATE ATTEMPT"
    assert evidence.duplicate["name_unchanged"] is False
    assert evidence.failures


# --- E: content clobbered. ------------------------------------------------


def test_lost_content_is_mutated_existing_and_fails_the_run():
    workspace = seeded_fake()
    workspace.create_project_document = (  # type: ignore[method-assign]
        lambda document_id, name, project_public_id: workspace.content.__setitem__(
            workspace.documents[document_id].secret, "clobbered"
        )
    )

    evidence = duplicate_evidence(workspace)

    assert evidence.duplicate["classification"] == probe.DUPLICATE_MUTATED_EXISTING
    assert evidence.duplicate["content_unchanged"] is False
    assert evidence.failures


# --- F: the state cannot be established at all. ---------------------------


def test_an_unreadable_read_back_is_an_unknown_outcome_and_fails_the_run():
    """An unprovable state is unknown, not rejected and not mutated."""
    workspace = seeded_fake()

    def refusing(document_id, name, project_public_id):
        raise FiberyError(LIVE_REJECTION)

    workspace.create_project_document = refusing  # type: ignore[method-assign]
    workspace.failures["read_document_content"] = FiberyError("content unreadable")

    evidence = duplicate_evidence(workspace)

    assert evidence.duplicate["classification"] == probe.DUPLICATE_OTHER
    assert probe.FAILURE_DUPLICATE_UNKNOWN in evidence.checks
    assert evidence.failures


def test_a_missing_placement_after_the_attempt_is_an_unknown_outcome():
    workspace = seeded_fake()

    def vanishing(document_id, name, project_public_id):
        del workspace.documents[document_id]
        raise FiberyError(LIVE_REJECTION)

    workspace.create_project_document = vanishing  # type: ignore[method-assign]

    evidence = duplicate_evidence(workspace)

    assert evidence.duplicate["classification"] == probe.DUPLICATE_OTHER
    assert evidence.failures


# --- the snapshot itself --------------------------------------------------


def test_the_snapshot_never_carries_the_raw_secret():
    workspace = seeded_fake()
    secret = workspace.documents[ROOT_ID].secret

    state = probe.snapshot_durable_state(workspace, ROOT_ID, secret)

    assert secret not in repr(state)
    assert state["placement"]["secret_present"] is True
    assert state["readable"] is True


def test_the_snapshot_compares_content_by_hash_not_by_text():
    workspace = seeded_fake()
    state = probe.snapshot_durable_state(
        workspace, ROOT_ID, workspace.documents[ROOT_ID].secret
    )

    assert state["content_sha256"] == probe.sha256("original")


def test_the_historical_live_observation_still_classifies_rejected():
    """The supplied first-run result, replayed through the corrected classifier."""
    before = {
        "placement": {
            "present": True,
            "document_id": "8dee7dd2-979c-473d-8ebb-7503053d2485",
            "name": "TSA-P1-PROBE ROOT 20261001T150152Z",
            "container_entity_type": "2d4bba0c-5eb7-4dc2-b406-0f10404ef31f",
            "container_entity_id": "27",
            "parent_document_id": None,
            "secret_present": True,
        },
        "name": "TSA-P1-PROBE ROOT 20261001T150152Z",
        "readable": True,
        "content_sha256": (
            "8c94cd897bf25731d77f0307adae87045297bb8270253ab6838028b2cf9e82b6"
        ),
    }

    assert probe.classify_create_outcome(FiberyError(LIVE_REJECTION)) == (
        probe.OUTCOME_CONFIRMED_REJECTION
    )
    assert (
        probe.classify_duplicate(
            probe.OUTCOME_CONFIRMED_REJECTION, before, dict(before)
        )
        == probe.DUPLICATE_REJECTED
    )


def test_the_duplicate_error_is_sanitized():
    workspace = seeded_fake()

    def leaking(document_id, name, project_public_id):
        raise FiberyError(f"secret {workspace.documents[ROOT_ID].secret} leaked")

    workspace.create_project_document = leaking  # type: ignore[method-assign]

    outcome = duplicate_outcome(workspace)

    assert workspace.documents[ROOT_ID].secret not in outcome["error"]
    assert probe.REDACTED in outcome["error"]


# ==========================================================================
# Evidence bookkeeping and the frozen payload
# ==========================================================================


def test_the_probe_payload_is_the_frozen_shape():
    assert probe.PROBE_PAYLOAD.startswith("# TSA P-1 Probe\n")
    assert "Probe payload." in probe.PROBE_PAYLOAD
    assert '```json\n{"probe":"tsa-p1","version":1}\n```' in probe.PROBE_PAYLOAD


def test_failed_checks_are_collected_with_detail():
    evidence = probe.Evidence(started_at="now")

    assert evidence.record("ok", True) is True
    assert evidence.record("bad", False, "because") is False

    assert evidence.checks == {"ok": True, "bad": False}
    assert evidence.failures == ["bad: because"]


def test_external_drift_is_recorded_as_not_executed():
    """No update-views or delete-views wrapper exists, so the row is not forced."""
    evidence = probe.Evidence(started_at="now")

    probe.record_drift_not_executed(evidence)

    assert evidence.drift["result"] == probe.DRIFT_NOT_EXECUTED
    assert evidence.drift["method"] is None
    assert "create-views" in evidence.drift["reason"]


# ==========================================================================
# The content criterion: byte-exact INSIDE the fence, per frozen §2.3
# ==========================================================================


class ReserializingWorkspace(FakeArchitectureWorkspace):
    """A fake whose read-back re-serializes Markdown, as live Fibery does.

    Models exactly the behaviours API constraint 11 records as VERIFIED live:
    the trailing newline is dropped and a `-` bullet comes back as `*`, while
    fenced content is returned verbatim.
    """

    def read_document_content(self, secret: str) -> str:
        stored = super().read_document_content(secret)
        head, fence, tail = stored.partition("```json")
        reserialized = head.replace("\n- ", "\n* ")
        return (reserialized + fence + tail).rstrip("\n")


class FenceCorruptingWorkspace(FakeArchitectureWorkspace):
    """A fake that rewrites the fenced payload, which MUST fail the criterion."""

    def read_document_content(self, secret: str) -> str:
        stored = super().read_document_content(secret)
        return stored.replace('"version":1', '"version": 1')


def content_evidence(workspace_class) -> probe.Evidence:
    workspace = workspace_class(projects=[project(public_id="7")])
    node = workspace.create_project_document(ROOT_ID, "ROOT", "7")
    evidence = probe.Evidence(started_at="now")
    assert node.secret is not None
    probe.probe_content(workspace, evidence, node.secret)
    return evidence


def test_the_fence_extractor_returns_the_payload_verbatim():
    assert probe.extract_json_fence(probe.PROBE_PAYLOAD) == (
        '{"probe":"tsa-p1","version":1}'
    )


def test_the_fence_extractor_excludes_the_markers():
    extracted = probe.extract_json_fence(probe.PROBE_PAYLOAD)
    assert extracted is not None
    assert "```" not in extracted


@pytest.mark.parametrize(
    ("label", "markdown"),
    [
        ("no fence", "# T\n\nProse.\n"),
        ("two fences", "```json\n{}\n```\n\n```json\n{}\n```\n"),
        ("unclosed fence", "```json\n{}\n"),
    ],
)
def test_the_fence_extractor_refuses_an_ambiguous_document(label, markdown):
    assert probe.extract_json_fence(markdown) is None


def test_whole_markdown_inequality_alone_does_not_fail_the_criterion():
    """The exact live shape: bytes differ outside the fence, fence is intact."""
    evidence = content_evidence(ReserializingWorkspace)

    assert evidence.content["full_markdown_byte_equality"] == (
        probe.FULL_MARKDOWN_RESERIALIZED
    )
    assert evidence.content["json_fence_byte_equality"] == probe.PASS
    assert evidence.fingerprint["document_fingerprint_equality"] == probe.PASS
    # Nothing failed: whole-document bytes are observational only.
    assert evidence.failures == []


def test_an_exact_round_trip_reports_full_equality_too():
    evidence = content_evidence(FakeArchitectureWorkspace)

    assert evidence.content["full_markdown_byte_equality"] == probe.FULL_MARKDOWN_EQUAL
    assert evidence.content["json_fence_byte_equality"] == probe.PASS
    assert evidence.failures == []


def test_a_changed_fence_payload_fails_the_criterion():
    evidence = content_evidence(FenceCorruptingWorkspace)

    assert evidence.content["json_fence_byte_equality"] == probe.FAIL
    assert any("json_fence_byte_exact" in failure for failure in evidence.failures)


def test_the_fenced_payload_is_not_canonicalized_before_comparison():
    """Whitespace inside the fence is a difference, not something to absorb."""
    evidence = content_evidence(FenceCorruptingWorkspace)

    assert (
        evidence.content["written_fence_sha256"]
        != (evidence.content["read_fence_sha256"])
    )


def test_the_three_content_values_are_reported_separately():
    evidence = content_evidence(ReserializingWorkspace)

    assert "full_markdown_byte_equality" in evidence.content
    assert "json_fence_byte_equality" in evidence.content
    assert "document_fingerprint_equality" in evidence.fingerprint
    assert evidence.content["full_markdown_is_observational_only"] is True


def test_fence_byte_counts_and_hashes_are_recorded_both_sides():
    evidence = content_evidence(ReserializingWorkspace)

    for key in (
        "written_fence_bytes",
        "read_fence_bytes",
        "written_fence_sha256",
        "read_fence_sha256",
    ):
        assert evidence.content[key] is not None


def test_only_the_fence_gates_the_content_criterion():
    """The recorded check name is about the fence, not the whole document."""
    evidence = content_evidence(ReserializingWorkspace)

    assert "json_fence_byte_exact" in evidence.checks
    assert not [name for name in evidence.checks if "full_markdown" in name]


# ==========================================================================
# I-1 evidence wording
# ==========================================================================


def test_the_probe_credits_the_existing_repository_evidence():
    assert "constraint 8" in probe.EXISTING_EVIDENCE_NOTE
    assert "already" in probe.EXISTING_EVIDENCE_NOTE
    source = Path(probe.__file__).read_text(encoding="utf-8")
    assert "i1_existing_repository_evidence" in source
    assert "i1_p1_adapter_confirmation" in source


def test_the_probe_does_not_claim_first_ever_evidence():
    source = Path(probe.__file__).read_text(encoding="utf-8")
    assert "not the first evidence" in source


def test_sha256_is_over_utf8_bytes():
    import hashlib

    assert probe.sha256("架構") == hashlib.sha256("架構".encode()).hexdigest()


# ==========================================================================
# H1 — no expected failure reaches the default traceback printer
# ==========================================================================

SYNTHETIC_TOKEN = "SYNTHETIC-TOKEN-abc123"
SYNTHETIC_SECRET = "SYNTHETIC-DOCUMENT-SECRET-xyz789"


def chained_fibery_error() -> FiberyError:
    """A FiberyError shaped exactly as `FiberyClient` raises one.

    The public message is sanitized, but the original transport exception — which
    carries the token — is retained as `__cause__` by `raise ... from error`.
    That cause is what Python's default handler prints.
    """
    try:
        raise OSError(f"transport failed: Authorization: Bearer {SYNTHETIC_TOKEN}")
    except OSError as cause:
        error = FiberyError(
            "Views method 'query-views' failed; the server's response is not reported."
        )
        error.__cause__ = cause
        return error


def test_the_cause_chain_really_does_carry_the_secret():
    """Guards the test itself: without the boundary there would be a leak."""
    error = chained_fibery_error()
    assert error.__cause__ is not None
    assert SYNTHETIC_TOKEN in str(error.__cause__)
    assert SYNTHETIC_TOKEN not in str(error)


def test_sanitize_never_walks_the_cause_chain():
    message = probe.sanitize(chained_fibery_error())
    assert SYNTHETIC_TOKEN not in message
    assert "Bearer" not in message


def run_cli_with_failure(monkeypatch, capsys, failure: BaseException, *, argv=None):
    """Drive the real `cli()` entry point with `run` raising `failure`."""
    probe.register_secret(SYNTHETIC_TOKEN)
    probe.register_secret(SYNTHETIC_SECRET)

    def exploding(arguments, evidence):
        raise failure

    monkeypatch.setattr(probe, "run", exploding)
    code = probe.cli(argv or ["--project-id", "p-1", "--confirm-live-mutation"])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_a_chained_fibery_error_exits_nonzero_without_leaking(monkeypatch, capsys):
    code, out, err = run_cli_with_failure(monkeypatch, capsys, chained_fibery_error())

    assert code != 0
    assert SYNTHETIC_TOKEN not in out + err
    assert "Bearer" not in out + err
    assert "Traceback (most recent call last)" not in out + err
    assert "__cause__" not in out + err
    assert "direct cause" not in out + err
    assert "FAILED:" in err


@pytest.mark.parametrize(
    ("label", "failure"),
    [
        ("FiberyError", FiberyError(f"leaked {SYNTHETIC_SECRET}")),
        ("OSError", OSError(f"socket died holding {SYNTHETIC_TOKEN}")),
        ("unexpected bug", RuntimeError(f"bug near {SYNTHETIC_SECRET}")),
    ],
)
def test_every_failure_class_exits_nonzero_without_leaking(
    monkeypatch, capsys, label, failure
):
    code, out, err = run_cli_with_failure(monkeypatch, capsys, failure)

    assert code != 0
    assert SYNTHETIC_SECRET not in out + err
    assert SYNTHETIC_TOKEN not in out + err
    assert "Traceback (most recent call last)" not in out + err


def test_an_unexpected_bug_is_labelled_as_such(monkeypatch, capsys):
    _, _, err = run_cli_with_failure(monkeypatch, capsys, RuntimeError("something odd"))
    assert "unexpected failure" in err


def test_keyboard_interrupt_is_not_swallowed(monkeypatch, capsys):
    """BaseException must still propagate: Ctrl-C is not a probe failure."""
    with pytest.raises(KeyboardInterrupt):
        run_cli_with_failure(monkeypatch, capsys, KeyboardInterrupt())


def test_system_exit_is_not_swallowed(monkeypatch, capsys):
    with pytest.raises(SystemExit):
        run_cli_with_failure(monkeypatch, capsys, SystemExit(3))


def test_the_entry_point_raises_system_exit_from_cli():
    source = Path(probe.__file__).read_text(encoding="utf-8")
    assert "raise SystemExit(cli())" in source


def test_the_probe_never_formats_a_traceback_or_a_cause():
    """Checked against code, not prose: the docstrings discuss the leak."""
    import ast

    source = Path(probe.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert "traceback" not in imported

    attributes = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    assert "__cause__" not in attributes
    assert "__context__" not in attributes
    assert "print_exc" not in attributes
    assert "format_exc" not in attributes

    # `repr` of an exception is never formatted either.
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "repr" not in called


# ==========================================================================
# H1 — safe partial evidence
# ==========================================================================


def test_partial_evidence_is_written_and_carries_no_secret(
    monkeypatch, capsys, tmp_path
):
    destination = tmp_path / "partial.json"
    probe.register_secret(SYNTHETIC_SECRET)

    def exploding(arguments, evidence):
        # Something was measured before the failure.
        evidence.project = {"name": "scratch", "public_id": "7"}
        evidence.record("root_caller_id_preserved", True)
        raise FiberyError(f"died holding {SYNTHETIC_SECRET}")

    monkeypatch.setattr(probe, "run", exploding)
    code = probe.cli(
        [
            "--project-id",
            "p-1",
            "--confirm-live-mutation",
            "--evidence-out",
            str(destination),
        ]
    )

    assert code != 0
    written = destination.read_text(encoding="utf-8")
    assert SYNTHETIC_SECRET not in written
    assert probe.REDACTED in written
    payload = json.loads(written)
    assert payload["completed"] is False
    assert payload["failure"]
    assert any("run_failed" in failure for failure in payload["failures"])


def test_partial_evidence_never_implies_success(monkeypatch, capsys, tmp_path):
    destination = tmp_path / "partial.json"

    def exploding(arguments, evidence):
        evidence.project = {"name": "scratch"}
        raise FiberyError("boom")

    monkeypatch.setattr(probe, "run", exploding)
    probe.cli(
        [
            "--project-id",
            "p-1",
            "--confirm-live-mutation",
            "--evidence-out",
            str(destination),
        ]
    )

    payload = json.loads(destination.read_text(encoding="utf-8"))
    assert payload["completed"] is False
    assert payload["failures"]


def test_no_evidence_file_is_written_when_nothing_was_measured(
    monkeypatch, capsys, tmp_path
):
    destination = tmp_path / "absent.json"

    def exploding(arguments, evidence):
        raise FiberyError("failed before measuring anything")

    monkeypatch.setattr(probe, "run", exploding)
    code = probe.cli(
        [
            "--project-id",
            "p-1",
            "--confirm-live-mutation",
            "--evidence-out",
            str(destination),
        ]
    )

    assert code != 0
    assert not destination.exists()
    assert "FAILED:" in capsys.readouterr().err


def test_a_completed_run_marks_itself_completed():
    evidence = probe.Evidence(started_at="now")
    assert evidence.completed is False
    assert evidence.failure is None


# ==========================================================================
# The scrub registry
# ==========================================================================


def test_the_registry_scrubs_a_value_it_was_told_about():
    probe.register_secret(SYNTHETIC_TOKEN)
    assert SYNTHETIC_TOKEN not in probe.scrub(f"saw {SYNTHETIC_TOKEN} here")


def test_the_registry_ignores_empty_values():
    before = set(probe._SECRETS)
    probe.register_secret(None)
    probe.register_secret("")
    assert before == probe._SECRETS


def test_the_token_is_registered_before_any_request():
    source = Path(probe.__file__).read_text(encoding="utf-8")
    assert "register_secret(settings.token)" in source


# ==========================================================================
# M1-A — confirmed rejection versus unknown transport outcome
# ==========================================================================


@pytest.mark.parametrize(
    ("label", "error", "expected"),
    [
        ("no error", None, probe.OUTCOME_SUCCESS),
        (
            "live JSON-RPC rejection",
            FiberyError(LIVE_REJECTION),
            probe.OUTCOME_CONFIRMED_REJECTION,
        ),
        (
            "timeout",
            FiberyError("Views method 'create-views' failed: the request timed out"),
            probe.OUTCOME_UNKNOWN_TRANSPORT,
        ),
        (
            "connection reset",
            FiberyError("connection reset by peer"),
            probe.OUTCOME_UNKNOWN_TRANSPORT,
        ),
        (
            "dns failure",
            OSError("Name or service not known"),
            probe.OUTCOME_UNKNOWN_TRANSPORT,
        ),
        ("opener OSError", OSError("socket closed"), probe.OUTCOME_UNKNOWN_TRANSPORT),
        (
            "aborted before response",
            FiberyError("request aborted before a response was received"),
            probe.OUTCOME_UNKNOWN_TRANSPORT,
        ),
        (
            "generic FiberyError",
            FiberyError("Document 'x' already exists."),
            probe.OUTCOME_UNKNOWN_TRANSPORT,
        ),
    ],
)
def test_create_outcome_classification(label, error, expected):
    assert probe.classify_create_outcome(error) == expected


def test_a_timeout_with_unchanged_state_is_never_rejected():
    """The defect this closes: a timeout proves nothing about the server."""
    workspace = seeded_fake()

    def timing_out(document_id, name, project_public_id):
        raise FiberyError("Views method 'create-views' failed: the request timed out")

    workspace.create_project_document = timing_out  # type: ignore[method-assign]

    evidence = duplicate_evidence(workspace)

    assert evidence.duplicate["create_outcome"] == probe.OUTCOME_UNKNOWN_TRANSPORT
    assert evidence.duplicate["classification"] != probe.DUPLICATE_REJECTED
    assert evidence.duplicate["classification"] == probe.DUPLICATE_OTHER
    assert probe.FAILURE_DUPLICATE_UNKNOWN in evidence.checks
    assert evidence.failures


def test_an_unknown_transport_with_changed_state_is_mutated_existing():
    """An observed mutation outranks an unknown transport outcome."""
    workspace = seeded_fake()

    def timing_out_after_damage(document_id, name, project_public_id):
        workspace.documents[document_id].name = name
        raise FiberyError("the request timed out")

    workspace.create_project_document = timing_out_after_damage  # type: ignore[method-assign]

    evidence = duplicate_evidence(workspace)

    assert evidence.duplicate["create_outcome"] == probe.OUTCOME_UNKNOWN_TRANSPORT
    assert evidence.duplicate["classification"] == probe.DUPLICATE_MUTATED_EXISTING
    assert probe.FAILURE_DUPLICATE_STATE_CHANGED in evidence.checks


def test_a_confirmed_rejection_with_changed_placement_is_mutated_existing():
    workspace = seeded_fake()

    def refusing_after_damage(document_id, name, project_public_id):
        workspace.documents[document_id].parent_document_id = "elsewhere"
        raise FiberyError(LIVE_REJECTION)

    workspace.create_project_document = refusing_after_damage  # type: ignore[method-assign]

    evidence = duplicate_evidence(workspace)

    assert evidence.duplicate["create_outcome"] == probe.OUTCOME_CONFIRMED_REJECTION
    assert evidence.duplicate["classification"] == probe.DUPLICATE_MUTATED_EXISTING


def test_classification_never_inspects_the_cause_chain():
    """Classifying from a cause could read a secret-bearing transport message."""
    try:
        raise OSError(f"Bearer {SYNTHETIC_TOKEN}")
    except OSError as cause:
        error = FiberyError("the request timed out")
        error.__cause__ = cause

    assert probe.classify_create_outcome(error) == probe.OUTCOME_UNKNOWN_TRANSPORT
    import ast

    tree = ast.parse(inspect.getsource(probe.classify_create_outcome))
    attributes = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert "__cause__" not in attributes


# ==========================================================================
# M1-B — the snapshot absorbs expected read failures
# ==========================================================================


@pytest.mark.parametrize("failing_call", ["resolve_placement", "read_document_content"])
def test_a_snapshot_read_failure_is_unreadable_not_an_exception(failing_call):
    workspace = seeded_fake()
    workspace.failures[failing_call] = FiberyError(f"{failing_call} unavailable")

    state = probe.snapshot_durable_state(
        workspace, ROOT_ID, workspace.documents[ROOT_ID].secret
    )

    assert state["readable"] is False
    assert state["sanitized_error"]
    assert "FiberyError" in state["sanitized_error"]


def test_a_snapshot_of_an_absent_document_is_unreadable():
    workspace = seeded_fake()
    del workspace.documents[ROOT_ID]

    state = probe.snapshot_durable_state(workspace, ROOT_ID, "any-secret")

    assert state["readable"] is False
    assert state["placement"] == {"present": False}
    assert state["name"] is None
    assert state["content_sha256"] is None


def test_a_snapshot_fabricates_nothing_when_unreadable():
    workspace = seeded_fake()
    workspace.failures["resolve_placement"] = FiberyError("unavailable")

    state = probe.snapshot_durable_state(workspace, ROOT_ID, "s")

    assert state["name"] is None
    assert state["content_sha256"] is None


def test_a_snapshot_error_is_sanitized():
    workspace = seeded_fake()
    secret = workspace.documents[ROOT_ID].secret
    workspace.failures["read_document_content"] = FiberyError(f"leaked {secret}")

    state = probe.snapshot_durable_state(workspace, ROOT_ID, secret)

    assert secret not in str(state)
    assert probe.REDACTED in state["sanitized_error"]


@pytest.mark.parametrize("failing_call", ["resolve_placement", "read_document_content"])
def test_a_snapshot_failure_makes_the_duplicate_outcome_unknown(failing_call):
    workspace = rejecting_fake()
    workspace.failures[failing_call] = FiberyError(f"{failing_call} unavailable")

    evidence = duplicate_evidence(workspace)

    assert evidence.duplicate["classification"] == probe.DUPLICATE_OTHER
    assert probe.FAILURE_DUPLICATE_UNKNOWN in evidence.checks
    assert evidence.failures


def test_an_unreadable_before_snapshot_is_an_unknown_outcome():
    before = {
        "readable": False,
        "placement": {"present": False},
        "name": None,
        "content_sha256": None,
    }
    after = {
        "readable": True,
        "placement": {"present": True},
        "name": "ROOT",
        "content_sha256": "x",
    }

    assert (
        probe.classify_duplicate(probe.OUTCOME_CONFIRMED_REJECTION, before, after)
        == probe.DUPLICATE_OTHER
    )


def test_an_unreadable_after_snapshot_is_an_unknown_outcome():
    before = {
        "readable": True,
        "placement": {"present": True},
        "name": "ROOT",
        "content_sha256": "x",
    }
    after = {
        "readable": False,
        "placement": {"present": False},
        "name": None,
        "content_sha256": None,
    }

    assert (
        probe.classify_duplicate(probe.OUTCOME_CONFIRMED_REJECTION, before, after)
        == probe.DUPLICATE_OTHER
    )


# ==========================================================================
# H1-A — a secret is registered the instant it exists
# ==========================================================================


def test_the_root_secret_is_registered_before_anything_else_runs(monkeypatch, capsys):
    """A failure right after the root create must not be able to leak it."""
    workspace = FakeArchitectureWorkspace(projects=[project(public_id="7")])
    evidence = probe.Evidence(started_at="now")

    created: dict = {}
    real_create = workspace.create_project_document

    def capturing(document_id, name, project_public_id):
        node = real_create(document_id, name, project_public_id)
        created["secret"] = node.secret
        return node

    workspace.create_project_document = capturing  # type: ignore[method-assign]

    # The very next adapter call fails, carrying the secret.
    def failing_resolve(document_id):
        raise FiberyError(f"resolve failed holding {created['secret']}")

    workspace.resolve_document = failing_resolve  # type: ignore[method-assign]

    with pytest.raises(FiberyError):
        probe.probe_root(workspace, evidence, project(public_id="7"), "ROOT")

    assert created["secret"] in probe._SECRETS
    assert created["secret"] not in probe.scrub(f"saw {created['secret']}")


def test_the_child_secret_is_registered_before_anything_else_runs():
    workspace = FakeArchitectureWorkspace(projects=[project(public_id="7")])
    root = workspace.create_project_document(ROOT_ID, "ROOT", "7")
    evidence = probe.Evidence(started_at="now")
    root_placement = workspace.resolve_placement(ROOT_ID)
    assert root_placement is not None

    created: dict = {}
    real_create = workspace.create_tsa_child_document

    def capturing(document_id, name, parent_document_id):
        node = real_create(document_id, name, parent_document_id)
        created["secret"] = node.secret
        return node

    workspace.create_tsa_child_document = capturing  # type: ignore[method-assign]
    workspace.failures["resolve_placement"] = FiberyError("next call fails")

    with pytest.raises(FiberyError):
        probe.probe_child(
            workspace,
            evidence,
            project(public_id="7"),
            ROOT_ID,
            root_placement,
            "CHILD",
        )

    assert created["secret"] in probe._SECRETS
    assert root.secret in probe._SECRETS


#: Every probe-side helper that registers a secret.
REGISTRARS = (
    "register_secret",
    "register_document_secret",
    "register_placement_secret",
    "register_document_collection_secrets",
    "register_placement_collection_secrets",
)

#: Every adapter method the probe calls that can hand back an object carrying a
#: Document secret. Kept as data so a newly used read cannot quietly skip
#: registration: add a call and this inventory fails until it is wrapped.
SECRET_BEARING_READS = (
    "create_project_document",
    "create_tsa_child_document",
    "resolve_document",
    "resolve_placement",
    "documents_attached_to_project",
    "child_documents",
    "child_placements",
)


def probe_source_tree():
    import ast

    return ast.parse(Path(probe.__file__).read_text(encoding="utf-8"))


def test_the_inventory_covers_every_secret_bearing_read_the_probe_calls():
    """No secret-bearing adapter read may be called that is not in the list."""
    import ast

    tree = probe_source_tree()
    called = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "workspace"
    }
    # Reads that cannot carry a secret are allowed outside the inventory.
    secretless = {"read_project", "read_document_content", "write_document_content"}
    uncovered = called - set(SECRET_BEARING_READS) - secretless
    assert not uncovered, f"unclassified workspace reads: {sorted(uncovered)}"


@pytest.mark.parametrize("read", SECRET_BEARING_READS)
def test_every_secret_bearing_read_registers_before_anything_else(read):
    """Structural: the result is registered in the same expression or the next
    statement, so nothing can run between receipt and registration."""
    import ast

    tree = probe_source_tree()
    sites = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == read
    ]
    assert sites, f"{read} is never called; drop it from the inventory"

    for function in (
        node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    ):
        for index, statement in enumerate(function.body):
            rendered = ast.unparse(statement)
            if f".{read}(" not in rendered:
                continue
            wrapped_inline = any(registrar in rendered for registrar in REGISTRARS)
            following = (
                ast.unparse(function.body[index + 1])
                if index + 1 < len(function.body)
                else ""
            )
            registered_next = any(registrar in following for registrar in REGISTRARS)
            assert wrapped_inline or registered_next, (
                f"{function.name}: {read} result is not registered immediately: "
                f"{rendered}"
            )


# ==========================================================================
# H1-B — the failure handler is itself fail-safe
# ==========================================================================


def test_an_unwritable_evidence_path_does_not_raise(monkeypatch, capsys):
    def exploding(arguments, evidence):
        evidence.project = {"name": "scratch"}
        raise FiberyError(f"primary failure holding {SYNTHETIC_SECRET}")

    probe.register_secret(SYNTHETIC_SECRET)
    monkeypatch.setattr(probe, "run", exploding)

    code = probe.cli(
        [
            "--project-id",
            "p-1",
            "--confirm-live-mutation",
            "--evidence-out",
            "/nonexistent-directory-xyz/partial.json",
        ]
    )

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert code != 0
    assert "Traceback (most recent call last)" not in combined
    assert SYNTHETIC_SECRET not in combined
    assert "partial evidence not written" in captured.err


def test_an_unexpected_evidence_write_failure_does_not_raise(monkeypatch, capsys):
    def exploding(arguments, evidence):
        evidence.project = {"name": "scratch"}
        raise FiberyError("primary failure")

    def unexpected_emit(evidence, destination):
        raise RuntimeError(f"odd failure mentioning {SYNTHETIC_TOKEN}")

    probe.register_secret(SYNTHETIC_TOKEN)
    monkeypatch.setattr(probe, "run", exploding)
    monkeypatch.setattr(probe, "_emit", unexpected_emit)

    code = probe.cli(
        ["--project-id", "p-1", "--confirm-live-mutation", "--evidence-out", "x.json"]
    )

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert code != 0
    assert "Traceback (most recent call last)" not in combined
    assert SYNTHETIC_TOKEN not in combined
    assert "unexpected output failure" in captured.err


def test_a_broken_stderr_does_not_raise(monkeypatch):
    """The reporter of last resort cannot itself fail."""

    def broken_print(*args, **kwargs):
        raise OSError("stderr closed")

    monkeypatch.setattr("builtins.print", broken_print)
    probe._safe_stderr("anything")  # must not raise


def test_the_failure_handler_returns_an_integer(monkeypatch, capsys):
    def exploding(arguments, evidence):
        raise FiberyError("boom")

    monkeypatch.setattr(probe, "run", exploding)
    code = probe.cli(["--project-id", "p-1", "--confirm-live-mutation"])
    assert isinstance(code, int) and code != 0


# ==========================================================================
# H1-A — secrets from LATER reads, not just creates
# ==========================================================================

LATE_SECRET = "LATE-READ-SECRET-9f9f"


def workspace_with_late_secret() -> FakeArchitectureWorkspace:
    """A workspace whose root Document carries a known secret."""
    workspace = FakeArchitectureWorkspace(projects=[project(public_id="7")])
    workspace.create_project_document(ROOT_ID, "ROOT", "7")
    workspace.documents[ROOT_ID].secret = LATE_SECRET
    workspace.content[LATE_SECRET] = "original"
    return workspace


@pytest.mark.parametrize(
    ("label", "registrar", "value"),
    [
        ("resolve_document", "register_document_secret", "node"),
        ("resolve_placement", "register_placement_secret", "placement"),
    ],
)
def test_a_single_late_read_registers_its_secret(label, registrar, value):
    workspace = workspace_with_late_secret()
    probe._SECRETS.discard(LATE_SECRET)

    if value == "node":
        probe.register_document_secret(workspace.resolve_document(ROOT_ID))
    else:
        probe.register_placement_secret(workspace.resolve_placement(ROOT_ID))

    assert LATE_SECRET in probe._SECRETS
    assert LATE_SECRET not in probe.scrub(f"message holding {LATE_SECRET}")


def test_a_listing_registers_every_secret_before_the_list_is_used():
    workspace = workspace_with_late_secret()
    probe._SECRETS.discard(LATE_SECRET)

    probe.register_placement_collection_secrets(
        workspace.documents_attached_to_project("7")
    )

    assert LATE_SECRET in probe._SECRETS


def test_a_document_listing_registers_every_secret():
    workspace = workspace_with_late_secret()
    workspace.create_tsa_child_document(CHILD_ID, "CHILD", ROOT_ID)
    workspace.documents[CHILD_ID].secret = LATE_SECRET + "-child"
    probe._SECRETS.discard(LATE_SECRET + "-child")

    probe.register_document_collection_secrets(workspace.child_documents(ROOT_ID))

    assert LATE_SECRET + "-child" in probe._SECRETS


@pytest.mark.parametrize("registrar", list(REGISTRARS[1:]))
def test_every_registrar_tolerates_absence(registrar):
    helper = getattr(probe, registrar)
    if "collection" in registrar:
        assert helper([]) == []
    else:
        assert helper(None) is None


def test_the_rediscovery_listing_registers_before_it_filters():
    """End to end: a failure after the listing cannot leak a listed secret."""
    workspace = workspace_with_late_secret()
    probe._SECRETS.discard(LATE_SECRET)
    evidence = probe.Evidence(started_at="now")
    root_placement = workspace.resolve_placement(ROOT_ID)
    assert root_placement is not None

    probe.probe_rediscovery(
        workspace, evidence, project(public_id="7"), ROOT_ID, root_placement
    )

    assert LATE_SECRET in probe._SECRETS
    assert LATE_SECRET not in repr(evidence.root)


def test_the_snapshot_registers_the_placement_secret_before_reading_content():
    """F: a content read failure mentioning the secret must come back sanitized."""
    workspace = workspace_with_late_secret()
    probe._SECRETS.discard(LATE_SECRET)
    workspace.failures["read_document_content"] = FiberyError(
        f"content read failed holding {LATE_SECRET}"
    )

    state = probe.snapshot_durable_state(workspace, ROOT_ID, LATE_SECRET)

    assert state["readable"] is False
    assert LATE_SECRET not in str(state)
    assert probe.REDACTED in state["sanitized_error"]


def test_a_child_listing_secret_cannot_leak_through_a_later_failure():
    workspace = workspace_with_late_secret()
    root_placement = workspace.resolve_placement(ROOT_ID)
    assert root_placement is not None
    child = workspace.create_tsa_child_document(CHILD_ID, "CHILD", ROOT_ID)
    workspace.documents[CHILD_ID].secret = LATE_SECRET
    probe._SECRETS.discard(LATE_SECRET)
    del child

    evidence = probe.Evidence(started_at="now")
    probe.register_placement_collection_secrets(workspace.child_placements(ROOT_ID))

    assert LATE_SECRET in probe._SECRETS
    assert LATE_SECRET not in repr(evidence.child)


# ==========================================================================
# M1-A — a query-views failure is not a create rejection
# ==========================================================================

QUERY_VIEWS_REJECTION = (
    "Views method 'query-views' failed: Fibery returned a JSON-RPC error "
    "(code -32000); the server's response is not reported."
)


@pytest.mark.parametrize(
    ("label", "error", "expected"),
    [
        (
            "create-views JSON-RPC",
            FiberyError(LIVE_REJECTION),
            probe.OUTCOME_CONFIRMED_REJECTION,
        ),
        (
            "query-views JSON-RPC",
            FiberyError(QUERY_VIEWS_REJECTION),
            probe.OUTCOME_UNKNOWN_TRANSPORT,
        ),
        (
            "create-views without a server answer",
            FiberyError("Views method 'create-views' failed: the request timed out"),
            probe.OUTCOME_UNKNOWN_TRANSPORT,
        ),
        (
            "server answer without the method",
            FiberyError("Fibery returned a JSON-RPC error (code -32000)"),
            probe.OUTCOME_UNKNOWN_TRANSPORT,
        ),
    ],
)
def test_only_a_create_views_server_answer_is_a_confirmed_rejection(
    label, error, expected
):
    assert probe.classify_create_outcome(error) == expected


def test_a_query_views_failure_during_read_back_is_an_unknown_outcome():
    """The reviewer's counterexample, end to end."""
    workspace = seeded_fake()

    def create_then_read_back_fails(document_id, name, project_public_id):
        raise FiberyError(QUERY_VIEWS_REJECTION)

    workspace.create_project_document = (  # type: ignore[method-assign]
        create_then_read_back_fails
    )

    evidence = duplicate_evidence(workspace)

    assert evidence.duplicate["create_outcome"] == probe.OUTCOME_UNKNOWN_TRANSPORT
    assert evidence.duplicate["classification"] == probe.DUPLICATE_OTHER
    assert evidence.duplicate["classification"] != probe.DUPLICATE_REJECTED
    assert probe.FAILURE_DUPLICATE_UNKNOWN in evidence.checks
    assert evidence.failures != []


def test_the_query_views_counterexample_exits_nonzero(monkeypatch, capsys):
    def failing_run(arguments, evidence):
        evidence.duplicate = {"classification": probe.DUPLICATE_OTHER}
        evidence.record(probe.FAILURE_DUPLICATE_UNKNOWN, False, "unknown outcome")
        evidence.completed = True
        return probe.EXIT_OK if not evidence.failures else probe.EXIT_FAILED

    monkeypatch.setattr(probe, "run", failing_run)
    assert probe.cli(["--project-id", "p-1", "--confirm-live-mutation"]) != 0


# ==========================================================================
# H1-B — exactly one evidence write attempt, ever
# ==========================================================================


def counting_writer(failure: BaseException):
    calls = {"n": 0}

    def writer(evidence, destination):
        calls["n"] += 1
        raise failure

    return writer, calls


@pytest.mark.parametrize(
    ("label", "failure"),
    [("OSError", OSError("unwritable")), ("RuntimeError", RuntimeError("odd"))],
)
def test_a_failing_partial_evidence_write_is_attempted_once(
    monkeypatch, capsys, label, failure
):
    writer, calls = counting_writer(failure)

    def exploding(arguments, evidence):
        evidence.project = {"name": "scratch"}
        raise FiberyError("primary failure")

    monkeypatch.setattr(probe, "run", exploding)
    monkeypatch.setattr(probe, "_emit", writer)

    code = probe.cli(
        ["--project-id", "p-1", "--confirm-live-mutation", "--evidence-out", "x.json"]
    )

    captured = capsys.readouterr()
    assert code != 0
    assert calls["n"] == 1, f"writer called {calls['n']} times"
    assert "Traceback (most recent call last)" not in captured.out + captured.err


@pytest.mark.parametrize(
    ("label", "failure"),
    [("OSError", OSError("unwritable")), ("RuntimeError", RuntimeError("odd"))],
)
def test_a_failing_final_evidence_write_is_attempted_once(
    monkeypatch, capsys, label, failure
):
    """The defect this closes: the reporter used to retry the final write."""
    writer, calls = counting_writer(failure)

    def completing(arguments, evidence):
        evidence.project = {"name": "scratch"}
        evidence.completed = True
        probe._emit_once(evidence, arguments.evidence_out)
        return probe.EXIT_OK

    monkeypatch.setattr(probe, "run", completing)
    monkeypatch.setattr(probe, "_emit", writer)

    code = probe.cli(
        ["--project-id", "p-1", "--confirm-live-mutation", "--evidence-out", "x.json"]
    )

    captured = capsys.readouterr()
    assert code != 0
    assert calls["n"] == 1, f"writer called {calls['n']} times"
    assert "Traceback (most recent call last)" not in captured.out + captured.err
    assert "FAILED:" in captured.err


def test_an_evidence_output_failure_never_reaches_the_generic_reporter(
    monkeypatch, capsys
):
    reporter_calls = {"n": 0}
    real_reporter = probe._report_failure

    def counting_reporter(evidence, arguments, message):
        reporter_calls["n"] += 1
        return real_reporter(evidence, arguments, message)

    def completing(arguments, evidence):
        evidence.completed = True
        probe._emit_once(evidence, arguments.evidence_out)
        return probe.EXIT_OK

    monkeypatch.setattr(probe, "run", completing)
    monkeypatch.setattr(probe, "_report_failure", counting_reporter)
    monkeypatch.setattr(
        probe,
        "_emit",
        lambda evidence, destination: (_ for _ in ()).throw(OSError("x")),
    )

    code = probe.cli(
        ["--project-id", "p-1", "--confirm-live-mutation", "--evidence-out", "x.json"]
    )

    assert code != 0
    assert reporter_calls["n"] == 0, "the generic reporter must not be entered"


def test_an_unexpected_write_failure_reports_no_message_text(monkeypatch, capsys):
    """An unsanitized message is never printed, only a fixed phrase."""

    def completing(arguments, evidence):
        evidence.completed = True
        probe._emit_once(evidence, arguments.evidence_out)
        return probe.EXIT_OK

    probe.register_secret(SYNTHETIC_TOKEN)
    monkeypatch.setattr(probe, "run", completing)
    monkeypatch.setattr(
        probe,
        "_emit",
        lambda evidence, destination: (_ for _ in ()).throw(
            RuntimeError(f"holds {SYNTHETIC_TOKEN}")
        ),
    )

    probe.cli(
        ["--project-id", "p-1", "--confirm-live-mutation", "--evidence-out", "x.json"]
    )

    err = capsys.readouterr().err
    assert SYNTHETIC_TOKEN not in err
    assert "unexpected output failure" in err


# ==========================================================================
# Exactly one evidence write attempt, on EVERY path
# ==========================================================================


def test_emit_is_only_ever_called_from_the_guarded_writer():
    """Structural: no path may acquire its own evidence-write error handling.

    Every evidence output — the final emission, each early return, and the
    reporter's partial write — must go through `_emit_once`. A direct `_emit`
    anywhere else is how an early path previously bypassed the invariant.
    """
    import ast

    tree = probe_source_tree()
    offenders = []
    for function in (
        node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    ):
        if function.name == "_emit_once":
            continue  # the one owner of the write
        for node in ast.walk(function):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "_emit"
            ):
                offenders.append(f"{function.name}:{node.lineno}")
    assert not offenders, f"direct _emit call sites outside _emit_once: {offenders}"


def test_the_guarded_writer_owns_exactly_one_emit_call():
    import ast

    tree = probe_source_tree()
    owner = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_emit_once"
    )
    emits = [
        node
        for node in ast.walk(owner)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_emit"
    ]
    assert len(emits) == 1


def write_failure_counts(monkeypatch, capsys, failure, runner, argv):
    """Drive `cli()` with a failing writer and count writer/reporter entries."""
    counts = {"writer": 0, "reporter": 0}
    real_reporter = probe._report_failure

    def writer(evidence, destination):
        counts["writer"] += 1
        raise failure

    def reporter(evidence, arguments, message):
        counts["reporter"] += 1
        return real_reporter(evidence, arguments, message)

    probe.register_secret(SYNTHETIC_TOKEN)
    monkeypatch.setattr(probe, "_emit", writer)
    monkeypatch.setattr(probe, "_report_failure", reporter)
    monkeypatch.setattr(probe, "run", runner)
    code = probe.cli(argv)
    captured = capsys.readouterr()
    return counts, code, captured.out + captured.err


def preflight_runner(arguments, evidence):
    """The read-only path: resolve the Project, then stop before mutation."""
    evidence.project = {"name": "scratch", "entity_id": "p-1", "public_id": "7"}
    if not arguments.confirm_live_mutation:
        probe._emit_once(evidence, arguments.evidence_out)
        return probe.EXIT_BLOCKED
    return probe.EXIT_OK


def early_failure_runner(arguments, evidence):
    """An early FAILED return that writes evidence, e.g. no usable root."""
    evidence.project = {"name": "scratch"}
    evidence.record("root_secret_usable", False, "no secret")
    probe._emit_once(evidence, arguments.evidence_out)
    return probe.EXIT_FAILED


def final_runner(arguments, evidence):
    evidence.project = {"name": "scratch"}
    evidence.completed = True
    probe._emit_once(evidence, arguments.evidence_out)
    return probe.EXIT_OK


def reporter_runner(arguments, evidence):
    """A primary runtime failure, so the reporter attempts the partial write."""
    evidence.project = {"name": "scratch"}
    raise FiberyError(f"primary failure holding {SYNTHETIC_TOKEN}")


@pytest.mark.parametrize(
    ("label", "failure"),
    [("OSError", OSError("unwritable")), ("RuntimeError", RuntimeError("odd"))],
)
@pytest.mark.parametrize(
    ("path", "runner", "argv"),
    [
        (
            "read-only preflight",
            preflight_runner,
            ["--project-id", "p-1", "--evidence-out", "x.json"],
        ),
        (
            "early failed return",
            early_failure_runner,
            [
                "--project-id",
                "p-1",
                "--confirm-live-mutation",
                "--evidence-out",
                "x.json",
            ],
        ),
        (
            "final emission",
            final_runner,
            [
                "--project-id",
                "p-1",
                "--confirm-live-mutation",
                "--evidence-out",
                "x.json",
            ],
        ),
        (
            "reporter partial write",
            reporter_runner,
            [
                "--project-id",
                "p-1",
                "--confirm-live-mutation",
                "--evidence-out",
                "x.json",
            ],
        ),
    ],
)
def test_every_evidence_path_writes_at_most_once(
    monkeypatch, capsys, label, failure, path, runner, argv
):
    counts, code, output = write_failure_counts(
        monkeypatch, capsys, failure, runner, argv
    )

    assert counts["writer"] == 1, f"{path}/{label}: writer called {counts['writer']}x"
    assert code != 0
    assert "Traceback (most recent call last)" not in output
    assert SYNTHETIC_TOKEN not in output


@pytest.mark.parametrize(
    ("path", "runner", "argv"),
    [
        (
            "read-only preflight",
            preflight_runner,
            ["--project-id", "p-1", "--evidence-out", "x.json"],
        ),
        (
            "early failed return",
            early_failure_runner,
            [
                "--project-id",
                "p-1",
                "--confirm-live-mutation",
                "--evidence-out",
                "x.json",
            ],
        ),
        (
            "final emission",
            final_runner,
            [
                "--project-id",
                "p-1",
                "--confirm-live-mutation",
                "--evidence-out",
                "x.json",
            ],
        ),
    ],
)
def test_an_evidence_write_failure_never_enters_the_generic_reporter(
    monkeypatch, capsys, path, runner, argv
):
    """The defect this closes: the reporter used to retry the write."""
    counts, code, output = write_failure_counts(
        monkeypatch, capsys, OSError("unwritable"), runner, argv
    )

    assert counts["reporter"] == 0, f"{path}: reporter entered {counts['reporter']}x"
    assert code != 0
    assert "FAILED:" in output


def test_a_successful_early_return_keeps_its_exit_code(monkeypatch, capsys, tmp_path):
    """Routing through the guarded writer must not change normal semantics."""
    destination = tmp_path / "preflight.json"
    monkeypatch.setattr(probe, "run", preflight_runner)

    code = probe.cli(["--project-id", "p-1", "--evidence-out", str(destination)])

    assert code == probe.EXIT_BLOCKED
    assert (
        json.loads(destination.read_text(encoding="utf-8"))["project"]["public_id"]
        == "7"
    )


def test_a_successful_final_emission_still_returns_ok(monkeypatch, tmp_path):
    destination = tmp_path / "final.json"
    monkeypatch.setattr(probe, "run", final_runner)

    assert (
        probe.cli(
            [
                "--project-id",
                "p-1",
                "--confirm-live-mutation",
                "--evidence-out",
                str(destination),
            ]
        )
        == probe.EXIT_OK
    )
    assert json.loads(destination.read_text(encoding="utf-8"))["completed"] is True
