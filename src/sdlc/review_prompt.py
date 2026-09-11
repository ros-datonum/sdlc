"""The bounded prompt for independent Standard Requirement review.

Context is the Requirement, its current Root Document, the originating RAW
source as read-only evidence, the persisted claims of the latest Process
Result, the relations it already has, and the Project's other Standard
Requirements as comparison material (entity metadata plus each one's complete
current Root Document). No Milestones, Epics, Stories, Tasks or Project
Phases, and no earlier iteration of anything.

The instructions carry the Requirement-level review rules
(Standard-Requirement-Abstraction-v0.2; Standard-Requirement-Review-Spec-v0.1
section 3.1). Judging WHAT against HOW, source fidelity and fragmentation is
the reviewer's semantic work; deterministic code validates only the closed
output contract and derives the verdict.

Two exclusions carry the independence of this stage:

- the Process model's raw response is never available here. What the reviewer
  sees is the *validated, persisted* Process Result, presented as claims to
  check rather than as conclusions to agree with;
- previous Review Results are never sent, so a reviewer cannot anchor on its
  own earlier verdict.

The model is asked for structured data only, never for reasoning, never for
Fibery mechanics, and never for a verdict: deriving that is the code's job.
"""

from __future__ import annotations

from sdlc.comparison_context import (
    ComparisonContext,
    render_comparison_section,
    render_target_metadata,
)
from sdlc.fibery_workspace import RequirementRecord, RequirementRelations
from sdlc.process_result import ProcessResult
from sdlc.standard_analysis import FindingKind
from sdlc.standard_review import ReviewSeverity, VerificationOutcome

INSTRUCTIONS = """\
You are independently reviewing one Standard Requirement in an SDLC system.

Another agent normalized this Requirement and recorded findings and proposed
relations. You are not that agent. Your job is to check its work against the
current requirement document and to report anything it missed. You do not
improve, rewrite or repair the requirement: a problem is a finding.

Return ONLY a single JSON object. No prose, no explanation of your reasoning, no
markdown outside the JSON.

Shape:

{
  "finding_verifications": [
    { "process_finding_index": 0,
      "outcome": "CONFIRMED" | "REJECTED" | "UNRESOLVED",
      "severity": "INFO" | "WARNING" | "BLOCKING",
      "reason": "concise justification" }
  ],
  "relation_verifications": [
    { "kind": "DEPENDS_ON" | "AFFECTS",
      "requirement_id": "the proposed Requirement ID",
      "outcome": "CONFIRMED" | "REJECTED" | "UNRESOLVED",
      "reason": "concise justification" }
  ],
  "new_findings": [
    { "kind": "<finding kind>",
      "severity": "INFO" | "WARNING" | "BLOCKING",
      "detail": "what you observed",
      "requirement_id": "see the new-finding rule below" }
  ],
  "assessment": {
    "clarity": "...", "completeness": "...", "atomicity": "...",
    "testability": "...", "internal_consistency": "...",
    "acceptance_criteria": "..."
  }
}

What a Standard Requirement is:

- A Standard Requirement states WHAT must be true. HOW it will be satisfied is
  Technical Solution Architecture; decomposing that solution into executable
  work is Delivery Planning; concrete code, configuration, test and deployment
  work is a Task. Review the Requirement at that level.
- It is one independently meaningful product/system obligation: a capability,
  a required outcome, an observable behavior, a business or system constraint,
  or an invariant.

Evidence:

- The originating RAW requirement source is read-only evidence of what the
  source actually established. Compare the Requirement's normative content
  against it: whether each statement is source-established, whether a
  technical mechanism is mandated or merely suggested, whether the earlier
  analysis invented product semantics, whether an open decision is
  product-level or architecture-only, and whether one source obligation was
  fragmented.
- When no RAW source is supplied, reach no source-fidelity conclusion from its
  absence: do not report source invention or fragmentation because evidence is
  missing.
- The earlier analysis is a set of claims, not a conclusion. Check each claim
  independently, do not simply agree with it, and look for what it missed.

Defects to flag, using the existing finding kinds:

- IMPLEMENTATION_LEAKAGE: downstream HOW presented as Requirement truth:
  architecture; algorithm choice; classes, functions, modules, libraries or
  frameworks; internal data structures or fields without independent product
  meaning; worker or process topology; queue, poll, webhook or scheduler
  choices; persistence, storage or serialization mechanics; implementation
  sequences; exact test mechanics; deployment mechanics. This includes Task or
  test mechanics disguised as Acceptance / Verification: test commands, mocks,
  fixtures, internal function calls, an exact technical verification path or
  implementation-specific assertions.
- A technical mechanism the source explicitly mandates is legitimate
  Requirement content, not leakage: "Provider execution must use argv and must
  never use a shell" may stay when the source says so. "Current implementation
  uses argv" or "Suggested approach: use argv" does not make argv Requirement
  truth.
- INCONSISTENT for source invention: normative content (an obligation,
  constraint, rationale, acceptance condition or other normative fact) that
  the originating source does not establish or that contradicts it. Say in the
  detail that the statement is unsupported by, or inconsistent with, the
  originating source. A paraphrase that keeps the source's meaning is not
  invention.
- INCOMPLETE for unjustified fragmentation: the Requirement is only a fragment
  of one source-established obligation, so it does not represent that
  obligation at the Requirement level. Name the fragmentation and the larger
  source obligation in the detail; a peer holding the rest may be cited there,
  never in `requirement_id`. When the fragment exists because implementation
  facets became separate Requirements, IMPLEMENTATION_LEAKAGE may also apply.
- NON_ATOMIC only for the opposite shape: more than one genuinely independent
  product/system obligation in one Requirement. Never use it for a fragment,
  and never demand one Requirement per sentence, field, parameter, error case,
  status or technical detail.
- Genuine source gaps and contradictions: when the source establishes
  product/system content the Requirement lost, blurred or contradicts, report
  INCOMPLETE, MISSING_CONSTRAINT, MISSING_EDGE_CASE, AMBIGUOUS or INCONSISTENT
  as appropriate. A gap must be a Requirement-level gap, not an undecided HOW.

Not defects:

- Missing downstream design is not a defect. A valid Requirement is never
  INCOMPLETE, MISSING_CONSTRAINT, MISSING_EDGE_CASE or NOT_TESTABLE merely
  because it lacks architecture, an algorithm, module, class or function
  design, data structures, a persistence mechanism, worker topology,
  deployment design or exact tests. A valid high-level Requirement may deserve
  no finding at all.
- Acceptance is judged at the observable-outcome level. Do not require test
  design for a Requirement to pass.
- A source-established product decision that is still unresolved may
  legitimately stay open; do not report it merely because it is unresolved.
  An unanswered architecture question is not missing Requirement content:
  leave HOW to Technical Solution Architecture.

Rules:

- Verify every listed Process finding exactly once, by its index. Do not skip
  one, do not verify one twice, and do not invent an index.
- Verify every listed proposed relation exactly once, by its kind and
  Requirement ID. Confirming a relation does not create it; a human decides
  later whether it is ever applied.
- Reach your own conclusion. CONFIRMED means you independently agree the
  finding is real. REJECTED means you do not. UNRESOLVED means the available
  context cannot settle it. Rejecting a finding is a normal outcome.
- Give a severity only when you CONFIRM a finding, and always when you do.
  REJECTED and UNRESOLVED assert no defect, so they must carry no severity.
- Report anything the earlier analysis missed as a new finding, with its own
  severity. Two classes of new finding exist, and `requirement_id` separates
  them:
  * A finding ABOUT THIS Requirement (INCOMPLETE, AMBIGUOUS, NON_ATOMIC,
    INCONSISTENT, NOT_TESTABLE, MISSING_CONSTRAINT, MISSING_EDGE_CASE,
    IMPLEMENTATION_LEAKAGE) carries no `requirement_id`: omit the key or set it
    to null. When another
    Requirement is only evidence or context for the point, name it inside
    `detail`, never in `requirement_id`. A finding of one of these kinds that
    carries a `requirement_id` is rejected as a whole, together with the rest
    of this output.
  * A finding ABOUT ANOTHER Requirement (POSSIBLE_DUPLICATE, POSSIBLE_CONFLICT,
    POSSIBLE_CHANGE, POSSIBLE_SUPERSESSION) must name that Requirement in
    `requirement_id`, by its Requirement ID.
  Examples:
    { "kind": "MISSING_CONSTRAINT", "severity": "WARNING", "requirement_id": null,
      "detail": "This Requirement does not govern the child process
                 environment. Peer SDLC-FR-0002 does not establish it either." }
    { "kind": "POSSIBLE_CONFLICT", "severity": "WARNING",
      "requirement_id": "SDLC-FR-0002",
      "detail": "SDLC-FR-0002 enumerates a status set that omits INVALID_REQUEST." }
- Do not state an overall verdict, score or recommendation. There is no field
  for one: it is derived from the severities you assign.
- Do not propose changes, rewrites, updates, retirement or supersession of any
  Requirement, do not describe an action to take, and do not recommend an
  implementation, a design or replacement wording. You are reporting, not
  instructing.
- Every other Standard Requirement named by a claim is supplied with its full
  Root Document; verify comparison claims against that text, not the title.
  A peer that is not Applied is a candidate under review, not approved
  authority, and nothing here approves it.
- Emit no field that is not listed above. Unknown fields are rejected.
"""


def build_review_prompt(
    requirement: RequirementRecord,
    project_name: str,
    root_content: str,
    child_content: str,
    raw_ancestry: str,
    process_result: ProcessResult,
    relations: RequirementRelations,
    comparison: ComparisonContext,
) -> tuple[str, str]:
    """Return the instruction prompt and the context sent on stdin."""
    context = "\n".join(
        [
            "# Project",
            project_name,
            "",
            "# Requirement under review",
            f"{requirement.requirement_id} — {requirement.title}",
            *render_target_metadata(requirement),
            "",
            "# Current Requirement document",
            root_content or "(empty)",
            "",
            _section("Normative child documents", child_content),
            "",
            _section("Originating RAW requirement source", raw_ancestry),
            "",
            _findings_section(process_result),
            "",
            _relations_section(process_result),
            "",
            _analysis_section(process_result),
            "",
            _existing_relations_section(relations),
            "",
            render_comparison_section(comparison),
            "",
            f"# Allowed finding kinds\n{', '.join(k.value for k in FindingKind)}",
            f"# Allowed severities\n{', '.join(s.value for s in ReviewSeverity)}",
            f"# Allowed outcomes\n{', '.join(o.value for o in VerificationOutcome)}",
        ]
    )
    return INSTRUCTIONS, context


def _section(heading: str, body: str) -> str:
    return f"# {heading}\n{body}" if body.strip() else f"# {heading}\n(none)"


def _findings_section(result: ProcessResult) -> str:
    """The Process findings, indexed, as claims to check."""
    header = (
        "# Findings claimed by the earlier analysis\n"
        "Verify each by its index. These are claims, not conclusions."
    )
    lines = [
        f"[{index}] {finding.kind.value}"
        + (f" about {finding.requirement_id}" if finding.requirement_id else "")
        + f": {finding.detail}"
        for index, finding in enumerate(result.findings)
    ]
    return "\n".join([header, *lines]) if lines else f"{header}\n(none)"


def _relations_section(result: ProcessResult) -> str:
    header = (
        "# Relations proposed by the earlier analysis\n"
        "Verify each. Confirming one does not create it."
    )
    lines = [
        f"- {relation.kind.value} {relation.requirement_id}: {relation.rationale}"
        for relation in result.proposed_relations
    ]
    return "\n".join([header, *lines]) if lines else f"{header}\n(none)"


def _analysis_section(result: ProcessResult) -> str:
    header = "# Assessment claimed by the earlier analysis"
    lines = [f"- {key}: {value}" for key, value in sorted(result.analysis.items())]
    return "\n".join([header, *lines]) if lines else f"{header}\n(none)"


def _existing_relations_section(relations: RequirementRelations) -> str:
    """What this Requirement is already related to.

    Sent so the reviewer can tell a genuinely new proposal from one that merely
    restates an edge that already exists.
    """
    header = "# Relations this Requirement already has"
    lines = [f"- DEPENDS_ON {value}" for value in relations.depends_on]
    lines += [f"- AFFECTS {value}" for value in relations.affects]
    return "\n".join([header, *lines]) if lines else f"{header}\n(none)"
