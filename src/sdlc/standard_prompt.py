"""The bounded prompt for Standard Requirement normalization and analysis.

Context is the Requirement, its documents, the RAW it came from, and the
Project's other Standard Requirements as comparison material (entity metadata
plus each one's complete current Root Document). No Milestones, Epics,
Stories, Tasks or Project Phases.

The model is asked for structured data only, never for reasoning, never for
Fibery mechanics, and never for permission to change anything.

The instructions carry the Requirement-level normalization and analysis rules
(Standard-Requirement-Abstraction-v0.2; Standard-Requirement-Process-Spec-v0.1
section 3.1). Judging WHAT against HOW is the model's semantic work;
deterministic code validates only the closed output contract and the document
structure.
"""

from __future__ import annotations

from sdlc.comparison_context import (
    ComparisonContext,
    render_comparison_section,
    render_target_metadata,
)
from sdlc.fibery_workspace import RequirementRecord
from sdlc.standard_analysis import FindingKind, RelationKind

INSTRUCTIONS = """\
You are normalizing and analyzing one Standard Requirement in an SDLC system.

Return ONLY a single JSON object. No prose, no explanation of your reasoning, no
markdown outside the JSON.

Shape:

{
  "normalized_requirement": {
    "title": "short descriptive title on a single line",
    "requirement": "the normative WHAT: the obligation that must be true",
    "detailed_behavior": "observable behavior needed to interpret it, or omit",
    "rationale": "why it exists, from the source only, or omit",
    "acceptance_verification": "observable evidence of satisfaction, or omit",
    "constraints_edge_cases": "boundaries or source-mandated constraints, or omit",
    "non_goals": "explicitly excluded behavior or scope, or omit",
    "open_questions": "unresolved product questions from the source, or omit"
  },
  "analysis": {
    "completeness": "...", "clarity": "...", "atomicity": "...",
    "testability": "...", "internal_consistency": "..."
  },
  "findings": [
    { "kind": "<finding kind>", "detail": "what you observed",
      "requirement_id": "see the finding rule below" }
  ],
  "proposed_relations": [
    { "kind": "DEPENDS_ON" | "AFFECTS",
      "requirement_id": "an existing Requirement ID",
      "rationale": "why" }
  ]
}

What a Standard Requirement is:

- A Standard Requirement states WHAT must be true. HOW it will be satisfied is
  Technical Solution Architecture; decomposing that solution into executable
  work is Delivery Planning; concrete code, configuration, test and deployment
  work is a Task.
- It is one independently meaningful product/system obligation: a capability,
  a required outcome, an observable behavior, a business or system constraint,
  or an invariant. Implementation independence is the default: it should stay
  true if the solution were replaced by a different valid technical solution.

What normalization is:

- Normalization expresses the same source-established Requirement-level
  obligation more clearly. It is not making the Requirement look complete at
  any cost.
- Use the current Requirement document and its originating RAW source as
  evidence. Do not invent obligations, rationale, constraints, acceptance
  evidence or answers to open questions.
- Keep a valid high-level Requirement high-level. Improve wording only where
  the source meaning is unchanged, and never add technical design, mechanisms
  or detail to make it more concrete.
- You are not required to turn every input into a valid Requirement. When the
  source does not establish enough Requirement-level truth to repair it without
  invention, keep its source-established meaning and report the defect as a
  finding.

Implementation leakage:

- Downstream HOW is: architecture; algorithm choice; classes, functions,
  modules, packages, libraries or frameworks; worker or process topology;
  queues, pollers, webhooks or schedulers; implementation sequence or steps;
  persistence, storage or serialization mechanics; exact test mechanics;
  deployment mechanics; implementation-specific edge cases; and internal fields
  or flags with no independent product/system meaning.
- A valid obligation that also carries HOW the source does not mandate: keep
  the WHAT, remove or omit the HOW from the normalized sections where that does
  not change source-established intent, and report IMPLEMENTATION_LEAKAGE
  describing the leaked material. Do not move the HOW into another section,
  and do not turn an implementation choice into a new product constraint.
- A Requirement that is itself essentially architecture, implementation, Task,
  test or deployment work, where the originating RAW source establishes no
  independently meaningful Requirement-level obligation behind it: report
  IMPLEMENTATION_LEAKAGE saying so. Do not invent a higher-level Requirement to
  rescue it, and do not derive a product outcome merely because one could
  justify the implementation. Keep the normalized sections faithful to what it
  states: it stays defective and goes to Review carrying the finding.
- Say in the detail which case applies and what material leaked. Do not rate
  severity; Review does that.

Source-mandated mechanisms:

- A technical mechanism is legitimate Requirement content when the source
  explicitly mandates that exact mechanism, and it may remain a constraint.
  "Provider execution must use argv and must never use a shell" is such a
  mandate. Do not report it as leakage merely because it is technical.
- A mechanism is not mandated merely because it appears in the current
  implementation, an example, background discussion, an existing architecture
  or a suggested solution: "current implementation uses argv" or "suggested
  solution: use argv" does not make argv a Requirement.
- When it is unclear whether a mechanism is mandated and the answer changes
  WHAT must be true, keep it as an open question; do not silently choose.

Sections:

- requirement: the normative WHAT.
- detailed_behavior: only externally or system-observable behavior needed to
  interpret the WHAT. Never algorithms, classes, functions or modules, worker
  or process topology, queues, pollers, webhooks or schedulers, implementation
  sequence, persistence or storage mechanics, test mechanics or deployment
  mechanics.
- rationale: why the obligation exists, only when the source says so.
- acceptance_verification: observable evidence that the obligation is
  satisfied. Never unit or integration test instructions, mocks, fixtures, a
  test framework, internal function calls or an implementation-specific
  verification path. Keep observable acceptance the source establishes. If the
  only material is test mechanics, omit it rather than converting it into
  invented acceptance criteria; if observable satisfaction cannot be derived
  from the source-established WHAT, leave the section empty.
- constraints_edge_cases: product/system boundaries that hold under any valid
  implementation, plus explicitly source-mandated technical constraints.
- non_goals: explicit scope exclusions, not implementation alternatives that
  were not chosen.
- open_questions: unresolved product decisions that affect WHAT must be true.
  Preserve each as a question and never answer it. A missing architecture
  decision is not a product gap unless the source makes that decision part of
  WHAT: leave architecture-only questions out.
- Omit a section, or leave it empty, when the source does not establish it.
  Deterministic code fills those in; inventing content is worse than omitting it.
- Code owns the document structure. The title is a single line, and section
  content must not contain a level-1 or level-2 Markdown heading (a # or ##
  line, or text directly underlined with = or -) outside a fenced code block.
  Such output is rejected.

Analysis, at the Requirement level:

- Completeness: a Requirement is not incomplete merely because it lacks
  architecture, an algorithm, component design, data structures, class or
  function names, a persistence strategy, worker topology, deployment design or
  exact tests. Report INCOMPLETE, MISSING_CONSTRAINT or MISSING_EDGE_CASE only
  for a product/system obligation, boundary or case the source establishes and
  the Requirement lacks, never because downstream design is not chosen yet.
- Atomicity: one independently meaningful product/system obligation, not one
  sentence, field, parameter, status, error case, implementation rule or
  component. Report NON_ATOMIC only when the Requirement holds more than one
  genuinely independent obligation, never for technical facets of one
  obligation. Do not split it: you cannot create Requirements.
- Testability: satisfaction can eventually be observed or evaluated at the
  Requirement level. Do not report NOT_TESTABLE merely because no test
  implementation or verification design exists.
- Clarity and internal consistency are analyzed as before.

Findings and relations:

- Two classes of finding exist, and `requirement_id` separates them:
  * A finding ABOUT THIS Requirement (INCOMPLETE, AMBIGUOUS, NON_ATOMIC,
    INCONSISTENT, NOT_TESTABLE, MISSING_CONSTRAINT, MISSING_EDGE_CASE,
    IMPLEMENTATION_LEAKAGE) carries no `requirement_id`: omit the key or set it
    to null. When another Requirement is only evidence or context for the
    point, name it inside `detail`, never in `requirement_id`. A finding of one
    of these kinds that carries a `requirement_id` is rejected as a whole,
    together with the rest of this output.
  * A finding ABOUT ANOTHER Requirement (POSSIBLE_DUPLICATE, POSSIBLE_CONFLICT,
    POSSIBLE_CHANGE, POSSIBLE_SUPERSESSION) must name that Requirement in
    `requirement_id`, by its Requirement ID.
  Examples:
    { "kind": "MISSING_CONSTRAINT", "requirement_id": null,
      "detail": "This Requirement does not govern the child process
                 environment. Peer SDLC-FR-0002 does not establish it either." }
    { "kind": "IMPLEMENTATION_LEAKAGE", "requirement_id": null,
      "detail": "Detailed Behavior prescribed a watchdog thread with SIGKILL
                 escalation; the source requires only that execution stops
                 within the limit, so the mechanism was omitted." }
    { "kind": "POSSIBLE_CONFLICT", "requirement_id": "SDLC-FR-0002",
      "detail": "SDLC-FR-0002 enumerates a status set that omits INVALID_REQUEST." }
  Findings are observations only. You cannot modify, retire or supersede
  anything.
- Relations are proposals for an independent reviewer to confirm. Proposing one
  does not create it.
- The other Standard Requirements are supplied with their full Root Documents
  so comparison findings and relations rest on what they actually state.
  They never authorize changing this Requirement's intent, and one that is
  not Applied is a candidate under review, not approved authority.
- Emit no field that is not listed above. Unknown fields are rejected.
"""


def build_analysis_prompt(
    requirement: RequirementRecord,
    project_name: str,
    root_content: str,
    child_content: str,
    raw_ancestry: str,
    comparison: ComparisonContext,
) -> tuple[str, str]:
    """Return the instruction prompt and the context sent on stdin."""
    context = "\n".join(
        [
            "# Project",
            project_name,
            "",
            "# Requirement under analysis",
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
            render_comparison_section(comparison),
            "",
            f"# Allowed finding kinds\n{', '.join(k.value for k in FindingKind)}",
            f"# Allowed relation kinds\n{', '.join(k.value for k in RelationKind)}",
        ]
    )
    return INSTRUCTIONS, context


def _section(heading: str, body: str) -> str:
    return f"# {heading}\n{body}" if body.strip() else f"# {heading}\n(none)"
