"""Audit finding A3: an empty Result Document after a failed body write.

Every model-backed stage creates its Result Document first and writes the
body second. When the body write fails, the shell is left behind, the run
must say so by id, an ordinary retry must refuse without calling the model,
and only an operator naming the exact shell may complete it in place.

Every scenario drives the real entry points on the shared fake. External
changes are made through the fake's data and never appear in its mutation
log, which records processor writes only.
"""

from __future__ import annotations

import pytest

from processor_fake import FakeModelRuntime, build_workspace, candidate, model_output
from review_fake import build_review_workspace, review_output
from sdlc import cli
from sdlc.fibery_workspace import DocumentNode, FiberyError
from sdlc.model_runtime import ModelResponse
from sdlc.process_result import parse_process_result
from sdlc.processing_result import parse_processing_result
from sdlc.raw_processor import process_raw_requirement
from sdlc.results import ProcessResultCode as RawCode
from sdlc.results import StandardProcessResultCode as ProcessCode
from sdlc.results import StandardReviewResultCode as ReviewCode
from sdlc.review_result import parse_review_result
from sdlc.standard_processor import process_standard_requirement
from sdlc.standard_reviewer import review_standard_requirement
from standard_fake import analysis_output, build_standard_workspace, set_state

RAW_OUTPUT = model_output([candidate()])
PROCESS_OUTPUT = analysis_output()
REVIEW_OUTPUT = review_output()


# -- one adapter per stage ---------------------------------------------------


class Stage:
    """Everything a test needs to drive one stage through its real entry point."""

    def __init__(self, name, build, run, codes, suffix, parser, ready_state):
        self.name = name
        self.build = build
        self.run = run
        self.codes = codes
        self.suffix = suffix
        self.parser = parser
        self.ready_state = ready_state

    def __repr__(self):
        return self.name


def _raw_build():
    ws, raw, root = build_workspace()
    return ws, raw, root


def _standard_build():
    ws, std, root = build_standard_workspace()
    return ws, std, root


def _review_build():
    ws, requirement, root, _ = build_review_workspace()
    return ws, requirement, root


def _raw_run(ws, record, model, recover=None):
    return process_raw_requirement(ws, model, record.id, recover_empty_result=recover)


def _standard_run(ws, record, model, recover=None):
    return process_standard_requirement(
        ws, model, record.id, recover_empty_result=recover
    )


def _review_run(ws, record, model, recover=None):
    return review_standard_requirement(
        ws, model, record.id, recover_empty_result=recover
    )


def _plain_run(stage, ws, record, model):
    """The entry point as the pre-fix code accepts it: no recovery argument."""
    if stage.name == "raw":
        return process_raw_requirement(ws, model, record.id)
    if stage.name == "process":
        return process_standard_requirement(ws, model, record.id)
    return review_standard_requirement(ws, model, record.id)


RAW = Stage(
    "raw",
    _raw_build,
    _raw_run,
    {
        "ok": RawCode.RAW_REQUIREMENT_PROCESSED,
        "partial": RawCode.PARTIAL_PROCESSING,
        "invalid": RawCode.INVALID_PROCESSING_RESULT,
        "conflict": RawCode.PROCESSING_STATE_CONFLICT,
        "write_failed": RawCode.PROCESSING_RESULT_WRITE_FAILED,
        "read_failed": RawCode.FIBERY_READ_FAILED,
    },
    "Processing Result",
    parse_processing_result,
    "Review",
)
PROCESS = Stage(
    "process",
    _standard_build,
    _standard_run,
    {
        "ok": ProcessCode.REQUIREMENT_PROCESSED,
        "partial": ProcessCode.PARTIAL_PROCESSING,
        "invalid": ProcessCode.INVALID_PROCESSING_RESULT,
        "conflict": ProcessCode.PROCESSING_STATE_CONFLICT,
        "write_failed": ProcessCode.PROCESS_RESULT_WRITE_FAILED,
        "read_failed": ProcessCode.FIBERY_READ_FAILED,
    },
    "Process Result 0001",
    parse_process_result,
    "Review",
)
REVIEW = Stage(
    "review",
    _review_build,
    _review_run,
    {
        "ok": ReviewCode.REQUIREMENT_REVIEWED,
        "partial": ReviewCode.PARTIAL_REVIEW,
        "invalid": ReviewCode.INVALID_REVIEW_RESULT,
        "conflict": ReviewCode.REVIEW_STATE_CONFLICT,
        "write_failed": ReviewCode.REVIEW_RESULT_WRITE_FAILED,
        "read_failed": ReviewCode.FIBERY_READ_FAILED,
    },
    "Review Result 0001",
    parse_review_result,
    "Ready",
)
STAGES = [RAW, PROCESS, REVIEW]
OUTPUTS = {"raw": RAW_OUTPUT, "process": PROCESS_OUTPUT, "review": REVIEW_OUTPUT}


def model_for(stage, responses=None):
    return FakeModelRuntime(list(responses) if responses else [OUTPUTS[stage.name]])


def result_documents(ws, stage):
    return [d for d in ws.documents if d.name.endswith(stage.suffix)]


def processor_writes(ws, before):
    return [
        m
        for m in ws.mutations[before:]
        if m.split(" ")[0]
        in {
            "write_content",
            "create_child_document",
            "set_requirement_state",
            "set_requirement_type",
            "set_requirement_id",
            "create_requirement_document",
            "create_requirement",
            "add_derived_from",
        }
    ]


def leave_a_shell(stage):
    """Create succeeds, the body write fails: the audited failure."""
    ws, record, root = stage.build()
    ws.failures["write_document_content"] = FiberyError("body write failed")
    failure = _plain_run(stage, ws, record, model_for(stage))
    [shell] = result_documents(ws, stage)
    assert ws.content[shell.secret] == ""
    return ws, record, root, shell, failure


class ChangingModelRuntime:
    """Changes the workspace while the model 'runs', as another actor would."""

    def __init__(self, response, change):
        self.response = response
        self.change = change
        self.calls = []

    @property
    def was_invoked(self):
        return bool(self.calls)

    def run(self, prompt, context=""):
        self.calls.append(prompt)
        self.change()
        return ModelResponse(text=self.response, runtime="fake", model=None)


# -- the audited failure: reporting and the stuck retry ----------------------


@pytest.mark.parametrize("stage", STAGES, ids=repr)
def test_a_failed_body_write_reports_the_created_shell_by_id(stage):
    _, _, root, shell, failure = leave_a_shell(stage)

    assert failure.code is stage.codes["partial"]
    assert stage.codes["write_failed"].value in failure.details
    assert shell.id in " ".join(failure.created)
    assert shell.id in " ".join(failure.details)
    assert any("created" in item for item in failure.created)
    assert not any("persisted" in item for item in failure.created)
    assert shell.secret not in " ".join(failure.created + failure.details)
    assert shell.parent_document_id == root.id


@pytest.mark.parametrize("stage", STAGES, ids=repr)
def test_a_failed_body_write_leaves_no_downstream_mutation(stage):
    ws, record, _, _, _ = leave_a_shell(stage)
    writes = [m for m in ws.mutations if not m.startswith("create_child_document")]
    assert writes == [], "only the shell's creation was written"
    assert ws.requirements[record.id].state != stage.ready_state


@pytest.mark.parametrize("stage", STAGES, ids=repr)
def test_an_ordinary_retry_refuses_the_shell_without_the_model(stage):
    ws, record, _, shell, _ = leave_a_shell(stage)
    before = len(ws.mutations)

    model = model_for(stage)
    retry = _plain_run(stage, ws, record, model)

    assert retry.code is stage.codes["invalid"]
    assert not model.was_invoked
    assert shell.id in retry.message
    assert "--recover-empty-result" in retry.message
    assert ws.mutations[before:] == []
    assert ws.content[shell.secret] == ""


# -- explicit recovery -------------------------------------------------------


@pytest.mark.parametrize("stage", STAGES, ids=repr)
def test_naming_the_shell_completes_it_in_place(stage):
    ws, record, root, shell, _ = leave_a_shell(stage)
    model = model_for(stage)

    result = stage.run(ws, record, model, recover=shell.id)

    assert result.code is stage.codes["ok"], result
    assert len(model.calls) == 1
    [document] = result_documents(ws, stage)
    assert (document.id, document.name, document.parent_document_id) == (
        shell.id,
        shell.name,
        root.id,
    )
    stage.parser(ws.content[document.secret])
    assert any("persisted" in item for item in result.created)
    assert ws.requirements[record.id].state == stage.ready_state


def test_raw_recovery_then_creates_the_candidates():
    ws, raw, _, shell, _ = leave_a_shell(RAW)
    result = RAW.run(ws, raw, model_for(RAW), recover=shell.id)
    assert result.code is RawCode.RAW_REQUIREMENT_PROCESSED
    standards = [r for r in ws.requirements.values() if r.type_name == "Standard"]
    assert len(standards) == 1


def test_process_recovery_keeps_the_reserved_iteration_and_rewrites_the_root():
    ws, std, root, shell, _ = leave_a_shell(PROCESS)
    result = PROCESS.run(ws, std, model_for(PROCESS), recover=shell.id)
    assert result.code is ProcessCode.REQUIREMENT_PROCESSED
    assert result.iteration == 1
    assert parse_process_result(ws.content[shell.secret]).iteration == 1
    assert "## Requirement" in ws.content[root.secret]


def test_review_recovery_binds_to_the_current_reviewed_state():
    ws, requirement, _, shell, _ = leave_a_shell(REVIEW)
    result = REVIEW.run(ws, requirement, model_for(REVIEW), recover=shell.id)
    assert result.code is ReviewCode.REQUIREMENT_REVIEWED
    assert parse_review_result(ws.content[shell.secret]).iteration == 1


@pytest.mark.parametrize("stage", STAGES, ids=repr)
def test_recovery_persists_before_any_downstream_work(stage):
    """The read-back is the gate: a body that does not read back stops the run."""
    ws, record, _, shell, _ = leave_a_shell(stage)
    original = ws.read_document_content
    seen = {"n": 0}

    def hide_the_body(secret):
        content = original(secret)
        if secret == shell.secret and content:
            seen["n"] += 1
            if seen["n"] == 1:
                return ""  # the read-back sees nothing stored
        return content

    ws.read_document_content = hide_the_body
    before = len(ws.mutations)

    result = stage.run(ws, record, model_for(stage), recover=shell.id)

    assert result.code is not stage.codes["ok"]
    assert stage.codes["write_failed"].value in (result.code.value, *result.details)
    downstream = [
        m
        for m in ws.mutations[before:]
        if not m.startswith("write_content " + shell.secret)
    ]
    assert downstream == []
    assert ws.requirements[record.id].state != stage.ready_state


# -- safety: what recovery refuses -------------------------------------------


@pytest.mark.parametrize("stage", STAGES, ids=repr)
def test_a_non_empty_malformed_result_is_never_recovered_over(stage):
    ws, record, _, shell, _ = leave_a_shell(stage)
    ws.content[shell.secret] = '# partial\n\n```json\n{"truncated": tru'
    before = len(ws.mutations)
    model = model_for(stage)

    result = stage.run(ws, record, model, recover=shell.id)

    assert result.code is stage.codes["invalid"]
    assert not model.was_invoked
    assert ws.mutations[before:] == []
    assert ws.content[shell.secret].startswith("# partial")


@pytest.mark.parametrize("stage", STAGES, ids=repr)
def test_a_valid_result_is_never_overwritten_through_the_option(stage):
    ws, record, _, shell, _ = leave_a_shell(stage)
    stage.run(ws, record, model_for(stage), recover=shell.id)
    valid = ws.content[shell.secret]
    set_state(ws, record, "Process" if stage.name != "review" else "Review")
    before = len(ws.mutations)
    model = model_for(stage)

    result = stage.run(ws, record, model, recover=shell.id)

    assert not model.was_invoked
    assert result.code is not stage.codes["ok"]
    assert "--recover-empty-result" in result.message or result.code in {
        stage.codes["conflict"],
        RawCode.REQUIREMENT_NOT_IN_PROCESS,
    }
    assert ws.content[shell.secret] == valid
    assert ws.mutations[before:] == []


@pytest.mark.parametrize("stage", STAGES, ids=repr)
def test_a_wrong_document_id_is_refused(stage):
    ws, record, root, _, _ = leave_a_shell(stage)
    before = len(ws.mutations)
    model = model_for(stage)

    result = stage.run(ws, record, model, recover=root.id)

    assert result.code is stage.codes["conflict"]
    assert not model.was_invoked
    assert ws.mutations[before:] == []


@pytest.mark.parametrize("stage", STAGES, ids=repr)
def test_a_duplicate_shell_is_refused(stage):
    ws, record, root, shell, _ = leave_a_shell(stage)
    ws.documents.append(
        DocumentNode(
            id="dup-shell",
            name=shell.name,
            folder_id=None,
            entity_public_id=None,
            secret="dup-secret",
            parent_document_id=root.id,
        )
    )
    ws.content["dup-secret"] = ""
    before = len(ws.mutations)
    model = model_for(stage)

    result = stage.run(ws, record, model, recover=shell.id)

    assert result.code is stage.codes["conflict"]
    assert not model.was_invoked
    assert ws.mutations[before:] == []


@pytest.mark.parametrize("stage", [PROCESS, REVIEW], ids=repr)
def test_a_wrong_state_is_refused_before_anything_else(stage):
    ws, record, _, shell, _ = leave_a_shell(stage)
    set_state(ws, record, "Draft")
    model = model_for(stage)
    result = stage.run(ws, record, model, recover=shell.id)
    assert result.code.value.startswith("REQUIREMENT_NOT_IN_")
    assert not model.was_invoked


def test_a_historical_hole_beneath_a_newer_result_is_not_recovered():
    ws, std, root = build_standard_workspace()
    process_standard_requirement(ws, FakeModelRuntime([PROCESS_OUTPUT]), std.id)
    set_state(ws, std, "Process")
    ws.content[root.secret] += "\nEdited.\n"
    process_standard_requirement(
        ws, FakeModelRuntime([analysis_output({"title": "Second"})]), std.id
    )
    first, _ = sorted(
        result_documents(ws, PROCESS)
        + [d for d in ws.documents if d.name.endswith("Process Result 0002")],
        key=lambda d: d.name,
    )
    ws.content[first.secret] = ""  # a hole beneath iteration 2
    set_state(ws, std, "Process")
    ws.content[root.secret] += "\nEdited again.\n"
    before = len(ws.mutations)
    model = FakeModelRuntime([PROCESS_OUTPUT])

    result = process_standard_requirement(
        ws, model, std.id, recover_empty_result=first.id
    )

    assert result.code is ProcessCode.PROCESSING_STATE_CONFLICT
    assert "terminal" in result.message
    assert not model.was_invoked
    assert ws.mutations[before:] == []
    assert ws.content[first.secret] == ""


def test_a_shell_already_reviewed_downstream_is_not_regenerated():
    ws, std, _ = build_standard_workspace()
    process_standard_requirement(ws, FakeModelRuntime([PROCESS_OUTPUT]), std.id)
    review_standard_requirement(ws, FakeModelRuntime([REVIEW_OUTPUT]), std.id)
    [process_result] = result_documents(ws, PROCESS)
    ws.content[process_result.secret] = ""  # cleared after Review consumed it
    set_state(ws, std, "Process")
    model = FakeModelRuntime([PROCESS_OUTPUT])

    result = process_standard_requirement(
        ws, model, std.id, recover_empty_result=process_result.id
    )

    assert result.code is ProcessCode.PROCESSING_STATE_CONFLICT
    assert "already reviewed" in result.message
    assert not model.was_invoked
    assert ws.content[process_result.secret] == ""


def test_raw_with_visible_candidates_refuses_regeneration():
    ws, raw, _ = build_workspace()
    process_raw_requirement(ws, FakeModelRuntime([RAW_OUTPUT]), raw.id)
    [result_doc] = result_documents(ws, RAW)
    ws.content[result_doc.secret] = ""  # cleared after the candidates existed
    set_state(ws, raw, "Process")
    before = len(ws.mutations)
    model = FakeModelRuntime([RAW_OUTPUT])

    result = process_raw_requirement(
        ws, model, raw.id, recover_empty_result=result_doc.id
    )

    assert result.code is RawCode.PROCESSING_STATE_CONFLICT
    assert "already produced" in result.message
    assert not model.was_invoked
    assert ws.mutations[before:] == []
    assert len([r for r in ws.requirements.values() if r.type_name == "Standard"]) == 1


@pytest.mark.parametrize("stage", STAGES, ids=repr)
def test_a_shell_filled_during_the_model_call_is_preserved(stage):
    ws, record, _, shell, _ = leave_a_shell(stage)
    before = len(ws.mutations)

    def another_actor_fills_it():
        ws.content[shell.secret] = "# Filled by someone else\n"

    model = ChangingModelRuntime(OUTPUTS[stage.name], another_actor_fills_it)
    result = stage.run(ws, record, model, recover=shell.id)

    assert result.code is stage.codes["conflict"]
    assert len(model.calls) == 1
    assert ws.content[shell.secret] == "# Filled by someone else\n"
    assert ws.mutations[before:] == []
    assert ws.requirements[record.id].state != stage.ready_state


@pytest.mark.parametrize("stage", STAGES, ids=repr)
def test_a_shell_renamed_during_the_model_call_is_preserved(stage):
    ws, record, _, shell, _ = leave_a_shell(stage)
    before = len(ws.mutations)

    def another_actor_renames_it():
        index = next(i for i, d in enumerate(ws.documents) if d.id == shell.id)
        ws.documents[index] = DocumentNode(
            **{**shell.__dict__, "name": shell.name + " (old)"}
        )

    model = ChangingModelRuntime(OUTPUTS[stage.name], another_actor_renames_it)
    result = stage.run(ws, record, model, recover=shell.id)

    assert result.code is stage.codes["conflict"]
    assert ws.mutations[before:] == []
    assert ws.content[shell.secret] == ""


@pytest.mark.parametrize("stage", STAGES, ids=repr)
def test_a_failed_fresh_read_before_filling_writes_nothing(stage):
    ws, record, _, shell, _ = leave_a_shell(stage)
    original = ws.child_documents
    seen = {"n": 0}

    def fail_the_recheck(parent_id):
        seen["n"] += 1
        if seen["n"] == 2:  # 1 = context read, 2 = the pre-write recheck
            raise FiberyError("induced")
        return original(parent_id)

    ws.child_documents = fail_the_recheck
    before = len(ws.mutations)

    result = stage.run(ws, record, model_for(stage), recover=shell.id)

    assert result.code is stage.codes["read_failed"]
    assert ws.mutations[before:] == []
    assert ws.content[shell.secret] == ""


@pytest.mark.parametrize("stage", STAGES, ids=repr)
def test_repeated_recovery_failures_do_not_accumulate_shells(stage):
    ws, record, _, shell, _ = leave_a_shell(stage)
    for _ in range(3):
        stage.run(ws, record, FakeModelRuntime(["not json"]), recover=shell.id)
    assert [d.id for d in result_documents(ws, stage)] == [shell.id]
    assert ws.content[shell.secret] == ""


# -- an uncertain write: stored, but the response was lost -------------------


@pytest.mark.parametrize("stage", STAGES, ids=repr)
def test_a_body_stored_despite_a_raised_write_is_used_by_the_next_retry(stage):
    ws, record, _ = stage.build()
    original = ws.write_document_content
    seen = {"n": 0}

    def store_then_raise(secret, markdown):
        original(secret, markdown)
        seen["n"] += 1
        if seen["n"] == 1:
            raise FiberyError("response lost after storing")

    ws.write_document_content = store_then_raise
    failure = _plain_run(stage, ws, record, model_for(stage))
    assert failure.code is stage.codes["partial"]
    [document] = result_documents(ws, stage)
    stage.parser(ws.content[document.secret])
    ws.write_document_content = original
    stored = ws.content[document.secret]

    model = model_for(stage)
    retry = _plain_run(stage, ws, record, model)

    assert not model.was_invoked, "the stored body is recognised, not regenerated"
    assert ws.content[document.secret] == stored
    assert [d.id for d in result_documents(ws, stage)] == [document.id]
    expected = ReviewCode.NO_CHANGES_TO_REVIEW if stage is REVIEW else stage.codes["ok"]
    assert retry.code is expected


# -- the CLI surface ---------------------------------------------------------


@pytest.mark.parametrize("command", ["process", "normalize", "review"])
def test_the_recovery_option_is_accepted_by_each_model_backed_command(command):
    arguments = cli.build_parser().parse_args(
        [
            "project",
            "requirement",
            command,
            "--requirement",
            "x",
            "--recover-empty-result",
            "doc-1",
        ]
    )
    assert arguments.recover_empty_result == "doc-1"
    plain = cli.build_parser().parse_args(
        ["project", "requirement", command, "--requirement", "x"]
    )
    assert plain.recover_empty_result is None


@pytest.mark.parametrize("command", ["approve", "rework", "apply"])
def test_ready_and_apply_gain_no_recovery_option(command):
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(
            [
                "project",
                "requirement",
                command,
                "--requirement",
                "x",
                "--recover-empty-result",
                "doc-1",
            ]
        )
