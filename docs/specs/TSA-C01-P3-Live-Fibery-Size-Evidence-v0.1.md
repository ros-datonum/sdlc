# TSA-C01 P-3 — Live Fibery Payload-Size Evidence v0.1

**Work item:** `TSA-C01 P-3 — bounded I-3 payload-limit probe`
**Status:** P3_EVIDENCE_RECORDED_UNVERIFIED
**Run (UTC):** 2026-10-16T11:04:30+00:00 → 2026-10-16T11:04:49+00:00
**Run id:** `20261016T110430Z`
**Repository baseline:** `bf68fa722f1ed119cb0225794fd0b62730288588`
**Probe:** `scripts/tsa_p3_fibery_size_probe.py`
**Raw evidence (sanitized by the probe):** `TSA-C01-P3-evidence/p3-live-evidence.json`
(sha256 `93164791fde4f70ab6d6126dfa9aee42eab5636ae64f2db1de920763a4ef47a0`)
**Normative authority:** `docs/specs/TSA-C01-Implementation-Spec-v0.3.md` §19.3
**Prior evidence:** `TSA-C01-P2-Live-Fibery-Evidence-v0.1.md` (fences up to 1 MiB
byte-exact)
**Production readiness claimed:** NO

One live mutation run, executed once. Every create, placement lookup, read and
write went through the existing `FiberyArchitectureWorkspace` over
`FiberyClient`, whose mutations are attempted exactly once. No production code,
dependency, runtime configuration or specification was changed; the P-2 probe
is reused only for its pure helpers and is unchanged. The probe has no
deletion path.

No token, environment value or Document content secret appears here or in the
raw evidence. Credentials were loaded into the probe process with
`uv run --frozen --env-file`; they were never displayed or copied. Payloads are
recorded only as byte counts and SHA-256 digests; the one error is the
client's sanitized public message.

## 1. Sequence

| Step | What | Result |
|---|---|---|
| 1 | Offline preflight (in-memory fake, five outcome scenarios, every guard refusal) | `PREFLIGHT OK` |
| 2 | Live read-only run (no confirmation flag) | Project verified; 0 creates / 0 writes; exit 2 by design |
| 3 | Live run with `--confirm-live-mutation` | exit 0; 2 creates / 2 writes / 0 deletes |

## 2. Scratch Project

| | |
|---|---|
| Workspace | `rb-ventures.fibery.io/19c62a00-7a47-11f1-aba7-67039973deac` |
| Name | `TSA P-1 SCRATCH — DO NOT USE` (contains `SCRATCH`) |
| Entity id | `368c0490-bda7-11f1-9f37-3f144160159b` (resolved by exact id) |
| Code / public id | `TSAP1` / `27` (both matched the expected values) |
| State | `Planned` before and after; `project_unchanged = true` |

The Project was re-read and compared with its baseline before each create and
write and once at the end. Writes were permitted only to a Document created by
this run, still carrying its probe name, still a root of Project `27`. No P-1,
P-2, TSA-cycle or other Document was a target.

## 3. Per-sample measurements

Each sample: a fresh Document, its original content read, one
`write_document_content` attempt (no retry), then re-discovery by id and a
durable read. Client timeout: 30 s (the configured default, unchanged).

| | 2 MiB | 4 MiB |
|---|---|---|
| Document | `4a827b68-0734-496c-860d-74671c6b8b7f` | `f165563f-278c-4b45-a1ce-8759e9acdf80` |
| Fence bytes (emitted) | 2097152 | 4194304 |
| Emitted Markdown bytes | 2097301 | 4194453 |
| Request body bytes | 2097333 | 4194485 |
| Original content | 0 bytes | 0 bytes |
| Write | returned | **raised: `PUT documents … failed (HTTP 500) on attempt 1`** |
| Failure attribution | — | `HTTP_REJECTION_UNATTRIBUTED` |
| Placement after write | present, root of `27`, unchanged | present, root of `27`, unchanged |
| Durable read | 2097300 bytes | **0 bytes** (sha256 of empty) |
| Durable state | `COMPLETE` | `EMPTY` (= the original) |
| Fence read back | 2097152 bytes, sha256 equal, exact | none |
| Fence JSON valid | yes | — |
| `document_fingerprint` equal | yes | no (empty Document) |
| Result | **SUCCESS** | **NOT_SUCCESS** |

The 2 MiB whole-Markdown read is one byte shorter than emitted (the trailing
newline, API constraint 11), exactly as in P-2; the fence and the fingerprint
are unaffected.

## 4. I-3 findings

| Limit item | Result |
|---|---|
| A — largest observed success | 2 MiB fence (2097301-byte Markdown) |
| B — smallest **verified size** refusal | **not established** |
| C — failure behaviour | at 4 MiB: HTTP 500, durable state EMPTY, placement intact |
| D — true maximum | unknown; the observed boundary lies somewhere in (2 MiB, 4 MiB] **if** the 500 is size-caused |
| Partial-write residue | none observed (the failed write left the Document empty) |

**Attribution.** The 4 MiB write failed with HTTP **500**, not 413. A 500 is a
server-side error that does not state its cause, and the client withholds the
response body by design. It is therefore recorded as an **unattributed HTTP
rejection**, not as a size limit. It is *consistent with* a size-related
failure (2 MiB succeeded under identical conditions moments earlier), but this
single observation does not distinguish a size cause from a transient server
fault.

**What the 4 MiB failure left behind**, measured, not inferred from the error:
the Document still resolves at its id with the same name and root placement in
Project `27`, and its content reads back as zero bytes — identical to its
original content. No partial or malformed payload was observed.

**I-3: INCOMPLETE.** The result is **SUPPORTED_AT_LEAST_2_MIB** (not
`SUPPORTED_AT_LEAST_4_MIB`, since 4 MiB did not succeed). §19.3 requires the
refusal behaviour above the supported size; what was observed is one
unattributed HTTP 500 that left no residue, not a verified size refusal.

## 5. Live versus fake

| # | Observation | Fake | Live | Effect |
|---|---|---|---|---|
| 1 | 4 MiB content write | accepted (the fake has no size bound) | HTTP 500; Document left empty | Recorded, not patched. The fake cannot represent this failure. |
| 2 | Whole-Markdown round trip | byte-identical | 1 byte shorter (trailing newline) | Already documented (API constraint 11); fence and fingerprint unaffected. |

## 6. Measurement limits

- One run, one attempt per size, no repetition: a transient server fault at
  4 MiB is not excluded, and a later read of the 4 MiB Document was not taken
  (the read followed the failed write immediately).
- No size between 2 MiB and 4 MiB was attempted; nothing above 4 MiB was
  attempted (by authorization).
- The failure carried no machine-readable cause beyond its HTTP status; the
  server's body is withheld by the client and was not recorded.
- Payloads are arbitrary canonical ASCII JSON in one fence, not schema-valid
  TSA artifacts. Non-ASCII content was not measured.
- The 400,000-code-point bound in Spec §15 applies to assembled model input,
  not model output, and is not used here as an artifact size limit.

## 7. Durable objects left in the scratch Project

Left in place for inspection (no deletion path). Both are Project-root
Documents of Project `27`.

| Id | Name | Content |
|---|---|---|
| `4a827b68-0734-496c-860d-74671c6b8b7f` | `TSA-P3-PROBE SIZE 2097152 20261016T110430Z` | 2 MiB sample (complete) |
| `f165563f-278c-4b45-a1ce-8759e9acdf80` | `TSA-P3-PROBE SIZE 4194304 20261016T110430Z` | empty (failed write) |

## 8. Remaining gates

- **I-3:** a verified size refusal (or a repeatable failure at a size) and its
  aftermath are still not established; distinguishing a size cause from a
  transient 500 would need a separately authorized repeat or intermediate size.
- This evidence is UNVERIFIED until independently reviewed.
