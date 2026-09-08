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

from sdlc.normative_tree import (
    LEGACY_NORMATIVE_TREE_VERSION,
    NORMATIVE_TREE_VERSION,
    InvalidTreeManifest,
    TreeManifest,
    document_fingerprint,
)
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

# 0.3 binds the normative tree with manifest v2 (exact canonical-byte document
# fingerprints, audit A8). 0.2 bound manifest v1 under the older fingerprint
# algorithm; 0.1 is the Root-only binding. Both older versions stay readable
# as history under their own semantics and are never written or rewritten.
PROCESS_RESULT_VERSION = "0.3"
TREE_BOUND_LEGACY_PROCESS_RESULT_VERSION = "0.2"
LEGACY_PROCESS_RESULT_VERSION = "0.1"
SUPPORTED_PROCESS_RESULT_VERSIONS = frozenset(
    {
        PROCESS_RESULT_VERSION,
        TREE_BOUND_LEGACY_PROCESS_RESULT_VERSION,
        LEGACY_PROCESS_RESULT_VERSION,
    }
)
# The manifest version each tree-bound Result version must carry; a payload
# that mixes them is a contradiction, never a best-effort read.
MANIFEST_VERSION_BY_RESULT_VERSION = {
    TREE_BOUND_LEGACY_PROCESS_RESULT_VERSION: LEGACY_NORMATIVE_TREE_VERSION,
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

    @property
    def name(self) -> str:
        return process_result_name(self.requirement_id, self.iteration)

    @property
    def is_tree_bound(self) -> bool:
        return self.input_tree is not None and self.output_tree is not None

    @property
    def is_current(self) -> bool:
        """0.3 with manifest v2 on both trees: evidence the current stages use.

        0.1 and 0.2 are history under their own algorithms; they are read,
        never replayed, certified or applied.
        """
        return (
            self.version == PROCESS_RESULT_VERSION
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
) -> ProcessResult:
    """Assemble the artifact, fingerprinting the document it will produce.

    The intended output tree is derived here from the deterministic rendering
    of the normalized document, never from anything the model supplied.
    """
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
    )


def render_process_result(result: ProcessResult) -> str:
    """Render the artifact: a short human header plus the machine payload."""
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
    return ProcessResult(
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
