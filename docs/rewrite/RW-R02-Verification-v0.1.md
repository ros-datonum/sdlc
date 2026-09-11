# RW-R02 Verification v0.1

**Work item:** `RW-R02 — Correct RAW decomposition contract`  
**Verdict:** VERIFIED  
**Frozen plan:** `docs/rewrite/SDLC-Rewrite-Plan-v0.2.md` at `d54db975e5cff73a2522598dfb1bc0727f45a523`  
**Implementation commit:** `ce76831b8196b73b4413faecdfa8b6c21ec6f402`  
**Implementation evidence commit:** `90282579e8868ec98635aa65159d25a21a338968`  
**Reviewed on:** 2026-09-11

## Independent review

The implementation was reviewed against the frozen RW-R02 Required Change, Must Preserve, Must Not, and Acceptance Criteria, using the actual branch diff rather than the implementation-agent summary.

### Acceptance Criteria

1. **PASS — one capability plus implementation details does not fragment.** The RAW prompt explicitly defines one candidate as one independently meaningful product/system obligation, rejects sentence/field/parameter/implementation-decision atomicity, states that technical facets of one proposed implementation are not candidates, and encodes no target candidate count. Focused processor fixtures preserve the RAW source and pass one conforming Requirement-level candidate through without deterministic splitting.
2. **PASS — independent obligations may remain separate.** Prompt rules explicitly forbid merging independent obligations merely because they share a paragraph, section, or implementation; focused fixtures exercise two separate obligations and provenance.
3. **PASS — source-mandated technical constraints are preserved.** The prompt distinguishes explicitly mandated mechanisms from examples/current implementation/background/suggestions, permits a mandated mechanism to remain a Constraint, and preserves uncertainty as an Open Question rather than silently promoting it.
4. **PASS — unresolved source decisions remain open.** Prompt rules prohibit inventing answers, preserve product-level open questions, and leave architecture-only questions downstream. Missing sections continue to use deterministic schema text.
5. **PASS — comparison findings remain observational and non-mutating.** The four existing finding kinds, structured result contract, peer context, and processor mutation boundary are unchanged. Focused and existing comparison tests exercise non-Applied peer findings without modifying peer content or relations.
6. **PASS — RAW source binding/recovery semantics are unchanged.** The implementation changes only `raw_prompt.py` under `src/`; `raw_processing.py`, `raw_processor.py`, Processing Result, comparison context, recovery, empty-result recovery, cross-stage protection, and the per-RAW execution guard are unchanged. The relevant existing suites are reported green.
7. **PASS — explicit anti-implementation-leakage rule exists.** The prompt names the WHAT/HOW boundary and explicitly rejects standalone candidates for implementation components, algorithms/sequences, topology, trigger/storage/serialization/deployment mechanisms, test mechanics, implementation-specific edge cases, and fields without independent product/system meaning.

## Scope and preservation review

- No expected candidate count was introduced.
- No one-candidate-per-paragraph/field rule was introduced.
- Open product questions are not solved.
- Architecture/test mechanics are not promoted merely to make Requirements testable.
- Zero/one/many candidates remain valid.
- Functional / Non-functional / Constraint categories remain unchanged.
- Structured output shape remains closed and bounded.
- No Fibery schema/live state, lifecycle, state-transition ownership, model runtime/auth, Ready/Apply behavior, or AMR corpus was changed.
- `standard_prompt.py` and `review_prompt.py` are unchanged; RW-R03/RW-R04 remain separate work items.

## Test evidence assessment

The new decomposition tests use the real processor with bounded fake-model output. This is appropriate for RW-R02 unit/regression verification: they prove the prompt contains the frozen semantic rules and that deterministic code preserves the model's validated decomposition without splitting, merging, counting, completing, or mutating it. They do **not** prove that a live reasoning model will always follow those rules. That live semantic-quality question remains for the later corrected-pipeline dogfood/verification work (notably RW-V02) and is not silently treated as proven here.

Reported execution evidence:

- targeted suites: `630 passed`;
- full gate: `uv sync --locked`, `ruff check`, `ruff format --check`, and `pytest -q` green with `1612 passed`;
- red check: 15 of 17 new tests fail against the pre-RW-R02 source, while the two preservation tests intentionally pass on both trees.

The repository has no independent CI status for this commit, so the command results above are implementation-run evidence reviewed alongside the code/test diff, not independently re-executed CI evidence.

## Result

`RW-R02` satisfies the frozen contract at implementation commit `ce76831b8196b73b4413faecdfa8b6c21ec6f402`.

This reviewer record satisfies the dependency gate for `RW-R03`. The moving plan may continue to carry implementation-agent status metadata until a later metadata reconciliation; this reviewer-owned record is the independent verification authority for this work item.
