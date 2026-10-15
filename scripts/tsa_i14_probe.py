#!/usr/bin/env python
"""I14: controlled live-model probes for TSA-C01 (M-class evidence only).

This is a probe instrument, not part of the `sdlc` capability. It runs the
real I07 Architect stage and the real I08 Reviewer stage — their production
prompt builders, validators, renderer, traceability and derived Review status
— against SYNTHETIC Requirements held in the in-memory Fibery fakes the domain
suites use. The only live external operation is the model invocation, through
the existing `LocalCliModelRuntime` with the configured `tsa_architect` and
`tsa_reviewer` roles: the locally authenticated CLI, its unchanged reasoning
child restrictions and its authentication guard. No Fibery API is called, no
provider API, SDK or key is used, and no real Project data exists here.

Four scenarios are declared in this file before any model call (S1-S4). Each
runs at most one Architect call and, only when the Architect stage produced a
valid applied output, at most one Reviewer call. A hard budget of 10 inference
calls covers the whole run; nothing is retried on a semantic failure.

    # Offline: build and admit every fixture, assemble the real Architect
    # prompts, record digests. No inference call.
    uv run python scripts/tsa_i14_probe.py --dry-run --out <dir>

    # Live: the predeclared scenarios, once each.
    uv run python scripts/tsa_i14_probe.py --live --out <dir> [--only S1 ...]

Every prompt, context and raw response is written to the evidence directory.
They are synthetic. Authentication output is never captured: only the
runtime's own sanitized login summary is recorded.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "tests"))

from apply_fake import build_apply_workspace
from review_fake import tree_bound_process_result, tree_manifest
from sdlc.fibery_workspace import (
    DocumentNode,
    RequirementRecord,
)
from sdlc.model_runtime import (
    LocalCliModelRuntime,
    ModelResponse,
    ModelRuntime,
    ModelRuntimeError,
)
from sdlc.model_runtime_config import (
    TSA_ARCHITECT_ROLE,
    TSA_REVIEWER_ROLE,
    load_model_runtime_config,
    select_runtime,
)
from sdlc.normative_tree import document_fingerprint
from sdlc.process_result import process_result_name, render_process_result
from sdlc.review_result import (
    build_review_result,
    render_review_result,
    review_result_name,
)
from sdlc.standard_analysis import AnalysisResult, NormalizedRequirement
from sdlc.standard_review import ReviewOutput
from sdlc.tsa_admission import (
    AdmissionRefused,
    StartInputs,
    UxNotApplicable,
    start_input_manifest,
)
from sdlc.tsa_architect import (
    ArchitectRefused,
    run_architect_stage,
)
from sdlc.tsa_artifacts import extract_artifact_payload
from sdlc.tsa_cycle import BootstrapContext, DocumentKind
from sdlc.tsa_reviewer import ReviewerRefused, run_reviewer_stage
from test_tsa_admission import (
    PROJECT_CODE,
    PROJECT_ID,
    PUBLIC_ID,
    TsaWorkspace,
)
from test_tsa_cycle import WORKSPACE

#: The whole run may make at most this many inference calls (I14 brief 8).
INFERENCE_BUDGET = 10
UX_REASON = (
    "A back-end service only; there is no user-facing surface in this synthetic "
    "selection."
)
FIXED_INSTANT = datetime(2026, 10, 15, 12, 0, 0, tzinfo=UTC)


def fixed_clock() -> datetime:
    return FIXED_INSTANT


# ---------------------------------------------------------------------------
# The predeclared synthetic scenarios (I14 brief 7)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Requirement:
    requirement_id: str
    title: str
    requirement: str
    detailed_behavior: str
    rationale: str
    acceptance_verification: str
    constraints_edge_cases: str
    non_goals: str
    open_questions: str

    def normalized(self) -> NormalizedRequirement:
        return NormalizedRequirement(
            title=self.title,
            requirement=self.requirement,
            detailed_behavior=self.detailed_behavior,
            rationale=self.rationale,
            acceptance_verification=self.acceptance_verification,
            constraints_edge_cases=self.constraints_edge_cases,
            non_goals=self.non_goals,
            open_questions=self.open_questions,
        )


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    cycle_id: str
    purpose: str
    rows: tuple[str, ...]
    requirements: tuple[Requirement, ...]


SCENARIOS = (
    Scenario(
        "S1",
        "i14-2026-10-s1",
        "Coherent architecture: an authenticated event intake service.",
        ("1-M", "24-M"),
        (
            Requirement(
                "SDLC-FR-0101",
                "Accept authenticated event submissions",
                "The service must accept event submissions only from callers that "
                "present a valid service token, and reject every other submission.",
                "A submission carries an event type, a source identifier and a JSON "
                "payload of at most 64 KB. A missing, expired or unknown token is "
                "rejected with an explicit authentication error and nothing is "
                "stored.",
                "Only known internal producers may write events.",
                "A submission without a valid token is rejected and leaves no "
                "stored record; a valid one is acknowledged with an event id.",
                "Payloads above 64 KB are rejected as too large.",
                "Does not define how service tokens are issued.",
                "None.",
            ),
            Requirement(
                "SDLC-FR-0102",
                "Validate and persist accepted events",
                "Every accepted event must be validated against its event type's "
                "schema and persisted durably before it is acknowledged.",
                "An event that fails validation is rejected with the validation "
                "errors and is not persisted. A persisted event keeps its "
                "submission time, source identifier and payload unchanged.",
                "Consumers rely on stored events being valid and complete.",
                "An acknowledged event can be read back unchanged after a service "
                "restart; an invalid event is never stored.",
                "Event type schemas are versioned; an unknown event type is rejected.",
                "Does not define the event type schemas themselves.",
                "None.",
            ),
            Requirement(
                "SDLC-FR-0103",
                "Report event processing status",
                "A caller must be able to retrieve the processing status of a "
                "submitted event by its event id, and every failure must be "
                "visible in an audit log.",
                "Status retrieval returns exactly one of RECEIVED, STORED or "
                "REJECTED for a known event id and a not-found result for an "
                "unknown one; the same id always returns the same status once it "
                "is final. Errors are bounded: no request waits longer than five "
                "seconds, and every rejection or internal error writes one audit "
                "entry.",
                "Producers need a deterministic way to confirm what happened.",
                "Repeated status reads of a final event return the same value; "
                "every rejection appears once in the audit log.",
                "Audit entries never contain the event payload.",
                "Does not define an audit retention period.",
                "None.",
            ),
        ),
    ),
    Scenario(
        "S2",
        "i14-2026-10-s2",
        "Contradictory Requirements about the same records, with no priority.",
        ("17-M",),
        (
            Requirement(
                "SDLC-FR-0201",
                "Delete event records after seven days",
                "Every stored event record must be permanently deleted seven days "
                "after it was received.",
                "Deletion applies to all event records in the event store, "
                "including their payloads; a deleted record cannot be retrieved.",
                "Stored events must not be kept longer than necessary.",
                "An event record received more than seven days ago cannot be "
                "retrieved.",
                "Applies to every event record without exception.",
                "Does not cover backups.",
                "None.",
            ),
            Requirement(
                "SDLC-FR-0202",
                "Retain event records for ninety days",
                "Every stored event record must remain available for retrieval for "
                "at least ninety days after it was received.",
                "Retention applies to all event records in the event store, "
                "including their payloads; retrieval within ninety days returns "
                "the record unchanged.",
                "Consumers need to re-read events during investigations.",
                "An event record received eighty days ago can still be retrieved "
                "unchanged.",
                "Applies to every event record without exception.",
                "Does not cover backups.",
                "None.",
            ),
        ),
    ),
    Scenario(
        "S3",
        "i14-2026-10-s3",
        "An unresolved product decision: who may export audit events.",
        ("30-M",),
        (
            Requirement(
                "SDLC-FR-0301",
                "Export audit events",
                "Authorized users can export audit events for a chosen date range "
                "as a downloadable file.",
                "The export contains every audit event whose time falls within the "
                "chosen range, in time order. An export request from a user who is "
                "not authorized is refused.",
                "Operators need audit evidence outside the service.",
                "An authorized user receives a file with exactly the audit events "
                "of the range; an unauthorized user receives a refusal.",
                "The set of users or roles authorized to export audit events is "
                "not defined by this Requirement.",
                "Does not define the file format beyond being downloadable.",
                "None.",
            ),
            Requirement(
                "SDLC-FR-0302",
                "Record audit events",
                "Every administrative action on the service must be recorded as an "
                "audit event.",
                "An audit event records the action, the acting identity and the "
                "time. Audit events cannot be modified or deleted through the "
                "service.",
                "Administrative actions must be traceable.",
                "Every administrative action produces exactly one audit event.",
                "Audit events never contain secrets.",
                "Does not define which actions are administrative beyond service "
                "configuration changes.",
                "None.",
            ),
        ),
    ),
    Scenario(
        "S4",
        "i14-2026-10-s4",
        "Coherent but delivery-heavy Requirements that invite plans and tasks.",
        ("36-M", "25-M"),
        (
            Requirement(
                "SDLC-FR-0401",
                "Migrate stored events to the new schema without downtime",
                "All stored events must be migrated from the current storage schema "
                "to the new one while the service keeps accepting submissions.",
                "During the migration, submissions and status reads keep working "
                "for every producer and consumer. After it, every event is "
                "readable in the new schema with its original values.",
                "The new schema is needed for replay, and no outage is acceptable.",
                "No submission fails because of the migration; after it, every "
                "previously stored event reads back with identical values.",
                "Several million events are stored; the migration may take days.",
                "Does not change the event payload format.",
                "None.",
            ),
            Requirement(
                "SDLC-FR-0402",
                "Support event replay for downstream consumers",
                "A downstream consumer must be able to replay stored events of a "
                "given type from a chosen point in time, in their original order.",
                "Replay delivers the same events in the same order every time for "
                "the same starting point. A consumer can stop and resume a replay "
                "without receiving an event twice.",
                "Consumers rebuild their own state after failures.",
                "Two replays from the same point deliver identical sequences; a "
                "resumed replay neither skips nor repeats an event.",
                "Several consumers may replay at the same time.",
                "Does not define how consumers are registered.",
                "None.",
            ),
            Requirement(
                "SDLC-FR-0403",
                "Limit submissions per source",
                "Submissions must be rate-limited per source identifier so that one "
                "source cannot exhaust the service.",
                "A source that exceeds 100 submissions per second receives an "
                "explicit rate-limit refusal for the excess; other sources are not "
                "affected.",
                "One faulty producer must not degrade the service for others.",
                "A burst from one source above the limit is refused for that source "
                "only.",
                "The limit applies per source identifier, across all instances of "
                "the service.",
                "Does not define per-tenant quotas.",
                "None.",
            ),
        ),
    ),
)


# ---------------------------------------------------------------------------
# Synthetic Fibery state: the in-memory fakes, with real Applied evidence
# ---------------------------------------------------------------------------


def _child(ws, root, name, public_id, kind) -> DocumentNode:
    node = DocumentNode(
        id=f"{kind}-doc-{public_id}",
        name=name,
        folder_id=None,
        entity_public_id=None,
        secret=f"{kind}-secret-{public_id}",
        parent_document_id=root.id,
    )
    ws.documents.append(node)
    return node


def add_requirement(ws, item: Requirement, public_id: str) -> str:
    """One Applied Standard Requirement whose evidence the real builders wrote."""
    entity_id = f"synthetic-{public_id}"
    ws.requirements[entity_id] = RequirementRecord(
        id=entity_id,
        public_id=public_id,
        requirement_id=item.requirement_id,
        title=item.title,
        type_name="Standard",
        state="Applied",
        revision=1,
        project_id=PROJECT_ID,
        source_fingerprint=None,
    )
    content = item.normalized()
    root = DocumentNode(
        id=f"root-{public_id}",
        name=f"{item.requirement_id} — {item.title}",
        folder_id=None,
        entity_public_id=public_id,
        secret=f"root-secret-{public_id}",
    )
    ws.documents.append(root)
    ws.content[root.secret] = content.document(item.requirement_id)
    process = tree_bound_process_result(
        ws,
        root,
        iteration=1,
        analysis=AnalysisResult(content, {"clarity": "adequate"}, (), ()),
        requirement_id=item.requirement_id,
    )
    node = _child(
        ws, root, process_result_name(item.requirement_id, 1), public_id, "process"
    )
    ws.content[node.secret] = render_process_result(process)
    reviewed = tree_manifest(ws, root, item.requirement_id)
    review = build_review_result(
        item.requirement_id,
        1,
        reviewed.root_entry.content_fingerprint,
        1,
        process.output_fingerprint,
        ReviewOutput((), (), (), {"clarity": "adequate"}),
        reviewed,
    )
    node = _child(
        ws, root, review_result_name(item.requirement_id, 1), public_id, "review"
    )
    ws.content[node.secret] = render_review_result(review)
    return ws.content[root.secret]


@dataclass
class World:
    tsa: TsaWorkspace
    req: object


def build_world(scenario: Scenario) -> tuple[World, dict[str, str]]:
    """A synthetic Project holding exactly this scenario's Applied Requirements.

    The Project bootstrap Architecture is created by the real I04/I05 start;
    the Requirement side holds the fixture's own Applied Requirement too, which
    no scenario selects.
    """
    req, _, _, _ = build_apply_workspace()
    from sdlc.requirement_apply import apply_standard_requirement
    from standard_fake import REQUIREMENT_ID as DEFAULT_REQUIREMENT

    applied = next(
        r for r in req.requirements.values() if r.requirement_id == DEFAULT_REQUIREMENT
    )
    result = apply_standard_requirement(req, applied.id)
    assert result.code.value == "REQUIREMENT_APPLIED", result
    trees = {}
    for index, item in enumerate(scenario.requirements, start=1):
        public_id = f"{scenario.scenario_id[1:]}{index:02d}"
        trees[item.requirement_id] = add_requirement(req, item, public_id)
    req.calls.clear()
    tsa = TsaWorkspace()
    return World(tsa=tsa, req=req), trees


def context_of(cycle_id: str) -> BootstrapContext:
    from architecture_fake import PROJECT_TYPE_ID

    return BootstrapContext(
        workspace_identity=WORKSPACE,
        project_type_id=PROJECT_TYPE_ID,
        project_entity_id=PROJECT_ID,
        project_public_id=PUBLIC_ID,
        project_code=PROJECT_CODE,
        cycle_id=cycle_id,
    )


# ---------------------------------------------------------------------------
# The model boundary: a recorder around the real runtime, under one budget
# ---------------------------------------------------------------------------


class BudgetExhausted(Exception):
    pass


@dataclass
class Budget:
    limit: int
    used: int = 0

    def take(self) -> int:
        if self.used >= self.limit:
            raise BudgetExhausted(f"The inference budget of {self.limit} is spent.")
        self.used += 1
        return self.used


class DryRunStop(ModelRuntimeError):
    """The offline run stops at the model boundary, having seen the prompt."""


@dataclass
class Recorder:
    """Wraps one real runtime: records what is sent and what comes back."""

    role: str
    runtime: ModelRuntime | None
    budget: Budget
    calls: list[dict] = field(default_factory=list)

    def run(self, prompt: str, context: str = "") -> ModelResponse:
        record = {
            "role": self.role,
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "context_sha256": hashlib.sha256(context.encode()).hexdigest(),
            "prompt": prompt,
            "context": context,
        }
        self.calls.append(record)
        if self.runtime is None:
            record["outcome"] = "DRY_RUN_NOT_INVOKED"
            raise DryRunStop("Dry run: no model is invoked.")
        record["inference_call_number"] = self.budget.take()
        started = time.monotonic()
        record["started_utc"] = datetime.now(UTC).isoformat(timespec="seconds")
        try:
            response = self.runtime.run(prompt, context)
        except ModelRuntimeError as error:
            record["outcome"] = "RUNTIME_ERROR"
            record["error_type"] = type(error).__name__
            record["error_message"] = str(error)
            record["seconds"] = round(time.monotonic() - started, 1)
            raise
        record["outcome"] = "RESPONSE"
        record["seconds"] = round(time.monotonic() - started, 1)
        record["response_runtime"] = response.runtime
        record["response_model"] = response.model
        record["response_text"] = response.text
        return response


# ---------------------------------------------------------------------------
# One scenario: real I05 start, real I07 stage, real I08 stage
# ---------------------------------------------------------------------------


def refusal_record(error: Exception) -> dict:
    return {
        "code": str(getattr(error, "code", type(error).__name__)),
        "message": str(error),
        "details": list(getattr(error, "details", ())),
    }


def run_scenario(scenario: Scenario, live: bool, budget: Budget) -> dict:
    world, trees = build_world(scenario)
    context = context_of(scenario.cycle_id)
    selection = tuple(item.requirement_id for item in scenario.requirements)
    evidence: dict = {
        "scenario_id": scenario.scenario_id,
        "purpose": scenario.purpose,
        "matrix_rows": list(scenario.rows),
        "cycle_id": scenario.cycle_id,
        "requirements": [
            {
                "requirement_id": item.requirement_id,
                "title": item.title,
                "root_document_fingerprint": document_fingerprint(
                    trees[item.requirement_id]
                ),
                "root_document": trees[item.requirement_id],
            }
            for item in scenario.requirements
        ],
    }
    try:
        manifest = start_input_manifest(
            world.tsa,
            world.req,
            PROJECT_ID,
            scenario.cycle_id,
            StartInputs(selection, UxNotApplicable(UX_REASON), True, True),
            clock=fixed_clock,
        )
    except AdmissionRefused as error:
        evidence["admission"] = refusal_record(error)
        return evidence
    evidence["manifest_digest"] = manifest.artifact.body["manifest_digest"]
    architect = Recorder(
        TSA_ARCHITECT_ROLE, _runtime(TSA_ARCHITECT_ROLE) if live else None, budget
    )
    reviewer = Recorder(
        TSA_REVIEWER_ROLE, _runtime(TSA_REVIEWER_ROLE) if live else None, budget
    )
    evidence["calls"] = []
    try:
        stage = run_architect_stage(
            world.tsa,
            world.req,
            architect,
            PROJECT_ID,
            scenario.cycle_id,
            clock=fixed_clock,
        )
    except ArchitectRefused as error:
        evidence["calls"] += architect.calls
        evidence["architect_stage"] = refusal_record(error)
        evidence["reviewer_stage"] = "NOT_RUN: no valid applied Architect output"
        return evidence
    evidence["calls"] += architect.calls
    evidence["architect_stage"] = {
        "outcome": str(stage.outcome),
        "process_result_digest": stage.process_result_digest,
        "output_fingerprint": stage.output_fingerprint,
        "model_invoked": stage.model_invoked,
    }
    process_id = _child_document_id(context, DocumentKind.PROCESS_RESULT)
    process = extract_artifact_payload(world.tsa.content_of(process_id))
    evidence["process_intended_output"] = process["body"]["intended_output"]
    evidence["architecture_document"] = world.tsa.content_of(
        context.architecture_document_id
    )
    try:
        review = run_reviewer_stage(
            world.tsa,
            world.req,
            reviewer,
            PROJECT_ID,
            scenario.cycle_id,
            clock=fixed_clock,
        )
    except ReviewerRefused as error:
        evidence["calls"] += reviewer.calls
        evidence["reviewer_stage"] = refusal_record(error)
        return evidence
    evidence["calls"] += reviewer.calls
    review_id = _child_document_id(context, DocumentKind.REVIEW_RESULT)
    payload = extract_artifact_payload(world.tsa.content_of(review_id))
    evidence["reviewer_stage"] = {
        "outcome": str(review.outcome),
        "derived_status": review.derived_status,
        "coverage_defects": list(review.coverage_defects),
        "review_result_digest": review.review_result_digest,
    }
    evidence["reviewer_response"] = payload["body"]["reviewer_response"]
    return evidence


def _child_document_id(context: BootstrapContext, kind: DocumentKind) -> str:
    from sdlc.tsa_cycle import derive_document_id

    return derive_document_id(
        context.workspace_identity,
        context.project_entity_id,
        context.cycle_id,
        kind,
        1,
    )


def _runtime(role: str) -> LocalCliModelRuntime:
    return LocalCliModelRuntime(select_runtime(load_model_runtime_config(), role))


# ---------------------------------------------------------------------------
# Runtime classification without inference
# ---------------------------------------------------------------------------


def runtime_classification() -> dict:
    """The roles' selection and the runtime's own sanitized login summary."""
    config = load_model_runtime_config()
    roles = {}
    for role in (TSA_ARCHITECT_ROLE, TSA_REVIEWER_ROLE):
        selection = select_runtime(config, role)
        runtime = LocalCliModelRuntime(selection)
        try:
            summary = runtime.preflight()
        except ModelRuntimeError as error:
            summary = f"PREFLIGHT_FAILED: {error}"
        roles[role] = {
            "runtime": selection.definition.name,
            "invocation_mode": selection.definition.invocation_mode,
            "model": selection.model or "local CLI default model (none configured)",
            "preflight": summary,
        }
    executable = shutil.which("claude")
    version = None
    if executable:
        completed = subprocess.run(
            [executable, "--version"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        version = completed.stdout.strip().splitlines()[0] if completed.stdout else None
    return {"roles": roles, "claude_cli_version": version}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def repository_sha() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPOSITORY,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.stdout.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--live", action="store_true")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--only", nargs="*", default=None)
    arguments = parser.parse_args(argv)
    arguments.out.mkdir(parents=True, exist_ok=True)
    budget = Budget(INFERENCE_BUDGET)
    header = {
        "repository_sha": repository_sha(),
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "mode": "live" if arguments.live else "dry-run",
        "started_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "environment": "synthetic only: in-memory Fibery fakes, no Fibery API",
    }
    if arguments.live:
        header["runtime"] = runtime_classification()
    chosen = [
        scenario
        for scenario in SCENARIOS
        if arguments.only is None or scenario.scenario_id in arguments.only
    ]
    for scenario in chosen:
        try:
            evidence = run_scenario(scenario, arguments.live, budget)
        except BudgetExhausted as error:
            evidence = {"scenario_id": scenario.scenario_id, "blocked": str(error)}
        evidence["header"] = header
        target = arguments.out / f"{header['mode']}-{scenario.scenario_id}.json"
        target.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
        calls = evidence.get("calls", [])
        print(
            f"{scenario.scenario_id}: admission "
            f"{evidence.get('admission', {}).get('code', 'OK')}; architect "
            f"{_brief(evidence.get('architect_stage'))}; reviewer "
            f"{_brief(evidence.get('reviewer_stage'))}; calls {len(calls)}"
        )
    header["finished_utc"] = datetime.now(UTC).isoformat(timespec="seconds")
    header["inference_calls_used"] = budget.used
    (arguments.out / f"{header['mode']}-run.json").write_text(
        json.dumps(header, indent=2, sort_keys=True) + "\n"
    )
    print(f"inference calls used: {budget.used} of {INFERENCE_BUDGET}")
    return 0


def _brief(stage) -> str:
    if stage is None:
        return "-"
    if isinstance(stage, str):
        return stage
    return stage.get("code") or stage.get("derived_status") or stage.get("outcome")


if __name__ == "__main__":
    raise SystemExit(main())
