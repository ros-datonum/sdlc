"""Staleness, iterations, no-change re-entry and retry.

A Review Result certifies one exact input. Everything here is about refusing to
apply a certification whose subject has moved, and about never asking the model
a second time for work that is already durable.
"""

from __future__ import annotations

from processor_fake import FakeModelRuntime
from review_fake import (
    build_review_workspace,
    confirm,
    finding,
    relation,
    relation_state,
    review_output,
    review_results,
    root_fingerprint,
    stored_review,
    verify_relation,
)
from sdlc.fibery_workspace import DocumentNode, FiberyError
from sdlc.process_result import (
    build_process_result,
    process_result_name,
    render_process_result,
)
from sdlc.results import StandardReviewResultCode as Code
from sdlc.review_result import review_result_name
from sdlc.standard_analysis import AnalysisResult, NormalizedRequirement
from sdlc.standard_reviewer import review_standard_requirement
from standard_fake import normalized, set_state

REQUIREMENT_ID = "SDLC-FR-0031"


def run(ws, requirement, responses=None):
    model = FakeModelRuntime(responses=responses or [review_output()])
    return review_standard_requirement(ws, model, requirement.id), model


def add_process_iteration(ws, root, iteration, title="Rewritten"):
    """Append a later Process Result, as a second Process run would."""
    result = build_process_result(
        requirement_id=REQUIREMENT_ID,
        iteration=iteration,
        input_fingerprint=f"input-{iteration}",
        analysis=AnalysisResult(
            normalized=NormalizedRequirement(**normalized(title=title)),
            analysis={},
            findings=(),
            proposed_relations=(),
        ),
    )
    secret = f"process-secret-{iteration}"
    ws.documents.append(
        DocumentNode(
            id=f"process-doc-{iteration}",
            name=process_result_name(REQUIREMENT_ID, iteration),
            folder_id=None,
            entity_public_id=None,
            secret=secret,
            parent_document_id=root.id,
        )
    )
    ws.content[secret] = render_process_result(result)
    return result


# -- identical re-entry -----------------------------------------------------


def test_identical_bindings_return_no_changes_to_review():
    ws, requirement, _, _ = build_review_workspace()
    run(ws, requirement)
    set_state(ws, requirement, "Review")
    before = len(ws.mutations)

    result, model = run(ws, requirement)
    assert result.code is Code.NO_CHANGES_TO_REVIEW
    assert result.is_normal
    assert not model.was_invoked
    assert ws.mutations[before:] == []


def test_no_changes_leaves_the_state_in_review():
    """It does not guess whether a human returned it or a transition failed."""
    ws, requirement, _, _ = build_review_workspace()
    run(ws, requirement)
    set_state(ws, requirement, "Review")
    run(ws, requirement)
    assert ws.requirements[requirement.id].state == "Review"


def test_no_changes_creates_no_new_review_result():
    ws, requirement, _, _ = build_review_workspace()
    run(ws, requirement)
    set_state(ws, requirement, "Review")
    run(ws, requirement)
    assert len(review_results(ws)) == 1


def test_no_changes_touches_no_document_and_no_relation():
    ws, requirement, _, _ = build_review_workspace(relations=(relation(),))
    run(ws, requirement, [review_output(relation_verifications=[verify_relation()])])
    set_state(ws, requirement, "Review")
    document_before = dict(ws.content)
    relations_before = relation_state(ws)

    run(ws, requirement)
    assert ws.content == document_before
    assert relation_state(ws) == relations_before


def test_no_changes_still_reports_the_standing_verdict():
    ws, requirement, _, _ = build_review_workspace(findings=(finding(),))
    run(ws, requirement, [review_output(finding_verifications=[confirm()])])
    set_state(ws, requirement, "Review")
    result, _ = run(ws, requirement)
    assert result.verdict == "NEEDS_WORK"
    assert result.iteration == 1


# -- new iterations ---------------------------------------------------------


def test_an_edited_document_starts_a_new_review_iteration():
    ws, requirement, root, _ = build_review_workspace()
    run(ws, requirement)
    set_state(ws, requirement, "Review")
    ws.content[root.secret] += "\n## Extra\n\nAdded by a human.\n"

    result, model = run(ws, requirement)
    assert result.code is Code.REQUIREMENT_REVIEWED
    assert result.iteration == 2
    assert model.was_invoked
    assert [d.name for d in review_results(ws)] == [
        review_result_name(REQUIREMENT_ID, 1),
        review_result_name(REQUIREMENT_ID, 2),
    ]


def test_a_new_process_iteration_starts_a_new_review_iteration():
    ws, requirement, root, _ = build_review_workspace()
    run(ws, requirement)
    set_state(ws, requirement, "Review")
    add_process_iteration(ws, root, 2)

    result, model = run(ws, requirement)
    assert result.iteration == 2
    assert model.was_invoked
    assert stored_review(ws).reviewed_process_iteration == 2


def test_earlier_review_results_are_never_modified():
    ws, requirement, root, _ = build_review_workspace()
    run(ws, requirement)
    first = review_results(ws)[0]
    before = ws.content[first.secret]

    set_state(ws, requirement, "Review")
    ws.content[root.secret] += "\nEdited.\n"
    run(ws, requirement)
    assert ws.content[first.secret] == before
    assert len(review_results(ws)) == 2


def test_revision_is_unchanged_across_a_second_iteration():
    ws, requirement, root, _ = build_review_workspace()
    before = ws.requirements[requirement.id].revision
    run(ws, requirement)
    set_state(ws, requirement, "Review")
    ws.content[root.secret] += "\nEdited.\n"
    run(ws, requirement)
    assert ws.requirements[requirement.id].revision == before


# -- staleness --------------------------------------------------------------


class EditsDocumentAfterReview:
    """A reviewer that edits the Root Document while it is being reviewed.

    Models the real race: a human saves the document between the read and the
    state transition.
    """

    def __init__(self, ws, root, response):
        self.ws = ws
        self.root = root
        self.response = response
        self.calls = []

    def run(self, prompt, context=""):
        self.calls.append({"prompt": prompt, "context": context})
        self.ws.content[self.root.secret] += "\n\nEdited mid-review.\n"
        from sdlc.model_runtime import ModelResponse

        return ModelResponse(text=self.response, runtime="fake", model=None)

    @property
    def was_invoked(self):
        return bool(self.calls)


def test_a_document_edited_during_review_is_stale():
    ws, requirement, root, _ = build_review_workspace()
    model = EditsDocumentAfterReview(ws, root, review_output())
    result = review_standard_requirement(ws, model, requirement.id)

    assert result.code is Code.REVIEW_RESULT_STALE
    assert "was edited after the review" in " ".join(result.details)
    assert ws.requirements[requirement.id].state == "Review"


class AddsProcessIterationDuringReview:
    def __init__(self, ws, root, response):
        self.ws = ws
        self.root = root
        self.response = response
        self.calls = []

    def run(self, prompt, context=""):
        self.calls.append({"prompt": prompt, "context": context})
        add_process_iteration(self.ws, self.root, 2)
        from sdlc.model_runtime import ModelResponse

        return ModelResponse(text=self.response, runtime="fake", model=None)

    @property
    def was_invoked(self):
        return bool(self.calls)


def test_a_new_process_iteration_during_review_is_stale():
    ws, requirement, root, _ = build_review_workspace()
    model = AddsProcessIterationDuringReview(ws, root, review_output())
    result = review_standard_requirement(ws, model, requirement.id)

    assert result.code is Code.REVIEW_RESULT_STALE
    assert "Process ran again" in " ".join(result.details)
    assert ws.requirements[requirement.id].state == "Review"


class RewritesProcessOutputDuringReview:
    """The same iteration number, a different output fingerprint."""

    def __init__(self, ws, response):
        self.ws = ws
        self.response = response
        self.calls = []

    def run(self, prompt, context=""):
        self.calls.append({"prompt": prompt, "context": context})
        result = build_process_result(
            requirement_id=REQUIREMENT_ID,
            iteration=1,
            input_fingerprint="input-1",
            analysis=AnalysisResult(
                normalized=NormalizedRequirement(**normalized(title="Different")),
                analysis={},
                findings=(),
                proposed_relations=(),
            ),
        )
        self.ws.content["process-secret-1"] = render_process_result(result)
        from sdlc.model_runtime import ModelResponse

        return ModelResponse(text=self.response, runtime="fake", model=None)

    @property
    def was_invoked(self):
        return bool(self.calls)


def test_a_changed_process_output_fingerprint_is_stale():
    ws, requirement, _, _ = build_review_workspace()
    model = RewritesProcessOutputDuringReview(ws, review_output())
    result = review_standard_requirement(ws, model, requirement.id)

    assert result.code is Code.REVIEW_RESULT_STALE
    assert "no longer produces the output" in " ".join(result.details)
    assert ws.requirements[requirement.id].state == "Review"


def test_a_stale_review_result_is_kept_not_deleted():
    """The evidence stays; only the certification is refused."""
    ws, requirement, root, _ = build_review_workspace()
    model = EditsDocumentAfterReview(ws, root, review_output())
    result = review_standard_requirement(ws, model, requirement.id)

    assert result.code is Code.REVIEW_RESULT_STALE
    assert len(review_results(ws)) == 1
    assert result.created  # reported, so a human knows it is there


def test_a_stale_result_never_writes_a_relation():
    ws, requirement, root, _ = build_review_workspace(relations=(relation(),))
    before = relation_state(ws)
    model = EditsDocumentAfterReview(
        ws, root, review_output(relation_verifications=[verify_relation()])
    )
    result = review_standard_requirement(ws, model, requirement.id)

    assert result.code is Code.REVIEW_RESULT_STALE
    assert relation_state(ws) == before


def test_a_stale_result_never_writes_the_root_document():
    ws, requirement, root, _ = build_review_workspace()
    model = EditsDocumentAfterReview(ws, root, review_output())
    review_standard_requirement(ws, model, requirement.id)
    assert [m for m in ws.mutations if m == f"write_content {root.secret}"] == []


def test_a_stale_result_does_not_call_the_model_again():
    ws, requirement, root, _ = build_review_workspace()
    model = EditsDocumentAfterReview(ws, root, review_output())
    review_standard_requirement(ws, model, requirement.id)
    assert len(model.calls) == 1


def test_the_next_run_reviews_the_new_state_as_a_fresh_iteration():
    """Recovery from staleness is a normal new iteration, not a repair."""
    ws, requirement, root, _ = build_review_workspace()
    review_standard_requirement(
        ws, EditsDocumentAfterReview(ws, root, review_output()), requirement.id
    )
    result, _ = run(ws, requirement)
    assert result.code is Code.REQUIREMENT_REVIEWED
    assert result.iteration == 2
    assert stored_review(ws).reviewed_document_fingerprint == root_fingerprint(ws, root)
    assert ws.requirements[requirement.id].state == "Ready"


# -- failures and retry -----------------------------------------------------


def test_a_failed_ready_transition_never_reports_success():
    ws, requirement, _, _ = build_review_workspace()
    ws.failures["set_requirement_state"] = FiberyError("workflow unavailable")

    result, _ = run(ws, requirement)
    assert result.code is Code.PARTIAL_REVIEW
    assert not result.is_normal
    assert ws.requirements[requirement.id].state == "Review"
    assert len(review_results(ws)) == 1


def test_after_a_failed_transition_a_retry_does_not_call_the_model():
    """The durable artifact is what makes the second model call unnecessary."""
    ws, requirement, _, _ = build_review_workspace()
    ws.failures["set_requirement_state"] = FiberyError("workflow unavailable")
    run(ws, requirement)

    result, model = run(ws, requirement)
    assert result.code is Code.NO_CHANGES_TO_REVIEW
    assert not model.was_invoked
    assert ws.requirements[requirement.id].state == "Review"
    assert len(review_results(ws)) == 1


def test_a_failure_before_persistence_leaves_nothing_durable():
    ws, requirement, _, _ = build_review_workspace()
    ws.failures["create_child_document"] = FiberyError("views unavailable")

    result, model = run(ws, requirement)
    assert result.code is Code.REVIEW_RESULT_WRITE_FAILED
    assert model.was_invoked
    assert review_results(ws) == []
    assert ws.requirements[requirement.id].state == "Review"


def test_a_retry_after_a_failure_before_persistence_may_call_the_model_again():
    ws, requirement, _, _ = build_review_workspace()
    ws.failures["create_child_document"] = FiberyError("views unavailable")
    run(ws, requirement)

    result, model = run(ws, requirement)
    assert result.code is Code.REQUIREMENT_REVIEWED
    assert model.was_invoked
    assert ws.requirements[requirement.id].state == "Ready"


def test_a_model_runtime_failure_is_reported_and_mutates_nothing():
    ws, requirement, _, _ = build_review_workspace()
    from sdlc.model_runtime import ModelRuntimeError

    model = FakeModelRuntime(error=ModelRuntimeError("claude is not authenticated"))
    result = review_standard_requirement(ws, model, requirement.id)

    assert result.code is Code.MODEL_RUNTIME_FAILED
    assert ws.mutations == []
    assert ws.requirements[requirement.id].state == "Review"


def test_invalid_reviewer_output_persists_nothing():
    ws, requirement, _, _ = build_review_workspace(findings=(finding(),))
    result, _ = run(ws, requirement, [review_output()])  # leaves the finding unverified

    assert result.code is Code.INVALID_MODEL_OUTPUT
    assert "unverified" in " ".join(result.details)
    assert ws.mutations == []


def test_a_state_read_back_that_disagrees_fails_validation():
    ws, requirement, _, _ = build_review_workspace()

    def refuse(entity_id, state):
        """Accepts the write, but the entity never actually changes."""
        ws.mutations.append(f"set_requirement_state {entity_id} {state}")

    ws.set_requirement_state = refuse
    result, _ = run(ws, requirement)

    assert result.code is Code.PARTIAL_REVIEW
    assert "VALIDATION_FAILED" in result.details
    assert ws.requirements[requirement.id].state == "Review"


# -- ambiguous history ------------------------------------------------------


def test_two_review_results_for_one_iteration_refuse_to_guess():
    ws, requirement, root, _ = build_review_workspace()
    run(ws, requirement)
    duplicate = review_results(ws)[0]
    ws.documents.append(
        DocumentNode(
            id="duplicate-review",
            name=duplicate.name,
            folder_id=None,
            entity_public_id=None,
            secret="duplicate-secret",
            parent_document_id=root.id,
        )
    )
    ws.content["duplicate-secret"] = ws.content[duplicate.secret]

    set_state(ws, requirement, "Review")
    result, model = run(ws, requirement)
    assert result.code is Code.REVIEW_STATE_CONFLICT
    assert not model.was_invoked
    assert ws.requirements[requirement.id].state == "Review"


def test_two_process_results_for_one_iteration_refuse_to_review():
    ws, requirement, root, _ = build_review_workspace()
    ws.documents.append(
        DocumentNode(
            id="duplicate-process",
            name=process_result_name(REQUIREMENT_ID, 1),
            folder_id=None,
            entity_public_id=None,
            secret="duplicate-process-secret",
            parent_document_id=root.id,
        )
    )
    ws.content["duplicate-process-secret"] = ws.content["process-secret-1"]

    result, model = run(ws, requirement)
    assert result.code is Code.INVALID_PROCESS_RESULT
    assert not model.was_invoked
    assert ws.mutations == []


def test_a_malformed_process_result_is_not_reviewed_against():
    ws, requirement, _, _ = build_review_workspace()
    ws.content["process-secret-1"] = "# Not a Process Result\n\nnothing here\n"

    result, model = run(ws, requirement)
    assert result.code is Code.INVALID_PROCESS_RESULT
    assert not model.was_invoked
    assert ws.mutations == []


def test_a_malformed_review_result_is_not_trusted():
    ws, requirement, _, _ = build_review_workspace()
    run(ws, requirement)
    node = review_results(ws)[0]
    ws.content[node.secret] = "# Review Result 0001\n\ncorrupted\n"

    set_state(ws, requirement, "Review")
    result, model = run(ws, requirement)
    assert result.code is Code.INVALID_REVIEW_RESULT
    assert not model.was_invoked
    assert ws.requirements[requirement.id].state == "Review"


def test_a_review_result_with_a_contradictory_verdict_is_not_trusted():
    ws, requirement, _, _ = build_review_workspace(findings=(finding(),))
    run(ws, requirement, [review_output(finding_verifications=[confirm()])])
    node = review_results(ws)[0]
    ws.content[node.secret] = ws.content[node.secret].replace(
        '"NEEDS_WORK"', '"PASS"', 1
    )

    set_state(ws, requirement, "Review")
    result, model = run(ws, requirement)
    assert result.code is Code.INVALID_REVIEW_RESULT
    assert not model.was_invoked
