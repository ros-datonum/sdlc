"""The persisted RAW processing artifact and deterministic candidate identity.

A Processing Result is the durable record of one validated model decomposition.
It exists so a retry never has to ask the model again: candidate identity, and
therefore the Fibery entity each candidate maps to, is reconstructed from this
document alone.

It is a process artifact stored as a child Document of the RAW Root Document.
It is not a Requirement, not a Database, and carries no chain-of-thought.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass

from sdlc.raw_processing import (
    SECTION_KEYS,
    Candidate,
    Category,
    Finding,
    FindingKind,
    InvalidModelOutput,
)

PROCESSING_RESULT_VERSION = "0.1"
PROCESSING_RESULT_SUFFIX = "Processing Result"

# Fixed namespace for deterministic candidate entity ids. Changing it would
# orphan every previously created candidate, so it must never change.
CANDIDATE_NAMESPACE = uuid.UUID("6f3c1d9e-58a4-5b2f-9c31-7a0e4d8b2f61")

CANDIDATE_KEY_PREFIX = "C"
CANDIDATE_KEY_WIDTH = 3

JSON_FENCE = re.compile(r"```json\s*\n(?P<body>.*?)\n```", re.DOTALL)

VERSION_KEY = "processing_result_version"
RAW_ID_KEY = "raw_requirement_id"
CANDIDATES_KEY = "candidates"
FINDINGS_KEY = "findings"
NO_CANDIDATE_REASON_KEY = "no_candidate_reason"
CANDIDATE_KEY_FIELD = "candidate_key"


class InvalidProcessingResult(ValueError):
    """A persisted Processing Result cannot be trusted to resume from."""


def candidate_key(index: int) -> str:
    """The stable key for the candidate at this position: C001, C002, ..."""
    return f"{CANDIDATE_KEY_PREFIX}{index + 1:0{CANDIDATE_KEY_WIDTH}d}"


def candidate_fibery_id(raw_fibery_id: str, key: str) -> str:
    """The deterministic Fibery entity id for one candidate.

    Derived from the RAW entity's uuid and the candidate key, so a retry that
    reaches the same candidate targets the same entity instead of creating a
    second one. This is execution identity only; it is never a Fibery Field and
    is not the human Requirement ID.
    """
    return str(uuid.uuid5(CANDIDATE_NAMESPACE, f"{raw_fibery_id}:{key}"))


@dataclass(frozen=True)
class KeyedCandidate:
    """One candidate with its assigned stable key."""

    key: str
    candidate: Candidate

    def fibery_id(self, raw_fibery_id: str) -> str:
        return candidate_fibery_id(raw_fibery_id, self.key)


@dataclass(frozen=True)
class ProcessingResult:
    """One validated decomposition, durable and immutable once persisted."""

    raw_requirement_id: str
    candidates: tuple[KeyedCandidate, ...]
    findings: tuple[Finding, ...]
    no_candidate_reason: str | None = None
    version: str = PROCESSING_RESULT_VERSION

    @property
    def is_empty(self) -> bool:
        return not self.candidates


def build_processing_result(raw_requirement_id: str, decomposition) -> ProcessingResult:
    """Assign candidate keys to a validated decomposition.

    Keys come from the validated order, assigned by this code. The model never
    chooses them.
    """
    return ProcessingResult(
        raw_requirement_id=raw_requirement_id,
        candidates=tuple(
            KeyedCandidate(key=candidate_key(index), candidate=candidate)
            for index, candidate in enumerate(decomposition.candidates)
        ),
        findings=tuple(decomposition.findings),
        no_candidate_reason=decomposition.no_candidate_reason,
    )


def processing_result_name(raw_requirement_id: str) -> str:
    """`<RAW Requirement ID> — Processing Result`."""
    return f"{raw_requirement_id} — {PROCESSING_RESULT_SUFFIX}"


def render_processing_result(result: ProcessingResult) -> str:
    """Render the artifact: a short human header plus the machine payload."""
    payload = {
        VERSION_KEY: result.version,
        RAW_ID_KEY: result.raw_requirement_id,
        CANDIDATES_KEY: [
            {
                CANDIDATE_KEY_FIELD: keyed.key,
                "category": keyed.candidate.category.value,
                "title": keyed.candidate.title,
                **{key: getattr(keyed.candidate, key) for key in SECTION_KEYS},
            }
            for keyed in result.candidates
        ],
        FINDINGS_KEY: [
            {
                "kind": finding.kind.value,
                "requirement_id": finding.requirement_id,
                "detail": finding.detail,
            }
            for finding in result.findings
        ],
        NO_CANDIDATE_REASON_KEY: result.no_candidate_reason,
    }
    body = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False)
    return (
        f"# {processing_result_name(result.raw_requirement_id)}\n"
        "\n"
        "Process artifact written by the RAW Requirement Processor. It records "
        "the validated decomposition so a retry can resume without asking the "
        "model again. It is not a Requirement.\n"
        "\n"
        f"```json\n{body}\n```\n"
    )


def parse_processing_result(text: str) -> ProcessingResult:
    """Read a persisted artifact back, or refuse to resume from it."""
    match = JSON_FENCE.search(text or "")
    if match is None:
        raise InvalidProcessingResult(
            "The Processing Result document contains no JSON payload."
        )
    try:
        payload = json.loads(match.group("body"))
    except ValueError as error:
        raise InvalidProcessingResult(
            f"The Processing Result payload is not valid JSON: {error}"
        ) from error
    if not isinstance(payload, dict):
        raise InvalidProcessingResult(
            "The Processing Result payload must be an object."
        )

    version = payload.get(VERSION_KEY)
    if version != PROCESSING_RESULT_VERSION:
        raise InvalidProcessingResult(
            f"Processing Result version {version!r} is not supported; this "
            f"processor reads {PROCESSING_RESULT_VERSION!r}."
        )
    raw_id = payload.get(RAW_ID_KEY)
    if not isinstance(raw_id, str) or not raw_id.strip():
        raise InvalidProcessingResult("The Processing Result names no RAW Requirement.")

    entries = payload.get(CANDIDATES_KEY)
    if not isinstance(entries, list):
        raise InvalidProcessingResult("'candidates' must be a list.")
    candidates = tuple(_read_keyed(entry, index) for index, entry in enumerate(entries))
    _check_keys(candidates)

    findings = tuple(
        _read_finding(entry) for entry in (payload.get(FINDINGS_KEY) or [])
    )
    reason = payload.get(NO_CANDIDATE_REASON_KEY)
    if not candidates and not (reason or "").strip():
        raise InvalidProcessingResult(
            "A Processing Result with no candidates must record why none was warranted."
        )
    return ProcessingResult(
        raw_requirement_id=raw_id,
        candidates=candidates,
        findings=findings,
        no_candidate_reason=reason or None,
        version=version,
    )


def _read_keyed(entry: object, index: int) -> KeyedCandidate:
    if not isinstance(entry, dict):
        raise InvalidProcessingResult(f"Candidate {index} must be an object.")
    key = entry.get(CANDIDATE_KEY_FIELD)
    if not isinstance(key, str) or not key.strip():
        raise InvalidProcessingResult(f"Candidate {index} has no candidate_key.")
    try:
        candidate = Candidate(
            category=Category(entry["category"]),
            title=entry["title"],
            **{field: entry[field] for field in SECTION_KEYS},
        )
    except (KeyError, ValueError, InvalidModelOutput) as error:
        raise InvalidProcessingResult(
            f"Candidate {key} is not a complete persisted candidate: {error}"
        ) from error
    return KeyedCandidate(key=key, candidate=candidate)


def _check_keys(candidates: tuple[KeyedCandidate, ...]) -> None:
    keys = [keyed.key for keyed in candidates]
    if len(set(keys)) != len(keys):
        raise InvalidProcessingResult(
            "The Processing Result reuses a candidate key, so candidate identity "
            "is ambiguous."
        )


def _read_finding(entry: object) -> Finding:
    if not isinstance(entry, dict):
        raise InvalidProcessingResult("Each finding must be an object.")
    try:
        return Finding(
            kind=FindingKind(entry["kind"]),
            requirement_id=entry["requirement_id"],
            detail=entry["detail"],
        )
    except (KeyError, ValueError) as error:
        raise InvalidProcessingResult(f"Malformed finding: {error}") from error
