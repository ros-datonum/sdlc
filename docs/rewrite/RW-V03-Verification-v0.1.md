# RW-V03 — Independent Verification v0.1

**Work item:** `RW-V03 — Human-reviewed cleanup of obsolete AMR dogfood requirements`  
**Verdict:** VERIFIED  
**Date:** 2026-09-12  
**Frozen plan:** `d54db975e5cff73a2522598dfb1bc0727f45a523`  
**Baseline evidence:** `docs/rewrite/RW-V01-AMR-Baseline-v0.1.md`  
**Corrected dogfood:** `docs/rewrite/RW-V02-AMR-Corrected-Dogfood-v0.1.md`  
**V02 verification:** `docs/rewrite/RW-V02-Verification-v0.1.md`  
**Cleanup classification/proposal:** `docs/rewrite/RW-V03-AMR-Cleanup-Proposal-v0.1.md`  
**Final cleanup decision:** `docs/rewrite/RW-V03-AMR-Cleanup-Decision-v0.2.md`

## Independent review

The old RW-V01 corpus was compared item-by-item against the independently verified corrected V02 corpus. All 28 historical Standards received an explicit semantic cleanup classification:

```text
19 replaced
8 over-decomposed
1 obsolete
```

The human explicitly approved exactly one live deletion:

```text
AMR-CON-0086
8d80e73d-59f0-5d16-afa8-75070a8f35eb
```

The target was re-read before deletion and confirmed to be the expected `ai-model-runner / AMR` Standard Requirement in `Applied`. It was then deleted by exact entity id. Post-delete lookup returns zero rows.

No other historical Requirement was deleted.

The extra `Gate V03-B` introduced in the first cleanup proposal was independently rechecked against the exact frozen RW-V03 work item. The frozen work item does not require a promotion/canonicalization mechanism and explicitly says cleanup must not become implementation of a general Requirement revision/supersession workflow. `RW-V03-AMR-Cleanup-Decision-v0.2.md` therefore correctly supersedes that extra sidecar gate without changing frozen product behavior.

## Live postconditions

Current canonical `ai-model-runner / AMR` corpus:

```text
2 Raw Requirements       -> Review
27 Standard Requirements -> Applied
AMR-CON-0086             -> absent
```

Both original RAW sources remain present.

Current corrected reference corpus:

```text
Project: ZZ RW-V02 AMR Corrected Dogfood 0912 / ZZV02AMR
2 Raw Requirements       -> Review / Succeeded
21 Standard Requirements -> Ready / Succeeded
0 Applied
0 Failed
```

The reference corpus retained its V02 modification dates through V03 cleanup and was not mutated.

Fibery activity history shows that deleting `AMR-CON-0086` automatically removed inverse relations pointing to the deleted entity. Those relation removals changed modification dates on the affected retained historical entities but did not change their Requirement IDs, Type, lifecycle State, Root Requirement content, or surviving obligation semantics. This is expected referential cleanup and not an additional unauthorized deletion/edit.

## Acceptance criteria

1. **PASS — every removed old AMR Requirement has explicit human-reviewed classification.** The only removed item, `AMR-CON-0086`, was classified `obsolete`, proposed explicitly, and deleted only after the user's exact V03-A approval.
2. **PASS — no corrected Requirement needed by the project is removed.** All 21 corrected Standards remain in the reference Project at `Ready / Succeeded`; none was deleted, Applied, or reworked.
3. **PASS — both RAW sources remain intact.** `AMR-RAW-0053` and `AMR-RAW-0077` remain in the canonical AMR Project at `Review`. The corrected reference RAW copies also remain intact.
4. **PASS — active AMR corpus contains only Requirements judged relevant after correction.** The single old item judged unnecessary without a canonical replacement, `AMR-CON-0086`, was removed. The other 27 remain operationally relevant because they still carry canonical AMR obligations; their corrected equivalents are reference-only and cannot safely replace them without a separate future decision.
5. **PASS — baseline evidence remains outside the active Requirement set.** RW-V01 permanently records both original RAWs and all 28 historical Standards, including the deleted `AMR-CON-0086`.
6. **PASS — cleanup reduces obsolete active context while preserving auditability.** One truly downstream/test-implementation Requirement was removed from active Fibery; its historical identity, rationale and corrected-pipeline comparison remain documented.

## Must-preserve / must-not review

Preserved:

- both original RAW Requirements;
- all corrected active reference Standards;
- compact evidence of the old `19 + 9` decomposition;
- explicit human authority over deletion.

Not violated:

- no cleanup occurred before corrected dogfood verification;
- no item was deleted because candidate count decreased;
- no general revision/supersession workflow was implemented;
- the human-approved obsolete Requirement was not retained merely for history after equivalent compact baseline evidence existed.

## Final decision

`RW-V03 = VERIFIED`.

With RW-V01, RW-V02 and RW-V03 independently verified, **Block E — Clean Dogfood / Verification is complete**.
