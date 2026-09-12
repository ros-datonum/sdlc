# RW-V02 — Corrected AMR Dogfood Evidence v0.1

**Status:** DOGFOOD COMPLETE — NOT INDEPENDENTLY VERIFIED
**Work item:** `RW-V02 — Re-run the two AMR RAW sources through corrected Requirement pipeline`
**Frozen plan:** `d54db975e5cff73a2522598dfb1bc0727f45a523`
**Procedure:** `docs/rewrite/RW-V02-Dogfood-Boundary-v0.2.md` (supersedes v0.1)
**Baseline evidence:** `docs/rewrite/RW-V01-AMR-Baseline-v0.1.md`
**Code baseline:** `c65314fee9796a5579261ba1db0b6fc5a7216286`
**Branch:** `rewrite/rw-v02-amr-corrected-dogfood`
**Date:** 2026-09-12

RW-V02 is a live non-destructive dogfood experiment. No production code and no
test code changed. The system under test generated, processed and reviewed the
disposable candidates; it does not verify itself. Every Review verdict below is
evidence for a human, never authority.

## 1. Reference Project

```text
Name: ZZ RW-V02 AMR Corrected Dogfood 0912
Code: ZZV02AMR
id:   01a096f9-03d7-7cb2-8bf9-c7028e1b249d
```

Uniqueness was proven before creation by bounded read-only queries
(`q/limit 3`): exact Name count `0`, Code count `0`. Created through the
existing deterministic `sdlc project init`. The production `ai-model-runner`
Project was never used as a dogfood target.

**Retained.** This Project and all its contents are comparison data for RW-V03
and must not be deleted under RW-V02.

## 2. Historical corpus integrity

All 30 protected entities were snapshotted read-only before the dogfood and
re-read after it.

```text
entities compared                                      30 / 30
entity id / Requirement ID / Type / State mismatches    0
modification-date mismatches                            0
```

Before and after, the corpus is exactly `2 × (Raw, Review)` and
`28 × (Standard, Applied)`.

Historical RAW Root Document bodies, by stable hash:

| Historical RAW | body length | SHA-256 of body | unchanged | stored Source Fingerprint unchanged |
|---|---|---|---|---|
| `AMR-RAW-0053` | 6178 | `14765ac3…88d03` | yes | yes |
| `AMR-RAW-0077` | 12052 | `01247789…6e6215` | yes | yes |

**No historical AMR entity was created, edited, transitioned, related or
deleted at any point.**

## 3. Source equivalence (v0.2 section 4)

### 3.1 Why the two fingerprint values differ

The historical `Source Fingerprint` is an **ingestion-time provenance value**,
computed by `fingerprint_of` over the original exported artifact when the RAW
was first ingested. Fibery re-serializes Markdown when a Document is later read
back (`-` bullets returned as `*`, inserted blank lines, soft breaks returned as
`<br>`). `fingerprint_of` normalizes only NFC, line endings and trailing
whitespace, so it deliberately does not absorb that re-serialization —
`canonical_markdown` / `content_equivalent` exist for exactly that purpose.

Recomputing `fingerprint_of` over the body Fibery returns therefore cannot
reproduce the original digest. This is a round-trip property of the storage
layer, **not** semantic source drift: the section-4 equivalence proof below
passes in full for both sources.

The v0.1 boundary required digest equality and was unsatisfiable for these two
RAWs; v0.2 supersedes it. `src/sdlc/raw_source.py` was not changed, no
fingerprint was migrated, and the fingerprint-contract tension is recorded as a
non-blocking observation for a separate owner decision.

### 3.2 Source A — `AMR-RAW-0053`

```text
historical Requirement ID      AMR-RAW-0053
historical entity id           01a081dc-b90a-7d93-b25b-f019e7fef3d2
historical Source Fingerprint  99b622c3f1198282f134bc0b1c8df678677e7856286e6d8e4f761dbae8ccb871
historical Root body           6178 chars, sha256 14765ac31ef4f66e36e4c3814ed5c1f94ee77bc1747c5d5e279e1daf07b88d03

provenance anchor
  Requirement ID == RW-V01 id                 PASS
  stored Source Fingerprint == RW-V01 baseline PASS
  belongs to ai-model-runner / AMR             PASS
  title is the expected source document        PASS
  exactly one normative Root Document          PASS

reconstruction (Export Metadata inserted only; 80 characters added)
  parse_raw_requirement                        PASS
  content_equivalent(parsed.body, historical)  PASS
  canonical_markdown equality                  PASS
  parsed title == historical title             PASS

reference_copy_fingerprint     14765ac31ef4f66e36e4c3814ed5c1f94ee77bc1747c5d5e279e1daf07b88d03
values differ                  yes — expected, non-blocking
SOURCE-EQUIVALENCE             PASS
```

### 3.3 Source B — `AMR-RAW-0077`

```text
historical Requirement ID      AMR-RAW-0077
historical entity id           01a08744-f75c-7c00-bfab-ad60694b9310
historical Source Fingerprint  a6c160dd1725c5b83caa3fe766028b78c274dd20fff91fc0f27c0912243cfc76
historical Root body           12052 chars, sha256 0124778933408f05e4c9ee17b1f37bce85bc9e1d33b2e912574a04b0975e6215

provenance anchor                              all PASS (as above)
reconstruction (80 characters added)
  parse_raw_requirement                        PASS
  content_equivalent(parsed.body, historical)  PASS
  canonical_markdown equality                  PASS

reference_copy_fingerprint     0124778933408f05e4c9ee17b1f37bce85bc9e1d33b2e912574a04b0975e6215
values differ                  yes — expected, non-blocking
SOURCE-EQUIVALENCE             PASS
```

No sentence, heading, list item, constraint, decision, open question or fenced
block was rewritten. The only change was the transport metadata section. The
ephemeral artifacts were deleted after ingestion and their bodies were never
committed.

### 3.4 Traceability bridge

| historical RID | historical entity | historical fingerprint | → | copied RID | copied entity | reference-copy fingerprint |
|---|---|---|---|---|---|---|
| `AMR-RAW-0053` | `01a081dc-b90a-…f3d2` | `99b622c3…cb871` | → | `ZZV02AMR-RAW-0090` | `01a096f9-435f-…3eb7` | `14765ac3…88d03` |
| `AMR-RAW-0077` | `01a08744-f75c-…9310` | `a6c160dd…cfc76` | → | `ZZV02AMR-RAW-0091` | `01a096f9-6fc1-…d215` | `01247789…6e6215` |

### 3.5 Copied RAW validation after ingest

Both copies, ingested through the existing deterministic
`sdlc project requirement add`:

```text
Type = Raw                                                  PASS (both)
State = Draft                                               PASS (both)
Processing Status = Not Processed                           PASS (both)
Source Fingerprint == pre-ingest parsed.fingerprint         PASS (both)
exactly one Root Document                                   PASS (both)
content_equivalent(copied_root, historical_root)            PASS (both)
canonical_markdown(copied_root) == canonical(historical)    PASS (both)
```

## 4. Runner safety preflight

```text
other local `sdlc worker run` owning the workspace   none
Raw + Process + Not Processed                        0
Standard + Process + Not Processed                   0
Standard + Review + Not Processed                    0
Standard + Apply + Not Processed                     0
total unrelated eligible Requirements                0  -> CLEAR
```

One foreground runner was used. Persistent `FIBERY_SPACE_ID` is still empty, so
the already-verified process-scoped Space-id injection was reused. `.env` and
user-global Claude/Codex configuration were not edited.

## 5. Runtime / model selection

From `config/sdlc.toml`, unchanged for this experiment:

```text
transport                        local_cli_oauth
raw_requirement_processor        runtime "claude", invocation_mode "print", model omitted (local CLI default)
standard_requirement_processor   runtime "claude", invocation_mode "print", model omitted (local CLI default)
standard_requirement_reviewer    runtime "claude", invocation_mode "print", model omitted (local CLI default)
```

No model or runtime override was applied. No auth material is recorded here.

## 6. State-driven lifecycle proof

Both sources ran through the normal path only. **No manual `process`,
`normalize`, `review`, `approve`, `rework` or `apply` command was issued at any
point.** The only human-owned actions were the two authorized State changes.

```text
HUMAN  copied RAW Draft -> Process        (ZZV02AMR-RAW-0090, then ZZV02AMR-RAW-0091)
SYSTEM RAW Processor                      -> RAW_REQUIREMENT_PROCESSED
SYSTEM candidates Draft -> Process        one bounded inherited progression per RAW
SYSTEM Standard Process                   -> REQUIREMENT_PROCESSED, HANDED_OFF to Review
SYSTEM Standard Review                    -> REQUIREMENT_REVIEWED
SYSTEM Ready                              -> STOP
```

Runner cycle totals for the whole dogfood:

```text
SUCCEEDED cycles                 23   (2 RAW + 21 Standard Review)
HANDED_OFF cycles                21   (Standard Process -> new Review cycle)
FAILED / refused cycles           0
candidate-progression events      2   (one per RAW, naming every candidate of that RAW)
```

The `Progressed:` line for source A named all 15 candidates in one event, and
for source B all 6, matching the RW-C04 section 12 bounded inherited path. Each
`HANDED_OFF` line records that Standard Process handed off to a new Review cycle
at `Not Processed` with nothing written — the Process→Review reset boundary is
respected and no `Succeeded` was written over the destination cycle.

Sequencing: source B remained `Raw + Draft` until every source-A candidate had
settled at `Ready`, verified immediately before its transition.

## 7. Candidate counts — OBSERVATION ONLY

```text
source A (AMR-RAW-0053):  15 candidates   (old corpus: 19)
source B (AMR-RAW-0077):   6 candidates   (old corpus:  9)
total                     21              (old corpus: 28)
```

**These counts are not a success criterion.** RW-V01 fixes that `19 + 9` is
historical evidence, never a target, and a corrected corpus of any size can pass
or fail solely on semantic correctness.

## 8. Final state

```text
ZZV02AMR-RAW-0090   Raw / Review / Succeeded
ZZV02AMR-RAW-0091   Raw / Review / Succeeded
21 Standard candidates   Ready / Succeeded   (21/21)
none Processing, none Failed, none Applied
workspace-wide machine-eligible Requirements remaining: 0
runner: WORKER_RUNNER_STOPPED (clean SIGINT shutdown)
```

## 9. Review verdicts

Verdicts are evidence, not authority. Every candidate remains at `Ready`.

```text
source A:  NEEDS_WORK 13,  PASS 2      (PASS: CON-0099, CON-0106)
source B:  NEEDS_WORK  4,  PASS 2      (PASS: CON-0111, CON-0112)
total:     NEEDS_WORK 17,  PASS 4,  BLOCKING 0
```

No candidate received `BLOCKING`. No `Ready -> Process` rework and no
`Ready -> Apply` was performed.

A `NEEDS_WORK` verdict here overwhelmingly reflects **preserved source gaps**:
the reviewer repeatedly confirmed that the RAW source leaves a product question
open and that the candidate correctly did not invent an answer. That is the
behaviour the abstraction contract requires, not a defect in the candidate.

## 10. Semantic evaluation — source A (from `AMR-RAW-0053`)

Ten questions per candidate, in the frozen v0.2 order:
1 meaningful WHAT · 2 implementation independence · 3 leakage kept downstream ·
4 observable acceptance · 5 source-mandated constraints preserved ·
6 open questions preserved · 7 no over-fragmentation · 8 independent obligations
kept distinct · 9 Architecture HOW headroom remains · 10 Process/Review added
useful evidence.

### `ZZV02AMR-FR-0092` — Provider-neutral execution of official Codex and Claude runtimes (FUNCTIONAL, NEEDS_WORK)

> The service must accept a provider-neutral `ModelRequest` from a consumer, route it to the requested provider's official runtime, execute it, and return a provider-neutral `ModelResponse`.

1 Y — one capability. 2 Y — any routing/process design satisfies it. 3 Y — no
module, algorithm or invocation mechanics. 4 Y — acceptance is consumer-observable
("receives a `ModelResponse` produced by that provider's runtime"). 5 Y — closed
`codex`/`claude` v1 set and OAuth-already-authenticated assumption retained as
Constraints. 6 Y — Review confirmed a WARNING that behaviour for an unsupported
provider name is not established by source; correctly left open. 7 Y — routing,
execution and response are one capability. 8 Y — failure classification is
separately held by FR-0100. 9 Y — adapter design, process model and routing table
all remain open. 10 Y — one finding confirmed, one rejected after checking peers.
**Old corpus:** `AMR-FR-0054`; absorbs `AMR-CON-0071` (closed set / no fallback)
as Constraint and Non-Goal.

### `ZZV02AMR-CON-0093` — Execution target and invocation parameters are configuration-owned (CONSTRAINT, NEEDS_WORK)

> The executable that runs for a provider, the working directory that provider process runs in, and the command-line flags passed to it must be determined by trusted configuration and by the adapter's derivation from the request contract, and must never be determined by the caller.

1 Y. 2 Y — the ownership boundary survives any invocation design. 3 **Partial** —
the phrase "the adapter's derivation" names an internal component; Review raised
exactly this as an INFO finding and noted the obligation stands without it. Minor
wording, not a leaked mechanism. 4 Y. 5 Y — configuration-owned executable path
and working directory preserved. 6 Y — Review confirmed two real gaps (child
process **environment** is an unguarded invocation parameter of the same class;
which contract fields may legitimately shape flags). 7 Y. 8 Y — distinct from
NFR-0094, which Review explicitly verified as cross-reference rather than
duplicate obligation. 9 Y. 10 Y — three confirmed findings, one rejected with
reasoning against the peer text.
**Old corpus:** `AMR-CON-0056`, partly `AMR-CON-0055`.

### `ZZV02AMR-NFR-0094` — Request content is inert data, never command syntax (NON_FUNCTIONAL, NEEDS_WORK)

> Request content must reach the provider runtime only as data and must never be interpolated into a command string or otherwise be interpreted as executable command syntax.

1 Y. 2 Y — states the security outcome, exactly RW-C01 Example 4. 3 Y. 4 Y —
"crafted content causes no command execution beyond the single intended
invocation". 5 Y — "argv arrays only; `shell=True` never used" retained as a
Constraint and explicitly labelled source-mandated, the §4 exception used
correctly. 6 Y — Review confirmed the absolute acceptance clause is ambiguous
against agentic CLIs that may themselves execute commands; preserved as a scope
gap rather than invented away. 7 Y. 8 Y. 9 Y — invocation design left open.
10 Y — Review **rejected** the claimed duplicate-obligation finding after reading
CON-0093 in full.
**Old corpus:** `AMR-CON-0055`.

### `ZZV02AMR-FR-0095` — Every execution is time-bounded and leaves no running process (FUNCTIONAL, NEEDS_WORK)

1 Y. 2 Y — clock, cancellation and cleanup strategy all unspecified, as
RW-C01 Example 5 requires. 3 Y. 4 Y. 5 Y — default and maximum timeouts
configuration-driven. 6 Y — carries an explicit Open Question about provider-spawned
grandchild processes, and Review confirmed a second gap for zero/negative
`timeout_seconds`. 7 Y — deliberately merges bounding, termination and the
`TIMEOUT` outcome into one obligation. 8 Y. 9 Y. 10 Y.
**Old corpus:** merges `AMR-FR-0058` + `AMR-FR-0059`.

### `ZZV02AMR-FR-0096` — Measured latency reported in every response (FUNCTIONAL, NEEDS_WORK)

1 Y. 2 Y. 3 Y. 4 Y. 5 Y — latency reporting explicitly not conditional on success.
6 Y — Review confirmed the interval's boundaries are unfixed by source, and that
scope is ambiguous for responses with no provider execution. 7 Y. 8 Y. 9 Y.
10 Y. **Old corpus:** `AMR-FR-0060`.

### `ZZV02AMR-FR-0097` — Oversized requests rejected with `INVALID_REQUEST` before execution (FUNCTIONAL, NEEDS_WORK)

1 Y. 2 Y. 3 Y. 4 Y — "no provider process is started for it". 5 Y — bound is
configuration-driven. 6 Y — Review confirmed the composite "request and prompt
size" is unresolved in source, and flagged a taxonomy inconsistency with FR-0100.
7 Y. 8 Y. 9 Y. 10 Y — cross-document verification against FR-0100's enumeration.
**Old corpus:** `AMR-FR-0061`.

### `ZZV02AMR-FR-0098` — Concurrent executions bounded by configured maximum (FUNCTIONAL, NEEDS_WORK)

1 Y. 2 Y — no queue, semaphore or scheduler named. 3 Y. 4 Y. 5 Y. 6 Y — carries
explicit Open Questions on global-versus-per-provider scope and on what the
consumer observes at the bound; all three findings confirmed. 7 Y. 8 Y. 9 Y.
10 Y. **Old corpus:** `AMR-NFR-0062`.

### `ZZV02AMR-CON-0099` — Resource controls in-process and configuration-driven in v1 (CONSTRAINT, **PASS**)

1 Y. 2 N — **by the §4 exception**: the source explicitly forbids Redis, a
database or an external queue in v1, so naming them is source-mandated
Constraint content, not leakage. 3 Y. 4 Y — observable by running with no
external store available. 5 Y. 6 Y. 7 Y. 8 Y. 9 Y — in-process enforcement
design left open. 10 Y — Review rejected two findings and kept one INFO about
host-level versus service-level framing.
**Old corpus:** `AMR-CON-0063`.

### `ZZV02AMR-FR-0100` — Provider failures returned as normalized statuses with sanitized errors (FUNCTIONAL, NEEDS_WORK)

1 Y. 2 Y. 3 Y. 4 Y — "the returned error message contains no raw stderr text".
5 Y — separate stdout/stderr capture and the raw-stderr prohibition retained as
source-mandated Constraints. 6 Y — Review confirmed that which observable
failure maps to which status is unestablished, and that "sanitized" has no
positive definition in source. 7 Y. 8 Y. 9 Y — classification mechanism open.
10 Y. **Old corpus:** `AMR-FR-0064`; absorbs `AMR-FR-0057` (separate
stdout/stderr capture) as a Constraint rather than a standalone Requirement.

### `ZZV02AMR-NFR-0101` — Identical package runs under any user, path and host (NON_FUNCTIONAL, NEEDS_WORK)

1 Y. 2 Y. 3 Y. 4 Y. 5 Y — the no-hardcoding constraint is preserved verbatim in
substance. 6 Y — Review confirmed missing behaviour when configuration is absent
or invalid. 7 Y. 8 Y. 9 Y. 10 Y — three of five findings rejected with reasons.
**Old corpus:** `AMR-CON-0065`.

### `ZZV02AMR-CON-0102` — Never reads, exposes or extracts provider credentials (CONSTRAINT, NEEDS_WORK)

1 Y. 2 Y. 3 Y. 4 Y. 5 Y — source-mandated prohibition preserved. 6 Y — four
confirmed findings, all of them preserved ambiguities ("credential extraction"
undefined in source; v1-qualified versus unqualified statement; child-process
environment exposure; credential material appearing in provider output). 7 Y.
8 Y. 9 Y. 10 Y. **Old corpus:** `AMR-CON-0066`.

### `ZZV02AMR-NFR-0103` — Telemetry carries execution metadata, excludes prompt and output (NON_FUNCTIONAL, NEEDS_WORK)

1 Y. 2 Y — no logging framework or format named. 3 Y. 4 Y. 5 Y — the source's
"by default" qualifier preserved rather than silently hardened. 6 Y — Review
confirmed the non-default condition is unestablished, that several listed fields
have no establishing peer Requirement, and that stderr's membership in "provider
output content" is unsettled. 7 Y. 8 Y. 9 Y. 10 Y.
**Old corpus:** `AMR-CON-0067`.

### `ZZV02AMR-CON-0104` — Temporary files are private and cleaned up (CONSTRAINT, NEEDS_WORK)

1 Y. 2 Y. 3 Y. 4 **Partial** — Review confirmed the acceptance clause "no such
file was readable beyond the service" names no principals or observation point,
so it is not yet objectively observable. A genuine testability finding, correctly
raised rather than papered over. 5 Y — conditional framing ("where the service
uses temporary files") preserved from source. 6 Y — crash/kill end state noted as
unaddressed. 7 Y. 8 Y. 9 Y. 10 Y.
**Old corpus:** `AMR-CON-0068`.

### `ZZV02AMR-CON-0105` — Default verification needs no credentials, live providers, usage, remote hosts or network (CONSTRAINT, NEEDS_WORK)

1 Y. 2 Y. 3 **Partial** — the second half carries a coverage list (subprocess
safety, timeout, process errors, request limits, concurrency). Under RW-C01
Example 7 a bare "add unit tests for X" is normally Delivery Planning; here the
list is verbatim source-mandated constraint text, so retaining it is defensible.
Review itself flagged that the document carries two obligations the source states
as two separate bullets. **The clearest fragmentation/abstraction question in the
corpus; flagged for the independent reviewer.** 4 Y. 5 Y. 6 Y — "default" scope
boundary preserved as undefined. 7 N (see 3). 8 **Partial** — arguably two
obligations in one Requirement. 9 Y. 10 Y — six findings, three rejected.
**Old corpus:** merges `AMR-CON-0069` + `AMR-CON-0070`.

### `ZZV02AMR-CON-0106` — Health checking must not consume provider model quota (CONSTRAINT, **PASS**)

1 Y. 2 Y. 3 Y. 4 Y — "provider model usage attributable to the service is
unchanged". 5 Y — source-mandated accepted decision. 6 Y — carries an explicit
Open Question on whether non-billable probes are permitted. 7 Y. 8 Y. 9 Y. 10 Y.
**Old corpus:** `AMR-CON-0072`.

## 11. Semantic evaluation — source B (from `AMR-RAW-0077`)

### `ZZV02AMR-FR-0107` — Provider-neutral `ModelRequest` contract (FUNCTIONAL, NEEDS_WORK)

1 Y. 2 N — **by the §4 / RW-C01 Example 6 exception**: the RAW source is *about*
an externally consumed request contract, so its mandatory field set is
Requirement-level contract detail rather than leaked internal structure. Field
types, serialization and transport are explicitly left open. 3 Y. 4 Y. 5 Y.
6 Y — four confirmed findings, all preserved gaps (who assigns `request_id` and
whether it must be unique; `reasoning_effort`/`metadata` meaning; validation
outcomes beyond the size bound). 7 Y. 8 Y. 9 Y — internal data model and
serialization open. 10 Y. **Old corpus:** `AMR-FR-0078`.

### `ZZV02AMR-FR-0108` — Provider-neutral `ModelResponse` contract (FUNCTIONAL, NEEDS_WORK)

1 Y. 2 N — same mandated-external-contract exception. 3 Y. 4 Y — acceptance is
what a consumer can observe without provider-specific output. 5 Y — sanitized
error and no-raw-stderr constraint preserved. 6 Y — seven confirmed findings,
including unspecified `usage`/`execution` structure, whether model substitution
is permitted, and field applicability when no provider execution occurred.
7 Y. 8 Y. 9 Y. 10 Y — the richest review evidence in the corpus.
**Old corpus:** `AMR-FR-0079`; absorbs `AMR-FR-0082` (attempt count / error code)
into the `execution` field.

### `ZZV02AMR-FR-0109` — Normalized status taxonomy (FUNCTIONAL, NEEDS_WORK)

1 Y. 2 N — mandated enumeration, source-stated "at minimum". 3 Y. 4 Y — "the
consumer can determine which outcome occurred from the response status alone".
5 Y — no-cross-provider-fallback preserved. 6 Y — explicit Open Questions on
extensibility and on which observable signals map to which status; Review also
connected the unresolved concurrency-bound outcome from FR-0098. 7 Y. 8 Y. 9 Y.
10 Y. **Old corpus:** `AMR-FR-0080`.

### `ZZV02AMR-FR-0110` — Output modes `TEXT`, `JSON`, `JSON_SCHEMA` (FUNCTIONAL, NEEDS_WORK)

1 Y. 2 N — mandated external contract. 3 Y — no parser or validator named.
4 Y — non-conforming `JSON_SCHEMA` result "is not reported as a successful
result". 5 Y. 6 Y — explicit Open Question on a `JSON_SCHEMA` request supplying
no schema. 7 Y. 8 Y. 9 Y — schema-validation mechanism open. 10 Y.
**Old corpus:** `AMR-FR-0081`.

### `ZZV02AMR-CON-0111` — `role` is opaque telemetry (CONSTRAINT, **PASS**)

1 Y. 2 Y. 3 Y. 4 Y — "two requests differing only in `role` are routed, executed
and bounded identically" is a genuinely observable acceptance. 5 Y —
source-mandated prohibition. 6 Y — none open in source. 7 Y. 8 Y. 9 Y. 10 Y —
both proposed findings rejected with reasons, and a relation proposal rejected.
**Old corpus:** `AMR-CON-0083`.

### `ZZV02AMR-CON-0112` — Contract is provider-neutral across the closed v1 set (CONSTRAINT, **PASS**)

1 Y. 2 Y. 3 Y. 4 Y. 5 Y — closed `codex`/`claude` set and the no-credential-field
clause preserved. 6 Y — carries an Open Question on whether `provider`, `model`
and `reasoning_effort` count as provider-specific. 7 Y. 8 Y. 9 Y. 10 Y.
**Old corpus:** `AMR-CON-0084`; absorbs `AMR-CON-0085` (no contract field carries
credentials) as a Constraint.

## 12. Old-corpus correspondence

Comparison evidence only. **RW-V03 owns cleanup classification; nothing is
classified for deletion here.**

| Old RW-V01 Requirement | Apparent corrected correspondence |
|---|---|
| `AMR-FR-0054` | `ZZV02AMR-FR-0092` |
| `AMR-CON-0055` | `ZZV02AMR-NFR-0094` (+ `CON-0093`) |
| `AMR-CON-0056` | `ZZV02AMR-CON-0093` |
| `AMR-FR-0057` | folded into `ZZV02AMR-FR-0100` Constraints |
| `AMR-FR-0058`, `AMR-FR-0059` | `ZZV02AMR-FR-0095` (merged) |
| `AMR-FR-0060` | `ZZV02AMR-FR-0096` |
| `AMR-FR-0061` | `ZZV02AMR-FR-0097` |
| `AMR-NFR-0062` | `ZZV02AMR-FR-0098` |
| `AMR-CON-0063` | `ZZV02AMR-CON-0099` |
| `AMR-FR-0064` | `ZZV02AMR-FR-0100` |
| `AMR-CON-0065` | `ZZV02AMR-NFR-0101` |
| `AMR-CON-0066` | `ZZV02AMR-CON-0102` |
| `AMR-CON-0067` | `ZZV02AMR-NFR-0103` |
| `AMR-CON-0068` | `ZZV02AMR-CON-0104` |
| `AMR-CON-0069`, `AMR-CON-0070` | `ZZV02AMR-CON-0105` (merged) |
| `AMR-CON-0071` | folded into `ZZV02AMR-FR-0092` / `FR-0109` |
| `AMR-CON-0072` | `ZZV02AMR-CON-0106` |
| `AMR-FR-0078` | `ZZV02AMR-FR-0107` |
| `AMR-FR-0079` | `ZZV02AMR-FR-0108` |
| `AMR-FR-0080` | `ZZV02AMR-FR-0109` |
| `AMR-FR-0081` | `ZZV02AMR-FR-0110` |
| `AMR-FR-0082` | folded into `ZZV02AMR-FR-0108` (`execution`) / `NFR-0103` |
| `AMR-CON-0083` | `ZZV02AMR-CON-0111` |
| `AMR-CON-0084` | `ZZV02AMR-CON-0112` |
| `AMR-CON-0085` | folded into `ZZV02AMR-CON-0112` Constraints |
| `AMR-CON-0086` | **no corresponding candidate** — a unit-test coverage statement, which RW-C01 Example 7 places downstream as Delivery Planning |

## 13. Implementation-leakage assessment

**No confirmed implementation-leakage blocker.**

Every place where a technical mechanism appears in a corrected candidate falls
under the RW-C01 section 4 source-mandated exception or the section 6 / Example 6
mandated-external-contract exception, and each is labelled as such in the
candidate's own Constraints section:

- `argv` arrays / never `shell=True` (`NFR-0094`) — source-mandated;
- no Redis / database / external queue in v1 (`CON-0099`) — source-mandated;
- `ModelRequest` / `ModelResponse` field sets and the status/output-mode
  enumerations (`FR-0107`, `FR-0108`, `FR-0109`, `FR-0110`) — the committed
  external contract that the RAW source exists to define.

Two observations are recorded for the independent reviewer, neither rising to a
blocker:

1. `CON-0093` uses the phrase "the adapter's derivation", naming an internal
   component inside a Requirement sentence. The system's own Review raised this
   (INFO) and concluded the obligation stands without it.
2. `CON-0105` carries both a real environment constraint and a verification
   coverage list in one Requirement. The coverage list is verbatim source
   constraint text, but it is the corpus's weakest point against RW-C01
   Example 7 and against the "independent obligations kept distinct" dimension.

No source-mandated obligation was observed to be lost. Technical Solution
Architecture retains substantial HOW headroom across the corpus: process
invocation design, timeout/cancellation/cleanup strategy, concurrency mechanism,
failure-signal classification, serialization, schema validation, logging
implementation and configuration delivery are all undecided.

## 14. Lifecycle assessment

No new BLOCKING lifecycle defect was observed.

```text
manual worker command required for the normal path   NO
human Ready boundary crossed automatically           NO
machine failure falsely advancing State              NO  (zero FAILED cycles)
runner processed unrelated workspace work            NO  (0 eligible before and after)
old AMR corpus mutated                               NO
```

## 15. Repository gates

Run after the live dogfood:

```text
uv sync --locked            Resolved 8 packages, checked 7 — OK
uv run ruff check .         All checks passed!
uv run ruff format --check  182 files already formatted
uv run pytest -q            2271 passed
```

Production-code changes: **NONE**. Test-code changes: **NONE**. The branch
diff against main touches no file under `src/` or `tests/`.

## 16. Frozen acceptance criteria

| AC | Statement | Evidence | Assessment |
|---|---|---|---|
| AC1 | No confirmed implementation-leakage blocker remains | §13 | MET — none confirmed; two non-blocking observations recorded |
| AC2 | No source-mandated obligation lost merely because technical | §10, §11, §12 | MET — every mandated mechanism retained as a labelled Constraint |
| AC3 | Reviewer can explain every candidate's boundary without ad hoc exceptions | §10, §11 | MET — each candidate classified under RW-C01 §4/§6 or plain WHAT |
| AC4 | Technical Solution Architecture retains meaningful HOW decisions | §13 | MET |
| AC5 | Lifecycle works through the state-driven normal path | §6 | MET — 23 SUCCEEDED / 21 HANDED_OFF / 0 FAILED, no manual command |
| AC6 | Dogfood produces no new BLOCKING lifecycle defect | §14 | MET |

These are the dogfood operator's assessments. **RW-V02 is not verified by this
document**; an independent reviewer must read every candidate and its evidence
against the semantic criteria before RW-V02 may be marked VERIFIED.

## 17. Fingerprint-contract observation (non-blocking)

Recorded, not resolved: the historical ingestion fingerprint and the
reference-copy fingerprint differ for both sources because `fingerprint_of`
normalizes more narrowly than `canonical_markdown`, while Fibery re-serializes
stored Markdown. `src/sdlc/raw_source.py` was not changed and no fingerprint was
migrated. Any future change to that algorithm requires versioning/migration
analysis against existing stored fingerprints and duplicate detection, under its
own work item.

## 18. Retention

The reference Project `ZZ RW-V02 AMR Corrected Dogfood 0912` (`ZZV02AMR`,
`01a096f9-03d7-7cb2-8bf9-c7028e1b249d`) and all 23 of its Requirements are
retained live for RW-V03 comparison. It is comparison data, not the canonical
`ai-model-runner` Project. Disposal is a separate explicit human decision after
RW-V03.

## 19. Proposed Change Requests

None arising from the dogfood itself.
