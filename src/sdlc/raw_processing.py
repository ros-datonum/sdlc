"""Structured contract for RAW Requirement decomposition.

The model returns data, never prose and never Fibery mechanics. This module
validates that data strictly and renders it into the approved Standard
Requirement Root Document, so a malformed or creative response fails here rather
than reaching Fibery.

Chain-of-thought is neither requested nor accepted: any field the contract does
not define is a validation error.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum

from sdlc.raw_source import FENCED_BLOCK_PATTERN

MISSING_INFORMATION = "Not specified in source."
NO_OPEN_QUESTIONS = "None."
TITLE_SEPARATOR = " — "


class Category(StrEnum):
    """Approved domain categories.

    These are the workspace's `enum/name` values as well; the Fibery option was
    corrected from the earlier `NON-FONCTIONAL` misspelling, so no mapping
    table is needed.
    """

    FUNCTIONAL = "FUNCTIONAL"
    NON_FUNCTIONAL = "NON_FUNCTIONAL"
    CONSTRAINT = "CONSTRAINT"

    @property
    def id_infix(self) -> str:
        """The Requirement ID infix this category uses."""
        return _CATEGORY_ID_INFIX[self]


_CATEGORY_ID_INFIX = {
    Category.FUNCTIONAL: "FR",
    Category.NON_FUNCTIONAL: "NFR",
    Category.CONSTRAINT: "CON",
}


class FindingKind(StrEnum):
    """How a candidate may relate to an existing Standard Requirement.

    A finding is recorded for Review. It never mutates the existing
    Requirement: RAW-Requirement-Processor-Decision-v0.1 defers all revision
    semantics.
    """

    POSSIBLE_DUPLICATE = "POSSIBLE_DUPLICATE"
    POSSIBLE_CONFLICT = "POSSIBLE_CONFLICT"
    POSSIBLE_CHANGE = "POSSIBLE_CHANGE"
    POSSIBLE_SUPERSESSION = "POSSIBLE_SUPERSESSION"


class InvalidModelOutput(ValueError):
    """The model's response does not satisfy the contract."""


# Section key -> heading, in the order the approved schema fixes.
DOCUMENT_SECTIONS = (
    ("requirement", "Requirement"),
    ("detailed_behavior", "Detailed Behavior"),
    ("rationale", "Rationale"),
    ("acceptance_verification", "Acceptance / Verification"),
    ("constraints_edge_cases", "Constraints & Edge Cases"),
    ("non_goals", "Non-Goals"),
    ("open_questions", "Open Questions"),
)
SECTION_KEYS = tuple(key for key, _ in DOCUMENT_SECTIONS)
OPEN_QUESTIONS_KEY = "open_questions"

# Heading levels 1 and 2 are the document's own structure: the title and the
# fixed sections. Section content holding one would add a section the schema
# does not define, such as an architecture or implementation-steps section.
# Both Markdown forms count: an ATX `#`/`##` line, and a line of `=` or `-`
# directly below a text line (refused even where a list above would make it a
# thematic break). Fenced content is literal example text, on the same boundary
# raw_source uses to decide document structure.
RESERVED_ATX_HEADING_PATTERN = re.compile(r"^ {0,3}#{1,2}(?:[ \t]|$)")
SETEXT_UNDERLINE_PATTERN = re.compile(r"^ {0,3}(?:=+|-+)[ \t]*$")
RESERVED_HEADING_MESSAGE = (
    "{where} contains the heading {heading!r}; heading levels 1 and 2 are "
    "reserved for the document title and its fixed sections."
)

CANDIDATE_KEYS = frozenset({"category", "title", *SECTION_KEYS})
REQUIRED_CANDIDATE_KEYS = frozenset({"category", "title", "requirement"})
FINDING_KEYS = frozenset({"kind", "requirement_id", "detail"})
REQUIRED_FINDING_KEYS = frozenset({"kind", "requirement_id", "detail"})
RESULT_KEYS = frozenset({"candidates", "findings", "no_candidate_reason"})


@dataclass(frozen=True)
class Finding:
    """An observation about an existing Standard Requirement."""

    kind: FindingKind
    requirement_id: str
    detail: str


@dataclass(frozen=True)
class Candidate:
    """One proposed Standard Requirement."""

    category: Category
    title: str
    requirement: str
    detailed_behavior: str
    rationale: str
    acceptance_verification: str
    constraints_edge_cases: str
    non_goals: str
    open_questions: str

    def document(self, requirement_id: str) -> str:
        """Render the approved Standard Requirement Root Document."""
        lines = [f"# {requirement_id}{TITLE_SEPARATOR}{self.title}", ""]
        for key, heading in DOCUMENT_SECTIONS:
            lines += [f"## {heading}", "", getattr(self, key), ""]
        return "\n".join(lines).rstrip("\n") + "\n"

    def document_name(self, requirement_id: str) -> str:
        return f"{requirement_id}{TITLE_SEPARATOR}{self.title}"


@dataclass(frozen=True)
class DecompositionResult:
    """Everything one RAW decomposition produced."""

    candidates: tuple[Candidate, ...]
    findings: tuple[Finding, ...]
    no_candidate_reason: str | None = None

    @property
    def is_empty(self) -> bool:
        return not self.candidates


def reserved_heading(text: str) -> str | None:
    """The first heading of level 1 or 2 in `text` outside a fenced block.

    Returns the heading's text line, or None when section content adds no
    document structure. Only structure is examined, never meaning.
    """
    unified = text.replace("\r\n", "\n").replace("\r", "\n")
    for prose in FENCED_BLOCK_PATTERN.split(unified)[::2]:
        previous = ""
        for line in prose.split("\n"):
            if RESERVED_ATX_HEADING_PATTERN.match(line):
                return line
            if previous.strip() and SETEXT_UNDERLINE_PATTERN.match(line):
                return previous
            previous = line
    return None


def parse_model_output(text: str) -> DecompositionResult:
    """Validate the model's JSON response, or raise InvalidModelOutput."""
    payload = _load_json(text)
    _reject_unknown(payload, RESULT_KEYS, "result")

    raw_candidates = payload.get("candidates")
    if not isinstance(raw_candidates, list):
        raise InvalidModelOutput("'candidates' must be a list.")
    raw_findings = payload.get("findings", [])
    if not isinstance(raw_findings, list):
        raise InvalidModelOutput("'findings' must be a list.")

    candidates = tuple(
        _read_candidate(entry, index) for index, entry in enumerate(raw_candidates)
    )
    findings = tuple(
        _read_finding(entry, index) for index, entry in enumerate(raw_findings)
    )
    reason = payload.get("no_candidate_reason")
    if reason is not None and not isinstance(reason, str):
        raise InvalidModelOutput("'no_candidate_reason' must be a string.")

    if not candidates and not (reason or "").strip():
        raise InvalidModelOutput(
            "A result with no candidates must explain why none is warranted."
        )
    return DecompositionResult(
        candidates=candidates,
        findings=findings,
        no_candidate_reason=(reason or None) if reason else None,
    )


def _load_json(text: str) -> dict[str, object]:
    """Parse the response body.

    A fenced code block is tolerated because CLIs commonly wrap JSON in one;
    nothing else about the shape is guessed at.
    """
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        stripped = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
    try:
        payload = json.loads(stripped)
    except ValueError as error:
        raise InvalidModelOutput(f"The response is not valid JSON: {error}") from error
    if not isinstance(payload, dict):
        raise InvalidModelOutput("The response must be a JSON object.")
    return payload


def _reject_unknown(
    payload: dict[str, object], allowed: frozenset[str], what: str
) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise InvalidModelOutput(
            f"The {what} contains keys the contract does not define: "
            + ", ".join(unknown)
        )


def _read_candidate(entry: object, index: int) -> Candidate:
    where = f"candidate {index}"
    if not isinstance(entry, dict):
        raise InvalidModelOutput(f"{where} must be an object.")
    _reject_unknown(entry, CANDIDATE_KEYS, where)

    missing = sorted(REQUIRED_CANDIDATE_KEYS - set(entry))
    if missing:
        raise InvalidModelOutput(f"{where} is missing: " + ", ".join(missing))

    category = _read_category(entry["category"], where)
    title = _read_text(entry["title"], f"{where} title")
    sections = {
        key: _section_text(entry.get(key), key, f"{where} {key}")
        for key in SECTION_KEYS
    }
    return Candidate(category=category, title=title, **sections)


def _read_category(value: object, where: str) -> Category:
    try:
        return Category(value)
    except ValueError as error:
        raise InvalidModelOutput(
            f"{where} has category {value!r}; expected one of "
            + ", ".join(c.value for c in Category)
        ) from error


def _read_text(value: object, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidModelOutput(f"{where} must be a non-empty string.")
    return value.strip()


def _section_text(value: object, key: str, where: str) -> str:
    """A section's content, with the schema's fixed text when absent."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return NO_OPEN_QUESTIONS if key == OPEN_QUESTIONS_KEY else MISSING_INFORMATION
    if not isinstance(value, str):
        raise InvalidModelOutput(f"{where} must be a string.")
    text = value.strip()
    heading = reserved_heading(text)
    if heading is not None:
        raise InvalidModelOutput(
            RESERVED_HEADING_MESSAGE.format(where=where, heading=heading)
        )
    return text


def _read_finding(entry: object, index: int) -> Finding:
    where = f"finding {index}"
    if not isinstance(entry, dict):
        raise InvalidModelOutput(f"{where} must be an object.")
    _reject_unknown(entry, FINDING_KEYS, where)
    missing = sorted(REQUIRED_FINDING_KEYS - set(entry))
    if missing:
        raise InvalidModelOutput(f"{where} is missing: " + ", ".join(missing))
    try:
        kind = FindingKind(entry["kind"])
    except ValueError as error:
        raise InvalidModelOutput(
            f"{where} has kind {entry['kind']!r}; expected one of "
            + ", ".join(k.value for k in FindingKind)
        ) from error
    return Finding(
        kind=kind,
        requirement_id=_read_text(entry["requirement_id"], f"{where} requirement_id"),
        detail=_read_text(entry["detail"], f"{where} detail"),
    )
