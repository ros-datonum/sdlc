"""Rework progress at Ready: budget, progress and oscillation from durable history.

Implements Requirement-Autonomous-Ready-v0.1 sections 7 and 8. Everything is
derived from the persisted Review Results and the Process Results they bound,
oldest first, so a restarted runner reaches exactly the same assessment and
no budget is ever reset. Nothing here reads Fibery, calls a model or trusts a
model's own claim that it made progress.

An *open issue* is an actionable item of one Review, as the WI-2 Rework Brief
builds it, that the Review did not settle. Its *key* is deterministic: a
relation by kind and exact target; anything else by its family, kind,
Requirement ID and normalized text. An item that re-raises an earlier one
(`REWORK_CLAIM`) takes the key of the item it originally re-raised, followed
through every Brief. Text keys are exact after normalization, so a reworded
issue is a new key: that can only miss a repetition, never invent one, and
the round budget still bounds every loop.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from sdlc.process_result import ProcessResult
from sdlc.review_result import InvalidReviewResult, ReviewResult, build_rework_brief
from sdlc.rework_brief import BriefCategory, BriefItem
from sdlc.standard_analysis import ReworkOutcome
from sdlc.standard_review import ReviewSeverity, VerificationOutcome

# The family an item belongs to, so that one issue keeps one key whichever
# list of a later Review reports it.
FAMILIES = {
    BriefCategory.PROCESS_FINDING: "FINDING",
    BriefCategory.NEW_FINDING: "FINDING",
    BriefCategory.RELATION_PROPOSAL: "RELATION",
    BriefCategory.EXISTING_DEPENDENCY: "RELATION",
    BriefCategory.PRODUCT_QUESTION: "QUESTION",
    BriefCategory.MATERIAL_WHAT: "QUESTION",
    BriefCategory.RESOLUTION: "RESOLUTION",
}
RELATION_FAMILY = "RELATION"
FINDING_FAMILY = "FINDING"
FINDING_CATEGORIES = frozenset(
    {BriefCategory.PROCESS_FINDING, BriefCategory.NEW_FINDING}
)
# A finding graded INFO is compatible with PASS: it is no reason to rework.
REWORK_SEVERITIES = frozenset({ReviewSeverity.WARNING, ReviewSeverity.BLOCKING})
PROGRESS_ANSWERS = frozenset({ReworkOutcome.RESOLVED, ReworkOutcome.REBUTTED})
WHITESPACE = re.compile(r"\s+")

IssueKey = tuple[str | None, ...]


class ProgressStop(StrEnum):
    """Why the history forbids another automatic rework (or an approval)."""

    REWORK_BUDGET_EXHAUSTED = "REWORK_BUDGET_EXHAUSTED"
    NO_INDEPENDENT_PROGRESS = "NO_INDEPENDENT_PROGRESS"
    UNCHANGED_NORMATIVE_OUTPUT = "UNCHANGED_NORMATIVE_OUTPUT"
    RETURNED_TO_EARLIER_OUTPUT = "RETURNED_TO_EARLIER_OUTPUT"
    REPEATED_ISSUE_SET = "REPEATED_ISSUE_SET"
    REINTRODUCED_ISSUE = "REINTRODUCED_ISSUE"
    REPEATED_ISSUE = "REPEATED_ISSUE"
    CONFLICTING_REVIEWS = "CONFLICTING_REVIEWS"


class ProgressUnknown(Exception):
    """The history cannot establish progress; a human must look."""


@dataclass(frozen=True)
class ProgressAssessment:
    """What the durable history says about the rework so far.

    `stops` carry a code and a content-free explanation: Review iterations,
    item references and counts, never Requirement text.
    """

    rounds_used: int
    rounds_limit: int
    open_issues: int
    independently_resolved: int
    stops: tuple[tuple[ProgressStop, str], ...]

    @property
    def permits_rework(self) -> bool:
        return not self.stops

    def summary(self) -> tuple[str, ...]:
        return (
            f"rework rounds used {self.rounds_used} of {self.rounds_limit}",
            f"open issues in the latest Review: {self.open_issues}",
            (
                "earlier items independently confirmed resolved by the latest "
                f"Review: {self.independently_resolved}"
            ),
        )


Lineage = Sequence[tuple[ProcessResult, ReviewResult]]


def assess_rework(
    lineage: Lineage, max_rework_rounds: int, max_issue_repeats: int
) -> ProgressAssessment:
    """Whether one more automatic rework is allowed by budget and progress.

    `lineage` is every Review Result, oldest first, with the Process Result it
    bound; its last pair is the Requirement's current evidence. Raises
    ProgressUnknown when an item cannot be traced to the issue it re-raises.
    """
    open_sets = _open_issue_sets(lineage)
    latest_review = lineage[-1][1]
    rounds = len(lineage) - 1
    stops: list[tuple[ProgressStop, str]] = []
    if rounds >= max_rework_rounds:
        stops.append(
            (
                ProgressStop.REWORK_BUDGET_EXHAUSTED,
                (
                    f"{rounds} rework round(s) are already in the history; the "
                    f"authorization allows {max_rework_rounds}."
                ),
            )
        )
    resolved = _independently_resolved(latest_review)
    if rounds:
        stops += _output_stops(lineage)
        if not resolved:
            stops.append(
                (
                    ProgressStop.NO_INDEPENDENT_PROGRESS,
                    (
                        f"Review Result {latest_review.iteration} confirms no earlier "
                        "item as resolved; a new iteration alone is not progress."
                    ),
                )
            )
        stops += _issue_stops(lineage, open_sets, max_issue_repeats)
    return ProgressAssessment(
        rounds_used=rounds,
        rounds_limit=max_rework_rounds,
        open_issues=len(open_sets[-1]),
        independently_resolved=resolved,
        stops=tuple(stops),
    )


def conflicting_reviews(lineage: Lineage) -> tuple[tuple[ProgressStop, str], ...]:
    """Earlier Reviews of the same normative output that concluded differently.

    Two independent Reviews of identical content that disagree on verdict or
    WHAT status mean the review itself is not reliable here; an automatic
    approval must not pick the convenient one.
    """
    latest_process, latest_review = lineage[-1]
    latest = (latest_review.verdict, latest_review.what_status)
    return tuple(
        (
            ProgressStop.CONFLICTING_REVIEWS,
            (
                f"Review Result {review.iteration} reviewed the same normative output "
                f"and derived {review.verdict.value} / "
                f"{review.what_status.value if review.what_status else 'no WHAT status'}."
            ),
        )
        for process, review in lineage[:-1]
        if _output(process) == _output(latest_process)
        and (review.verdict, review.what_status) != latest
    )


# -- the detectors -------------------------------------------------------------------


def _output_stops(lineage: Lineage) -> list[tuple[ProgressStop, str]]:
    """The latest rework left the normative output unchanged or restored an older one."""
    latest = _output(lineage[-1][0])
    previous_process, previous_review = lineage[-2]
    if latest == _output(previous_process):
        return [
            (
                ProgressStop.UNCHANGED_NORMATIVE_OUTPUT,
                (
                    f"Process Result {lineage[-1][0].iteration} produced the same "
                    f"normative output as Process Result {previous_process.iteration}, "
                    f"which Review Result {previous_review.iteration} sent back."
                ),
            )
        ]
    return [
        (
            ProgressStop.RETURNED_TO_EARLIER_OUTPUT,
            (
                f"Process Result {lineage[-1][0].iteration} restored the normative "
                f"output of Process Result {process.iteration}, already reviewed by "
                f"Review Result {review.iteration}."
            ),
        )
        for process, review in lineage[:-2]
        if _output(process) == latest
    ][:1]


def _issue_stops(
    lineage: Lineage,
    open_sets: list[dict[IssueKey, str]],
    max_issue_repeats: int,
) -> list[tuple[ProgressStop, str]]:
    latest_iteration = lineage[-1][1].iteration
    latest = open_sets[-1]
    stops: list[tuple[ProgressStop, str]] = []
    for index, earlier in enumerate(open_sets[:-1]):
        if latest and set(latest) == set(earlier):
            stops.append(
                (
                    ProgressStop.REPEATED_ISSUE_SET,
                    (
                        f"Review Result {latest_iteration} reports exactly the open "
                        f"issues of Review Result {lineage[index][1].iteration}."
                    ),
                )
            )
            break
    first_ref = _first_references(open_sets)
    for key in latest:
        present = [key in issues for issues in open_sets]
        if _reintroduced(present):
            stops.append(
                (
                    ProgressStop.REINTRODUCED_ISSUE,
                    (
                        f"Issue {first_ref[key]} was resolved in an earlier Review and "
                        f"is open again in Review Result {latest_iteration}."
                    ),
                )
            )
        run = _trailing_run(present)
        if run - 1 > max_issue_repeats:
            stops.append(
                (
                    ProgressStop.REPEATED_ISSUE,
                    (
                        f"Issue {first_ref[key]} is still open after {run - 1} rework "
                        f"round(s) in a row; the authorization allows "
                        f"{max_issue_repeats} repeat(s)."
                    ),
                )
            )
    return stops


def _independently_resolved(review: ReviewResult) -> int:
    """Earlier items the Reviewer confirmed as resolved or rightly rebutted.

    A confirmed escalation is not progress: it confirms the issue stays open.
    """
    answers = {
        reviewed.response.item: reviewed.response.outcome
        for reviewed in review.reviewed_rework_responses
    }
    return sum(
        1
        for verification in review.rework_verifications
        if verification.outcome is VerificationOutcome.CONFIRMED
        and answers.get(verification.item) in PROGRESS_ANSWERS
    )


def _reintroduced(present: list[bool]) -> bool:
    """Open, then settled, then open again: A, then B, then A."""
    seen = settled = False
    for is_open in present:
        if is_open and settled:
            return True
        if is_open:
            seen = True
        elif seen:
            settled = True
    return False


def _trailing_run(present: list[bool]) -> int:
    run = 0
    for is_open in reversed(present):
        if not is_open:
            break
        run += 1
    return run


# -- open issues ------------------------------------------------------------------


def _open_issue_sets(lineage: Lineage) -> list[dict[IssueKey, str]]:
    """Per Review, oldest first: each open issue's key and its item reference.

    Cost: one Brief built per Review in the history; no Fibery read.
    """
    try:
        briefs = [build_rework_brief(review, process) for process, review in lineage]
    except InvalidReviewResult as error:
        raise ProgressUnknown(str(error)) from error
    by_ref = {item.ref: item for brief in briefs for item in brief.items}
    for process, _ in lineage:
        if process.rework_brief is not None:
            for item in process.rework_brief.items:
                by_ref.setdefault(item.ref, item)
    return [
        {_key(item, by_ref): item.ref for item in brief.items if _is_open(item)}
        for brief in briefs
    ]


def _is_open(item: BriefItem) -> bool:
    if item.category in FINDING_CATEGORIES:
        if item.outcome is VerificationOutcome.REJECTED:
            return False
        return item.severity is None or item.severity in REWORK_SEVERITIES
    if item.category is BriefCategory.PRODUCT_QUESTION:
        return item.blocks_what
    return True


def _key(item: BriefItem, by_ref: dict[str, BriefItem]) -> IssueKey:
    """The issue an item raises, followed back through every re-raise."""
    seen = {item.ref}
    while item.category is BriefCategory.REWORK_CLAIM:
        origin = item.origin_ref
        if origin is None or origin not in by_ref or origin in seen:
            raise ProgressUnknown(
                f"Item {item.ref} re-raises {origin!r}, which the history does "
                "not hold."
            )
        seen.add(origin)
        item = by_ref[origin]
    family = FAMILIES[item.category]
    if family == RELATION_FAMILY:
        return (family, item.kind, item.requirement_id)
    return (
        family,
        item.kind if family == FINDING_FAMILY else None,
        item.requirement_id,
        _normalized(item.detail),
    )


def _first_references(open_sets: list[dict[IssueKey, str]]) -> dict[IssueKey, str]:
    first: dict[IssueKey, str] = {}
    for issues in open_sets:
        for key, ref in issues.items():
            first.setdefault(key, ref)
    return first


def _normalized(text: str) -> str:
    return WHITESPACE.sub(" ", text).strip().rstrip(".").casefold()


def _output(process: ProcessResult) -> str:
    """The normative output a Process Result produced, as its fingerprint."""
    if process.output_tree is not None:
        return process.output_tree.fingerprint
    return process.output_fingerprint
