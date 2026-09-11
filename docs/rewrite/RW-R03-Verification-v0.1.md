# RW-R03 Verification v0.1

**Work item:** `RW-R03 — Correct Standard Process normalization and analysis`  
**Verdict:** VERIFIED  
**Frozen plan:** `docs/rewrite/SDLC-Rewrite-Plan-v0.2.md` at `d54db975e5cff73a2522598dfb1bc0727f45a523`  
**Implementation commit:** `a4243ba03a99608d591439907aa8d217e78c8c20`  
**Implementation evidence commit:** `82c244b46e41c8cd53f379ec2cb1795fb19c138b`  
**Reviewed on:** 2026-09-11

## Independent review

The implementation was reviewed against the frozen RW-R03 Required Change, Must Preserve, Must Not, and Acceptance Criteria using the actual branch diff and changed files rather than the implementation-agent summary.

### Acceptance Criteria

1. **PASS — implementation leakage becomes an explicit finding instead of being deepened.** `IMPLEMENTATION_LEAKAGE` is a new self finding in the closed `FindingKind`. The Process prompt distinguishes partial HOW leakage from a candidate that is itself Architecture/Task/test/deployment work. For partial leakage it preserves source-established WHAT, omits non-mandated HOW where that can be done without changing intent, and reports the leak; for a pure-HOW candidate it reports the defect without inventing a higher-level Requirement. Focused tests exercise both cases through the real Standard Process boundary.
2. **PASS — valid high-level Requirements remain high-level.** The prompt defines normalization as clarity-preserving expression of the same source-established obligation, explicitly forbids adding technical design merely to make the Requirement more concrete, and focused tests preserve a high-level obligation without adding implementation detail.
3. **PASS — source-mandated constraints remain intact.** The prompt preserves the RW-C01/RW-R02 exception: an exact technical mechanism explicitly mandated by the source is legitimate Requirement content and is not leakage; current implementation, examples, background, existing architecture, and suggestions do not create such authority. The argv/no-shell fixture remains intact without a leakage finding.
4. **PASS — open product decisions are not invented.** Product-level open questions are preserved and unanswered; architecture-only questions are not treated as missing Requirement content. Focused fixtures exercise both cases.
5. **PASS — stale-input, resume, iteration, recovery, and evidence behavior is preserved.** `standard_processor.py`, Process Result serialization/versioning, comparison context, normative-tree machinery, Review implementation, and recovery/concurrency code are unchanged. The reported focused suite includes explicit resume, iteration, state-machine, concurrent-edit protection, Process→Review chain, empty-result recovery, normative tree, fingerprints, and comparison context.
6. **PASS — WHAT→HOW leakage has focused regression coverage.** The new Standard Process abstraction suite covers valid high-level Requirements, partial leakage, pure-HOW candidates, source-mandated constraints, acceptance-vs-test mechanics, product-vs-architecture questions, atomicity, testability, and peer/relation preservation. The finding-reference suite pins `IMPLEMENTATION_LEAKAGE` as a self finding with no `requirement_id` and proves a Process Result carrying it remains consumable by Review.

## Scope and preservation review

- `IMPLEMENTATION_LEAKAGE` is a finding about this Requirement and therefore carries no `requirement_id`; the existing strict self-vs-cross parser rule remains unchanged.
- Process assigns no severity; Review remains responsible for severity/verdict.
- No autonomous split, merge, or Requirement creation was introduced.
- No product intent is rewritten merely to make implementation easier.
- Missing architecture decisions are not converted into product Requirements.
- Completeness, atomicity, and testability are explicitly evaluated at Requirement level rather than against missing downstream design.
- Relation proposals remain non-canonical and peer Requirements remain non-mutating comparison evidence.
- Unknown-field rejection, deterministic rendering, missing-information semantics, single-line title protection, and reserved H1/H2 protection remain unchanged.
- No semantic keyword/regex classifier was introduced; WHAT/HOW judgement remains model-backed.
- `review_prompt.py` changed only to keep the shared finding vocabulary mechanically consistent by listing `IMPLEMENTATION_LEAKAGE` among self findings. No RW-R04 abstraction instructions, verdict logic, severity logic, or reviewer mutation behavior were added.
- Fibery schema/live state, lifecycle ownership, Processing Status, worker routing, bootstrap, model runtime/authentication, Ready/Apply, A1–A11 hardening, and AMR dogfood state were not changed.

## Test evidence assessment

The new tests use bounded fake-model outputs through the real Standard Process stage. This is appropriate for RW-R03 unit/regression verification: they prove the Process prompt encodes the frozen semantic rules, the closed structured contract carries the new finding correctly, and deterministic persistence rewrites exactly the validated normalization without splitting, multiplying, or mutating peer Requirements. They do **not** prove that a live reasoning model will always judge WHAT/HOW leakage correctly. That semantic-quality question remains for the later corrected-pipeline dogfood/verification work, notably RW-V02.

Reported execution evidence:

- focused suites: `751 passed`;
- full gate: `uv sync --locked`, `ruff check`, `ruff format --check`, and `pytest -q` green with `1635 passed`;
- red check: 14 of 17 new abstraction tests and all four new leakage finding-reference tests fail against the pre-RW-R03 implementation, while preservation checks intentionally pass.

The repository has no independent CI status for this implementation, so the command results above are implementation-run evidence reviewed alongside the code/test diff, not independently re-executed CI evidence.

## Result

`RW-R03` satisfies the frozen contract at implementation commit `a4243ba03a99608d591439907aa8d217e78c8c20`.

This reviewer record satisfies the dependency gate for `RW-R04`. The moving plan may continue to carry implementation-agent status metadata until a later metadata reconciliation; this reviewer-owned record is the independent verification authority for this work item.
