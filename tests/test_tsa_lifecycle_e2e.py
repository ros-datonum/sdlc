"""I13 — the TSA-C01 cycle end to end, through the real `sdlc` command line.

Every step is `cli.main([...])` with real arguments, and everything below it
is production code: the I12 command orchestration and result mapping, the I04
discovery and bootstrap, I05 admission and the Input Manifest, the I06
renderer, the I07 Architect and I08 Reviewer stages with their real prompt
builders, I10 recovery and the I11 Human Decision. Only the external
boundaries are replaced:

- Fibery, by the in-memory workspaces the domain suites use, which keep their
  durable state across CLI invocations within one scenario;
- the two model runtimes, by role-aware fakes built afresh for every
  invocation (a process restart) that record the prompts I07/I08 assemble;
- the clock, by a fixed, counting one;
- transport failures, injected at the workspace boundary.

The three adapters reach the engine through a recording pass-through, so the
zero-downstream-side-effect row (contract 16 row 35) is asserted on the
journal of what the engine actually called, never on source text.

Everything here is D-class. The live gates stay open: I-2 (replacement and
deletion), I-3 (large writes), the F lines of rows 1, 22 and 23, and every M
line (I14).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from architect_fake import (
    TRACE_MODEL_CALL,
    architect_response,
    payload_of,
    process_id,
    reset_trace,
    response_text,
)
from architecture_fake import PROJECT_TYPE_ID
from reviewer_fake import (
    claims,
    decision_id,
    finding,
    review_id,
    reviewer_response,
    verification,
)
from sdlc import cli
from sdlc.config import ENV_HOST, ENV_SPACE, ENV_TOKEN
from sdlc.fibery_workspace import FiberyError, ProjectRecord
from sdlc.model_runtime import ModelResponse, ModelRuntimeError
from sdlc.model_runtime_config import TSA_ARCHITECT_ROLE, TSA_REVIEWER_ROLE
from sdlc.normative_tree import document_fingerprint
from sdlc.tsa_architecture import render_architecture
from sdlc.tsa_artifacts import (
    extract_architecture_envelope,
    ux_evidence_digest,
    validate_artifact,
)
from sdlc.tsa_cycle import DocumentKind, derive_document_id
from sdlc.worker_runner_guard import hold_workspace
from standard_fake import REQUIREMENT_ID
from test_tsa_admission import (
    ARCHITECTURE_ID,
    CONTEXT,
    CYCLE,
    MANIFEST_ID,
    PROJECT_CODE,
    PROJECT_ID,
    PUBLIC_ID,
    SECOND_ID,
    UX_CONTENT,
    UX_DOCUMENT_ID,
    UX_REASON,
    add_applied_requirement,
    root_edited_after_review,
    world,
)
from test_tsa_architect import other_architecture, other_process_carrier, reseal
from test_tsa_decision import material_what, product_question

ENVIRONMENT = {
    ENV_HOST: "example.fibery.io",
    ENV_TOKEN: "e2e-secret-token",
    ENV_SPACE: "SDLC",
}
PROJECT = ProjectRecord(
    id=PROJECT_ID, name="SDLC", code=PROJECT_CODE, state="Planned", public_id=PUBLIC_ID
)
CREATE_ROOT = "create_project_document"
CREATE = "create_tsa_child_document"
WRITE = "write_document_content"
FIRST_INSTANT = datetime(2026, 10, 15, 9, 0, 0, tzinfo=UTC)

#: The only mutating calls the engine may make, on the TSA side only.
TSA_MUTATIONS = frozenset({CREATE_ROOT, CREATE, WRITE})
#: Everything else the TSA engine may call on the Architecture workspace.
TSA_READS = frozenset(
    {
        "lock_scope",
        "project_type_id",
        "read_project",
        "resolve_placement",
        "resolve_document",
        "documents_attached_to_project",
        "child_documents",
        "child_placements",
        "read_document_content",
    }
)
#: The Requirement side is evidence: the engine may only read it.
REQUIREMENT_READS = frozenset(
    {
        "find_requirements_by_requirement_id",
        "read_requirement",
        "documents_attached_to_requirement",
        "child_documents",
        "read_document_content",
        "resolve_document",
    }
)
PROJECT_READS = frozenset({"find_project_by_code"})


def tsa_ids(iterations: int = 4) -> frozenset[str]:
    """Every deterministic TSA Document id this cycle may ever own."""
    ids = {ARCHITECTURE_ID, MANIFEST_ID}
    for iteration in range(1, iterations + 1):
        for kind in (
            DocumentKind.PROCESS_RESULT,
            DocumentKind.REVIEW_RESULT,
            DocumentKind.HUMAN_DECISION,
        ):
            ids.add(
                derive_document_id(
                    CONTEXT.workspace_identity, PROJECT_ID, CYCLE, kind, iteration
                )
            )
    return frozenset(ids)


# --------------------------------------------------------------------------
# The external boundaries: recorded adapters, role-aware models, a clock
# --------------------------------------------------------------------------


class Recorded:
    """A pass-through over one fake adapter that journals every engine call."""

    def __init__(self, target: object, side: str, journal: list) -> None:
        self._target = target
        self._side = side
        self._journal = journal

    def __getattr__(self, name: str):
        value = getattr(self._target, name)
        if not callable(value):
            self._journal.append((self._side, name, ()))
            return value

        def call(*args, **kwargs):
            self._journal.append((self._side, name, args))
            return value(*args, **kwargs)

        return call


@dataclass
class ModelCall:
    role: str
    prompt: str
    context: str

    @property
    def text(self) -> str:
        return f"{self.prompt}\n{self.context}"


def current_process_iteration(scene) -> int:
    """The highest iteration whose Process Result holds an artifact now."""
    iteration = 1
    while process_id(iteration + 1) in scene.tsa.documents:
        iteration += 1
    return iteration


@dataclass
class Models:
    """The two TSA roles, answering from durable state at call time.

    `architect` lists raw Architect responses, used in order, then the default
    valid response. The Reviewer covers every claim of the Process Result that
    is durable when it is called, changed by `review_changes`. `errors` and
    `during` are one-shot, per role.
    """

    scene: object
    architect: list[str] = field(default_factory=list)
    review_changes: Callable[[object, int], dict] | None = None
    errors: dict[str, Exception] = field(default_factory=dict)
    during: dict[str, Callable[[], None]] = field(default_factory=dict)
    calls: list[ModelCall] = field(default_factory=list)

    def count(self, role: str) -> int:
        return sum(1 for call in self.calls if call.role == role)

    @property
    def counts(self) -> tuple[int, int]:
        return self.count(TSA_ARCHITECT_ROLE), self.count(TSA_REVIEWER_ROLE)


class RoleRuntime:
    """One configured role for one CLI invocation; a restart builds a new one."""

    def __init__(self, models: Models, role: str) -> None:
        self.models = models
        self.role = role

    def run(self, prompt: str, context: str = "") -> ModelResponse:
        models = self.models
        scene = models.scene
        scene.tsa.log.append((TRACE_MODEL_CALL, self.role))
        models.calls.append(ModelCall(self.role, prompt, context))
        if self.role in models.during:
            models.during.pop(self.role)()
        if self.role in models.errors:
            raise models.errors.pop(self.role)
        if self.role == TSA_ARCHITECT_ROLE:
            text = models.architect.pop(0) if models.architect else response_text()
        else:
            iteration = current_process_iteration(scene)
            changes = (
                {}
                if models.review_changes is None
                else models.review_changes(scene, iteration)
            )
            text = json.dumps(reviewer_response(scene, iteration, **changes))
        return ModelResponse(text=text, runtime="fake", model=None)


class Clock:
    """A fixed, strictly increasing clock that counts its reads."""

    def __init__(self) -> None:
        self.reads = 0

    def __call__(self) -> datetime:
        self.reads += 1
        return FIRST_INSTANT + timedelta(seconds=self.reads)


class Projects:
    def find_project_by_code(self, code: str) -> ProjectRecord | None:
        return PROJECT if code == PROJECT_CODE else None


@dataclass
class Run:
    exit_code: int
    out: str
    err: str

    @property
    def stream(self) -> str:
        return self.out if self.exit_code == 0 else self.err

    @property
    def code(self) -> str:
        return self.stream.splitlines()[0]


@dataclass
class Lifecycle:
    """One synthetic Project and its Fibery state across many invocations."""

    scene: object
    models: Models
    clock: Clock
    capsys: pytest.CaptureFixture[str]
    journal: list = field(default_factory=list)
    roles_built: list[str] = field(default_factory=list)

    def __call__(self, *argv: str) -> Run:
        exit_code = cli.main(["project", "architecture", *argv])
        captured = self.capsys.readouterr()
        return Run(exit_code, captured.out, captured.err)

    def runtime(self, selection) -> RoleRuntime:
        """The model factory: a role is built only when the engine resolves it."""
        self.roles_built.append(selection.role)
        return RoleRuntime(self.models, selection.role)

    def workspaces(self, settings):
        return (
            Recorded(Projects(), "projects", self.journal),
            Recorded(self.scene.tsa, "tsa", self.journal),
            Recorded(self.scene.req, "req", self.journal),
        )

    def mutations(self) -> list[tuple[str, tuple]]:
        return [
            (name, args)
            for side, name, args in self.journal
            if side == "tsa" and name in TSA_MUTATIONS
        ]

    def mark(self) -> int:
        return len(self.journal)

    def mutations_since(self, mark: int) -> list[tuple[str, tuple]]:
        return [
            (name, args)
            for side, name, args in self.journal[mark:]
            if side == "tsa" and name in TSA_MUTATIONS
        ]


def base_scene():
    """A Project with one selected Applied Requirement and one unselected."""
    scene = world("absent")
    add_applied_requirement(scene.req, SECOND_ID)
    reset_trace(scene)
    return scene


@pytest.fixture
def lifecycle(monkeypatch, capsys):
    """The real CLI over one scene; row 35 is asserted when the scenario ends."""
    built: list[Lifecycle] = []

    def make(scene=None) -> Lifecycle:
        scene = base_scene() if scene is None else scene
        clock = Clock()
        cycle = Lifecycle(scene, Models(scene), clock, capsys)
        for name, value in ENVIRONMENT.items():
            monkeypatch.setenv(name, value)
        monkeypatch.setattr(cli, "_architecture_workspaces", cycle.workspaces)
        monkeypatch.setattr(cli, "_tsa_clock", clock)
        monkeypatch.setattr(cli, "LocalCliModelRuntime", cycle.runtime)
        built.append(cycle)
        return cycle

    yield make
    for cycle in built:
        assert_zero_downstream_effects(cycle)


# --------------------------------------------------------------------------
# Row 35: zero downstream side effects, on the real call journal
# --------------------------------------------------------------------------


def assert_zero_downstream_effects(cycle: Lifecycle) -> None:
    """Only TSA Documents of this cycle were created or written; nothing else.

    No Epic, Story, Task or Milestone create; no Requirement content, State
    or relation write; no Project State or Phase change; no Document outside
    the cycle. The Requirement side and the Project lookup were only read.
    """
    allowed_ids = tsa_ids()
    for side, name, args in cycle.journal:
        if side == "req":
            assert name in REQUIREMENT_READS, f"Requirement side called {name}"
        elif side == "projects":
            assert name in PROJECT_READS, f"Project side called {name}"
        else:
            assert name in TSA_READS | TSA_MUTATIONS, f"TSA side called {name}"
            if name in (CREATE_ROOT, CREATE):
                assert args[0] in allowed_ids, f"created a foreign Document {args}"
            if name == WRITE:
                secrets = {
                    cycle.scene.tsa.documents[document_id].secret
                    for document_id in allowed_ids
                    if document_id in cycle.scene.tsa.documents
                }
                assert args[0] in secrets, "wrote a Document outside the cycle"
    assert cycle.scene.tsa.projects[PROJECT_ID] == PROJECT_RECORD_AT_START


PROJECT_RECORD_AT_START = ProjectRecord(
    id=PROJECT_ID, name="SDLC", code=PROJECT_CODE, state="Planned", public_id=PUBLIC_ID
)


# --------------------------------------------------------------------------
# Arguments and small readers
# --------------------------------------------------------------------------


def selector(*extra: str) -> list[str]:
    return ["--project", PROJECT_CODE, "--cycle", CYCLE, *extra]


def start_argv(*ux: str) -> list[str]:
    branch = list(ux) or ["--ux", "not-applicable", "--ux-reason", UX_REASON]
    return [
        "start",
        *selector("--requirement", REQUIREMENT_ID),
        *branch,
        "--accept-inputs",
        "--accept-ux",
    ]


APPLICABLE_ARGV = (
    "--ux",
    "applicable",
    "--ux-document",
    UX_DOCUMENT_ID,
    "--ux-scope",
    REQUIREMENT_ID,
)
RESUME = ["resume", *selector()]
INSPECT = ["inspect", *selector()]


def decision_argv(command: str, iteration: int = 1, *extra: str) -> list[str]:
    argv = [
        command,
        *selector(
            "--iteration", str(iteration), "--review-result-id", review_id(iteration)
        ),
        *extra,
    ]
    return [*argv, "--confirm"] if command == "approve" else argv


def json_of(run: Run) -> dict:
    first, blank, body = run.stream.split("\n", 2)
    assert (first, blank) == (run.code, "")
    return json.loads(body)


def artifact(scene, document_id: str) -> dict:
    payload = payload_of(scene, document_id)
    validate_artifact(payload)
    return payload


def assert_result(run: Run, code: str, exit_code: int) -> None:
    assert run.exit_code == exit_code, run.stream
    assert run.code == code, run.stream
    assert run.stream.splitlines()[1] == ""
    assert (run.err if exit_code == 0 else run.out) == ""
    assert ENVIRONMENT[ENV_TOKEN] not in run.out + run.err


def ux_reads(cycle: Lifecycle) -> list:
    """Every engine operation that named the UX Document or its secret."""
    targets = {UX_DOCUMENT_ID, cycle.scene.tsa.documents[UX_DOCUMENT_ID].secret}
    return [
        entry
        for entry in cycle.journal
        if any(
            argument in targets for argument in entry[2] if isinstance(argument, str)
        )
    ]


def started(cycle: Lifecycle, *ux: str) -> Run:
    run = cycle(*start_argv(*ux))
    assert_result(run, "ARCHITECTURE_CYCLE_STARTED", 0)
    return run


# --------------------------------------------------------------------------
# A. Row 1: the complete approval cycle, NOT_APPLICABLE UX
# --------------------------------------------------------------------------


def test_row_1_start_inspect_approve_resume_and_every_retry(lifecycle):
    cycle = lifecycle()
    scene = cycle.scene

    # A — start: bootstrap, Manifest, Architect, Reviewer, then the boundary.
    run = started(cycle)
    assert cycle.models.counts == (1, 1)
    assert [name for name, _ in cycle.mutations()] == [
        CREATE_ROOT,
        WRITE,
        CREATE,
        WRITE,
        CREATE,
        WRITE,
        WRITE,
        CREATE,
        WRITE,
    ]
    created = [args[0] for name, args in cycle.mutations() if name != WRITE]
    assert created == [ARCHITECTURE_ID, MANIFEST_ID, process_id(1), review_id(1)]
    assert decision_id(1) not in scene.tsa.documents, "no Decision before a human"
    lineage_is_exact(scene, iteration=1)
    assert f"Review Result: {review_id(1)}" in run.out

    # B — inspect: read-only, model-free, current, per input.
    mark = cycle.mark()
    human = cycle(*INSPECT)
    record = json_of(cycle(*INSPECT, "--json"))
    assert_result(human, "INSPECT_CURRENT", 0)
    assert cycle.mutations_since(mark) == [] and cycle.models.counts == (1, 1)
    assert record["code"] == "INSPECT_CURRENT"
    assert (record["project_id"], record["project_code"], record["cycle_id"]) == (
        PROJECT_ID,
        PROJECT_CODE,
        CYCLE,
    )
    assert record["case"] == "REVIEW_RECORDED" and record["iteration"] == 1
    assert record["review_result"]["document_id"] == review_id(1)
    assert (
        record["review_result"]["digest"]
        == artifact(scene, review_id(1))["artifact_digest"]
    )
    assert record["inputs"] == {
        "status": "CURRENT",
        "requirements": [{"requirement_id": REQUIREMENT_ID, "current": True}],
        "ux": {"kind": "NOT_APPLICABLE", "current": True},
        "selection_refusal": None,
    }

    # C — approve: one immutable APPROVE, read back, model-free.
    mark = cycle.mark()
    reads_before = cycle.clock.reads
    roles_before = list(cycle.roles_built)
    approve = cycle(*decision_argv("approve"))
    assert_result(approve, "ARCHITECTURE_APPROVED", 0)
    assert cycle.roles_built == roles_before, "no TSA role is even constructed"
    assert [name for name, _ in cycle.mutations_since(mark)] == [CREATE, WRITE]
    assert cycle.models.counts == (1, 1), "APPROVE invokes no model"
    assert cycle.clock.reads == reads_before + 1, "recorded_at read once"
    decision = approve_binds_the_exact_tuple(scene)

    # D — inspect after approval: the approved lifecycle, still current.
    record = json_of(cycle(*INSPECT, "--json"))
    assert record["code"] == "INSPECT_CURRENT" and record["case"] == "APPROVED"
    assert record["human_decision"]["decision"] == "APPROVE"

    # E — resume on the approved cycle (row 47): read-only.
    mark = cycle.mark()
    assert_result(cycle(*RESUME), "CYCLE_APPROVED", 0)
    assert cycle.mutations_since(mark) == [] and cycle.models.counts == (1, 1)

    # F — repeat approve: idempotent, the Decision untouched.
    stored = scene.tsa.content_of(decision_id(1))
    reads_before = cycle.clock.reads
    mark = cycle.mark()
    again = cycle(*decision_argv("approve"))
    assert_result(again, "DECISION_ALREADY_RECORDED", 0)
    assert cycle.mutations_since(mark) == [] and cycle.clock.reads == reads_before
    assert scene.tsa.content_of(decision_id(1)) == stored
    assert f"recorded at {decision['body']['recorded_at']}" in again.out

    # G — repeat start, same inputs: the approved cycle stays authoritative.
    mark = cycle.mark()
    assert_result(cycle(*start_argv()), "CYCLE_APPROVED", 0)
    assert cycle.mutations_since(mark) == [] and cycle.models.counts == (1, 1)
    assert scene.tsa.content_of(decision_id(1)) == stored


def lineage_is_exact(scene, iteration: int) -> None:
    """I01 envelopes and digests, placements, and every cross-artifact binding."""
    root = scene.tsa.documents[ARCHITECTURE_ID]
    assert (root.container_entity_type, root.container_entity_id) == (
        PROJECT_TYPE_ID,
        PUBLIC_ID,
    )
    for document_id in (MANIFEST_ID, process_id(iteration), review_id(iteration)):
        assert scene.tsa.documents[document_id].parent_document_id == ARCHITECTURE_ID
    manifest = artifact(scene, MANIFEST_ID)
    process = artifact(scene, process_id(iteration))
    review = artifact(scene, review_id(iteration))
    envelope = extract_architecture_envelope(scene.tsa.content_of(ARCHITECTURE_ID))
    assert (
        manifest["body"]["acceptance"]["manifest_digest"]
        == (manifest["body"]["manifest_digest"])
    )
    assert process["body"]["manifest_digest"] == manifest["body"]["manifest_digest"]
    assert review["body"]["manifest_digest"] == manifest["body"]["manifest_digest"]
    assert review["body"]["process_result_digest"] == process["artifact_digest"]
    assert (
        review["body"]["architecture_fingerprint"]
        == (envelope["body"]["content_fingerprint"])
    )
    assert review["body"]["process_result_document_id"] == process_id(iteration)
    assert envelope["body"]["manifest_digest"] == manifest["body"]["manifest_digest"]
    assert envelope["body"]["current_iteration"] == iteration
    for child in (process, review):
        assert child["body"]["architecture_document_id"] == ARCHITECTURE_ID
        assert child["iteration"] == iteration
    assert review["body"]["derived_status"] == "REVIEW_PASS"
    requirements = manifest["body"]["manifest_body"]["requirements"]
    assert [row["requirement_id"] for row in requirements] == [REQUIREMENT_ID]


#: The closed `tsa.human_decision` body of I01 (4.6.5), without the optional
#: `reason` no command here supplies. No field names an approver.
DECISION_BODY_KEYS = frozenset(
    {
        "accepted_dispositions",
        "architecture_document_id",
        "architecture_fingerprint",
        "decision",
        "manifest_digest",
        "process_result",
        "recorded_at",
        "review_result",
        "target",
        "ux_evidence_digest",
    }
)


def approve_binds_the_exact_tuple(scene, iteration: int = 1) -> dict:
    decision = artifact(scene, decision_id(iteration))
    manifest = artifact(scene, MANIFEST_ID)
    process = artifact(scene, process_id(iteration))
    review = artifact(scene, review_id(iteration))
    envelope = extract_architecture_envelope(scene.tsa.content_of(ARCHITECTURE_ID))
    body = decision["body"]
    assert body["decision"] == "APPROVE"
    assert body["target"] == {
        "iteration": iteration,
        "review_result_document_id": review_id(iteration),
        "review_result_digest": review["artifact_digest"],
    }
    assert body["process_result"] == {
        "document_id": process_id(iteration),
        "payload_digest": process["artifact_digest"],
    }
    assert body["review_result"]["document_id"] == review_id(iteration)
    assert body["review_result"]["payload_digest"] == review["artifact_digest"]
    assert body["architecture_document_id"] == ARCHITECTURE_ID
    assert body["architecture_fingerprint"] == envelope["body"]["content_fingerprint"]
    assert body["manifest_digest"] == manifest["body"]["manifest_digest"]
    assert body["ux_evidence_digest"] == ux_evidence_digest(
        manifest["body"]["manifest_body"]["ux"]
    )
    assert set(body) == DECISION_BODY_KEYS, "the frozen schema; no approver"
    return decision


def test_operation_order_puts_every_model_call_inside_its_stage(lifecycle):
    """Bootstrap, Manifest, Architect, Process, apply, Reviewer, Review."""
    cycle = lifecycle()
    started(cycle)

    trace = [
        name if name != TRACE_MODEL_CALL else f"model:{argument}"
        for name, argument in cycle.scene.tsa.log
        if name in TSA_MUTATIONS or name == TRACE_MODEL_CALL
    ]
    assert trace == [
        CREATE_ROOT,
        WRITE,
        CREATE,
        WRITE,
        f"model:{TSA_ARCHITECT_ROLE}",
        CREATE,
        WRITE,
        WRITE,
        f"model:{TSA_REVIEWER_ROLE}",
        CREATE,
        WRITE,
    ]


# --------------------------------------------------------------------------
# B. Prompt and authority boundaries (spec 16)
# --------------------------------------------------------------------------


def test_prompts_carry_only_the_selected_inputs(lifecycle):
    cycle = lifecycle()
    started(cycle)
    architect, reviewer = cycle.models.calls
    selected_tree = cycle.scene.req.content[cycle.scene.root.secret]

    for call in (architect, reviewer):
        assert REQUIREMENT_ID in call.text
        assert any(line in call.text for line in selected_tree.splitlines() if line)
        assert SECOND_ID not in call.text, "an unselected Requirement leaked"
        assert UX_CONTENT.splitlines()[0] not in call.text, "no UX under N/A"
    applied = "A runtime gate in front of every model call."
    assert applied in reviewer.text, "the Reviewer reviews the applied Architecture"
    assert applied not in architect.text, "the Architect saw only the bootstrap"
    assert ux_reads(cycle) == [], "NOT_APPLICABLE reads no UX Document"


def test_the_reviewer_of_n_plus_1_never_sees_the_previous_review(lifecycle):
    cycle = lifecycle()
    started(cycle)
    first_review = artifact(cycle.scene, review_id(1))

    assert_result(cycle(*decision_argv("rework")), "ARCHITECTURE_REWORK_RECORDED", 0)

    second = [c for c in cycle.models.calls if c.role == TSA_REVIEWER_ROLE][1]
    assert first_review["artifact_digest"] not in second.text
    assert review_id(1) not in second.text
    assert decision_id(1) not in second.text


# --------------------------------------------------------------------------
# C. UX APPLICABLE end to end
# --------------------------------------------------------------------------


def test_an_applicable_ux_cycle_binds_its_document_and_approves(lifecycle):
    cycle = lifecycle()
    scene = cycle.scene

    started(cycle, *APPLICABLE_ARGV)
    approve = cycle(*decision_argv("approve"))

    assert_result(approve, "ARCHITECTURE_APPROVED", 0)
    ux = artifact(scene, MANIFEST_ID)["body"]["manifest_body"]["ux"]
    assert ux["kind"] == "APPLICABLE"
    assert ux["document_id"] == UX_DOCUMENT_ID
    assert ux["scope_requirement_ids"] == [REQUIREMENT_ID]
    assert ux["content_digest"] == document_fingerprint(UX_CONTENT)
    assert ux["approval"]["recorded_at"], "the explicit --accept-ux record"
    for call in cycle.models.calls:
        assert "The user confirms the order on one screen." in call.text
    approve_binds_the_exact_tuple(scene)
    record = json_of(cycle(*INSPECT, "--json"))
    assert record["inputs"]["ux"] == {
        "kind": "APPLICABLE",
        "document_id": UX_DOCUMENT_ID,
        "current": True,
    }


# --------------------------------------------------------------------------
# D. REWORK: N -> N+1 on the same Manifest, then approval of N+1
# --------------------------------------------------------------------------


def test_rework_opens_n_plus_1_and_keeps_every_earlier_artifact(lifecycle):
    cycle = lifecycle()
    scene = cycle.scene
    started(cycle)
    first = {
        document_id: scene.tsa.content_of(document_id)
        for document_id in (MANIFEST_ID, process_id(1), review_id(1))
    }

    rework = cycle(*decision_argv("rework", 1, "--reason", "Split the gate."))

    assert_result(rework, "ARCHITECTURE_REWORK_RECORDED", 0)
    assert artifact(scene, decision_id(1))["body"]["decision"] == "REWORK"
    assert {d: scene.tsa.content_of(d) for d in first} == first, "history intact"
    assert cycle.models.counts == (2, 2)
    lineage_is_exact(scene, iteration=2)
    assert {process_id(2), review_id(2)} <= set(scene.tsa.documents)
    assert decision_id(2) not in scene.tsa.documents, "no automatic approval"
    events = semantic_events(scene)
    decision_written = events.index(f"write:{decision_id(1)}")
    decision_read_back = events.index(f"read:{decision_id(1)}", decision_written)
    models_before = [e for e in events[:decision_written] if e.startswith("model:")]
    models_after = [e for e in events[decision_written:] if e.startswith("model:")]
    assert models_before == [
        f"model:{TSA_ARCHITECT_ROLE}",
        f"model:{TSA_REVIEWER_ROLE}",
    ], "iteration 1 only, before the REWORK"
    assert models_after == models_before, "iteration 2 only after the REWORK"
    first_after = events.index(models_after[0], decision_written)
    assert events.index(f"create:{decision_id(1)}") < decision_written
    assert decision_read_back < first_after, "durable and read back before N+1"
    assert events.index(f"create:{process_id(2)}") > first_after

    approve = cycle(*decision_argv("approve", 2))
    assert_result(approve, "ARCHITECTURE_APPROVED", 0)
    approve_binds_the_exact_tuple(scene, iteration=2)

    reads_before = cycle.clock.reads
    mark = cycle.mark()
    retry = cycle(*decision_argv("rework", 1))
    assert_result(retry, "DECISION_ALREADY_RECORDED", 0)
    assert cycle.mutations_since(mark) == []
    assert cycle.models.counts == (2, 2) and cycle.clock.reads == reads_before
    assert process_id(3) not in scene.tsa.documents


def semantic_events(scene) -> list[str]:
    """Model calls and TSA operations, named by role or by Document id."""
    by_secret = {
        document.secret: document_id
        for document_id, document in scene.tsa.documents.items()
    }
    events = []
    for name, argument in scene.tsa.log:
        if name == TRACE_MODEL_CALL:
            events.append(f"model:{argument}")
        elif name in (CREATE_ROOT, CREATE):
            events.append(f"create:{argument}")
        elif name == WRITE:
            events.append(f"write:{by_secret[argument]}")
        elif name == "read_document_content" and argument in by_secret:
            events.append(f"read:{by_secret[argument]}")
    return events


def test_approve_after_rework_on_the_same_target_is_a_conflict(lifecycle):
    cycle = lifecycle()
    started(cycle)
    assert_result(cycle(*decision_argv("rework")), "ARCHITECTURE_REWORK_RECORDED", 0)
    stored = cycle.scene.tsa.content_of(decision_id(1))
    history = {
        d: cycle.scene.tsa.content_of(d)
        for d in (process_id(1), review_id(1), process_id(2), review_id(2))
    }
    counts = cycle.models.counts
    mark = cycle.mark()

    run = cycle(*decision_argv("approve", 1))

    assert_result(run, "DECISION_CONFLICT", 1)
    assert cycle.mutations_since(mark) == [] and cycle.models.counts == counts
    assert cycle.scene.tsa.content_of(decision_id(1)) == stored, "no rewrite"
    assert artifact(cycle.scene, decision_id(1))["body"]["decision"] == "REWORK"
    assert {d: cycle.scene.tsa.content_of(d) for d in history} == history


def test_rework_after_approve_is_a_conflict_and_the_cycle_stays_closed(lifecycle):
    cycle = lifecycle()
    started(cycle)
    assert_result(cycle(*decision_argv("approve")), "ARCHITECTURE_APPROVED", 0)
    mark = cycle.mark()

    assert_result(cycle(*decision_argv("rework")), "DECISION_CONFLICT", 1)
    assert cycle.mutations_since(mark) == [] and cycle.models.counts == (1, 1)


# --------------------------------------------------------------------------
# E. Recovery across separate invocations (one per durable transition)
# --------------------------------------------------------------------------


def creates(cycle: Lifecycle, document_id: str) -> int:
    return sum(
        1
        for name, args in cycle.mutations()
        if name in (CREATE_ROOT, CREATE) and args[0] == document_id
    )


def test_a_root_whose_carrier_was_never_written_is_completed_by_start(lifecycle):
    cycle = lifecycle()
    cycle.scene.tsa.before(WRITE, 1, fail_with("connection reset"))

    first = cycle(*start_argv())
    assert_result(first, "FIBERY_WRITE_FAILED", 1)
    assert cycle.scene.tsa.content_of(ARCHITECTURE_ID) == ""
    assert cycle.models.counts == (0, 0)

    started(cycle)
    assert creates(cycle, ARCHITECTURE_ID) == 1, "the same shell, in place"


def test_state_b_needs_start_and_resume_says_so(lifecycle):
    cycle = lifecycle(bootstrapped_scene())

    assert_result(cycle(*RESUME), "MANIFEST_INPUTS_REQUIRED", 1)
    started(cycle)
    assert creates(cycle, ARCHITECTURE_ID) == 0


def bootstrapped_scene():
    scene = world("bootstrapped")
    add_applied_requirement(scene.req, SECOND_ID)
    reset_trace(scene)
    return scene


def test_a_persisted_unapplied_process_is_replayed_without_the_architect(lifecycle):
    cycle = lifecycle()
    cycle.scene.tsa.before(WRITE, 4, fail_with("connection reset"))

    first = cycle(*start_argv())
    assert_result(first, "FIBERY_WRITE_FAILED", 1)
    artifact(cycle.scene, process_id(1))
    assert cycle.models.counts == (1, 0)

    resumed = cycle(*RESUME)
    assert_result(resumed, "ARCHITECTURE_CYCLE_RESUMED", 0)
    assert cycle.models.counts == (1, 1), "replayed, no second Architect call"
    assert creates(cycle, process_id(1)) == 1
    lineage_is_exact(cycle.scene, iteration=1)


def test_an_applied_output_without_a_review_resumes_with_the_reviewer(lifecycle):
    cycle = lifecycle()
    cycle.models.errors[TSA_REVIEWER_ROLE] = ModelRuntimeError("reviewer down")

    first = cycle(*start_argv())
    assert_result(first, "MODEL_RUNTIME_FAILED", 1)
    assert "This start wrote the cycle's accepted Input Manifest" in first.err
    assert f"Process Result '{process_id(1)}' of iteration 1 was persisted" in (
        first.err
    ), "the durable Process is stated positively"
    assert "was applied to the Architecture Document" in first.err
    assert "othing was persisted" not in first.err

    assert_result(cycle(*RESUME), "ARCHITECTURE_CYCLE_RESUMED", 0)
    assert cycle.models.counts == (1, 2)
    lineage_is_exact(cycle.scene, iteration=1)


def test_an_empty_review_shell_is_completed_in_place_by_resume(lifecycle):
    cycle = lifecycle()
    cycle.scene.tsa.before(WRITE, 5, fail_with("connection reset"))

    first = cycle(*start_argv())
    assert_result(first, "FIBERY_WRITE_FAILED", 1)
    assert (
        f"Review Result '{review_id(1)}' of iteration 1"
        not in first.err.split("The Human Decision")[0]
    ), "no Review is claimed before it was written"
    assert cycle.scene.tsa.content_of(review_id(1)) == ""
    assert cycle.models.counts == (1, 1)

    resumed = cycle(*RESUME)

    assert_result(resumed, "ARCHITECTURE_CYCLE_RESUMED", 0)
    assert "advanced to the Human Decision boundary of iteration 1" in resumed.out
    assert f"Review Result: {review_id(1)} (digest " in resumed.out
    assert "Reviewer stage: REVIEW_RECORDED, model invoked" in resumed.out
    assert creates(cycle, review_id(1)) == 1, "the shell, never a second Review"
    assert cycle.models.counts == (1, 2), "one Reviewer call, no Architect"
    lineage_is_exact(cycle.scene, iteration=1)
    record = json_of(cycle(*INSPECT, "--json"))
    assert (record["case"], record["review_result"]["document_id"]) == (
        "REVIEW_RECORDED",
        review_id(1),
    )


def test_a_valid_review_without_a_decision_is_re_presented_without_a_model(
    lifecycle,
):
    cycle = lifecycle()
    started(cycle)
    mark = cycle.mark()

    for argv in (RESUME, start_argv()):
        assert_result(cycle(*argv), "ARCHITECTURE_REVIEW_READY", 0)
    assert cycle.mutations_since(mark) == [] and cycle.models.counts == (1, 1)


def test_a_durable_rework_is_continued_by_a_later_resume(lifecycle):
    cycle = lifecycle()
    started(cycle)
    cycle.models.errors[TSA_ARCHITECT_ROLE] = ModelRuntimeError("architect down")

    rework = cycle(*decision_argv("rework"))
    assert_result(rework, "MODEL_RUNTIME_FAILED", 1)
    assert "REWORK of iteration 1 was recorded" in rework.err
    assert artifact(cycle.scene, decision_id(1))["body"]["decision"] == "REWORK"

    assert_result(cycle(*RESUME), "ARCHITECTURE_CYCLE_RESUMED", 0)
    assert cycle.models.counts == (3, 2)
    lineage_is_exact(cycle.scene, iteration=2)


# --------------------------------------------------------------------------
# F. Unknown transport outcomes: a lost response is not a lost write
# --------------------------------------------------------------------------


def fail_with(message: str):
    def effect() -> None:
        raise FiberyError(message)

    return effect


#: (call, occurrence) whose effect lands before the response is lost, during
#: one `start` from state A: the first create is the root, then the Manifest,
#: Process and Review children; writes are the carrier, Manifest, Process,
#: Architecture apply and Review.
LOST_IN_START = {
    "A-root-create": (CREATE_ROOT, 1),
    "B-manifest-write": (WRITE, 2),
    "D-architecture-apply": (WRITE, 4),
    "E-review-create": (CREATE, 3),
    "F-review-write": (WRITE, 5),
}


@pytest.mark.parametrize("window", LOST_IN_START)
def test_a_lost_response_during_start_is_rediscovered_never_redone(window, lifecycle):
    cycle = lifecycle()
    call, occurrence = LOST_IN_START[window]
    cycle.scene.tsa.after(call, occurrence, fail_with("response lost"))

    run = cycle(*start_argv())

    assert_result(run, "ARCHITECTURE_CYCLE_STARTED", 0)
    for document_id in (ARCHITECTURE_ID, MANIFEST_ID, process_id(1), review_id(1)):
        assert creates(cycle, document_id) == 1, f"{document_id} created twice"
    writes = [event for event in semantic_events(cycle.scene) if event[:6] == "write:"]
    assert writes == [
        f"write:{ARCHITECTURE_ID}",
        f"write:{MANIFEST_ID}",
        f"write:{process_id(1)}",
        f"write:{ARCHITECTURE_ID}",
        f"write:{review_id(1)}",
    ], "every body written once: a landed write is confirmed, never redone"
    assert cycle.models.counts == (1, 1), "no model call was retried"
    assert "othing was" not in run.out and "rolled back" not in run.out
    lineage_is_exact(cycle.scene, iteration=1)


def test_c_a_persisted_process_survives_a_later_failure_truthfully(lifecycle):
    cycle = lifecycle()
    cycle.scene.tsa.before(WRITE, 4, fail_with("connection reset"))

    run = cycle(*start_argv())

    assert_result(run, "FIBERY_WRITE_FAILED", 1)
    assert "This start wrote the cycle's accepted Input Manifest" in run.err
    assert "the Architecture still holds the recorded input" in run.err, (
        "I07's own mutation-aware diagnostic is kept"
    )
    assert "The Human Decision boundary was not reached." in run.err
    assert "othing was persisted" not in run.err
    artifact(cycle.scene, process_id(1))
    assert cycle.models.counts == (1, 0)


def test_g_a_landed_decision_create_is_an_unrecoverable_shell(lifecycle):
    """Frozen I11 window F: an empty Decision shell is never completed."""
    cycle = lifecycle()
    started(cycle)
    reset_trace(cycle.scene)
    cycle.scene.tsa.after(CREATE, 1, fail_with("response lost"))

    run = cycle(*decision_argv("approve"))

    assert_result(run, "DECISION_SHELL_UNRECOVERABLE", 1)
    assert creates(cycle, decision_id(1)) == 1, "never a second create"
    assert cycle.scene.tsa.content_of(decision_id(1)) == "", "left for a human"
    mark = cycle.mark()
    assert_result(cycle(*decision_argv("approve")), "DECISION_SHELL_UNRECOVERABLE", 1)
    assert cycle.mutations_since(mark) == [] and cycle.models.counts == (1, 1)
    assert json_of(cycle(*INSPECT, "--json"))["code"] == "INSPECT_CURRENT"


def test_h_a_landed_decision_write_is_confirmed_once(lifecycle):
    cycle = lifecycle()
    started(cycle)
    reset_trace(cycle.scene)
    cycle.scene.tsa.after(WRITE, 1, fail_with("response lost"))

    run = cycle(*decision_argv("approve"))

    assert_result(run, "ARCHITECTURE_APPROVED", 0)
    assert creates(cycle, decision_id(1)) == 1
    secret = cycle.scene.tsa.documents[decision_id(1)].secret
    writes = [args[0] for name, args in cycle.mutations() if name == WRITE]
    assert writes.count(secret) == 1, "never written twice"
    approve_binds_the_exact_tuple(cycle.scene)
    assert_result(cycle(*decision_argv("approve")), "DECISION_ALREADY_RECORDED", 0)


# --------------------------------------------------------------------------
# G. Staleness between commands (contract 4.4, 10)
# --------------------------------------------------------------------------


def edit_ux(scene) -> None:
    scene.tsa.set_content(UX_DOCUMENT_ID, "# Checkout flow\n\nTwo screens now.\n")


def edit_architecture(scene) -> None:
    scene.tsa.set_content(
        ARCHITECTURE_ID, other_architecture(scene, "Edited by hand.").text
    )


def process_of_another_manifest(scene) -> None:
    """A valid Process sealed under another Manifest: lineage invariant 2."""
    scene.tsa.set_content(process_id(1), other_process_carrier())


def review_binds_a_replaced_process(scene) -> None:
    """P2 for the same Manifest, cycle, iteration and output: invariant 3 only."""
    resealed_process(scene)


STALENESS = {
    "A-requirement-after-freeze": ((), root_edited_after_review, "INPUTS_STALE"),
    "B-applicable-ux-edited": (APPLICABLE_ARGV, edit_ux, "INPUTS_STALE"),
    "D-architecture-after-review": ((), edit_architecture, "ARCHITECTURE_DIVERGED"),
    "E-review-process-binding": (
        (),
        review_binds_a_replaced_process,
        ("ARTIFACT_MALFORMED"),
    ),
    "E0-process-of-another-manifest": (
        (),
        process_of_another_manifest,
        ("ARTIFACT_MALFORMED"),
    ),
}


@pytest.mark.parametrize("label", STALENESS)
def test_an_external_edit_is_refused_and_nothing_follows(label, lifecycle):
    ux, edit, code = STALENESS[label]
    cycle = lifecycle()
    started(cycle, *ux)
    edit(cycle.scene)
    before = {d: cycle.scene.tsa.content_of(d) for d in cycle.scene.tsa.documents}
    mark = cycle.mark()

    for argv in (decision_argv("approve"), decision_argv("rework"), RESUME):
        assert_result(cycle(*argv), code, 1)

    assert cycle.mutations_since(mark) == [], "a failed gate writes nothing"
    assert cycle.models.counts == (1, 1), "and calls no model"
    after = {d: cycle.scene.tsa.content_of(d) for d in cycle.scene.tsa.documents}
    assert after == before, "historical evidence untouched"
    inspected = json_of(cycle(*INSPECT, "--json"))["code"]
    assert inspected == (
        "INSPECT_STALE" if code == "INPUTS_STALE" else "INSPECT_INCOMPLETE"
    )


def test_c_not_applicable_drift_after_approval_reads_no_ux(lifecycle):
    cycle = lifecycle()
    started(cycle)
    assert_result(cycle(*decision_argv("approve")), "ARCHITECTURE_APPROVED", 0)
    root_edited_after_review(cycle.scene)

    record = json_of(cycle(*INSPECT, "--json"))
    assert_result(cycle(*RESUME), "INPUTS_STALE", 1)

    assert record["code"] == "INSPECT_STALE"
    assert record["inputs"]["ux"] == {"kind": "NOT_APPLICABLE", "current": False}
    assert ux_reads(cycle) == [], "no UX Document read under NOT_APPLICABLE"


def test_acceptance_is_never_refreshed_by_a_repeated_start(lifecycle):
    cycle = lifecycle()
    started(cycle)
    manifest = cycle.scene.tsa.content_of(MANIFEST_ID)
    root_edited_after_review(cycle.scene)

    assert_result(cycle(*start_argv()), "INPUTS_STALE", 1)
    assert cycle.scene.tsa.content_of(MANIFEST_ID) == manifest


# --------------------------------------------------------------------------
# H. Invalid and conflicting durable state
# --------------------------------------------------------------------------


def malformed(document_id_of: Callable[[], str]):
    def edit(scene) -> None:
        document_id = document_id_of()
        if document_id not in scene.tsa.documents:
            scene.tsa.seed_child(document_id, ARCHITECTURE_ID, "")
        scene.tsa.set_content(document_id, "A note someone left here.\n")

    return edit


def duplicate_review(scene) -> None:
    content = scene.tsa.content_of(review_id(1))
    scene.tsa.seed_child("rogue-review", ARCHITECTURE_ID, content)


def empty_decision_shell(scene) -> None:
    scene.tsa.seed_child(decision_id(1), ARCHITECTURE_ID, "")


INVALID = {
    "malformed-process": (malformed(lambda: process_id(1)), "ARTIFACT_MALFORMED"),
    "malformed-review": (malformed(lambda: review_id(1)), "ARTIFACT_MALFORMED"),
    "malformed-decision": (malformed(lambda: decision_id(1)), "ARTIFACT_MALFORMED"),
    "duplicate-review": (duplicate_review, "ARTIFACT_DUPLICATE"),
    "divergent-architecture": (edit_architecture, "ARCHITECTURE_DIVERGED"),
    "empty-decision-shell": (empty_decision_shell, "DECISION_SHELL_UNRECOVERABLE"),
}


@pytest.mark.parametrize("label", INVALID)
def test_invalid_durable_state_is_refused_and_never_repaired(label, lifecycle):
    edit, code = INVALID[label]
    cycle = lifecycle()
    started(cycle)
    edit(cycle.scene)
    before = {d: cycle.scene.tsa.content_of(d) for d in cycle.scene.tsa.documents}
    mark = cycle.mark()

    for argv in (start_argv(), RESUME, decision_argv("approve")):
        assert_result(cycle(*argv), code, 1)

    assert cycle.mutations_since(mark) == [] and cycle.models.counts == (1, 1)
    after = {d: cycle.scene.tsa.content_of(d) for d in cycle.scene.tsa.documents}
    assert after == before, "nothing repaired or overwritten"


# --------------------------------------------------------------------------
# I. Reviewer input drift (spec v0.5)
# --------------------------------------------------------------------------


def test_a_process_replaced_during_the_reviewer_call_is_review_input_changed(
    lifecycle,
):
    cycle = lifecycle()
    cycle.models.during[TSA_REVIEWER_ROLE] = lambda: resealed_process(cycle.scene)

    run = cycle(*start_argv())

    assert_result(run, "REVIEW_INPUT_CHANGED", 1)
    assert cycle.models.counts == (1, 1), "no automatic second Reviewer call"
    assert review_id(1) not in cycle.scene.tsa.documents
    later = cycle(*RESUME)
    assert_result(later, "ARCHITECTURE_CYCLE_RESUMED", 0)
    assert cycle.models.counts == (1, 2), "one explicit later Reviewer call"
    review = artifact(cycle.scene, review_id(1))
    current = artifact(cycle.scene, process_id(1))["artifact_digest"]
    assert review["body"]["process_result_digest"] == current, "reviews P2 only"


def resealed_process(scene) -> None:
    reseal(
        scene,
        process_id(1),
        lambda payload: payload["body"].update(created_at="2027-01-02T03:04:05Z"),
    )


# --------------------------------------------------------------------------
# J. Approval policy: an accepted technical risk, a material WHAT
# --------------------------------------------------------------------------


def test_a_needs_work_review_is_approved_with_an_accepted_risk(lifecycle):
    cycle = lifecycle()
    cycle.models.review_changes = lambda scene, iteration: {
        "new_findings": [finding("WARNING")]
    }
    started(cycle)
    review = artifact(cycle.scene, review_id(1))
    assert review["body"]["derived_status"] == "REVIEW_NEEDS_WORK"
    ref = f"{review['artifact_digest']}#new_findings/0"

    run = cycle(
        *decision_argv("approve", 1, "--accept-risk", ref, "--accept-reason", "Known.")
    )

    assert_result(run, "ARCHITECTURE_APPROVED", 0)
    body = artifact(cycle.scene, decision_id(1))["body"]
    assert body["accepted_dispositions"] == [{"ref": ref, "reason": "Known."}]


def test_a_material_what_cannot_be_approved_or_accepted_away(lifecycle):
    cycle = lifecycle()
    cycle.models.review_changes = lambda scene, iteration: {
        "material_unresolved_what": [material_what()]
    }
    started(cycle)
    review = artifact(cycle.scene, review_id(1))
    assert review["body"]["derived_status"] == "REVIEW_BLOCKED_ON_WHAT"
    ref = f"{review['artifact_digest']}#material_unresolved_what/0"
    mark = cycle.mark()

    for extra in ((), ("--accept-risk", ref, "--accept-reason", "Anyway.")):
        run = cycle(*decision_argv("approve", 1, *extra))
        assert_result(run, "REVIEW_BLOCKED_ON_WHAT", 1)
    assert cycle.mutations_since(mark) == []
    assert decision_id(1) not in cycle.scene.tsa.documents


def test_a_material_product_question_stays_evidence_and_blocks_approval(lifecycle):
    cycle = lifecycle()
    cycle.models.architect = [
        response_text(architect_response(product_questions=[product_question()]))
    ]

    def leave_the_question_open(scene, iteration):
        question = f"{payload_of(scene, process_id(iteration))['artifact_digest']}"
        question += "#product_questions/0"
        return {
            "verifications": [
                verification(ref, "UNRESOLVED")
                if ref == question
                else verification(ref)
                for ref in claims(scene, iteration)
            ]
        }

    cycle.models.review_changes = leave_the_question_open
    started(cycle)

    assert_result(cycle(*decision_argv("approve")), "REVIEW_BLOCKED_ON_WHAT", 1)
    intended = artifact(cycle.scene, process_id(1))["body"]["intended_output"]
    assert intended["product_questions"] == [product_question()]


# --------------------------------------------------------------------------
# K. Two cooperating commands (row 21): one integration control
# --------------------------------------------------------------------------


def test_a_second_mutating_command_is_busy_while_inspect_still_reads(lifecycle):
    cycle = lifecycle()
    started(cycle)
    mark = cycle.mark()

    with hold_workspace(cycle.scene.tsa.lock_scope):
        busy = cycle(*decision_argv("approve"))
        inspected = cycle(*INSPECT)

    assert_result(busy, "WORKSPACE_BUSY", 1)
    assert_result(inspected, "INSPECT_CURRENT", 0)
    assert cycle.mutations_since(mark) == [] and cycle.models.counts == (1, 1)
    assert_result(cycle(*decision_argv("approve")), "ARCHITECTURE_APPROVED", 0)


# --------------------------------------------------------------------------
# L. Output contract across the journey
# --------------------------------------------------------------------------


def test_no_output_carries_a_secret_or_document_content(lifecycle):
    cycle = lifecycle()
    outputs = [
        cycle(*start_argv()),
        cycle(*INSPECT),
        cycle(*INSPECT, "--json"),
        cycle(*decision_argv("approve")),
        cycle(*RESUME),
    ]
    text = "".join(run.out + run.err for run in outputs)
    secrets = [document.secret for document in cycle.scene.tsa.documents.values()]

    assert ENVIRONMENT[ENV_TOKEN] not in text
    assert not [secret for secret in secrets if secret in text]
    assert "One Requirement about model execution guards." not in text
    for run in outputs:
        assert run.exit_code == 0 and run.err == ""


# --------------------------------------------------------------------------
# M. The Review/Process binding alone (lineage invariant 3)
# --------------------------------------------------------------------------


def test_a_review_bound_to_a_replaced_process_is_refused_for_that_reason(
    lifecycle,
):
    """P2 is valid on its own and for the cycle; only R1 -> P1 is broken."""
    cycle = lifecycle()
    scene = cycle.scene
    started(cycle)
    first = artifact(scene, process_id(1))
    review = artifact(scene, review_id(1))
    manifest = artifact(scene, MANIFEST_ID)
    envelope = extract_architecture_envelope(scene.tsa.content_of(ARCHITECTURE_ID))

    resealed_process(scene)
    second = artifact(scene, process_id(1))

    assert second["artifact_digest"] != first["artifact_digest"]
    assert second["iteration"] == first["iteration"] == 1
    assert (second["cycle_id"], second["project_entity_id"]) == (CYCLE, PROJECT_ID)
    assert second["body"]["manifest_digest"] == manifest["body"]["manifest_digest"]
    assert second["body"]["intended_output"] == first["body"]["intended_output"]
    rendered = render_architecture(
        second["body"]["intended_output"], manifest["body"]["manifest_body"]
    )
    assert rendered.content_fingerprint == envelope["body"]["content_fingerprint"]
    assert review["body"]["process_result_digest"] == first["artifact_digest"]
    before = {d: scene.tsa.content_of(d) for d in scene.tsa.documents}
    mark = cycle.mark()

    for argv in (
        decision_argv("approve"),
        decision_argv("rework"),
        RESUME,
        start_argv(),
    ):
        run = cycle(*argv)
        assert_result(run, "ARTIFACT_MALFORMED", 1)
        assert "process_result_digest does not name the supplied Process" in run.err
    record = json_of(cycle(*INSPECT, "--json"))

    assert record["code"] == "INSPECT_INCOMPLETE"
    assert cycle.mutations_since(mark) == [] and cycle.models.counts == (1, 1)
    after = {d: scene.tsa.content_of(d) for d in scene.tsa.documents}
    assert after == before, "the historical Review is not repaired"


# --------------------------------------------------------------------------
# N. Project prose and UX content never reach a prompt they may not
# --------------------------------------------------------------------------

PROJECT_PROSE = "PROJECT_DESCRIPTION_NOT_NORMATIVE_5b1e9c"
UX_SENTINEL = "UX_ONLY_SENTINEL_d41c07"


def with_project_prose(scene) -> None:
    """A Project-level context Document the engine can read, never authority."""
    scene.tsa.seed_root(
        "project-context-doc",
        f"# SDLC project context\n\nThis Project ships safely. {PROJECT_PROSE}\n",
        name="SDLC — Project context",
    )


def test_project_prose_never_reaches_the_reviewer_as_authority(lifecycle):
    scene = base_scene()
    with_project_prose(scene)
    cycle = lifecycle(scene)

    started(cycle)

    architect, reviewer = cycle.models.calls
    process = artifact(scene, process_id(1))
    manifest = artifact(scene, MANIFEST_ID)
    selected = scene.req.content[scene.root.secret]
    assert any(line in reviewer.text for line in selected.splitlines() if line)
    assert manifest["body"]["manifest_digest"] in reviewer.text
    assert "A runtime gate in front of every model call." in reviewer.text
    assert process["body"]["architect_response"]["risks"][0]["detail"] in (
        reviewer.text
    ), "the persisted Architect claims"
    for call in (architect, reviewer):
        assert PROJECT_PROSE not in call.text, f"Project prose reached {call.role}"
        assert SECOND_ID not in call.text
    for document_id in (ARCHITECTURE_ID, MANIFEST_ID, process_id(1), review_id(1)):
        assert PROJECT_PROSE not in scene.tsa.content_of(document_id)


@pytest.mark.parametrize("branch", ["not-applicable", "applicable"])
def test_ux_content_reaches_the_prompts_only_when_applicable(branch, lifecycle):
    scene = base_scene()
    scene.tsa.set_content(UX_DOCUMENT_ID, f"# Checkout flow\n\n{UX_SENTINEL}\n")
    cycle = lifecycle(scene)

    started(cycle, *(APPLICABLE_ARGV if branch == "applicable" else ()))

    for call in cycle.models.calls:
        assert (UX_SENTINEL in call.text) is (branch == "applicable"), call.role
    assert bool(ux_reads(cycle)) is (branch == "applicable")
