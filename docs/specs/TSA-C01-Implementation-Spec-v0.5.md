# TSA-C01 — Implementation Specification v0.5 (delta to v0.3 + v0.4)

**Status:** FROZEN.
**Human approval:** explicit instruction approving the result code and the
bounded I08 correction below, given for repository snapshot
`e4e337d030e10a10454c8f7e77c045590b528789`.
**Implementation authorization:** GRANTED ONLY FOR THE BOUNDED I08 CORRECTION
DESCRIBED IN SECTION 6.
**Authority source:** `docs/architecture/TSA-C01-Contract-v0.2.md` (frozen),
unchanged.
**Base:** `docs/specs/TSA-C01-Implementation-Spec-v0.3.md` and
`docs/specs/TSA-C01-Implementation-Spec-v0.4.md` (both frozen), unchanged.

The approval record is that instruction. No signature or authenticated
identity is claimed for it.

## 1. Relation to v0.3 and v0.4

This document is a **delta**. v0.3 and v0.4 apply in full, except for the
additions below. Nothing in them is restated, amended or replaced; their
files are unchanged. In particular the meaning of `INPUTS_STALE` (v0.3 13.8:
Requirement or UX inputs drifted) is unchanged, and so is every other code.

## 2. New result code `REVIEW_INPUT_CHANGED`

**SPEC — addition to the result-code catalogue of v0.3 13.8.**

| Code | Meaning | Exit |
|---|---|---|
| `REVIEW_INPUT_CHANGED` | During one Reviewer-stage operation, the exact upstream Process Result that the operation fixed as its review input was replaced by another otherwise valid Process artifact before the intended Review Result became durable | 1 |

It names exact Reviewer-input **identity** drift. It does not name malformed
evidence: the replacing Process is not made malformed by it.

**SPEC — when it applies.** All of:

1. the operation started on a valid Process Result `P` and fixed `P`'s
   Document id and `artifact_digest` (section 4);
2. a later fresh read of the same Process slot and iteration finds another
   Process artifact `P2` that passes schema, digest and lineage on read;
3. `P2.artifact_digest != P.artifact_digest`.

It applies even when `P2`'s lineage is valid and its `intended_output`, and
so its rendered Architecture, is byte- and fingerprint-identical to `P`'s. The
same output does not make `P2` the artifact the Reviewer was given.

**SPEC — consequences.** On detection: no Review create and no Review body
write after it; a Reviewer output already obtained is not re-bound to `P2`;
the operation does not continue on the new snapshot. The code implies no
automatic retry, no new model call, no repair and no new iteration. A Review
write already executed before the detection is neither rolled back nor
repeated.

## 3. Precedence

**SPEC.** `REVIEW_INPUT_CHANGED` is decided only after the fresh read has
validated the Process slot, and never in place of a more specific code:

| Situation | Code |
|---|---|
| Requirement or UX input drift | `INPUTS_STALE`, unchanged |
| The Process read fails schema, digest or lineage | `ARTIFACT_MALFORMED` |
| Two artifacts claim the Process slot | `ARTIFACT_DUPLICATE` |
| Architecture content that does not match the Process (case 4) | `ARCHITECTURE_DIVERGED` |
| A supplied persisted Review that does not bind the target, where that code is frozen (11.1.1) | `REVIEW_NOT_CURRENT` |
| A valid Process at the fixed slot whose digest differs from the fixed one | `REVIEW_INPUT_CHANGED` |
| A mutation that failed, or a read-back that is not the intended Review | `FIBERY_WRITE_FAILED` |

**SPEC — order inside one fresh read.** The Process slot is validated
(schema, digest, lineage) first, then compared with the operation's fixed
binding, and only then is the Review slot validated against it. So after a
Review write, a durable Review bound to `P` beside a valid `P2` is
`REVIEW_INPUT_CHANGED`, not `ARTIFACT_MALFORMED` and not
`FIBERY_WRITE_FAILED`: the Process replacement is what was established.

**SPEC.** A missing or empty Process slot is not a replacement by an
otherwise valid artifact; the existing classification applies to it.

## 4. The fixed Reviewer Process binding

**SPEC.** Before its model call, a Reviewer operation fixes, as
operation-local values: the iteration, the Process Result Document id and
`artifact_digest`, and the Manifest and Architecture bindings it already
fixes. These are expectations of one operation, held in memory only. They
are not persisted, not a new artifact, field, journal or lock, and they are
compared against every fresh read of the operation: after the model call,
after a known Review create, after an unknown create before any retry, and
at the read-back confirmation of the Review write.

## 5. An empty Review shell is not Review evidence

**SPEC.** For the Reviewer stage's read classification, a Review slot is
`ABSENT`, `EMPTY` or `VALID` (non-empty and malformed is refused as
`ARTIFACT_MALFORMED`). `EMPTY` is not persisted Review evidence: until a valid
Review exists, the Architect case of the iteration is classified by the normal
case rules of contract 14.3 —

| Process | Architecture | Review slot | Outcome |
|---|---|---|---|
| valid | recorded input | `EMPTY` | Architect stage required (pending apply); the shell does not make the state malformed |
| valid | intended output | `EMPTY` | Review shell completion in place at the same id (13.7-7) |
| valid | neither | `EMPTY` | `ARCHITECTURE_DIVERGED`, with the input, output and current fingerprints |
| valid | intended output | `VALID` | current Review reuse, unchanged |

No second Review Document is created and no shell is deleted.

## 6. No migration, bounded authorization

**SPEC.** No persisted artifact is migrated, rewritten or re-sealed, and no
wire schema changes. `REVIEW_INPUT_CHANGED` is a result code, not an artifact
field or lifecycle state.

**Authorized:** the I08 correction of findings F1 (section 5) and F2
(sections 2–4) in `src/sdlc/tsa_reviewer.py`, `tests/test_tsa_reviewer.py` and
`tests/reviewer_fake.py`, and in `src/sdlc/tsa_architect.py` /
`tests/test_tsa_architect.py` only for the minimal correction of the
Reviewer's read boundary (`read_review_target`) these sections need.

**Not authorized:** any other work item (I10, I11, I12); changes to the
prompt modules, I01–I06, I09, schemas, adapters, dependencies, runtime, CLI or
worker; any change of I07's own recovery semantics; any change of the
contract or of the meaning of an existing code; live Fibery or model runs;
merge.
