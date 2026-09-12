# RW-V03 — AMR Cleanup Proposal v0.1

**Status:** V03-A EXECUTED; V03-B HUMAN DECISION REQUIRED  
**Work item:** `RW-V03 — Human-reviewed cleanup of obsolete AMR dogfood requirements`  
**Date:** 2026-09-12  
**Historical baseline:** `docs/rewrite/RW-V01-AMR-Baseline-v0.1.md`  
**Corrected dogfood:** `docs/rewrite/RW-V02-AMR-Corrected-Dogfood-v0.1.md`  
**Independent V02 verification:** `docs/rewrite/RW-V02-Verification-v0.1.md`

## 1. Purpose

This document records the explicit human-reviewed classification and staged cleanup set for the 28 historical Applied Standard Requirements that existed in the canonical `ai-model-runner` / `AMR` Project at the RW-V01 baseline.

The frozen RW-V03 classifications are:

```text
still-needed
obsolete
redundant
over-decomposed
replaced
```

Classification and deletion are deliberately separate decisions.

---

## 2. Critical canonicality boundary

RW-V02 intentionally ran the corrected pipeline in the isolated reference Project:

```text
ZZ RW-V02 AMR Corrected Dogfood 0912 / ZZV02AMR
```

Its 21 corrected Standard Requirements are all `Ready / Succeeded` and none is Applied.

The V02 contract explicitly defines this Project as **comparison/reference data, not the canonical AMR Project**.

Therefore:

```text
semantic replacement in the reference corpus
!=
canonical replacement in ai-model-runner / AMR
```

Deleting an old AMR Requirement merely because a corrected reference candidate covers it would remove a canonical AMR obligation before an authorized canonical replacement exists.

For that reason cleanup is split into two sets:

1. **Immediate safe cleanup** — old Requirement content that no longer belongs at Requirement level and needs no replacement Requirement.
2. **Deferred replacement cleanup** — old Requirements that are semantically superseded by the corrected corpus but must remain until a separate human-approved canonicalization/promotion decision makes their replacement obligations authoritative for AMR.

This is a safety boundary, not a claim that the old decomposition is still desirable.

---

## 3. Classification summary

| Classification | Count | Meaning here |
|---|---:|---|
| `replaced` | 19 | corrected reference Requirement expresses the same obligation at the corrected abstraction boundary |
| `over-decomposed` | 8 | old standalone Requirement is folded into a broader corrected Requirement/Constraint where it belongs |
| `obsolete` | 1 | content belongs downstream rather than in the active Requirement corpus and needs no replacement Requirement |
| `redundant` | 0 | none requires this label separately from over-decomposition/replacement |
| `still-needed` | 0 semantically | none is the preferred corrected Requirement form; 27 remain operationally necessary only until canonical replacement exists |
| **Total** | **28** | historical V01 corpus |

Candidate count is not the reason for any classification.

---

## 4. Source A cleanup classification — `AMR-RAW-0053`

| Old Requirement | Classification | Corrected correspondence | Current action | Rationale |
|---|---|---|---|---|
| `AMR-FR-0054` | replaced | `ZZV02AMR-FR-0092` | KEEP pending canonical replacement | provider-neutral execution is preserved as one corrected capability |
| `AMR-CON-0055` | replaced | `ZZV02AMR-NFR-0094` (+ `CON-0093`) | KEEP pending canonical replacement | argv/no-shell remains a source-mandated safety constraint, expressed without making subprocess implementation the capability itself |
| `AMR-CON-0056` | replaced | `ZZV02AMR-CON-0093` | KEEP pending canonical replacement | configuration ownership remains, while the corrected Requirement leaves derivation/implementation structure downstream |
| `AMR-FR-0057` | over-decomposed | folded into `ZZV02AMR-FR-0100` Constraints | KEEP pending canonical replacement | stdout/stderr handling is not an independently useful capability; it constrains observable failure/result behavior |
| `AMR-FR-0058` | over-decomposed | `ZZV02AMR-FR-0095` | KEEP pending canonical replacement | timeout bound and timeout outcome form one meaningful execution-timeout obligation |
| `AMR-FR-0059` | over-decomposed | `ZZV02AMR-FR-0095` | KEEP pending canonical replacement | termination/cleanup/TIMEOUT belongs with the same timeout capability rather than a separate Requirement |
| `AMR-FR-0060` | replaced | `ZZV02AMR-FR-0096` | KEEP pending canonical replacement | latency obligation remains independently meaningful |
| `AMR-FR-0061` | replaced | `ZZV02AMR-FR-0097` | KEEP pending canonical replacement | request-size admission behavior remains independently meaningful |
| `AMR-NFR-0062` | replaced | `ZZV02AMR-FR-0098` | KEEP pending canonical replacement | bounded concurrency remains observable system behavior; corrected category/wording is preferable |
| `AMR-CON-0063` | replaced | `ZZV02AMR-CON-0099` | KEEP pending canonical replacement | source-mandated in-process/configuration-driven v1 constraint is preserved exactly as an allowed source-mandated mechanism |
| `AMR-FR-0064` | replaced | `ZZV02AMR-FR-0100` | KEEP pending canonical replacement | normalized/sanitized failure behavior remains one corrected capability |
| `AMR-CON-0065` | replaced | `ZZV02AMR-NFR-0101` | KEEP pending canonical replacement | portability obligation remains but is expressed as required outcome rather than implementation prohibition alone |
| `AMR-CON-0066` | replaced | `ZZV02AMR-CON-0102` | KEEP pending canonical replacement | credential isolation obligation is preserved |
| `AMR-CON-0067` | replaced | `ZZV02AMR-NFR-0103` | KEEP pending canonical replacement | telemetry/logging privacy obligation is preserved at system-observable level |
| `AMR-CON-0068` | replaced | `ZZV02AMR-CON-0104` | KEEP pending canonical replacement | temporary-file safety remains a source constraint |
| `AMR-CON-0069` | over-decomposed | `ZZV02AMR-CON-0105` | KEEP pending canonical replacement | default verification environment and its source-mandated coverage belong together in the corrected source constraint rather than two old standalone Requirements |
| `AMR-CON-0070` | over-decomposed | `ZZV02AMR-CON-0105` | KEEP pending canonical replacement | same merged verification obligation; V02 notes the corrected candidate is non-atomic but still closer to source abstraction than two test-plan Requirements |
| `AMR-CON-0071` | over-decomposed | folded into `ZZV02AMR-FR-0092` / `FR-0109` | KEEP pending canonical replacement | no-cross-provider-fallback constrains execution/status behavior and need not be a standalone product Requirement |
| `AMR-CON-0072` | replaced | `ZZV02AMR-CON-0106` | KEEP pending canonical replacement | health-check quota obligation remains independently meaningful |

Source A classification:

```text
replaced         = 13
over-decomposed  = 6
obsolete         = 0
total            = 19
```

---

## 5. Source B cleanup classification — `AMR-RAW-0077`

| Old Requirement | Classification | Corrected correspondence | Current action | Rationale |
|---|---|---|---|---|
| `AMR-FR-0078` | replaced | `ZZV02AMR-FR-0107` | KEEP pending canonical replacement | corrected external-contract Requirement preserves the mandatory ModelRequest field set while leaving representation/serialization HOW open |
| `AMR-FR-0079` | replaced | `ZZV02AMR-FR-0108` | KEEP pending canonical replacement | corrected ModelResponse contract preserves the externally observable field set and open source gaps |
| `AMR-FR-0080` | replaced | `ZZV02AMR-FR-0109` | KEEP pending canonical replacement | normalized status taxonomy remains mandated external behavior |
| `AMR-FR-0081` | replaced | `ZZV02AMR-FR-0110` | KEEP pending canonical replacement | output modes/result carriers remain mandated external behavior |
| `AMR-FR-0082` | over-decomposed | folded into `ZZV02AMR-FR-0108` (`execution`) / `NFR-0103` | KEEP pending canonical replacement | attempts/error telemetry belongs inside response/telemetry obligations rather than as its own Requirement |
| `AMR-CON-0083` | replaced | `ZZV02AMR-CON-0111` | KEEP pending canonical replacement | role remains opaque telemetry with no execution semantics |
| `AMR-CON-0084` | replaced | `ZZV02AMR-CON-0112` | KEEP pending canonical replacement | provider-neutral closed-v1 contract constraint remains intact |
| `AMR-CON-0085` | over-decomposed | folded into `ZZV02AMR-CON-0112` Constraints | KEEP pending canonical replacement | no-credential-field rule is part of the broader consumer-contract constraint rather than a separate Requirement |
| `AMR-CON-0086` | obsolete | **no corrected Requirement candidate** | **DELETED under approved V03-A** | unit-test coverage statement belongs downstream under RW-C01 Example 7; V02 intentionally produced no Requirement candidate for it, so removing it loses no corrected product Requirement obligation |

Source B classification:

```text
replaced         = 6
over-decomposed  = 2
obsolete         = 1
total            = 9
```

---

## 6. Gate V03-A — approved and executed

Human approval received verbatim:

```text
Approve V03-A: delete only AMR-CON-0086 by exact entity id; keep the other 27 historical Standards and the entire corrected reference corpus unchanged.
```

### Pre-delete re-read

The exact target was re-read immediately before deletion and matched all guard conditions:

```text
Requirement ID = AMR-CON-0086
entity id       = 8d80e73d-59f0-5d16-afa8-75070a8f35eb
Project         = ai-model-runner / AMR
Type            = Standard
State           = Applied
```

### Executed action

Exactly one entity was deleted from `SDLC/Requirement`:

```text
AMR-CON-0086
8d80e73d-59f0-5d16-afa8-75070a8f35eb
```

Post-delete exact-id query returns zero rows.

### Referential cleanup side effect

Fibery automatically removed inverse relationship references to the deleted entity. Activity history shows only these relation removals on retained historical entities:

- `AMR-RAW-0077`: `Produces -> AMR-CON-0086` removed;
- `AMR-CON-0071`, `AMR-FR-0078`, `AMR-FR-0079`, `AMR-FR-0080`, `AMR-FR-0081`, `AMR-FR-0082`: inverse `Blocks` references to `AMR-CON-0086` removed;
- `AMR-FR-0081`, `AMR-FR-0082`: inverse `Affects` references to `AMR-CON-0086` removed.

The deleted entity's own `Derived From`, `Depends On`, and `Impacted By` relations were removed as part of deletion.

This changed `fibery/modification-date` on those retained entities, but **did not change their Requirement ID, Type, State, Root Document content, or surviving obligation semantics**. No other historical entity was modified.

### Historical corpus postcondition

The canonical AMR Project now contains:

```text
2 Raw Requirements       -> Review
27 Standard Requirements -> Applied
AMR-CON-0086             -> absent
```

The remaining 27 historical Standards are preserved.

### Corrected reference corpus postcondition

The retained V02 reference Project remains exactly:

```text
2 Raw Requirements       -> Review / Succeeded
21 Standard Requirements -> Ready / Succeeded
0 Applied
0 Failed
```

Its entity modification dates are unchanged from the V02 verification snapshot, so V03-A did not mutate the corrected reference corpus.

The V01 compact baseline remains the permanent audit record for historical `AMR-CON-0086`.

**Gate V03-A: COMPLETE.**

---

## 7. Deferred cleanup set — do not delete yet

The remaining 27 old Requirements are semantically superseded/over-decomposed, but their corrected replacements currently exist only in the non-canonical reference Project.

Therefore all 27 remain protected from deletion for now:

```text
AMR-FR-0054
AMR-CON-0055
AMR-CON-0056
AMR-FR-0057
AMR-FR-0058
AMR-FR-0059
AMR-FR-0060
AMR-FR-0061
AMR-NFR-0062
AMR-CON-0063
AMR-FR-0064
AMR-CON-0065
AMR-CON-0066
AMR-CON-0067
AMR-CON-0068
AMR-CON-0069
AMR-CON-0070
AMR-CON-0071
AMR-CON-0072
AMR-FR-0078
AMR-FR-0079
AMR-FR-0080
AMR-FR-0081
AMR-FR-0082
AMR-CON-0083
AMR-CON-0084
AMR-CON-0085
```

Deleting these before canonical replacement would violate the purpose of cleanup: reducing obsolete context **without losing required product/system obligations**.

---

## 8. Canonicalization gap before full cleanup

RW-V02 deliberately leaves the corrected corpus here:

```text
reference Project ZZV02AMR
21 corrected Standards
State = Ready
not Applied
not canonical AMR Project requirements
```

Neither RW-V02 nor frozen RW-V03 defines a mechanism to promote/migrate those corrected Requirements into `ai-model-runner / AMR` while preserving correct Project identity, Requirement IDs, provenance and human approval.

This is not permission to:

- move the reference Requirements by editing their Project relation;
- rewrite old Applied Requirements in place;
- clone corrected Requirements manually;
- Apply reference Requirements and pretend they belong to AMR;
- rerun processing inside AMR;
- delete the 27 protected old Requirements anyway.

A separate explicit human decision is required before full replacement cleanup can safely proceed.

The cleanup problem therefore remains split:

```text
A. Remove Requirement-level material that is genuinely obsolete and needs no replacement
   -> COMPLETE: AMR-CON-0086 deleted under explicit human approval.

B. Replace the remaining old decomposition with corrected canonical AMR Requirements
   -> canonicalization/promotion decision required first.
```

---

## 9. Gate V03-B — canonicalization strategy

Before the remaining 27 may be deleted, choose/authorize a bounded mechanism that makes the verified corrected obligations canonical for `ai-model-runner / AMR` without corrupting identity/history.

Until Gate V03-B is resolved:

```text
remaining old AMR Standards: KEEP
reference corrected corpus: KEEP
both original RAWs: KEEP
```

No further live deletion is authorized by V03-A.

---

## 10. Current RW-V03 state

RW-V03 is **not complete** after V03-A.

Current truthful state:

```text
classification:                    COMPLETE
Gate V03-A human approval:         COMPLETE
Gate V03-A live deletion:          COMPLETE (AMR-CON-0086 only)
remaining historical Standards:    27 Applied, protected
corrected reference Standards:     21 Ready/Succeeded, protected
canonicalization/promotion decision: PENDING (Gate V03-B)
RW-V03 final verification:         NOT YET ELIGIBLE
```
