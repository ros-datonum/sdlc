# Requirement Dependency Bindings — v0.1 (delta)

**Status:** IMPLEMENTED ON BRANCH `impl/requirements-dependency-bindings`; NOT LIVE-VERIFIED.
**Authorization:** human instruction "Implement WI-4 — Requirement Relation Semantics, Dependency Bindings and Collective Completeness", for baseline `29a2fef5aefc6e1e6af32c119683e58cb7fe0878`. The approval record is that instruction; no signature is claimed.
**Amends, narrowly and only as stated here:**
- Standard-Requirement-Process-Spec-v0.1 §5 (input context);
- Standard-Requirement-Review-Spec-v0.1 §5 (input context), §7 (contract), the Review Result shape;
- Standard-Requirement-Ready-Spec-v0.1 (approval checks);
- Standard-Requirement-Apply-Spec-v0.1 (validation before and after the relation writes);
- Requirement-Material-WHAT-Gate-v0.1 §5 (the `ANSWERED_BY_OTHER_REQUIREMENT` row);
- Requirement-Rework-Brief-v0.1 §4 (one more item category);
- TSA-C01-Contract-v0.2 §2.1 (admission gains check 10 and selection closure).

Those documents are unchanged on disk. Where this delta and they disagree, this delta governs for the listed points only. It preserves WI-1's non-waivable material-WHAT gate and WI-2's Rework Brief.

## 1. Purpose and boundary

Related Standard Requirements must be interpretable, reviewable and approvable as one consistent normative contract without restating shared definitions. This delta gives DEPENDS_ON a precise meaning, binds every normative dependency to the exact version that was reviewed, refuses stale or cyclic dependency evidence before any mutation, and closes a TSA selection under DEPENDS_ON.

Unchanged: the lifecycle and its States, the relation types and databases, the Fibery schema, the dispatcher and runner, human authority at Ready, AFFECTS semantics for Apply. No new agent, State, grouping entity, store, automatic transition, impact propagation or reprocessing. Process never writes a relation; only Apply does, after Review and human approval, exactly as before.

## 2. Relation semantics

- **DEPENDS_ON (R -> D):** understanding or evaluating at least one normative obligation of R requires a definition, rule, constraint or behaviour that D owns. R and D are interpreted together; D keeps owning the definition and R refers to it instead of restating it.
- **AFFECTS (R -> X):** a change to R may require re-evaluating X. It never establishes that X depends on R, never supplies a definition, and never enters an interpretation set, a binding, WHAT clearance or TSA closure.
- **Derived From / Produces:** provenance only.
- A shared topic does not establish DEPENDS_ON. Relations have direction; Fibery's inverse sides (Blocks, Impacted By) stay as they are. Historical relations are not migrated.

Both prompts carry these definitions. Process is told to distinguish a genuinely missing definition, a definition an existing dependency supplies (not missing, not to be copied), a conflicting definition (POSSIBLE_CONFLICT, no winner chosen), a duplicated definition that should have one owner (POSSIBLE_DUPLICATE), a missing DEPENDS_ON (propose it) and change impact (AFFECTS only). Process now also receives the Requirement's existing relations, read once a model call is certain.

## 3. Interpretation set

The interpretation set of R is R's direct DEPENDS_ON dependencies and, transitively, each member's own bound direct dependencies. Each member is read fresh and must be admissible normative authority, or the set is refused, never cut:
- exactly one Requirement carries its ID; Type Standard; same Project as R; not R;
- exactly one Root; a valid normative tree;
- its latest Process and Review Results exist without duplicate iterations; the Review Result is **dependency-bound (0.6)**, reviews the current tree and the latest Process output, and derives WHAT **CLEAR** through `what_clearance`;
- its DEPENDS_ON edges in Fibery are a subset of what its Review bound, and exactly that set once it is Applied;
- its own bindings still describe the current members (its evidence is not stale).

Its State is recorded but not restricted here: a Ready or Apply candidate may be reviewed with, and is labelled as such (§7 restricts Apply).

**Cycles:** reaching R, or a member already on the path, refuses with a cycle (`DEPENDENCY_CYCLE`), including a self-dependency.

**Bound:** at most `INTERPRETATION_SET_LIMIT` (100, the comparison-corpus record limit) members; more is refused. Every member is also inside the existing full-Project comparison context, whose input budget still applies. The reviewer receives the set in its own section: each direct dependency (existing edge or bindable proposal) and each transitive one, with its State, and each proposal that cannot be confirmed with the reason.

## 3.1 Complete relation reads

Every consumer of a Requirement's DEPENDS_ON and AFFECTS edges (Process context, Review, Ready, Apply, TSA admission and the traversal above) reads them through `requirement_relations`. A result means **both complete collections of exactly that Requirement, every target resolved**; it never means "whatever was available". The reader raises `FiberyError` instead of returning a smaller graph when:
- the Requirement Database has no Depends On or no Affects Field (the schema itself still loads, so commands that use no relations, such as Requirement add, are unaffected);
- the entity query returns no row, more than one, or a row for another entity;
- a collection is absent, `null`, or not exactly the verified shape `{"fibery/id": [<non-empty text id>, ...]}` (an empty object, a bare list or an extra key included);
- an id appears twice;
- a target cannot be read back as exactly that entity, has no Requirement ID, or shares its Requirement ID with another target.

**Valid empty** is `{"fibery/id": []}`: the shape constraint 15 verified live for a collection with no members. No other representation is read as empty.

Every consumer turns the failure into its own read-failure refusal, never into "no dependencies": `FIBERY_READ_FAILED` for Process, Review (before the model), Ready, Apply (before any write) and TSA admission (`CycleResultCode.FIBERY_READ_FAILED`, so a TSA input recheck reports a read failure, not stale inputs). Nothing is written, no State moves and no partial graph is bound or accepted. The in-memory test fake refuses the same way.

## 4. Review: independent verification

The Review response gains `dependency_verifications: [{requirement_id, outcome, severity, reason}]`: exactly one per existing DEPENDS_ON edge of R (required when R has any; missing, duplicate or invented entries are `INVALID_MODEL_OUTPUT`).
- CONFIRMED: the dependency is necessary and correctly directed.
- REJECTED: a false or misdirected dependency; a defect with a required severity that counts toward the verdict like a confirmed finding.
- UNRESOLVED: no severity.

Proposed DEPENDS_ON relations keep their existing `relation_verifications`. Before the reviewer runs, existing edges are resolved strictly (any failure refuses the review, no model call: `DEPENDENCY_EVIDENCE_INVALID`, `DEPENDENCY_CYCLE` or `FIBERY_READ_FAILED`); each DEPENDS_ON proposal is resolved on its own, and one that cannot be bound (missing, foreign, unreviewed, cyclic, …) is shown as unconfirmable. A review that confirms an unconfirmable proposal is `INVALID_MODEL_OUTPUT`, nothing written.

The reviewer is instructed to judge necessity, direction, ownership and consistency against the interpretation set, and to report a missing required dependency (INCOMPLETE naming the owner), a duplicated definition (POSSIBLE_DUPLICATE), contradictory rules or ambiguous ownership (POSSIBLE_CONFLICT) and AFFECTS used as authority (INCONSISTENT), without repairing or choosing. Review independence is unchanged: no earlier Review Result is sent.

A pre-0.6 latest Review never makes a new review redundant.

## 5. Proposed versus written relations

| Edge | Bound as | Written by |
|---|---|---|
| existing DEPENDS_ON of R | `EXISTING` (whatever its verification) | already in Fibery |
| DEPENDS_ON proposal the review confirms | `PROPOSED` | Apply, after approval |
| DEPENDS_ON proposal rejected or unresolved | not bound | never |
| a dependency of a bound dependency | `TRANSITIVE` | never by R's Apply |
| any AFFECTS | not bound | Apply as before, when confirmed |

Review validates a confirmed proposal against its target's evidence without pretending the edge exists.

## 6. Dependency bindings: Review Result 0.6

**Review Result 0.6** = 0.5 plus two required lists:
- `dependency_verifications` (§4);
- `dependency_bindings`: one per member of the bound set, in Requirement-ID order: `{requirement_id, entity_id, origin, tree_fingerprint, review_iteration, review_digest}`. `tree_fingerprint` is the member's normative-tree fingerprint (normative-tree binding v2); `review_digest` the canonical-content fingerprint of its latest Review Result, the same digest TSA admission records. These detect change; they are not signatures.

The bound set is the closure of EXISTING plus PROPOSED, computed by code from the members read; the model never supplies a binding.

**On read:** closed shapes; IDs unique and ordered; the EXISTING IDs are exactly the verified existing dependencies; the PROPOSED IDs exactly the confirmed DEPENDS_ON proposals that were not already edges; the verdict and the WHAT status are recomputed with the §4 and §8 terms. Older versions may carry neither key, and **establish no dependency evidence: their dependencies are unknown, not absent.** Process Results are unchanged (still 0.5).

## 7. Ready and Apply

Both recompute the interpretation set from the bound direct dependencies, against current Fibery, and require it to equal the bindings exactly.

- **Ready `approve`:** after the WI-1 gate and before the verdict acknowledgement. R's DEPENDS_ON edges must be exactly the EXISTING ones. Refusals, with nothing written and no acknowledgement override: `DEPENDENCY_EVIDENCE_REQUIRED` (pre-0.6 evidence), `DEPENDENCY_EVIDENCE_STALE`, `DEPENDENCY_CYCLE`, `FIBERY_READ_FAILED`.
- **Apply:**
  - immediately before the first write, R's edges may be the EXISTING ones plus confirmed proposals a partial earlier run wrote; every direct dependency must be **Applied** (`DEPENDENCY_NOT_APPLIED` otherwise), so an unapproved candidate never becomes authority for an Applied Requirement;
  - after the relation writes and before `Applied`, R's DEPENDS_ON edges must be exactly the bound direct set;
  - a cycle that appeared after approval through a dependency's re-reviewed evidence is `DEPENDENCY_CYCLE`; one created only by an unreviewed edge in Fibery is refused as `DEPENDENCY_EVIDENCE_STALE`, because that member's edges disagree with its Review;
  - the existing target preflight (missing, ambiguous, foreign, self) runs first and keeps its codes;
  - nothing is removed or replaced to make the graph agree; partial-write and retry semantics are unchanged (a retry completes the missing edges); no rollback, no retry.

## 8. WHAT clearance through a dependency

A material question rejected as `ANSWERED_BY_OTHER_REQUIREMENT` naming D now clears only when D is a **verified direct dependency** of R in a 0.6 review: an existing edge the review CONFIRMED, or a DEPENDS_ON proposal of a new edge it CONFIRMED and could bind. A proposal that repeats an existing edge decides nothing; that edge's own verification does. A 0.4 or 0.5 Review Result has no verified dependencies and keeps the WI-1 rule it was written under. Then D's exact version is bound (§6), and §7 and §9 refuse once it is stale. A bare Requirement ID, a Process assertion, an AFFECTS edge, a transitive dependency, a rejected or unresolved edge, or an unbindable proposal clears nothing. Every other WI-1 rule and the WI-2 escalation rules are unchanged, including the contradiction check, which uses the same verified set.

## 9. Staleness

R's dependency evidence stops establishing approval readiness as soon as any bound member's tree, latest Review Result, identity or own dependency evidence changes, a member becomes inadmissible, R gains or loses a DEPENDS_ON edge, or a cycle appears. This is checked against current Fibery content at Ready, before and after Apply's writes, and at TSA admission. A stale dependency refuses before any normative or relation write. R's State is not changed, nothing is reprocessed, and no impact is propagated. A change to an AFFECTS peer invalidates nothing.

Recovery is the existing lifecycle: rework R (Ready -> Process), or the human move Apply -> Process; the new Review binds the current versions.

## 10. TSA admission

- **Check 10:** after that Requirement's checks 1–9, its latest Review Result must be dependency-bound, its bindings current, its DEPENDS_ON edges exactly the bound direct set and each direct dependency Applied.
- **Selection closure:** every member of each selected Requirement's bound set (direct and transitive) must be in the selection. Otherwise `REQUIREMENT_NOT_ADMISSIBLE` naming each missing `R -> D`; nothing is added and nothing is written. Only DEPENDS_ON closes the selection.
- The existing checks, the duplicate-entity check, human acceptance and explicit scope selection are unchanged. Check 10 runs per Requirement, so a selection that is both stale and duplicated reports the stale Requirement; the closure check runs after the duplicate-entity check; Manifest rows are unchanged; input currentness re-runs admission, so a later dependency change makes a TSA cycle's inputs stale.
- Closure proves that declared dependencies are included, not that every product Requirement was discovered.

## 11. Rework

The Rework Brief gains category `EXISTING_DEPENDENCY` (letter `E`): an existing DEPENDS_ON edge the Review did not confirm, carrying its kind, exact target, outcome, severity and reason. A REWORK_CLAIM that re-raises it keeps the relation identity, as for RELATION_PROPOSAL. A product-question item blocks under §8. The next Review recomputes current dependency evidence; earlier feedback is never normative authority. No automatic decision is added.

## 12. Historical compatibility

- Process and Review Results 0.1–0.5 stay readable and are never rewritten or migrated.
- Pre-0.6 Review evidence is refused at Ready (`DEPENDENCY_EVIDENCE_REQUIRED`), Apply (same) and TSA admission, and is not admissible as a dependency, whatever its WHAT status. Requalification is a new Process and Review.
- A Requirement whose existing DEPENDS_ON targets hold only pre-0.6 evidence cannot be reviewed until those targets are requalified (`DEPENDENCY_EVIDENCE_INVALID`).
- Historical Applied Requirements and their relations stay untouched. TSAP1 is historical, is not migrated and is not required to pass these rules; its saved FR-0124 normalization is used offline as test evidence only.

## 13. Refusal codes

| Code | Raised by |
|---|---|
| `DEPENDENCY_EVIDENCE_INVALID` (new) | Review: an existing dependency is not admissible authority |
| `DEPENDENCY_CYCLE` (new) | Review, Ready, Apply |
| `DEPENDENCY_EVIDENCE_REQUIRED` (new) | Ready, Apply: pre-0.6 evidence |
| `DEPENDENCY_EVIDENCE_STALE` (new) | Ready, Apply |
| `DEPENDENCY_NOT_APPLIED` (new) | Apply |
| `FIBERY_READ_FAILED` (existing) | any stage, when a relation or dependency read fails or is incomplete (§3.1); TSA admission uses `CycleResultCode.FIBERY_READ_FAILED` |
| `INVALID_MODEL_OUTPUT` (existing) | Review: `dependency_verifications` breaks §4, or an unconfirmable proposal is confirmed |
| `REQUIREMENT_NOT_ADMISSIBLE` (existing) | TSA check 10 and closure |

All are deterministic, write nothing beyond what was already durable, and are never retried automatically.

## 14. Non-goals and limits

**Non-goals:** WI-5 autonomy policy, WI-6 automatic decisions, automatic rework or approval, Applied revision, graph-wide reprocessing, impact propagation, new relation types, grouping entities, databases, States or agents, Delivery Planning.

**Limits:**
- Whether a dependency is semantically necessary, a definition genuinely answers a question, or rules contradict is a model judgement; code enforces structure, binding, currentness, cycles and closure. The Uppercase tests therefore prove the contract (what each stage is given and how evidence is judged), not a model's semantic conclusions.
- Order of authority: a dependency must be reviewed (0.6, CLEAR) before its dependent can be reviewed, and Applied before its dependent can be Applied.
- Every check reads each member afresh (a handful of reads per member, at most 100 members); nothing is cached across a mutation.
- A consistent hand edit of a Review Result and every artifact it binds is not detectable.
- §3.1 rests on the live-verified collection shape. Not yet probed live: that a Requirement with no relations returns `{"fibery/id": []}` for both Depends On and Affects in this query (if Fibery returned anything else, the read refuses visibly rather than reading "none"), and whether the collection sub-select ever truncates a large collection.
- Not live-verified: the 0.6 payload and the TSA path's new use of the existing `requirement_relations` read have not been compared against live Fibery, so they are not frozen under the project rule.
