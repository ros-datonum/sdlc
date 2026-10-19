# Requirement Rework Brief — v0.1 (delta)

**Status:** IMPLEMENTED ON BRANCH `impl/requirements-rework-brief`; NOT LIVE-VERIFIED.
**Authorization:** human instruction "Implement WI-2 — Evidence-Bound Rework Brief for Standard Requirements", for baseline `951672a5aac7002e6cda35cb0f234dfd906ab3b6`. The approval record is that instruction; no signature is claimed.
**Amends, narrowly and only as stated here:**
- Standard-Requirement-Process-Spec-v0.1 §5 (input context), §6 (output shape), §8 (Process Result), §11 (no-change reprocessing, authorized new cycle);
- Standard-Requirement-Review-Spec-v0.1 §5 (input context), §7 (contract), the Review Result shape;
- Requirement-Material-WHAT-Gate-v0.1 §5 (derivation) and §6 (Review Result binding), by addition only.

Those documents are unchanged on disk. Where this delta and they disagree, this delta governs for the listed points only. It preserves the authority of the Material-WHAT Gate: nothing here can produce CLEAR that the gate would not.

## 1. Purpose and boundary

Before this delta a rework was blind: Process never saw the Review that sent the Requirement back. Now, when a Standard Requirement returns `Ready -> Process`, the next Process iteration receives the actionable items of the latest completed Review as a **Rework Brief** and must answer each one; the next independent Review verifies every answer.

Unchanged: the workflow (`Process -> Review -> Ready`, REWORK `Ready -> Process`), the States, the dispatcher routes, the human authority at Ready, relation semantics, and every existing recovery option. No new State, database, agent role, model call, Fibery Document or automatic transition. No automatic rework or approval.

## 2. Non-normative status

The Brief is feedback, never Requirement truth. It is not part of the Root, a normative child, the originating RAW, a peer Requirement or comparison authority, and it is never written to any of them.
- Code builds it; no model writes it.
- Process receives it in its own context section, `# PREVIOUS REVIEW FEEDBACK — NON-NORMATIVE`, after every normative and source section, with instructions that a review can be mistaken and that nothing in it is an obligation unless the Requirement, its RAW or an Applied peer establishes it.
- It is persisted only inside the Process Result that consumed it (§8), which the normative tree reader already excludes by name.

## 3. Selection and lineage

The **source Review** of a new Process iteration is the Review Result with the highest iteration under the Requirement's Root Document. There is no source, and no Brief, when no Review Result exists: an **initial Process** behaves as before.

Before a Brief is built, every Review Result under the Root is validated; any failure refuses the run with `REVIEW_LINEAGE_INVALID` before any model call, and nothing is written:
- it parses as a supported Review Result (0.1–0.5), and its payload names this Requirement and the iteration its Document name carries;
- no two Review Result Documents carry the same iteration;
- it binds a persisted Process Result of this Requirement by iteration **and** output fingerprint;
- successive Review Results bind strictly increasing Process iterations (two Reviews of one iteration, or a later Review of an earlier iteration, are crossed lineage);
- the source Review is coherent with the Process Result it bound: its finding indexes exist, its relation verifications are that Result's proposals, and its WHAT and rework evidence pass `what_clearance` (Material-WHAT Gate §6, §9 here).
- the Brief built from it satisfies the closed shape it is read back with (§8): for example a Review whose persisted reason or assessment text is empty refuses here, before any model call, rather than producing a Process Result that cannot be read.

A Review is never chosen by timestamp, never skipped, and never repaired. The Requirement must be in `Process` (unchanged entry check). Because the source binds a persisted, reviewed Process iteration, an unreviewed partial iteration is never a source; it may lie between the source and the new iteration, and the source's feedback still applies.

Recovery from `REVIEW_LINEAGE_INVALID` is manual; this delta adds none.

## 4. Brief content and identity

**Items.** One per actionable entry of the source Review, in this order, each with a deterministic reference `R<review iteration, 4 digits>.<letter><index in the Review's own list>`:

| Category | Letter | Source | Included |
|---|---|---|---|
| `PROCESS_FINDING` | F | a Process finding with the Review's verification | every verification, any outcome |
| `NEW_FINDING` | N | a finding the Review added | all |
| `RELATION_PROPOSAL` | L | a proposed relation the Review verified | REJECTED or UNRESOLVED only |
| `PRODUCT_QUESTION` | Q | a Process product question with the Review's verification (0.4+) | all |
| `MATERIAL_WHAT` | W | `material_unresolved_what` (0.4+) | all |
| `REWORK_CLAIM` | C | a rework response of the source's own Process the Review did not confirm (0.5) | REJECTED or UNRESOLVED only |

Each item carries: reference, category, the actual finding, question or rationale text, the source reviewer's reason (`feedback`), the Review's verification outcome where one exists, finding or relation kind, severity where the Review graded one, the Requirement ID where the source names one, and `blocks_what`.

A `REWORK_CLAIM` also carries `origin_ref`, the reference of the item it re-raises in the source Process Result's own Brief, and copies that item's structured `kind` and `requirement_id`. For an item that came from a relation proposal they are the relation's kind and exact target, never parsed from text: with the claim's own outcome and feedback, and the source identity's Review and Process iterations, they keep the relation's full identity. `origin_ref` must name an earlier Review than the claim's own. A claim whose origin is a relation item must carry a relation kind and a target; a claim whose origin is itself a claim carries what that claim carried, so a relation keeps its kind and target through every generation. No other category carries `origin_ref`.

`blocks_what` is true for a `MATERIAL_WHAT` item, for a `PRODUCT_QUESTION` item whose verification blocks under Material-WHAT Gate §5, and for a `REWORK_CLAIM` that carried a material WHAT item forward. It is false otherwise.

**Assessment.** The source Review's assessment travels as context. It needs no response, because nothing in it is deterministically actionable; actionable content belongs in findings.

**Source identity.** Requirement ID, Review Result iteration and version, and the bound Process Result's iteration, output fingerprint and version.

**Brief identity.** SHA-256 over the canonical JSON of the source identity, the items and the assessment. It detects change; it is not an authentication or signature, and a consistent hand edit of history is not detectable.

**Run-input identity.** SHA-256 over the canonical JSON of the normative input tree fingerprint and the Brief identity (or null). It identifies what one Process model call consumes. Peers and the RAW are context and are not part of it.

## 5. Initial Process, rework and repeated input

- **Initial Process:** no Review exists; no Brief, no feedback section, `rework_responses` must be absent or empty.
- **Authorized rework:** a Review exists; the Brief is built and supplied, and Process must answer it.
- **Unchanged tree with new feedback:** the CR-002 authorized new cycle already processes an unchanged tree; it now carries the Brief, so the first legitimate rework is never refused for an unchanged Root fingerprint.
- **Ordinary call:** keeps the CR-002 no-change behaviour (`NO_CHANGES_TO_PROCESS` over an unchanged tree), unchanged.
- **Exactly repeated input:** when a new model call would consume exactly the latest iteration's run-input identity (same input tree, same Brief), no model is called and nothing is written: `NO_CHANGES_TO_PROCESS`. This narrows CR-002 only for that case (a toggle with no edit, no new Review and a fixpoint normalization); the runner's Processing Status claim stays the guard against re-dispatch.

No iteration budget, autonomy policy or automatic decision is introduced.

## 6. Process output contract

The Process response gains `rework_responses: [{item, outcome, explanation, product_question_index}]`:
- `outcome` is `RESOLVED` (corrected in this output, or already settled by authoritative content), `REBUTTED` (the item does not establish a real defect, with evidence) or `ESCALATED` (it stays unresolved, and why);
- `explanation` is required non-empty text;
- `product_question_index` is allowed only on ESCALATED. It is **required** when the item is a material WHAT item, and must then name a question of the same output with `material: true`. An escalated material WHAT therefore stays in `product_questions` (Material-WHAT Gate §3), and the WI-1 Review must verify it.

When a Brief was supplied the key is required, even for a Brief with no items; its absence answers nothing. Every item is answered exactly once by its reference: a missing, duplicated or invented reference is `INVALID_MODEL_OUTPUT`, and there is no group or "everything resolved" answer. Without a Brief, a non-empty list is `INVALID_MODEL_OUTPUT`.

The prompt instructs Process to examine every item; decide whether it is valid; try to resolve it from the current Requirement, the RAW, the peers and source-established constraints; correct the normalized Requirement only where that evidence justifies it; rebut with evidence; escalate a material WHAT that evidence and authority cannot settle; and never invent product decisions, add product behaviour, contradict another obligation or drop a genuinely open material question. Delegated autonomous defaults are WI-5 and are not authorized here.

WI-1's `product_questions` semantics are unchanged.

## 7. Independent Review

The Review receives, as part of the current Process Result's claims, each rework response with the Brief item it answers (reference, category, `material WHAT` flag, kind, Requirement ID, text, and the answer). It never receives the previous Review Result, its verdict, severities, reasons, WHAT status or assessment. It still performs its own full review of the current Requirement.

The Review response gains `rework_verifications: [{item, outcome, severity, reason}]`:
- `CONFIRMED`: the claim holds (the defect is gone, faithfully to the source, consistently, with no new defect; or the rebuttal is right; or the escalation is genuine);
- `REJECTED`: the claim does not hold and a defect remains; it carries the severity of what remains;
- `UNRESOLVED`: the context cannot settle it; no severity.

When the Process Result answered a Brief the key is required and every response is verified exactly once; without a Brief a non-empty list is refused.

**Derivation**, by code only:
- **verdict:** a REJECTED rework verification contributes its severity, like a confirmed finding;
- **WHAT status:** a material WHAT item makes the status `BLOCKED_ON_WHAT` when its response is ESCALATED (whatever the verification), or when its verification is not CONFIRMED. This term can only block. A material WHAT item clears only through a RESOLVED or REBUTTED answer that the reviewer CONFIRMED, and then only if the unchanged Material-WHAT Gate derivation over the new Process Result's own questions and `material_unresolved_what` is also CLEAR. No Process-authored outcome overrides the gate.

**Escalation consistency.** A CONFIRMED verification of an ESCALATED material WHAT answer asserts that the WHAT is still open. The same review's verification of the product question that answer names (`product_question_index`) must then leave the question open under Material-WHAT Gate §5: CONFIRMED with `material: true`, UNRESOLVED, or REJECTED as `ANSWERED_BY_OTHER_REQUIREMENT` (still open here). Confirming the escalation while rejecting the question as answered in this Requirement or as technical HOW, or confirming it as immaterial, is a contradiction: the model output is `INVALID_MODEL_OUTPUT`, and a persisted Review Result that carries it is `INVALID_REVIEW_RESULT` on read. A rejected or unresolved escalation is not a contradiction; it blocks.

| Answer to a material WHAT item | Verification | Status contribution |
|---|---|---|
| RESOLVED or REBUTTED | CONFIRMED | none: may clear |
| RESOLVED or REBUTTED | REJECTED or UNRESOLVED | blocks |
| ESCALATED | CONFIRMED, question left open | blocks |
| ESCALATED | CONFIRMED, question closed | refused as contradictory |
| ESCALATED | REJECTED or UNRESOLVED | blocks |

The quality verdict is unchanged by this rule.

## 8. Artifact versions

**Process Result 0.5** = 0.4 plus three keys, all required:
- `rework_brief`: the full Brief payload with its identity, or null;
- `rework_responses`: the list, possibly empty;
- `run_input_identity`.

On read, the Brief identity and the run-input identity are recomputed and must match, the Brief items keep their closed category shapes, and the responses are held to the same exact-once and escalation rules as the model's response. A 0.5 Result without a Brief cannot carry responses. Older versions may carry none of the keys; 0.1–0.4 iterations received no feedback by construction, so their Brief is none and their run-input identity is computed with a null Brief.

**Review Result 0.5** = 0.4 plus three keys, all required:
- `reviewed_rework_brief_identity` (or null);
- `reviewed_rework_responses`: a copy of the bound Process Result's responses, each with the `blocks_what` of its item;
- `rework_verifications`.

On read the verdict and WHAT status are recomputed with the §7 terms, the verifications must cover the reviewed responses exactly once, and older versions may carry none of the keys.

**Coherence** (`what_clearance`, extending Material-WHAT Gate §6): a 0.5 Review must carry exactly the bound Process Result's Brief identity and responses. A pre-0.5 Review of a 0.5 Process Result is incoherent, because the reviewer of a 0.5 Result always writes 0.5. A 0.5 Review of a 0.4 Process Result carries a null Brief and no responses. Incoherence is `INVALID_REVIEW_RESULT` at Ready and Apply, and `REQUIREMENT_NOT_ADMISSIBLE` at TSA admission, exactly as for WI-1 evidence.

**Validation against history.** Read-back of a persisted Brief checks its shape and recomputes its identity, which detects an inconsistent edit but not a consistent one. So a bound Brief is also rebuilt from the artifacts it names and must have the same identity:
- by Process on `--resume-result` (§10);
- by Review before the reviewer runs: the source must be the latest Review Result of an earlier Process iteration (§3), and the Brief of the Process Result under review is rebuilt from it and the Process Result it reviewed, both under the Root. A missing source, an incoherent lineage or a different identity (for example an altered item, relation kind or target) is `INVALID_PROCESS_RESULT`; no model call, nothing written.

A Review Result therefore binds only a Brief that its own stage proved from history. A consistent hand edit of both the Brief and its source Review remains undetectable, as for every Standard artifact without a digest.

Older Process and Review Results (0.1–0.4) stay readable and are never rewritten or reinterpreted.

## 9. WI-1 compatibility

TSA admission (I05 check 9) is unchanged: it calls `what_clearance` on the latest Process and Review Results, so 0.5 rework evidence is admitted only when CLEAR, coherent and bound to the current tree, and every BLOCKED_ON_WHAT, contradictory, mismatched, stale or misbound pair is `REQUIREMENT_NOT_ADMISSIBLE`. Offline regressions run the production admission over evidence produced by the real Process and Review stages.

Preserved unchanged: structured product questions, independent question verification, `material_unresolved_what`, the derived status, CLEAR / BLOCKED_ON_WHAT, legacy UNKNOWN, and the Ready, Apply and TSA admission refusals. 0.5 evidence is WI-1 evidence (`has_question_evidence`). Only a valid current Review can establish clearance.

## 10. Recovery and idempotency

Unchanged: numbered immutable Process Results, persisted before the Root rewrite; fresh-state checks before every write; the input-equality ambiguity and its explicit options; empty-shell recovery; the Process -> Review transition.

Added:
- **Fresh Brief before persisting.** Immediately before a new or recovered Process Result is persisted, the Brief is rebuilt from a fresh read of the Root's children. A different identity is `PROCESSING_STATE_CONFLICT`; the model output is dropped and nothing is written.
- **Explicit resume.** `--resume-result` replays the persisted output without a model call. For a 0.5 Result, the Brief rebuilt from durable history must equal the bound one; otherwise `PROCESSING_STATE_CONFLICT`, nothing written, and `--new-iteration-after` processes the current tree with the current feedback. A persisted Brief is never rebuilt into a different one. Pre-0.5 Results are replayed as before.
- **Empty-shell recovery** binds the Brief derived from the same durable history.
- **Read-back** of a persisted Process Result also compares the Brief identity and the responses.

Locking and concurrency assumptions are unchanged.

## 11. Historical Review feedback

A 0.1–0.3 Review Result is a valid source when its lineage holds. It supplies its finding and relation items; it has no question evidence, so it supplies no question, material-WHAT or rework items, and nothing is fabricated for it. It never establishes WHAT clearance (Material-WHAT Gate §10): the new Process writes 0.5 and the next Review writes 0.5, which alone can derive CLEAR. No migration is required. A historical Review that cannot be validated refuses with `REVIEW_LINEAGE_INVALID`.

## 12. Relations and peers

The full Project comparison context and the existing relations are reused unchanged. An unconfirmed relation proposal is carried as a Brief item and may stay unresolved (ESCALATED without a product question) until its peer evidence is checked. No relation is written, and no DEPENDS_ON semantics, closure, dependency binding, graph algorithm or peer reprocessing is added (WI-4).

## 13. Refusal codes

| Code | Raised by |
|---|---|
| `REVIEW_LINEAGE_INVALID` (new) | Process: the review history cannot establish which feedback a rework must answer (§3) |
| `INVALID_MODEL_OUTPUT` (existing) | Process: `rework_responses` breaks §6; Review: `rework_verifications` breaks §7, including a contradictory escalation |
| `INVALID_PROCESS_RESULT` (existing) | Review: the bound Brief is not the one its source Review gives (§8) |
| `PROCESSING_STATE_CONFLICT` (existing) | Process: the Brief changed during the run or since a resumed Result (§10) |
| `NO_CHANGES_TO_PROCESS` (existing, normal) | Process: exactly repeated run input (§5) |
| `INVALID_REVIEW_RESULT` / `REQUIREMENT_NOT_ADMISSIBLE` (existing) | incoherent rework evidence (§8) |

All are deterministic, are never retried automatically, and write nothing beyond what was already durable.

## 14. Non-goals and limits

**Non-goals:** WI-4 relation semantics, WI-5 autonomy policy, WI-6 automatic Ready decisions, Applied Requirement revision, new States, roles, databases or a Rework Brief entity, Delivery Planning.

**Limits:**
- Whether a correction is faithful, a rebuttal right or an escalation genuine is a model judgement; code enforces coverage, binding and the WHAT rule only.
- An empty Process Result shell left by an **unedited** rework cannot be completed with `--recover-empty-result`: an ordinary call over the unchanged tree reports no changes first. This predates this delta (it equally affects CR-002) and is not changed here.
- Escalation consistency compares judgements by structure (the named question); a reviewer who confirms a RESOLVED answer while listing the same question again in `material_unresolved_what` under different wording is not detected as contradictory, but still blocks through that list.
- Any unreadable Review Result under the Root, including an empty Review shell left by a failed review, now refuses every Process run with `REVIEW_LINEAGE_INVALID`, where Process previously ignored it; recovery is manual (complete the Review shell in `Review` first).
- Not live-verified: the 0.5 payloads have not been compared against live Fibery serialization. Under the project's Fibery rule they are not frozen until a live probe and a fake-versus-live comparison exist.
