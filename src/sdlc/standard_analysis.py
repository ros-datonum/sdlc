"""Structured contract for Standard Requirement normalization and analysis.

The model returns data only: a normalized requirement in the approved document
sections, analysis findings, proposed relations, the open product questions
(Requirement-Material-WHAT-Gate-v0.1), the product questions it resolved
itself with their cited evidence (Requirement-Autonomous-Resolution-v0.1) and,
during a rework, one response per Rework Brief item
(Requirement-Rework-Brief-v0.1). Code renders the Open Questions section from
the structured questions, so the gate never reads Markdown prose. It never
writes to Fibery, never names a Fibery identifier, and is never asked for
reasoning traces.

The shapes here are the model contract. Whether a citation exists in its
source, which entity and fingerprint it binds, and whether a policy clause
exists is checked by `resolution_evidence` against what the run read.

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


class ResolutionClass(StrEnum):
    """The closed decision classification (Autonomous Resolution v0.1 §2).

    Only the first three are resolutions. HUMAN_REQUIRED and
    INSUFFICIENT_EVIDENCE classify an unresolved product question, and
    TECHNICAL_HOW is recorded nowhere: it belongs to TSA.
    """

    SOURCE_GROUNDED = "SOURCE_GROUNDED"
    DEPENDENCY_GROUNDED = "DEPENDENCY_GROUNDED"
    DELEGATED_DEFAULT = "DELEGATED_DEFAULT"
    HUMAN_REQUIRED = "HUMAN_REQUIRED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    TECHNICAL_HOW = "TECHNICAL_HOW"


AUTONOMOUS_CLASSES = frozenset(
    {
        ResolutionClass.SOURCE_GROUNDED,
        ResolutionClass.DEPENDENCY_GROUNDED,
        ResolutionClass.DELEGATED_DEFAULT,
    }
)
QUESTION_AUTHORITIES = frozenset(
    {ResolutionClass.HUMAN_REQUIRED, ResolutionClass.INSUFFICIENT_EVIDENCE}
)
#: An unanswerable question offers the human at least this many options.
MIN_ALTERNATIVES = 2


class SourceKind(StrEnum):
    """What a citation quotes."""

    # The originating RAW Requirement's Root Document.
    RAW = "RAW"
    # This Requirement's own normative input, as Process consumed it.
    REQUIREMENT = "REQUIREMENT"
    # A DEPENDS_ON target's Root Document; never an AFFECTS peer.
    DEPENDENCY = "DEPENDENCY"


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
PRODUCT_QUESTION_OPTIONAL_KEYS = frozenset({"authority", "alternatives"})
REWORK_RESPONSE_KEYS = frozenset(
    {"item", "outcome", "explanation", "product_question_index"}
)
REWORK_EVIDENCE_KEYS = frozenset({"resolution_index", "evidence"})
REWORK_RESPONSES_KEY = "rework_responses"
RESOLUTIONS_KEY = "resolutions"
RESOLUTION_KEYS = frozenset(
    {
        "class",
        "issue",
        "answer",
        "affected_sections",
        "sources",
        "policy_clause",
        "justification",
    }
)
SOURCE_KEYS = frozenset({"kind", "requirement_id", "quote"})
RESULT_KEYS = frozenset(
    {
        "normalized_requirement",
        "analysis",
        "findings",
        "proposed_relations",
        "product_questions",
        RESOLUTIONS_KEY,
        REWORK_RESPONSES_KEY,
    }
)
#: The normalized sections a resolution may change (Open Questions is code's).
RESOLVABLE_SECTIONS = frozenset(SECTION_KEYS) - {OPEN_QUESTIONS_KEY}
#: A citation shorter than this proves nothing even as a substring.
MIN_QUOTE_CHARACTERS = 12
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

    `authority` says why it stays open (Autonomous Resolution v0.1 §2:
    HUMAN_REQUIRED or INSUFFICIENT_EVIDENCE) and `alternatives` are the
    decision options for the human. Both are None and () on questions
    recorded before that contract.
    """

    detail: str
    material: bool
    authority: ResolutionClass | None = None
    alternatives: tuple[str, ...] = ()


@dataclass(frozen=True)
class SourceCitation:
    """One quoted piece of authoritative evidence.

    The model supplies `kind`, `requirement_id` (a RAW or a dependency, never
    for REQUIREMENT) and `quote`. `entity_id` and `fingerprint` are bound by
    code from what the run actually read; the model never supplies either.
    """

    kind: SourceKind
    quote: str
    requirement_id: str | None = None
    entity_id: str | None = None
    fingerprint: str | None = None

    @property
    def is_bound(self) -> bool:
        return self.fingerprint is not None


@dataclass(frozen=True)
class Resolution:
    """A product question Process answered under stated authority.

    A claim like any other Process output: the independent Reviewer verifies
    it, and only a CONFIRMED verification stops it blocking WHAT clearance.
    """

    resolution_class: ResolutionClass
    issue: str
    answer: str
    affected_sections: tuple[str, ...]
    sources: tuple[SourceCitation, ...]
    justification: str
    policy_clause: str | None = None


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
    # Autonomous Resolution v0.1 §7: the resolution a RESOLVED answer relies
    # on, and the evidence a REBUTTED answer cites. None and () before it.
    resolution_index: int | None = None
    evidence: tuple[SourceCitation, ...] = ()


@dataclass(frozen=True)
class ReworkExpectation:
    """What the Rework Brief demands: one response per item, by reference.

    `what_refs` are the items that are material WHAT questions; an ESCALATED
    response to one must keep it as a material product question.
    """

    item_refs: tuple[str, ...]
    what_refs: frozenset[str]
    # Items re-raising an unconfirmed resolution (ReworkBrief.resolution_refs).
    resolution_refs: frozenset[str] = frozenset()


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
    resolutions: tuple[Resolution, ...] = ()


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
    resolutions = tuple(
        _read_resolution(entry, index)
        for index, entry in enumerate(
            _as_list(payload.get(RESOLUTIONS_KEY), RESOLUTIONS_KEY)
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
        rework_responses=_read_rework_responses(
            payload, rework, questions, resolutions
        ),
        resolutions=resolutions,
    )


def _read_rework_responses(
    payload: dict[str, object],
    rework: ReworkExpectation | None,
    questions: tuple[ProductQuestion, ...],
    resolutions: tuple[Resolution, ...],
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
    require_rework_coverage(responses, rework, questions, resolutions)
    return responses


def require_rework_coverage(
    responses: tuple[ReworkResponse, ...],
    rework: ReworkExpectation,
    questions: tuple[ProductQuestion, ...],
    resolutions: tuple[Resolution, ...] | None = (),
) -> None:
    """Exactly one response per Brief item; escalations stay recorded.

    Shared with the Process Result reader, so a persisted iteration is held to
    the same contract as the model's response. `resolutions` are the output's
    resolutions; None for a Result written before Autonomous Resolution v0.1,
    whose responses carry no evidence binding and are not held to its rules.
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
        if resolutions is not None:
            _require_evidence_bound(response, rework, resolutions)
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


def _require_evidence_bound(
    response: ReworkResponse,
    rework: ReworkExpectation,
    resolutions: tuple[Resolution, ...],
) -> None:
    """Autonomous Resolution v0.1 §7: a claim cites what makes it so.

    RESOLVED of a material WHAT item names the resolution that answers it;
    only RESOLVED names one. REBUTTED cites evidence; nothing else does.
    """
    index = response.resolution_index
    if index is not None:
        if response.outcome is not ReworkOutcome.RESOLVED:
            raise InvalidAnalysisOutput(
                f"rework response for {response.item} is {response.outcome.value}; "
                "only RESOLVED names a resolution."
            )
        if not 0 <= index < len(resolutions):
            raise InvalidAnalysisOutput(
                f"rework response for {response.item} names resolution {index}, "
                f"but the output has {len(resolutions)}."
            )
    elif (
        response.outcome is ReworkOutcome.RESOLVED and response.item in rework.what_refs
    ):
        raise InvalidAnalysisOutput(
            f"Brief item {response.item} is a material WHAT question; resolving it "
            "must name the resolution that answers it, with its evidence."
        )
    is_rebuttal = response.outcome is ReworkOutcome.REBUTTED
    if is_rebuttal != bool(response.evidence):
        raise InvalidAnalysisOutput(
            f"rework response for {response.item} is {response.outcome.value}; "
            "a REBUTTED response cites evidence and no other response does."
        )
    if response.item in rework.resolution_refs:
        _require_outside_authority(response, resolutions)


def _require_outside_authority(
    response: ReworkResponse, resolutions: tuple[Resolution, ...]
) -> None:
    """An unconfirmed resolution cannot become its own source on rework.

    Its answer was written into the Requirement, so that text is the earlier
    model's output, not authority. Resolving or rebutting the item needs the
    RAW, a dependency or a policy clause (Autonomous Resolution v0.1 §7).
    """
    outcome = response.outcome
    if outcome is ReworkOutcome.RESOLVED:
        if response.resolution_index is None:
            raise InvalidAnalysisOutput(
                f"Brief item {response.item} carries an unconfirmed resolution; "
                "resolving it must name the resolution that answers it."
            )
        resolution = resolutions[response.resolution_index]
        cited = {source.kind for source in resolution.sources}
        if (
            resolution.resolution_class is not ResolutionClass.DELEGATED_DEFAULT
            and cited <= {SourceKind.REQUIREMENT}
        ):
            raise InvalidAnalysisOutput(
                f"Brief item {response.item} carries an unconfirmed resolution whose "
                "answer is now in this Requirement's text; that text is not "
                "authority for it. Cite the RAW or a dependency, or apply a clause."
            )
    elif outcome is ReworkOutcome.REBUTTED and {
        source.kind for source in response.evidence
    } <= {SourceKind.REQUIREMENT}:
        raise InvalidAnalysisOutput(
            f"Brief item {response.item} carries an unconfirmed resolution; a "
            "rebuttal must cite the RAW or a dependency, not this Requirement's "
            "own text, which holds the unconfirmed answer."
        )


def _read_rework_response(entry: object, index: int) -> ReworkResponse:
    where = f"rework response {index}"
    if not isinstance(entry, dict):
        raise InvalidAnalysisOutput(f"{where} must be an object.")
    _reject_unknown(entry, REWORK_RESPONSE_KEYS | REWORK_EVIDENCE_KEYS, where)
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
    resolution = entry.get("resolution_index")
    if resolution is not None and (
        not isinstance(resolution, int) or isinstance(resolution, bool)
    ):
        raise InvalidAnalysisOutput(f"{where} resolution_index must be an integer.")
    return ReworkResponse(
        item=_read_text(entry["item"], f"{where} item"),
        outcome=_read_enum(ReworkOutcome, entry["outcome"], where),
        explanation=_read_text(entry["explanation"], f"{where} explanation"),
        product_question_index=question,
        resolution_index=resolution,
        evidence=tuple(
            _read_source(source, f"{where} evidence {position}")
            for position, source in enumerate(
                _as_list(entry.get("evidence"), f"{where} evidence")
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
    _reject_unknown(
        entry, PRODUCT_QUESTION_KEYS | PRODUCT_QUESTION_OPTIONAL_KEYS, where
    )
    missing = sorted((PRODUCT_QUESTION_KEYS | {"authority"}) - set(entry))
    if missing:
        raise InvalidAnalysisOutput(f"{where} is missing: " + ", ".join(missing))
    if not isinstance(entry["material"], bool):
        raise InvalidAnalysisOutput(f"{where} material must be true or false.")
    detail = _read_single_line(entry["detail"], f"{where} detail")
    authority = _read_enum(ResolutionClass, entry["authority"], f"{where} authority")
    if authority not in QUESTION_AUTHORITIES:
        raise InvalidAnalysisOutput(
            f"{where} authority is {authority.value}; an unresolved product "
            "question is HUMAN_REQUIRED or INSUFFICIENT_EVIDENCE. A resolved one "
            "belongs in resolutions, and technical HOW is not a product question."
        )
    alternatives = tuple(
        _read_single_line(option, f"{where} alternative {position}")
        for position, option in enumerate(
            _as_list(entry.get("alternatives"), f"{where} alternatives")
        )
    )
    if (
        authority is ResolutionClass.INSUFFICIENT_EVIDENCE
        and len(alternatives) < MIN_ALTERNATIVES
    ):
        raise InvalidAnalysisOutput(
            f"{where} is INSUFFICIENT_EVIDENCE and must offer at least "
            f"{MIN_ALTERNATIVES} alternatives for the human to decide between."
        )
    return ProductQuestion(
        detail=detail,
        material=entry["material"],
        authority=authority,
        alternatives=alternatives,
    )


def _read_single_line(value: object, where: str) -> str:
    text = _read_text(value, where)
    if not is_single_line(text):
        raise InvalidAnalysisOutput(f"{where} must be a single line.")
    return text


def _read_resolution(entry: object, index: int) -> Resolution:
    """One resolution's closed shape and its class rules (§4).

    Whether each quote exists in its source, and whether a clause exists in
    the active policy, is `resolution_evidence`'s check against what was read.
    """
    where = f"resolution {index}"
    if not isinstance(entry, dict):
        raise InvalidAnalysisOutput(f"{where} must be an object.")
    _reject_unknown(entry, RESOLUTION_KEYS, where)
    missing = sorted((RESOLUTION_KEYS - {"policy_clause"}) - set(entry))
    if missing:
        raise InvalidAnalysisOutput(f"{where} is missing: " + ", ".join(missing))
    resolution_class = _read_enum(ResolutionClass, entry["class"], f"{where} class")
    if resolution_class not in AUTONOMOUS_CLASSES:
        raise InvalidAnalysisOutput(
            f"{where} has class {resolution_class.value}, which is not a "
            "resolution: an open question stays in product_questions."
        )
    sections = _as_list(entry["affected_sections"], f"{where} affected_sections")
    if (
        not sections
        or not all(isinstance(key, str) for key in sections)
        or len(set(sections)) != len(sections)
        or not set(sections) <= RESOLVABLE_SECTIONS
    ):
        raise InvalidAnalysisOutput(
            f"{where} affected_sections must name normalized sections, each once: "
            + ", ".join(sorted(RESOLVABLE_SECTIONS))
        )
    sources = tuple(
        _read_source(source, f"{where} source {position}")
        for position, source in enumerate(
            _as_list(entry["sources"], f"{where} sources")
        )
    )
    clause = entry.get("policy_clause")
    resolution = Resolution(
        resolution_class=resolution_class,
        issue=_read_single_line(entry["issue"], f"{where} issue"),
        answer=_read_text(entry["answer"], f"{where} answer"),
        affected_sections=tuple(sections),
        sources=sources,
        justification=_read_text(entry["justification"], f"{where} justification"),
        policy_clause=(
            _read_text(clause, f"{where} policy_clause") if clause is not None else None
        ),
    )
    require_resolution_shape(resolution, where, InvalidAnalysisOutput)
    return resolution


def require_resolution_shape(
    resolution: Resolution, where: str, error: type[ValueError]
) -> None:
    """The class rules of section 4, shared with the Process Result reader."""
    kinds = {source.kind for source in resolution.sources}
    resolution_class = resolution.resolution_class
    if not resolution.sources:
        raise error(f"{where} cites no source.")
    if resolution_class is ResolutionClass.SOURCE_GROUNDED and not kinds <= {
        SourceKind.RAW,
        SourceKind.REQUIREMENT,
    }:
        raise error(
            f"{where} is SOURCE_GROUNDED and may cite only the RAW and this "
            "Requirement; a dependency is DEPENDENCY_GROUNDED."
        )
    if (
        resolution_class is ResolutionClass.DEPENDENCY_GROUNDED
        and SourceKind.DEPENDENCY not in kinds
    ):
        raise error(f"{where} is DEPENDENCY_GROUNDED but cites no dependency.")
    is_delegated = resolution_class is ResolutionClass.DELEGATED_DEFAULT
    if is_delegated != (resolution.policy_clause is not None):
        raise error(
            f"{where}: a policy_clause is named by DELEGATED_DEFAULT and by no "
            "other class."
        )


def _read_source(entry: object, where: str) -> SourceCitation:
    if not isinstance(entry, dict):
        raise InvalidAnalysisOutput(f"{where} must be an object.")
    _reject_unknown(entry, SOURCE_KEYS, where)
    if "kind" not in entry or "quote" not in entry:
        raise InvalidAnalysisOutput(f"{where} needs a kind and a quote.")
    kind = _read_enum(SourceKind, entry["kind"], f"{where} kind")
    quote = _read_text(entry["quote"], f"{where} quote")
    if len(quote) < MIN_QUOTE_CHARACTERS:
        raise InvalidAnalysisOutput(
            f"{where} quote is shorter than {MIN_QUOTE_CHARACTERS} characters."
        )
    requirement_id = entry.get("requirement_id")
    if kind is SourceKind.REQUIREMENT:
        if requirement_id is not None:
            raise InvalidAnalysisOutput(
                f"{where} quotes this Requirement and must not name one."
            )
    else:
        if requirement_id is None:
            raise InvalidAnalysisOutput(
                f"{where} quotes a {kind.value} and must name its Requirement ID."
            )
        requirement_id = _read_requirement_id(requirement_id, where)
    return SourceCitation(kind=kind, quote=quote, requirement_id=requirement_id)


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
