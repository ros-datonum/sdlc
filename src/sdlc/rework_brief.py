"""The Rework Brief: the previous independent Review, as non-normative feedback.

Implements Requirement-Rework-Brief-v0.1. When a Standard Requirement returns
to Process after a completed Review, the next Process iteration receives the
actionable items of that Review and must answer each one. The Brief is
assembled deterministically by code from the persisted Review Result and the
Process Result it reviewed; no model writes it.

It is feedback, never Requirement truth: it is not part of the Root, of a
normative child, of the RAW or of a peer, and it is persisted only inside the
Process Result that consumed it. Its identity is a SHA-256 over its canonical
content, used to detect change; it is not an authentication.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import StrEnum

from sdlc.standard_analysis import FindingKind, RelationKind
from sdlc.standard_review import ReviewSeverity, VerificationOutcome


class InvalidReworkBrief(ValueError):
    """A Rework Brief, or a persisted copy of one, cannot be trusted."""


class BriefCategory(StrEnum):
    """Where in the source Review an actionable item came from."""

    # A Process finding, with the Review's outcome for it.
    PROCESS_FINDING = "PROCESS_FINDING"
    # A defect the Review found itself.
    NEW_FINDING = "NEW_FINDING"
    # A proposed relation the Review did not confirm.
    RELATION_PROPOSAL = "RELATION_PROPOSAL"
    # A Process product question, with the Review's outcome for it.
    PRODUCT_QUESTION = "PRODUCT_QUESTION"
    # A material WHAT question the Review added (material_unresolved_what).
    MATERIAL_WHAT = "MATERIAL_WHAT"
    # A rework response of the source Process the Review did not confirm.
    REWORK_CLAIM = "REWORK_CLAIM"


# One letter per category in the deterministic item reference
# `R<review iteration>.<letter><index in the source Review's own list>`.
REF_LETTERS = {
    BriefCategory.PROCESS_FINDING: "F",
    BriefCategory.NEW_FINDING: "N",
    BriefCategory.RELATION_PROPOSAL: "L",
    BriefCategory.PRODUCT_QUESTION: "Q",
    BriefCategory.MATERIAL_WHAT: "W",
    BriefCategory.REWORK_CLAIM: "C",
}
REF_PATTERN = re.compile(r"^R(?P<iteration>\d{4,})\.(?P<letter>[A-Z])(?P<index>\d+)$")
ITERATION_WIDTH = 4

SOURCE_KEYS = frozenset(
    {
        "requirement_id",
        "review_iteration",
        "review_version",
        "process_iteration",
        "process_output_fingerprint",
        "process_version",
    }
)
ITEM_KEYS = frozenset(
    {
        "ref",
        "category",
        "detail",
        "feedback",
        "outcome",
        "kind",
        "severity",
        "requirement_id",
        "blocks_what",
    }
)
BRIEF_KEYS = frozenset({"brief_identity", "source_review", "items", "assessment"})
IDENTITY_KEY = "brief_identity"


def item_ref(review_iteration: int, category: BriefCategory, index: int) -> str:
    """`R0001.F0`: stable for the same Review Result, whatever reads it."""
    return f"R{review_iteration:0{ITERATION_WIDTH}d}.{REF_LETTERS[category]}{index}"


@dataclass(frozen=True)
class ReviewSource:
    """Which Review Result the Brief came from, and what that Review bound."""

    requirement_id: str
    review_iteration: int
    review_version: str
    process_iteration: int
    process_output_fingerprint: str
    process_version: str


@dataclass(frozen=True)
class BriefItem:
    """One actionable item of the source Review. A claim, never a conclusion.

    `feedback` is the source reviewer's stated reason, `outcome` the source
    Review's verification outcome for a verified claim. `blocks_what` says
    the item is a material WHAT question the source Review left open: only a
    later independent Review that confirms its resolution clears it.
    """

    ref: str
    category: BriefCategory
    detail: str
    blocks_what: bool = False
    feedback: str | None = None
    outcome: VerificationOutcome | None = None
    kind: str | None = None
    severity: ReviewSeverity | None = None
    requirement_id: str | None = None


@dataclass(frozen=True)
class ReworkBrief:
    """The actionable feedback one completed Review gives the next Process."""

    source: ReviewSource
    items: tuple[BriefItem, ...]
    assessment: dict[str, str] = field(default_factory=dict)

    @property
    def item_refs(self) -> tuple[str, ...]:
        return tuple(item.ref for item in self.items)

    @property
    def what_refs(self) -> frozenset[str]:
        return frozenset(item.ref for item in self.items if item.blocks_what)

    def item(self, ref: str) -> BriefItem:
        return next(item for item in self.items if item.ref == ref)

    @property
    def identity(self) -> str:
        """SHA-256 of the canonical content: change detection, not authentication."""
        return _digest(self._content())

    def to_payload(self) -> dict[str, object]:
        return {IDENTITY_KEY: self.identity, **self._content()}

    def _content(self) -> dict[str, object]:
        return {
            "source_review": {
                "requirement_id": self.source.requirement_id,
                "review_iteration": self.source.review_iteration,
                "review_version": self.source.review_version,
                "process_iteration": self.source.process_iteration,
                "process_output_fingerprint": self.source.process_output_fingerprint,
                "process_version": self.source.process_version,
            },
            "items": [_item_payload(item) for item in self.items],
            "assessment": dict(sorted(self.assessment.items())),
        }

    @classmethod
    def from_payload(cls, payload: object) -> ReworkBrief:
        """Read a persisted Brief back; its identity is recomputed, never trusted."""
        if not isinstance(payload, dict) or set(payload) != BRIEF_KEYS:
            raise InvalidReworkBrief(
                "A persisted Rework Brief must carry exactly: "
                + ", ".join(sorted(BRIEF_KEYS))
            )
        source = _read_source(payload["source_review"])
        items = payload["items"]
        if not isinstance(items, list):
            raise InvalidReworkBrief("Rework Brief items must be a list.")
        brief = cls(
            source=source,
            items=tuple(_read_item(entry, source.review_iteration) for entry in items),
            assessment=_read_assessment(payload["assessment"]),
        )
        refs = brief.item_refs
        if len(set(refs)) != len(refs):
            raise InvalidReworkBrief("A Rework Brief item reference is repeated.")
        if payload[IDENTITY_KEY] != brief.identity:
            raise InvalidReworkBrief(
                "The persisted Rework Brief identity does not match its content."
            )
        return brief


def run_input_identity(input_tree_fingerprint: str, brief_identity: str | None) -> str:
    """What one Process model call consumes: the normative tree and the Brief.

    Two runs with the same identity would show the model the same Requirement
    and the same feedback; peers and the RAW are context, not part of it.
    """
    return _digest(
        {
            "normative_input_tree": input_tree_fingerprint,
            "rework_brief": brief_identity,
        }
    )


def _digest(content: dict[str, object]) -> str:
    canonical = json.dumps(
        content, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _item_payload(item: BriefItem) -> dict[str, object]:
    return {
        "ref": item.ref,
        "category": item.category.value,
        "detail": item.detail,
        "feedback": item.feedback,
        "outcome": item.outcome.value if item.outcome else None,
        "kind": item.kind,
        "severity": item.severity.value if item.severity else None,
        "requirement_id": item.requirement_id,
        "blocks_what": item.blocks_what,
    }


def _read_source(entry: object) -> ReviewSource:
    if not isinstance(entry, dict) or set(entry) != SOURCE_KEYS:
        raise InvalidReworkBrief("The Rework Brief source_review is malformed.")
    for key in ("review_iteration", "process_iteration"):
        value = entry[key]
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise InvalidReworkBrief(f"The Rework Brief source {key} is invalid.")
    for key in (
        "requirement_id",
        "review_version",
        "process_output_fingerprint",
        "process_version",
    ):
        if not isinstance(entry[key], str) or not entry[key].strip():
            raise InvalidReworkBrief(f"The Rework Brief source has no {key}.")
    return ReviewSource(**entry)


def _read_item(entry: object, review_iteration: int) -> BriefItem:
    if not isinstance(entry, dict) or set(entry) != ITEM_KEYS:
        raise InvalidReworkBrief(f"Malformed Rework Brief item: {entry!r}")
    try:
        item = BriefItem(
            ref=entry["ref"],
            category=BriefCategory(entry["category"]),
            detail=entry["detail"],
            blocks_what=entry["blocks_what"],
            feedback=entry["feedback"],
            outcome=(
                VerificationOutcome(entry["outcome"])
                if entry["outcome"] is not None
                else None
            ),
            kind=entry["kind"],
            severity=(
                ReviewSeverity(entry["severity"])
                if entry["severity"] is not None
                else None
            ),
            requirement_id=entry["requirement_id"],
        )
    except ValueError as error:
        raise InvalidReworkBrief(f"Malformed Rework Brief item: {error}") from error
    _require_item_shape(item, review_iteration)
    return item


def _require_item_shape(item: BriefItem, review_iteration: int) -> None:
    """Each category carries exactly the fields its source defines."""
    match = REF_PATTERN.match(item.ref) if isinstance(item.ref, str) else None
    if (
        match is None
        or int(match.group("iteration")) != review_iteration
        or match.group("letter") != REF_LETTERS[item.category]
    ):
        raise InvalidReworkBrief(
            f"Rework Brief item reference {item.ref!r} does not name its source."
        )
    if not isinstance(item.detail, str) or not item.detail.strip():
        raise InvalidReworkBrief(f"Rework Brief item {item.ref} has no detail.")
    if not isinstance(item.blocks_what, bool):
        raise InvalidReworkBrief(
            f"Rework Brief item {item.ref} blocks_what is invalid."
        )
    for label, value in (
        ("feedback", item.feedback),
        ("requirement_id", item.requirement_id),
        ("kind", item.kind),
    ):
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise InvalidReworkBrief(f"Rework Brief item {item.ref} {label} is empty.")
    if not _has_category_shape(item):
        raise InvalidReworkBrief(
            f"Rework Brief item {item.ref} does not have the shape its category "
            f"{item.category.value} requires."
        )


def _has_category_shape(item: BriefItem) -> bool:
    is_finding_kind = item.kind in {kind.value for kind in FindingKind}
    verified = item.outcome is not None and item.feedback is not None
    graded_iff_rejected = (item.severity is not None) == (
        item.outcome is VerificationOutcome.REJECTED
    )
    if item.category is BriefCategory.PROCESS_FINDING:
        return (
            verified
            and is_finding_kind
            and not item.blocks_what
            and (item.severity is not None)
            == (item.outcome is VerificationOutcome.CONFIRMED)
        )
    if item.category is BriefCategory.NEW_FINDING:
        return (
            item.outcome is None
            and item.feedback is None
            and is_finding_kind
            and item.severity is not None
            and not item.blocks_what
        )
    if item.category is BriefCategory.RELATION_PROPOSAL:
        return (
            verified
            and item.outcome is not VerificationOutcome.CONFIRMED
            and item.kind in {kind.value for kind in RelationKind}
            and item.requirement_id is not None
            and item.severity is None
            and not item.blocks_what
        )
    if item.category is BriefCategory.PRODUCT_QUESTION:
        return verified and item.kind is None and item.severity is None
    if item.category is BriefCategory.MATERIAL_WHAT:
        return (
            item.outcome is None
            and item.feedback is None
            and item.kind is None
            and item.severity is None
            and item.requirement_id is None
            and item.blocks_what
        )
    return (
        verified
        and item.outcome is not VerificationOutcome.CONFIRMED
        and item.kind is None
        and item.requirement_id is None
        and graded_iff_rejected
    )


def _read_assessment(value: object) -> dict[str, str]:
    if not isinstance(value, dict) or not all(
        isinstance(key, str) and isinstance(text, str) and text.strip()
        for key, text in value.items()
    ):
        raise InvalidReworkBrief("The Rework Brief assessment is malformed.")
    return dict(value)
