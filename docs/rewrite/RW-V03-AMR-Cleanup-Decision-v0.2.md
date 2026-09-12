# RW-V03 — AMR Cleanup Decision v0.2

**Status:** FINAL CLEANUP DECISION  
**Work item:** `RW-V03 — Human-reviewed cleanup of obsolete AMR dogfood requirements`  
**Date:** 2026-09-12  
**Supersedes:** only the extra `Gate V03-B` / incompleteness interpretation introduced by `RW-V03-AMR-Cleanup-Proposal-v0.1.md`; the v0.1 classification tables and V03-A execution evidence remain valid.

## 1. Decision

The frozen RW-V03 work item does **not** require a canonicalization/promotion mechanism for the 21 corrected reference Requirements before RW-V03 can complete.

The v0.1 cleanup proposal introduced `Gate V03-B` as a conservative safety checkpoint after observing that the corrected corpus lives in the isolated `ZZV02AMR` reference Project. That gate is not present in the frozen rewrite plan and must not be interpreted as a new normative dependency.

The frozen RW-V03 contract requires:

1. semantic comparison of every old AMR Standard Requirement against the corrected corpus;
2. an explicit cleanup classification;
3. an explicit cleanup set for human review;
4. removal only of human-approved unnecessary items;
5. gradual, checkable cleanup;
6. retention of RW-V01 baseline evidence;
7. preservation of both original RAW sources and the corrected active Standard Requirements;
8. no implementation of a general Requirement revision/supersession workflow as part of cleanup.

Those conditions are satisfied by the cleanup actually approved and executed.

## 2. Human-approved cleanup scope

The explicit human decision was:

```text
Approve V03-A: delete only AMR-CON-0086 by exact entity id; keep the other 27 historical Standards and the entire corrected reference corpus unchanged.
```

The exact approved entity was:

```text
Requirement ID: AMR-CON-0086
Entity id:      8d80e73d-59f0-5d16-afa8-75070a8f35eb
Classification: obsolete
```

It was deleted after an exact pre-delete identity/type/state/project re-read. A post-delete exact-id query returns no entity.

No other deletion is authorized by that human decision.

## 3. Remaining 27 historical Standards

The v0.1 semantic comparison remains valid:

```text
19 replaced
8 over-decomposed
1 obsolete (AMR-CON-0086, deleted)
```

For the remaining 27, semantic classification and current operational relevance are separate facts.

The corrected equivalents currently live only in the isolated dogfood reference Project and are not canonical `ai-model-runner / AMR` Requirements. Therefore deleting the 27 would remove canonical AMR obligations without an authorized canonical replacement.

For the purpose of the frozen RW-V03 acceptance boundary, the remaining 27 are consequently still relevant to the active AMR corpus **operationally**, even though their decomposition is no longer the preferred corrected abstraction.

They remain untouched except for Fibery's automatic inverse-relation cleanup caused by deleting `AMR-CON-0086`.

A future human may separately decide to introduce a bounded canonical replacement/migration mechanism. That would be a new explicit decision outside RW-V03; it is not required to complete this rewrite cleanup item.

## 4. Referential cleanup side effect

Deleting `AMR-CON-0086` caused Fibery to remove relations that pointed to the deleted entity.

Activity history confirms relation-only removals on retained entities, including:

- `AMR-RAW-0077` — `Produces -> AMR-CON-0086`;
- `AMR-CON-0071`, `AMR-FR-0078`, `AMR-FR-0079`, `AMR-FR-0080`, `AMR-FR-0081`, `AMR-FR-0082` — inverse `Blocks` references;
- `AMR-FR-0081`, `AMR-FR-0082` — inverse `Affects` references.

These referential removals changed `fibery/modification-date` on the affected retained entities, but did not change their Requirement ID, Type, State, Root Requirement content, or remaining obligation semantics.

This is expected referential cleanup of links to a deleted entity, not an additional cleanup decision.

## 5. Final live postconditions

Canonical `ai-model-runner / AMR` corpus:

```text
2 Raw Requirements       -> Review
27 Standard Requirements -> Applied
AMR-CON-0086             -> absent
```

Corrected reference Project `ZZV02AMR`:

```text
2 Raw Requirements       -> Review / Succeeded
21 Standard Requirements -> Ready / Succeeded
0 Applied
0 Failed
```

The corrected reference corpus retained the same modification dates as the V02 verification snapshot through the V03-A cleanup, proving it was not mutated by cleanup.

Both original AMR RAW Requirements remain intact.

## 6. Scope conclusion

RW-V03 cleanup is complete at the human-approved boundary.

It intentionally does **not**:

- promote or move reference Requirements into AMR;
- rewrite old Applied Requirements in place;
- implement Requirement revision/supersession;
- delete the remaining 27 historical Standards;
- delete either original RAW source;
- mutate or Apply the corrected reference Standards.

The old v0.1 statement that RW-V03 itself remained blocked on a separate `Gate V03-B` is superseded by this decision.
