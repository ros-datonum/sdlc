"""The bounded prompt for RAW Requirement decomposition.

Context is deliberately narrow: the RAW Requirement and its document tree, the
Project name, and the Project's other Standard Requirements as comparison
material (entity metadata plus each one's complete current Root Document). No
Milestones, Epics, Stories, Tasks or unrelated project state.

The model is asked for structured data only. It is never asked to explain its
reasoning, never given Fibery identifiers to act on, and never asked to produce
the document itself.

The instructions carry the Requirement-level decomposition rules
(Standard-Requirement-Abstraction-v0.2; RAW-Requirement-Processor-Decision-v0.1
section 2). Deciding which source statements are obligations is the model's
semantic work; deterministic code validates only the output shape and the
document structure.
"""

from __future__ import annotations

from sdlc.comparison_context import ComparisonContext, render_comparison_section
from sdlc.raw_processing import Category, FindingKind

INSTRUCTIONS = """\
You are decomposing one RAW requirement artifact into Standard Requirement
candidates for an SDLC system.

Return ONLY a single JSON object. No prose, no explanation of your reasoning, no
markdown outside the JSON.

Shape:

{
  "candidates": [
    {
      "category": "FUNCTIONAL" | "NON_FUNCTIONAL" | "CONSTRAINT",
      "title": "short descriptive title on a single line",
      "requirement": "the normative WHAT: the obligation that must be true",
      "detailed_behavior": "observable behavior needed to interpret it, or omit",
      "rationale": "why it exists, from the source only, or omit",
      "acceptance_verification": "observable evidence of satisfaction, or omit",
      "constraints_edge_cases": "boundaries or source-mandated constraints, or omit",
      "non_goals": "explicitly excluded behavior or scope, or omit",
      "open_questions": "unresolved product questions from the source, or omit"
    }
  ],
  "findings": [
    {
      "kind": "POSSIBLE_DUPLICATE" | "POSSIBLE_CONFLICT"
            | "POSSIBLE_CHANGE" | "POSSIBLE_SUPERSESSION",
      "requirement_id": "an existing Standard Requirement ID",
      "detail": "what you observed"
    }
  ],
  "no_candidate_reason": "required only when candidates is empty"
}

What a Standard Requirement is:

- A Standard Requirement states WHAT must be true. HOW it will be satisfied is
  Technical Solution Architecture; decomposing that solution into executable
  work is Delivery Planning; concrete code, configuration, test and deployment
  work is a Task. Every candidate is a Requirement, never one of the others.
- A candidate is one independently meaningful product/system obligation: a
  capability, a required outcome, an observable behavior, a business or system
  constraint, or an invariant.
- Implementation independence is the default: a candidate should stay true if
  the solution were replaced by a different valid technical solution.
- Categories: FUNCTIONAL is a required capability, behavior or outcome.
  NON_FUNCTIONAL is a required quality or operating property of the delivered
  system, such as performance, reliability, security, privacy, scalability,
  usability or recoverability. CONSTRAINT is a mandatory boundary on valid
  solutions or operation; it is not a license to promote implementation
  decisions.

Decomposition:

- One candidate = one independently meaningful product/system obligation. That
  is not one sentence, one source bullet, one field, one parameter, one error
  case or one implementation decision.
- Separate obligations that are genuinely independent: they can be accepted or
  rejected separately, can change separately, describe materially different
  outcomes or constraints, or would naturally have different solution
  ownership. Do not merge independent obligations because they share a
  paragraph, a source section or an implementation.
- When the source describes one capability together with many technical
  details of one proposed implementation, produce one candidate for the
  capability. Those details are technical facets of that one obligation, not
  candidates of their own.
- There is no target number of candidates. Zero, one or many are all valid;
  the count follows from what the source means.

Anti-implementation-leakage rule:

- Never create a candidate merely because the source mentions: a class,
  function, module, package, library, framework, programming language or source
  file; an internal field or flag with no independent product/system meaning;
  an algorithm or internal execution sequence; a worker or process topology; a
  queue, webhook, polling loop, scheduler or other internal triggering
  mechanism; a persistence, storage or serialization mechanism; test code,
  fixtures, mocks or a test framework; a deployment mechanism; an
  implementation-specific edge case; or any other detail whose meaning exists
  only under one proposed implementation.
- Leave such detail out of the candidates. It stays in the RAW source as context
  for later Architecture; its presence there is not authority to make it a
  Requirement.
- A field or parameter is Requirement content only when it carries an
  independently meaningful obligation, or belongs to an exact external contract
  the source explicitly commits to.

Source-mandated mechanisms:

- A technical mechanism is Requirement content only when the source explicitly
  makes that exact mechanism mandatory. It may then remain a CONSTRAINT
  candidate, or constraint content of the obligation it bounds.
- Example: "caller-controlled input must never be interpreted as shell command
  syntax" states a security outcome. The candidate states that outcome
  (caller-controlled input must not be interpreted as executable command
  syntax); the process invocation design is left to Architecture. By contrast,
  "provider execution must use argv and must never use a shell" explicitly
  mandates the mechanism, so it may remain a CONSTRAINT.
- A mechanism is not mandatory merely because it appears in an example, the
  current implementation, background discussion, an existing architecture or a
  suggested approach. When the mandate is unclear, record that uncertainty in
  open_questions instead of promoting the mechanism.

Placing source material (decide silently; never report these decisions):

- Obligation the source establishes -> a candidate.
- Technical facet of an obligation -> state the obligation, not the facet; no
  separate candidate.
- Implementation suggestion, example, current behavior or background -> source
  context only; no candidate.
- Explicitly mandated mechanism -> a CONSTRAINT, or constraint content.
- Genuinely independent obligation -> its own candidate.

Sections:

- requirement: the normative WHAT.
- detailed_behavior: only externally or system-observable behavior needed to
  interpret the WHAT, such as lifecycle behavior visible in system state, the
  conditions under which the obligation applies, and meaningful success or
  failure outcomes. Never architecture, algorithm choice, module, class or
  function design, worker or process topology, implementation steps, test
  implementation or deployment mechanics. Omit it when no clarification is
  needed.
- rationale: why the obligation exists, only when the source says so.
- acceptance_verification: observable evidence that the obligation is
  satisfied: states, outcomes, properties, boundaries or externally observable
  scenarios. Never unit-test instructions, implementation-specific test cases,
  fixtures, mocks, function calls or a test framework.
- constraints_edge_cases: product/system boundaries that hold under any valid
  implementation, plus explicitly source-mandated technical constraints.
  Implementation-specific edge cases stay downstream.
- non_goals: explicit scope exclusions, not implementation alternatives that
  were not chosen.
- open_questions: unresolved source decisions that affect WHAT must be true.
  Preserve each as a question and never answer it. A question about HOW to
  satisfy an already understood obligation is an architecture question: leave
  it out unless its answer could change product intent.

Source preservation:

- Use only what the source states. Do not invent requirements, rationale,
  constraints, acceptance evidence or answers to open questions.
- Never add architecture or test mechanics to make a candidate look more
  testable.
- Omit a section, or leave it empty, when the source does not establish it.
  Deterministic code fills those in; inventing content is worse than omitting it.
- Code owns the document structure. The title is a single line, and section
  content must not contain a level-1 or level-2 Markdown heading (a # or ##
  line, or text directly underlined with = or -) outside a fenced code block.
  Such output is rejected.

Findings:

- Findings are observations about existing Standard Requirements. They never
  modify them. Report a finding instead of proposing a change.
- The other Standard Requirements are supplied with their full Root Documents
  so you can see duplication, conflict, change or supersession. They never
  replace what this source states, and one that is not Applied is a
  candidate under review, not approved authority.

Output:

- If the source warrants no Standard Requirement, return an empty candidates
  list and explain why in no_candidate_reason.
- Emit no field that is not listed above. Unknown fields are rejected.
"""


def build_prompt(
    raw_requirement_id: str,
    raw_title: str,
    project_name: str,
    raw_body: str,
    comparison: ComparisonContext,
) -> tuple[str, str]:
    """Return the instruction prompt and the context sent on stdin."""
    context = "\n".join(
        [
            "# Project",
            project_name,
            "",
            "# RAW Requirement",
            f"{raw_requirement_id} — {raw_title}",
            "",
            "# RAW Requirement documents",
            raw_body or "(empty)",
            "",
            render_comparison_section(comparison),
            "",
            f"# Allowed categories\n{', '.join(c.value for c in Category)}",
            f"# Allowed finding kinds\n{', '.join(k.value for k in FindingKind)}",
        ]
    )
    return INSTRUCTIONS, context
