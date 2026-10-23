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
  own earlier verdict. During a rework (Requirement-Rework-Brief-v0.1) the
  Process Result's own rework claims are sent: each response with the Brief
  item it answers, as Process recorded it. That is the only trace of earlier
  feedback, and it carries no verdict, severity, WHAT status or assessment.

The model is asked for structured data only, never for reasoning, never for
Fibery mechanics, and never for a verdict: deriving that is the code's job.

The resolutions the earlier analysis adopted itself
(Requirement-Autonomous-Resolution-v0.1) are sent as claims too, each with
its bound citations, and for a delegated default the clauses of the policy it
bound with the human-only domains no clause can cover. The reviewer answers
ten checks per resolution; code holds its outcome to them. The operator's
attestations of this Requirement's text (Requirement-Human-Attestation-v0.1)
are listed as the only evidence that any of its text is a human decision.
"""

from __future__ import annotations

from sdlc.autonomy_policy import AutonomyPolicy, render_policy_section
from sdlc.comparison_context import (
    ComparisonContext,
    render_comparison_section,
    render_target_metadata,
)
from sdlc.fibery_workspace import RequirementRecord, RequirementRelations
from sdlc.human_attestation import HumanAttestation, render_attestation_section
from sdlc.process_result import ProcessResult
from sdlc.standard_analysis import FindingKind
from sdlc.standard_review import (
    RESOLUTION_CHECKS,
    CheckOutcome,
    RejectionBasis,
    ReviewSeverity,
    VerificationOutcome,
)

REWORK_HEADING = "Rework responses claimed by the earlier analysis"

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
      "severity": "CONFIRMED only: INFO" | "WARNING" | "BLOCKING",
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
  "question_verifications": [
    { "question_index": 0,
      "outcome": "CONFIRMED" | "REJECTED" | "UNRESOLVED",
      "material": true | false,
      "basis": "ANSWERED_IN_THIS_REQUIREMENT" | "TECHNICAL_HOW"
               | "ANSWERED_BY_OTHER_REQUIREMENT",
      "requirement_id": "see the question rules below",
      "reason": "concise justification" }
  ],
  "material_unresolved_what": [
    { "detail": "a material product question nobody listed, on one line" }
  ],
  "dependency_verifications": [
    { "requirement_id": "an existing DEPENDS_ON target",
      "outcome": "CONFIRMED" | "REJECTED" | "UNRESOLVED",
      "severity": "REJECTED only: INFO" | "WARNING" | "BLOCKING",
      "reason": "concise justification" }
  ],
  "rework_verifications": [
    { "item": "the Brief item reference of one rework response",
      "outcome": "CONFIRMED" | "REJECTED" | "UNRESOLVED",
      "severity": "REJECTED only: INFO" | "WARNING" | "BLOCKING",
      "reason": "concise justification" }
  ],
  "resolution_verifications": [
    { "resolution_index": 0,
      "outcome": "CONFIRMED" | "REJECTED" | "UNRESOLVED",
      "severity": "REJECTED only: INFO" | "WARNING" | "BLOCKING",
      "checks": {
        "issue_identified": "PASS" | "FAIL" | "UNCERTAIN",
        "source_supports_answer": "...",
        "authority_class_correct": "...",
        "within_policy_clause": "... or NOT_APPLICABLE",
        "consistent_with_raw": "...",
        "consistent_with_related": "...",
        "no_unsupported_obligation": "...",
        "no_new_contradiction": "...",
        "no_material_what_open": "...",
        "testable_at_what_level": "..." },
      "reason": "concise justification" }
  ],
  "assessment": {
    "clarity": "...", "completeness": "...", "atomicity": "...",
    "testability": "...", "internal_consistency": "...",
    "acceptance_criteria": "..."
  }
}

Severity: a "severity" marked "CONFIRMED only" or "REJECTED only" is given
exactly when the outcome is that one; for every other outcome omit the
"severity" key entirely (no null, no empty string, no placeholder). Every
new finding carries its own severity. relation_verifications and
question_verifications carry no severity.

What a Standard Requirement is:

- A Standard Requirement states WHAT must be true. HOW it will be satisfied is
  Technical Solution Architecture; decomposing that solution into executable
  work is Delivery Planning; concrete code, configuration, test and deployment
  work is a Task. Review the Requirement at that level.
- It is one independently meaningful product/system obligation: a capability,
  a required outcome, an observable behavior, a business or system constraint,
  or an invariant.

Requirement relations:

- DEPENDS_ON (this -> other): understanding or evaluating at least one
  normative obligation of this Requirement requires a definition, rule,
  constraint or behavior that the other Requirement owns. The two must be
  interpreted together; the other keeps owning that definition, and this
  Requirement refers to it instead of restating it.
- AFFECTS (this -> other): a change to this Requirement may require
  re-evaluating the other. It never means the other supplies, or depends on,
  this Requirement's meaning, and it is never authority for a definition.
- A shared topic, a similar subject or an AFFECTS edge does not establish
  DEPENDS_ON. Dependencies have direction: the Requirement that needs the
  definition depends on the one that owns it.

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
- INCONSISTENT when the work under review contradicts itself about an open
  product decision: its analysis or one of its findings acknowledges a
  decision about WHAT that is still unmade, while the Requirement's Open
  Questions section records none. Report that contradiction. You do not
  rewrite the document to add the question, and you do not answer it.

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
- An unresolved product question is not a defect merely because it exists,
  and its existence alone is never grounds for BLOCKING.

Rules:

- Verify every listed Process finding exactly once, by its index. Do not skip
  one, do not verify one twice, and do not invent an index.
- Verify every listed proposed relation exactly once, by its kind and
  Requirement ID. Confirming a relation does not create it; a human decides
  later whether it is ever applied.
- Reach your own conclusion. CONFIRMED means you independently agree the
  finding is real. REJECTED means you do not. UNRESOLVED means the available
  context cannot settle it. Rejecting a finding is a normal outcome.
- In finding_verifications, give a severity only when you CONFIRM a Process
  finding, and always when you do. REJECTED and UNRESOLVED assert no defect
  there, so they must carry no severity. This rule is for
  finding_verifications only: in dependency_verifications,
  rework_verifications and resolution_verifications CONFIRMED asserts that no
  defect remains, so there only REJECTED carries a severity.
- Decide independently whether a defect is real, then rate what it puts at
  risk under these same rules. An open product question earns no automatic
  severity, and nothing here forbids a justified BLOCKING when the unmade
  product decision genuinely warrants it.
- A question you are the first to notice is a new finding and stays here as
  evidence for a human: it does not enter the Requirement document, and it is
  not by itself a demand for more work.
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
- Verify every listed product question exactly once, by its index:
  * CONFIRMED: it is a genuine product question about WHAT that this
    Requirement's normative content leaves unanswered. Give "material": true
    exactly when two plausible answers would require a different externally
    observable outcome for at least one input or situation in this
    Requirement's scope, and false when every plausible answer leads to the
    same observable outcome. Carry no basis and no requirement_id.
  * REJECTED: it is not an open product question here. Give a "basis":
    ANSWERED_IN_THIS_REQUIREMENT when this Requirement's own normative content
    answers it; TECHNICAL_HOW when its plausible answers differ only in
    mechanism, technology, structure or how the outcome is produced;
    ANSWERED_BY_OTHER_REQUIREMENT when only another Requirement's text answers
    it, naming that Requirement in requirement_id. A question answered only by
    another Requirement still counts as open for this one. Carry no material.
  * UNRESOLVED: the available context cannot settle it. Carry no material,
    basis or requirement_id.
- Report in material_unresolved_what every material product question about
  WHAT for this Requirement that the listed questions do not already cover,
  including one you see in the document, in its Open Questions section or in
  the earlier analysis. Never answer such a question and never list a HOW
  question there. An empty list asserts that you found none.
- Interpretation set: review this Requirement together with every
  Requirement in its interpretation set (listed in the context, each with its
  full text among the other Standard Requirements). A definition the
  Requirement leaves to a listed dependency is not missing here. Check each
  dependency independently: is it semantically necessary, in the right
  direction, owned by that target, and consistent with this Requirement?
- Verify every existing DEPENDS_ON edge exactly once in
  dependency_verifications, by its target. CONFIRMED: the dependency is
  necessary and correct; no severity. REJECTED: it is a false or wrongly
  directed dependency, which is a defect: always give a severity.
  UNRESOLVED: the context cannot settle it; no severity. Never confirm a proposed DEPENDS_ON
  that the context says cannot be confirmed.
- Report, with the existing finding kinds: a missing required dependency
  (this Requirement needs a definition another Requirement owns but neither
  depends on it nor states it) as INCOMPLETE naming the owner in the detail; a
  duplicated normative definition that should have one owner as
  POSSIBLE_DUPLICATE; contradictory definitions or ambiguous ownership of a
  shared rule as POSSIBLE_CONFLICT; an AFFECTS edge used as if it supplied a
  definition as INCONSISTENT. Do not choose between contradicting
  Requirements, and do not repair anything.
- A product question may be REJECTED as ANSWERED_BY_OTHER_REQUIREMENT only
  when that Requirement genuinely answers it. It counts as answered only if
  that Requirement is a confirmed DEPENDS_ON dependency of this one; a
  question answered by any other Requirement stays open.
- Rework responses (only when the context lists them): the earlier analysis
  received feedback on an earlier version and answered each item. Its answers
  are claims. Verify every listed response exactly once, by its item
  reference, against the current document, the RAW source and the peers:
  * CONFIRMED: the claim holds. For RESOLVED, the defect is gone in the
    current document, the correction is faithful to the source, consistent
    with the rest of the Requirement and with related Requirements, and
    introduces no new defect. For REBUTTED, the evidence shows the item was
    not a real defect. For ESCALATED, it genuinely cannot be settled from the
    evidence and stays recorded as an open question. No defect remains, so
    no severity.
  * REJECTED: the claim does not hold, so a defect remains: the original
    problem still exists, the correction is unfaithful or contradictory, the
    rebuttal is wrong, or the escalation was avoidable. Always give the
    severity of what remains.
  * UNRESOLVED: the available context cannot settle it. No severity.
  A material WHAT item is cleared only by your CONFIRMED. Report any new
  defect a correction introduced as a new finding as well. Do your own full
  review of the current Requirement regardless: the responses are not the
  scope of your review.
- Resolutions (only when the context lists them): the earlier analysis
  answered these product questions itself and adopted the answers into the
  Requirement. Each is a claim about authority and evidence, not a
  conclusion: a quote that exists in its source proves only that the text
  exists. Verify every listed resolution exactly once, by its index, against
  the cited sources, the RAW source, the current document, the related
  Requirements and, for DELEGATED_DEFAULT, the listed policy clause. Answer
  each check PASS, FAIL or UNCERTAIN:
  * issue_identified: the issue it resolved is a real product question here,
    stated correctly.
  * source_supports_answer: the cited text actually supports this answer,
    not merely mentions its topic.
  * authority_class_correct: the class is right. SOURCE_GROUNDED needs the
    RAW or this Requirement's own input to establish the answer;
    DEPENDENCY_GROUNDED needs a necessary DEPENDS_ON dependency that owns
    the definition (an AFFECTS peer, a merely similar peer, or one that is
    not approved authority never qualifies); DELEGATED_DEFAULT needs no
    source to settle it and an approved clause to permit it. Do not accept
    the class because it is stated.
  * within_policy_clause: DELEGATED_DEFAULT only; NOT_APPLICABLE for the
    other two classes. The answer is exactly the clause's permitted decision,
    its conditions hold, it stays within the boundaries, no exclusion
    applies, and the evidence the clause requires was cited. A broadened or
    paraphrased clause FAILS. A decision touching a human-only domain FAILS
    whatever the clause says.
  * consistent_with_raw and consistent_with_related: it contradicts neither
    the RAW source nor a related Requirement.
  * no_unsupported_obligation: it adds no obligation the source or clause
    does not establish.
  * no_new_contradiction: the change creates no contradiction in this
    Requirement.
  * no_material_what_open: no material WHAT question about this issue is
    left open by the adopted answer.
  * testable_at_what_level: with the answer, the affected obligation can be
    judged objectively at the WHAT level.
  This Requirement's current content may hold text an earlier analysis
  wrote, including answers an earlier review did not confirm: such text is
  not authority, and a REQUIREMENT citation of it does not pass
  source_supports_answer or authority_class_correct. The one exception is a
  text listed under OPERATOR-ATTESTED CLARIFICATIONS: code verified that the
  operator's configuration attests that exact text as a human decision for
  this Requirement, and code refuses any REQUIREMENT citation answering a
  material item carried over from an earlier review that is not quoted from
  one. A citation of an attested text settles who decided: it passes
  authority_class_correct, and source_supports_answer when the text actually
  states the answer, and an obligation it states is not unsupported. It does
  not make the decision correct: still FAIL consistent_with_raw,
  consistent_with_related or no_new_contradiction when it contradicts the RAW
  source, a related Requirement or this Requirement.
  CONFIRMED requires every check to PASS (within_policy_clause may be
  NOT_APPLICABLE as above), with no severity. Any FAIL is REJECTED, with the severity of the
  unsupported or unauthorized decision. Otherwise any UNCERTAIN is
  UNRESOLVED, with no severity. A resolution you do not confirm keeps the
  Requirement blocked on WHAT; never choose a different answer yourself.
- Do not state an overall verdict, WHAT status, score or recommendation. There
  is no field for one: code derives them from what you report.
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
    dependencies: tuple[str, ...] = (),
    policy: AutonomyPolicy | None = None,
    attestations: tuple[HumanAttestation, ...] = (),
) -> tuple[str, str]:
    """Return the instruction prompt and the context sent on stdin.

    `dependencies` describes the interpretation set, one line per member.
    `policy` is the autonomy policy a delegated default bound, already proved
    current; it is shown only when a resolution relies on it.
    `attestations` are the operator attestations of this exact Requirement in
    the stage's configuration snapshot (Requirement-Human-Attestation-v0.1).
    """
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
            render_attestation_section(attestations),
            "",
            _findings_section(process_result),
            "",
            _relations_section(process_result),
            "",
            _analysis_section(process_result),
            "",
            _questions_section(process_result),
            "",
            *(
                [_resolutions_section(process_result), ""]
                if process_result.resolutions
                else []
            ),
            *(
                [render_policy_section(policy), ""]
                if process_result.relies_on_policy
                else []
            ),
            *(
                [_rework_section(process_result), ""]
                if process_result.rework_brief is not None
                else []
            ),
            _existing_relations_section(relations),
            "",
            _dependencies_section(dependencies),
            "",
            render_comparison_section(comparison),
            "",
            f"# Allowed finding kinds\n{', '.join(k.value for k in FindingKind)}",
            f"# Allowed severities\n{', '.join(s.value for s in ReviewSeverity)}",
            f"# Allowed outcomes\n{', '.join(o.value for o in VerificationOutcome)}",
            f"# Allowed rejection bases\n{', '.join(b.value for b in RejectionBasis)}",
            *(_check_vocabulary() if process_result.resolutions else []),
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


def _questions_section(result: ProcessResult) -> str:
    """The Process product questions, indexed, as claims to check."""
    header = (
        "# Product questions claimed by the earlier analysis\n"
        "Verify each by its index. Its materiality is a claim, not a conclusion."
    )
    lines = [
        f"[{index}] material={'true' if question.material else 'false'}"
        + (f", {question.authority.value}" if question.authority else "")
        + f": {question.detail}"
        + (
            f" (alternatives: {' | '.join(question.alternatives)})"
            if question.alternatives
            else ""
        )
        for index, question in enumerate(result.product_questions or ())
    ]
    return "\n".join([header, *lines]) if lines else f"{header}\n(none)"


def _check_vocabulary() -> list[str]:
    """The resolution checks and their outcomes, only when there is one to check."""
    return [
        f"# Resolution checks\n{', '.join(RESOLUTION_CHECKS)}",
        f"# Allowed check outcomes\n{', '.join(c.value for c in CheckOutcome)}",
    ]


def _resolutions_section(result: ProcessResult) -> str:
    """The resolutions the analysis adopted, indexed, with their citations."""
    header = (
        "# Resolutions adopted by the earlier analysis\n"
        "Verify each by its index. Each is a claim of authority and evidence; "
        "its citations were checked only for existence."
    )
    blocks = []
    for index, resolution in enumerate(result.resolutions):
        lines = [
            f"[{index}] {resolution.resolution_class.value}: {resolution.issue}",
            f"  Adopted answer: {resolution.answer}",
            f"  Affected sections: {', '.join(resolution.affected_sections)}",
        ]
        if resolution.policy_clause:
            lines.append(f"  Policy clause: {resolution.policy_clause}")
        lines += [
            f"  Source {source.kind.value}"
            + (f" {source.requirement_id}" if source.requirement_id else "")
            + f': "{source.quote}"'
            for source in resolution.sources
        ]
        lines.append(f"  Justification: {resolution.justification}")
        blocks.append("\n".join(lines))
    return "\n".join([header, *blocks]) if blocks else f"{header}\n(none)"


def _rework_section(result: ProcessResult) -> str:
    """Each Process rework response with the Brief item it answers, as claims."""
    header = (
        f"# {REWORK_HEADING}\n"
        "Verify each by its item reference. Each item is earlier feedback the "
        "analysis answered; the item and the answer are claims, not conclusions."
    )
    blocks = []
    for response in result.rework_responses:
        item = result.rework_brief.item(response.item)
        facts = [item.category.value]
        if item.blocks_what:
            facts.append("material WHAT question")
        if item.kind:
            facts.append(item.kind)
        if item.requirement_id:
            facts.append(f"about {item.requirement_id}")
        answer = f"  Answer: {response.outcome.value}: {response.explanation}"
        if response.product_question_index is not None:
            answer += f" (kept as product question [{response.product_question_index}])"
        if response.resolution_index is not None:
            answer += f" (relies on resolution [{response.resolution_index}])"
        answer += "".join(
            f"\n  Evidence {source.kind.value}"
            + (f" {source.requirement_id}" if source.requirement_id else "")
            + f': "{source.quote}"'
            for source in response.evidence
        )
        blocks.append(f"[{item.ref}] ({', '.join(facts)}) {item.detail}\n{answer}")
    return "\n".join([header, *blocks]) if blocks else f"{header}\n(none)"


def _analysis_section(result: ProcessResult) -> str:
    header = "# Assessment claimed by the earlier analysis"
    lines = [f"- {key}: {value}" for key, value in sorted(result.analysis.items())]
    return "\n".join([header, *lines]) if lines else f"{header}\n(none)"


def _dependencies_section(lines: tuple[str, ...]) -> str:
    header = (
        "# Interpretation set (normative dependencies)\n"
        "Interpret this Requirement together with these; their full text is "
        "among the other Standard Requirements below."
    )
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
