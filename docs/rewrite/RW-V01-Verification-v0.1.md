# RW-V01 — Independent Verification v0.1

**Work item:** `RW-V01 — Preserve old AMR corpus as baseline evidence`  
**Verdict:** VERIFIED  
**Date:** 2026-09-12  
**Baseline evidence:** `docs/rewrite/RW-V01-AMR-Baseline-v0.1.md`  
**Evidence commit:** `307a95ae10189e0a9a5fe4b6e329f9f014303776`

## Review

The baseline was collected from live Fibery using read-only queries only.

The two required historical RAW inputs are reproducibly identified by Requirement ID, entity id, public id, Project identity and Source Fingerprint:

- `AMR-RAW-0053` — fingerprint `99b622c3f1198282f134bc0b1c8df678677e7856286e6d8e4f761dbae8ccb871`;
- `AMR-RAW-0077` — fingerprint `a6c160dd1725c5b83caa3fe766028b78c274dd20fff91fc0f27c0912243cfc76`.

The live `Produces` relations contained exactly the historical corpus required by the frozen plan:

```text
AMR-RAW-0053 -> 19 Standard Requirements
AMR-RAW-0077 ->  9 Standard Requirements
```

All 28 produced entities were observed as `Type = Standard`, `State = Applied`, and are listed individually in the baseline with stable Requirement IDs and entity ids.

No Fibery mutation tool was used while creating or verifying this baseline. Neither RAW nor any old Standard Requirement was created, edited, transitioned or deleted.

The baseline explicitly rejects candidate-count optimization. It freezes semantic comparison criteria covering Requirement meaning, implementation independence/leakage, observable acceptance, source-mandated constraints, open questions, fragmentation, independent obligations, Architecture headroom, and Process/Review quality.

## Acceptance criteria

1. **PASS — baseline inputs are reproducibly identifiable.** Stable ids, fingerprints, project identity and exact old corpus membership are recorded.
2. **PASS — no live AMR Standard Requirement was deleted or rewritten.** Collection and review were read-only.
3. **PASS — comparison criteria are semantic, not "produce fewer Requirements".** `19 + 9` is explicitly historical baseline evidence only.

## Final decision

`RW-V01 = VERIFIED`.

The old AMR corpus must remain untouched until corrected dogfood is independently verified and a later RW-V03 cleanup set receives explicit human approval.
