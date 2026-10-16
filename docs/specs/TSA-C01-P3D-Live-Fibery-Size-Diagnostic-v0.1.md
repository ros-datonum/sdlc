# TSA-C01 P-3D — Live Fibery Payload-Size Diagnostic v0.1

**Work item:** `TSA-C01 P-3D — final bounded I-3 diagnostic (3 MiB, then 4 MiB)`
**Status:** P3D_EVIDENCE_RECORDED_UNVERIFIED
**Run (UTC):** 2026-10-16T11:35:13+00:00 → 2026-10-16T11:35:22+00:00
**Run id:** `20261016T113513Z`
**Repository baseline:** `7f97c5481c4509e5e74ae27d2bf2f881ddabc790`
**Probe:** `scripts/tsa_p3d_fibery_size_diagnostic.py`
**Raw evidence (sanitized by the probe):** `TSA-C01-P3D-evidence/p3d-live-evidence.json`
(sha256 `eb47991be52ff0f50eb836f29bc71b28ff678f9321799074a87fe01b2dae7c5c`)
**Normative authority:** `docs/specs/TSA-C01-Implementation-Spec-v0.3.md` §19.3
**Prior evidence:** `TSA-C01-P2-Live-Fibery-Evidence-v0.1.md`,
`TSA-C01-P3-Live-Fibery-Size-Evidence-v0.1.md`
**Production readiness claimed:** NO

One live mutation run, executed once, as the final payload-size diagnostic of
the current TSA-C01 verification effort. Every create, placement lookup, read
and write went through the existing `FiberyArchitectureWorkspace` over
`FiberyClient`, whose mutations are attempted exactly once. The Project and
ownership guards, caps, payload generation and size bound are P-3's, imported
unchanged; no production code, dependency, runtime configuration,
specification, P-2 probe or P-3 probe was changed. The probe has no deletion
path.

No token, environment value or Document content secret appears here or in the
raw evidence. Credentials were loaded into the probe process with
`uv run --frozen --env-file`; they were never displayed or copied. Payloads are
recorded only as byte counts and SHA-256 digests; the one error is the
client's sanitized public message.

## 1. Sequence

| Step | What | Result |
|---|---|---|
| 1 | Offline preflight (nine failure-injection scenarios, every guard refusal) | `PREFLIGHT OK` |
| 2 | Live read-only run (no confirmation flag) | Project verified; 0 creates / 0 writes; exit 2 by design |
| 3 | Live run with `--confirm-live-mutation` | exit 0; **1 create / 1 write** / 0 deletes; stopped by the stop rule |

## 2. Scratch Project

| | |
|---|---|
| Workspace | `rb-ventures.fibery.io/19c62a00-7a47-11f1-aba7-67039973deac` |
| Name | `TSA P-1 SCRATCH — DO NOT USE` (contains `SCRATCH`) |
| Entity id | `368c0490-bda7-11f1-9f37-3f144160159b` (resolved by exact id) |
| Code / public id | `TSAP1` / `27` (both matched the expected values) |
| State | `Planned` before and after; `project_unchanged = true` |

The Project was re-read and compared with its baseline before the create and
the write and once at the end. The write was permitted only after re-checking
that the target was created by this run, still carried its probe name and was
still a root of Project `27`. No P-1, P-2, P-3 or other Document was a target.

The Document name carries P-3's prefix because P-3's guard, reused unchanged,
requires it; `DIAG` and the new run id distinguish it from P-3's Documents.

## 3. Measurements

| | 3 MiB | 4 MiB |
|---|---|---|
| Document | `3df5b2ed-a7a6-49d9-8a7e-2546da70e6c5` | — |
| Fence bytes (emitted) | 3145728 | — |
| Emitted Markdown bytes | 3145882 | — |
| Request body bytes (estimate) | 3145914 | — |
| Original content | 0 bytes | — |
| Write | **raised: `PUT documents … failed (HTTP 500) on attempt 1`** | **NOT_EXECUTED** (3 MiB did not succeed) |
| Outcome | `HTTP_500_UNATTRIBUTED` | — |
| Placement after write | present, root of `27`, same name | — |
| Durable read | 0 bytes (sha256 of empty) | — |
| Durable state | `EMPTY`; `durable_equals_original = true` | — |
| Fence read back | none | — |

Client timeout: 30 s (the configured default, unchanged). The run took about
nine seconds end to end; the failure was a server response, not a timeout.

## 4. Classified results

| Category | This run | Across P-2, P-3, P-3D |
|---|---|---|
| Confirmed successful payload sizes (validated read-back) | none | 8 KiB, 64 KiB, 256 KiB, 512 KiB, 1 MiB (P-2); 2 MiB (P-3) |
| HTTP 413 size refusals | none | none |
| HTTP 500 unattributed failures | 3 MiB | 4 MiB (P-3); 3 MiB (P-3D) |
| Transport timeouts / unknown outcomes | none | none |
| Durable content after every failed write | EMPTY (= original) | EMPTY (= original) in both failures |
| Partial or malformed artifacts | none | none |

## 5. Interpretation, kept separate

**Observed supported payload.** Fenced canonical ASCII JSON of up to
**2 MiB** (2097152-byte fence, 2097301-byte Markdown) was written and read back
byte-exact, with an equal `document_fingerprint`. Nothing between 2 MiB and
3 MiB was measured.

**Observed operational failure.** Two writes, at 4 MiB (P-3) and 3 MiB (P-3D),
about thirty minutes apart, each failed with HTTP 500 on its single attempt;
in both cases the fresh Document stayed in place, resolvable at its id, with
empty content. The pattern — success at 2 MiB, failure at both larger sizes,
no failure at any smaller size — is **consistent with** a size-related server
failure somewhere in (2 MiB, 3 MiB]. It is not proof: a 500 does not state its
cause, the response body is withheld by the client, and each size was
attempted once.

**Confirmed hard size refusal.** **None.** No HTTP 413 (or any response that
names size) was observed. No hard Fibery size limit is claimed.

**Production-safe operational limit.** Not determined by measurement. The
measurements show only that payloads up to 2 MiB were accepted and preserved,
and that 3 MiB and 4 MiB were not. Choosing an operating bound (and its
margin) is a decision for the gate owner, not a measured fact.

**Failure aftermath.** For the observed failures, a failed large write left
the Document's prior (empty) content unchanged, its placement intact and no
partial payload. Whether a failed write over **non-empty** prior content would
likewise leave the original untouched was not measured: every failure here
was on a fresh, empty Document.

**Formal I-3 gate status: INCOMPLETE.** §19.3 requires establishing the
supported payload size, the refusal behaviour above it, and what a partial
write leaves behind. Measured: a supported size of at least 2 MiB; above it,
an unattributed HTTP 500 with no durable residue, twice. Not established: a
verified size refusal, the boundary between 2 MiB and 3 MiB, and the aftermath
of a failed write over existing content.

## 6. Residual uncertainty

- Whether the 500s are size-caused (likely, given the pattern, but
  unconfirmed) or coincidental server faults.
- The actual boundary within (2 MiB, 3 MiB].
- Whether the boundary depends on content (non-ASCII, many fences, structure)
  rather than bytes; all payloads were canonical ASCII JSON in one fence.
- The aftermath of a failed write that replaces existing, non-empty content.
- Durability over time: each read followed its write immediately; no later
  re-read was taken.

## 7. Live versus fake

| # | Observation | Fake | Live | Effect |
|---|---|---|---|---|
| 1 | 3 MiB content write | accepted (the fake has no size bound) | HTTP 500; Document left empty | Recorded, not patched; same class as P-3's 4 MiB discrepancy. |

## 8. Durable objects left in the scratch Project

Left in place for inspection (no deletion path); a Project-root Document of
Project `27`:

| Id | Name | Content |
|---|---|---|
| `3df5b2ed-a7a6-49d9-8a7e-2546da70e6c5` | `TSA-P3-PROBE DIAG SIZE 3145728 20261016T113513Z` | empty (failed write) |

No 4 MiB Document was created.

## 9. Scope

This is the final payload-size diagnostic of the current TSA-C01 verification
effort. No further size probe is proposed here; how to treat the remaining I-3
gate is left to the gate owner. This evidence is UNVERIFIED until
independently reviewed.
