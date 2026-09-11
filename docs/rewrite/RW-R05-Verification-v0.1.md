# RW-R05 Verification v0.1

**Work item:** `RW-R05 — Build Requirement abstraction regression corpus`  
**Verdict:** VERIFIED  
**Frozen plan:** `docs/rewrite/SDLC-Rewrite-Plan-v0.2.md` at `d54db975e5cff73a2522598dfb1bc0727f45a523`  
**Implementation commit:** `4dfa8d1450b9560c79924c1d8ee945192c805d01`  
**Implementation evidence commit:** `a980328d019432195849ed7431926599442705ff`  
**Reviewed on:** 2026-09-11

## Independent review

The implementation and the independent-review correction were inspected against the frozen RW-R05 Required Change, Must Preserve, Must Not, and Acceptance Criteria using the actual Git diff and corpus code rather than the implementation-agent summary.

### Acceptance Criteria

1. **PASS — all ten frozen abstraction classes have explicit expected properties.** The corpus contains exactly the ten required synthetic classes. Each case declares source-established obligation concepts, category, and at least one abstraction-boundary property. Exact per-case cardinality is used only where the synthetic source semantics make it unambiguous; there is no global candidate-count target.
2. **PASS — promoted implementation detail is detected semantically.** Negative controls cover a watchdog promoted to a Requirement, a Redis suggestion promoted to a constraint, test mechanics promoted to Acceptance, and an internal field promoted to its own Requirement. These outputs are structurally valid and pass the real stage before the corpus reports named semantic violations.
3. **PASS — source-mandated constraints cannot silently disappear.** The corpus requires the exact `argv` / `shell` mandate where identity is itself normative and catches mandate loss at RAW decomposition and Standard Process, plus an unwarranted Review confirmation of leakage against the mandate.
4. **PASS — unresolved product questions cannot be silently answered.** The corpus preserves the open decision and catches both closure and invented answers across multiple equivalent wordings, including `override` and `bypass` forms.
5. **PASS — the corpus is reusable by an independent reviewer for future prompt/model changes.** Case data and semantic checks are separate from stage runners and import no prompt. A reviewer can parse a new structured output and apply the case checks directly. Reference outputs are examples rather than golden prose.

## Independent-review correction

The first RW-R05 implementation represented semantic concepts as single literal substrings. Independent review classified this as `CHANGES_REQUIRED` because a valid paraphrase such as `configured maximum duration` / `deadline-exceeded outcome` could fail a case whose markers were `time limit` / `timeout`, contradicting the frozen rule that semantic properties rather than exact model prose are the pass condition.

Correction `4dfa8d1450b9560c79924c1d8ee945192c805d01` resolves this by introducing a bounded test-only `Concept` representation:

- each Concept contains a case-specific list of equivalent expressions;
- a Concept is present when any configured equivalent is present;
- an Obligation may require multiple Concepts and all required Concepts must be represented;
- obligation recognition, observable acceptance, open product questions, invented answers, and architecture questions use Concepts;
- exact string identity remains where identity is the property, notably source-mandated mechanisms and forbidden implementation/test identifiers.

The corpus documentation now accurately states that this is a deterministic case-specific semantic proxy, not a general NLP classifier. A novel valid paraphrase outside configured equivalents requires reviewer judgement / fixture-equivalence refinement and is not itself evidence of a product defect.

Marker-free positive controls confirm:

- C01 passes using `configured maximum duration` and `deadline-exceeded outcome` with neither `time limit` nor `timeout` present;
- C06 preserves the unresolved decision using `bypass` with no `override` marker;
- C05 preserves observable acceptance using `next cycle` / `succeeded or failed` with the original acceptance markers absent;
- C07 still detects a reworded architecture question (`enforcement mechanism`).

The pre-correction matcher fails the first three paraphrases while the corrected matcher accepts them.

## Scope and preservation review

- Implementation/correction changes only `tests/abstraction_corpus.py` and `tests/test_abstraction_corpus.py`; the moving plan contains implementation metadata only.
- No file under `src/` or `config/` changed.
- No production prompt, parser, processor, reviewer, persistence contract, lifecycle behavior, Fibery schema/state, model runtime, or authentication changed.
- No live AMR state, live Fibery workspace, or live model is used.
- Historical AMR candidate counts 19 and 9 are not encoded as desired output.
- Existing RW-R01 through RW-R04 regression suites remain unchanged.
- Negative controls remain effective after the semantic-proxy correction.

## Test evidence assessment

Reported implementation evidence after correction:

- dedicated corpus: `57 passed`;
- RW-R01 through RW-R04 abstraction/stage suites plus corpus: `447 passed`;
- full gate: `uv sync --locked`, `ruff check`, `ruff format --check`, and `pytest -q` green with `1712 passed`.

The repository has no independent CI result for this commit, so these command results are implementation-run evidence reviewed alongside the actual test/corpus diff rather than independently re-executed CI evidence.

## Result

`RW-R05` satisfies the frozen contract at implementation commit `4dfa8d1450b9560c79924c1d8ee945192c805d01`.

Block B — Requirement abstraction rewrite is now independently verified through RW-R05. This reviewer record satisfies the dependency gate for the next frozen execution block. The moving plan may continue to carry implementation-agent status metadata until later metadata reconciliation; this reviewer-owned record is the independent verification authority for RW-R05.
