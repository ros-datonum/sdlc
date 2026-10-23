# Requirement Human Attestation — v0.1 (delta)

**Status:** IMPLEMENTED ON BRANCH `fix/requirements-human-attestation`; NOT LIVE-VERIFIED. No attestation is configured anywhere.
**Authorization:** human instruction "Fix Human-Authored Normative Input Authority Across Rework and Review", for baseline `4df9f3c1196fab9403f3ca372295e0393642072f`. The operator chose, in that session, to record attestations in `config/sdlc.toml` and to recompute reliance from persisted evidence rather than change the Result schemas. The approval record is that instruction; no signature is claimed.
**Amends, narrowly and only as stated here:**
- Requirement-Autonomous-Resolution-v0.1 §2 (Class A), §6 (Review pre-checks and reviewer instruction), §7 (rework authority rule), §8 (currentness) and §11.3 (how approval is recorded, for this one decision kind);
- Requirement-Rework-Brief-v0.1, only through Autonomous Resolution §7 as amended here.

Those documents are unchanged on disk. Where this delta and they disagree, this delta governs for the listed points only. Material-WHAT Gate v0.1 is unchanged: its gate, its derived WHAT status and its non-waivability are exactly as before.

## 1. The defect

Autonomous Resolution §2 lets a SOURCE_GROUNDED resolution rest on "this Requirement's own normative input (which holds any earlier human clarification)". Two rules contradicted that:

1. The Review prompt told the reviewer, without condition, that "this Requirement's current content was written by the earlier analysis", so a REQUIREMENT citation of it never passed `source_supports_answer` or `authority_class_correct`. That is false for a text the operator edited into the Root between iterations.
2. §7 forbade a REQUIREMENT-only answer to an item that carries an unconfirmed resolution. Once a Review rejected a resolution resting on a human clarification, no later iteration could cite that clarification again. The same rule was also weaker than it looked: adding any RAW quote beside the REQUIREMENT one exempted it.

ARP1-CON-0132 met both live. Its Review 2 rejected the operator's logging decision as text "the earlier analysis added". That was false: Process Result 1's output does not contain it.

## 2. What persisted evidence can and cannot prove

- **What can be shown.** Each Process Result persists its normalized output and the fingerprint of its input tree. A quote absent from every earlier Process output was written by no Process iteration of this Requirement.
- **What cannot be shown.** That a human decided the text:
  - The Root's first content is the RAW decomposition's model output.
  - Fibery records no author for Document content.
  - The SDLC writes with the operator's own account, so its transitions and the operator's look the same.
  - A Root may be edited by any tool with access, including an agent acting on an instruction.

  "This text existed before this model call" is therefore not "a human approved this text".

So human authority needs an explicit attestation. A fingerprint is change detection, never authorship. A model's statement that a text is a human decision is never evidence.

## 3. The attestation (what counts as human-authored input)

A human-authored normative input is exactly a text the operator attests in the SDLC runtime configuration, `config/sdlc.toml`. This is the same operator-controlled boundary that approves an autonomy policy (Autonomous Resolution §3.1). Nothing else attests: not a Fibery Document, comment or field, not a State transition, and not a model's claim.

```toml
[[attestations.clarifications]]
project_code = "<PROJECT_CODE>"
requirement_id = "<PROJECT_CODE>-<…>"   # must belong to that Project
entity_id = "<the Requirement's Fibery entity UUID>"
text = "<the exact decided text>"
approved_by = "<who decided>"
approved_fingerprint = "<64 hex>"        # SHA-256 of the canonical content
```

- **Canonical content:**
  - the fields `project_code`, `requirement_id`, `entity_id` and `text`;
  - `requirement_id` and `text` are taken with leading and trailing whitespace stripped;
  - serialized as sorted-key, compact UTF-8 JSON and hashed with SHA-256;
  - `approved_by` is outside the fingerprint, as for a policy.
  - No command computes the fingerprint. A mismatch refusal prints the computed value, so re-approval is a deliberate copy by the operator: change detection, not a second factor.
- **Exact text.** A quote must occur, apart from whitespace runs, both in the Requirement's input as Process reads it (rendered Markdown) and in the attested `text`. Attest the text exactly as it stands in the Root, including any Markdown markers such as list bullets or emphasis; otherwise a legitimate citation is refused.
- **Load refusals.** The whole configuration is refused before any Fibery read when:
  - an unknown key appears or a key is missing;
  - any text is empty;
  - the Project code is not exact;
  - the Requirement ID is not of that Project;
  - the entity id is not a lowercase UUID;
  - the fingerprint does not match;
  - an attestation is repeated.

  The command reports a configuration error. A worker stage reports `AUTONOMY_POLICY_INVALID` (the snapshot is refused whole, §5).
- **Default and audit trail.**
  - Absent, the table attests nothing. This repository ships none.
  - Recording one is a reviewed change to the committed configuration, so git history records when it changed and who committed it.
  - It is not an authenticated signature: like a Fibery State transition, it attests that the operator's configuration says so.
- **Identity.** An attestation names one Requirement by both entity id and Requirement ID. It authorizes no other Requirement: not another entity with the same ID, and not the reverse.

An attestation is never a delegated policy, never a clause, never a `DELEGATED_DEFAULT` and never part of a policy's fingerprint or identity. Settling *who decided* does not make the decision right.

## 4. The authority rule

A Rework Brief item is **material** when it blocks WHAT (`what_refs`) or carries a resolution the source Review did not confirm (`resolution_refs`).

An answer to a material item **relies on** a REQUIREMENT citation when either:
- it is `RESOLVED` naming a resolution that cites it (a `DELEGATED_DEFAULT` excepted: its authority is its clause, and its REQUIREMENT applicability evidence stays governed by the policy checks); or
- it is `REBUTTED` and its evidence cites it.

`ESCALATED` relies on nothing.

**Rule.** Every relied-on REQUIREMENT citation must occur (whitespace runs as one space) within a current attestation of exactly this Requirement. Each citation is judged on its own: a RAW or dependency source beside it no longer exempts it.

This replaces the Autonomous Resolution §7 sentence "RESOLVED must name a resolution that cites the RAW or a dependency, or is a delegated default. REBUTTED must cite the RAW or a dependency." The structural rule that a `RESOLVED` answer to a `RESOLUTION` item names a resolution is kept.

**Scope of the narrowing.** This applies to every material item, not only to the `RESOLUTION` items the old §7 rule covered. That rule never applied to a blocking `PRODUCT_QUESTION`, a `MATERIAL_WHAT` item or a claim re-raising one, so before this delta a REQUIREMENT-only answer to such an item could pass Process, Review and Ready. It no longer can: closing a material question a Review left open from this Requirement's own text now needs a human attestation of that text. This narrows Autonomous Resolution §2 Class A for material Brief items, deliberately: unattested Requirement text at that point is indistinguishable from model output.

Everything else is unchanged:
- a REQUIREMENT citation must still quote the run's input, never its output, and binds the input-tree fingerprint (§4 of Autonomous Resolution);
- an answer to a non-material item, or a resolution no material item relies on, is governed by the earlier rules alone.

**Why a model cannot self-authorize.**
- Text a Process iteration wrote is in no attestation, because only the operator's configuration holds one.
- A model cannot write the configuration, and its claim that something is attested is ignored: code computes coverage.
- Widening an attested sentence makes the quote stop occurring in the attestation.
- Editing the attestation changes its fingerprint, and the configuration then refuses to load until it is approved again.

## 5. Where the rule is checked and how it becomes stale

The attestations travel in the same per-stage configuration snapshot as the autonomy policies (`AutonomyPolicies.attestations`). They are read as each command or worker stage starts and immutable for that stage, with the lifetime of Autonomous Resolution §3.4. Reliance is recomputed from persisted evidence at every point: the bound Brief, the rework responses, the resolutions and the exact quotes. No Result schema changes.

| Point | Check | Refusal |
|---|---|---|
| Process | After citations are bound, before anything is persisted. The model is shown this Requirement's attestations (`# OPERATOR-ATTESTED CLARIFICATIONS`). | `INVALID_MODEL_OUTPUT`; nothing written |
| Review | Before the reviewer is invoked, with the citation and policy re-checks. The reviewer is shown this Requirement's current attestations. | `RESOLUTION_EVIDENCE_STALE`; reviewer not invoked |
| Ready approval, Apply (before and after its writes), TSA admission | Inside the resolution currentness check, against the Requirement's entity. | `RESOLUTION_EVIDENCE_STALE` (Ready, Apply); `REQUIREMENT_NOT_ADMISSIBLE` (TSA) |
| Autonomous Ready, just before its State write | The reloaded snapshot's attestations must equal the ones the decision was made under. | The decision's guard refuses the transition |

A broken `[attestations]` table refuses the whole snapshot. A worker stage reports it under the existing `AUTONOMY_POLICY_INVALID` code, and the details name the `[attestations]` error.

Evidence becomes stale when:
- the relied-on attestation is removed;
- it is changed so that it no longer contains the quote;
- it is re-pointed at another Requirement;
- the Root changes after Review, which the existing tree bindings already refuse.

An attestation changed but still containing the exact quote keeps attesting that exact text, so evidence relying on that quote stays current.

**Operator obligation.** Evidence that relied on an attestation stays current only while the attestation does. Removing one after Apply makes that Requirement inadmissible to TSA, and with it any TSA selection containing it. Keep an attestation for as long as any evidence relies on it.

**Not covered.** `--resume-result` replays a persisted iteration without a model call and does not re-check attestations. The Review that must follow refuses a revoked one before its reviewer runs.

## 6. Review

The reviewer instruction no longer says that all current content was written by an earlier analysis. It now says:
- text an earlier analysis wrote is not authority;
- the one exception is a text listed under OPERATOR-ATTESTED CLARIFICATIONS, which code verified against the operator's configuration;
- citing an attested text settles who decided: it passes `authority_class_correct`, it passes `source_supports_answer` when the text actually states the answer, and an obligation it states is not unsupported;
- it does not make the decision correct: the reviewer still FAILs `consistent_with_raw`, `consistent_with_related` or `no_new_contradiction` when it contradicts the RAW, a related Requirement or this Requirement.

WHAT clearance is derived exactly as before: a resolution only stops being a blocker when the reviewer CONFIRMs it.

## 7. Rework and recovery

A Review that rejected an attested resolution stays valid history. Its Brief carries the resolution as a `RESOLUTION` item (and a rejected rework claim as a `REWORK_CLAIM`), both material. A later iteration may answer them again by citing the attested text. It may not cite any unattested text of the Requirement, with or without a RAW quote beside it.

For ARP1-CON-0132, the Root already equals Process Result 2's output, so an ordinary Process reports no changes. The next iteration therefore runs through the existing authorized-new-cycle dispatcher path, after the operator records the attestation and moves the Requirement Ready → Process.

## 8. Historical compatibility

- No Process or Review Result schema changes; every persisted Result stays readable and is never rewritten.
- `run_input_identity` is unchanged: it is recomputed on read-back from persisted fields, which carry no attestation. A repeat run whose only change is a newly recorded attestation is therefore reported as identical. The authorized-new-cycle route runs it.
- **Behaviour change for existing evidence.** Resolution-bound evidence whose rework answer to a material item relies on a REQUIREMENT citation is now refused unless a current attestation covers the quote:
  - at Review as `RESOLUTION_EVIDENCE_STALE`;
  - at Ready and Apply as `RESOLUTION_EVIDENCE_STALE`;
  - at TSA admission as `REQUIREMENT_NOT_ADMISSIBLE`.

  This includes answers the old rules accepted: a REQUIREMENT-only answer to a blocking question or `MATERIAL_WHAT` item, and a mixed RAW + REQUIREMENT answer to a `RESOLUTION` item. It applies to Requirements already in Ready, Apply or Applied.
- **Recovery.** If the cited text really is a human decision, the operator attests it, and the existing evidence becomes current again without a new iteration. Otherwise the Requirement goes through a new Process and Review cycle.
- **Inventory.** Before this change was integrated, every Standard Requirement in the live workspace (64, of which 61 have Process Results) was read without writes. Each one's latest Process Result was checked against this rule. Only ARP1-CON-0132's Process Result 2 relies on such a citation, and its Review 2 is BLOCKING. Earlier, superseded iterations were not checked: no consumer reads them as current evidence.

## 9. Non-goals

- No new Fibery database, field, State, role, relation type or agent.
- No authentication beyond the operator configuration, and no inference of authorship from Fibery history, timestamps or textual differences.
- No change to the RAW, to DELEGATED_DEFAULT, to the autonomy policy, or to dependency semantics.
- Nothing is live-verified.
