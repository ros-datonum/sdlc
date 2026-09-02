"""The `sdlc project requirement review` command surface.

The distinction the output has to carry is that a BLOCKING verdict is a
successful run: the exit code reports whether the review executed, never
whether the Requirement is good.
"""

from __future__ import annotations

import io

import pytest

from sdlc import cli
from sdlc.results import StandardReviewResult
from sdlc.results import StandardReviewResultCode as Code


def render(result):
    stream = io.StringIO()
    cli.render_review_result(result, stream)
    return stream.getvalue()


def reviewed(**changes):
    base = {
        "code": Code.REQUIREMENT_REVIEWED,
        "message": "SDLC-FR-0031 reviewed, iteration 1; verdict BLOCKING.",
        "requirement_id": "SDLC-FR-0031",
        "iteration": 1,
        "verdict": "BLOCKING",
        "model_invoked": True,
    }
    return StandardReviewResult(**{**base, **changes})


# -- argument parsing -------------------------------------------------------


def test_review_takes_a_requirement_and_optional_overrides():
    arguments = cli.build_parser().parse_args(
        [
            "project",
            "requirement",
            "review",
            "--requirement",
            "entity-uuid",
            "--runtime",
            "codex",
            "--model",
            "some-model",
        ]
    )
    assert arguments.requirement == "entity-uuid"
    assert (arguments.runtime, arguments.model) == ("codex", "some-model")


def test_the_requirement_is_required():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["project", "requirement", "review"])


def test_review_is_separate_from_normalize():
    """Two capabilities, two commands: reviewing never normalizes."""
    parser = cli.build_parser()
    review = parser.parse_args(
        ["project", "requirement", "review", "--requirement", "x"]
    )
    normalize = parser.parse_args(
        ["project", "requirement", "normalize", "--requirement", "x"]
    )
    assert review.handler is not normalize.handler


# -- output -----------------------------------------------------------------


def test_the_result_code_comes_first():
    assert render(reviewed()).startswith("REQUIREMENT_REVIEWED\n")


def test_a_blocking_verdict_is_still_a_successful_run():
    result = reviewed()
    assert result.is_normal
    assert "BLOCKING" in render(result)


@pytest.mark.parametrize(
    ("code", "normal"),
    [
        (Code.REQUIREMENT_REVIEWED, True),
        (Code.NO_CHANGES_TO_REVIEW, True),
        (Code.REVIEW_RESULT_STALE, False),
        (Code.PARTIAL_REVIEW, False),
        (Code.NOT_A_STANDARD_REQUIREMENT, False),
        (Code.NO_PROCESS_RESULT, False),
        (Code.INVALID_MODEL_OUTPUT, False),
    ],
)
def test_only_the_two_completed_outcomes_are_normal(code, normal):
    assert StandardReviewResult(code=code, message="m").is_normal is normal


def test_blocking_and_warning_findings_are_listed_for_the_human():
    output = render(
        reviewed(
            blocking=("NOT_TESTABLE: no measurable threshold",),
            warnings=("confirmed Process finding [0]: still ambiguous",),
        )
    )
    assert "Blocking:" in output
    assert "no measurable threshold" in output
    assert "Warnings:" in output


def test_relations_are_labelled_as_not_written():
    output = render(
        reviewed(relations=("CONFIRMED DEPENDS_ON SDLC-FR-0002: real dependency",))
    )
    assert "none written to Fibery" in output
    assert "SDLC-FR-0002" in output


def test_no_changes_reports_only_the_code_and_message():
    output = render(
        StandardReviewResult(
            code=Code.NO_CHANGES_TO_REVIEW,
            message="SDLC-FR-0031 is unchanged since review iteration 1.",
            verdict="PASS",
        )
    )
    assert "NO_CHANGES_TO_REVIEW" in output
    assert "Blocking:" not in output


def test_a_stale_result_names_what_was_left_in_place():
    output = render(
        StandardReviewResult(
            code=Code.REVIEW_RESULT_STALE,
            message="SDLC-FR-0031 changed while it was being reviewed.",
            created=("SDLC-FR-0031 — Review Result 0001 (doc-1)",),
            details=("The Root Document was edited after the review.",),
        )
    )
    assert "Created in Fibery (left in place):" in output
    assert "Review Result 0001" in output
    assert "The Root Document was edited after the review." in output
