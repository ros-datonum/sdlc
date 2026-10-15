# TSA-C01 — I14 Live-Model Evidence v0.1

**Status:** EVIDENCE RECORDED, UNVERIFIED (awaiting independent review).
**Work item:** I14 — controlled live-model probes (implementation spec v0.3 §17,
§18). M-class evidence only.
**Repository:** baseline `59c67968acdf9aefea1fe02ab9d3b8790ba4c9b5`; the probe
runner and this evidence are added on top of it, with no production change.
**Run window (UTC):** 2026-10-15T19:17:19Z to 2026-10-15T19:28:55Z.
**Environment:** synthetic only. Every Project, Requirement, Manifest, Process,
Review and Architecture Document lived in the in-memory Fibery fakes of the test
suite. No Fibery API, provider API, SDK, API key or OpenRouter was used, and no
real or private data was involved.

This document records measurements, not a target. A partially unsuccessful probe
is valid evidence and is reported as such.

## 1. What was run

`scripts/tsa_i14_probe.py` runs, per scenario:

1. the real I05 `start_input_manifest` over synthetic Applied Requirements, with
   explicit acceptance and UX `NOT_APPLICABLE`;
2. the real I07 `run_architect_stage`, with its production prompt builder,
   closed-contract validator, v0.4 rule S/X checks, I06 renderer, traceability
   and persist-then-apply;
3. only when step 2 applied a valid output, the real I08 `run_reviewer_stage`,
   with its production prompt builder, closed-contract validator, exactly-once
   claim coverage and derived status.

The model boundary is the existing `LocalCliModelRuntime`, selected by
`select_runtime` for the configured roles. A thin recorder wraps it to keep each
prompt, context and raw response; it does not alter, clean or retry anything.
Nothing in `src/` was changed.

## 2. Runtime and authentication

| Role | Runtime | Invocation mode | Model | Preflight (the runtime's own sanitized summary) |
|---|---|---|---|---|
| `tsa_architect` | `claude` | `print` | local CLI default model (none configured) | `claude: logged in via claude.ai (firstParty)` |
| `tsa_reviewer` | `claude` | `print` | local CLI default model (none configured) | `claude: logged in via claude.ai (firstParty)` |

Claude Code CLI version: `2.1.300 (Claude Code)`. The runtime returned
`model = None` for every response, so the exact model identity behind the CLI
default is **not known** from SDLC's side. Codex was not used (its execution
stays blocked by policy). No authentication output, token or environment value
was recorded.

## 3. Predeclaration and integrity

All four scenarios are defined in the runner. Before any model call, an offline
dry run admitted every fixture through real I05 and assembled the real Architect
prompts, with zero inference calls. Its output is committed as
`TSA-C01-I14-evidence/dry-run-*.json` (started 2026-10-15T19:16:52Z).

| Check | Result |
|---|---|
| Runner sha256 recorded by the dry run and by the live run | identical: `23a511b3fe3f37ed16dd8b77050a64b9f5b143c911300197a1e888b7f22bb159` |
| Live Manifest digests, Requirement fingerprints, Architect prompt and context hashes vs the dry run | identical for S1–S4 |
| Committed runner | `a750d8dfea46ac1189236c9051037ea8b19bb1d8dd79ec14b1d754110b4db8ec`; differs from the executed runner only by lint and format changes, recorded in `runner-as-executed-to-committed.diff`, whose headers use the neutral labels `a/tsa_i14_probe.as-executed.py` and `b/scripts/tsa_i14_probe.py`. Reverse-applying it to the committed runner reconstructs the executed runner's sha256 exactly. A fresh dry run with it reproduces identical fixtures, Manifests and Architect prompt/context hashes. |

Every scenario was run exactly once. No call was retried and no response was
regenerated.

## 4. Scenarios and fixture identities

Full Requirement texts are in `live-S*.json` (`requirements[].root_document`).

| Scenario | Purpose | Rows | Requirements (root document fingerprint) | Manifest digest |
|---|---|---|---|---|
| S1 | coherent event intake service | 1-M, 24-M | `SDLC-FR-0101` `9aa948cd…4a0b`, `SDLC-FR-0102` `e0336aa1…233a`, `SDLC-FR-0103` `4b1e33ba…2c6f` | `a94e53b0eea6…f580` |
| S2 | contradictory retention, same records, no priority | 17-M | `SDLC-FR-0201` `e3ca5a37…cde4`, `SDLC-FR-0202` `fcb9d2b0…bc88` | `9f450e40103e…9f59` |
| S3 | unresolved product decision: who may export | 30-M | `SDLC-FR-0301` `d71c6d84…fe4b`, `SDLC-FR-0302` `0008de84…9989` | `6f3f8d30f12f…4d03` |
| S4 | coherent but delivery-heavy (migration, replay, rate limit) | 36-M, 25-M | `SDLC-FR-0401` `bda7cc9a…0fe1`, `SDLC-FR-0402` `8aefbb4e…bdd6`, `SDLC-FR-0403` `26957a94…253b` | `364ad080245f…0a7d` |

**Fixture flaw, recorded honestly.** S1 was declared as having no contradictory
WHAT, but it carries an unintended tension. `SDLC-FR-0103` defines a `REJECTED`
status and an audit entry for every rejection, while `SDLC-FR-0101` and
`SDLC-FR-0102` say a rejected submission leaves nothing stored. Both live models
surfaced this independently (§6). S1 is therefore not the clean coherent
baseline it was meant to be. It was not changed after the run.

## 5. Calls and deterministic validation

Budget: at most 10 inference calls. Used: **8** (one Architect and one Reviewer
per scenario; no infrastructure retry was needed). Each call also ran the
runtime's own authentication status check, which is not an inference.

| # | Scenario | Role | Seconds | Response chars | Stage result |
|---|---|---|---|---|---|
| 1 | S1 | Architect | 100.3 | 22528 | `OUTPUT_APPLIED`, Process `a34accdba987…` |
| 2 | S1 | Reviewer | 109.7 | 13522 | Review recorded, derived `REVIEW_BLOCKED_ON_WHAT` |
| 3 | S2 | Architect | 47.9 | 14112 | `OUTPUT_APPLIED`, Process `8e8dd4506a55…` |
| 4 | S2 | Reviewer | 57.3 | 11113 | Review recorded, derived `REVIEW_BLOCKED_ON_WHAT` |
| 5 | S3 | Architect | 67.3 | 18409 | `OUTPUT_APPLIED`, Process `230ad344e861…` |
| 6 | S3 | Reviewer | 59.9 | 10498 | Review recorded, derived `REVIEW_BLOCKED_ON_WHAT` |
| 7 | S4 | Architect | 145.2 | 23416 | `OUTPUT_APPLIED`, Process `58b02859bf26…` |
| 8 | S4 | Reviewer | 107.4 | 17152 | Review recorded, derived `REVIEW_BLOCKED_ON_WHAT` |

Deterministic outcomes, all from the production validators on the raw responses:

- **Architect (I07/I06/I01).** All four responses passed the closed contract
  (no `INVALID_MODEL_OUTPUT`: no unknown or missing key, no code block under rule
  S/X, product questions only for selected Requirements). They also passed I06
  rendering and traceability (one row per selected Requirement, valid anchors,
  no `TRACEABILITY_*` or `SECTION_MANDATORY_EMPTY`). All were persisted as valid
  I01 Process Results, then applied.
- **Reviewer (I08/I01).** All four responses passed the closed contract and the
  exactly-once claim coverage (`coverage_defects` empty: no
  `REVIEW_COVERAGE_INCOMPLETE` or `_DUPLICATE`). They were persisted as valid I01
  Review Results.
- **Derived status.** `REVIEW_BLOCKED_ON_WHAT` in all four, because every
  Reviewer recorded at least one `material_unresolved_what`. Under the frozen
  policy, approval was therefore unavailable in every scenario. No approval was
  attempted: approval is deterministic and model-free and is D-covered by I11 and
  I13.

| Scenario | Claims verified (outcomes) | New findings | Material unresolved WHAT | Architect product questions (material) |
|---|---|---|---|---|
| S1 | 16 (all CONFIRMED) | 6 | 3 | 8 (8) |
| S2 | 6 (CONFIRMED, one UNRESOLVED) | 5 | 2 | 2 (2) |
| S3 | 12 (all CONFIRMED) | 3 | 2 | 5 (2) |
| S4 | 15 (all CONFIRMED) | 6 | 4 | 6 (4) |

## 6. Semantic evaluation

Quotations in italics are verbatim excerpts of the recorded raw responses; an
ellipsis `…` marks omitted text, and nothing is completed or paraphrased inside
quotation marks.

Rubric: PASS / FAIL / INCONCLUSIVE per applicable check, judged by reading the
raw outputs against the synthetic Requirements. A valid JSON response is not
treated as semantically correct, and a Reviewer finding is not treated as
correct unless it was independently checked. "Independently verified" below
means the claim was checked against the exact Architecture text in the evidence
file.

### Architect

| Check | S1 | S2 | S3 | S4 |
|---|---|---|---|---|
| One integrated architecture, not a catalogue | PASS | PASS | PASS | PASS |
| Explicit design trade-offs | PASS | PASS | PASS | PASS |
| No invented product obligation | PASS | PASS | PASS | PASS |
| No answer to an unresolved WHAT | INCONCLUSIVE ¹ | PASS ² | PASS ³ | INCONCLUSIVE ⁴ |
| No Task, Epic, sprint, estimate, assignment or code | PASS | PASS | PASS | PASS ⁴ |
| Design internally correct (independently verified) | FAIL ⁵ | FAIL ⁶ | FAIL ⁷ | FAIL ⁸ |

1. S1, classified by kind (no fixture was changed afterwards):
   - *Observed invention of a product obligation:* none found.
   - *Stated assumption settling a WHAT tension:* *"The phrase "nothing is
     stored" in SDLC-FR-0101 refers to event and status records. The audit entry
     that SDLC-FR-0103 requires for every rejection is still written, with no
     payload."*
   - *Provisional default for a question it also left open:* *"Submission time
     is recorded as the server receipt time, captured once at intake and
     persisted unchanged."*, while its material product question asks *"Is the
     persisted submission time the server receipt time or a time supplied by the
     caller?"*.
   - *Design choice with a WHAT consequence:* the size guard runs before token
     authentication (*"Authentication runs after the size guard so that
     oversized bodies are cut off early."*), which fixes a rejection precedence
     the Requirements leave undefined.
   - *Unresolved product questions:* all 8 recorded as material, including
     *"Is the 64 KB limit 64,000 or 65,536 bytes …"*.
   - *Contradiction independently detected by the Reviewer:* the fixture's own
     tension between "nothing is stored" and the `REJECTED` status and audit
     entry of `SDLC-FR-0103` (⁹).

   Every one of these is visible in the evidence, not silent. Whether the
   assumption, the default and the precedence count as answering a product
   question is contestable, so the check is INCONCLUSIVE.
2. S2: *"Choosing a period would answer a product question, which is outside the
   Architect's authority, so the conflict is raised as a material product
   question."* Both Requirements remain traced, each satisfied only "in
   isolation".
3. S3 invented no export roles: a deny-by-default `Export Authorization Policy`
   whose *"rule set is deliberately left open pending the product decision"*,
   plus a material product question *"Which users or roles are authorized to
   export audit events?"*. The line-oriented export format is labelled a design
   choice, as `SDLC-FR-0301` leaves the format open.
4. S4, two separate points.
   - *Provisional defaults (the INCONCLUSIVE entry):* the rate limiter uses *"a
     sliding window of 100 submissions per second"* while the same component
     says its *"exact window semantics are pending a product question"*, and it
     asks that question as material. It also states *"Replay is enabled only
     after the migration is verified, because SDLC-FR-0401 states the new schema
     is the precondition for replay."*, which derives a sequencing rule from
     `SDLC-FR-0401`'s rationale rather than from `SDLC-FR-0402`. Both are
     disclosed defaults, not hidden answers; whether they amount to implicit
     product decisions cannot be settled from the evidence, so the entry is
     INCONCLUSIVE, not PASS and not a proven violation.
   - *Migration phases (the Task/Epic entry):* the Migration Implications
     section describes eight ordered phases. They are architecture-level cutover
     sequencing gated on metrics, with no tasks, estimates, owners or sprints, so
     they were not judged a violation.
5. S1, independently verified: *"A local durable audit spool is the fallback for
   internal errors that occur when the database itself is unreachable"* versus
   *"It falls back to the local Audit Spool when the database is unreachable"*
   (the spool scope differs). A minor inconsistency.
6. S2, independently verified: *"physical deletion lags the horizon by no more
   than one scheduling interval"* (and an alert on exactly that bound), while
   storage uses whole-partition purge with *"partition size … no larger than the
   enforcement interval"*. A whole partition can be removed only once its newest
   record expires, so the lag can reach one partition width plus one interval.
7. S3, independently verified: timestamps *"come from the database transaction
   clock"*, yet *"a repeated export of a fully past range returns the same
   content"*. A long transaction that commits after an export can add an event
   timestamped inside that range, so the claim does not hold.
8. S4, independently verified: the Applier *"upserts full row after-images into
   the new tables"*, the Backfill *"inserts each into the new tables only if
   absent"*, and the Sequencer assigns live positions *"to each newly created
   event (not to backfilled ones, and not to updates)"*. A pre-boundary event
   updated before the Backfill reaches it is created in the new tables by the
   Applier, receives a live position, and is then skipped by the Backfill. Its
   original replay order is lost, contrary to `SDLC-FR-0402`.

### Reviewer

| Check | S1 | S2 | S3 | S4 |
|---|---|---|---|---|
| Source fidelity of restated Requirements | PASS | PASS | PASS | PASS |
| Real contradiction detected with precise Requirement ids | PASS ⁹ | PASS ¹⁰ | n/a | n/a |
| No silent winner between conflicting Requirements | PASS | PASS | n/a | n/a |
| Independent disagreement, independently verified | PASS ⁵ | PASS ⁶ | PASS ⁷ | PASS ⁸ |
| No invented issue | INCONCLUSIVE ¹¹ | PASS | PASS | PASS |
| No approval or verdict field; no Architecture change | PASS ¹² | PASS ¹² | PASS ¹² | PASS ¹² |
| Task, Epic or invention flagged when present | n/a: none observed | n/a | n/a | n/a: none observed |

9. S1 recorded the unintended fixture tensions as `requirement_contradiction`
   findings naming `SDLC-FR-0101`, `SDLC-FR-0102` and `SDLC-FR-0103`, and
   recorded the "nothing is stored" question as material unresolved WHAT. These
   are true positives against the flawed fixture (§4).
10. S2: a BLOCKING `REQUIREMENT_CONTRADICTION`, *"SDLC-FR-0201 (permanent deletion
    … seven days after receipt) and SDLC-FR-0202 (… retrievable unchanged for at
    least ninety days …) contradict each other for every record aged between
    seven and ninety days"*. It also verified the Architect's risk with both
    acceptance criteria (*"the eighty-day record … must be both unretrievable and
    retrievable"*) and recorded material unresolved WHAT for both Requirements,
    without proposing a resolution.
11. S1's finding that ordering the size guard before authentication *"departs
    from SDLC-FR-0101's explicit authentication error"* is defensible, but the
    Reviewer itself notes the Requirement does not define precedence. Its
    escalation to material WHAT is a judgement call.
12. The Reviewer contract has no verdict field and its output was
    schema-validated. The Reviewer stage writes only its own Review Result; that
    write confinement is D-class (I08/I13) and was not re-measured here.

## 7. M-row coverage

| Row | Line | Category | Evidence |
|---|---|---|---|
| 1 | live Architect + Reviewer on a synthetic cycle | **VERIFIED** (the §17 1-M line) | S1–S4: the real Architect and the real Reviewer ran through the production I07/I08 stages, the Process was persisted and applied, the Review persisted, and deterministic validation succeeded. It does **not** mean a Human Decision APPROVE occurred, that a complete live Fibery lifecycle ran, or that any resulting Architecture was approvable: all four Reviews ended `REVIEW_BLOCKED_ON_WHAT`. Approval is model-free and D-covered (I11, I13). |
| 17 | live Reviewer detects a real contradiction | **VERIFIED** | S2 (¹⁰), with both Requirement ids, BLOCKING, and no winner chosen by the Architect or the Reviewer. S1 adds detection of an unintended fixture tension (⁹). |
| 24 | Architect returns one integrated architecture, not a catalogue | **VERIFIED** | S1–S4, each with one recommended design and stated trade-offs. |
| 25 | Reviewer independently disagrees with a real Architect output | **VERIFIED** | Real defects in real Architect outputs, identified by the real Reviewer and independently verified: S4 (⁸, BLOCKING), S2 (⁶), S3 (⁷), S1 (⁵). |
| 30 | Architect answers a product question instead of HOW; detected | **NOT_DEMONSTRATED** | The planned S3 probe showed adherence: no roles invented, a material product question, deny-by-default. No clear violation was observed, so detection of one was not demonstrated. S1 contains a contestable candidate (¹), which the Reviewer escalated to material WHAT, blocking approval. It is recorded but not counted. |
| 36 | Task, Epic or product invention in allowed prose; detected | **NOT_DEMONSTRATED** | No such invention was observed in S1–S4 (S4's migration phases judged architecture, ⁴), so the detection path was not exercised by a real violation. |

The `D` lines of rows 1, 17 and 30 are I13's and I08's; nothing here
substitutes for them, and no D-class test substitutes for these M lines.

## 8. Observations

1. **Material-WHAT escalation is frequent.** All four live cycles ended at
   `REVIEW_BLOCKED_ON_WHAT`, including coherent S3 and S4. S1's Architect marked
   all 8 of its product questions material, including whether "64 KB" means
   64,000 or 65,536 bytes. Under the frozen policy, approval is then unavailable
   until a human resolves them. This is not a rule violation: questions that are
   genuinely open should block approval. But it means a live cycle may rarely be
   approvable without Requirement clarification. Narrow follow-up, if the human
   wants one: measure "material" calibration on a larger synthetic set before
   changing any prompt wording. A prompt change would need its own approved spec
   delta; I14 does not authorize one.
2. **Real Architect designs carried substantive defects** (⁵–⁸), which the
   Reviewer found. This is the independence the contract asks for. It also means
   an Architect output should not be trusted without review.
3. **`new_findings.kind` casing varies between runs** (`requirement_contradiction`
   versus `REQUIREMENT_CONTRADICTION`). The field is free text in the frozen
   schema, so this is not a defect. A consumer should not match on it
   case-sensitively.
4. **One sample per scenario.** Model output is nondeterministic, and each
   scenario ran once, as the budget required. The results describe these eight
   calls, not a rate.

## 9. Limitations

- **Model identity:** the default model behind Claude Code CLI 2.1.300 was not
  pinned and is not reported by the runtime.
- **Synthetic data only:** results do not transfer automatically to real
  Requirement sets.
- **Rows 30-M and 36-M** remain NOT_DEMONSTRATED. A future probe that induces a
  real violation would be needed to exercise detection. Fabricating a violation
  in an Architect response would not be live-model evidence.
- **This evidence does not establish:** live Fibery lifecycle compatibility,
  Fibery Document payload limits, UX replacement or deletion behaviour, full
  live-cycle correctness, or production readiness. Live gates **I-2** and
  **I-3**, and the F lines of rows 1, 22 and 23, remain **open**.

## 10. Reproduction

```text
uv run python scripts/tsa_i14_probe.py --dry-run --out <dir>   # no inference
uv run python scripts/tsa_i14_probe.py --live --out <dir>      # ≤ 10 calls
```

The live command needs a locally authenticated `claude` CLI and makes real
model calls through `LocalCliModelRuntime`. Its outputs differ run to run. The
committed `live-*.json` files are the exact prompts, contexts and raw responses
of the run reported here.
