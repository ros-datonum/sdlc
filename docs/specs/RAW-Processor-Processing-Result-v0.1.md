# RAW Processor — Processing Result and Resume Semantics v0.1

**Status:** Approved design for RAW Requirement processing v0.

Records how the processor stays idempotent without adding any Requirement Field
or relation. The domain provenance model is unchanged:

```text
RAW.Produces  <->  STANDARD.Derived From
```

## 1. Why an artifact is needed

Provenance cannot be written atomically with a candidate entity: Fibery's
`entity/create` silently ignores collection Fields, and `/api/commands` batches
are not transactional (constraints 15 and 16). So `RAW.Produces` alone cannot be
the partial-processing marker — a crash between the entity write and the
relation write would leave `Produces` empty and a retry would duplicate.

The fix is to make candidate identity knowable *before* any candidate exists.

## 2. The Processing Result

One child Document of the RAW Root Document, named:

```text
<RAW Requirement ID> — Processing Result
```

Child nesting uses `fibery/parent-page-id` on `create-views` — undocumented, but
accepted and read back (constraint 19).

It holds the validated decomposition: a version, the RAW Requirement ID, the
candidates each with an assigned key, the findings, and any
`no_candidate_reason`. It is a process artifact, not a Requirement and not a
Database. It carries no chain-of-thought: the model output contract rejects any
field it does not define.

The processor skips this document when reading the RAW document tree, so its own
output is never fed back as requirement source material.

## 3. Candidate keys

After validation, deterministic code assigns `C001`, `C002`, ... in validated
order. The model never chooses them. Once persisted the artifact is immutable
for that attempt; a duplicate key makes it unresumable and is refused.

## 4. Deterministic candidate identity

```text
candidate_fibery_id = uuid5(CANDIDATE_NAMESPACE, "<RAW uuid>:<candidate key>")
```

The namespace is fixed and must never change: changing it orphans every
previously created candidate.

Fibery honours a caller-supplied `fibery/id` (constraint 17) and rejects a
second create at the same id with `entity.error/schema-field-unique-failed`
(constraint 20). Creation is therefore its own existence check, and a retry
targeting the same candidate targets the same entity.

This is execution identity only. It is never a Fibery Field, and it is not the
human Requirement ID.

## 5. Order, and what it guarantees

```text
model runs once
-> validated output
-> Processing Result persisted and read back      <- before any candidate exists
-> per candidate: create at deterministic id
                  assign Requirement ID from public-id
                  set Type/State
                  add Derived From
                  create Root Document in Requirements/Draft
                  write content
                  validate
-> RAW: Process -> Review
```

The invariant that matters:

```text
a Standard candidate exists  =>  the Processing Result already exists
```

so a retry never needs the model to reconstruct candidate identity.

## 6. Resume

Before invoking the model the processor looks for the Processing Result.

- **Absent** — run the model, persist, then apply candidates.
- **Present** — do not invoke the model. Read it, and complete only the missing
  steps for each candidate.
- **More than one** — `PROCESSING_STATE_CONFLICT`. The processor refuses to
  guess which is authoritative.
- **Unparseable or a version it does not read** — `INVALID_PROCESSING_RESULT`.

Each candidate step is independently verifiable, so resume completes exactly
what is missing. An entity already at a candidate's id is checked against the
expected Project and title before adoption, so an unrelated entity is never
silently reused.

## 7. Failure behaviour

A failure before the Processing Result is persisted creates no candidate, and a
retry may call the model again because nothing durable exists.

A failure after it leaves the RAW in `Process` with partial candidates in place.
Nothing is deleted. A retry resumes without the model.

The RAW moves to `Review` only when every candidate is complete and validated.
Zero candidates is a successful outcome when the result records why none was
warranted.
