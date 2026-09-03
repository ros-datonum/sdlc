"""Post-write validation: Markdown fidelity and the RAW state transition."""

from processor_fake import (
    FakeModelRuntime,
    build_workspace,
    candidate,
    model_output,
    reserialize_like_fibery,
)
from sdlc.fibery_workspace import RequirementRecord
from sdlc.raw_processor import process_raw_requirement
from sdlc.results import ProcessResultCode

BULLETED = candidate(
    requirement="The runtime must:\n- refuse API keys\n- refuse OpenRouter",
    constraints_edge_cases="Applies when:\n- offline\n- rate limited",
    non_goals="- credential rotation\n- key storage",
)


def reset_to_process(ws, raw):
    ws.requirements[raw.id] = RequirementRecord(
        **{**ws.requirements[raw.id].__dict__, "state": "Process"}
    )


def standards(ws):
    return [r for r in ws.requirements.values() if r.type_name == "Standard"]


# -- Markdown reserialization ----------------------------------------------


def test_the_fake_reserializes_like_fibery():
    """Pins every verified behaviour the regressions below depend on.

    Each was confirmed against the live workspace by writing the case to a
    Document and reading it back.
    """
    # A "-" bullet is returned as "*", and the trailing newline is stripped.
    assert reserialize_like_fibery("- one\n  - two\n") == "* one\n  * two"
    # A blank line is inserted between a paragraph and a list following it.
    assert reserialize_like_fibery("Intro:\n- one\n") == "Intro:\n\n* one"
    # And after a heading followed directly by anything.
    assert reserialize_like_fibery("## S\nBody.\n") == "## S\n\nBody."
    # A soft line break inside a paragraph becomes a literal <br>.
    assert reserialize_like_fibery("a a\nb b\n") == "a a<br>b b"
    # A wrapped list item is joined the same way, and its indent is dropped.
    assert reserialize_like_fibery("- a a,\n  b b\n- c\n") == "* a a,<br>b b\n* c"
    # A real paragraph break is not a soft break and is preserved.
    assert reserialize_like_fibery("One.\n\nTwo.\n") == "One.\n\nTwo."
    # A fenced block is returned verbatim: this is where artifact JSON lives.
    fenced = '# X\n\n```json\n{\n  "a": 1\n}\n```\n'
    assert reserialize_like_fibery(fenced) == fenced.rstrip("\n")


def test_a_candidate_with_bullet_lists_validates_and_reaches_review():
    """The blocking defect: bullets read back as "*" and failed forever."""
    ws, raw, _ = build_workspace()

    result = process_raw_requirement(
        ws, FakeModelRuntime([model_output([BULLETED])]), raw.id
    )

    assert result.code is ProcessResultCode.RAW_REQUIREMENT_PROCESSED
    assert ws.requirements[raw.id].state == "Review"


def test_bullets_survive_in_the_stored_document():
    ws, raw, _ = build_workspace()

    process_raw_requirement(ws, FakeModelRuntime([model_output([BULLETED])]), raw.id)

    [std] = standards(ws)
    [doc] = ws.documents_attached_to_requirement(std.public_id)
    assert "refuse OpenRouter" in ws.content[doc.secret]
    assert "credential rotation" in ws.content[doc.secret]


def test_bulleted_candidates_are_not_permanently_stuck():
    """Previously a retry rewrote the same content and failed identically."""
    ws, raw, _ = build_workspace()
    process_raw_requirement(ws, FakeModelRuntime([model_output([BULLETED])]), raw.id)
    reset_to_process(ws, raw)

    model = FakeModelRuntime([model_output([BULLETED])])
    result = process_raw_requirement(ws, model, raw.id)

    assert result.code is ProcessResultCode.RAW_REQUIREMENT_PROCESSED
    assert not model.was_invoked
    assert len(standards(ws)) == 1


def test_every_section_is_compared_not_only_the_requirement():
    """Validation covers the whole rendered document."""
    ws, raw, _ = build_workspace()
    original = ws.read_document_content

    def lose_a_later_section(secret):
        return original(secret).replace("Does not do the other thing.", "")

    ws.read_document_content = lose_a_later_section

    result = process_raw_requirement(
        ws, FakeModelRuntime([model_output([candidate()])]), raw.id
    )

    assert result.code is ProcessResultCode.PARTIAL_PROCESSING
    assert any("content does not match" in d for d in result.details)


def test_real_content_loss_is_still_rejected():
    ws, raw, _ = build_workspace()
    original = ws.read_document_content

    def truncate(secret):
        text = original(secret)
        return text[: len(text) // 2] if "## Non-Goals" in text else text

    ws.read_document_content = truncate

    result = process_raw_requirement(
        ws, FakeModelRuntime([model_output([candidate()])]), raw.id
    )

    assert result.code is ProcessResultCode.PARTIAL_PROCESSING
    assert ws.requirements[raw.id].state == "Process"


def test_changed_wording_is_still_rejected():
    ws, raw, _ = build_workspace()
    original = ws.read_document_content

    def tamper(secret):
        return original(secret).replace("must do the thing", "must not do the thing")

    ws.read_document_content = tamper

    result = process_raw_requirement(
        ws, FakeModelRuntime([model_output([candidate()])]), raw.id
    )

    assert result.code is ProcessResultCode.PARTIAL_PROCESSING


# -- RAW transition read-back ----------------------------------------------


def test_a_successful_transition_is_confirmed_by_read_back():
    ws, raw, _ = build_workspace()

    result = process_raw_requirement(
        ws, FakeModelRuntime([model_output([candidate()])]), raw.id
    )

    assert result.code is ProcessResultCode.RAW_REQUIREMENT_PROCESSED
    assert ws.requirements[raw.id].state == "Review"
    assert "read_requirement" in ws.calls


def test_a_silently_ignored_transition_is_not_reported_as_success():
    ws, raw, _ = build_workspace()
    real = ws.set_requirement_state

    def swallow(entity_id, state):
        if entity_id == raw.id and state == "Review":
            return
        return real(entity_id, state)

    ws.set_requirement_state = swallow

    result = process_raw_requirement(
        ws, FakeModelRuntime([model_output([candidate()])]), raw.id
    )

    assert result.code is not ProcessResultCode.RAW_REQUIREMENT_PROCESSED
    assert ws.requirements[raw.id].state == "Process"
    assert any("still in State" in d for d in result.details)


def test_durable_state_survives_a_failed_transition():
    ws, raw, _ = build_workspace()
    real = ws.set_requirement_state
    ws.set_requirement_state = lambda e, s: (
        None if (e == raw.id and s == "Review") else real(e, s)
    )

    result = process_raw_requirement(
        ws, FakeModelRuntime([model_output([candidate()])]), raw.id
    )

    assert len(standards(ws)) == 1
    assert [d for d in ws.documents if d.name.endswith("Processing Result")]
    assert any("Standard candidate" in item for item in result.created)


def test_retry_after_a_failed_transition_resumes_and_completes():
    ws, raw, _ = build_workspace()
    real = ws.set_requirement_state
    ws.set_requirement_state = lambda e, s: (
        None if (e == raw.id and s == "Review") else real(e, s)
    )
    first = process_raw_requirement(
        ws, FakeModelRuntime([model_output([candidate()])]), raw.id
    )
    assert first.code is not ProcessResultCode.RAW_REQUIREMENT_PROCESSED

    ws.set_requirement_state = real
    model = FakeModelRuntime([model_output([candidate()])])
    result = process_raw_requirement(ws, model, raw.id)

    assert result.code is ProcessResultCode.RAW_REQUIREMENT_PROCESSED
    assert not model.was_invoked, "the Processing Result must be reused"
    assert len(standards(ws)) == 1, "the existing candidate must be reused"
    assert ws.requirements[raw.id].state == "Review"
