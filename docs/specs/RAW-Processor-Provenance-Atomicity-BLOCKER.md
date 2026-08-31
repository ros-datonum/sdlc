# RAW Processor — Provenance Atomicity Blocker

**Status:** Open. Blocks Standard Requirement candidate creation.
**Raised by:** the §4 investigation the RAW Processor task required before implementation.

## 1. The approved idempotency design

`RAW.Produces` is the partial-processing marker: if it is non-empty the
processor refuses to reprocess. That is safe **only** if the required invariant
holds:

```text
Standard candidate durably exists
=> Standard.Derived From includes the source RAW
=> RAW.Produces includes that candidate
```

The task asked whether a Standard Requirement can be created with
`Derived From = RAW` inside the same Fibery entity-creation mutation.

## 2. Answer: no

Three findings, each verified against the live workspace.

### `entity/create` silently ignores collection fields

Creating an entity with `"SDLC/Derived From": [{"fibery/id": <raw>}]` returns
`success: true` and writes nothing. The field reads back empty.

The read was calibrated to rule out a query mistake: the same entity linked
afterwards with `fibery.entity/add-collection-items` read back as
`{"fibery/id": ["<raw>"]}`, while the entity created with the inline relation
stayed `{"fibery/id": []}`.

There is no error to catch. Trusting the success flag yields unlinked entities.

### Relations need a separate command

```text
fibery.entity/add-collection-items
  args: { type, field, entity: { "<entity uuid>": ["<item uuid>", ...] } }
```

Setting one side populates the inverse, since `Produces` and `Derived From`
share relation id `8002c1d0-9e2c-11f1-91a5-45a5f32849ca`.

### `/api/commands` batches are not transactional

A batch of `[create valid, create invalid]` returned `[true, false]` and the
first entity survived. Sending `[create, add-collection-items]` in one request
is therefore not atomic.

## 3. The failure window

```text
create Standard entity        <- durable
        crash / 429 / timeout
add-collection-items          <- never runs

retry: RAW.Produces is empty  -> processor proceeds
                              -> duplicates the candidate
```

Fibery's ~3 req/s limit makes this window realistic rather than theoretical: a
`429` already interrupted a `project requirement add` run during review.

## 4. Smallest alternative, for approval

Add one **scalar** Text Field to the `Requirement` Database:

```text
Derived From RAW ID
```

Scalar fields *are* written atomically by `entity/create` (this is how
`Source Fingerprint` already works). The processor would then:

```text
create Standard entity WITH Derived From RAW ID = <raw Requirement ID>   <- atomic
add-collection-items to set Produces / Derived From                      <- best effort
```

and the idempotency check becomes "does any Standard Requirement in this Project
carry `Derived From RAW ID = <this RAW>`", which is true the instant the first
candidate becomes durable. The relation stays the human-facing provenance; the
scalar is the machine-checkable marker.

Cost: one Fibery Field, and provenance is briefly represented in two places
until the relation write lands.

Alternatives considered and rejected as larger than necessary:

- **Client-supplied deterministic `fibery/id`** (Fibery does honour a
  caller-generated id). Rejected: the id would have to derive from candidate
  content, and model output is not stable across runs, so a retry would compute
  different ids and duplicate anyway.
- **A local ledger or reconciliation subsystem.** Rejected: introduces a second
  source of truth, which the project prohibits, and is far more than the problem
  needs.

## 5. Decision required

Approve the `Derived From RAW ID` Field (or specify another marker) before
candidate creation is implemented. Until then the processor stops after
validated decomposition and writes nothing to Fibery.
