# TSA-C01 I03 — P-1 Live Fibery Evidence v0.1

**Work item:** `I03 — Live Fibery probe P-1`
**Status:** EVIDENCE RECORDED
**Run (UTC):** 2026-10-01T15:01:50+00:00
**Repository baseline:** `8d935fe0039d9b26b89f31fe9d5e0f9968e6d2c6`
**Probe:** `scripts/tsa_p1_probe.py`
**Frozen authority:** `docs/architecture/TSA-C01-Contract-v0.1.md`,
`docs/specs/TSA-C01-Implementation-Spec-v0.1.md` §2, §2.2.1, §2.3, §17, §19
**Implementation authorized:** NO (this document records evidence only)

One live mutation run, executed once. Every call went through the real
`FiberyArchitectureWorkspace` added by I02, so what is recorded below is the
behaviour of the adapter I04+ will consume, not of a reimplementation.

No token, no `.env` content and no Document content secret appears in this
document. The one live error text was sanitized by the probe before capture.

## 1. Workspace and scratch Project

```text
workspace identity   rb-ventures.fibery.io/19c62a00-7a47-11f1-aba7-67039973deac
```

The Project was resolved by **exact entity id**, never by name:

| | |
|---|---|
| Name | `TSA P-1 SCRATCH — DO NOT USE` |
| Entity id | `368c0490-bda7-11f1-9f37-3f144160159b` |
| Public id | `27` |
| Code | `TSAP1` |

The entity id and the public id are different values, which is the distinction
`I-1` is about.

## 2. Root Document — Project containment

```text
name           TSA-P1-PROBE ROOT 20261001T150152Z
requested id   8dee7dd2-979c-473d-8ebb-7503053d2485
returned id    8dee7dd2-979c-473d-8ebb-7503053d2485
```

The caller-supplied id was preserved exactly: the adapter sent it as `fibery/id`
and Fibery returned the same value on read-back.

### Placement

| Field | Observed |
|---|---|
| `container_entity_type` | `2d4bba0c-5eb7-4dc2-b406-0f10404ef31f` (the Project Database's type id) |
| `container_entity_id` | `27` — the Project **public id** |
| `parent_document_id` | `None` |
| secret present | yes |

`container_entity_id` is the public id `27`, **not** the entity uuid
`368c0490-bda7-11f1-9f37-3f144160159b`. The container type is the Project
Database's own type id, which is also the id recorded in API constraint 8.

### Rediscovery

```text
documents_attached_to_project(public_id="27")  ->  1 Document
probe root matches                             ->  1
```

The listing placement was **equal** to the directly resolved placement, so the
two read paths agree field for field.

### Checks

All twelve root checks PASS:

```text
root_caller_id_preserved                root_resolve_document
root_container_id_is_not_entity_id      root_resolve_placement
root_container_id_is_project_public_id  root_secret_present
root_container_type_is_project_database root_rediscovered_exactly_once
root_has_no_parent                      root_listing_matches_direct_resolve
root_predicate_accepts                  root_placement_still_valid_after_child
```

`root_predicate_accepts` is `is_valid_root_placement` returning true against the
live Project type id and public id — the pure predicate I02 froze, evaluated on
live data.

## 3. Child Document — deterministic nesting

```text
name           TSA-P1-PROBE CHILD 20261001T150152Z
requested id   fa4256c9-2659-435d-b00a-1497a38ce9d8
returned id    fa4256c9-2659-435d-b00a-1497a38ce9d8
parent         8dee7dd2-979c-473d-8ebb-7503053d2485
```

| Field | Observed |
|---|---|
| `parent_document_id` | the root id |
| `container_entity_type` | `None` |
| `container_entity_id` | `None` |
| secret present | yes |

**The child carries no Project container fields of its own, and that matches the
frozen model.** §2.2.1 requires a child to be tied to the Project *through* the
root: `is_valid_child_placement` validates the child's parentage and then
validates the parent as a root. Had I02 compared the child's own
`container_entity_id` against the Project public id — the mistake §2.2.1
explicitly forbids — this live child would have been rejected.

### Rediscovery, both read shapes

```text
child_placements(root id)  ->  1 match   (DocumentPlacement)
child_documents(root id)   ->  1 match   (DocumentNode)
resolve_placement(child)   ->  found
resolve_document(child)    ->  found
```

### Checks

All seven child checks PASS:

```text
child_caller_id_preserved        child_resolve_document
child_in_child_documents_once    child_resolve_placement
child_in_child_placements_once   child_predicate_accepts_through_root
child_parent_is_root
```

The root placement was re-resolved after the child was created and remained
valid (`root_placement_still_valid_after_child`).

## 4. Content round trip

The payload was the deterministic probe document: a level-1 heading, one prose
paragraph, and one `` ```json `` fence containing
`{"probe":"tsa-p1","version":1}`.

### Whole Markdown — OBSERVATIONAL ONLY

```text
FULL_MARKDOWN_BYTE_EQUALITY   DIFFERENT_DUE_TO_FIBERY_RESERIALIZATION
observational only            true

written bytes   76
read bytes      75

written SHA-256 b3206f8143c1c33cc8b54f7aa3982f15dfdcf10da0cdaf54b0805653741cc5c9
read SHA-256    8c94cd897bf25731d77f0307adae87045297bb8270253ab6838028b2cf9e82b6
```

**Why this is not a failure.** API constraint 11
(`docs/fibery/Fibery-API-Constraints-v0.1.md`) already records, verified live,
that Fibery re-serializes stored Markdown: the trailing newline is dropped, `-`
bullets come back as `*`, blank lines are inserted after a heading or before a
list, and a soft line break becomes a literal `<br>`. A fenced block is the
documented exception and is returned verbatim.

The frozen acceptance criterion is therefore not whole-document equality.
§2.3 line 358 requires that content survives write → read-back **"byte-exact
inside the `` ```json `` fence"**. Whole-document bytes are recorded here for the
record and gate nothing.

The one-byte difference (76 → 75) is exactly the documented dropped trailing
newline, and nothing else: recomputing the written payload locally reproduces
`b3206f81…`, and applying only that single transformation reproduces the
observed read hash `8c94cd89…` exactly. No undocumented rewriting occurred.

### JSON fence — the frozen criterion

```text
JSON_FENCE_BYTE_EQUALITY   PASS

written fence bytes   30
read fence bytes      30

written fence SHA-256 153d19202534f4a2f931261056d3624c7871cfea9dffc4cce796fb1f004e5537
read fence SHA-256    153d19202534f4a2f931261056d3624c7871cfea9dffc4cce796fb1f004e5537
```

The fenced payload survived byte for byte. It was extracted between the fence
markers and compared with no normalisation, canonicalisation or re-indentation.

This is what makes a TSA artifact carrier viable: the `` ```json `` envelope of
an Input Manifest, Process Result, Review Result or Human Decision survives a
live round trip unchanged, so `artifact_digest` over it is stable.

## 5. Document fingerprint — `I-4`

```text
before  a7d60d4504a8213824bd239f1b84b1f198eef55aa46ec3c8102731f7e845321b
after   a7d60d4504a8213824bd239f1b84b1f198eef55aa46ec3c8102731f7e845321b

DOCUMENT_FINGERPRINT_EQUALITY  PASS
```

`document_fingerprint` is stable across the live round trip even though the
stored bytes changed, because `canonical_markdown` absorbs exactly the
re-serialization of constraint 11 while keeping fenced content literal.

This is the combination the frozen model depends on and the one `I-4` asked
about: the Architecture Document's `content_fingerprint` binds approval and
currentness, so it must not move when Fibery re-serializes prose around a fence.

**`I-4` = CLEARED.**

## 6. Project container id kind — `I-1`

`I-1` is **not** first-ever evidence. API constraint 8 already records live
verification that `SDLC/Project` `container-entity-id` accepts the Project's
public id and rejects the entity uuid with `parent-entity-not-found`.

What P-1 adds is confirmation through the **new I02 adapter path**:

```text
EXISTING_REPOSITORY_EVIDENCE   Project public-id containment already
                               live-verified (API constraint 8)
P1_ADAPTER_CONFIRMATION        PASS

observed container_entity_id   "27"           (Project public id)
Project entity uuid            368c0490-bda7-11f1-9f37-3f144160159b
```

```text
PROJECT_CONTAINER_ID_KIND = PUBLIC_ID
```

No contradiction with frozen §2 or contract §5 was observed, so the §21
escalation path was not entered.

**`I-1` = CLEARED.**

## 7. Duplicate caller-supplied Document id

The I02 fake assumed a second `create-views` at an existing `fibery/id` is
rejected, and labelled that assumption PROVISIONAL pending this probe. API
constraint 20 covered `entity/create`, not `create-views`, so the views surface
was genuinely unverified.

```text
attempted id      8dee7dd2-979c-473d-8ebb-7503053d2485
attempted name    TSA-P1-PROBE ROOT 20261001T150152Z DUPLICATE ATTEMPT

classification    REJECTED
raised            true
sanitized error   FiberyError: Views method 'create-views' failed: Fibery
                  returned a JSON-RPC error (code -32000); the server's
                  response is not reported.
```

State immediately after the rejected attempt:

| | |
|---|---|
| Root name | unchanged — `TSA-P1-PROBE ROOT 20261001T150152Z` |
| Root placement | unchanged |
| Original content survived | **true** |

The existing Document was neither renamed, re-placed nor clobbered. Live
`create-views` therefore behaves as the fake modelled, which is what makes a
retry at a deterministic id safe after an unknown write outcome.

**How `REJECTED` is established.** The reviewed classifier infers rejection
neither from the exception nor from the state alone. It decides two things
separately and then combines them.

First, what the create attempt itself did, read from the sanitized public
message only — never from the cause chain, which can carry a secret:

```text
CONFIRMED_REJECTION       Fibery answered the CREATE and refused it. The message
                          must identify both the method and the server answer:
                          "Views method 'create-views' failed" AND
                          "returned a JSON-RPC error".
SUCCESS                   no error at all.
UNKNOWN_TRANSPORT_OUTCOME anything else — a timeout, a reset connection, a DNS
                          failure, an opener OSError, a request aborted before
                          a response, a generic message, or a JSON-RPC error
                          from query-views during read-back. Whether the
                          mutation was applied server side is not known.
```

**A read-back failure is not a rejection.** `FiberyClient` phrases every
JSON-RPC failure the same way, so `Views method 'query-views' failed: Fibery
returned a JSON-RPC error …` carries the same server-answer wording while saying
nothing about the preceding `create-views`. Matching the JSON-RPC marker alone
would let a read-back failure masquerade as a confirmed rejection, so the
classifier requires the create method to be named too.

Second, the durable observable state, snapshotted before the attempt and again
after it. A snapshot whose placement or content cannot be read is UNREADABLE,
and an unreadable snapshot is never evidence that nothing changed.

`REJECTED` requires **all five**:

```text
create outcome == CONFIRMED_REJECTION   AND
before snapshot readable                AND
after snapshot readable                 AND
name unchanged                          AND
placement unchanged                     (all non-secret placement fields)   AND
content unchanged                       (compared by SHA-256, never by secret)
```

Precedence where they disagree:

| Observation | Classification |
|---|---|
| any durable state changed | `MUTATED_EXISTING` — even if the transport outcome was unknown, because the damage is established whatever the call reported |
| unchanged, outcome `CONFIRMED_REJECTION` | `REJECTED` |
| unchanged, outcome `SUCCESS` | `IDEMPOTENT` |
| unchanged, outcome `UNKNOWN_TRANSPORT_OUTCOME` | `OTHER_UNKNOWN_OUTCOME` |
| either snapshot unreadable | `OTHER_UNKNOWN_OUTCOME` |

A timeout with unchanged state is therefore **never** `REJECTED`: not knowing
whether the create was applied is not the same as knowing it was refused.

The observation recorded above satisfies all five conditions — the live error
reports a JSON-RPC error (code `-32000`), both snapshots were readable, and
name, placement and content were unchanged — so it classifies `REJECTED` under
the corrected classifier as well. Every measured value in this document is
unchanged.

**The fake's provisional assumption is confirmed. No fake correction is
required**, and the PROVISIONAL label on that behaviour can be retired.

## 8. External placement drift — F row 22

```text
result   NOT_EXECUTED_SAFE_MUTATION_UNAVAILABLE
method   none
```

Row 22 requires an out-of-band placement edit, then detection at fresh
revalidation. The repository wraps exactly two Views methods, `query-views` and
`create-views`. `create-views` sets placement only at create time, and there is
no `update-views` or `delete-views` wrapper anywhere in the client or the
adapter. Inducing live placement drift would mean adding a new Fibery write
capability, which exceeds I03.

**F row 22 = NOT_EXECUTED.** It is explicitly **not** claimed as PASS, and no
placement-mutation API was added to make it green. The row remains open for a
later work item that legitimately owns a placement-update capability.

## 9. Fake versus live

Compared across every dimension the discrepancy rule names — Project root
containment, container id kind, container type, root parentage, child parentage,
root rediscovery, child rediscovery, `DocumentNode` values, `DocumentPlacement`
values, exact caller-supplied ids, content round trip, duplicate-id behaviour:

```text
Fake-vs-live               MATCH
Discrepancy classification NONE
```

No `FAKE_ONLY` difference, no `ADAPTER_BUG`, no `FROZEN_SPEC_CONFLICT`. **I02 is
not reopened**, and no `src/` production file changed for this work item.

## 10. Probe Documents remaining live

No deletion capability exists in the adapter or client, and I03 does not
introduce one, so both probe Documents remain in the scratch Project. Their names
make them unmistakable and they can be removed by hand.

| Role | Document id | Name | Parent |
|---|---|---|---|
| Root | `8dee7dd2-979c-473d-8ebb-7503053d2485` | `TSA-P1-PROBE ROOT 20261001T150152Z` | none |
| Child | `fa4256c9-2659-435d-b00a-1497a38ce9d8` | `TSA-P1-PROBE CHILD 20261001T150152Z` | `8dee7dd2-979c-473d-8ebb-7503053d2485` |

They live in `TSA P-1 SCRATCH — DO NOT USE`
(`368c0490-bda7-11f1-9f37-3f144160159b`). Nothing outside that Project was
created, modified or read destructively.

## 11. Conclusions

| Gate | Result |
|---|---|
| `I-1` | **CLEARED** |
| `I-4` | **CLEARED** |
| F row 22 | **NOT_EXECUTED** |
| F row 23 | **PASS** |
| Fake-vs-live | **MATCH** |
| I02 finalization | **ELIGIBLE** |
| I02 status | **VERIFIED** |

### What VERIFIED means here, and what it does not

The live obligations that gated I02 finalization are discharged:
Project-contained root creation; Project public-id containment; the exact
caller-supplied root id; root placement; root rediscovery; the exact
caller-supplied child id; child nesting; child rediscovery through both
`DocumentNode` and `DocumentPlacement`; fenced-payload round trip; document
fingerprint stability; `create-views` duplicate-id rejection; and fake
consistency.

It does **not** mean F row 22 passed — that row is NOT_EXECUTED, for the reason
in section 8. It does not mean a full TSA cycle was verified: rows beyond 23
belong to later work items, and no cycle, admission, renderer, Architect,
Reviewer, recovery or decision behaviour exists or was exercised.

One live run was performed. It was not repeated, and no cleanup mutation was
made.
