# TSA-C01 P-2 — Live Fibery Capability Evidence v0.1

**Work item:** `TSA-C01 Live Fibery Verification P-2` (gates `I-2`, `I-3`)
**Status:** P2_EVIDENCE_RECORDED_UNVERIFIED
**Run (UTC):** 2026-10-16T10:46:39+00:00 → 2026-10-16T10:47:39+00:00
**Run id:** `20261016T104639Z`
**Repository baseline:** `a943adcd7af34563872d98c84d1bf7357cc1480f`
**Probe:** `scripts/tsa_p2_fibery_probe.py`
**Raw evidence (sanitized by the probe):** `TSA-C01-P2-evidence/p2-live-evidence.json`
(sha256 `f25a7a2b02dd4cc50d14ba469dbd597a40781327bc4cf76c775152354c65695f`)
**Normative authority:** `docs/specs/TSA-C01-Implementation-Spec-v0.3.md` §19.3
**Production readiness claimed:** NO

One live mutation run, executed once. Every create, write, read, placement
lookup and listing went through the existing `FiberyArchitectureWorkspace` over
`FiberyClient`; the I05 UX read was the production `admit_ux`. The one
deletion used the documented Views method `delete-views`
(`docs/fibery/Fibery-API-Constraints-v0.1.md`, constraint 23) through the
client's existing generic `views_rpc`. No production code, dependency, runtime
configuration or worker behaviour was changed.

No token, environment value or Document content secret appears here or in the
raw evidence: the probe registers and scrubs every secret, records placements
with `secret_present` only, and records the size samples as byte counts and
SHA-256 digests only. Credentials were loaded into the probe process with
`uv run --frozen --env-file`; they were never displayed or copied.

## 1. Sequence

| Step | What | Result |
|---|---|---|
| 1 | Settings presence check (values not printed) | present |
| 2 | Offline preflight against the in-memory fake | `PREFLIGHT OK` |
| 3 | Live read-only run (no confirmation flags) | Project verified; 0 creates / 0 writes / 0 deletes; exit 2 by design |
| 4 | Live run with `--confirm-live-mutation --confirm-probe-deletion` | exit 0; 7 creates / 8 writes / 1 delete (all at the caps) |

## 2. Workspace and scratch Project

```text
workspace identity   rb-ventures.fibery.io/19c62a00-7a47-11f1-aba7-67039973deac
```

| | |
|---|---|
| Name | `TSA P-1 SCRATCH — DO NOT USE` (contains `SCRATCH`) |
| Entity id | `368c0490-bda7-11f1-9f37-3f144160159b` (resolved by exact id) |
| Code | `TSAP1` (matched `--expect-code`) |
| Public id | `27` (matched `--expect-public-id`) |
| State | `Planned` before and after |

The Project record (id, name, code, public id, state) was re-read and compared
with the baseline before every create, write and delete, and once at the end:
`project_unchanged = true`. No Requirement was read or written; the UX scope of
the I05 read is the synthetic id `TSAP2-FR-0001`, which is never resolved.

Mutation guards: a create needs a fresh UUID with no existing placement and a
`TSA-P2-PROBE … <run id>` name; a write or delete needs a Document created by
**this** run, still carrying its probe name, and still a valid root of the
scratch Project. The P-1 Documents (`8dee7dd2-…`, `fa4256c9-…`) were never a
target of any mutation.

## 3. I-2 — UX Document replacement and deletion

UX-A and UX-B are two Project-root Documents with the **same name**
`TSA-P2-PROBE UX 20261016T104639Z` and different content.

| Id | Role |
|---|---|
| `c49e6690-861d-4ecb-8152-f59425b128f3` | UX-A (bound, modified, then deleted) |
| `2131861f-6eea-4b24-8f5d-cb0ed160d4be` | UX-B (same name, left in place) |

### 3.1 Measurements

| Step | Observation |
|---|---|
| A created + written | resolves by id; container `27`, root (no parent); listed exactly once under the Project |
| A bound via `admit_ux` | `content_digest = f01f6ea4…240a` = fingerprint of the content read back = fingerprint of the content written |
| B created (same name) | id distinct from A; listed once; Project listing shows 2 Documents with that name |
| After B | A's content fingerprint unchanged; `admit_ux(A)` still yields `f01f6ea4…240a` — B is not adopted by name |
| A content replaced (`write_document_content`) | same id resolves, same placement, listed once; fingerprint now `b7ddee39…3ec5`; `admit_ux(A)` now yields `b7ddee39…3ec5` ≠ the bound digest |
| A deleted (`delete-views`, ids `[A]`) | `resolve_placement(A)` → absent; A listed 0 times; B still listed once with unchanged fingerprint; 1 Document of that name remains |
| `admit_ux(A)` after deletion | refused `UX_EVIDENCE_INVALID`: "no Document exists at that id" |

Deletion success was not inferred from the transport response: it was measured
by id resolution, the Project listing, and the production I05 read.

### 3.2 Classification

| Sub-item | Result |
|---|---|
| direct-id rediscovery | VERIFIED |
| Project listing | VERIFIED |
| fingerprint currentness (`admit_ux` digest = read-back fingerprint) | VERIFIED |
| same-name Document of another identity; original still present and distinguishable | VERIFIED |
| content modification at the same id | VERIFIED |
| original binding invalidated by modification (digest differs) | VERIFIED |
| deletion of a probe Document | VERIFIED |
| original binding invalidated by deletion (`UX_EVIDENCE_INVALID`) | VERIFIED |

**I-2: CLEARED** — for the measured operations (in-place content
replacement, a same-name Document of another identity, and deletion via
`delete-views`), id-based rediscovery stays exact, a name is never adopted, and
the I05 read no longer reproduces the originally bound digest.

## 4. I-3 — fenced JSON payload size

Each sample: its own fresh probe Document, one `write_document_content` attempt,
no retry. The fence is deterministic canonical ASCII JSON of exactly the sample
size (one `filler` string field), inside a heading + prose carrier.

| Sample | Document | Emitted md bytes | Read md bytes | Fence bytes (emitted / read) | Fence exact | JSON valid | Fingerprint equal | Durable state |
|---|---|---|---|---|---|---|---|---|
| 8 KiB | `bbd5f6c7-c555-497e-8406-4ab6477e15f8` | 8338 | 8337 | 8192 / 8192 | yes | yes | yes | COMPLETE_NEW |
| 64 KiB | `538f1f40-cbc5-44e9-be5e-3ab5827006d7` | 65683 | 65682 | 65536 / 65536 | yes | yes | yes | COMPLETE_NEW |
| 256 KiB | `90063c88-1503-48b3-98ba-ff3551a1b9ae` | 262292 | 262291 | 262144 / 262144 | yes | yes | yes | COMPLETE_NEW |
| 512 KiB | `441cabc0-778b-4664-9424-aa02bb19def1` | 524436 | 524435 | 524288 / 524288 | yes | yes | yes | COMPLETE_NEW |
| 1 MiB | `c04b85ed-bccf-4e21-8bba-bb446e2e3235` | 1048725 | 1048724 | 1048576 / 1048576 | yes | yes | yes | COMPLETE_NEW |

Every write returned without error. Fence SHA-256 values and whole-Markdown
digests are in the raw evidence.

| Limit item | Result |
|---|---|
| A — largest success | 1 MiB fence (1048725-byte Markdown) |
| B — smallest rejected | not observed (none attempted above 1 MiB) |
| C — refusal behaviour | not observed |
| D — true maximum | unknown |
| Partial-write residue | not observed (no failure occurred) |

**I-3: INCOMPLETE — SUPPORTED_AT_LEAST_1_MIB.** §19.3 requires the refusal
behaviour above the limit and what a partial write leaves behind; neither was
reached under the 1 MiB cap of this brief.

## 5. Live versus fake

| # | Observation | Fake | Live | Effect |
|---|---|---|---|---|
| 1 | Whole-Markdown round trip | byte-identical | 1 byte shorter (trailing newline dropped) | Already documented (API constraint 11). Fence bytes and `document_fingerprint` are equal, so neither the I05 digest nor fence extraction is affected. No production change. |

No other discrepancy: placement, listing, same-name handling, content
replacement, deletion and the I05 refusal behaved as the fake models them.

## 6. Measurement limits

- One run, one workspace, one Project; no repetition, no concurrency, no
  timing/propagation measurement (each read followed its write in sequence).
- Deletion was measured only via `delete-views`, on a Document with no
  children; trash/restore, deletion of a Document with children, and deletion
  by another actor were not measured.
- "Replacement" by another identity was measured with the original still
  present; replacement after deletion (B taking A's place) was observed only as
  "B is not adopted for A's id".
- I-3 payloads are arbitrary canonical ASCII JSON, not schema-valid TSA
  artifacts; non-ASCII content, many fences per Document, and many small
  writes were not measured. Sizes above 1 MiB were not attempted.
- Transport errors, HTTP 429 handling and unknown-outcome writes did not occur
  and were not exercised.

## 7. Durable objects left in the scratch Project

Not cleaned up (by design). All are Project-root Documents of Project `27`.

| Id | Name |
|---|---|
| `2131861f-6eea-4b24-8f5d-cb0ed160d4be` | `TSA-P2-PROBE UX 20261016T104639Z` |
| `bbd5f6c7-c555-497e-8406-4ab6477e15f8` | `TSA-P2-PROBE SIZE 8192 20261016T104639Z` |
| `538f1f40-cbc5-44e9-be5e-3ab5827006d7` | `TSA-P2-PROBE SIZE 65536 20261016T104639Z` |
| `90063c88-1503-48b3-98ba-ff3551a1b9ae` | `TSA-P2-PROBE SIZE 262144 20261016T104639Z` |
| `441cabc0-778b-4664-9424-aa02bb19def1` | `TSA-P2-PROBE SIZE 524288 20261016T104639Z` |
| `c04b85ed-bccf-4e21-8bba-bb446e2e3235` | `TSA-P2-PROBE SIZE 1048576 20261016T104639Z` |

Deleted: `c49e6690-861d-4ecb-8152-f59425b128f3` (UX-A). The P-1 Documents
were never targeted by any mutation (their content was not re-read).

## 8. Remaining gates

- **I-3** above-limit refusal and partial-write residue: needs a separately
  authorized probe above 1 MiB.
- This evidence is UNVERIFIED until independently reviewed.
