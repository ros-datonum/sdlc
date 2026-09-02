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
from dataclasses import dataclass

from sdlc.raw_source import canonical_markdown, fingerprint_of
from sdlc.standard_analysis import (
    SECTION_KEYS,
    AnalysisResult,
    Finding,
    FindingKind,
    InvalidAnalysisOutput,
    NormalizedRequirement,
    ProposedRelation,
    RelationKind,
)

PROCESS_RESULT_VERSION = "0.1"
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
NORMALIZED_KEY = "normalized_requirement"
ANALYSIS_KEY = "analysis"
FINDINGS_KEY = "findings"
RELATIONS_KEY = "proposed_relations"


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


def document_fingerprint(content: str) -> str:
    """Fingerprint Root Document content.

    Fingerprints the same canonical representation `content_equivalent`
    compares, so the two agree by construction:

        content_equivalent(a, b)  <=>  document_fingerprint(a) == ...(b)

    Without that, Fibery's Markdown re-serialization would make an untouched
    document look edited and force a spurious processing iteration.
    """
    return fingerprint_of(canonical_markdown(content))


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

    @property
    def name(self) -> str:
        return process_result_name(self.requirement_id, self.iteration)


def build_process_result(
    requirement_id: str,
    iteration: int,
    input_fingerprint: str,
    analysis: AnalysisResult,
) -> ProcessResult:
    """Assemble the artifact, fingerprinting the document it will produce."""
    document = analysis.normalized.document(requirement_id)
    return ProcessResult(
        requirement_id=requirement_id,
        iteration=iteration,
        input_fingerprint=input_fingerprint,
        output_fingerprint=document_fingerprint(document),
        normalized=analysis.normalized,
        analysis=dict(analysis.analysis),
        findings=tuple(analysis.findings),
        proposed_relations=tuple(analysis.proposed_relations),
    )


def render_process_result(result: ProcessResult) -> str:
    """Render the artifact: a short human header plus the machine payload."""
    payload = {
        VERSION_KEY: result.version,
        ITERATION_KEY: result.iteration,
        REQUIREMENT_ID_KEY: result.requirement_id,
        INPUT_FINGERPRINT_KEY: result.input_fingerprint,
        OUTPUT_FINGERPRINT_KEY: result.output_fingerprint,
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
    if version != PROCESS_RESULT_VERSION:
        raise InvalidProcessResult(
            f"Process Result version {version!r} is not supported; this "
            f"processor reads {PROCESS_RESULT_VERSION!r}."
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

    return ProcessResult(
        requirement_id=requirement_id,
        iteration=iteration,
        input_fingerprint=_require_text(
            payload.get(INPUT_FINGERPRINT_KEY), "input_fingerprint"
        ),
        output_fingerprint=_require_text(
            payload.get(OUTPUT_FINGERPRINT_KEY), "output_fingerprint"
        ),
        normalized=normalized,
        analysis=dict(payload.get(ANALYSIS_KEY) or {}),
        findings=tuple(
            _read_finding(entry) for entry in (payload.get(FINDINGS_KEY) or [])
        ),
        proposed_relations=tuple(
            _read_relation(entry) for entry in (payload.get(RELATIONS_KEY) or [])
        ),
        version=version,
    )


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
