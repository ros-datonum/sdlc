"""Structured contract for Standard Requirement normalization and analysis.

The model returns data only: a normalized requirement in the approved document
sections, analysis findings, and proposed relations. It never writes to Fibery,
never names a Fibery identifier, and is never asked for reasoning traces.

Anything the contract does not define is a validation error, which is what keeps
chain-of-thought and invented mutation instructions out.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum

from sdlc.raw_processing import (
    DOCUMENT_SECTIONS,
    MISSING_INFORMATION,
    NO_OPEN_QUESTIONS,
    OPEN_QUESTIONS_KEY,
    RESERVED_HEADING_MESSAGE,
    SECTION_KEYS,
    TITLE_SEPARATOR,
    reserved_heading,
)

# `<CODE>-<FR|NFR|CON|RAW>-<digits>`; the processor never invents one.
REQUIREMENT_ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*-(?:FR|NFR|CON|RAW)-\d{4,}$")


class FindingKind(StrEnum):
    """The closed set of things Process may report.

    Quality findings describe the requirement itself; comparison findings
    describe its relationship to an existing Standard Requirement. Neither ever
    mutates anything: Review decides what they mean.
    """

    INCOMPLETE = "INCOMPLETE"
    AMBIGUOUS = "AMBIGUOUS"
    NON_ATOMIC = "NON_ATOMIC"
    INCONSISTENT = "INCONSISTENT"
    NOT_TESTABLE = "NOT_TESTABLE"
    MISSING_CONSTRAINT = "MISSING_CONSTRAINT"
    MISSING_EDGE_CASE = "MISSING_EDGE_CASE"
    POSSIBLE_DUPLICATE = "POSSIBLE_DUPLICATE"
    POSSIBLE_CONFLICT = "POSSIBLE_CONFLICT"
    POSSIBLE_CHANGE = "POSSIBLE_CHANGE"
    POSSIBLE_SUPERSESSION = "POSSIBLE_SUPERSESSION"

    @property
    def is_about_another_requirement(self) -> bool:
        return self in _COMPARISON_FINDINGS


_COMPARISON_FINDINGS = frozenset(
    {
        FindingKind.POSSIBLE_DUPLICATE,
        FindingKind.POSSIBLE_CONFLICT,
        FindingKind.POSSIBLE_CHANGE,
        FindingKind.POSSIBLE_SUPERSESSION,
    }
)


class RelationKind(StrEnum):
    """Relations Process may propose.

    Only the forward sides: Fibery populates `Blocks` and `Impacted By`
    automatically, so proposing them separately would be redundant.
    """

    DEPENDS_ON = "DEPENDS_ON"
    AFFECTS = "AFFECTS"


class InvalidAnalysisOutput(ValueError):
    """The model's response does not satisfy the contract."""


ANALYSIS_KEYS = frozenset(
    {"completeness", "clarity", "atomicity", "testability", "internal_consistency"}
)
NORMALIZED_KEYS = frozenset({"title", *SECTION_KEYS})
REQUIRED_NORMALIZED_KEYS = frozenset({"title", "requirement"})
FINDING_KEYS = frozenset({"kind", "requirement_id", "detail"})
RELATION_KEYS = frozenset({"kind", "requirement_id", "rationale"})
RESULT_KEYS = frozenset(
    {"normalized_requirement", "analysis", "findings", "proposed_relations"}
)


@dataclass(frozen=True)
class Finding:
    """One observation. Never an instruction."""

    kind: FindingKind
    detail: str
    requirement_id: str | None = None


@dataclass(frozen=True)
class ProposedRelation:
    """A relation Review may later confirm. Process never writes it."""

    kind: RelationKind
    requirement_id: str
    rationale: str


@dataclass(frozen=True)
class NormalizedRequirement:
    """The requirement rewritten into the approved document sections."""

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


@dataclass(frozen=True)
class AnalysisResult:
    """One validated normalization and analysis."""

    normalized: NormalizedRequirement
    analysis: dict[str, str]
    findings: tuple[Finding, ...]
    proposed_relations: tuple[ProposedRelation, ...]


def parse_analysis_output(text: str) -> AnalysisResult:
    """Validate the model's JSON response, or raise InvalidAnalysisOutput."""
    payload = _load_json(text)
    _reject_unknown(payload, RESULT_KEYS, "result")

    normalized = payload.get("normalized_requirement")
    if not isinstance(normalized, dict):
        raise InvalidAnalysisOutput("'normalized_requirement' must be an object.")

    return AnalysisResult(
        normalized=_read_normalized(normalized),
        analysis=_read_analysis(payload.get("analysis")),
        findings=tuple(
            _read_finding(entry, index)
            for index, entry in enumerate(_as_list(payload.get("findings"), "findings"))
        ),
        proposed_relations=tuple(
            _read_relation(entry, index)
            for index, entry in enumerate(
                _as_list(payload.get("proposed_relations"), "proposed_relations")
            )
        ),
    )


def _as_list(value: object, where: str) -> list[object]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise InvalidAnalysisOutput(f"{where!r} must be a list.")
    return value


def _load_json(text: str) -> dict[str, object]:
    stripped = (text or "").strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        stripped = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
    try:
        payload = json.loads(stripped)
    except ValueError as error:
        raise InvalidAnalysisOutput(
            f"The response is not valid JSON: {error}"
        ) from error
    if not isinstance(payload, dict):
        raise InvalidAnalysisOutput("The response must be a JSON object.")
    return payload


def _reject_unknown(
    payload: dict[str, object], allowed: frozenset[str], what: str
) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise InvalidAnalysisOutput(
            f"The {what} contains keys the contract does not define: "
            + ", ".join(unknown)
        )


def _read_normalized(entry: dict[str, object]) -> NormalizedRequirement:
    _reject_unknown(entry, NORMALIZED_KEYS, "normalized_requirement")
    missing = sorted(REQUIRED_NORMALIZED_KEYS - set(entry))
    if missing:
        raise InvalidAnalysisOutput(
            "normalized_requirement is missing: " + ", ".join(missing)
        )
    sections = {
        key: _section_text(entry.get(key), key, f"normalized_requirement {key}")
        for key in SECTION_KEYS
    }
    return NormalizedRequirement(
        title=_read_text(entry["title"], "normalized_requirement title"), **sections
    )


def _read_analysis(value: object) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise InvalidAnalysisOutput("'analysis' must be an object.")
    _reject_unknown(value, ANALYSIS_KEYS, "analysis")
    return {
        key: _read_text(item, f"analysis {key}")
        for key, item in value.items()
        if item is not None
    }


def _read_text(value: object, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidAnalysisOutput(f"{where} must be a non-empty string.")
    return value.strip()


def _section_text(value: object, key: str, where: str) -> str:
    """A section's content, with the approved schema's fixed text when absent."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return NO_OPEN_QUESTIONS if key == OPEN_QUESTIONS_KEY else MISSING_INFORMATION
    if not isinstance(value, str):
        raise InvalidAnalysisOutput(f"{where} must be a string.")
    text = value.strip()
    heading = reserved_heading(text)
    if heading is not None:
        raise InvalidAnalysisOutput(
            RESERVED_HEADING_MESSAGE.format(where=where, heading=heading)
        )
    return text


def _read_finding(entry: object, index: int) -> Finding:
    where = f"finding {index}"
    if not isinstance(entry, dict):
        raise InvalidAnalysisOutput(f"{where} must be an object.")
    _reject_unknown(entry, FINDING_KEYS, where)
    if "kind" not in entry or "detail" not in entry:
        raise InvalidAnalysisOutput(f"{where} needs a kind and a detail.")
    kind = _read_enum(FindingKind, entry["kind"], where)

    requirement_id = entry.get("requirement_id")
    if kind.is_about_another_requirement:
        if requirement_id is None:
            raise InvalidAnalysisOutput(
                f"{where} of kind {kind.value} must name the Requirement it is about."
            )
        requirement_id = _read_requirement_id(requirement_id, where)
    elif requirement_id is not None:
        raise InvalidAnalysisOutput(
            f"{where} of kind {kind.value} is about this Requirement and must not "
            "name another one."
        )
    return Finding(
        kind=kind,
        detail=_read_text(entry["detail"], f"{where} detail"),
        requirement_id=requirement_id,
    )


def _read_relation(entry: object, index: int) -> ProposedRelation:
    where = f"proposed relation {index}"
    if not isinstance(entry, dict):
        raise InvalidAnalysisOutput(f"{where} must be an object.")
    _reject_unknown(entry, RELATION_KEYS, where)
    missing = sorted(RELATION_KEYS - set(entry))
    if missing:
        raise InvalidAnalysisOutput(f"{where} is missing: " + ", ".join(missing))
    return ProposedRelation(
        kind=_read_enum(RelationKind, entry["kind"], where),
        requirement_id=_read_requirement_id(entry["requirement_id"], where),
        rationale=_read_text(entry["rationale"], f"{where} rationale"),
    )


def _read_enum(enum: type[StrEnum], value: object, where: str) -> StrEnum:
    try:
        return enum(value)
    except ValueError as error:
        raise InvalidAnalysisOutput(
            f"{where} has kind {value!r}; expected one of "
            + ", ".join(member.value for member in enum)
        ) from error


def _read_requirement_id(value: object, where: str) -> str:
    text = _read_text(value, f"{where} requirement_id")
    if not REQUIREMENT_ID_PATTERN.match(text):
        raise InvalidAnalysisOutput(
            f"{where} names {text!r}, which is not a Requirement ID."
        )
    return text
