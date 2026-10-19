"""Structured contract for Standard Requirement normalization and analysis.

The model returns data only: a normalized requirement in the approved document
sections, analysis findings, proposed relations, the open product questions
(Requirement-Material-WHAT-Gate-v0.1) and, during a rework, one response per
Rework Brief item (Requirement-Rework-Brief-v0.1). Code renders the Open
Questions section from those structured questions, so the gate never reads
Markdown prose. It never writes to Fibery,
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
    MULTILINE_TITLE_MESSAGE,
    NO_OPEN_QUESTIONS,
    OPEN_QUESTIONS_KEY,
    RESERVED_HEADING_MESSAGE,
    SECTION_KEYS,
    TITLE_SEPARATOR,
    is_single_line,
    reserved_heading,
)

# `<CODE>-<FR|NFR|CON|RAW>-<digits>`; the processor never invents one.
REQUIREMENT_ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*-(?:FR|NFR|CON|RAW)-\d{4,}$")


class FindingKind(StrEnum):
    """The closed set of things Process may report.

    Quality findings describe the requirement itself; comparison findings
    describe its relationship to an existing Standard Requirement. Neither ever
    mutates anything: Review decides what they mean.

    IMPLEMENTATION_LEAKAGE is a quality finding: downstream HOW inside the
    Requirement, or a Requirement that is itself architecture, Task, test or
    deployment work (Standard-Requirement-Process-Spec-v0.1 section 3.1).
    """

    INCOMPLETE = "INCOMPLETE"
    AMBIGUOUS = "AMBIGUOUS"
    NON_ATOMIC = "NON_ATOMIC"
    INCONSISTENT = "INCONSISTENT"
    NOT_TESTABLE = "NOT_TESTABLE"
    MISSING_CONSTRAINT = "MISSING_CONSTRAINT"
    MISSING_EDGE_CASE = "MISSING_EDGE_CASE"
    IMPLEMENTATION_LEAKAGE = "IMPLEMENTATION_LEAKAGE"
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


class ReworkOutcome(StrEnum):
    """How one Process iteration answered one Rework Brief item."""

    # Corrected in this output, or already answered by authoritative content.
    RESOLVED = "RESOLVED"
    # The previous finding does not establish a real defect.
    REBUTTED = "REBUTTED"
    # It stays unresolved; a material WHAT is kept as a product question.
    ESCALATED = "ESCALATED"


class InvalidAnalysisOutput(ValueError):
    """The model's response does not satisfy the contract."""


ANALYSIS_KEYS = frozenset(
    {"completeness", "clarity", "atomicity", "testability", "internal_consistency"}
)
#: Open Questions is rendered from `product_questions` (Material-WHAT Gate
#: v0.1 section 3); the model never writes that section itself.
NORMALIZED_KEYS = frozenset({"title", *SECTION_KEYS} - {OPEN_QUESTIONS_KEY})
REQUIRED_NORMALIZED_KEYS = frozenset({"title", "requirement"})
FINDING_KEYS = frozenset({"kind", "requirement_id", "detail"})
RELATION_KEYS = frozenset({"kind", "requirement_id", "rationale"})
PRODUCT_QUESTION_KEYS = frozenset({"detail", "material"})
REWORK_RESPONSE_KEYS = frozenset(
    {"item", "outcome", "explanation", "product_question_index"}
)
REWORK_RESPONSES_KEY = "rework_responses"
RESULT_KEYS = frozenset(
    {
        "normalized_requirement",
        "analysis",
        "findings",
        "proposed_relations",
        "product_questions",
        REWORK_RESPONSES_KEY,
    }
)
OPEN_QUESTION_TEMPLATE = "- {detail}"


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
class ProductQuestion:
    """One unresolved product decision about WHAT, never answered here.

    `material` is the Process claim that two plausible answers would require a
    different observable outcome for some input or situation in this
    Requirement's scope (Material-WHAT Gate v0.1 section 2). Review verifies
    the claim; it is never the deciding evidence on its own.
    """

    detail: str
    material: bool


@dataclass(frozen=True)
class ReworkResponse:
    """The answer to one Rework Brief item, referenced by its item ref.

    `product_question_index` names the product question of the same output
    that keeps an ESCALATED item open; only ESCALATED may carry one.
    """

    item: str
    outcome: ReworkOutcome
    explanation: str
    product_question_index: int | None = None


@dataclass(frozen=True)
class ReworkExpectation:
    """What the Rework Brief demands: one response per item, by reference.

    `what_refs` are the items that are material WHAT questions; an ESCALATED
    response to one must keep it as a material product question.
    """

    item_refs: tuple[str, ...]
    what_refs: frozenset[str]


def render_open_questions(questions: tuple[ProductQuestion, ...]) -> str:
    """The Open Questions section, derived from the structured questions only."""
    if not questions:
        return NO_OPEN_QUESTIONS
    return "\n".join(
        OPEN_QUESTION_TEMPLATE.format(detail=question.detail) for question in questions
    )


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
    product_questions: tuple[ProductQuestion, ...] = ()
    rework_responses: tuple[ReworkResponse, ...] = ()


def parse_analysis_output(
    text: str, rework: ReworkExpectation | None = None
) -> AnalysisResult:
    """Validate the model's JSON response, or raise InvalidAnalysisOutput.

    `rework` is the Rework Brief this run supplied, None when it supplied none.
    """
    payload = _load_json(text)
    _reject_unknown(payload, RESULT_KEYS, "result")

    normalized = payload.get("normalized_requirement")
    if not isinstance(normalized, dict):
        raise InvalidAnalysisOutput("'normalized_requirement' must be an object.")

    questions = tuple(
        _read_product_question(entry, index)
        for index, entry in enumerate(
            _as_list(payload.get("product_questions"), "product_questions")
        )
    )
    return AnalysisResult(
        normalized=_read_normalized(normalized, questions),
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
        product_questions=questions,
        rework_responses=_read_rework_responses(payload, rework, questions),
    )


def _read_rework_responses(
    payload: dict[str, object],
    rework: ReworkExpectation | None,
    questions: tuple[ProductQuestion, ...],
) -> tuple[ReworkResponse, ...]:
    entries = payload.get(REWORK_RESPONSES_KEY)
    if rework is None:
        if entries:
            raise InvalidAnalysisOutput(
                "rework_responses answers a Rework Brief, but no previous review "
                "feedback was supplied."
            )
        return ()
    if REWORK_RESPONSES_KEY not in payload:
        raise InvalidAnalysisOutput(
            "Previous review feedback was supplied, so rework_responses must "
            "answer every item: its absence answers none."
        )
    responses = tuple(
        _read_rework_response(entry, index)
        for index, entry in enumerate(_as_list(entries, REWORK_RESPONSES_KEY))
    )
    require_rework_coverage(responses, rework, questions)
    return responses


def require_rework_coverage(
    responses: tuple[ReworkResponse, ...],
    rework: ReworkExpectation,
    questions: tuple[ProductQuestion, ...],
) -> None:
    """Exactly one response per Brief item; escalations stay recorded.

    Shared with the Process Result reader, so a persisted iteration is held to
    the same contract as the model's response.
    """
    seen: set[str] = set()
    for response in responses:
        if response.item not in rework.item_refs:
            raise InvalidAnalysisOutput(
                f"rework response for {response.item!r} answers no Brief item."
            )
        if response.item in seen:
            raise InvalidAnalysisOutput(
                f"Brief item {response.item} is answered more than once."
            )
        seen.add(response.item)
        _require_escalation_recorded(response, rework, questions)
    missing = [ref for ref in rework.item_refs if ref not in seen]
    if missing:
        raise InvalidAnalysisOutput(
            "rework_responses leaves Brief items unanswered: " + ", ".join(missing)
        )


def _require_escalation_recorded(
    response: ReworkResponse,
    rework: ReworkExpectation,
    questions: tuple[ProductQuestion, ...],
) -> None:
    index = response.product_question_index
    if response.outcome is not ReworkOutcome.ESCALATED:
        if index is not None:
            raise InvalidAnalysisOutput(
                f"rework response for {response.item} is {response.outcome.value}; "
                "only ESCALATED names a product question."
            )
        return
    if index is None:
        if response.item in rework.what_refs:
            raise InvalidAnalysisOutput(
                f"Brief item {response.item} is a material WHAT question; "
                "escalating it must name the product question that keeps it open."
            )
        return
    if not 0 <= index < len(questions):
        raise InvalidAnalysisOutput(
            f"rework response for {response.item} names product question {index}, "
            f"but the output has {len(questions)}."
        )
    if response.item in rework.what_refs and not questions[index].material:
        raise InvalidAnalysisOutput(
            f"Brief item {response.item} is a material WHAT question, but product "
            f"question {index} that keeps it open is not material."
        )


def _read_rework_response(entry: object, index: int) -> ReworkResponse:
    where = f"rework response {index}"
    if not isinstance(entry, dict):
        raise InvalidAnalysisOutput(f"{where} must be an object.")
    _reject_unknown(entry, REWORK_RESPONSE_KEYS, where)
    missing = sorted({"item", "outcome", "explanation"} - set(entry))
    if missing:
        raise InvalidAnalysisOutput(f"{where} is missing: " + ", ".join(missing))
    question = entry.get("product_question_index")
    if question is not None and (
        not isinstance(question, int) or isinstance(question, bool)
    ):
        raise InvalidAnalysisOutput(
            f"{where} product_question_index must be an integer."
        )
    return ReworkResponse(
        item=_read_text(entry["item"], f"{where} item"),
        outcome=_read_enum(ReworkOutcome, entry["outcome"], where),
        explanation=_read_text(entry["explanation"], f"{where} explanation"),
        product_question_index=question,
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


def _read_normalized(
    entry: dict[str, object], questions: tuple[ProductQuestion, ...]
) -> NormalizedRequirement:
    if OPEN_QUESTIONS_KEY in entry:
        raise InvalidAnalysisOutput(
            "normalized_requirement must not contain open_questions: the Open "
            "Questions section is rendered from product_questions."
        )
    _reject_unknown(entry, NORMALIZED_KEYS, "normalized_requirement")
    missing = sorted(REQUIRED_NORMALIZED_KEYS - set(entry))
    if missing:
        raise InvalidAnalysisOutput(
            "normalized_requirement is missing: " + ", ".join(missing)
        )
    sections = {
        key: _section_text(entry.get(key), key, f"normalized_requirement {key}")
        for key in SECTION_KEYS
        if key != OPEN_QUESTIONS_KEY
    }
    sections[OPEN_QUESTIONS_KEY] = render_open_questions(questions)
    return NormalizedRequirement(
        title=_read_title(entry["title"], "normalized_requirement title"), **sections
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


def _read_title(value: object, where: str) -> str:
    title = _read_text(value, where)
    if not is_single_line(title):
        raise InvalidAnalysisOutput(MULTILINE_TITLE_MESSAGE.format(where=where))
    return title


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


def _read_product_question(entry: object, index: int) -> ProductQuestion:
    where = f"product question {index}"
    if not isinstance(entry, dict):
        raise InvalidAnalysisOutput(f"{where} must be an object.")
    _reject_unknown(entry, PRODUCT_QUESTION_KEYS, where)
    missing = sorted(PRODUCT_QUESTION_KEYS - set(entry))
    if missing:
        raise InvalidAnalysisOutput(f"{where} is missing: " + ", ".join(missing))
    if not isinstance(entry["material"], bool):
        raise InvalidAnalysisOutput(f"{where} material must be true or false.")
    detail = _read_text(entry["detail"], f"{where} detail")
    if not is_single_line(detail):
        raise InvalidAnalysisOutput(f"{where} detail must be a single line.")
    return ProductQuestion(detail=detail, material=entry["material"])


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
