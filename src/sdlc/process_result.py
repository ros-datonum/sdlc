"""Process Result iterations for Standard Requirement processing.

Unlike the RAW Processing Result, which is a single artifact per RAW, a Standard
Requirement may be processed deliberately more than once. Each attempt writes a
numbered, immutable child Document and records the Root Document content it
consumed and produced, as fingerprints.

Those two fingerprints are what separate a genuinely changed input from someone
toggling the workflow state: re-entering Process with an unchanged document is
recognised and costs no model call.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace

from sdlc.autonomy_policy import FINGERPRINT_PATTERN, PolicyBinding
from sdlc.normative_tree import (
    LEGACY_NORMATIVE_TREE_VERSION,
    NORMATIVE_TREE_VERSION,
    InvalidTreeManifest,
    TreeManifest,
    document_fingerprint,
)
from sdlc.rework_brief import InvalidReworkBrief, ReworkBrief, run_input_identity
from sdlc.standard_analysis import (
    MIN_ALTERNATIVES,
    MIN_QUOTE_CHARACTERS,
    RESOLVABLE_SECTIONS,
    SECTION_KEYS,
    AnalysisResult,
    Finding,
    FindingKind,
    InvalidAnalysisOutput,
    NormalizedRequirement,
    ProductQuestion,
    ProposedRelation,
    RelationKind,
    Resolution,
    ResolutionClass,
    ReworkExpectation,
    ReworkOutcome,
    ReworkResponse,
    SourceCitation,
    SourceKind,
    require_resolution_shape,
    require_rework_coverage,
)

# 0.6 is 0.5 plus the autonomous resolutions with their bound citations, the
# autonomy policy the run had, each product question's authority and
# alternatives, and each rework response's resolution and evidence
# (Requirement-Autonomous-Resolution-v0.1).
# 0.5 is 0.4 plus the Rework Brief the iteration received (null when none),
# one response per Brief item and the run-input identity
# (Requirement-Rework-Brief-v0.1). 0.4 is 0.3 plus the structured product
# questions of the Material-WHAT Gate v0.1; no older iteration received any
# review feedback. 0.3 binds the normative tree with manifest v2 (exact canonical-byte
# document fingerprints, audit A8); it stays current tree evidence but carries
# no question evidence. 0.2 bound manifest v1 under the older fingerprint
# algorithm; 0.1 is the Root-only binding. Older versions stay readable as
# history under their own semantics and are never written or rewritten.
PROCESS_RESULT_VERSION = "0.6"
PRE_RESOLUTION_PROCESS_RESULT_VERSION = "0.5"
PRE_REWORK_PROCESS_RESULT_VERSION = "0.4"
PRE_QUESTION_PROCESS_RESULT_VERSION = "0.3"
TREE_BOUND_LEGACY_PROCESS_RESULT_VERSION = "0.2"
LEGACY_PROCESS_RESULT_VERSION = "0.1"
SUPPORTED_PROCESS_RESULT_VERSIONS = frozenset(
    {
        PROCESS_RESULT_VERSION,
        PRE_RESOLUTION_PROCESS_RESULT_VERSION,
        PRE_REWORK_PROCESS_RESULT_VERSION,
        PRE_QUESTION_PROCESS_RESULT_VERSION,
        TREE_BOUND_LEGACY_PROCESS_RESULT_VERSION,
        LEGACY_PROCESS_RESULT_VERSION,
    }
)
#: Versions whose tree binding is manifest v2: the current tree evidence.
CURRENT_TREE_PROCESS_RESULT_VERSIONS = frozenset(
    {
        PROCESS_RESULT_VERSION,
        PRE_RESOLUTION_PROCESS_RESULT_VERSION,
        PRE_REWORK_PROCESS_RESULT_VERSION,
        PRE_QUESTION_PROCESS_RESULT_VERSION,
    }
)
#: Versions that record the structured product questions.
QUESTION_BOUND_PROCESS_RESULT_VERSIONS = frozenset(
    {
        PROCESS_RESULT_VERSION,
        PRE_RESOLUTION_PROCESS_RESULT_VERSION,
        PRE_REWORK_PROCESS_RESULT_VERSION,
    }
)
#: Versions that record which review feedback they received.
REWORK_BOUND_PROCESS_RESULT_VERSIONS = frozenset(
    {PROCESS_RESULT_VERSION, PRE_RESOLUTION_PROCESS_RESULT_VERSION}
)
# The manifest version each tree-bound Result version must carry; a payload
# that mixes them is a contradiction, never a best-effort read.
MANIFEST_VERSION_BY_RESULT_VERSION = {
    TREE_BOUND_LEGACY_PROCESS_RESULT_VERSION: LEGACY_NORMATIVE_TREE_VERSION,
    PRE_QUESTION_PROCESS_RESULT_VERSION: NORMATIVE_TREE_VERSION,
    PRE_REWORK_PROCESS_RESULT_VERSION: NORMATIVE_TREE_VERSION,
    PRE_RESOLUTION_PROCESS_RESULT_VERSION: NORMATIVE_TREE_VERSION,
    PROCESS_RESULT_VERSION: NORMATIVE_TREE_VERSION,
}
PROCESS_RESULT_SUFFIX = "Process Result"
ITERATION_WIDTH = 4
FIRST_ITERATION = 1

NAME_PATTERN = re.compile(
    rf"^(?P<requirement_id>.+) — {PROCESS_RESULT_SUFFIX} (?P<iteration>\d{{{ITERATION_WIDTH},}})$"
)
JSON_FENCE = re.compile(r"```json\s*\n(?P<body>.*?)\n```", re.DOTALL)

VERSION_KEY = "process_result_version"
ITERATION_KEY = "iteration"
REQUIREMENT_ID_KEY = "requirement_id"
INPUT_FINGERPRINT_KEY = "input_fingerprint"
OUTPUT_FINGERPRINT_KEY = "output_fingerprint"
INPUT_TREE_KEY = "normative_input_tree"
OUTPUT_TREE_KEY = "normative_output_tree"
NORMALIZED_KEY = "normalized_requirement"
ANALYSIS_KEY = "analysis"
FINDINGS_KEY = "findings"
RELATIONS_KEY = "proposed_relations"
PRODUCT_QUESTIONS_KEY = "product_questions"
REWORK_BRIEF_KEY = "rework_brief"
REWORK_RESPONSES_KEY = "rework_responses"
RUN_INPUT_KEY = "run_input_identity"
REWORK_KEYS = (REWORK_BRIEF_KEY, REWORK_RESPONSES_KEY, RUN_INPUT_KEY)
RESOLUTIONS_KEY = "resolutions"
AUTONOMY_POLICY_KEY = "autonomy_policy"
RESOLUTION_KEYS = (RESOLUTIONS_KEY, AUTONOMY_POLICY_KEY)
LEGACY_QUESTION_KEYS = frozenset({"detail", "material"})
QUESTION_KEYS = LEGACY_QUESTION_KEYS | {"authority", "alternatives"}
LEGACY_RESPONSE_KEYS = frozenset(
    {"item", "outcome", "explanation", "product_question_index"}
)
RESPONSE_KEYS = LEGACY_RESPONSE_KEYS | {"resolution_index", "evidence"}
PERSISTED_RESOLUTION_KEYS = frozenset(
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
CITATION_KEYS = frozenset(
    {"kind", "requirement_id", "entity_id", "fingerprint", "quote"}
)


class InvalidProcessResult(ValueError):
    """A persisted Process Result cannot be trusted to resume from."""


def process_result_name(requirement_id: str, iteration: int) -> str:
    """`<Requirement ID> — Process Result 0001`."""
    return f"{requirement_id} — {PROCESS_RESULT_SUFFIX} {iteration:0{ITERATION_WIDTH}d}"


def parse_process_result_name(name: str) -> tuple[str, int] | None:
    """Split an artifact name back into Requirement ID and iteration."""
    match = NAME_PATTERN.match(name.strip())
    if match is None:
        return None
    return match.group("requirement_id"), int(match.group("iteration"))


@dataclass(frozen=True)
class ProcessResult:
    """One completed or in-flight processing iteration."""

    requirement_id: str
    iteration: int
    input_fingerprint: str
    output_fingerprint: str
    normalized: NormalizedRequirement
    analysis: dict[str, str]
    findings: tuple[Finding, ...]
    proposed_relations: tuple[ProposedRelation, ...]
    version: str = PROCESS_RESULT_VERSION
    # The tree this iteration consumed and the tree it intends to produce:
    # the same Documents, parents and names, with only the Root's content
    # fingerprint replaced. None on a legacy 0.1 result.
    input_tree: TreeManifest | None = None
    output_tree: TreeManifest | None = None
    # The structured open product questions (0.4 and later). None on every
    # older version: their absence is "not recorded", never "there were none".
    product_questions: tuple[ProductQuestion, ...] | None = None
    # The Rework Brief this iteration received and its answer to each item
    # (0.5). None and () on an initial Process and on every older version,
    # none of which ever received review feedback.
    rework_brief: ReworkBrief | None = None
    rework_responses: tuple[ReworkResponse, ...] = ()
    # The resolutions and the policy the run had (0.6). () and None on every
    # older version, which recorded none: never "there were none".
    resolutions: tuple[Resolution, ...] = ()
    autonomy_policy: PolicyBinding | None = None

    @property
    def name(self) -> str:
        return process_result_name(self.requirement_id, self.iteration)

    @property
    def has_question_evidence(self) -> bool:
        """Whether this iteration recorded its product questions (0.4+)."""
        return self.version in QUESTION_BOUND_PROCESS_RESULT_VERSIONS and (
            self.product_questions is not None
        )

    @property
    def is_rework_bound(self) -> bool:
        """Whether this iteration records which review feedback it received."""
        return self.version in REWORK_BOUND_PROCESS_RESULT_VERSIONS

    @property
    def is_resolution_bound(self) -> bool:
        """Whether this iteration records its resolutions and policy (0.6)."""
        return self.version == PROCESS_RESULT_VERSION

    @property
    def relies_on_policy(self) -> bool:
        """Whether a resolution's authority is a delegated policy clause."""
        return any(
            resolution.resolution_class is ResolutionClass.DELEGATED_DEFAULT
            for resolution in self.resolutions
        )

    @property
    def citations(self) -> tuple[SourceCitation, ...]:
        """Every bound citation: the resolutions' sources and rebuttal evidence."""
        return tuple(
            source for resolution in self.resolutions for source in resolution.sources
        ) + tuple(
            source for response in self.rework_responses for source in response.evidence
        )

    @property
    def brief_identity(self) -> str | None:
        return self.rework_brief.identity if self.rework_brief else None

    @property
    def run_input_identity(self) -> str | None:
        """The normative input tree and the Brief this iteration consumed.

        None for a 0.1 result, which binds no tree. Before 0.5 no iteration
        received review feedback, so its Brief is none by construction.
        """
        if self.input_tree is None:
            return None
        return run_input_identity(
            self.input_tree.fingerprint,
            self.brief_identity,
            self.autonomy_policy.fingerprint if self.autonomy_policy else None,
        )

    @property
    def is_tree_bound(self) -> bool:
        return self.input_tree is not None and self.output_tree is not None

    @property
    def is_current(self) -> bool:
        """0.3 or 0.4 with manifest v2 on both trees: current tree evidence.

        0.1 and 0.2 are history under their own algorithms; they are read,
        never replayed, certified or applied. Whether a current Result also
        carries question evidence is `has_question_evidence`.
        """
        return (
            self.version in CURRENT_TREE_PROCESS_RESULT_VERSIONS
            and self.input_tree is not None
            and self.output_tree is not None
            and self.input_tree.is_current
            and self.output_tree.is_current
        )


def build_process_result(
    requirement_id: str,
    iteration: int,
    input_fingerprint: str,
    analysis: AnalysisResult,
    input_tree: TreeManifest,
    rework_brief: ReworkBrief | None = None,
    autonomy_policy: PolicyBinding | None = None,
) -> ProcessResult:
    """Assemble the artifact, fingerprinting the document it will produce.

    The intended output tree is derived here from the deterministic rendering
    of the normalized document, never from anything the model supplied.
    `rework_brief` is the feedback this iteration received, bound as is;
    `autonomy_policy` the policy the run had. `analysis` carries bound
    citations (`resolution_evidence.bind_citations`).
    """
    if any(not source.is_bound for source in _citations(analysis)):
        raise InvalidProcessResult(
            "A Process Result binds every citation to the source that was read."
        )
    if any(question.authority is None for question in analysis.product_questions):
        raise InvalidProcessResult(
            "A Process Result records why each product question stays open."
        )
    document = analysis.normalized.document(requirement_id)
    output_fingerprint = document_fingerprint(document)
    if not input_tree.is_current:
        raise InvalidProcessResult(
            f"A Process Result {PROCESS_RESULT_VERSION} binds manifest version "
            f"{NORMATIVE_TREE_VERSION}, not {input_tree.version}."
        )
    if input_tree.root_entry.content_fingerprint != input_fingerprint:
        raise InvalidProcessResult(
            "The captured tree's Root fingerprint disagrees with input_fingerprint."
        )
    return ProcessResult(
        requirement_id=requirement_id,
        iteration=iteration,
        input_fingerprint=input_fingerprint,
        output_fingerprint=output_fingerprint,
        normalized=analysis.normalized,
        analysis=dict(analysis.analysis),
        findings=tuple(analysis.findings),
        proposed_relations=tuple(analysis.proposed_relations),
        input_tree=input_tree,
        output_tree=input_tree.with_root_fingerprint(output_fingerprint),
        product_questions=tuple(analysis.product_questions),
        rework_brief=rework_brief,
        rework_responses=tuple(analysis.rework_responses),
        resolutions=tuple(analysis.resolutions),
        autonomy_policy=autonomy_policy,
    )


def _citations(analysis: AnalysisResult) -> tuple[SourceCitation, ...]:
    return tuple(
        source for resolution in analysis.resolutions for source in resolution.sources
    ) + tuple(
        source for response in analysis.rework_responses for source in response.evidence
    )


def render_process_result(result: ProcessResult) -> str:
    """Render the artifact: a short human header plus the machine payload."""
    is_question_bound = result.version in QUESTION_BOUND_PROCESS_RESULT_VERSIONS
    if is_question_bound and result.product_questions is None:
        raise InvalidProcessResult(
            f"A Process Result {result.version} must carry its product questions."
        )
    payload = {
        VERSION_KEY: result.version,
        ITERATION_KEY: result.iteration,
        REQUIREMENT_ID_KEY: result.requirement_id,
        INPUT_FINGERPRINT_KEY: result.input_fingerprint,
        OUTPUT_FINGERPRINT_KEY: result.output_fingerprint,
        **(
            {
                INPUT_TREE_KEY: result.input_tree.to_payload(),
                OUTPUT_TREE_KEY: result.output_tree.to_payload(),
            }
            if result.version != LEGACY_PROCESS_RESULT_VERSION
            and result.input_tree is not None
            and result.output_tree is not None
            else {}
        ),
        NORMALIZED_KEY: {
            "title": result.normalized.title,
            **{key: getattr(result.normalized, key) for key in SECTION_KEYS},
        },
        ANALYSIS_KEY: result.analysis,
        FINDINGS_KEY: [
            {
                "kind": finding.kind.value,
                "requirement_id": finding.requirement_id,
                "detail": finding.detail,
            }
            for finding in result.findings
        ],
        RELATIONS_KEY: [
            {
                "kind": relation.kind.value,
                "requirement_id": relation.requirement_id,
                "rationale": relation.rationale,
            }
            for relation in result.proposed_relations
        ],
        **(
            {
                PRODUCT_QUESTIONS_KEY: [
                    question_payload(question, result.is_resolution_bound)
                    for question in result.product_questions
                ]
            }
            if is_question_bound
            else {}
        ),
        **(_rework_payload(result) if result.is_rework_bound else {}),
        **(
            {
                RESOLUTIONS_KEY: [
                    resolution_payload(resolution) for resolution in result.resolutions
                ],
                AUTONOMY_POLICY_KEY: (
                    result.autonomy_policy.to_payload()
                    if result.autonomy_policy
                    else None
                ),
            }
            if result.is_resolution_bound
            else {}
        ),
    }
    body = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False)
    return (
        f"# {result.name}\n"
        "\n"
        "Process artifact written by the Standard Requirement Processor. It "
        "records the validated normalization and analysis of one processing "
        "iteration so a retry can resume without asking the model again. It is "
        "immutable process history, and the relations it proposes are not "
        "written to Fibery.\n"
        "\n"
        f"```json\n{body}\n```\n"
    )


def _rework_payload(result: ProcessResult) -> dict[str, object]:
    return {
        REWORK_BRIEF_KEY: (
            result.rework_brief.to_payload() if result.rework_brief else None
        ),
        REWORK_RESPONSES_KEY: [
            response_payload(response, result.is_resolution_bound)
            for response in result.rework_responses
        ],
        RUN_INPUT_KEY: result.run_input_identity,
    }


def question_payload(
    question: ProductQuestion, resolution_bound: bool
) -> dict[str, object]:
    """A persisted product question; 0.6 adds its authority and alternatives."""
    payload: dict[str, object] = {
        "detail": question.detail,
        "material": question.material,
    }
    if resolution_bound:
        payload["authority"] = question.authority.value if question.authority else None
        payload["alternatives"] = list(question.alternatives)
    return payload


def response_payload(
    response: ReworkResponse, resolution_bound: bool
) -> dict[str, object]:
    """A persisted rework response; 0.6 adds its resolution and evidence."""
    payload: dict[str, object] = {
        "item": response.item,
        "outcome": response.outcome.value,
        "explanation": response.explanation,
        "product_question_index": response.product_question_index,
    }
    if resolution_bound:
        payload["resolution_index"] = response.resolution_index
        payload["evidence"] = [citation_payload(item) for item in response.evidence]
    return payload


def citation_payload(citation: SourceCitation) -> dict[str, object]:
    return {
        "kind": citation.kind.value,
        "requirement_id": citation.requirement_id,
        "entity_id": citation.entity_id,
        "fingerprint": citation.fingerprint,
        "quote": citation.quote,
    }


def resolution_payload(resolution: Resolution) -> dict[str, object]:
    return {
        "class": resolution.resolution_class.value,
        "issue": resolution.issue,
        "answer": resolution.answer,
        "affected_sections": list(resolution.affected_sections),
        "sources": [citation_payload(source) for source in resolution.sources],
        "policy_clause": resolution.policy_clause,
        "justification": resolution.justification,
    }


def parse_process_result(text: str) -> ProcessResult:
    """Read a persisted iteration back, or refuse to resume from it."""
    match = JSON_FENCE.search(text or "")
    if match is None:
        raise InvalidProcessResult(
            "The Process Result document contains no JSON payload."
        )
    try:
        payload = json.loads(match.group("body"))
    except ValueError as error:
        raise InvalidProcessResult(
            f"The Process Result payload is not valid JSON: {error}"
        ) from error
    if not isinstance(payload, dict):
        raise InvalidProcessResult("The Process Result payload must be an object.")

    version = payload.get(VERSION_KEY)
    if version not in SUPPORTED_PROCESS_RESULT_VERSIONS:
        raise InvalidProcessResult(
            f"Process Result version {version!r} is not supported; this "
            f"processor reads {sorted(SUPPORTED_PROCESS_RESULT_VERSIONS)!r}."
        )
    iteration = payload.get(ITERATION_KEY)
    if not isinstance(iteration, int) or iteration < FIRST_ITERATION:
        raise InvalidProcessResult(
            f"Process Result iteration {iteration!r} is not a positive integer."
        )
    requirement_id = _require_text(payload.get(REQUIREMENT_ID_KEY), "requirement_id")

    try:
        normalized_payload = payload.get(NORMALIZED_KEY) or {}
        normalized = NormalizedRequirement(
            title=normalized_payload["title"],
            **{key: normalized_payload[key] for key in SECTION_KEYS},
        )
    except (KeyError, TypeError, InvalidAnalysisOutput) as error:
        raise InvalidProcessResult(
            f"The persisted normalized requirement is incomplete: {error}"
        ) from error

    input_fingerprint = _require_text(
        payload.get(INPUT_FINGERPRINT_KEY), "input_fingerprint"
    )
    output_fingerprint = _require_text(
        payload.get(OUTPUT_FINGERPRINT_KEY), "output_fingerprint"
    )
    input_tree, output_tree = _read_trees(
        payload, version, requirement_id, input_fingerprint, output_fingerprint
    )
    result = ProcessResult(
        requirement_id=requirement_id,
        iteration=iteration,
        input_fingerprint=input_fingerprint,
        output_fingerprint=output_fingerprint,
        normalized=normalized,
        analysis=dict(payload.get(ANALYSIS_KEY) or {}),
        findings=tuple(
            _read_finding(entry) for entry in (payload.get(FINDINGS_KEY) or [])
        ),
        proposed_relations=tuple(
            _read_relation(entry) for entry in (payload.get(RELATIONS_KEY) or [])
        ),
        version=version,
        input_tree=input_tree,
        output_tree=output_tree,
        product_questions=_read_product_questions(payload, version),
    )
    return _with_rework_evidence(_with_resolutions(result, payload), payload)


def _with_resolutions(
    result: ProcessResult, payload: dict[str, object]
) -> ProcessResult:
    """0.6 carries its resolutions and policy binding; no older version may."""
    if not result.is_resolution_bound:
        present = [key for key in RESOLUTION_KEYS if key in payload]
        if present:
            raise InvalidProcessResult(
                f"A {result.version} Process Result cannot carry resolution "
                "evidence: " + ", ".join(present)
            )
        return result
    missing = [key for key in RESOLUTION_KEYS if key not in payload]
    if missing:
        raise InvalidProcessResult(
            f"A {PROCESS_RESULT_VERSION} Process Result is missing its resolution "
            "evidence: " + ", ".join(missing)
        )
    entries = payload[RESOLUTIONS_KEY]
    if not isinstance(entries, list):
        raise InvalidProcessResult(f"{RESOLUTIONS_KEY} must be a list.")
    resolutions = tuple(
        read_resolution_payload(entry, InvalidProcessResult) for entry in entries
    )
    binding = payload[AUTONOMY_POLICY_KEY]
    try:
        policy = PolicyBinding.from_payload(binding) if binding is not None else None
    except ValueError as error:
        raise InvalidProcessResult(str(error)) from error
    bound = replace(result, resolutions=resolutions, autonomy_policy=policy)
    if bound.relies_on_policy and policy is None:
        raise InvalidProcessResult(
            "A DELEGATED_DEFAULT resolution needs the autonomy policy it relied on."
        )
    return bound


def read_resolution_payload(entry: object, error: type[ValueError]) -> Resolution:
    """A persisted resolution, held to its closed shape and class rules."""
    if not isinstance(entry, dict) or set(entry) != PERSISTED_RESOLUTION_KEYS:
        raise error(f"Malformed persisted resolution: {entry!r}")
    try:
        resolution_class = ResolutionClass(entry["class"])
    except ValueError as cause:
        raise error(f"Malformed persisted resolution: {cause}") from cause
    sections = entry["affected_sections"]
    sources = entry["sources"]
    clause = entry["policy_clause"]
    if (
        not all(
            isinstance(entry[key], str) and entry[key].strip()
            for key in ("issue", "answer", "justification")
        )
        or not isinstance(sections, list)
        or not sections
        or not all(
            isinstance(key, str) and key in RESOLVABLE_SECTIONS for key in sections
        )
        or len(set(sections)) != len(sections)
        or not isinstance(sources, list)
        or (clause is not None and (not isinstance(clause, str) or not clause.strip()))
    ):
        raise error(f"Malformed persisted resolution: {entry!r}")
    resolution = Resolution(
        resolution_class=resolution_class,
        issue=entry["issue"],
        answer=entry["answer"],
        affected_sections=tuple(sections),
        sources=tuple(read_citation_payload(item, error) for item in sources),
        justification=entry["justification"],
        policy_clause=clause,
    )
    require_resolution_shape(resolution, "A persisted resolution", error)
    return resolution


def read_citation_payload(entry: object, error: type[ValueError]) -> SourceCitation:
    """A persisted, bound citation: identity and fingerprint present, or refused."""
    if not isinstance(entry, dict) or set(entry) != CITATION_KEYS:
        raise error(f"Malformed persisted citation: {entry!r}")
    try:
        kind = SourceKind(entry["kind"])
    except ValueError as cause:
        raise error(f"Malformed persisted citation: {cause}") from cause
    quote, requirement_id, entity_id, fingerprint = (
        entry["quote"],
        entry["requirement_id"],
        entry["entity_id"],
        entry["fingerprint"],
    )
    names_entity = kind is not SourceKind.REQUIREMENT
    if (
        not isinstance(quote, str)
        or len(quote.strip()) < MIN_QUOTE_CHARACTERS
        or not isinstance(fingerprint, str)
        or not FINGERPRINT_PATTERN.match(fingerprint)
        or names_entity
        != (isinstance(requirement_id, str) and bool(requirement_id.strip()))
        or names_entity != (isinstance(entity_id, str) and bool(entity_id.strip()))
        or (not names_entity and (requirement_id is not None or entity_id is not None))
    ):
        raise error(f"Malformed persisted citation: {entry!r}")
    return SourceCitation(
        kind=kind,
        quote=quote,
        requirement_id=requirement_id,
        entity_id=entity_id,
        fingerprint=fingerprint,
    )


def _with_rework_evidence(
    result: ProcessResult, payload: dict[str, object]
) -> ProcessResult:
    """0.5+ carries all three rework keys, re-validated; no older version may."""
    if not result.is_rework_bound:
        present = [key for key in REWORK_KEYS if key in payload]
        if present:
            raise InvalidProcessResult(
                f"A {result.version} Process Result cannot carry rework evidence: "
                + ", ".join(present)
            )
        return result
    missing = [key for key in REWORK_KEYS if key not in payload]
    if missing:
        raise InvalidProcessResult(
            f"A {PROCESS_RESULT_VERSION} Process Result is missing its rework "
            "evidence: " + ", ".join(missing)
        )
    brief = _read_brief(payload[REWORK_BRIEF_KEY], result.requirement_id)
    entries = payload[REWORK_RESPONSES_KEY]
    if not isinstance(entries, list):
        raise InvalidProcessResult(f"{REWORK_RESPONSES_KEY} must be a list.")
    responses = tuple(
        _read_rework_response(entry, result.is_resolution_bound) for entry in entries
    )
    if brief is None and responses:
        raise InvalidProcessResult(
            "A Process Result that received no Rework Brief cannot answer one."
        )
    if brief is not None:
        try:
            require_rework_coverage(
                responses,
                ReworkExpectation(
                    brief.item_refs, brief.what_refs, brief.resolution_refs
                ),
                result.product_questions or (),
                result.resolutions if result.is_resolution_bound else None,
            )
        except InvalidAnalysisOutput as error:
            raise InvalidProcessResult(
                f"The persisted rework responses are incoherent: {error}"
            ) from error
    bound = replace(result, rework_brief=brief, rework_responses=responses)
    if payload[RUN_INPUT_KEY] != bound.run_input_identity:
        raise InvalidProcessResult(
            "The persisted run_input_identity does not match the bound input tree "
            "and Rework Brief."
        )
    return bound


def _read_brief(value: object, requirement_id: str) -> ReworkBrief | None:
    if value is None:
        return None
    try:
        brief = ReworkBrief.from_payload(value)
    except InvalidReworkBrief as error:
        raise InvalidProcessResult(f"Invalid Rework Brief: {error}") from error
    if brief.source.requirement_id != requirement_id:
        raise InvalidProcessResult(
            f"The Rework Brief comes from a review of {brief.source.requirement_id!r}, "
            f"not {requirement_id!r}."
        )
    return brief


def _read_rework_response(entry: object, resolution_bound: bool) -> ReworkResponse:
    keys = RESPONSE_KEYS if resolution_bound else LEGACY_RESPONSE_KEYS
    if not isinstance(entry, dict) or set(entry) != keys:
        raise InvalidProcessResult(f"Malformed persisted rework response: {entry!r}")
    explanation = entry["explanation"]
    index = entry["product_question_index"]
    try:
        outcome = ReworkOutcome(entry["outcome"])
    except ValueError as error:
        raise InvalidProcessResult(
            f"Malformed persisted rework response: {error}"
        ) from error
    if (
        not isinstance(entry["item"], str)
        or not isinstance(explanation, str)
        or not explanation.strip()
        or (
            index is not None
            and (not isinstance(index, int) or isinstance(index, bool))
        )
    ):
        raise InvalidProcessResult(f"Malformed persisted rework response: {entry!r}")
    resolution = entry.get("resolution_index")
    evidence = entry.get("evidence", [])
    if (
        resolution is not None
        and (not isinstance(resolution, int) or isinstance(resolution, bool))
    ) or not isinstance(evidence, list):
        raise InvalidProcessResult(f"Malformed persisted rework response: {entry!r}")
    return ReworkResponse(
        item=entry["item"],
        outcome=outcome,
        explanation=explanation,
        product_question_index=index,
        resolution_index=resolution,
        evidence=tuple(
            read_citation_payload(item, InvalidProcessResult) for item in evidence
        ),
    )


def _read_product_questions(
    payload: dict[str, object], version: str
) -> tuple[ProductQuestion, ...] | None:
    """0.4 and 0.5 carry the list, even empty; no older version may carry it."""
    if version not in QUESTION_BOUND_PROCESS_RESULT_VERSIONS:
        if PRODUCT_QUESTIONS_KEY in payload:
            raise InvalidProcessResult(
                f"A {version} Process Result cannot carry product questions."
            )
        return None
    entries = payload.get(PRODUCT_QUESTIONS_KEY)
    if not isinstance(entries, list):
        raise InvalidProcessResult(
            f"A {version} Process Result must carry its {PRODUCT_QUESTIONS_KEY} list."
        )
    return tuple(
        read_question_payload(
            entry, version == PROCESS_RESULT_VERSION, InvalidProcessResult
        )
        for entry in entries
    )


def read_question_payload(
    entry: object,
    resolution_bound: bool,
    error: type[ValueError],
    *,
    copies_older_process: bool = False,
) -> ProductQuestion:
    """A persisted product question; 0.6 and Review 0.7 carry its authority.

    `copies_older_process` is for a Review 0.7 reading its copy of the
    questions: a question copied from a Process Result older than 0.6 never
    recorded an authority and is copied in that older shape, never with an
    invented one. `what_clearance` then holds the copy to the bound Process.
    """
    keys = QUESTION_KEYS if resolution_bound else LEGACY_QUESTION_KEYS
    if (
        copies_older_process
        and isinstance(entry, dict)
        and set(entry) == LEGACY_QUESTION_KEYS
    ):
        keys, resolution_bound = LEGACY_QUESTION_KEYS, False
    if (
        not isinstance(entry, dict)
        or set(entry) != keys
        or not isinstance(entry["detail"], str)
        or not entry["detail"].strip()
        or not isinstance(entry["material"], bool)
    ):
        raise error(f"Malformed persisted product question: {entry!r}")
    if not resolution_bound:
        return ProductQuestion(detail=entry["detail"], material=entry["material"])
    alternatives = entry["alternatives"]
    try:
        authority = ResolutionClass(entry["authority"])
    except ValueError as cause:
        raise error(f"Malformed persisted product question: {cause}") from cause
    if (
        authority
        not in {ResolutionClass.HUMAN_REQUIRED, ResolutionClass.INSUFFICIENT_EVIDENCE}
        or not isinstance(alternatives, list)
        or not all(isinstance(item, str) and item.strip() for item in alternatives)
        or (
            authority is ResolutionClass.INSUFFICIENT_EVIDENCE
            and len(alternatives) < MIN_ALTERNATIVES
        )
    ):
        raise error(f"Malformed persisted product question: {entry!r}")
    return ProductQuestion(
        detail=entry["detail"],
        material=entry["material"],
        authority=authority,
        alternatives=tuple(alternatives),
    )


def _read_trees(
    payload: dict[str, object],
    version: str,
    requirement_id: str,
    input_fingerprint: str,
    output_fingerprint: str,
) -> tuple[TreeManifest | None, TreeManifest | None]:
    """The tree bindings of a 0.2 or 0.3 payload, validated for consistency.

    A legacy 0.1 payload has none, and none is ever synthesized for it. A
    tree-bound payload must carry both, owned by this Requirement, in the
    manifest version its own version declares, with Root entries agreeing
    with the retained Root fingerprints, and an output tree that preserves
    every child, parent and name of the input tree.
    """
    if version == LEGACY_PROCESS_RESULT_VERSION:
        if INPUT_TREE_KEY in payload or OUTPUT_TREE_KEY in payload:
            raise InvalidProcessResult(
                "A 0.1 Process Result cannot carry normative tree bindings."
            )
        return None, None
    try:
        input_tree = TreeManifest.from_payload(payload.get(INPUT_TREE_KEY))
        output_tree = TreeManifest.from_payload(payload.get(OUTPUT_TREE_KEY))
    except InvalidTreeManifest as error:
        raise InvalidProcessResult(
            f"Invalid normative tree binding: {error}"
        ) from error
    expected_manifest = MANIFEST_VERSION_BY_RESULT_VERSION[version]
    for label, tree in ((INPUT_TREE_KEY, input_tree), (OUTPUT_TREE_KEY, output_tree)):
        if tree.version != expected_manifest:
            raise InvalidProcessResult(
                f"A Process Result {version} binds manifest version "
                f"{expected_manifest}, but {label} is version {tree.version}; the "
                "payload mixes fingerprint algorithms."
            )
    for label, tree in ((INPUT_TREE_KEY, input_tree), (OUTPUT_TREE_KEY, output_tree)):
        if tree.requirement_id != requirement_id:
            raise InvalidProcessResult(
                f"{label} belongs to {tree.requirement_id!r}, not {requirement_id!r}."
            )
    if input_tree.root_entry.content_fingerprint != input_fingerprint:
        raise InvalidProcessResult(
            "normative_input_tree's Root entry disagrees with input_fingerprint."
        )
    if output_tree.root_entry.content_fingerprint != output_fingerprint:
        raise InvalidProcessResult(
            "normative_output_tree's Root entry disagrees with output_fingerprint."
        )
    if output_tree != input_tree.with_root_fingerprint(output_fingerprint):
        raise InvalidProcessResult(
            "normative_output_tree changes more than the Root content: a Process "
            "Result may not add, remove, rename, re-parent or alter children."
        )
    return input_tree, output_tree


def _require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidProcessResult(f"The Process Result has no {field}.")
    return value


def _read_finding(entry: object) -> Finding:
    if not isinstance(entry, dict):
        raise InvalidProcessResult("Each finding must be an object.")
    try:
        return Finding(
            kind=FindingKind(entry["kind"]),
            detail=entry["detail"],
            requirement_id=entry.get("requirement_id"),
        )
    except (KeyError, ValueError) as error:
        raise InvalidProcessResult(f"Malformed persisted finding: {error}") from error


def _read_relation(entry: object) -> ProposedRelation:
    if not isinstance(entry, dict):
        raise InvalidProcessResult("Each proposed relation must be an object.")
    try:
        return ProposedRelation(
            kind=RelationKind(entry["kind"]),
            requirement_id=entry["requirement_id"],
            rationale=entry["rationale"],
        )
    except (KeyError, ValueError) as error:
        raise InvalidProcessResult(f"Malformed persisted relation: {error}") from error
