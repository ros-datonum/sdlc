# RW-V02 — Independent Verification v0.1

**Work item:** `RW-V02 — Re-run the two AMR RAW sources through corrected Requirement pipeline`  
**Verdict:** VERIFIED  
**Date:** 2026-09-12  
**Baseline:** `c65314fee9796a5579261ba1db0b6fc5a7216286`  
**Dogfood evidence commit:** `027b06537082dae8dad30e36036dd37415abf487`  
**Plan evidence/status commit:** `37ecddad0dc3232ae510717c46902aae2d780d0c`

## Independent review

The branch was compared with the corrected RW-V02 baseline. It changes only:

- `docs/rewrite/RW-V02-AMR-Corrected-Dogfood-v0.1.md`;
- the allowed RW-V02 execution/status fields in the moving rewrite plan.

No production code and no test code changed.

The dogfood evidence was read in full. The retained live reference Project was then independently inspected rather than relying on the system-under-test report. Every one of the 21 corrected Standard Requirements was reviewed from its live normative Root Document together with its Process Result iteration 1 and Review Result iteration 1. The independent review used `Standard-Requirement-Abstraction-v0.2.md` as the classification authority, not the model Review verdict.

A structured live Fibery query independently confirmed the retained reference corpus currently contains exactly 23 Requirements:

```text
2 Raw Requirements   -> Review / Succeeded
21 Standard Requirements -> Ready / Succeeded
0 Applied corrected Standards
0 Failed corrected Requirements
```

The two copied RAW fingerprints are the v0.2 reference-copy fingerprints recorded by the dogfood evidence, while the historical AMR RAW entities retain their original V01 provenance fingerprints.

A separate live query independently confirmed all 30 protected historical AMR Requirements still have the same stable entity ids, Requirement IDs, Types and States frozen by RW-V01:

```text
2 Raw Requirements      -> Review
28 Standard Requirements -> Applied
```

Every protected entity's current `fibery/modification-date` predates the September 12 RW-V02 dogfood (all are September 8–10), independently proving the dogfood did not mutate those protected entities. The historical RAW Source Fingerprint fields also still equal the V01 baseline values.

## Semantic review of the corrected corpus

### Source A — `AMR-RAW-0053`

The 15 corrected candidates preserve the meaningful source obligations while materially reducing implementation-oriented fragmentation from the historical 19-item decomposition.

The independent review found:

- provider-neutral execution remains an outcome/capability rather than an implementation design;
- source-mandated `argv`-only / never-shell safety remains a valid Constraint rather than being discarded as "technical";
- source-mandated in-process/configuration-driven resource controls and the v1 no-external-coordination boundary remain valid Constraints;
- timeout, latency, request-size, concurrency, failure normalization, portability, credential handling, telemetry, temporary-file safety and health-check quota obligations remain independently meaningful;
- unresolved source questions such as grandchild-process termination, concurrency scope and quota boundaries remain open rather than being invented away;
- downstream implementation choices remain available to Technical Solution Architecture.

`ZZV02AMR-CON-0093` contains the phrase "the adapter's derivation". Process and Review correctly surface this as `IMPLEMENTATION_LEAKAGE`, but Review severity is `INFO`: the noun is extraneous wording, the obligation remains completely intelligible without it, and the Requirement does not constrain a component boundary or choose an implementation mechanism. This is a non-blocking lexical leak, not an abstraction blocker.

`ZZV02AMR-CON-0105` is the weakest structural candidate. It combines the default-environment constraint with source-mandated verification coverage and Review confirms `NON_ATOMIC` at `INFO`. Process proposed `IMPLEMENTATION_LEAKAGE`, but independent Review rejected that finding because the verification obligation is explicitly source-mandated and the Requirement does not prescribe fixtures, mocks, framework internals or concrete test commands. This is permitted by the abstraction contract's source-mandated mechanism exception and its "not a standalone Requirement by default" treatment of test coverage. It is therefore a non-blocking structural weakness rather than a confirmed leakage blocker.

`ZZV02AMR-CON-0106` contains slight wording strengthening around successful normalization, but Review treats it as non-blocking and the source obligation remains intact.

### Source B — `AMR-RAW-0077`

The 6 corrected candidates correctly use the explicit external-contract exception. The RAW source exists specifically to define the externally visible ModelRequest/ModelResponse contract, so exact field-level contract requirements are valid Requirements rather than implementation leakage.

The independent review confirmed:

- the ModelRequest and ModelResponse external contracts remain provider-neutral;
- status taxonomy and output-mode behavior remain externally observable obligations;
- `role` remains opaque telemetry with no execution semantics;
- credential-free/provider-neutral contract constraints remain intact;
- unresolved questions about `resolved_model`, usage/execution shapes and taxonomy extensibility remain visible rather than being invented away;
- Architecture still owns implementation representation and internal execution choices.

`ZZV02AMR-FR-0110` uses "exactly" for the three v1 output modes, which could be read as closing future extensibility. Given the source's explicit v1 mode set, this is not a blocker for the current contract, but it is recorded as a non-blocking wording concern.

## Review verdict distribution

The system Review artifacts report:

```text
NEEDS_WORK = 17
PASS       = 4
```

This distribution is not an RW-V02 failure. Independent inspection confirmed that the NEEDS_WORK verdicts overwhelmingly expose genuine source gaps or unresolved decisions while leaving them unresolved. That is the desired behavior: Review evidence is not authority to invent missing product intent.

The four PASS candidates are the cases with no material unresolved source gap at the Requirement boundary. No model verdict was used as the independent RW-V02 verdict.

## Acceptance criteria

1. **PASS — no confirmed implementation-leakage blocker remains.** The one confirmed lexical leakage in `CON-0093` is INFO-level wording and does not constrain HOW. `CON-0105`'s source-mandated verification clause is allowed by the frozen exception and its leakage finding was correctly rejected.
2. **PASS — no source-mandated obligation was lost merely because it is technical.** The corrected corpus retains mandated argv/no-shell safety, in-process v1 controls, credential constraints, exact external-contract fields/modes/status semantics and required verification obligations where the source itself mandates them.
3. **PASS — every corrected candidate has an explainable Requirement boundary without ad-hoc rules.** Each candidate can be classified directly under the frozen WHAT/HOW contract, source-mandated constraint exception or explicit external-contract exception.
4. **PASS — Technical Solution Architecture retains meaningful HOW decisions.** Internal components, algorithms, fixture/test mechanics, runtime structure and implementation decomposition are not made canonical product Requirements by the corrected corpus.
5. **PASS — lifecycle used the verified normal state-driven path.** The only human lifecycle action per copied RAW was `Draft -> Process`; the runner automatically executed RAW processing, candidate progression, Standard Process and Standard Review, and stopped every candidate at Ready. The evidence reports `23 SUCCEEDED`, `21 HANDED_OFF`, `0 FAILED`; no manual process/normalize/review command was needed.
6. **PASS — dogfood exposes no new blocking lifecycle defect.** Both copied RAWs finished `Review/Succeeded`; all 21 corrected Standards finished `Ready/Succeeded`; no candidate was automatically approved, applied or reworked.

## Source fidelity and fingerprint note

The v0.2 source-equivalence correction is accepted for this dogfood. Historical Source Fingerprints remain provenance identifiers for the original ingest. Fibery re-serializes Markdown, so a reconstructed reference copy may have a different current fingerprint while still proving semantic source equivalence through:

- exact historical entity/provenance fingerprint;
- exact historical Root Document;
- successful current transport parsing;
- `content_equivalent(...) == True`;
- `canonical_markdown(...)` equality;
- no semantic source edits.

No fingerprint algorithm or persisted historical fingerprint was changed under RW-V02. Any future change to make fingerprints stable across Fibery write/read round trips requires an explicit versioning/migration decision and is not a blocker for this dogfood verdict.

## Scope and safety

- The historical AMR Project and all 30 protected Requirements remain unchanged.
- No corrected candidate was Applied.
- No `Ready -> Process` rework occurred.
- No manual internal worker command was used for the normal path.
- The runner was stopped after dogfood and the workspace had zero eligible machine routes afterwards.
- The reference Project `ZZ RW-V02 AMR Corrected Dogfood 0912` / `ZZV02AMR` is intentionally retained for RW-V03 comparison.
- No production code or test code changed.
- Repository gates reported: `uv sync --locked` OK; Ruff clean; `pytest -q` `2271 passed`.

## Non-blocking follow-up observations

These do not change the verdict but should remain visible during RW-V03/final documentation review:

1. `CON-0093` has one implementation-flavored noun (`adapter`) that can be removed on a future explicit rework without changing the obligation.
2. `CON-0105` is non-atomic and has a duplicated Requirement-ID/title prefix in its rendered Root heading; the semantic obligation remains valid, but it is the weakest corrected candidate structurally.
3. `CON-0106` slightly strengthens wording around successful-result normalization.
4. `FR-0110`'s "exactly" wording may unnecessarily imply closed future extensibility beyond the source's current v1 scope.

None is a confirmed implementation-leakage blocker under the frozen acceptance criteria.

## Final decision

`RW-V02 = VERIFIED`.

RW-V03 may now prepare the explicit human-reviewed cleanup proposal. **This verification authorizes no deletion.** Old Applied AMR Standards must remain intact until the human reviews and explicitly approves an exact cleanup set under RW-V03.
