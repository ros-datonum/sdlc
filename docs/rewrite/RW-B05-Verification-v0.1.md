# RW-B05 — Independent Verification v0.1

**Work item:** `RW-B05 — Bootstrap end-to-end test on disposable project`  
**Verdict:** VERIFIED  
**Date:** 2026-09-12  
**Baseline:** `99263693322d43362b7bb8f24d8e046de87e18cc`  
**Live evidence commit:** `9ab69b36fe859feadde4fa4ad3cf38b14c6f0103`  
**Plan evidence/status commit:** `d0655c1c69be65dfebd30b3d9356c9503a98b9f3`

## Independent review

The branch was compared against the B05 baseline. It changes only:

- `docs/rewrite/RW-B05-Live-Bootstrap-Evidence-v0.1.md`;
- the allowed RW-B05 implementation/status fields in the moving rewrite plan.

No production code or test code changed.

The live evidence was read in full and cross-checked against the verified B01–B04 contracts. The probe used a disposable Project and RAW Requirement only, exercised the real user-facing bootstrap CLI, verified the exact managed local tree and descriptor/context/guidance contracts, verified one live Project and one live RAW in `Raw + Draft`, reran the exact command without duplicates, exercised a safe local conflict through the real CLI, and removed the disposable live and local state afterwards.

Independent live cleanup checks after the reported cleanup found:

```text
Project Name/Code match for the disposable identity: 0 rows
RAW Source Fingerprint match for the disposable source: 0 rows
```

The current live schema also still exposes Requirement `Processing Status` defaulting to `Not Processed`; no B05 lifecycle mutation or worker execution was required or performed.

## Acceptance criteria

1. **PASS — one setup action creates usable local project structure.** The real CLI returned `PROJECT_BOOTSTRAPPED` and created exactly the B01-managed consumer artifacts.
2. **PASS — descriptor/context match frozen contract.** B03 parsing and B02 compatibility passed; context bytes matched the supplied artifact.
3. **PASS — Fibery Project exists exactly once.** The probe used bounded Name/Code queries and both mapped to one disposable Project.
4. **PASS — initial RAW Requirement exists exactly once.** The Project + Source Fingerprint query returned one disposable RAW, with its one Root Document.
5. **PASS — rerun is safe.** The same CLI command returned `PROJECT_ALREADY_BOOTSTRAPPED`; local digests and live entity/document identities remained unchanged and counts stayed one.
6. **PASS — user-global model/auth/edit settings are not overwritten.** Claude and Codex global config hashes were unchanged before/after; no global file was written by bootstrap.
7. **PASS — no credentials written.** The live token value and credential-like literals were absent from every managed consumer file.
8. **PASS — failure is truthful and non-destructive.** A conflicting context file produced `BOOTSTRAP_CONFLICT`, preserved the foreign bytes, created no managed files in that target, and changed no live Project/Requirement state.
9. **PASS — no Requirement processing begins without authority.** The disposable RAW remained `Raw + Draft + Not Processed`, with no Standard candidate and no Processing Result after the observation interval.

## Scope and safety

- No production Project or Requirement was used.
- No AMR entity was touched.
- No model ran.
- No RAW processor or worker runner handled the probe Requirement.
- No `Draft -> Process` transition occurred.
- No production/test code changed.
- No user-global configuration was modified.
- Cleanup used exact recorded disposable entity ids only.
- Repository regression gates reported: dedicated bootstrap `79 passed`; full suite `2271 passed`; Ruff clean.

The persistent local `.env` still has an empty `FIBERY_SPACE_ID`, so the probe used a process-scoped Space id discovered read-only. This is an already-known operator configuration gap, not a B05 product/code defect, and does not alter the verification verdict.

## Final decision

`RW-B05 = VERIFIED`.

With RW-B01 through RW-B05 independently verified, **Block D — Project Bootstrap is complete**.
