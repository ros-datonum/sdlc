# Requirement Applied Requalification — v0.1 (delta)

**Status:** CONTRACT DELTA. Offline-verified only (`tests/test_applied_requalification.py`); NOT LIVE-VERIFIED. No production code changes for it.
**Authorization:** human instruction "ARP1 Gate 3D — Authorize Bounded Requalification of Applied Requirements", for baseline `8bb29e2d5d8cc320d02c05cf5c06f3799e6e9add`. The approval record is that instruction; no signature is claimed. It authorizes the transition; it performs none, and it approves no clarification text.
**Amends, narrowly and only as stated here:**
- Requirement-Lifecycle-Ownership-v0.2 §12 (one row) and §13 (one chaining segment);
- Requirement-Lifecycle-v0.2-Current §2 (one more human transition);
- Requirement-Dependency-Bindings-v0.1 §9 (one more recovery route);
- the "Applied revision" non-goals of Standard-Requirement-Process-Spec-v0.1 §17, Standard-Requirement-Apply-Spec-v0.1 §26 (and the undesigned "revision question" of §13 and §17), Requirement-Dependency-Bindings-v0.1 §14, Requirement-Rework-Brief-v0.1, Requirement-Autonomous-Ready-v0.1, Requirement-Autonomous-Resolution-v0.1 §12 and Requirement-Material-WHAT-Gate-v0.1 §13: Applied revision stays a non-goal except for the bounded requalification defined here;
- Requirement-Material-WHAT-Gate-v0.1 §10 and §11: "requalification of an Applied Requirement", left there to "the separate Applied-revision work item", is this delta;
- TSA-C01-Contract-v0.2 §7.4: "the existing Requirement lifecycle" through which a Requirement is "separately changed and approved" is this requalification.

Those documents are unchanged on disk. Where this delta and they disagree, this delta governs for the listed points only. Apart from the points listed, Material-WHAT Gate v0.1, Rework Brief v0.1, Dependency Bindings v0.1, Normative Tree Binding v0.1, Human Attestation v0.1, Autonomous Ready v0.1 and TSA-C01 are otherwise unchanged.

## 1. The defect

TSA-C01 §7.4 requires a material WHAT question found by TSA to be answered by changing the Requirement "through the existing Requirement lifecycle", then starting a new TSA cycle. The Requirement lifecycle had no such path, and three things must be kept apart:

| | What it is | Before this delta |
|---|---|---|
| A. Implementation route | A human may set any State in Fibery. A `Standard + Process + Not Processed` Requirement is routed to Process, which the dispatcher runs as an authorized new cycle (CR-002). The dispatcher cannot see the previous State. | Present. A hand-made `Applied -> Process` runs Process, Review and, after a human approval, Apply. |
| B. Lifecycle contract | The ownership table (Lifecycle Ownership v0.2 §12) lists every authorized transition; "No other normal-flow transition is authorized." | No row leaves `Applied`. Applied revision is a non-goal in seven specifications. Dependency Bindings §9 names only `Ready -> Process` and `Apply -> Process` as recovery. |
| C. Generic revision | Revision numbering, update, supersession, split, merge, relation restructuring. | Unsupported, and still unsupported (§11). |

A successful fake-workspace probe of A is not authorization. This delta adds B for one bounded case and leaves C out.

## 2. The transition

| Requirement | From | To | Owner | Meaning |
|---|---|---|---|---|
| Standard | Applied | Process | HUMAN | REQUALIFY: start a new Standard Process cycle for a previously Applied Requirement, after a human decided its content must be clarified |

Boundaries:
- **Explicit and human.** The operator makes it in Fibery, or an authorized assistant makes it on the operator's explicit instruction for that Requirement. No machine stage, dispatcher route, runner step or Ready decider ever makes it: the dispatcher has no route from `Applied`, and the Ready decider only leaves `Ready`.
- **No new State, database, field, relation type, artifact or role.** The State transition is the decision, as for `Ready -> Process`.
- **Same identity.** The same Requirement entity, Requirement ID, public id, Type, Project and Root Document continue.
- **History kept.** Every Process and Review Result stays immutable. Nothing is reset or deleted.
- **The normal chain follows:** a new Process iteration, a mandatory independent Review, a stop at `Ready`, a fresh human `Ready -> Apply`, and deterministic Apply with every current evidence check.
- **Nothing propagates.** No dependent is moved, reprocessed or rebound automatically, and no TSA cycle is approved, reworked or recovered.

Chaining segment (Lifecycle Ownership v0.2 §13):

```text
HUMAN:  Applied -> Process          REQUALIFY
SYSTEM: Process -> Review -> Ready
STOP
HUMAN:  Ready -> Apply              fresh APPROVE (or Ready -> Process, REWORK)
SYSTEM: Apply -> Applied
STOP
```

`Standard + Applied` stays a machine no-op. Processing Status is reset on entering `Process` exactly as for any other entry.

## 3. Execution

- **Process runs through the dispatcher route** (`Standard + Process + Not Processed`). The dispatcher invokes it as an authorized new cycle, so it creates the next iteration even when the Root is unedited. That is required for a dependent requalified only because its dependency changed (§7). Use a runner scoped to the Project (`sdlc worker run --project <CODE>`), after checking that no other Requirement of that Project is machine-eligible.
- The manual `sdlc project requirement process` command is not an authorized new cycle. Over an unedited Root it reports `NO_CHANGES_TO_PROCESS` and writes nothing.
- The Rework Brief of the new iteration comes from the latest historical Review, as for any iteration (Rework Brief v0.1). A TSA Review is never Requirement input; a TSA question reaches the Requirement only through a human Root edit (§4).
- **Review** reviews the new Process iteration over the current tree. A Review over an unchanged tree reports `NO_CHANGES_TO_REVIEW`, so there is no Review-only requalification.
- **Ready and Apply** are unchanged. Apply requires `State = Apply`, a current reviewed binding, current resolution and dependency evidence, and every direct dependency Applied.

## 4. Authoritative input

- **When.** A human clarification is written into the normative Root as part of the requalification, before its Process run. With no runner working on the Project, the edit may follow the human `Applied -> Process`. With a runner working on it, the reset automation and the runner would start Process within seconds of the transition, so the edit is made just before it. An edited Root of an `Applied` Requirement is not by itself requalification: it only makes the Requirement inadmissible to TSA (its tree no longer matches its Review) and starts nothing.
- **Root editing proves nothing about authorship** (Human Attestation v0.1 §2). The model never creates an attestation, and its earlier output never becomes authority.
- **Attestation.** The operator attests each new clarification under Human Attestation v0.1 §3, with the exact Root text, before the Process run. Process and Review are then shown it under `# OPERATOR-ATTESTED CLARIFICATIONS`. Wherever a material Rework Brief item's answer relies on a REQUIREMENT citation, the citation must be covered by a current attestation, inside a requalification as anywhere else: Process refuses (`INVALID_MODEL_OUTPUT`), Review (`RESOLUTION_EVIDENCE_STALE`, no model call), Ready and Apply (`RESOLUTION_EVIDENCE_STALE`) and TSA admission (`REQUIREMENT_NOT_ADMISSIBLE`).
- **What is not code-enforced.** A requalification normally starts from an Applied Requirement whose latest current-format Review derived WHAT `CLEAR`. That Review's Rework Brief carries no material item, so a clarification answering a TSA question relies on no Brief item, and no code binds it to an attestation. Its authority is the operator's attestation shown to both stages, the independent Review, the fresh human `Ready -> Apply`, and the explicit Input Manifest acceptance of the next TSA cycle (TSA-C01 §2.2). Process may normalize the wording, so the operational gate checks each attestation against the Root before the Process run and again against the processed Root at `Ready`, before `Ready -> Apply` (§10).
- **Legacy Applied rows.** A historical Applied Requirement with pre-0.4 or pre-0.6 evidence, or a hand-placed `Applied`, may also be requalified; Material-WHAT Gate v0.1 §11 and Dependency Bindings v0.1 §12 already name requalification as its only route to current evidence. Its latest Review may not be `CLEAR` current-format evidence, so its Brief may carry material items, which the attestation rule then governs as above.
- **Existing attestations are kept** unless the operator explicitly revokes one. Reliance is recomputed from the current evidence (Human Attestation v0.1 §5). Once a requalified iteration no longer cites an attested text, revoking that attestation refuses nothing. Keeping it remains the operator's obligation.
- **The RAW is never touched.** Its Processing Result and the `Derived From` provenance are unchanged.

## 5. Revision

- Requalification keeps the same entity and the same `Revision` value. No stage writes `Revision`; Ready and Apply read it back unchanged.
- The evidence history of a requalification is its new Process and Review iterations, their fingerprints and digests, and the TSA Input Manifest that later binds them.
- `Revision` is not provenance and no consumer uses it as version identity: TSA-C01 §2.2 already says so, and no Process, Review, dependency binding or Manifest row records it. An unchanged value is therefore not unsafe here, and it is not a revision mechanism.
- Revision numbering stays unsupported. This delta is not Requirement versioning and must not be described as one.

## 6. Relations

- Apply is additive: it writes confirmed proposals and never removes or replaces an edge.
- Review re-verifies every existing DEPENDS_ON edge (one `dependency_verifications` entry each, or `INVALID_MODEL_OUTPUT`) and binds them as `EXISTING` whatever their outcome. Existing AFFECTS edges are not re-verified.
- **Bounded requalification is supported only while the existing relation graph stays semantically valid.** A Fibery edge that is still present is not evidence that it is still correct.
- **Operational recovery gate.** Before the human `Ready -> Apply` of each requalified Requirement, the gate compares:
  1. the relations before requalification;
  2. the new Process relation proposals;
  3. the independent Review's verifications and confirmations;
  4. the edges Apply will write.

  If an existing edge would need removal or replacement (for example, the new Review rejected it), STOP before `Ready -> Apply`. Apply would leave it in place, so approving would make an Applied Requirement whose own latest Review rejects its edge. Relation pruning is not part of this delta.

## 7. Dependency cascade

- Any new Review Result or tree change of a dependency D makes every Requirement whose Review bound D stale (Dependency Bindings v0.1 §9), directly or transitively. TSA admission then refuses any selection containing it.
- A stale dependent is requalified on its own: `Applied -> Process`, an unedited Root is enough, Process through the dispatcher, then Review binds the current versions. No binding is rewritten by hand or by code.
- **Order.** A dependent's Review refuses while any member of its interpretation set has stale evidence (`DEPENDENCY_EVIDENCE_INVALID`, no model call), and its Apply refuses until every direct dependency is Applied (`DEPENDENCY_NOT_APPLIED`). Requalify dependencies first, each to `Applied`, then their dependents.
- **Out of order.** A refused Review leaves the dependent at `Review` with Processing Status `Failed`, which the runner never retries. Once its dependencies are current, the operator runs the stage explicitly (`sdlc project requirement review`); nothing recovers it automatically.
- **ARP1:** FR-0130 DEPENDS_ON FR-0129; CON-0133 DEPENDS_ON FR-0129 and FR-0130. A change to FR-0129 requires FR-0129, then FR-0130, then CON-0133. CON-0132 is outside that chain.
- **AFFECTS** invalidates nothing and supplies no definition. NFR-0131, connected to CON-0132 by AFFECTS both ways, keeps its evidence. It needs its own requalification only if an approved clarification changes its normative meaning, which is a human judgement.

## 8. TSA currentness

TSA-C01 is unchanged. Bounded requalification relies on it as follows:
- A selected Requirement leaving `Applied`, a changed normative tree, a new Process Result, a new Review Result, or a change to its dependency evidence makes the cycle's inputs stale. `approve`, `rework` and `resume` refuse with `INPUTS_STALE`, and `inspect` reports `INSPECT_STALE`.
- A repeated `start` for the same cycle id refuses with `INPUTS_STALE`. It never re-accepts.
- The Input Manifest and the Architecture, Process, Review and Human Decision artifacts of the old cycle remain immutable, readable history.
- A cycle cannot take new Requirement versions (TSA-C01 §3.2). Further architecture work uses a new cycle id, whose admission reads the requalified evidence and whose Manifest is accepted afresh. The same Requirement identities may be selected again.

## 9. Autonomy

- Requalification is permitted only while no Ready delegation exists for the Project in `[ready_decisions]`, for the whole cycle from `Applied -> Process` to `Applied`. The Ready decider cannot tell a requalification cycle from any other, so this is an operator precondition checked at each operational gate, not a code guard.
- `[autonomy]` delegated defaults are unchanged and authorize no transition.
- The repository ships no Ready delegation (`mode = "disabled"`), and a test pins it.

## 10. Operational recovery gate

Every live requalification runs under a separately authorized, read-mostly gate, run by the operator or an assistant on the operator's instruction. Code does not enforce these checks. For each Requirement:

1. **Before `Applied -> Process`:** no Ready delegation for the Project (§9); the dependency order of §7; each clarification approved by the operator and attested exactly as it will stand in the Root (§4); a snapshot of the Requirement's relations.
2. **At `Ready`, before `Ready -> Apply`:**
   - the new Review is current, and its WHAT status and verdict are what the operator accepts;
   - each attestation still matches the processed Root text (§4);
   - the relation comparison of §6. STOP if an existing edge would need removal or replacement: human `approve` needs only an acknowledgement of a BLOCKING verdict, and a direct Fibery `Ready -> Apply` needs nothing, so this STOP is procedural.
3. **After `Applied`:** dependents now stale are listed for their own requalification (§7). TSA admission of the intended selection is checked read-only before any new cycle (§8).

Not yet live-verified: that the Fibery reset automation sets `Not Processed` on `Standard Applied -> Process`. Its condition is the target State, which makes this plausible, but the project rule for new Fibery semantics requires a narrow probe on temporary state before the first live requalification.

## 11. Not supported

- Revision numbering, update, retirement, supersession, split or merge.
- Relation removal, replacement or pruning, and any restructuring of the relation graph.
- Automatic requalification of dependents, impact propagation, or reprocessing the graph.
- Requalification of a Raw Requirement, or of a Standard Requirement in any State other than `Applied`.
- An automatic or delegated `Applied -> Process`.
- Any change to TSA-C01, its artifacts or its result codes.
- Any change to the Fibery schema, automations or runtime configuration.

## 12. Verification

`tests/test_applied_requalification.py` uses the in-memory fakes, fake model runtimes and the production entry points. No Fibery call, no model call.

| Case | Test |
|---|---|
| A–D, I: re-entry, authorized new cycle, next iteration, history immutable, identity | `test_a_human_applied_to_process_runs_the_next_iteration` (edited and unedited Root) |
| manual command over an unedited Root | `test_an_unedited_requalification_needs_the_dispatcher_route` |
| E, F, H: independent Review of the current input, stop at Ready, no Apply without a human | `test_review_judges_the_new_iteration_and_stops_at_ready` |
| G, I, J: fresh approval re-Applies; identity and Revision unchanged | `test_a_fresh_human_approval_re_applies_with_revision_unchanged` (the fake has no Revision write, so the guarantee is the production read-back of every stage) |
| K: existing edges re-verified and kept | `test_existing_edges_are_reverified_and_kept` |
| L: no removal (out of scope) | `test_a_rejected_existing_edge_is_never_removed_by_apply` |
| M: FR-0129 change makes FR-0130 and CON-0133 stale | `test_a_requalified_fr_0129_makes_fr_0130_and_con_0133_stale` |
| N: no Review-only shortcut; order; restored bindings; TSA admits | `test_dependents_requalify_in_order_and_restore_current_bindings` |
| O: AFFECTS invalidates nothing | `test_an_affects_peer_is_not_invalidated_by_requalification` (an AFFECTS pair modelled like NFR-0131 and CON-0132, both ways) |
| P, Q: leaving Applied alone makes the old cycle stale; so does each later step; a new cycle admits; the old Manifest is kept | `test_leaving_applied_alone_makes_the_bound_cycle_stale`, `test_requalification_makes_the_bound_cycle_stale_and_a_new_cycle_admits_it` |
| R: attestation currentness inside requalification; recomputed reliance | `test_an_attested_answer_inside_a_requalification_needs_a_current_attestation`, `test_reliance_is_recomputed_from_the_requalified_evidence` |
| S: only the requalified Requirement is written | `test_requalification_writes_only_the_requalified_requirement` |
| T: no Ready delegation | `test_the_repository_delegates_no_ready_decision_for_requalification` |

In M, N and O the predecessor's completed requalification is represented by replacing its evidence with a new reviewed iteration. The real Process, Review and Apply path of a requalified Requirement is exercised on the dependent itself. In N the refused out-of-order Review is retried by calling the dispatcher again, as the explicit `review` command would; a live runner does not retry it (§7).
