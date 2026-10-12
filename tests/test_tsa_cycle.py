"""I04 — cycle identity, discovery and the Architecture bootstrap.

Driven entirely by an in-memory workspace. Nothing here calls live Fibery or a
model, so every claim below is D-class only.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone

import pytest

from architecture_fake import (
    OTHER_DATABASE_TYPE_ID,
    PROJECT_TYPE_ID,
    FakeArchitectureWorkspace,
)
from sdlc.fibery_workspace import FiberyError, ProjectRecord
from sdlc.tsa_artifacts import (
    INPUT_MANIFEST,
    compute_artifact_digest,
    extract_architecture_envelope,
    validate_artifact,
)
from sdlc.tsa_cycle import (
    BOOTSTRAP_SENTENCE,
    DURABLE_STATES,
    TSA_DOCUMENT_NAMESPACE,
    BootstrapContext,
    CycleOutcome,
    CycleRefused,
    CycleResultCode,
    DocumentKind,
    bootstrap_readback_matches,
    build_bootstrap_artifact,
    created_at_now,
    derive_document_id,
    discover_cycle,
    ensure_bootstrap_architecture,
    rediscover_after_unknown_outcome,
    render_bootstrap_carrier,
    resolve_bootstrap_context,
)
from test_tsa_artifacts import (
    DIGEST_A,
    applied_group,
    architecture_artifact,
    carrier,
    envelope,
    input_manifest_artifact,
)

WORKSPACE = "example.fibery.io/11111111-2222-4333-8444-555555555555"
PROJECT_ID = "proj-1"
PUBLIC_ID = "7"
PROJECT_CODE = "SDLC"
CYCLE = "arch-2026-09-a"
ARCHITECTURE_ID = "0576efe5-1d70-515e-b587-0a39f85ce6f2"
MANIFEST_ID = "3800ce1f-893d-5324-8539-d2e2e842ad55"
STRAY_ID = "stray-architecture"
CREATED_AT = "2026-10-10T12:00:00Z"
NAME = "SDLC — TSA arch-2026-09-a — Architecture"

CONTEXT = BootstrapContext(
    workspace_identity=WORKSPACE,
    project_type_id=PROJECT_TYPE_ID,
    project_entity_id=PROJECT_ID,
    project_public_id=PUBLIC_ID,
    project_code=PROJECT_CODE,
    cycle_id=CYCLE,
)

PINNED_CARRIER = (
    "# SDLC — TSA arch-2026-09-a — Architecture\n"
    "\n"
    "Bootstrap shell. No Architect output has been applied.\n"
    "\n"
    "```json\n"
    '{"artifact_digest":'
    '"601f4cb06d4d72252992d5969be8548c3c81e8535cc3645bb9ec733be5c1e180",'
    '"artifact_type":"tsa.architecture",'
    '"body":{"created_at":"2026-10-10T12:00:00Z","cycle_id":"arch-2026-09-a"},'
    '"cycle_id":"arch-2026-09-a","project_code":"SDLC",'
    '"project_entity_id":"proj-1","schema_version":1,'
    '"workspace_identity":'
    '"example.fibery.io/11111111-2222-4333-8444-555555555555"}\n'
    "```\n"
)


def fixed_clock() -> datetime:
    return datetime(2026, 10, 10, 12, 0, 0, 987654, tzinfo=UTC)


def project_record(code: str | None = PROJECT_CODE) -> ProjectRecord:
    return ProjectRecord(
        id=PROJECT_ID, name="SDLC", code=code, state="Planned", public_id=PUBLIC_ID
    )


class ScriptedWorkspace(FakeArchitectureWorkspace):
    """The shared fake, plus an argument log and per-call scripted effects.

    `before` and `after` run an effect around the nth occurrence of one call, so
    a test can move a placement, drop a Project Code or raise at an exact point.
    `store_as` rewrites what a content write stores, standing in for Fibery's
    re-serialization or for a write that did not land.
    """

    def __init__(self, record: ProjectRecord | None = None) -> None:
        super().__init__([record if record is not None else project_record()])
        self.log: list[tuple[str, str]] = []
        self.written: list[str] = []
        self.store_as: Callable[[str], str] | None = None
        self._before: dict[tuple[str, int], Callable[[], None]] = {}
        self._after: dict[tuple[str, int], Callable[[], None]] = {}
        self._seen: Counter[str] = Counter()

    @property
    def lock_scope(self) -> str:
        return WORKSPACE

    def before(self, call: str, occurrence: int, effect: Callable[[], None]) -> None:
        self._before[(call, occurrence)] = effect

    def after(self, call: str, occurrence: int, effect: Callable[[], None]) -> None:
        self._after[(call, occurrence)] = effect

    def _run(self, call: str, argument: str, operation: Callable[[], object]):
        self._seen[call] += 1
        key = (call, self._seen[call])
        self.log.append((call, argument))
        if key in self._before:
            self._before[key]()
        result = operation()
        if key in self._after:
            self._after[key]()
        return result

    def read_project(self, project_id):
        parent = super()
        return self._run(
            "read_project", project_id, lambda: parent.read_project(project_id)
        )

    def resolve_placement(self, document_id):
        parent = super()
        return self._run(
            "resolve_placement",
            document_id,
            lambda: parent.resolve_placement(document_id),
        )

    def documents_attached_to_project(self, project_public_id):
        parent = super()
        return self._run(
            "documents_attached_to_project",
            project_public_id,
            lambda: parent.documents_attached_to_project(project_public_id),
        )

    def create_project_document(self, document_id, name, project_public_id):
        parent = super()
        return self._run(
            "create_project_document",
            document_id,
            lambda: parent.create_project_document(
                document_id, name, project_public_id
            ),
        )

    def read_document_content(self, secret):
        parent = super()
        return self._run(
            "read_document_content",
            secret,
            lambda: parent.read_document_content(secret),
        )

    def write_document_content(self, secret, markdown):
        parent = super()
        self.written.append(markdown)
        stored = self.store_as(markdown) if self.store_as else markdown
        return self._run(
            "write_document_content",
            secret,
            lambda: parent.write_document_content(secret, stored),
        )

    # -- seeding and observation ------------------------------------------

    def seed_root(self, document_id: str, content: str = "", name: str = "") -> None:
        self.place_foreign_document(
            document_id,
            container_entity_type=PROJECT_TYPE_ID,
            container_entity_id=PUBLIC_ID,
        )
        self.documents[document_id].name = name or document_id
        self.set_content(document_id, content)

    def seed_child(self, document_id: str, parent_id: str, content: str = "") -> None:
        self.place_foreign_document(document_id, parent_document_id=parent_id)
        self.set_content(document_id, content)

    def set_content(self, document_id: str, content: str) -> None:
        self.content[self.documents[document_id].secret] = content

    def content_of(self, document_id: str) -> str:
        return self.content[self.documents[document_id].secret]

    def count(self, call: str) -> int:
        """Attempts, including one a scripted effect made fail."""
        return [name for name, _ in self.log].count(call)


def bootstrap_carrier(
    context: BootstrapContext = CONTEXT, created_at: str = CREATED_AT
) -> str:
    return render_bootstrap_carrier(
        context, build_bootstrap_artifact(context, created_at)
    )


def architecture_document(payload: dict[str, object]) -> str:
    """Any valid Architecture carrier: prose, then one trailing envelope."""
    return f"# Some heading\n\nSome prose.\n\n```json\n{json.dumps(payload)}\n```\n"


def stray_architecture() -> str:
    """A valid same-cycle `tsa.architecture`, to be placed at a non-derived id."""
    return architecture_document(architecture_artifact())


def bootstrapped() -> ScriptedWorkspace:
    workspace = ScriptedWorkspace()
    workspace.seed_root(ARCHITECTURE_ID, bootstrap_carrier())
    return workspace


def with_empty_shell() -> ScriptedWorkspace:
    workspace = ScriptedWorkspace()
    workspace.seed_root(ARCHITECTURE_ID)
    return workspace


def discover(workspace: ScriptedWorkspace, cycle: object = CYCLE):
    return discover_cycle(workspace, PROJECT_ID, cycle)


def ensure(workspace: ScriptedWorkspace, create_if_absent: bool = True):
    return ensure_bootstrap_architecture(
        workspace,
        PROJECT_ID,
        CYCLE,
        create_if_absent=create_if_absent,
        clock=fixed_clock,
    )


def refusal(workspace: ScriptedWorkspace, create_if_absent: bool = True):
    with pytest.raises(CycleRefused) as caught:
        ensure(workspace, create_if_absent)
    return caught.value


# --------------------------------------------------------------------------
# Deterministic Document ids (3.5)
# --------------------------------------------------------------------------


def test_namespace_is_reproducible_from_the_frozen_url():
    import uuid

    assert (
        uuid.uuid5(uuid.NAMESPACE_URL, "https://github.com/ros-datonum/sdlc/tsa/v1")
        == TSA_DOCUMENT_NAMESPACE
    )


@pytest.mark.parametrize(
    ("kind", "iteration", "expected"),
    [
        (DocumentKind.ARCHITECTURE, None, "0576efe5-1d70-515e-b587-0a39f85ce6f2"),
        (DocumentKind.INPUT_MANIFEST, None, "3800ce1f-893d-5324-8539-d2e2e842ad55"),
        (DocumentKind.PROCESS_RESULT, 1, "cae8d621-7c7d-5b18-9531-9e34a503d4fe"),
        (DocumentKind.REVIEW_RESULT, 1, "3f02b5c6-40ea-566f-a545-d47c0a6cbada"),
        (DocumentKind.HUMAN_DECISION, 1, "91404f8c-fd19-5c15-ac72-e65d93dec39d"),
        (DocumentKind.PROCESS_RESULT, 2, "5b1448bb-1430-5a49-8b62-13001e8f1939"),
    ],
)
def test_reproduces_the_normative_id_vectors(kind, iteration, expected):
    assert derive_document_id(WORKSPACE, PROJECT_ID, CYCLE, kind, iteration) == expected


def test_same_tuple_always_derives_the_same_id():
    first = derive_document_id(WORKSPACE, PROJECT_ID, CYCLE, "process_result", 7)
    second = derive_document_id(WORKSPACE, PROJECT_ID, CYCLE, "process_result", 7)
    assert first == second


def test_project_code_and_public_id_do_not_affect_the_id():
    other = replace(CONTEXT, project_code="OTHER", project_public_id="999")
    assert other.architecture_document_id == ARCHITECTURE_ID
    assert other.input_manifest_document_id == MANIFEST_ID


@pytest.mark.parametrize(
    "changed",
    [
        ("other.fibery.io/x", PROJECT_ID, CYCLE, "process_result", 1),
        (WORKSPACE, "proj-2", CYCLE, "process_result", 1),
        (WORKSPACE, PROJECT_ID, "arch-2026-09-b", "process_result", 1),
        (WORKSPACE, PROJECT_ID, CYCLE, "review_result", 1),
        (WORKSPACE, PROJECT_ID, CYCLE, "process_result", 2),
    ],
)
def test_every_tuple_component_affects_the_id(changed):
    baseline = derive_document_id(WORKSPACE, PROJECT_ID, CYCLE, "process_result", 1)
    assert derive_document_id(*changed) != baseline


def test_id_derivation_uses_the_canonical_cycle_id():
    assert (
        derive_document_id(WORKSPACE, PROJECT_ID, "  ARCH-2026-09-A ", "architecture")
        == ARCHITECTURE_ID
    )


@pytest.mark.parametrize("iteration", [0, 1000, -1, None, True, "1", 1.0])
def test_iterated_id_refuses_an_iteration_outside_1_to_999(iteration):
    with pytest.raises(ValueError):
        derive_document_id(WORKSPACE, PROJECT_ID, CYCLE, "process_result", iteration)


@pytest.mark.parametrize(("iteration", "rendered"), [(1, "0001"), (999, "0999")])
def test_iteration_is_rendered_as_exactly_four_digits(iteration, rendered):
    import uuid

    expected = uuid.uuid5(
        TSA_DOCUMENT_NAMESPACE,
        f"{WORKSPACE}|{PROJECT_ID}|{CYCLE}|human_decision|{rendered}",
    )
    assert derive_document_id(
        WORKSPACE, PROJECT_ID, CYCLE, "human_decision", iteration
    ) == str(expected)


@pytest.mark.parametrize("kind", ["architecture", "input_manifest"])
def test_non_iterated_id_refuses_an_iteration(kind):
    with pytest.raises(ValueError):
        derive_document_id(WORKSPACE, PROJECT_ID, CYCLE, kind, 1)


def test_unknown_document_kind_is_refused():
    with pytest.raises(ValueError):
        derive_document_id(WORKSPACE, PROJECT_ID, CYCLE, "tsa.architecture")


# --------------------------------------------------------------------------
# Cycle id (3.1) and the trusted expected context (4.1.1)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    ["arch-2026-09-a", "  Arch-2026-09-A\n", "ARCH-2026-09-A", "\tarch-2026-09-a "],
)
def test_cycle_id_is_trimmed_and_lowercased(raw):
    assert resolve_bootstrap_context(ScriptedWorkspace(), PROJECT_ID, raw).cycle_id == (
        CYCLE
    )


@pytest.mark.parametrize("raw", ["abc", "a" * 40, "a-b", "0-9", "a" + "-" * 38 + "b"])
def test_cycle_id_boundary_values_are_accepted(raw):
    assert resolve_bootstrap_context(ScriptedWorkspace(), PROJECT_ID, raw).cycle_id == (
        raw
    )


@pytest.mark.parametrize(
    "raw",
    [
        "ab",
        "a" * 41,
        "-ab",
        "ab-",
        "a_b",
        "a b",
        "",
        "   ",
        "arch/1",
        "ärch-1",
        7,
        None,
    ],
)
def test_invalid_cycle_id_is_refused_before_any_fibery_call(raw):
    workspace = ScriptedWorkspace()
    with pytest.raises(CycleRefused) as caught:
        discover(workspace, raw)
    assert caught.value.code is CycleResultCode.INVALID_CYCLE_ID
    assert workspace.calls == []


def test_context_is_built_from_the_workspace_and_a_fresh_project_read():
    assert resolve_bootstrap_context(ScriptedWorkspace(), PROJECT_ID, CYCLE) == CONTEXT


def test_context_holds_the_deterministic_ids():
    assert CONTEXT.architecture_document_id == ARCHITECTURE_ID
    assert CONTEXT.input_manifest_document_id == MANIFEST_ID


@pytest.mark.parametrize(
    "call", ["read_project", "resolve_placement", "documents_attached_to_project"]
)
def test_a_failed_read_is_fibery_read_failed_not_a_guessed_state(call):
    workspace = ScriptedWorkspace()
    workspace.failures[call] = FiberyError("boom")
    with pytest.raises(CycleRefused) as caught:
        discover(workspace)
    assert caught.value.code is CycleResultCode.FIBERY_READ_FAILED
    assert workspace.mutations == []


def test_a_failed_content_read_is_fibery_read_failed():
    workspace = bootstrapped()
    workspace.failures["read_document_content"] = FiberyError("boom")
    with pytest.raises(CycleRefused) as caught:
        discover(workspace)
    assert caught.value.code is CycleResultCode.FIBERY_READ_FAILED


def test_an_unknown_project_is_fibery_read_failed():
    with pytest.raises(CycleRefused) as caught:
        discover_cycle(ScriptedWorkspace(), "no-such-project", CYCLE)
    assert caught.value.code is CycleResultCode.FIBERY_READ_FAILED


def test_a_project_without_a_public_id_is_fibery_read_failed():
    workspace = ScriptedWorkspace(replace(project_record(), public_id=""))
    with pytest.raises(CycleRefused) as caught:
        discover(workspace)
    assert caught.value.code is CycleResultCode.FIBERY_READ_FAILED


def test_a_programmer_error_is_not_converted_into_a_lifecycle_state():
    workspace = ScriptedWorkspace()

    def explode() -> None:
        raise RuntimeError("not a Fibery failure")

    workspace.before("resolve_placement", 1, explode)
    with pytest.raises(RuntimeError):
        discover(workspace)


# --------------------------------------------------------------------------
# Discovery — contract row 39, in the frozen order and precedence (3.4)
# --------------------------------------------------------------------------


def test_derived_absent_and_no_conflict_is_state_a():
    workspace = ScriptedWorkspace()
    found = discover(workspace)
    assert found.outcome is CycleOutcome.A
    assert found.refusal_code is None
    assert workspace.mutations == []


def test_correctly_placed_empty_derived_document_is_the_empty_shell_not_a():
    found = discover(with_empty_shell())
    assert found.outcome is CycleOutcome.EMPTY_ARCHITECTURE_SHELL
    assert found.outcome not in DURABLE_STATES
    assert found.refusal_code is None


@pytest.mark.parametrize("body", [" ", "\n\n", "\t \n"])
def test_whitespace_only_derived_document_is_the_empty_shell(body):
    workspace = ScriptedWorkspace()
    workspace.seed_root(ARCHITECTURE_ID, body)
    assert discover(workspace).outcome is CycleOutcome.EMPTY_ARCHITECTURE_SHELL


def test_valid_derived_architecture_alone_is_adopted_as_state_b():
    workspace = bootstrapped()
    found = discover(workspace)
    assert found.outcome is CycleOutcome.B
    assert found.context.architecture_document_id == ARCHITECTURE_ID
    assert workspace.mutations == []


def test_non_derived_same_cycle_architecture_alone_is_ambiguous_never_adopted():
    workspace = ScriptedWorkspace()
    workspace.seed_root(STRAY_ID, stray_architecture())
    found = discover(workspace)
    assert found.outcome is CycleOutcome.E
    assert found.refusal_code is CycleResultCode.CYCLE_AMBIGUOUS
    assert STRAY_ID in found.detail


def test_non_derived_same_cycle_architecture_beside_a_valid_derived_is_ambiguous():
    workspace = bootstrapped()
    workspace.seed_root(STRAY_ID, stray_architecture())
    assert discover(workspace).refusal_code is CycleResultCode.CYCLE_AMBIGUOUS


def test_non_derived_same_cycle_architecture_beside_an_empty_shell_is_ambiguous():
    workspace = with_empty_shell()
    workspace.seed_root(STRAY_ID, stray_architecture())
    found = discover(workspace)
    assert found.outcome is CycleOutcome.E
    assert found.refusal_code is CycleResultCode.CYCLE_AMBIGUOUS


@pytest.mark.parametrize(
    "placement",
    [
        {"container_entity_type": PROJECT_TYPE_ID, "container_entity_id": "999"},
        {
            "container_entity_type": OTHER_DATABASE_TYPE_ID,
            "container_entity_id": PUBLIC_ID,
        },
        {
            "container_entity_type": PROJECT_TYPE_ID,
            "container_entity_id": PUBLIC_ID,
            "parent_document_id": "some-parent",
        },
        {"container_entity_type": None, "container_entity_id": None},
    ],
)
def test_foreign_derived_placement_is_refused_before_any_content_is_read(placement):
    workspace = ScriptedWorkspace()
    workspace.place_foreign_document(ARCHITECTURE_ID, **placement)
    workspace.set_content(ARCHITECTURE_ID, bootstrap_carrier())
    workspace.seed_root(STRAY_ID, stray_architecture())
    found = discover(workspace)
    assert found.outcome is CycleOutcome.E
    assert found.refusal_code is CycleResultCode.CYCLE_FOREIGN_PROJECT
    assert workspace.count("read_document_content") == 0
    assert workspace.count("documents_attached_to_project") == 0


def malformed_derived_bodies() -> dict[str, str]:
    valid = build_bootstrap_artifact(CONTEXT, CREATED_AT)
    return {
        "no fence": "Some notes a human left behind.",
        "half-written fence": '# X\n\nText.\n\n```json\n{"a": 1}\n',
        "two envelopes": bootstrap_carrier() + bootstrap_carrier(),
        "bad digest": render_bootstrap_carrier(
            CONTEXT, {**valid, "artifact_digest": DIGEST_A}
        ),
        "unknown key": render_bootstrap_carrier(
            CONTEXT, envelope("tsa.architecture", valid["body"], surprise="x")
        ),
        "another artifact type": carrier(input_manifest_artifact()),
        "not json": "# X\n\nText.\n\n```json\nnot json\n```\n",
    }


@pytest.mark.parametrize("label", sorted(malformed_derived_bodies()))
def test_malformed_derived_content_is_artifact_malformed(label):
    workspace = ScriptedWorkspace()
    workspace.seed_root(ARCHITECTURE_ID, malformed_derived_bodies()[label])
    found = discover(workspace)
    assert found.outcome is CycleOutcome.E
    assert found.refusal_code is CycleResultCode.ARTIFACT_MALFORMED
    assert workspace.mutations == []


def test_malformed_derived_content_takes_precedence_over_ambiguity():
    workspace = ScriptedWorkspace()
    workspace.seed_root(ARCHITECTURE_ID, "Some notes a human left behind.")
    workspace.seed_root(STRAY_ID, stray_architecture())
    found = discover(workspace)
    assert found.refusal_code is CycleResultCode.ARTIFACT_MALFORMED
    assert workspace.count("documents_attached_to_project") == 0


def name_only_documents() -> dict[str, str]:
    other_project = envelope(
        "tsa.architecture", {"cycle_id": CYCLE, "created_at": CREATED_AT}
    )
    other_project = {**other_project, "project_entity_id": "proj-2"}
    del other_project["artifact_digest"]
    other_project["artifact_digest"] = compute_artifact_digest(other_project)
    other_cycle = build_bootstrap_artifact(
        replace(CONTEXT, cycle_id="arch-2026-09-b"), CREATED_AT
    )
    return {
        "empty": "",
        "garbage": "Looks like an Architecture, is not one.",
        "bad digest": architecture_document(
            {**architecture_artifact(), "artifact_digest": DIGEST_A}
        ),
        "another cycle": architecture_document(other_cycle),
        "another project": architecture_document(other_project),
        "an input manifest": carrier(input_manifest_artifact()),
    }


@pytest.mark.parametrize("label", sorted(name_only_documents()))
def test_a_name_match_alone_decides_nothing(label):
    workspace = ScriptedWorkspace()
    workspace.seed_root(STRAY_ID, name_only_documents()[label], name=NAME)
    assert discover(workspace).outcome is CycleOutcome.A


@pytest.mark.parametrize(
    "placement",
    [
        {"container_entity_type": PROJECT_TYPE_ID, "container_entity_id": "999"},
        {
            "container_entity_type": PROJECT_TYPE_ID,
            "container_entity_id": PUBLIC_ID,
            "parent_document_id": "some-parent",
        },
    ],
)
def test_a_valid_architecture_outside_the_project_root_is_not_a_candidate(placement):
    workspace = ScriptedWorkspace()
    workspace.place_foreign_document(STRAY_ID, **placement)
    workspace.set_content(STRAY_ID, stray_architecture())
    assert discover(workspace).outcome is CycleOutcome.A


def test_a_candidate_is_recognised_whatever_its_name():
    workspace = ScriptedWorkspace()
    workspace.seed_root(STRAY_ID, stray_architecture(), name="Shopping list")
    assert discover(workspace).refusal_code is CycleResultCode.CYCLE_AMBIGUOUS


def test_discovery_resolves_the_derived_id_before_listing_the_project():
    workspace = bootstrapped()
    discover(workspace)
    calls = [call for call, _ in workspace.log]
    assert workspace.log[1] == ("resolve_placement", ARCHITECTURE_ID)
    assert calls.index("resolve_placement") < calls.index("read_document_content")
    assert calls.index("read_document_content") < calls.index(
        "documents_attached_to_project"
    )


def test_empty_shell_is_never_a_result_code_and_c_is_never_an_outcome():
    assert "EMPTY_ARCHITECTURE_SHELL" not in {code.value for code in CycleResultCode}
    assert {outcome.value for outcome in CycleOutcome} == {
        "A",
        "B",
        "D",
        "E",
        "EMPTY_ARCHITECTURE_SHELL",
    }
    assert {state.value for state in DURABLE_STATES} == {"A", "B", "D", "E"}


# --------------------------------------------------------------------------
# Trusted context: a valid digest never proves ownership (4.1.1)
# --------------------------------------------------------------------------


def body_cycle_only_mismatch() -> str:
    payload = dict(build_bootstrap_artifact(CONTEXT, CREATED_AT))
    del payload["artifact_digest"]
    payload["body"] = {"cycle_id": "arch-2026-09-b", "created_at": CREATED_AT}
    payload["artifact_digest"] = compute_artifact_digest(payload)
    return render_bootstrap_carrier(CONTEXT, payload)


def wrongly_bound_carriers() -> dict[str, str]:
    """Each is correctly placed, non-empty and — bar one — digest-valid."""
    return {
        "workspace_identity": bootstrap_carrier(
            replace(CONTEXT, workspace_identity="other.fibery.io/space")
        ),
        "project_entity_id": bootstrap_carrier(
            replace(CONTEXT, project_entity_id="proj-2")
        ),
        "project_code": bootstrap_carrier(replace(CONTEXT, project_code="OTHER")),
        "cycle_id": bootstrap_carrier(replace(CONTEXT, cycle_id="arch-2026-09-b")),
        "body.cycle_id": body_cycle_only_mismatch(),
        "heading project code": bootstrap_carrier().replace("# SDLC —", "# OTHER —"),
        "heading cycle": bootstrap_carrier().replace(
            "TSA arch-2026-09-a — Arch", "TSA arch-2026-09-b — Arch"
        ),
    }


@pytest.mark.parametrize("field", sorted(wrongly_bound_carriers()))
def test_wrong_external_binding_is_artifact_malformed_never_b(field):
    workspace = ScriptedWorkspace()
    workspace.seed_root(ARCHITECTURE_ID, wrongly_bound_carriers()[field])
    found = discover(workspace)
    assert found.outcome is CycleOutcome.E
    assert found.refusal_code is CycleResultCode.ARTIFACT_MALFORMED


@pytest.mark.parametrize(
    "field", ["workspace_identity", "project_entity_id", "project_code", "cycle_id"]
)
def test_the_wrongly_bound_fixtures_are_self_consistent(field):
    """The refusal above comes from the binding, not from a broken digest."""
    content = wrongly_bound_carriers()[field]
    validate_artifact(extract_architecture_envelope(content))


def test_wrong_placement_beats_wrong_content_binding():
    workspace = ScriptedWorkspace()
    workspace.place_foreign_document(
        ARCHITECTURE_ID,
        container_entity_type=PROJECT_TYPE_ID,
        container_entity_id="999",
    )
    workspace.set_content(ARCHITECTURE_ID, wrongly_bound_carriers()["project_code"])
    found = discover(workspace)
    assert found.refusal_code is CycleResultCode.CYCLE_FOREIGN_PROJECT
    assert workspace.count("read_document_content") == 0


@pytest.mark.parametrize("code", [None, "", "   "])
def test_non_empty_bootstrap_document_without_a_project_code_is_malformed(code):
    workspace = ScriptedWorkspace(project_record(code))
    workspace.seed_root(ARCHITECTURE_ID, bootstrap_carrier())
    found = discover(workspace)
    assert found.refusal_code is CycleResultCode.ARTIFACT_MALFORMED
    assert workspace.mutations == []


def test_discovery_reuses_only_the_persisted_created_at():
    workspace = ScriptedWorkspace()
    workspace.seed_root(
        ARCHITECTURE_ID, bootstrap_carrier(created_at="2020-01-02T03:04:05Z")
    )
    assert discover(workspace).outcome is CycleOutcome.B


def test_discovery_accepts_the_carrier_less_its_one_final_newline():
    workspace = ScriptedWorkspace()
    workspace.seed_root(ARCHITECTURE_ID, bootstrap_carrier()[:-1])
    assert discover(workspace).outcome is CycleOutcome.B


def respaced_json(emitted: str) -> str:
    """The same payload, re-serialized with different JSON bytes."""
    lines = emitted.split("\n")
    lines[5] = json.dumps(json.loads(lines[5]), sort_keys=True)
    return "\n".join(lines)


def non_conforming_readbacks() -> dict[str, Callable[[str], str]]:
    return {
        "wrong heading": lambda emitted: emitted.replace("# SDLC", "# Sdlc", 1),
        "extra blank line": lambda emitted: emitted.replace(
            "\n\n```json", "\n\n\n```json"
        ),
        "missing blank line": lambda emitted: emitted.replace(
            "\n\nBootstrap", "\nBootstrap"
        ),
        "wrong sentence": lambda emitted: emitted.replace("Bootstrap shell.", "Shell."),
        "wrong json bytes": respaced_json,
        "wrong external binding": lambda emitted: bootstrap_carrier(
            replace(CONTEXT, project_code="OTHER")
        ),
        "trailing content": lambda emitted: emitted + "trailing\n",
        "second final newline": lambda emitted: emitted + "\n",
        "crlf": lambda emitted: emitted.replace("\n", "\r\n"),
        "no fence at all": lambda emitted: "Something else entirely.",
        "another created_at": lambda emitted: bootstrap_carrier(
            created_at="2020-01-02T03:04:05Z"
        ),
    }


DISCOVERABLE_AS_B = {"another created_at"}


@pytest.mark.parametrize(
    "label", sorted(set(non_conforming_readbacks()) - DISCOVERABLE_AS_B)
)
def test_discovery_refuses_every_other_difference_from_the_carrier(label):
    workspace = ScriptedWorkspace()
    workspace.seed_root(
        ARCHITECTURE_ID, non_conforming_readbacks()[label](bootstrap_carrier())
    )
    assert discover(workspace).refusal_code is CycleResultCode.ARTIFACT_MALFORMED


# --------------------------------------------------------------------------
# Bootstrap carrier emission (4.1.1)
# --------------------------------------------------------------------------


def test_emitted_carrier_is_pinned_byte_for_byte():
    assert bootstrap_carrier() == PINNED_CARRIER


def test_emitted_carrier_structure():
    lines = bootstrap_carrier().split("\n")
    assert lines[0] == f"# {NAME}"
    assert lines[1] == ""
    assert lines[2] == BOOTSTRAP_SENTENCE
    assert lines[2] == "Bootstrap shell. No Architect output has been applied."
    assert lines[3] == ""
    assert lines[4] == "```json"
    assert lines[6] == "```"
    assert lines[7:] == [""]
    assert bootstrap_carrier().count("```json") == 1
    assert not any(line.startswith("## ") for line in lines)


def test_emitted_payload_is_the_canonical_sealed_bootstrap_artifact():
    payload = json.loads(bootstrap_carrier().split("\n")[5])
    assert bootstrap_carrier().split("\n")[5] == json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    assert "iteration" not in payload
    assert set(payload["body"]) == {"cycle_id", "created_at"}
    assert payload["body"] == {"cycle_id": CYCLE, "created_at": CREATED_AT}
    assert payload["artifact_type"] == "tsa.architecture"
    assert payload["schema_version"] == 1
    assert payload["workspace_identity"] == WORKSPACE
    assert payload["project_entity_id"] == PROJECT_ID
    assert payload["project_code"] == PROJECT_CODE
    assert payload["cycle_id"] == CYCLE
    assert payload["artifact_digest"] == validate_artifact(payload).artifact_digest


def test_created_at_is_utc_second_precision_with_a_z_suffix():
    assert created_at_now(fixed_clock) == CREATED_AT


def test_created_at_is_converted_to_utc():
    plus_two = timezone(timedelta(hours=2))
    assert (
        created_at_now(lambda: datetime(2026, 10, 10, 14, 0, 0, tzinfo=plus_two))
        == CREATED_AT
    )


def test_a_naive_clock_is_a_programmer_error():
    with pytest.raises(ValueError):
        created_at_now(lambda: datetime(2026, 10, 10, 12, 0, 0))  # noqa: DTZ001


@pytest.mark.parametrize(
    ("emitted", "readback", "expected"),
    [
        ("abc\n", "abc\n", True),
        ("abc\n", "abc", True),
        ("abc\n", "ab", False),
        ("abc\n", "abc\n\n", False),
        ("abc\n\n", "abc", False),
        ("abc\n", " abc\n", False),
        ("abc\n", "abc ", False),
        ("abc\n", "", False),
        ("abc", "ab", False),
        ("abc", "abc", True),
    ],
)
def test_bootstrap_readback_allows_exactly_one_terminal_newline(
    emitted, readback, expected
):
    assert bootstrap_readback_matches(emitted, readback) is expected


# --------------------------------------------------------------------------
# One bootstrap write contract, for both origins of the empty shell (4.1.1)
# --------------------------------------------------------------------------

ORIGINS = {"freshly created": ScriptedWorkspace, "rediscovered": with_empty_shell}
EXPECTED_CREATES = {"freshly created": 1, "rediscovered": 0}
# The gate reads the shell (after the create, or on rediscovery), and the write
# contract re-reads it immediately before writing.
# It resolves the derived Architecture id, then the Input Manifest id.
DISCOVERY_RESOLVES = 2
CONTENT_READS_BEFORE_WRITE = {"freshly created": 2, "rediscovered": 2}


@pytest.fixture(params=sorted(ORIGINS))
def origin(request) -> str:
    return request.param


def test_exact_readback_establishes_b(origin):
    workspace = ORIGINS[origin]()
    found = ensure(workspace)
    assert found.outcome is CycleOutcome.B
    assert workspace.written == [PINNED_CARRIER]
    assert workspace.content_of(ARCHITECTURE_ID) == PINNED_CARRIER
    assert workspace.count("create_project_document") == EXPECTED_CREATES[origin]
    assert workspace.count("write_document_content") == 1
    assert discover(workspace).outcome is CycleOutcome.B


def test_readback_less_its_final_newline_establishes_b(origin):
    workspace = ORIGINS[origin]()
    workspace.store_as = lambda emitted: emitted[:-1]
    assert ensure(workspace).outcome is CycleOutcome.B
    assert workspace.content_of(ARCHITECTURE_ID) == PINNED_CARRIER[:-1]
    assert workspace.count("write_document_content") == 1


@pytest.mark.parametrize("stored", ["", " ", "\n", " \n\t"])
def test_empty_or_whitespace_readback_is_fibery_write_failed(origin, stored):
    workspace = ORIGINS[origin]()
    workspace.store_as = lambda emitted: stored
    refused = refusal(workspace)
    assert refused.code is CycleResultCode.FIBERY_WRITE_FAILED
    assert workspace.count("write_document_content") == 1
    assert workspace.count("create_project_document") == EXPECTED_CREATES[origin]
    workspace.store_as = None
    assert discover(workspace).outcome is CycleOutcome.EMPTY_ARCHITECTURE_SHELL


@pytest.mark.parametrize("label", sorted(non_conforming_readbacks()))
def test_non_empty_non_conforming_readback_is_artifact_malformed(origin, label):
    workspace = ORIGINS[origin]()
    workspace.store_as = non_conforming_readbacks()[label]
    refused = refusal(workspace)
    assert refused.code is CycleResultCode.ARTIFACT_MALFORMED
    assert workspace.count("write_document_content") == 1
    assert workspace.count("create_project_document") == EXPECTED_CREATES[origin]


def test_both_origins_emit_the_same_carrier():
    emitted = []
    for build in ORIGINS.values():
        workspace = build()
        ensure(workspace)
        emitted.append(workspace.written)
    assert emitted[0] == emitted[1] == [PINNED_CARRIER]


def test_state_a_create_uses_the_derived_id_name_and_public_id():
    workspace = ScriptedWorkspace()
    ensure(workspace)
    stored = workspace.documents[ARCHITECTURE_ID]
    assert list(workspace.documents) == [ARCHITECTURE_ID]
    assert stored.name == NAME
    assert stored.container_entity_id == PUBLIC_ID
    assert stored.parent_document_id is None


def test_state_a_create_alone_does_not_establish_b():
    """A crash between the create and the carrier leaves the empty shell."""
    workspace = ScriptedWorkspace()

    def crash() -> None:
        raise KeyboardInterrupt

    workspace.before("write_document_content", 1, crash)
    with pytest.raises(KeyboardInterrupt):
        ensure(workspace)
    assert discover(workspace).outcome is CycleOutcome.EMPTY_ARCHITECTURE_SHELL

    restarted = ensure(workspace)
    assert restarted.outcome is CycleOutcome.B
    assert workspace.count("create_project_document") == 1
    assert list(workspace.documents) == [ARCHITECTURE_ID]


def test_state_a_without_permission_to_create_writes_nothing():
    workspace = ScriptedWorkspace()
    assert ensure(workspace, create_if_absent=False).outcome is CycleOutcome.A
    assert workspace.mutations == []


def test_empty_shell_is_completed_even_without_permission_to_create():
    workspace = with_empty_shell()
    assert ensure(workspace, create_if_absent=False).outcome is CycleOutcome.B
    assert workspace.count("create_project_document") == 0


def test_an_existing_b_is_returned_without_any_write():
    workspace = bootstrapped()
    assert ensure(workspace).outcome is CycleOutcome.B
    assert workspace.mutations == []


def test_an_existing_b_keeps_its_persisted_created_at_and_never_reads_the_clock():
    persisted = bootstrap_carrier(created_at="2020-01-02T03:04:05Z")
    workspace = ScriptedWorkspace()
    workspace.seed_root(ARCHITECTURE_ID, persisted)

    def unread_clock() -> datetime:
        raise AssertionError("rediscovery must not generate a created_at")

    found = ensure_bootstrap_architecture(
        workspace, PROJECT_ID, CYCLE, create_if_absent=True, clock=unread_clock
    )
    assert found.outcome is CycleOutcome.B
    assert workspace.content_of(ARCHITECTURE_ID) == persisted
    assert workspace.mutations == []


def test_one_bootstrap_write_reads_the_clock_exactly_once(origin):
    workspace = ORIGINS[origin]()
    readings: list[datetime] = []

    def counting_clock() -> datetime:
        readings.append(fixed_clock())
        return readings[-1]

    found = ensure_bootstrap_architecture(
        workspace, PROJECT_ID, CYCLE, create_if_absent=True, clock=counting_clock
    )
    assert found.outcome is CycleOutcome.B
    assert len(readings) == 1
    assert workspace.written == [PINNED_CARRIER]


@pytest.mark.parametrize(
    "seed",
    [
        lambda workspace: workspace.seed_root(STRAY_ID, stray_architecture()),
        lambda workspace: workspace.seed_root(ARCHITECTURE_ID, "human notes"),
        lambda workspace: workspace.place_foreign_document(
            ARCHITECTURE_ID,
            container_entity_type=PROJECT_TYPE_ID,
            container_entity_id="999",
        ),
    ],
)
def test_a_failed_bootstrap_gate_permits_zero_writes(seed):
    workspace = ScriptedWorkspace()
    seed(workspace)
    found = ensure(workspace)
    assert found.outcome is CycleOutcome.E
    assert workspace.mutations == []
    assert workspace.count("create_project_document") == 0
    assert workspace.count("write_document_content") == 0


def test_ambiguity_beside_an_empty_shell_leaves_the_shell_uncompleted():
    workspace = with_empty_shell()
    workspace.seed_root(STRAY_ID, stray_architecture())
    assert ensure(workspace).refusal_code is CycleResultCode.CYCLE_AMBIGUOUS
    assert workspace.mutations == []


# --------------------------------------------------------------------------
# Project Code before a bootstrap mutation (4.1.1)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("code", [None, "", "   ", "\n"])
def test_state_a_without_a_project_code_refuses_before_the_create(code):
    workspace = ScriptedWorkspace(project_record(code))
    refused = refusal(workspace)
    assert refused.code is CycleResultCode.FIBERY_READ_FAILED
    assert workspace.count("create_project_document") == 0
    assert workspace.mutations == []
    assert discover(workspace).outcome is CycleOutcome.A


@pytest.mark.parametrize("code", [None, "", "   "])
def test_empty_shell_without_a_project_code_refuses_before_the_write(code):
    workspace = ScriptedWorkspace(project_record(code))
    workspace.seed_root(ARCHITECTURE_ID)
    refused = refusal(workspace)
    assert refused.code is CycleResultCode.FIBERY_READ_FAILED
    assert workspace.count("write_document_content") == 0
    assert workspace.mutations == []
    assert discover(workspace).outcome is CycleOutcome.EMPTY_ARCHITECTURE_SHELL


def test_a_project_code_lost_after_discovery_still_refuses_before_the_write():
    """The Project is read again before the mutation, never reused."""
    workspace = with_empty_shell()
    workspace.before(
        "read_project",
        2,
        lambda: workspace.projects.update({PROJECT_ID: project_record(None)}),
    )
    refused = refusal(workspace)
    assert refused.code is CycleResultCode.FIBERY_READ_FAILED
    assert workspace.mutations == []


# --------------------------------------------------------------------------
# Structural Input Manifest classification (3.4.1) — never a Manifest write
# --------------------------------------------------------------------------


def manifest_missing_acceptance() -> str:
    body = dict(input_manifest_artifact()["body"])
    del body["acceptance"]
    return carrier(envelope(INPUT_MANIFEST, body))


def manifest_with_acceptance_mismatch() -> str:
    body = dict(input_manifest_artifact()["body"])
    body["acceptance"] = {**body["acceptance"], "manifest_digest": DIGEST_A}
    return carrier(envelope(INPUT_MANIFEST, body))


def manifest_cases() -> dict[str, tuple[str, CycleOutcome, CycleResultCode | None]]:
    malformed = CycleResultCode.ARTIFACT_MALFORMED
    return {
        "empty shell": (
            "",
            CycleOutcome.E,
            CycleResultCode.MANIFEST_SHELL_UNRECOVERABLE,
        ),
        "whitespace shell": (
            " \n",
            CycleOutcome.E,
            CycleResultCode.MANIFEST_SHELL_UNRECOVERABLE,
        ),
        "no fence": ("human notes", CycleOutcome.E, malformed),
        "another artifact type": (
            carrier(architecture_artifact()),
            CycleOutcome.E,
            malformed,
        ),
        "bad digest": (
            carrier({**input_manifest_artifact(), "artifact_digest": DIGEST_A}),
            CycleOutcome.E,
            malformed,
        ),
        "missing acceptance": (
            manifest_missing_acceptance(),
            CycleOutcome.E,
            malformed,
        ),
        "acceptance mismatch": (
            manifest_with_acceptance_mismatch(),
            CycleOutcome.E,
            CycleResultCode.MANIFEST_ACCEPTANCE_MISMATCH,
        ),
        "valid accepted": (carrier(input_manifest_artifact()), CycleOutcome.D, None),
    }


def test_no_manifest_document_is_state_b():
    assert discover(bootstrapped()).outcome is CycleOutcome.B


@pytest.mark.parametrize("label", sorted(manifest_cases()))
def test_manifest_child_is_classified_structurally(label):
    content, outcome, code = manifest_cases()[label]
    workspace = bootstrapped()
    workspace.seed_child(MANIFEST_ID, ARCHITECTURE_ID, content)
    found = discover(workspace)
    assert (found.outcome, found.refusal_code) == (outcome, code)
    assert workspace.mutations == []
    assert workspace.count("create_tsa_child_document") == 0


@pytest.mark.parametrize("label", sorted(manifest_cases()))
def test_ensure_never_writes_under_an_existing_manifest_child(label):
    content, outcome, code = manifest_cases()[label]
    workspace = bootstrapped()
    workspace.seed_child(MANIFEST_ID, ARCHITECTURE_ID, content)
    found = ensure(workspace)
    assert (found.outcome, found.refusal_code) == (outcome, code)
    assert workspace.mutations == []


def test_manifest_for_another_cycle_at_the_derived_child_id_is_malformed():
    other = dict(input_manifest_artifact())
    del other["artifact_digest"]
    other["project_entity_id"] = "proj-2"
    other["artifact_digest"] = compute_artifact_digest(other)
    workspace = bootstrapped()
    workspace.seed_child(MANIFEST_ID, ARCHITECTURE_ID, carrier(other))
    assert discover(workspace).refusal_code is CycleResultCode.ARTIFACT_MALFORMED


@pytest.mark.parametrize("parent", [None, "another-document"])
def test_manifest_id_outside_the_architecture_root_is_foreign(parent):
    workspace = bootstrapped()
    workspace.place_foreign_document(MANIFEST_ID, parent_document_id=parent)
    workspace.set_content(MANIFEST_ID, carrier(input_manifest_artifact()))
    found = discover(workspace)
    assert found.outcome is CycleOutcome.E
    assert found.refusal_code is CycleResultCode.CYCLE_FOREIGN_PROJECT


def applied_architecture() -> str:
    return architecture_document(architecture_artifact(**applied_group()))


def test_applied_architecture_with_a_valid_manifest_is_state_d():
    workspace = ScriptedWorkspace()
    workspace.seed_root(ARCHITECTURE_ID, applied_architecture())
    workspace.seed_child(
        MANIFEST_ID, ARCHITECTURE_ID, carrier(input_manifest_artifact())
    )
    assert discover(workspace).outcome is CycleOutcome.D


def test_applied_architecture_without_a_manifest_is_never_b():
    workspace = ScriptedWorkspace()
    workspace.seed_root(ARCHITECTURE_ID, applied_architecture())
    found = discover(workspace)
    assert found.outcome is CycleOutcome.E
    assert found.refusal_code is CycleResultCode.ARTIFACT_MALFORMED


# --------------------------------------------------------------------------
# The Manifest is classified BEFORE any bootstrap mutation (contract 14.1.2)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("label", sorted(manifest_cases()))
def test_manifest_child_overrides_the_empty_architecture_shell(label):
    content, outcome, code = manifest_cases()[label]
    workspace = with_empty_shell()
    workspace.seed_child(MANIFEST_ID, ARCHITECTURE_ID, content)
    found = discover(workspace)
    assert (found.outcome, found.refusal_code) == (outcome, code)
    assert workspace.mutations == []


@pytest.mark.parametrize("label", sorted(manifest_cases()))
def test_empty_shell_is_never_completed_over_an_existing_manifest_child(label):
    """E refuses and D is handed off unchanged: the shell is not repaired."""
    content, outcome, code = manifest_cases()[label]
    workspace = with_empty_shell()
    workspace.seed_child(MANIFEST_ID, ARCHITECTURE_ID, content)
    found = ensure(workspace)
    assert (found.outcome, found.refusal_code) == (outcome, code)
    assert workspace.mutations == []
    assert workspace.count("create_project_document") == 0
    assert workspace.count("write_document_content") == 0
    assert workspace.content_of(ARCHITECTURE_ID) == ""


@pytest.mark.parametrize("label", ["empty shell", "valid accepted"])
@pytest.mark.parametrize("parent", [None, "another-document", ARCHITECTURE_ID])
def test_state_a_with_a_stray_manifest_document_is_foreign_and_creates_nothing(
    parent, label
):
    """No valid root exists, so nothing at the Manifest id can be its child."""
    workspace = ScriptedWorkspace()
    workspace.place_foreign_document(MANIFEST_ID, parent_document_id=parent)
    workspace.set_content(MANIFEST_ID, manifest_cases()[label][0])
    for found in (discover(workspace), ensure(workspace)):
        assert found.outcome is CycleOutcome.E
        assert found.refusal_code is CycleResultCode.CYCLE_FOREIGN_PROJECT
    assert workspace.mutations == []
    assert workspace.count("create_project_document") == 0
    assert workspace.count("write_document_content") == 0
    assert ARCHITECTURE_ID not in workspace.documents


def test_manifest_placement_is_decided_before_its_content_is_read():
    workspace = ScriptedWorkspace()
    workspace.place_foreign_document(MANIFEST_ID, parent_document_id=None)
    workspace.set_content(MANIFEST_ID, carrier(input_manifest_artifact()))
    assert discover(workspace).refusal_code is CycleResultCode.CYCLE_FOREIGN_PROJECT
    assert workspace.count("read_document_content") == 0


def test_architecture_refusal_keeps_precedence_over_the_manifest_child():
    workspace = ScriptedWorkspace()
    workspace.seed_root(ARCHITECTURE_ID, "human notes")
    workspace.seed_child(MANIFEST_ID, ARCHITECTURE_ID, "")
    found = discover(workspace)
    assert found.refusal_code is CycleResultCode.ARTIFACT_MALFORMED
    assert ("resolve_placement", MANIFEST_ID) not in workspace.log


def test_ambiguity_keeps_precedence_over_the_manifest_child():
    workspace = with_empty_shell()
    workspace.seed_root(STRAY_ID, stray_architecture())
    workspace.seed_child(MANIFEST_ID, ARCHITECTURE_ID, "")
    found = ensure(workspace)
    assert found.refusal_code is CycleResultCode.CYCLE_AMBIGUOUS
    assert ("resolve_placement", MANIFEST_ID) not in workspace.log
    assert workspace.mutations == []


@pytest.mark.parametrize("build", [ScriptedWorkspace, with_empty_shell])
def test_manifest_id_is_resolved_before_any_bootstrap_mutation(build):
    workspace = build()
    assert ensure(workspace).outcome is CycleOutcome.B
    names = [name for name, _ in workspace.log]
    first_mutation = min(
        names.index(call)
        for call in ("create_project_document", "write_document_content")
        if call in names
    )
    assert workspace.log.index(("resolve_placement", MANIFEST_ID)) < first_mutation


# --------------------------------------------------------------------------
# A state A create is a revalidation boundary: the carrier write needs its own
# fresh gate (contract 14.2, spec 2.2.1)
# --------------------------------------------------------------------------


def after_create(workspace: ScriptedWorkspace, effect: Callable[[], None]) -> None:
    workspace.after("create_project_document", 1, effect)


def assert_created_but_never_written(workspace: ScriptedWorkspace) -> None:
    assert workspace.count("create_project_document") == 1
    assert workspace.count("write_document_content") == 0
    assert workspace.mutations == [f"create:{ARCHITECTURE_ID}"]
    assert workspace.content_of(ARCHITECTURE_ID) == ""


def test_state_a_runs_the_full_gate_again_between_the_create_and_the_write():
    workspace = ScriptedWorkspace()
    assert ensure(workspace).outcome is CycleOutcome.B
    names = [name for name, _ in workspace.log]
    create = names.index("create_project_document")
    write = names.index("write_document_content")
    assert create < write
    for gate_read in (
        ("read_project", PROJECT_ID),
        ("resolve_placement", ARCHITECTURE_ID),
        ("documents_attached_to_project", PUBLIC_ID),
        ("resolve_placement", MANIFEST_ID),
    ):
        assert gate_read in workspace.log[:create]
        assert gate_read in workspace.log[create + 1 : write]
    between = workspace.log[create + 1 : write]
    manifest_gate = between.index(("resolve_placement", MANIFEST_ID))
    assert between.index(("documents_attached_to_project", PUBLIC_ID)) < manifest_gate
    # The write contract's own fresh context and placement follow the gate.
    assert ("read_project", PROJECT_ID) in between[manifest_gate + 1 :]
    assert ("resolve_placement", ARCHITECTURE_ID) in between[manifest_gate + 1 :]
    assert ("resolve_placement", ARCHITECTURE_ID) in workspace.log[write + 1 :]
    assert "read_document_content" in names[write + 1 :]


@pytest.mark.parametrize("label", sorted(manifest_cases()))
def test_manifest_appearing_after_the_create_stops_the_carrier_write(label):
    content, outcome, code = manifest_cases()[label]
    workspace = ScriptedWorkspace()
    after_create(
        workspace,
        lambda: workspace.seed_child(MANIFEST_ID, ARCHITECTURE_ID, content),
    )
    found = ensure(workspace)
    assert (found.outcome, found.refusal_code) == (outcome, code)
    assert_created_but_never_written(workspace)
    again = discover(workspace)
    assert (again.outcome, again.refusal_code) == (outcome, code)


def test_conflict_appearing_after_the_create_stops_the_carrier_write():
    workspace = ScriptedWorkspace()
    after_create(workspace, lambda: workspace.seed_root(STRAY_ID, stray_architecture()))
    found = ensure(workspace)
    assert found.outcome is CycleOutcome.E
    assert found.refusal_code is CycleResultCode.CYCLE_AMBIGUOUS
    assert_created_but_never_written(workspace)


def test_root_relocated_after_the_create_is_foreign_before_any_content_access():
    workspace = ScriptedWorkspace()
    after_create(workspace, relocate(workspace))
    found = ensure(workspace)
    assert found.outcome is CycleOutcome.E
    assert found.refusal_code is CycleResultCode.CYCLE_FOREIGN_PROJECT
    assert_created_but_never_written(workspace)
    assert workspace.count("read_document_content") == 0


@pytest.mark.parametrize("code", [None, "", "   "])
def test_project_code_lost_after_the_create_refuses_the_carrier_write(code):
    workspace = ScriptedWorkspace()
    after_create(
        workspace,
        lambda: workspace.projects.update({PROJECT_ID: project_record(code)}),
    )
    refused = refusal(workspace)
    assert refused.code is CycleResultCode.FIBERY_READ_FAILED
    assert_created_but_never_written(workspace)
    assert discover(workspace).outcome is CycleOutcome.EMPTY_ARCHITECTURE_SHELL


def test_project_code_changed_after_the_create_is_the_one_written():
    """The carrier is built from the context read after the create."""
    workspace = ScriptedWorkspace()
    after_create(
        workspace,
        lambda: workspace.projects.update({PROJECT_ID: project_record("RENAMED")}),
    )
    assert ensure(workspace).outcome is CycleOutcome.B
    assert workspace.written == [
        bootstrap_carrier(replace(CONTEXT, project_code="RENAMED"))
    ]


def test_document_vanishing_after_the_create_is_fibery_write_failed():
    workspace = ScriptedWorkspace()
    after_create(workspace, lambda: workspace.documents.pop(ARCHITECTURE_ID))
    refused = refusal(workspace)
    assert refused.code is CycleResultCode.FIBERY_WRITE_FAILED
    assert refused.rediscovered.outcome is CycleOutcome.A
    assert workspace.count("create_project_document") == 1
    assert workspace.count("write_document_content") == 0


# --------------------------------------------------------------------------
# Unknown bootstrap mutation outcomes — rediscover, never retry blind (3.5)
# --------------------------------------------------------------------------


def calls_after(workspace: ScriptedWorkspace, call: str) -> list[tuple[str, str]]:
    names = [name for name, _ in workspace.log]
    return workspace.log[names.index(call) + 1 :]


def fail(message: str = "connection dropped") -> None:
    raise FiberyError(message)


def test_unknown_create_that_did_not_land_runs_full_discovery_and_does_not_retry():
    workspace = ScriptedWorkspace()
    workspace.before("create_project_document", 1, fail)
    refused = refusal(workspace)
    assert refused.code is CycleResultCode.FIBERY_WRITE_FAILED
    assert refused.rediscovered.outcome is CycleOutcome.A
    assert workspace.count("create_project_document") == 1
    assert workspace.count("write_document_content") == 0
    following = calls_after(workspace, "create_project_document")
    assert ("resolve_placement", ARCHITECTURE_ID) in following
    assert ("documents_attached_to_project", PUBLIC_ID) in following


def test_unknown_create_that_landed_empty_is_completed_without_a_second_create():
    workspace = ScriptedWorkspace()
    workspace.after("create_project_document", 1, fail)
    assert ensure(workspace).outcome is CycleOutcome.B
    assert workspace.count("create_project_document") == 1
    assert workspace.count("write_document_content") == 1
    following = calls_after(workspace, "create_project_document")
    listing = following.index(("documents_attached_to_project", PUBLIC_ID))
    write = [name for name, _ in following].index("write_document_content")
    assert listing < write


def test_unknown_create_that_landed_with_a_valid_carrier_is_b_with_no_retry():
    workspace = ScriptedWorkspace()

    def land_complete_then_fail() -> None:
        workspace.set_content(ARCHITECTURE_ID, bootstrap_carrier())
        fail()

    workspace.after("create_project_document", 1, land_complete_then_fail)
    assert ensure(workspace).outcome is CycleOutcome.B
    assert workspace.count("create_project_document") == 1
    assert workspace.count("write_document_content") == 0


def test_unknown_create_followed_by_a_conflict_is_refused():
    workspace = ScriptedWorkspace()

    def conflict_then_fail() -> None:
        workspace.seed_root(STRAY_ID, stray_architecture())
        fail()

    workspace.before("create_project_document", 1, conflict_then_fail)
    found = ensure(workspace)
    assert found.refusal_code is CycleResultCode.CYCLE_AMBIGUOUS
    assert workspace.count("create_project_document") == 1


def test_known_create_then_unknown_write_rediscovers_and_never_creates_again():
    workspace = ScriptedWorkspace()
    workspace.before("write_document_content", 1, fail)
    refused = refusal(workspace)
    assert refused.code is CycleResultCode.FIBERY_WRITE_FAILED
    assert refused.rediscovered.outcome is CycleOutcome.EMPTY_ARCHITECTURE_SHELL
    assert workspace.count("create_project_document") == 1
    assert workspace.count("write_document_content") == 1
    following = calls_after(workspace, "write_document_content")
    assert ("resolve_placement", ARCHITECTURE_ID) in following
    assert ("documents_attached_to_project", PUBLIC_ID) in following


def test_unknown_write_that_landed_is_b_after_full_rediscovery(origin):
    workspace = ORIGINS[origin]()
    workspace.after("write_document_content", 1, fail)
    assert ensure(workspace).outcome is CycleOutcome.B
    assert workspace.count("write_document_content") == 1
    assert workspace.count("create_project_document") == EXPECTED_CREATES[origin]
    assert ("documents_attached_to_project", PUBLIC_ID) in calls_after(
        workspace, "write_document_content"
    )


def test_unknown_write_followed_by_a_conflict_is_refused(origin):
    workspace = ORIGINS[origin]()

    def conflict_then_fail() -> None:
        workspace.seed_root(STRAY_ID, stray_architecture())
        fail()

    workspace.after("write_document_content", 1, conflict_then_fail)
    assert ensure(workspace).refusal_code is CycleResultCode.CYCLE_AMBIGUOUS
    assert workspace.count("write_document_content") == 1


def test_failed_readback_read_rediscovers_instead_of_reporting_success(origin):
    workspace = ORIGINS[origin]()
    workspace.before(
        "read_document_content", CONTENT_READS_BEFORE_WRITE[origin] + 1, fail
    )
    assert ensure(workspace).outcome is CycleOutcome.B
    assert workspace.count("write_document_content") == 1
    assert ("documents_attached_to_project", PUBLIC_ID) in calls_after(
        workspace, "write_document_content"
    )


def test_readback_that_keeps_failing_is_fibery_read_failed_not_success():
    workspace = with_empty_shell()
    workspace.after(
        "write_document_content",
        1,
        lambda: workspace.failures.update(
            {"read_document_content": FiberyError("still down")}
        ),
    )
    refused = refusal(workspace)
    assert refused.code is CycleResultCode.FIBERY_READ_FAILED
    assert workspace.count("write_document_content") == 1


def test_unknown_manifest_outcome_revalidates_the_cycle_before_the_child():
    workspace = bootstrapped()
    workspace.seed_child(
        MANIFEST_ID, ARCHITECTURE_ID, carrier(input_manifest_artifact())
    )
    found = rediscover_after_unknown_outcome(
        workspace, PROJECT_ID, CYCLE, DocumentKind.INPUT_MANIFEST
    )
    assert found.outcome is CycleOutcome.D
    root = workspace.log.index(("resolve_placement", ARCHITECTURE_ID))
    listing = workspace.log.index(("documents_attached_to_project", PUBLIC_ID))
    child = workspace.log.index(("resolve_placement", MANIFEST_ID))
    assert root < listing < child
    assert workspace.mutations == []


def test_unknown_manifest_outcome_with_no_child_is_b_and_creates_nothing():
    workspace = bootstrapped()
    found = rediscover_after_unknown_outcome(
        workspace, PROJECT_ID, CYCLE, DocumentKind.INPUT_MANIFEST
    )
    assert found.outcome is CycleOutcome.B
    assert workspace.mutations == []
    assert workspace.count("create_tsa_child_document") == 0


def test_unknown_manifest_outcome_stops_at_a_failed_cycle_level_revalidation():
    workspace = bootstrapped()
    workspace.seed_child(
        MANIFEST_ID, ARCHITECTURE_ID, carrier(input_manifest_artifact())
    )
    workspace.seed_root(STRAY_ID, stray_architecture())
    found = rediscover_after_unknown_outcome(
        workspace, PROJECT_ID, CYCLE, DocumentKind.INPUT_MANIFEST
    )
    assert found.refusal_code is CycleResultCode.CYCLE_AMBIGUOUS
    assert ("resolve_placement", MANIFEST_ID) not in workspace.log


def test_unknown_architecture_outcome_is_the_full_discovery():
    workspace = with_empty_shell()
    found = rediscover_after_unknown_outcome(
        workspace, PROJECT_ID, CYCLE, DocumentKind.ARCHITECTURE
    )
    assert found.outcome is CycleOutcome.EMPTY_ARCHITECTURE_SHELL
    assert ("documents_attached_to_project", PUBLIC_ID) in workspace.log
    assert workspace.mutations == []


@pytest.mark.parametrize(
    "target",
    [
        DocumentKind.PROCESS_RESULT,
        DocumentKind.REVIEW_RESULT,
        DocumentKind.HUMAN_DECISION,
    ],
)
def test_only_bootstrap_targets_are_rediscovered_here(target):
    with pytest.raises(ValueError):
        rediscover_after_unknown_outcome(bootstrapped(), PROJECT_ID, CYCLE, target)


# --------------------------------------------------------------------------
# Placement freshness (2.2.1) — nothing is reused across a mutation
# --------------------------------------------------------------------------


def relocate(workspace: ScriptedWorkspace) -> Callable[[], None]:
    def move() -> None:
        workspace.documents[ARCHITECTURE_ID].container_entity_id = "999"

    return move


def test_placement_changed_after_discovery_refuses_the_write():
    workspace = with_empty_shell()
    workspace.before("resolve_placement", DISCOVERY_RESOLVES + 1, relocate(workspace))
    refused = refusal(workspace)
    assert refused.code is CycleResultCode.CYCLE_FOREIGN_PROJECT
    assert workspace.count("write_document_content") == 0
    assert workspace.mutations == []


def test_placement_changed_by_the_write_is_detected_on_fresh_readback(origin):
    workspace = ORIGINS[origin]()
    workspace.after("write_document_content", 1, relocate(workspace))
    refused = refusal(workspace)
    assert refused.code is CycleResultCode.CYCLE_FOREIGN_PROJECT
    assert workspace.count("write_document_content") == 1
    following = [name for name, _ in calls_after(workspace, "write_document_content")]
    assert "resolve_placement" in following
    assert "read_document_content" not in following


def test_a_document_that_vanishes_after_the_write_is_fibery_write_failed(origin):
    """Absence at read-back is not an empty read-back: no shell is claimed."""
    workspace = ORIGINS[origin]()
    workspace.after(
        "write_document_content", 1, lambda: workspace.documents.pop(ARCHITECTURE_ID)
    )
    refused = refusal(workspace)
    assert refused.code is CycleResultCode.FIBERY_WRITE_FAILED
    assert "empty shell" not in str(refused)
    assert workspace.count("write_document_content") == 1
    assert workspace.count("create_project_document") == EXPECTED_CREATES[origin]
    following = [name for name, _ in calls_after(workspace, "write_document_content")]
    assert "read_document_content" not in following


def test_placement_and_project_are_read_again_on_each_side_of_the_write():
    workspace = with_empty_shell()
    ensure(workspace)
    names = [name for name, _ in workspace.log]
    write = names.index("write_document_content")
    for call in ("read_project", "resolve_placement"):
        assert call in names[:write]
        assert call in names[write + 1 :]
    before = names[:write]
    last_listing = len(before) - 1 - before[::-1].index("documents_attached_to_project")
    manifest_gate = workspace.log.index(("resolve_placement", MANIFEST_ID))
    assert last_listing < manifest_gate < write
    after_gate = workspace.log[manifest_gate + 1 : write]
    assert ("resolve_placement", ARCHITECTURE_ID) in after_gate
    assert ("read_project", PROJECT_ID) in after_gate
    assert ("resolve_placement", ARCHITECTURE_ID) in workspace.log[write + 1 :]


def test_state_a_create_is_preceded_by_a_fresh_absence_check():
    workspace = ScriptedWorkspace()
    ensure(workspace)
    names = [name for name, _ in workspace.log]
    create = names.index("create_project_document")
    manifest_gate = workspace.log.index(("resolve_placement", MANIFEST_ID))
    assert names.index("documents_attached_to_project") < manifest_gate < create
    after_gate = workspace.log[manifest_gate + 1 : create]
    assert ("resolve_placement", ARCHITECTURE_ID) in after_gate
    assert ("read_project", PROJECT_ID) in after_gate


def test_a_document_that_appears_before_the_create_is_not_created_twice():
    workspace = ScriptedWorkspace()
    workspace.before(
        "resolve_placement",
        DISCOVERY_RESOLVES + 1,
        lambda: workspace.seed_root(ARCHITECTURE_ID),
    )
    assert ensure(workspace).outcome is CycleOutcome.B
    assert workspace.count("create_project_document") == 0
    assert workspace.count("write_document_content") == 1


def test_content_that_appears_before_the_write_is_never_overwritten():
    workspace = with_empty_shell()
    discovery_reads = 1
    workspace.before(
        "read_document_content",
        discovery_reads + 1,
        lambda: workspace.set_content(ARCHITECTURE_ID, "human notes"),
    )
    found = ensure(workspace)
    assert found.refusal_code is CycleResultCode.ARTIFACT_MALFORMED
    assert workspace.count("write_document_content") == 0
    assert workspace.content_of(ARCHITECTURE_ID) == "human notes"


def test_a_shell_that_vanishes_before_the_write_is_not_recreated():
    workspace = with_empty_shell()
    workspace.before(
        "resolve_placement",
        DISCOVERY_RESOLVES + 1,
        lambda: workspace.documents.pop(ARCHITECTURE_ID),
    )
    refused = refusal(workspace)
    assert refused.code is CycleResultCode.FIBERY_WRITE_FAILED
    assert workspace.mutations == []
