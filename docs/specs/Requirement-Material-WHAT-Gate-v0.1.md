# Requirement Material-WHAT Gate — v0.1 (delta)

**Status:** IMPLEMENTED ON BRANCH `impl/requirements-material-what-gate`; NOT LIVE-VERIFIED.
**Authorization:** human instruction "Implement WI-1 — Material-WHAT Safety Gate", for baseline `01aedc2002025ca5025db2be83c2eeec2f269514`. The approval record is that instruction; no signature is claimed.
**Amends, narrowly and only as stated here:**
- Standard-Requirement-Process-Spec-v0.1 §6 (output shape), §21 (open questions);
- Standard-Requirement-Review-Spec-v0.1 §7 (contract), §10 (Ready);
- Standard-Requirement-Ready-Spec-v0.1 §9 (acknowledgement);
- Standard-Requirement-Apply-Spec-v0.1 (validation before the first write);
- TSA-C01-Contract-v0.2 §2.1 (admission checks).

Those documents are unchanged on disk. Where this delta and they disagree, this delta governs for the listed points only.

## 1. Purpose and boundary

A Requirement may newly become Applied, and may enter a new TSA cycle, only when its current Review evidence establishes WHAT clearance under this contract. A known, material, unresolved product question about WHAT is never waivable. This delta adds one deterministic gate for that. It does not change:
- the lifecycle, the Fibery States or the human authority to approve a NEEDS_WORK or BLOCKING verdict of CLEAR evidence;
- relation semantics (dependency bindings are a later work item);
- the quality verdict;
- the normative tree binding.

It adds no automatic transition, no model role and no store.

## 2. Materiality

A product question is **material** when two plausible answers would require a different externally observable outcome for at least one input or situation within the Requirement's scope, so its acceptance cannot be judged without the answer.
- If every plausible answer leads to the same observable outcome, the question is not material.
- A question whose answers differ only in mechanism, technology, structure or how an outcome is produced is **technical HOW**, not a product question.

Materiality is a model judgement. The Process claim is verified by an independent Review; neither alone decides.

## 3. Process: structured question evidence

- The Process response gains `product_questions: [{detail, material}]`.
  - `detail` is non-empty and on one line.
  - `material` is a JSON boolean.
  - No other key is allowed. An absent list means none.
- `normalized_requirement.open_questions` is no longer accepted. Code renders the Open Questions section from the list, one `- {detail}` line per question, or `None.` when there are none. The gate never reads Open Questions prose.
- A question that only another Requirement seems to answer stays a question here (§5).
- **Process Result 0.4** = 0.3 plus a required `product_questions` list, which may be empty.
  - 0.3 stays readable and stays current tree evidence. It carries no question evidence; its absence means "not recorded", never "none".
  - A pre-0.4 payload carrying the key is refused.

## 4. Review: independent verification

The Review response gains two fields:
- **`question_verifications`**: exactly one per Process question, by `question_index`. Missing, duplicate or invented indexes are refused.
  - `CONFIRMED`: a genuine product question this Requirement leaves unanswered. It carries the reviewer's own `material` boolean, and no `basis` or `requirement_id`.
  - `REJECTED`: carries a `basis`:
    - `ANSWERED_IN_THIS_REQUIREMENT`;
    - `TECHNICAL_HOW`;
    - `ANSWERED_BY_OTHER_REQUIREMENT`, with `requirement_id` (and only this basis carries one).
    - It carries no `material`.
  - `UNRESOLVED`: carries no `material`, `basis` or `requirement_id`.
- **`material_unresolved_what: [{detail}]`**: material WHAT questions the listed ones do not cover, found anywhere, including Open Questions prose or the earlier analysis.
  - The key is **required**, even as an empty list. An absent key is refused rather than read as "none found".

The model states neither a verdict nor a WHAT status; there is no field for either. Review still never repairs or answers.

## 5. Derived `what_status`

Code derives the status; no model supplies it. A Process question **blocks** when:

| Verification | Blocks when |
|---|---|
| CONFIRMED | the reviewer's `material` is true |
| REJECTED, `ANSWERED_IN_THIS_REQUIREMENT` or `TECHNICAL_HOW` | never |
| REJECTED, `ANSWERED_BY_OTHER_REQUIREMENT` | the Process claimed it material |
| UNRESOLVED | always: the reviewer could not settle it, and a Process claim alone never clears a question |

`what_status` is `BLOCKED_ON_WHAT` if any question blocks or `material_unresolved_what` is non-empty, otherwise `CLEAR`.

A bare reference to another Requirement never clears a material question in v0.1, because no dependency evidence is bound.

`what_status` is independent of the verdict:
- a NEEDS_WORK Requirement may be CLEAR;
- a PASS Requirement may be BLOCKED_ON_WHAT;
- WARNING, NEEDS_WORK and PASS imply nothing about WHAT.

## 6. Review Result 0.4: binding and currentness

**Review Result 0.4** = 0.3 plus four fields:
- `reviewed_product_questions`: a copy of the bound Process Result's questions;
- `product_question_verifications`;
- `material_unresolved_what`;
- `derived_what_status`.

**On read:**
- All four are required in 0.4 and forbidden before it.
- The three lists must be JSON lists. Each persisted verification keeps its closed shape: only the defined keys, a non-empty text `reason`, and the field combination its outcome requires.
- The status is recomputed, and a mismatch makes the artifact invalid. This catches an internally inconsistent artifact, for example a status edited to CLEAR. It is **not** tamper protection: Standard Review Results carry no digest or signature, so a consistent hand edit of the verifications themselves is not detectable, exactly as for the quality verdict.

**Clearance** (`what_clearance`) is established only when all of these hold:
- the Review Result is 0.4;
- its existing bindings to the current Root, tree, Process iteration and Process output already hold, as checked by each consumer;
- its `reviewed_product_questions` equal exactly the bound Process Result 0.4's `product_questions`. Otherwise the evidence is incoherent and is refused as an invalid Review Result.

A pre-0.4 Review Result paired with a Process Result 0.4 is also incoherent and refused, because the reviewer of a 0.4 Process always writes 0.4. A downgraded Review therefore cannot drop the WHAT evidence of a question-bound Process.

Changed normative content is therefore stale before the gate is reached, and changed questions are incoherent.

`what_clearance` thus has exactly three coherent outcomes, and every gate admits only the first:

| Outcome | Meaning |
|---|---|
| `CLEAR` | current 0.4 evidence establishes that no material WHAT question is open |
| `BLOCKED_ON_WHAT` | current 0.4 evidence confirms an unresolved material WHAT question |
| **UNKNOWN** (no status) | the evidence predates this contract (§10), so whether a material WHAT question is open is not established either way |

UNKNOWN is not a status the Review Result records and is never reported as a confirmed defect.

## 7. Ready approval

`approve` changes State only for CLEAR evidence. After the existing binding checks and before the verdict acknowledgement check, it refuses:
- `BLOCKED_ON_WHAT` with `MATERIAL_WHAT_UNRESOLVED`; its details name the open questions;
- UNKNOWN with `PRODUCT_QUESTION_EVIDENCE_REQUIRED`; the message says clearance is unknown and names no defect;
- incoherent or forged evidence with `INVALID_REVIEW_RESULT`.

No verdict acknowledgement waives either refusal, and each writes nothing. The verdict acknowledgement rule is unchanged for CLEAR evidence.
- REWORK is unchanged.

## 8. Apply

- Apply applies only CLEAR evidence, however State became Apply: the approve command, a direct Fibery move, a Requirement already in Apply before this gate, or any later delegated transition. It refuses `BLOCKED_ON_WHAT` with `MATERIAL_WHAT_UNRESOLVED` and UNKNOWN with `PRODUCT_QUESTION_EVIDENCE_REQUIRED`.
- The check runs inside the binding check, so it applies at the start, immediately before the first write and immediately before Applied, against the Process Result read at that moment.
- On refusal nothing is written: no relation, Document or State. Through the runner, the only effects are its existing `Processing` claim and `Failed` status in Apply, as for every Apply refusal.
- All other Apply validation is unchanged.

## 9. TSA admission

- Admission gains **check 9**: the latest Review Result must establish `CLEAR` for the latest Process Result (§6).
  - `BLOCKED_ON_WHAT` and pre-0.4 evidence both give `REQUIREMENT_NOT_ADMISSIBLE`. The whole selection is refused and nothing is written.
- Input currentness re-runs admission, so a TSA cycle bound to pre-0.4 evidence now reads as not current.
- Check 9 never widens or narrows the selection (TSA-C01 §2).

## 10. Legacy evidence

- 0.1–0.3 Process and Review Results stay parseable and are never rewritten. "Legacy" means both artifacts are pre-0.4 (§6); they establish no WHAT status, so clearance is **UNKNOWN**, never CLEAR.

| Record | Behaviour |
|---|---|
| Legacy evidence in Ready | `approve` refuses with `PRODUCT_QUESTION_EVIDENCE_REQUIRED` until requalified (§11). REWORK is available. |
| Legacy evidence in Apply, however it got there | Apply refuses with `PRODUCT_QUESTION_EVIDENCE_REQUIRED` before any write (§8). |
| Historical Applied Requirement | Unchanged: its State, relations and Process and Review artifacts stay valid historical records. Nothing re-validates, migrates, resets or rewrites it; Apply reports it as already Applied. |
| Historical Applied Requirement selected for a new TSA cycle | Admission refuses (§9) until current clearance exists. Existing TSA Documents are not modified. |
| Review of a pre-0.4 Process Result | Refused with `PRODUCT_QUESTION_EVIDENCE_REQUIRED` before any model call. A pre-0.4 Review never makes a new review redundant. |

- There is no migration path; requalification is the only route to clearance (§11). This delta does not provide requalification of an Applied Requirement; that is the separate Applied-revision work item.
- The historical TSAP1 Project is not requalified; its artifacts serve only as offline regression fixtures.

## 11. Recovery after a refusal

- The human answers the question **in the Requirement's normative content**, by editing the Root Document (for example removing it from Open Questions and stating the answer in the normative sections).
- The Requirement then goes back to Process:
  - from Ready by REWORK (Ready → Process);
  - after an Apply refusal by a human Apply → Process move in Fibery. This is a State move the lifecycle documents do not yet list. It needs no new behaviour: the reset automation fires on any State change into Standard + Process whatever the source State, and the existing `Standard + Process + Not Processed` route runs Process as an authorized new cycle, which writes a new iteration whether the latest Process Result is 0.3 (an unchanged tree is processed again) or older (an older format is never replayed).
- **Requalification** is that ordinary new Process and independent Review: they write 0.4 evidence, and only a derived CLEAR then permits approval and Apply. It applies equally to UNKNOWN legacy evidence, for which no edit is required.
- Earlier Process and Review Results stay as immutable history.
- No acknowledgement, flag or edit to a Review Result substitutes for that.
- A Review, approval or Apply refused for missing question evidence (§10) recovers the same way: by moving it to Process. No transition is automatic.

## 12. Refusal codes

| Code | Raised by |
|---|---|
| `MATERIAL_WHAT_UNRESOLVED` | Ready, Apply: confirmed BLOCKED_ON_WHAT |
| `PRODUCT_QUESTION_EVIDENCE_REQUIRED` | Review: a pre-0.4 Process Result. Ready, Apply: UNKNOWN clearance from legacy evidence |
| `INVALID_REVIEW_RESULT` (existing) | incoherent or forged WHAT evidence |
| `REQUIREMENT_NOT_ADMISSIBLE` (existing) | TSA check 9 |

All are deterministic, write nothing and are never retried automatically.

## 13. Non-goals and limits

**Non-goals:** Rework Brief, automatic rework or approval, autonomy policy or defaults, dependency bindings, revision of Applied Requirements.

**Limits:**
- Materiality and discovery remain model judgements: the gate catches what Process or Review records, not what both miss.
- The Apply → Process recovery move is verified offline against the fakes only, including the modelled reset automation; it is not live-verified.
