# RW-V01 — AMR Dogfood Baseline v0.1

**Status:** FROZEN BASELINE  
**Work item:** `RW-V01 — Preserve old AMR corpus as baseline evidence`  
**Owner:** Human + independent reviewer  
**Implementation actor:** NONE  
**Date:** 2026-09-12  
**Fibery project:** `ai-model-runner` (`AMR`)  
**Project entity id:** `01a081dc-80f1-7f6d-bbfe-3f38baee5fbb`

## 1. Purpose

This document freezes the live AMR Requirement corpus that existed before the corrected Requirement pipeline is dogfooded under `RW-V02`.

It is historical comparison evidence, not a target decomposition.

In particular:

```text
old candidate count != desired candidate count
19 + 9 is baseline evidence, not an optimization target
```

The corrected pipeline is judged semantically. It may legitimately produce fewer, the same number, or more Standard Requirements if that is what the corrected Requirement abstraction requires.

No live AMR entity was created, edited, transitioned or deleted while producing this baseline. The snapshot was collected through read-only Fibery queries.

---

## 2. Baseline RAW input A

```text
Requirement ID:      AMR-RAW-0053
Entity id:           01a081dc-b90a-7d93-b25b-f019e7fef3d2
Fibery public id:    53
Project:             ai-model-runner / AMR
Title:               Safe subprocess boundary and resource controls for provider runtimes
Type:                Raw
State:               Review
Source Fingerprint:  99b622c3f1198282f134bc0b1c8df678677e7856286e6d8e4f761dbae8ccb871
Old Produces count:  19
```

### Old Standard corpus produced by AMR-RAW-0053

| # | Requirement ID | State | Title | Entity id |
|---:|---|---|---|---|
| 1 | `AMR-FR-0054` | Applied | Provider-neutral execution service for official Codex and Claude CLIs | `4ec328e0-9563-5388-90bb-90bd2eb94337` |
| 2 | `AMR-CON-0055` | Applied | Subprocess invocation uses argv arrays only and never a shell | `ed9f3e2c-6606-5938-bc44-7ba40b99740a` |
| 3 | `AMR-CON-0056` | Applied | Executable path, working directory and CLI flags are configuration-owned, not caller-owned | `5a8e3545-ad5f-5632-b7d2-b3ebf073204a` |
| 4 | `AMR-FR-0057` | Applied | Separate capture of child stdout and stderr | `fa80b3ec-850e-5276-bb27-2cfa67545e13` |
| 5 | `AMR-FR-0058` | Applied | Every execution is bounded by a resolved timeout | `f2636b15-a996-57bb-a064-ec7c09dd5e49` |
| 6 | `AMR-FR-0059` | Applied | Timed-out child processes are terminated, cleaned up and reported as TIMEOUT | `74fe2047-f012-5e7e-b63d-6837e323efeb` |
| 7 | `AMR-FR-0060` | Applied | Latency is measured and reported for every execution | `74b9f555-d847-5664-930c-ec9dc67cdabb` |
| 8 | `AMR-FR-0061` | Applied | Oversized requests are rejected before provider execution | `6959624f-884d-5d5b-834d-d762111db0f7` |
| 9 | `AMR-NFR-0062` | Applied | Maximum concurrency is bounded by configuration | `a740994c-393c-5f8c-8685-c60a37c6d56e` |
| 10 | `AMR-CON-0063` | Applied | Resource controls are in-process and configuration-driven in v1 | `72d33a51-482e-5c82-a22b-f22ee960d57d` |
| 11 | `AMR-FR-0064` | Applied | Provider failures are classified into the normalized status taxonomy and returned sanitized | `ebbb0e26-2c3e-5ec1-b546-b9d3601e9834` |
| 12 | `AMR-CON-0065` | Applied | No environment-specific values are hardcoded in application code | `7bdc4312-3fd6-53e8-852c-85c1fd577273` |
| 13 | `AMR-CON-0066` | Applied | No OAuth credential files are read or exposed | `3c9fd794-3782-59a9-ae08-1e78b7aead4e` |
| 14 | `AMR-CON-0067` | Applied | Prompt and output content are excluded from logs; structured log fields are fixed | `b2859fa7-dff9-53ce-acbe-03f6cc2f9806` |
| 15 | `AMR-CON-0068` | Applied | Temporary files are private and cleaned up | `4e0bb74b-b163-58e6-8ab0-646f61c96cff` |
| 16 | `AMR-CON-0069` | Applied | Default unit test suite runs without credentials, live providers or network | `c552fb33-4449-52f5-b150-0ac01fb13a78` |
| 17 | `AMR-CON-0070` | Applied | Unit tests cover subprocess safety, timeout, process errors, request limits and concurrency | `25df2fee-4ad3-56e6-8859-1a0fd92fdd9d` |
| 18 | `AMR-CON-0071` | Applied | Closed provider set with no cross-provider fallback | `f26f6730-397c-5203-926f-87136944f232` |
| 19 | `AMR-CON-0072` | Applied | Health checks must not consume model quota | `5dd7361c-6697-503e-9fcf-cd16eb122b2b` |

---

## 3. Baseline RAW input B

```text
Requirement ID:      AMR-RAW-0077
Entity id:           01a08744-f75c-7c00-bfab-ad60694b9310
Fibery public id:    77
Project:             ai-model-runner / AMR
Title:               ModelRequest / ModelResponse and execution result contract
Type:                Raw
State:               Review
Source Fingerprint:  a6c160dd1725c5b83caa3fe766028b78c274dd20fff91fc0f27c0912243cfc76
Old Produces count:  9
```

### Old Standard corpus produced by AMR-RAW-0077

| # | Requirement ID | State | Title | Entity id |
|---:|---|---|---|---|
| 1 | `AMR-FR-0078` | Applied | Provider-neutral ModelRequest contract and its field set | `1761bf54-c1c1-5f21-9246-64ae8a4b2876` |
| 2 | `AMR-FR-0079` | Applied | Provider-neutral ModelResponse contract and its field set | `5abf56bf-cd40-5edd-9e49-7f1302e45c26` |
| 3 | `AMR-FR-0080` | Applied | Status taxonomy of ModelResponse.status with SUCCESS, admission and execution-failure outcomes | `17e5ed1a-b5f4-5971-b8e6-ae045321c385` |
| 4 | `AMR-FR-0081` | Applied | Output modes TEXT, JSON and JSON_SCHEMA select the response result carrier | `cfba195a-8967-534f-bd33-38a4f33ac091` |
| 5 | `AMR-FR-0082` | Applied | Execution telemetry reports attempt count and error code | `2731a4c3-a7d4-5788-ab19-ab0e0262ba00` |
| 6 | `AMR-CON-0083` | Applied | `role` is opaque telemetry and carries no execution semantics | `14c3de6d-b2e4-5eba-b5d8-57f2ecd2c845` |
| 7 | `AMR-CON-0084` | Applied | The request/response contract is provider-neutral and identical across the v1 provider set | `4b80a834-00f2-5d1a-bb27-3d16e273cad4` |
| 8 | `AMR-CON-0085` | Applied | No contract field carries or requests credentials | `108cbbc8-e394-5c7f-ad0f-255b3ddf98a5` |
| 9 | `AMR-CON-0086` | Applied | Unit test coverage for the contract: HTTP validation, output modes, error statuses, repair bound and no fallback | `8d80e73d-59f0-5d16-afa8-75070a8f35eb` |

---

## 4. Baseline facts

At the time of the snapshot:

```text
AMR-RAW-0053 -> 19 Standard Requirements
AMR-RAW-0077 ->  9 Standard Requirements
Total old produced Standard Requirements = 28
All 28 are Type = Standard
All 28 are State = Applied
Both RAW inputs still exist and are State = Review
```

The relation used for this baseline is the live RAW `Produces` relation. The item lists above preserve each old Standard Requirement's stable Requirement ID, entity id, title and current State, while the RAW sections preserve the stable source fingerprints and project identity.

These identifiers are sufficient to reproduce the old corpus membership without relying on title search or candidate count.

---

## 5. Semantic comparison criteria for RW-V02 / RW-V03

The corrected corpus is **not** compared by asking whether it has fewer items.

For every corrected candidate, and when comparing an old item to the corrected corpus, evaluate:

1. **Requirement meaning:** Is the item an independently meaningful statement of WHAT must be true?
2. **Implementation independence:** Could multiple valid technical implementations satisfy it unless the source explicitly mandates a mechanism?
3. **Implementation leakage:** Did components, functions, libraries, algorithms, execution steps, deployment mechanics or test implementation stay downstream unless source-mandated?
4. **Observable acceptance:** Does Requirement-level acceptance describe observable satisfaction rather than exact test code/framework mechanics?
5. **Source-mandated constraints:** Were explicit technical/product constraints from the RAW source preserved rather than discarded merely because they are technical?
6. **Open product questions:** Were unresolved source decisions preserved as open rather than silently invented?
7. **Fragmentation:** Was one meaningful capability kept together rather than split solely because the source described many technical details?
8. **Independent obligations:** Were genuinely independent product/system obligations kept distinct rather than merged merely because they appeared together?
9. **Architecture headroom:** Would Technical Solution Architecture still have meaningful HOW decisions left after the Requirement is accepted?
10. **Process/Review quality:** Did Standard Process/Review improve clarity, completeness, consistency, testability and relationship evidence without demanding downstream architecture detail?

For an old Standard Requirement, cleanup classification after successful corrected dogfood is one of:

```text
still-needed
obsolete
redundant
over-decomposed
replaced
```

No classification authorizes deletion by itself. `RW-V03` requires explicit human review before any removal.

---

## 6. Preservation rule

Until `RW-V02` has been independently verified and `RW-V03` reaches an explicit human cleanup decision:

- do not delete either RAW input;
- do not delete any of the 28 listed old Standard Requirements;
- do not rewrite their Requirement content merely to align it with the corrected abstraction;
- do not use old candidate count as a pass/fail target;
- dogfood corrected behavior only in an isolated/disposable corpus or another explicitly approved non-destructive setup.

This compact baseline remains the audit record after later human-approved cleanup removes obsolete old active Requirements.

---

## 7. RW-V01 acceptance mapping

### AC1 — baseline inputs reproducibly identifiable

PASS. Each RAW has stable Requirement ID, entity id, public id, Project identity, title and Source Fingerprint; every old produced Standard has stable Requirement ID and entity id.

### AC2 — no live AMR Standard Requirement deleted or rewritten

PASS. Baseline collection used read-only Fibery queries only. No AMR entity was created, updated, transitioned or deleted.

### AC3 — comparison criteria are semantic, not "produce fewer Requirements"

PASS. Section 5 freezes semantic comparison dimensions and explicitly states that 19 + 9 is historical evidence rather than a target count.

## Final decision

`RW-V01 = VERIFIED`.
