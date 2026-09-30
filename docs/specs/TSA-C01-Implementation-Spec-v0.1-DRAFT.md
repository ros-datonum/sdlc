# TSA-C01 — Implementation Specification v0.1 DRAFT

**Status:** DRAFT. Not APPROVED, not VERIFIED.
**Implementation authorized:** NO.
**Authority source:** `docs/architecture/TSA-C01-Contract-v0.1.md` (frozen).
**Repository baseline:** `ros-datonum/sdlc`, `main` at `8916d900eec390e9d36673d27755a4a567b6a642`.

This document closes the **implementation-level** decisions the frozen contract
leaves open. It decides mechanism, never authority. Where the contract froze a
rule, this specification restates only enough to bind the mechanism to it, and
**MUST NOT** be read as amending it. No code is written here, and completing this
document does not authorize writing any.

## 0. How to read this document

| Marker | Meaning |
|---|---|
| **SPEC** | An implementation decision this document closes. Implementation MUST follow it. |
| **REUSE** | An existing mechanism used unchanged. Implementation MUST NOT fork or re-version it. |
| **PROBE** | A claim that MUST be confirmed against the live workspace or a live model before it is relied on. |
| **I-n** | An implementation-level open issue this document could not close. |

`MUST`, `MUST NOT`, `MAY` are RFC-2119.

### 0.1 What this document may not reopen

Requirement authority, UX authority, human approval authority, Project-vs-Phase
authority, worker exclusion, synchronous execution, the canonical storage model,
the WHAT/HOW boundary, and the recovery semantics already frozen. Section 21
reports the one place where a frozen rule and a current API are in tension; it is
reported, not redesigned.

## 1. Reused mechanisms

**REUSE.** These are consumed exactly as they exist. No TSA type re-versions them.

| Mechanism | Source | Used for |
|---|---|---|
| `DocumentNode` | `fibery_workspace.py:53-68` | Every TSA Document handle |
| `read_document_content` / `write_document_content` | `fibery_workspace.py:203-207` | Artifact body IO |
| `create_child_document(name, parent_document_id)` | `fibery_workspace.py:209` | Requirement callers only — **not** reused for TSA (3.5, 2.1) |
| `child_documents(parent_document_id)` | `fibery_workspace.py:200` | Discovery under Architecture |
| `read_normative_tree`, `TreeManifest`, `describe_drift` | `normative_tree.py` | Requirement input evidence |
| `document_fingerprint` (canonical Markdown SHA-256) | `normative_tree.py:89-97` | Requirement and UX Document content digests |
| `parse_process_result`, `ProcessResult.is_current` | `process_result.py:230` | Requirement Process evidence |
| `parse_review_result`, `ReviewResult.is_current` | `review_result.py:270` | Requirement Review evidence |
| `hold_workspace(scope)` | `worker_runner_guard.py:78` | Single-writer guard |
| `LocalCliModelRuntime`, `select_runtime` | `model_runtime.py`, `model_runtime_config.py` | Architect and Reviewer invocation |
| `` ```json `` fenced payload in a Markdown Document | `process_result.py:216-227`, `JSON_FENCE` at `:64` | TSA artifact carrier |

**SPEC.** TSA introduces **no** second fingerprint algorithm for Requirement or
UX Document content: `document_fingerprint` is used for both. TSA JSON artifacts
use their own digest (section 6), which is never presented as a Requirement
normative-tree manifest.

---

## 2. U-3 — Project-contained Document adapter

Contract §5 freezes that the Architecture Document is contained **directly** by
the Project entity and that the Project entity id is the authoritative container
identity. The current adapter cannot do this: `create_requirement_document`
hard-codes the Requirement type id (`fibery_http.py:508-510`), and `project init`
deliberately creates no Project Document (`Project-Init-Spec-v0.3.md:206`).

### 2.1 Protocol additions

**SPEC.** One new protocol, `ArchitectureWorkspace`, in `fibery_workspace.py`.
It is **not** a generic entity-document framework: it adds the minimum the
contract requires, parameterised only where Fibery forces it.

```python
class ArchitectureWorkspace(Protocol):
    @property
    def lock_scope(self) -> str: ...

    def read_project(self, project_id: str) -> ProjectRecord | None: ...

    # -- Project-contained Documents ------------------------------------
    def create_project_document(
        self, document_id: str, name: str, project_public_id: str
    ) -> DocumentNode: ...

    def create_tsa_child_document(
        self, document_id: str, name: str, parent_document_id: str
    ) -> DocumentNode: ...

    def documents_attached_to_project(
        self, project_public_id: str
    ) -> list[DocumentNode]: ...

    # -- reused, unchanged ----------------------------------------------
    def create_child_document(
        self, name: str, parent_document_id: str
    ) -> DocumentNode: ...
    def child_documents(self, parent_document_id: str) -> list[DocumentNode]: ...
    def resolve_document(self, document_id: str) -> DocumentNode | None: ...
    def read_document_content(self, secret: str) -> str: ...
    def write_document_content(self, secret: str, markdown: str) -> None: ...
```

**SPEC.** `create_project_document` mirrors `create_requirement_document`
(`fibery_http.py:482-524`) with two substitutions: the container entity type is
the **Project** Database's type id, resolved from the schema, and `fibery/id` is
the **caller's** value rather than one the adapter generates. Everything else is
identical and is not re-derived: client-supplied `documentSecret`,
`fibery/container-app` from the resolved Space id, `fibery/container-type:
"object"`, `fibery/container-entity-id` = the Project **public** id, no
`fibery/Folder`, then read-back.

**SPEC — deterministic ids reach the API.** The caller computes the UUIDv5 of
3.5 **first**, and the adapter **MUST** send that exact value as `fibery/id`. A
TSA create **MUST NOT** generate a `uuid4` internally.

**SPEC — why a new child creator.** The existing `create_child_document`
generates its own id (`document_id = str(uuid.uuid4())`, `fibery_http.py:806`)
and exposes no parameter for the caller's. It is therefore **not** reused
unchanged for TSA: `create_tsa_child_document` is added as an explicit path that
accepts `document_id`. The existing method stays exactly as it is for its current
Requirement callers, which this specification does not touch.

**SPEC.** `documents_attached_to_project` mirrors
`documents_attached_to_requirement` (`fibery_http.py:239`), filtering
`query-views` on `fibery/container-entity-type` = Project type id and
`fibery/container-entity-id` = the Project public id.

| Protocol method | Fibery operation |
|---|---|
| `create_project_document` | `create-views` (`fibery/type: "document"`, container-type `object`, container-entity-type = Project type id) |
| `documents_attached_to_project` | `query-views` filtered by container entity type + public id |
| `create_tsa_child_document` | `create-views` with `fibery/parent-page-id` **and the caller's `fibery/id`** |
| `child_documents` | `query-views` filtered by `fibery/parent-page-id` (unchanged) |
| `resolve_document` | `query-views` `{"filter": {"ids": [id]}}` (unchanged) |
| `read/write_document_content` | `/api/documents/<secret>` (unchanged) |

### 2.2 Verification obligations

**SPEC.** Every create is followed by read-back before the result is used, as
the existing creators already do (`fibery_http.py:521-524`). A create whose
read-back fails is a failure, never a success with a warning.

**SPEC.** Before an Architecture candidate's Fibery id is accepted as machine
identity, the implementation MUST verify all of:

1. **Project containment** — `entity_public_id` equals the target Project's
   public id, and the container entity type is the Project type;
2. **Parentage** — for children, `parent_document_id` equals the Architecture
   Document id;
3. **Identity** — the payload's `cycle_id` and `project_entity_id` match the
   command's;
4. **Uniqueness** — exactly one candidate survives 1–3;
5. **Wrong-project refusal** — any candidate failing 1 aborts the command;
6. **Duplicate refusal** — two or more survivors abort the command.

### 2.2.1 Where each verified value actually comes from

**SPEC.** Verification may only use values the adapter genuinely exposes. This
table is the authority; nothing below assumes a field a record does not carry.

| Value | Source | Status |
|---|---|---|
| Project entity id | `ProjectRecord.id` | exists |
| Project public id | `ProjectRecord.public_id` | **must be confirmed present**; see below |
| Document id | `DocumentNode.id` | exists |
| Document secret | `DocumentNode.secret` | exists |
| `parent_document_id` | `DocumentNode.parent_document_id` | exists |
| container entity **public** id | `DocumentNode.entity_public_id` | exists |
| container entity **type** | **not on `DocumentNode`** | see below |

**SPEC.** `DocumentNode` carries `entity_public_id` but **no container entity
type** (`fibery_workspace.py:53-68`). Two containers of different Databases could
share a public id and be indistinguishable from that record alone.

**SPEC — the repository primitive is client-side filtering.** The existing
Requirement implementation issues `query-views` and then filters the returned
views **in Python**, in the adapter — that is what
`documents_attached_to_requirement` and `child_documents` actually do
(`fibery_http.py:239`, `:786-790`). This specification does **not** describe it
as a server-side constraint, and TSA does not assume one.

**SPEC — `DocumentPlacement`.** Because filtering is client-side, the adapter
**MUST** surface the fields the filter and the validation both need. A closed
record is added beside `DocumentNode`, not replacing it:

```python
@dataclass(frozen=True)
class DocumentPlacement:
    document_id: str
    secret: str | None
    name: str
    container_entity_type: str | None   # the Fibery type id of the container
    container_entity_id: str | None     # the container's PUBLIC id
    parent_document_id: str | None
```

**SPEC — which operations return it.** These three return
`list[DocumentPlacement]` or `DocumentPlacement | None`, and they are the only
sources of placement metadata:

```python
def documents_attached_to_project(self, project_public_id: str) -> list[DocumentPlacement]: ...
def child_placements(self, parent_document_id: str) -> list[DocumentPlacement]: ...
def resolve_placement(self, document_id: str) -> DocumentPlacement | None: ...
```

**SPEC — the exact low-level read.** All three use the Views API `query-views`,
reading `fibery/id`, `fibery/name`, `fibery/container-entity-type`,
`fibery/container-entity-id`, `fibery/parent-page-id` and
`fibery/meta.documentSecret` from each returned view — the same fields
`_to_document` already consumes (`fibery_http.py`), plus the container type that
`DocumentNode` drops. `resolve_placement` filters on
`{"filter": {"ids": [document_id]}}`, the shape `resolve_document` already uses.

**SPEC — validation before adoption.** Every returned `DocumentPlacement` is
validated before adoption. The rule is **not** uniform: a TSA root Document and a
TSA child Document are contained differently in Fibery, so each has its own
predicate and the wrong one **MUST NOT** be applied.

**SPEC — root placement (`is_valid_root_placement`).** Applies to the
**Architecture** Document only — the one Document TSA attaches directly to the
Project. All four conditions must hold:

```text
1. placement.container_entity_type == <Project Database type id>
2. placement.container_entity_id   == <target Project public id>
3. placement.parent_document_id    is None
4. neither container field is None or empty
```

Condition 3 is normative: a Document that is contained by the Project **and**
nested under some other Document is not a TSA root. An unset
`container_entity_type` or `container_entity_id` is a **refusal**, not a pass.

**SPEC — child placement (`is_valid_child_placement`).** Applies to every TSA
child Document (Input Manifest, Process Result, Review Result, Human Decision).
A child is **not** contained by the Project — it is nested under the Architecture
Document — so its own container fields are **not** compared against the Project.
Validation is two-step and ordered:

```text
1. placement.parent_document_id == <Architecture Document id, from 3.5>
2. then resolve the PARENT's placement and require
   is_valid_root_placement(parent_placement) against the same Project
```

Step 2 is what ties the child to the Project. Checking a child's own
`container_entity_id` against the Project public id is **wrong** and **MUST NOT**
be done: a nested view carries whatever container the Views API reports for a
child page, and the contract's containment guarantee (contract §5) runs through
the root.

**SPEC — placement freshness, not invocation-wide caching.** A validated
placement result is **not** valid for the life of a command. It MAY be reused
only inside **one bounded validation snapshot**, and the snapshot ends at least
when any of these occurs:

```text
- a model call begins;
- a remote mutation is attempted;
- a remote mutation completes;
- a required post-write / read-back validation begins;
- control returns to another lifecycle or recovery step;
- any operation after which external Fibery state may have changed.
```

Crossing any of those boundaries **invalidates every placement result held**.

**SPEC — revalidate immediately before every mutation.** Before **every** remote
mutation whose correctness depends on ownership or parentage, the engine **MUST**
freshly resolve and validate the placement facts that mutation relies on. For a
child write, immediately before the write and with nothing in between:

```text
1. resolve the child / target placement, where one applies;
2. freshly resolve the Architecture root placement;
3. is_valid_root_placement — direct Project containment, no parent;
4. is_valid_child_placement — exact expected Architecture parentage;
5. only then mutate.
```

This is the placement half of the mutation cycle of 14.1, not a separate rule.

**SPEC — a placement read from before a model call is dead.** A placement result
obtained **before** a model call **MUST NOT** be reused for any write **after**
that call. A model call is the longest gap in the command and the one across
which external Fibery state is most likely to have moved.

**SPEC — read-back too.** Post-write read-back and currentness validation
**MUST** use **fresh** placement reads wherever containment or parentage is part
of the assertion. Re-asserting the pre-write placement would make the read-back
prove nothing about the state the write actually landed in.

**SPEC — this is optimistic revalidation, not isolation.** No transaction, no
snapshot isolation and no lock over Fibery state is claimed or available. A
freshly validated placement can still be invalidated by a concurrent external
edit between validation and write; that residual window is why the read-back of
14.1 exists and why drift at read-back is a failure, never a warning.

**SPEC — what an implementation cache may be.** A memo of a placement read MAY
exist purely as a local optimization **inside one validation operation**. It
**MUST NOT** cross a revalidation boundary as defined above, and no part of this
specification may be implemented by widening it to command scope.

**SPEC — which predicate applies where.**

| Document | Predicate |
| --- | --- |
| `tsa.architecture` | `is_valid_root_placement` |
| `tsa.input_manifest` | `is_valid_child_placement` |
| `tsa.process_result` | `is_valid_child_placement` |
| `tsa.review_result` | `is_valid_child_placement` |
| `tsa.human_decision` | `is_valid_child_placement` |

**SPEC — wrong-Project detection for a deterministic id.** A directly resolved
deterministic id (3.5) is checked through `resolve_placement`, **not**
`resolve_document`: `resolve_document` returns a `DocumentNode`, which carries no
container type and therefore cannot answer the ownership question. This is the
path by which a foreign-Project or foreign-Database Document occupying the
derived id is detected, and it is why the extra record exists. For an
Architecture id the check is `is_valid_root_placement`; for any child id it is
`is_valid_child_placement`, which reaches the Project through the root.

**SPEC.** If `ProjectRecord` does not expose `public_id`, the minimum extension
is to add it, populated from the same `fibery/public-id` field the Requirement
record already reads. No other field is added, and `DocumentNode` is **not**
extended: adding a container-type field would change a record three frozen
capabilities already consume.

**SPEC — Project identity.** Resolution **MUST** expose both the Project
**entity id** and the Project **public id**: the entity id is the container
identity the contract freezes (contract §5), the public id is what
`fibery/container-entity-id` actually carries. If `ProjectRecord` does not expose
`public_id`, the minimum extension is to add it, populated from the same
`fibery/public-id` field the Requirement record already reads. No other field is
added, and `DocumentNode` is **not** extended: `DocumentPlacement` carries the
new data instead, so three frozen capabilities keep their record unchanged.

**SPEC — `P-1` scope.** `P-1` verifies **live Fibery behaviour** of the adapter
specified here. It does **not** fill an unspecified API: every method, field and
query above is specified before the probe runs, and the probe either confirms it
or contradicts it under the discrepancy rule of 2.3.

**SPEC — repository evidence.** Project **public-id** containment is not a
choice between two designs: `create_requirement_document` already passes the
entity's **public** id as `fibery/container-entity-id`, with the comment that
passing the uuid fails with `parent-entity-not-found`
(`fibery_http.py:516-520`). The Project case is specified the same way for that
reason. `P-1` verifies the **live behaviour** of that established shape; it is
not design authority and does not choose a storage model.

### 2.3 Live probe

**PROBE — `P-1`.** Nothing in this section may be claimed verified until a
read-only-then-narrow-write probe on a scratch Project confirms, on the live
workspace: that a Document can be created contained by a Project entity; that
`documents_attached_to_project` returns it; that `create_child_document` nests
under it; that `child_documents` returns the child; and that content survives
write → read-back byte-exact inside the `` ```json `` fence.

**SPEC — fake-vs-live discrepancy rule.** The in-memory fake used by `D` tests
MUST be corrected to match any observed live behaviour, and a regression test
MUST be added for the discrepancy, **before** the capability is recorded as
verified. A green fake is never integration proof (`.claude/CLAUDE.md`, Fibery
integration rule).

---

## 3. Cycle identity and discovery

### 3.1 Representation

**SPEC.** A cycle id is a caller-supplied string matching:

```text
^[a-z0-9]([a-z0-9-]{1,38}[a-z0-9])$          # 3..40 chars, lowercase
```

**SPEC.** Canonical form: NFC, trimmed, lowercased. Input differing only by case
or surrounding whitespace normalises to the same cycle id. Anything else that
does not match the pattern is `INVALID_CYCLE_ID` — no coercion, no generation.

**SPEC.** Uniqueness is scoped to **one Project**. The same cycle id in two
Projects is two cycles. Within one Project the same cycle id always means the
same cycle (contract §12.1).

**SPEC.** The cycle id is generated by the caller **before** the first remote
mutation and never by the engine mid-command (contract §12.1). A UUIDv4 string
is an acceptable caller choice but is not required.

### 3.2 Where it is stored

**SPEC.** The authoritative location is the `cycle_id` field of the artifact
envelope (section 5) inside every TSA Document for that cycle, including the
Architecture Document itself. The Document **name** carries it too
(`<Project Code> — TSA <cycle-id> — Architecture`), but only as human navigation
metadata (contract §5.1).

### 3.3 Recognising an Architecture shell

**SPEC.** A Project-contained Document is an Architecture shell for cycle `C`
when: it is contained by the target Project entity; its body parses as a TSA
envelope with `artifact_type = "tsa.architecture"`; and its `cycle_id` equals `C`.
A Document whose body is empty, or is non-empty but unparseable, is **not** a
shell — it is classified by section 14.4.

### 3.4 Candidate classification

**SPEC.** Discovery lists `documents_attached_to_project`, then filters by the
recognition rule of 3.3. Names **MAY** narrow the candidate list first; they
**MUST NOT** decide identity.

| Surviving candidates | Classification | Action |
|---|---|---|
| 0 | State **A** | Create is permitted |
| 1 | State **B**/**C**/**D** by its children | Adopt its Fibery id |
| ≥2 | State **E** | `CYCLE_AMBIGUOUS` — refuse, create nothing |
| any owned by another Project | State **E** | `CYCLE_FOREIGN_PROJECT` — refuse |

**SPEC.** Classification is by the **deterministic id** of 3.5, not by name
search. `resolve_document(derived_id)` answers the question directly: absent ⇒
create permitted; present ⇒ validate and adopt or refuse. A body that is empty
is still an adopted shell, never a reason to create a second Document.

**SPEC.** Name-based listing (`documents_attached_to_project`) remains available
as a **diagnostic** and to detect a foreign Document occupying the expected name,
but it never decides identity and never authorises a create.

### 3.5 Deterministic Document identity

**SPEC.** Every TSA Document's Fibery id is **derived**, not generated. It is
computable before the first create, recomputable after any restart, and
identical for the same logical artifact forever. No journal and no local state
are involved.

**SPEC — namespace constant.**

```text
TSA_DOCUMENT_NAMESPACE = 9164554b-34b0-5f02-8f0c-6050170c7eee
```

derived reproducibly as
`uuid5(uuid.NAMESPACE_URL, "https://github.com/ros-datonum/sdlc/tsa/v1")`, so the
literal can be re-verified rather than trusted.

**SPEC — derivation.** UUID **version 5** (SHA-1 based), over the UTF-8 encoding
of a `|`-delimited tuple. No trailing delimiter, no padding, no whitespace.

```text
architecture     UUIDv5(NS, "<workspace_identity>|<project_entity_id>|<cycle_id>|architecture")
input_manifest   UUIDv5(NS, "<workspace_identity>|<project_entity_id>|<cycle_id>|input_manifest")
iterated         UUIDv5(NS, "<workspace_identity>|<project_entity_id>|<cycle_id>|<artifact_type>|<iteration>")
```

**SPEC — tuple components.**

| Component | Exact form |
|---|---|
| `workspace_identity` | `host/<space-uuid>`, as `FiberyClient.workspace_identity` renders it |
| `project_entity_id` | the Fibery entity id, verbatim |
| `cycle_id` | the **canonical** form of 3.1 (NFC, trimmed, lowercased) |
| `artifact_type` | the short vocabulary below, **not** the `tsa.` prefixed envelope value |
| `iteration` | zero-padded to exactly four digits: `0001` … `0999` |

**SPEC — short artifact-type vocabulary**, closed:

```text
architecture      input_manifest      process_result
review_result     human_decision
```

`architecture` and `input_manifest` are the two **non-iterated** artifacts and
use the three-part tuple; the other three always carry `|<iteration>`.

**SPEC — normative id vectors.** With
`workspace_identity = "example.fibery.io/11111111-2222-4333-8444-555555555555"`,
`project_entity_id = "proj-1"`, `cycle_id = "arch-2026-09-a"`:

| Artifact | Derived Fibery id |
|---|---|
| architecture | `0576efe5-1d70-515e-b587-0a39f85ce6f2` |
| input_manifest | `3800ce1f-893d-5324-8539-d2e2e842ad55` |
| process_result, iteration 1 | `cae8d621-7c7d-5b18-9531-9e34a503d4fe` |
| review_result, iteration 1 | `3f02b5c6-40ea-566f-a545-d47c0a6cbada` |
| human_decision, iteration 1 | `91404f8c-fd19-5c15-ac72-e65d93dec39d` |
| process_result, iteration 2 | `5b1448bb-1430-5a49-8b62-13001e8f1939` |

**SPEC — create.** Every create passes this exact value as `fibery/id`, which
the existing creators already support (`fibery_http.py:495`, `:506`).

**SPEC — unknown create outcome.** The recovery is a direct identity lookup, for
**every** artifact type including children:

1. recompute the deterministic id from the tuple;
2. `resolve_document(id)`;
3. if **absent** → the create did not land; retry the create with **the same
   deterministic id**, never a new one;
4. if **present** → validate placement (2.2.1 — root predicate for
   `tsa.architecture`, child predicate otherwise), envelope `artifact_type`,
   `cycle_id`, `project_entity_id` and lineage (4.6);
   - all valid → adopt;
   - malformed, foreign-Project, or lineage-conflicting → **refuse**
     (`ARTIFACT_MALFORMED` / `CYCLE_FOREIGN_PROJECT` / `ARTIFACT_DUPLICATE`).

**SPEC.** A deterministic id **does not by itself prove ownership**. Containment
**MUST** still be validated on the resolved Document: a colliding or
maliciously pre-created id is detected there, not by the derivation.

**SPEC.** Names remain human navigation metadata only (contract §5.1). Discovery
by name is a diagnostic aid; identity is the derived id.

**SPEC.** Because the id is a pure function of durable inputs, a restart
recomputes it with no journal, and a duplicate create is structurally impossible:
a second create with the same id targets the same Document.

**SPEC.** After an unknown create outcome, rediscovery is exactly this procedure
re-run (contract §5.1.1). There is **no** local database, journal or cached
intent: every classification is derived from durable Fibery state.

---

## 4. U-4 — the TSA artifact envelope

### 4.1 Carrier

**SPEC.** Every immutable TSA artifact is one Fibery Document whose Markdown is:
a level-1 heading with the artifact's human name, one short prose paragraph, and
exactly one `` ```json `` fenced payload — the pattern of
`process_result.py:216-227`, parsed back with the same `JSON_FENCE` shape.

**SPEC.** The Architecture Document is different: it is human-readable Markdown
under the 16 frozen headings (section 9), **plus** one trailing `` ```json ``
envelope carrying its machine metadata and traceability block. Its prose is the
canonical architecture; the fence is metadata about it.

### 4.2 Common envelope fields

**SPEC.** Every TSA artifact payload is a JSON object with these keys:

| Key | Type | Rule |
|---|---|---|
| `artifact_type` | string | One of the five in 4.3 |
| `schema_version` | integer | `1` for this specification |
| `workspace_identity` | string | `host/<space-uuid>`, as `FiberyClient.workspace_identity` renders it |
| `project_entity_id` | string | Fibery entity id |
| `project_code` | string | Human code; never identity |
| `cycle_id` | string | Canonical form, section 3.1 |
| `iteration` | integer or absent | Present for Process/Review/Decision; absent for Manifest and Architecture |
| `body` | object | The artifact-specific payload |
| `artifact_digest` | string | Lowercase hex SHA-256, section 5.2 |

**SPEC.** `artifact_digest` is computed over the payload **with the
`artifact_digest` key removed**. A payload never hashes a field containing its
own digest. This is the only self-reference rule and it applies to all five
artifact types.

### 4.3 Artifact types

```text
tsa.architecture      the Architecture Document's metadata envelope
tsa.input_manifest    the immutable input set (section 8)
tsa.process_result    one Architect iteration (section 9)
tsa.review_result     one Reviewer iteration (section 10)
tsa.human_decision    one REWORK or APPROVE (section 12)
```

### 4.4 Validation policy

**SPEC.** Unknown keys are **rejected**, at every level of a TSA payload. The
Requirement-side model contracts already reject unknown fields
(`standard_prompt.py`, "Unknown fields are rejected"); an artifact read back
from Fibery is held to the same standard, because a key the reader does not
understand may be exactly the one carrying authority.

**SPEC.** A non-empty artifact that does not parse, fails schema validation,
carries an unknown key, or whose recomputed `artifact_digest` differs from the
stored one, is **malformed**. Malformed artifacts **fail closed**: refuse, never
repair, never overwrite, never treat as absent (contract §14.3 case 8).

**SPEC.** An **empty** Document body is not malformed: it is an empty shell,
handled by contract §14.3 case 7 and section 14.4 here.

**SPEC.** `schema_version` mismatch is a refusal, not a migration. This
specification defines version `1` only.


### 4.5 Iteration

**SPEC.** `iteration` is a positive integer. The first Architect run of a cycle
is **`1`**. Permitted range `1..999`; `1000` is `ITERATION_LIMIT`. It increments
by exactly one, and **only** when a `REWORK` decision is persisted (contract
§6). Re-running a command never increments it.

**SPEC.** For one iteration `N` there is **at most one** `tsa.process_result`, at
most one `tsa.review_result` and at most one `tsa.human_decision`, all carrying
`iteration = N`. Two artifacts of one type with the same `iteration` is
`ARTIFACT_DUPLICATE`.

**SPEC.** `iteration` is **present** on `tsa.process_result`,
`tsa.review_result`, `tsa.human_decision`; **absent** on `tsa.input_manifest`
and `tsa.architecture`. Presence where absence is required, or the reverse, is a
schema error.

### 4.6 Closed body schemas

**SPEC.** These five schemas are closed and complete. Unknown keys are rejected
at every level (4.4). `?` marks optional; everything else is required. All
digests and fingerprints are lowercase hex SHA-256 strings of length 64. All
timestamps are RFC-3339 UTC with a `Z` suffix and second precision.

**SPEC.** Two conforming implementations cannot choose different wire formats:
every key, type and presence rule below is fixed.

#### 4.6.1 `tsa.architecture`

```text
body.cycle_id                    string   canonical cycle id (3.1)
body.created_at                  string   timestamp
body.manifest_digest?            string   absent until the manifest is accepted
body.content_fingerprint?        string   document_fingerprint of this Document's
                                          Markdown, absent on an empty shell
body.current_iteration?          integer  highest iteration with a Process Result
body.traceability?               array    rows of 8.2; absent until first apply
body.traceability[*].requirement_id  string
body.traceability[*].anchors         array of string, non-empty
body.traceability[*].how_satisfied   string
body.traceability[*].constraints     array of string
body.traceability[*].gaps            array of string
body.assumptions?                array    of string; present once output applied
body.risks?                      array    of { detail: string,
                                               impact: "LOW"|"MEDIUM"|"HIGH" }
body.open_architecture_questions? array   of string
body.product_questions?          array    of { detail: string,
                                               requirement_id: string,
                                               material: boolean }
```

**SPEC.** A newly created Architecture Document carries `cycle_id` and
`created_at` only — that is the **bootstrap metadata** that makes the shell
recoverable (section 3.5). Every other key appears when an iteration's output is
applied.

**SPEC — presence rule for the renderer-owned arrays.** `assumptions`, `risks`,
`open_architecture_questions` and `product_questions` are **absent before the
first apply** and, from the first apply onward, are **always present as arrays**,
empty when the iteration produced none. There is no null and no omission once the
document holds applied output.

**SPEC — schema/renderer closure.** The body above is exactly the set of
renderer-owned fields `intended_output` carries (4.6.3.1), plus the four
bootstrap and binding fields (`cycle_id`, `created_at`, `manifest_digest`,
`content_fingerprint`, `current_iteration`). Applying an iteration is therefore a
total copy:

```text
body.traceability                 ← intended_output.traceability
body.assumptions                  ← intended_output.assumptions
body.risks                        ← intended_output.risks
body.open_architecture_questions  ← intended_output.open_architecture_questions
body.product_questions            ← intended_output.product_questions
```

with `intended_output.sections` rendered into the sixteen Markdown headings.
**No renderer-owned field exists outside this closed schema**, and no field is
dropped or invented on the way in: the twelve `sections` keys are consumed by the
renderer, the five arrays are copied verbatim, and `content_fingerprint` is then
computed over the rendered Markdown excluding the envelope.

**SPEC.** `content_fingerprint` is `document_fingerprint` (REUSE) over the
Document's Markdown **excluding** the trailing envelope fence, so the fingerprint
does not depend on itself. The excluded region is exactly the final
`` ```json `` … `` ``` `` block.

#### 4.6.2 `tsa.input_manifest`

```text
body.manifest_body               object   section 7.2, digested as 5.4
body.manifest_digest             string
body.acceptance                  object   section 7.4
```

**SPEC.** `iteration` absent. `manifest_body` is immutable once written;
`acceptance` is written in the same create (13.1) and never edited afterwards.

#### 4.6.3 `tsa.process_result`

```text
body.manifest_digest             string   binds the accepted inputs
body.architecture_document_id    string
body.input_fingerprint           string   Architecture content_fingerprint BEFORE apply
body.intended_output             object   the COMPLETE renderer input, 4.6.3.1
body.architect_response          object   the validated Architect payload (9.1),
                                          verbatim, unknown keys already rejected
body.runtime                     object
body.runtime.role                string   "tsa_architect"
body.runtime.model?              string   omitted when the CLI default was used
body.created_at                  string
```

##### 4.6.3.1 `intended_output` — the complete renderer input

**SPEC.** `intended_output` is the **complete normalized input of the
Architecture renderer**. It **MUST** carry every field §8.3 consumes, so the
exact intended Document is reproducible without another model call, without
consulting `architect_response`, and without defaulting or inventing any prose.

```text
intended_output.sections                      object  the 12 Architect section keys of 9.1
intended_output.traceability                  array   rows of 8.2, ordered by requirement_id
intended_output.assumptions                   array of string
intended_output.risks                         array of { detail: string,
                                                         impact: "LOW"|"MEDIUM"|"HIGH" }
intended_output.open_architecture_questions   array of string
intended_output.product_questions             array of { detail: string,
                                                         requirement_id: string,
                                                         material: boolean }
```

**SPEC.** All six keys are **required**; the five arrays MAY be empty; `sections`
carries all twelve keys. Unknown keys are rejected (4.4).

**SPEC.** `product_questions` is carried here because §8.3 preserves
product-question evidence in the Architecture envelope, and contract §7.4
requires that evidence to survive. It is renderer input even though it produces
none of the 16 headings.

**SPEC — the replay identity.** The renderer is a pure function:

```text
render(intended_output, manifest_body) → canonical Architecture Markdown
                                       → content_fingerprint
```

`manifest_body` contributes only the generated `Source` column (8.3) and is
itself immutable, so the pair is fixed for an iteration. Case 2 replay **MUST**
reproduce **the same bytes and the same `content_fingerprint`**. A replay
producing different bytes is `ARCHITECTURE_RENDER_INVALID`, never an accepted
write.

**SPEC.** `architect_response` stays persisted as evidence and for `M`-class
review, but recovery cases 2 and 3 **MUST** read only `intended_output`. An
implementation that re-derives the document from `architect_response` is
non-conforming.

**SPEC.** `body.artifact_digest` does not exist; the digest lives on the envelope
(4.2) and is the artifact's Process digest wherever the contract says "Process
Result payload digest".

#### 4.6.4 `tsa.review_result`

```text
body.manifest_digest             string
body.process_result_document_id  string
body.process_result_digest       string   the envelope artifact_digest of 4.6.3
body.architecture_document_id    string
body.architecture_fingerprint    string   content_fingerprint reviewed
body.reviewer_response           object   the validated Reviewer payload (10.1)
body.derived_status              string   enum of 10.2
body.runtime                     object   as 4.6.3, role "tsa_reviewer"
body.created_at                  string
```

**SPEC.** `derived_status` is computed by code (10.2) and stored so `inspect` and
`approve` need not recompute it from prose; it is still revalidated against
`reviewer_response` on read, and a disagreement is `ARTIFACT_MALFORMED`.

#### 4.6.5 `tsa.human_decision`

Body exactly as section 11, restated here as the closed key list:

```text
body.decision                    string   "REWORK" | "APPROVE"
body.target                      object   section 11.1
body.target.iteration            integer
body.target.review_result_document_id  string
body.target.review_result_digest       string
body.architecture_document_id    string
body.architecture_fingerprint    string
body.manifest_digest             string
body.ux_evidence_digest          string
body.process_result              object   { document_id, payload_digest }
body.review_result               object   { document_id, payload_digest }
body.accepted_dispositions       array    of { ref, reason }, possibly empty
body.reason?                     string
body.recorded_at                 string
```

**SPEC — lineage invariants**, checked on every read of any artifact:

1. every artifact's `cycle_id` and `project_entity_id` equal the Architecture
   Document's;
2. every `manifest_digest` equals the Input Manifest's;
3. a Review Result's `process_result_digest` names a Process Result of the
   **same** `iteration`;
4. a Human Decision's `target.review_result_digest` names a Review Result of the
   same `iteration`;
5. a Human Decision's `architecture_fingerprint` equals the Review Result's;
6. `accepted_dispositions[*].ref` resolves under section 6;
7. `render(process_result.intended_output, manifest_body)` reproduces exactly the
   `content_fingerprint` the Architecture Document carries once that iteration's
   output is applied — checked on every case-2 and case-3 classification.

A violated invariant is `ARTIFACT_MALFORMED`, never a repairable state.

---

## 5. Canonical JSON serialization and digest

This closes U-4 technically. It is deliberately precise enough that two
independent implementations produce identical bytes.

### 5.1 Canonical form

**SPEC.**

1. **Encoding** — UTF-8, no BOM, no trailing newline.
2. **Value types** — object, array, string, integer, boolean only.
   **Floating-point numbers are forbidden**; so is `null`.
3. **Absent vs null** — an optional field that has no value **MUST be omitted**.
   `null` is never emitted and never accepted.
4. **Object keys** — ASCII only, matching `^[a-z][a-z0-9_]*$`, sorted ascending
   by code point. Restricting keys to ASCII removes the UTF-16-vs-code-point
   ordering ambiguity that would otherwise need resolving.
5. **Separators** — `,` and `:` with **no** whitespace anywhere outside string
   literals.
6. **Strings** — normalised to **NFC** before serialization; emitted as real
   UTF-8 (`ensure_ascii=False`); escaped only where JSON requires it (`"`, `\`,
   and control characters `U+0000`–`U+001F` as `\u00XX`, except `\b \f \n \r \t`
   which use their short forms).
7. **Integers** — decimal, no leading zeros, no `+`, no exponent; `-0` is
   forbidden.
8. **Arrays** — order is significant and preserved exactly as the schema defines.

### 5.1.1 Reused subtrees — the serialization boundary

**SPEC.** Rules 2, 3 and 6 of 5.1 bind **TSA-owned** values only. A **reused
subtree** is a payload produced by an existing repository mechanism and embedded
verbatim; TSA does not own its semantics and **MUST NOT** rewrite them.

**SPEC.** For schema version 1 there is exactly **one** reused subtree:

```text
tsa.input_manifest → body.manifest_body.requirements[*].tree_manifest
                     = TreeManifest.to_payload()   (Requirement manifest v2)
```

**SPEC.** Inside a reused subtree:

1. its field and value semantics **MUST NOT** be rewritten, normalised or
   reinterpreted;
2. `null` **is permitted** where the producing mechanism emits it;
3. strings **MUST NOT** be NFC-normalised;
4. no key-name restriction of 5.1.4 applies.

**SPEC.** A reused subtree is serialized by the producing mechanism's own
canonical rule, embedded as those exact bytes:

```python
json.dumps(subtree, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
```

which is `normative_tree._canonical_bytes` (`normative_tree.py:451-457`) — the
same ordering and separators TSA uses, differing only in permitting `null` and
not normalising Unicode. The digest therefore preserves the subtree's exact
semantic value.

**SPEC.** No new Requirement manifest version is created. The embedded value is
manifest **v2**, unchanged.

**Why this boundary is mandatory, not stylistic.** The manifest carries its own
`normative_tree_fingerprint`, computed over its entries. Applying TSA's NFC rule
to a manifest holding a decomposed Unicode Document name changes those entries,
so the stored fingerprint no longer matches — and
`TreeManifest.from_payload` then **rejects the payload outright**:

```text
InvalidTreeManifest: The declared normative tree fingerprint does not
match the manifest.
```

Verified against `normative_tree.py:204` at this baseline. NFC-normalising a
reused subtree does not merely alter a digest; it destroys the artifact.

**SPEC.** A reader **MUST** validate an embedded manifest with
`TreeManifest.from_payload` (REUSE). A manifest that fails that call makes the
whole TSA artifact malformed (4.4).

Reference definition:

```python
def canonical_json(value: object) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    )
```

with all strings NFC-normalised and all keys validated against 5.1.4 **before**
the call. `json.dumps` is not itself the specification; the rules above are, and
a validator MUST reject any value the rules forbid rather than rely on the
library's defaults.

### 5.2 Digest

**SPEC.** Domain-separated SHA-256:

```python
def artifact_digest(artifact_type: str, schema_version: int, payload: dict) -> str:
    body = {k: v for k, v in payload.items() if k != "artifact_digest"}
    prefix = f"sdlc.tsa.v1\n{artifact_type}\n{schema_version}\n"
    return hashlib.sha256((prefix + canonical_json(body)).encode("utf-8")).hexdigest()
```

**SPEC.** The prefix binds the digest to its artifact type and schema version, so
an identical body under a different type or version digests differently. The
literal `sdlc.tsa.v1` is the domain tag of this specification and changes only
with a new digest scheme.

**SPEC.** `artifact_digest` is excluded from its own input (4.2). No other field
is excluded.

### 5.3 Test vectors

**SPEC.** These are normative. An implementation that does not reproduce them
exactly is wrong. Computed against the definition above.

| # | type | ver | canonical bytes | digest |
|---|---|---|---|---|
| 1 | `tsa.input_manifest` | 1 | `{}` | `5abac6256c44bab88f54fc5c50fb57b7ff1a42c70f9efa107636c7eebd986804` |
| 2 | `tsa.input_manifest` | 1 | `{"a":2,"b":1}` | `2835effdc8d98d1141a39359f44c011669ac9cfc2dc8a0ce683febbceb0c5eb3` |
| 3 | `tsa.process_result` | 1 | `{"a":{"b":"c","y":"x"},"z":[3,1,2]}` | `9da4e049c9c7b5d784bd6d9183cb9cd2589209a658b2d6c24a6a2fbdce6a53ac` |
| 4 | `tsa.human_decision` | 1 | `{"reason":"架構 — é"}` | `e4b95ef40323909ad1a38301cc50c708eab33931a58a6984cf2ba349c37bef2d` |
| 5 | `tsa.review_result` | 1 | `{"count":0,"iteration":1}` | `1f0dcaa550973d78da0b70ae6799dd7b20bb94c7b356d06c765ecf84ec767a26` |

Vector 2 pins key ordering; vector 3 pins nested ordering with array order
preserved; vector 4 pins NFC and non-ASCII emission; vector 5 pins integer form
and that `0` is emitted, not omitted.

**Vector 6 — reused subtree with `null` and decomposed Unicode.** Body:

```text
requirement_id  = "SDLC-FR-0007"
tree_fingerprint = "a"*64
tree_manifest   = TreeManifest(
    requirement_id="SDLC-FR-0007", root_document_id="doc-root",
    entries=(TreeEntry("doc-root", None, "Cafe\u0301 design", "a"*64),
             TreeEntry("doc-child", "doc-root", "Child", "b"*64))
).to_payload()
```

with `("tree_manifest",)` declared a reused path. The manifest's own
`normative_tree_fingerprint` is
`2e8e2d81a31883d9e7abb953e600934c31e1278938150cc66856224636226cb1`.

```text
type   tsa.input_manifest      version 1
digest fe4a508fa8056d4030e2fa4d1dc64752e460ed29b6de8714f0cd783bd6518ddf
```

This vector is normative and proves both required properties: the TSA digest is
deterministic over a body containing `parent_document_id: null` and a decomposed
`e` + `U+0301`; and the embedded manifest still validates through
`TreeManifest.from_payload` with its fingerprint unchanged, because the subtree
was embedded verbatim rather than normalised.


### 5.4 Sub-digest families

**SPEC.** Three sub-digests exist besides `artifact_digest`. Each has its own
domain tag, so the same bytes under two roles never collide. All use SHA-256 and
lowercase hex. None excludes any field of its input object; each input object is
named exactly.

```python
def sub_digest(tag: str, value: object) -> str:            # version is always 1
    return hashlib.sha256(
        (f"sdlc.tsa.v1\n{tag}\n1\n" + canonical_json(value)).encode("utf-8")
    ).hexdigest()
```

| Digest | Domain tag | Exact input object |
|---|---|---|
| `requirement_input_digest` | `tsa.requirement_input` | the whole ordered `manifest_body.requirements` **array** |
| `ux_evidence_digest` | `tsa.ux_evidence` | the whole `manifest_body.ux` **object**, whichever branch |
| `manifest_digest` | `sdlc.tsa.manifest.v1` | the whole `manifest_body` **object** — dedicated formula below |

**SPEC.** `canonical_json` here is 5.1 **with 5.1.1 applied**: every
`requirements[*].tree_manifest` is a reused subtree and is embedded verbatim.

**SPEC — `manifest_digest` has its own authoritative formula**, and it is the
**only** definition of that value anywhere in this specification:

```python
manifest_digest = hashlib.sha256(
    ("sdlc.tsa.manifest.v1\n" + canonical_json(manifest_body)).encode("utf-8")
).hexdigest()
```

The shape differs from the generic `sub_digest` helper: the tag line is
`sdlc.tsa.manifest.v1` and there is **no** separate version line, because the
version is inside the tag. `tsa.input_manifest_body` **MUST NOT** be used as a
manifest-digest domain — it no longer exists — and `tsa.input_manifest` is the
envelope `artifact_type`, a different thing.

**SPEC — one tag per family.** Each family has exactly one authoritative domain,
and no domain carries two meanings:

| Family | Domain | Shape |
|---|---|---|
| `artifact_digest` | `sdlc.tsa.v1` + `artifact_type` + `schema_version` | 5.2 |
| `requirement_input_digest` | `sdlc.tsa.v1` + `tsa.requirement_input` + `1` | `sub_digest` |
| `ux_evidence_digest` | `sdlc.tsa.v1` + `tsa.ux_evidence` + `1` | `sub_digest` |
| `manifest_digest` | `sdlc.tsa.manifest.v1` | dedicated, above |

**SPEC — recomputation, not comparison.** A reader **MUST** recompute each
sub-digest from the canonical source values it has just read, and compare the
result with the stored field. Comparing one stored field against another stored
field proves nothing: a tampered body carrying a matching tampered digest would
pass. A mismatch is `ARTIFACT_MALFORMED`.

**SPEC.** `ux_evidence_digest` is computed over the `ux` object for **both**
branches, so a `NOT_APPLICABLE` record is bound exactly as strongly as an
`APPLICABLE` one, with no UX Document involved.

**SPEC — no circularity.** `requirement_input_digest` covers `requirements`
only. `ux.requirement_input_digest` (NOT_APPLICABLE branch) stores that value, so
`ux_evidence_digest` depends on it — one direction only. `manifest_digest` covers
`manifest_body`, which contains both. `acceptance` lives **outside**
`manifest_body` (7.1) and therefore cannot feed back into `manifest_digest`.
`artifact_digest` covers the whole payload minus itself. The dependency order is
strictly:

```text
requirements → requirement_input_digest → ux → ux_evidence_digest
            → manifest_body → manifest_digest → acceptance → artifact_digest
```

### 5.5 Sub-digest vectors

**SPEC.** Normative, computed from the fixture below. `<M>` is the vector-6
manifest payload of 5.3.

```text
requirements = [ { "requirement_id": "SDLC-FR-0007", "entity_id": "e-1",
                   "tree_manifest": <M>, "tree_fingerprint": "a"*64,
                   "process_result": { "document_id": "p-1", "iteration": 3,
                                       "payload_digest": "c"*64 },
                   "review_result":  { "document_id": "r-1",
                                       "payload_digest": "d"*64 } } ]

ux_APPLICABLE     = { "kind": "APPLICABLE", "document_id": "ux-1",
                      "content_digest": "e"*64,
                      "scope_requirement_ids": ["SDLC-FR-0007"],
                      "approval": { "accepted": true,
                                    "recorded_at": "2026-09-29T18:00:00Z" } }

ux_NOT_APPLICABLE = { "kind": "NOT_APPLICABLE",
                      "reason": "No user-facing surface.",
                      "requirement_input_digest": <R>,
                      "decision": { "accepted": true,
                                    "recorded_at": "2026-09-29T18:00:00Z" } }

manifest_body     = { "workspace_identity":
                        "example.fibery.io/11111111-2222-4333-8444-555555555555",
                      "project_code": "SDLC", "project_entity_id": "proj-1",
                      "cycle_id": "arch-2026-09-a",
                      "created_at": "2026-09-29T18:00:00Z",
                      "requirements": requirements, "ux": ux_APPLICABLE }
```

| Digest | Value |
|---|---|
| `requirement_input_digest` `<R>` | `8d993bb0938335a8897a5f22b8af9311187bb003d0704f189b73675abdd0b605` |
| `ux_evidence_digest` (APPLICABLE) | `f8b222d6839d0ffe725ba59f95353067f0d2bc01e0c6d304b0414a6a484ad378` |
| `ux_evidence_digest` (NOT_APPLICABLE) | `d2fc5ebd736ab831a3161c0d73d5280f6329e07bae0a0450c358691c7beac67a` |
| `manifest_digest` (tag `sdlc.tsa.manifest.v1`) | `15bc34b97823e3e2e443267c347b474abfa00242226cfa886bd971ff8083daba` |

The two `ux_evidence_digest` values differ under the same tag, which is the
point: the discriminator is inside the hashed object, so the branches can never
be confused.

---

## 6. Stable finding, risk and disposition identity

Contract §9 binds accepted findings and risks **individually**, and matrix row 49
requires unknown or duplicated references to be refused. That needs identities
that are stable across reads and reproducible from an immutable payload.

### 6.1 Reference grammar

**SPEC.** One vocabulary, used by the Reviewer, by Human Decisions and by
`inspect`. No aliases exist; every name below is a literal key in the schemas of
sections 9 and 10.

```text
reference  = digest "#" collection "/" index
digest     = 64 lowercase hex characters          the source artifact_digest
collection = one of the literals in 6.2
index      = "0" | [1-9][0-9]*                    zero-based, no leading zeros
```

**SPEC.** `index` addresses the zero-based position in that array **of the
artifact whose `artifact_digest` prefixes the reference**. `0` is valid; `00`,
`-1` and `1.0` are not.

### 6.2 Allowed collections, by source artifact type

**SPEC.** A reference is valid only for these exact pairs. Any other
`collection`, or a collection used against the wrong artifact type, is
`DISPOSITION_UNKNOWN_REFERENCE`.

| Source artifact | Allowed `collection` | Array in the schema |
|---|---|---|
| `tsa.process_result` | `assumptions` | `architect_response.assumptions` |
| `tsa.process_result` | `risks` | `architect_response.risks` |
| `tsa.process_result` | `open_architecture_questions` | `architect_response.open_architecture_questions` |
| `tsa.process_result` | `product_questions` | `architect_response.product_questions` |
| `tsa.review_result` | `claim_verifications` | `reviewer_response.claim_verifications` |
| `tsa.review_result` | `new_findings` | `reviewer_response.new_findings` |
| `tsa.review_result` | `material_unresolved_what` | `reviewer_response.material_unresolved_what` |

**SPEC.** The Architect schema of section 9 has **no** `findings` array; its
claim-bearing collections are exactly the four above. The earlier draft listed
`findings` and `open_questions`, which do not exist in that schema — corrected
here so every collection name maps to a real key.

### 6.3 What the Reviewer refers to, and how

**SPEC.** All three cases use the same grammar; only the collection differs.

| The Reviewer is addressing | Reference it uses |
|---|---|
| an Architect **product question** | `<process_digest>#product_questions/<i>` |
| an Architect **technical risk** | `<process_digest>#risks/<i>` |
| a **material unresolved WHAT** it raises itself | its own `<review_digest>#material_unresolved_what/<i>` |

**SPEC — exactly-once verification coverage.** Every Architect claim requiring
verification — the union of `risks`, `open_architecture_questions` and
`product_questions` of that iteration's Process Result — **MUST** appear
**exactly once** as a `claim_ref` in `claim_verifications`. `assumptions` are
context, not claims, and are **not** required to be verified.

- a required claim absent from `claim_verifications` is
  `REVIEW_COVERAGE_INCOMPLETE`;
- the same `claim_ref` twice is `REVIEW_COVERAGE_DUPLICATE`;
- a `claim_ref` outside that union is `DISPOSITION_UNKNOWN_REFERENCE`.

### 6.4 Validation rules

**SPEC.** Consequences, all deterministic:

- **Uniqueness** — guaranteed by construction: one array position, one id.
- **Immutability** — the payload is immutable, so positions never shift.
- **Cross-artifact** — the digest prefix names exactly which artifact the item
  came from, so a Reviewer finding and an Architect risk can never collide.
- **Cross-iteration** — iteration N+1 produces a different artifact digest, so
  its item ids differ. A disposition **MUST** reference an id whose digest
  belongs to the iteration being decided; a reference to another iteration's
  artifact is `DISPOSITION_FOREIGN_ITERATION`.
- **Reference validation** — an id whose digest does not match a persisted
  artifact of this cycle, or whose index is out of range, is
  `DISPOSITION_UNKNOWN_REFERENCE`.
- **Duplicates** — the same id twice in one decision is
  `DISPOSITION_DUPLICATE_REFERENCE`.

- **Foreign artifact** — a digest that resolves to an artifact of another cycle,
  or to no persisted artifact of this cycle, is
  `DISPOSITION_UNKNOWN_REFERENCE`.
- **Out of range** — an `index` beyond the array's length is
  `DISPOSITION_UNKNOWN_REFERENCE`.
- **Wrong type** — a collection not allowed for that artifact type (6.2) is
  `DISPOSITION_UNKNOWN_REFERENCE`.

**SPEC.** Human Decision `accepted_dispositions[*].ref` consumes **this same
vocabulary** — the same grammar, the same collections, the same refusals. There
is no second reference format anywhere in this specification.

**SPEC.** A disposition **MUST NOT** reference `material_unresolved_what`: a
material WHAT is not waivable inside TSA (contract §9.3), so accepting one is
`DISPOSITION_NOT_WAIVABLE`, distinct from an unknown reference.

**SPEC.** No authenticated human identity is invented anywhere in this scheme
(contract §9.4).

---

## 7. Input Manifest schema

### 7.1 Resolving the digest recursion

Contract §3.1 requires the manifest to carry both *a digest of the complete
manifest* and *human acceptance bound to that digest*. Read literally that is
circular. **SPEC — two layers:**

```text
manifest_body          ← the input set; contains no acceptance and no digest
      │
      ├─ canonical_json → sha256 (domain "sdlc.tsa.manifest.v1") → manifest_digest
      │
acceptance             ← binds manifest_digest; never part of manifest_body
      │
artifact payload       = envelope + body{manifest_body, manifest_digest, acceptance}
      │
      └─ artifact_digest over the payload minus artifact_digest
```

**SPEC.** `manifest_digest` is the value the human accepts and the value every
later binding (contract §9) refers to. It is stable under a later acceptance
write because `acceptance` is outside `manifest_body`. `artifact_digest` covers
the whole artifact including the acceptance, so tampering with the acceptance is
detectable without changing what was accepted.

### 7.2 `manifest_body`

```json
{
  "workspace_identity": "example.fibery.io/<space-uuid>",
  "project_code": "SDLC",
  "project_entity_id": "<uuid>",
  "cycle_id": "arch-2026-09-a",
  "created_at": "2026-09-29T18:00:00Z",
  "requirements": [
    {
      "requirement_id": "SDLC-FR-0007",
      "entity_id": "<uuid>",
      "tree_manifest": { "normative_tree_version": 2, "…": "…" },
      "tree_fingerprint": "<sha256>",
      "process_result": {
        "document_id": "<uuid>",
        "iteration": 3,
        "payload_digest": "<sha256>"
      },
      "review_result": {
        "document_id": "<uuid>",
        "payload_digest": "<sha256>"
      }
    }
  ],
  "ux": { "…": "discriminated union, 7.3" }
}
```

**SPEC.** `requirements` is ordered by `requirement_id` ascending, so the same
selection always produces the same digest regardless of CLI argument order.
Duplicate `requirement_id` or duplicate `entity_id` is `SELECTION_DUPLICATE`.
The array MUST be non-empty (contract §2).

**SPEC.** `tree_manifest` embeds `TreeManifest.to_payload()`
(`normative_tree.py:169`) verbatim — manifest v2, unmodified and not
re-versioned. `tree_fingerprint` is its Root `content_fingerprint`.

**SPEC.** `payload_digest` for a Requirement's Process or Review Result is
`document_fingerprint(<the Result Document's canonical Markdown>)` — the
existing Requirement-side algorithm (REUSE), not the TSA JSON digest. These are
Requirement artifacts and are digested the Requirement way.

### 7.3 UX discriminated union

**SPEC.** Exactly one shape, selected by `kind`:

```json
{ "kind": "APPLICABLE",
  "document_id": "<uuid>",
  "content_digest": "<sha256 via document_fingerprint>",
  "scope_requirement_ids": ["SDLC-FR-0007", "SDLC-NFR-0002"],
  "approval": { "accepted": true, "recorded_at": "<iso8601>" } }
```

```json
{ "kind": "NOT_APPLICABLE",
  "reason": "<non-empty text>",
  "requirement_input_digest": "<sha256>",
  "decision": { "accepted": true, "recorded_at": "<iso8601>" } }
```

**SPEC.** `NOT_APPLICABLE` **MUST NOT** carry `document_id`, `content_digest` or
`scope_requirement_ids`; their presence is a schema error. This is the structural
guarantee behind contract §4.4: the `APPLICABLE` checks are unreachable for a
`NOT_APPLICABLE` manifest because the fields they read do not exist.

**SPEC.** `requirement_input_digest` is the digest of the ordered
`requirements` array's canonical form, so Requirement-input drift invalidates a
`NOT_APPLICABLE` decision (contract §4.4) without consulting any UX Document.

**SPEC.** `scope_requirement_ids` MUST be a non-empty subset of the manifest's
`requirement_id` values; an id outside the selection is `UX_SCOPE_FOREIGN`.

### 7.4 `acceptance`

```json
{ "manifest_digest": "<sha256>", "accepted": true, "recorded_at": "<iso8601>" }
```

**SPEC.** `accepted` MUST be `true` — a recorded acceptance is the only admissible
value; refusal is simply the absence of the artifact. `manifest_digest` MUST equal
the sibling field; a mismatch is `MANIFEST_ACCEPTANCE_MISMATCH` and the manifest
counts as **not accepted** (contract §3.3).

---

## 8. Architecture Document representation

### 8.1 Template

**SPEC.** The Document is Markdown with exactly the 16 frozen headings of
contract §8, at level 2, in the frozen order, each rendered as
`## <n>. <Heading>` with `n` its contract position. No heading is omitted,
renamed, reordered or added.

**SPEC.** A *Content-or-N/A* section whose content does not apply holds exactly:

```text
N/A — <reason on one line>
```

A *Mandatory* section holding that literal form is `SECTION_MANDATORY_EMPTY`.

**SPEC.** Empty-list sections (`Assumptions`, `Risks`,
`Open Architecture Questions`) use `None identified.` rather than N/A when the
Architect considered them and found none. This mirrors the Open-Questions
discipline the Requirement engine already enforces: an explicit "none" is an
answer, silence is not.

### 8.2 Traceability

**SPEC.** Section 2 of the Document holds a Markdown table, and the same rows
appear machine-readably in the trailing envelope's `body.traceability`:

| Requirement ID | Source | Architecture anchors | How satisfied | Constraints honoured | Gaps |
|---|---|---|---|---|---|

```json
"traceability": [
  { "requirement_id": "SDLC-FR-0007",
    "anchors": ["tsa-s03", "tsa-s05"],
    "how_satisfied": "<text>",
    "constraints": ["<text>"],
    "gaps": [] }
]
```

**SPEC.** Deterministic validation, all of which a validator can decide without
semantics:

- the set of `requirement_id` values equals the manifest's selection **exactly** —
  every included Requirement appears **exactly once** (contract §8.1);
- an id not in the manifest is `TRACEABILITY_UNKNOWN_REQUIREMENT`;
- a repeated id is `TRACEABILITY_DUPLICATE_REQUIREMENT`;
- a missing id is `TRACEABILITY_MISSING_REQUIREMENT`;
- `anchors` is non-empty and every entry matches `^tsa-s(0[1-9]|1[0-6])$`
  (8.3.1) — **one-to-many is allowed**; heading text is never an anchor, and any
  entry outside the grammar is `TRACEABILITY_UNKNOWN_ANCHOR`;
- the Markdown table rows and the JSON rows agree on ids and anchors.

**SPEC.** Whether the architecture *actually satisfies* the Requirement is
Reviewer work and is never claimed by the validator (contract §8.1).

### 8.3 Deterministic rendering

**SPEC — section mapping.** The 12 Architect `architecture` keys map to the 16
frozen headings one-to-one, and the remaining four are generated by code, not by
the model:

| # | Heading | Source |
|---|---|---|
| 1 | Scope & Inputs | `architecture.scope_and_inputs` |
| 2 | Requirement Traceability | **generated** from `traceability` (8.2) |
| 3 | Solution Structure | `architecture.solution_structure` |
| 4 | Components & Responsibilities | `architecture.components_and_responsibilities` |
| 5 | Interfaces & Data Flows | `architecture.interfaces_and_data_flows` |
| 6 | Data / Storage | `architecture.data_storage` |
| 7 | External Integrations | `architecture.external_integrations` |
| 8 | Security / Authentication / Authorization | `architecture.security_authn_authz` |
| 9 | Deployment / Runtime Model | `architecture.deployment_runtime_model` |
| 10 | Failure / Recovery | `architecture.failure_recovery` |
| 11 | Observability | `architecture.observability` |
| 12 | Migration Implications | `architecture.migration_implications` |
| 13 | Architecture Decisions / Trade-offs | `architecture.architecture_decisions` |
| 14 | Assumptions | **generated** from `assumptions` |
| 15 | Risks | **generated** from `risks` |
| 16 | Open Architecture Questions | **generated** from `open_architecture_questions` |

**SPEC — exact templates.** Generated sections render one Markdown list item per
array entry, in array order, or the single literal line `None identified.` when
the array is empty. `escape_markdown` is the function of 8.3.1.

| Section | Source array | Exact line template |
|---|---|---|
| 14 Assumptions | `assumptions` (string) | `- <esc(item)>` |
| 15 Risks | `risks` `{detail, impact}` | `- <esc(detail)> — Impact: <esc(impact)>` |
| 16 Open Architecture Questions | `open_architecture_questions` (string) | `- <esc(item)>` |

**SPEC.** `product_questions` is **not** rendered into any of the 16 headings. It
is preserved verbatim in the trailing envelope as `body.product_questions`, so
the evidence survives without becoming architecture prose. A `material: true`
entry is what makes approval unavailable (contract §7.4); rendering it as prose
would invite reading it as a decision.

**SPEC.** Each rendered list is followed by exactly one blank line before the
next heading; sections are separated by exactly one blank line; the document ends
with a single newline before the trailing envelope fence.

### 8.3.1 Escaping

**SPEC — one escaping function.** `escape_markdown(value)` is the **only**
escaping defined by this specification. It applies to **every** model-supplied
string placed into generated Markdown — table cells, list items, rendered
paragraphs, everything — and no other escaping rule exists anywhere in this
document. There is no per-context variant.

```text
escape_markdown(value):
  0. value := value with leading and trailing whitespace stripped
  1. map each character of the stripped value, once, by this table
  2. return the concatenation of the mapped characters
```

| Source character | Replacement |
|---|---|
| `\` | `\\` |
| `\|` | `\\\|` |
| `\r\n`, `\r`, `\n` | `<br>` |
| `<` | `&lt;` |
| `>` | `&gt;` |
| any other character | itself |

`\r\n` is consumed as **one** source sequence and yields **one** `<br>`; it does
not produce two.

**SPEC — single-pass, no re-scanning.** The mapping is applied **character by
character to the original stripped input**, and output produced by the table is
**never re-scanned**. This is what makes the order in the table descriptive
rather than operative: the `<` and `>` of a `<br>` introduced by the newline rule
are output, not input, so they are not turned into `&lt;br&gt;`. Implementing
this as a sequence of whole-string `replace()` calls is **non-conforming**,
because that re-scans earlier output. No Markdown library is involved, so the
result is independent of any library's behaviour.

**SPEC — array-valued table cells.** `constraints`, `gaps` and `anchors` render
into one cell each. Every element is passed through `escape_markdown`
**independently**, then the results are joined in source order with exactly the
literal `<br>`, emitted after escaping so it is never itself escaped. An empty
array renders as an empty cell.

**SPEC — anchors, one form only.** Every heading is rendered as

```text
## <n>. <Heading> <!-- anchor: tsa-s<nn> -->
```

with `<nn>` **always two digits**. The grammar is exactly

```text
^tsa-s(0[1-9]|1[0-6])$
```

so the sixteen anchors are `tsa-s01` … `tsa-s16`. No one-digit form exists
anywhere. Anchors are assigned by code from the frozen order and are unique by
construction; a duplicate anchor in rendered output is a renderer defect
(`ARCHITECTURE_RENDER_INVALID`). `traceability[*].anchors` entries are these
anchor strings, never free-form heading text; an entry outside the grammar is
`TRACEABILITY_UNKNOWN_ANCHOR`, and the same anchor twice in one Requirement row
is `TRACEABILITY_DUPLICATE_ANCHOR`.

**SPEC — envelope placement.** The trailing `` ```json `` metadata fence sits
**after** heading 16 and is **outside** all sixteen normative sections. It is
excluded from `content_fingerprint` (4.6.1), so that fingerprint covers the
sixteen sections and nothing else.

**SPEC — the `Source` column.** Column 2 of the traceability table is generated
by code from the Input Manifest, not supplied by the model: it renders
`<requirement_id> @ <tree_fingerprint first 12 hex chars>`. The model cannot
influence it, so it cannot misattribute a source.

**SPEC — ordering.** Traceability rows are ordered by `requirement_id`
ascending, matching the manifest order (7.2), so the rendered document is a
deterministic function of the manifest and the Architect response.

**SPEC — duplicate anchors within one Requirement mapping.** `anchors` is a
**set** semantically: the same anchor twice in one row is
`TRACEABILITY_DUPLICATE_ANCHOR`. Across different Requirements the same anchor
**is** allowed — that is the one-to-many case the contract permits.

---

## 9. Architect output contract

### 9.1 Response shape

**SPEC.** `tsa_architect` returns **one JSON object**, no prose, no reasoning
trace, matching exactly:

```json
{
  "architecture": {
    "scope_and_inputs": "…", "solution_structure": "…",
    "components_and_responsibilities": "…", "interfaces_and_data_flows": "…",
    "data_storage": "…", "external_integrations": "…",
    "security_authn_authz": "…", "deployment_runtime_model": "…",
    "failure_recovery": "…", "observability": "…",
    "migration_implications": "…", "architecture_decisions": "…"
  },
  "traceability": [ { "requirement_id": "…", "anchors": ["…"],
                      "how_satisfied": "…", "constraints": ["…"], "gaps": ["…"] } ],
  "assumptions": ["…"],
  "risks": [ { "detail": "…", "impact": "LOW|MEDIUM|HIGH" } ],
  "open_architecture_questions": ["…"],
  "product_questions": [ { "detail": "…", "requirement_id": "…",
                           "material": true } ]
}
```

**SPEC.** All twelve `architecture` keys are **required**; the four list keys are
required and MAY be empty arrays. `requirement_traceability` is not a prose
section — it is generated from `traceability`. Unknown keys are rejected.

**SPEC.** `impact` and `material` are closed enums/booleans. `material: true`
marks a product question the Architect judges necessary for a correct HOW; code
uses it to make approval unavailable (contract §7.4, §9.3), and a Reviewer may
disagree (section 10).

**SPEC.** The response **MUST NOT** contain mutation instructions, Fibery ids it
was not given, Requirement state changes, Epics, Stories, Tasks, estimates,
sprint sequencing, implementation assignments, code blocks other than
illustrative diagrams, or deployment commands.

### 9.2 Deterministic vs semantic

**SPEC.** A validator decides: schema conformance; unknown keys; all 16 sections
produced; traceability coverage (8.2); enum validity; the absence of
structurally recognisable Tasks/Epics/estimates/code blocks; input-size bounds.

**SPEC.** A validator does **not** decide: whether the architecture is
adequate; whether prose smuggles a Task or invents a product obligation; whether
a conflict was detected. Those are Reviewer or live-probe evidence (contract §16
rows 15, 17, 24, 25, 30, 36).

---

## 10. Reviewer output contract

### 10.1 Response shape

**SPEC.** `tsa_reviewer` returns **one JSON object**:

```json
{
  "claim_verifications": [
    { "claim_ref": "<artifact_digest>#<collection>/<index>",
      "outcome": "CONFIRMED|REJECTED|UNRESOLVED",
      "severity": "INFO|WARNING|BLOCKING",
      "reason": "…" }
  ],
  "traceability_verification": {
    "outcome": "CONFIRMED|REJECTED|UNRESOLVED", "reason": "…" },
  "new_findings": [
    { "kind": "…", "severity": "INFO|WARNING|BLOCKING",
      "detail": "…", "requirement_id": "…" }
  ],
  "material_unresolved_what": [
    { "detail": "…", "requirement_id": "…" } ],
  "assessment": {
    "completeness": "…", "internal_consistency": "…",
    "source_fidelity": "…", "traceability": "…",
    "implementability": "…" }
}
```

**SPEC.** `severity` is present **only** on `CONFIRMED` verifications and on
`new_findings`, mirroring the Requirement Review rule that REJECTED and
UNRESOLVED assert no defect (`review_prompt.py`).

**SPEC.** There is **no verdict field**. The overall status is derived by code,
as the Standard Review pattern already does (`standard_review.py`). The Reviewer
MUST NOT state approval, recommend an action, or propose replacement wording.

### 10.2 Derived status

**SPEC.** Code derives, in this precedence:

| Condition | Derived status |
|---|---|
| Any structural invalidity (schema, digest, binding, traceability) | `REVIEW_STRUCTURALLY_INVALID` |
| Any `material_unresolved_what` entry, or any Architect `product_questions` entry with `material: true` not rejected by the Reviewer | `REVIEW_BLOCKED_ON_WHAT` |
| Any `BLOCKING` severity | `REVIEW_BLOCKING` |
| Any `WARNING` severity | `REVIEW_NEEDS_WORK` |
| Otherwise | `REVIEW_PASS` |

**SPEC.** Waivability, exactly as contract §9 freezes it:

- `REVIEW_STRUCTURALLY_INVALID` — **never** waivable; approval unavailable.
- `REVIEW_BLOCKED_ON_WHAT` — **never** waivable inside TSA; resolution is a
  Requirement change and a new cycle.
- `REVIEW_BLOCKING` / `REVIEW_NEEDS_WORK` on **technical** risk — a human **MAY**
  accept individually, by disposition reference (section 6), recorded with a
  reason. Acceptance never deletes the finding.

---

## 11. Human Decision schema

**SPEC.** `body` of a `tsa.human_decision` artifact:

```json
{
  "decision": "REWORK|APPROVE",
  "architecture_document_id": "<uuid>",
  "architecture_fingerprint": "<sha256 via document_fingerprint>",
  "manifest_digest": "<sha256>",
  "ux_evidence_digest": "<sha256>",
  "process_result": { "document_id": "<uuid>", "payload_digest": "<sha256>" },
  "review_result":  { "document_id": "<uuid>", "payload_digest": "<sha256>" },
  "accepted_dispositions": [
    { "ref": "<artifact_digest>#new_findings/2", "reason": "…" } ],
  "reason": "…",
  "recorded_at": "<iso8601>"
}
```

**SPEC.** `ux_evidence_digest` is the digest of the manifest's `ux` object in
canonical form — one field for both branches, so the `NOT_APPLICABLE` record is
bound just as strongly as an `APPLICABLE` document digest, with no UX Document
required.

**SPEC.** No `approved_by`, no account, no identity claim (contract §9.4).

**SPEC — REWORK.** MUST reference the same `manifest_digest` as the cycle's
Input Manifest; authorizes iteration N+1 only; MUST NOT carry a scope change.
A `REWORK` **targeting an iteration that already carries an `APPROVE`** is
`DECISION_CONFLICT` under the precedence of 11.1.1. Symmetrically, an `APPROVE`
targeting an iteration that already carries a `REWORK` is also
`DECISION_CONFLICT`. In both directions the durable decision at the exact target
iteration decides the outcome, and nothing is written.

**SPEC — APPROVE.** Before persist, the exact tuple above is revalidated
(section 14); after persist it is read back and revalidated. Success is reported
only after read-back. It closes the cycle to writes (contract §6).

### 11.1 Target binding

**SPEC.** A decision command identifies the exact Human Decision boundary it
targets with `body.target`:

```text
target.iteration                       integer
target.review_result_document_id       string
target.review_result_digest            string
```

**SPEC.** The target is **supplied explicitly by the caller**, never inferred.
`rework` and `approve` both require:

```text
--cycle <cycle-id>
--iteration <N>
--review-result-id <fibery-document-id>
```

There is **no** implicit "current Review" selection. An operator who does not
know the triple runs `inspect` first.

**SPEC — resolution order**, before any write:

1. resolve the exact cycle from `--cycle`;
2. resolve the exact iteration `N` from `--iteration`;
3. resolve the supplied `--review-result-id`;
4. verify that Review Result belongs to **all** of: the same Project; the same
   cycle; exactly iteration `N`; the Process Result current for `N`; the exact
   Architecture fingerprint it reviewed; the cycle's Input Manifest. Any
   mismatch is `REVIEW_NOT_CURRENT`, and nothing is written;
5. look up the **deterministic** Human Decision id for `(cycle, N)` (3.5)
   through `resolve_placement`.

#### 11.1.1 Precedence — frozen

**SPEC.** A decision command evaluates exactly this order, and **no other order
is admissible anywhere in this specification**:

```text
1. resolve and validate the target triple    (11.1 steps 1-4)
       cycle, iteration N, review-result-id
2. target resolution failed
     -> stop with the target-resolution error:
          CYCLE_NOT_FOUND / CYCLE_AMBIGUOUS / CYCLE_FOREIGN_PROJECT /
          ARTIFACT_MALFORMED / ARTIFACT_DUPLICATE / INPUTS_STALE /
          <the shell rule of 13.7-7>   where one of those governs,
          otherwise REVIEW_NOT_CURRENT.
        STOP. Nothing is written. No model is called.
3. look up the deterministic Human Decision id for (cycle, N)
4. a durable, non-empty Human Decision exists at that id
     -> semantic comparison (11.3)
          equivalent      -> DECISION_ALREADY_RECORDED, exit 0
          not equivalent  -> DECISION_CONFLICT,          exit 1
     -> STOP. Nothing is written. No further rule is evaluated.
5. a valid current Review exists and NO Decision exists
     -> this state IS the Human Decision boundary, by definition
     -> validate, write, read back
```

**SPEC — there is no separate admissibility test.** Step 5 is not a permission
check that can fail; it is the **definition** of the boundary. "A valid, current
Review Result for the exact target, with no Decision recorded against it" **is**
the Human Decision boundary, so a command that reaches step 5 is at the boundary
and proceeds. This specification therefore defines **no** "not at boundary"
refusal — under that name or any other — and no result code may be added to
express one.

**SPEC — why a boundary refusal has no state to describe.** Every state that is
not the boundary is already decided earlier:

```text
no resolvable cycle              -> step 2   CYCLE_NOT_FOUND / _AMBIGUOUS / _FOREIGN_PROJECT
no valid current Review for N    -> step 2   REVIEW_NOT_CURRENT
Review malformed / duplicated /
  an empty shell / over stale
  inputs                         -> step 2   that specific rule
a Decision already exists at N   -> step 4   DECISION_ALREADY_RECORDED / _CONFLICT
valid Review, no Decision        -> step 5   the boundary itself
```

The five branches are exhaustive, so nothing is left over for a boundary refusal
to name.

**SPEC — what this settles.** Idempotency outranks everything after target
resolution. A retried `rework` or `approve` whose decision is already durable
returns the idempotent answer **even when the cycle has since moved past that
boundary** — which is the entire point, because a retry after an unknown write
outcome (14.3 case 9) is exactly the case where the boundary has already
advanced. Symmetrically, an invalid or non-current Review target can **never**
fall through to decision handling: step 2 stops first.

**SPEC — the cross-decision cases.** Both mismatches resolve the same way at
step 4, and neither reaches step 5:

| Durable at target iteration `N` | Command | Result | Exit |
|---|---|---|---|
| `APPROVE` | `rework --iteration N` | `DECISION_CONFLICT` | 1 |
| `REWORK` | `approve --iteration N` | `DECISION_CONFLICT` | 1 |
| `APPROVE` | `approve --iteration N`, same tuple | `DECISION_ALREADY_RECORDED` | 0 |
| `REWORK` | `rework --iteration N`, same tuple | `DECISION_ALREADY_RECORDED` | 0 |
| either | same decision, **different** tuple | `DECISION_CONFLICT` | 1 |

In every row nothing is written and no model is called; an approved cycle stays
closed.

**SPEC — why no "already approved" code exists.** In an approved cycle **every**
iteration that a decision command can legally target already carries a durable
Decision: iterations `1 … N-1` carry the `REWORK` that opened the next one, and
iteration `N` carries the `APPROVE` that closed the cycle. An iteration beyond
`N` has no Review Result, so target resolution fails at step 2 with
`REVIEW_NOT_CURRENT`. Step 4 therefore always matches, step 5 is unreachable for
an approved cycle, and a distinct "cycle already approved" refusal has no state
that can emit it. An **empty** Decision shell at the target id does not create
one either: that is `DECISION_SHELL_UNRECOVERABLE` (13.7-7), which stops at
step 2.

**SPEC — empty shell at the Decision id.** An **empty** Human Decision shell at
the deterministic id is not a durable decision: step 3 does not match it, and the
command stops with `DECISION_SHELL_UNRECOVERABLE` (13.7-7) rather than falling
through to step 4.

**SPEC — retry cannot slide forward.** Because `--iteration N` and
`--review-result-id` are explicit, a retried `rework` after `REWORK` already
opened `N+1` still targets `N`, finds the existing decision, and is an idempotent
no-op. It can never be read as a decision about `N+1`, and it can never open
`N+2`.

### 11.2 Idempotency procedure

**SPEC.** Every decision command runs this order, before any write:

1. resolve and verify `target` (11.1 steps 1–4);
2. search the cycle for an existing `tsa.human_decision` with that
   `target.iteration`;
3. if none exists → validate, generate `recorded_at` **once**, write, read back;
4. if exactly one exists → compare **semantic equivalence** (11.3):
   - equivalent → `DECISION_ALREADY_RECORDED`; write nothing; the durable
     `recorded_at` is **preserved**, never rewritten;
   - not equivalent → `DECISION_CONFLICT`; write nothing;
5. if more than one exists → `ARTIFACT_DUPLICATE`, write nothing.

**SPEC.** Step 4 is never skipped: an existing decision is **never**
unconditionally reported as `DECISION_ALREADY_RECORDED`. The comparison decides
between that code and `DECISION_CONFLICT`.

**SPEC.** After an unknown write outcome, the command **MUST** re-run steps 1–2
and compare before attempting any further write (contract §14.3 case 9).

### 11.3 Semantic equivalence

**SPEC.** Two decisions are semantically equivalent when **all** of these match:

```text
decision, target.iteration, target.review_result_document_id,
target.review_result_digest, architecture_document_id,
architecture_fingerprint, manifest_digest, ux_evidence_digest,
process_result.document_id, process_result.payload_digest,
review_result.document_id, review_result.payload_digest,
the multiset of accepted_dispositions[*].ref
```

**SPEC.** `recorded_at`, `reason` and `accepted_dispositions[*].reason` are
**excluded** from the comparison. A timestamp that differs on a retry **MUST
NOT** defeat idempotency. The durable record's original `recorded_at` is kept;
the retry never rewrites it.

**SPEC.** `accepted_dispositions` compares as a multiset of `ref` values, so
argument order does not create a false conflict; a repeated `ref` within one
command is already `DISPOSITION_DUPLICATE_REFERENCE` (6.4).

---

## 12. U-7 — CLI surface

**SPEC.** Five commands under `sdlc project architecture`, registered in the
existing `argparse` style (`cli.py:170-186`), non-interactive, no hidden prompt.

### 12.1 `start`

```text
sdlc project architecture start
  --project <CODE|entity-id>        required
  --cycle <cycle-id>                required
  --requirement <REQUIREMENT-ID>    required, repeatable
  --ux applicable|not-applicable    required
  --ux-document <fibery-doc-id>     required iff --ux applicable
  --ux-scope <REQUIREMENT-ID>       repeatable; defaults to all selected
  --ux-reason <text>                required iff --ux not-applicable
  --accept-inputs                   required; the explicit human acceptance
  --accept-ux                       required; explicit UX approval/decision
```

**SPEC.** `--requirement` repeated is the scope-selection syntax; a `--from-file`
form is **not** introduced, matching the repeated-flag style already used for
`--skills-dir`-like options and avoiding a JSON blob on the command line.

**SPEC.** Normalisation: Requirement ids are upper-cased and de-duplicated
**only** by exact match after trimming; a duplicate is reported, not silently
collapsed (`SELECTION_DUPLICATE`). Ordering in the manifest is by id ascending
(7.2), so argument order never changes the digest.

**SPEC.** `--accept-inputs` and `--accept-ux` are the auditable human acceptance
(contract §3.3, §4). Their presence in argv is the record; acceptance is **never**
inferred from the fact that the command ran. Missing either is
`HUMAN_ACCEPTANCE_REQUIRED` and nothing is written.

### 12.2 The other four

```text
sdlc project architecture resume  --project <P> --cycle <cycle-id>

sdlc project architecture rework  --project <P> --cycle <cycle-id>
                                  --iteration <N>
                                  --review-result-id <fibery-doc-id>
                                  [--reason <text>]

sdlc project architecture approve --project <P> --cycle <cycle-id>
                                  --iteration <N>
                                  --review-result-id <fibery-doc-id>
                                  [--accept-risk <ref> --accept-reason <text>]...
                                  --confirm

sdlc project architecture inspect --project <P> --cycle <cycle-id> [--json]
```

**SPEC — the flag is `--cycle` everywhere.** All five commands spell the cycle
selector `--cycle`, taking a cycle id. No alias, no `--cycle-id`, no positional
form.

**SPEC — both decision commands require the full target triple.** `rework` and
`approve` each require `--cycle`, `--iteration` **and** `--review-result-id`
(11.1). The requirement is symmetric: neither command infers any element of the
triple, and a missing flag is an argparse usage error (exit `2`), never an
inferred default. `--reason` and `--accept-risk`/`--accept-reason`/`--confirm`
remain command-specific.

**SPEC.** `--accept-risk` takes a disposition reference (section 6) and is
repeatable, each paired with `--accept-reason`. `--confirm` is the explicit
approval act. `inspect` is read-only and takes `--json` for machine output.

### 12.3 Output and exit codes

**SPEC.** Every command prints its result code on the first line, then human
detail — the existing convention (`render_result`, `cli.py`). Exit `0` for a
normal outcome including no-op refusals that are correct answers
(`DECISION_ALREADY_RECORDED`, `CYCLE_APPROVED`); exit `1` for any refusal or
failure; exit `2` reserved for argparse usage errors. No other exit codes.

---

## 13. Command semantics

**SPEC.** Every mutating command acquires `hold_workspace(lock_scope)` first and
holds it for its whole life (contract §13). `inspect` does not.

### 13.1 `start`

```text
guard → resolve Project → validate selection (§2.1 of the contract)
→ validate UX evidence (§4.1/§4.2) → discover cycle candidates (§3.4)
→ bootstrap gate → create/adopt Architecture shell
→ persist Input Manifest + acceptance → normal gate
→ Architect → persist Process Result → apply output to Architecture
→ Reviewer → persist Review Result → stop at the Human Decision boundary
```

**SPEC.** If the cycle is already past any of these points, `start` does **not**
repeat it: it classifies durable state (contract §14.4 state D) and continues
from there, exactly as `resume` would. `start` and `resume` differ only in that
`start` carries the inputs needed to create a manifest that does not yet exist.

### 13.2 `resume`

**SPEC.** Guard → classify durable state → run the bootstrap gate (states A–C) or
the normal gate (state D) → continue. Never a duplicate model call, never a
duplicate artifact. `resume` on an approved cycle is `CYCLE_APPROVED`, read-only.

### 13.3 `rework`

**SPEC.** Reaches its write only through 11.1.1: a resolvable exact target, a
valid current Review Result and no Decision recorded against it. Persists
`REWORK`, opens iteration N+1 on the **same** Input Manifest, then runs Architect
→ Reviewer → boundary. Every other state is already answered at 11.1.1 step 2 or
step 4; `rework` has no boundary refusal of its own.

### 13.4 `approve`

**SPEC.** Deterministic and **model-free**. Revalidates the exact tuple, validates
every disposition reference (section 6), persists `APPROVE`, reads back,
revalidates. No downstream side effect of any kind: no Epic, Story, Task, no
Requirement, Project or Project Phase write.

### 13.5 `inspect`

**SPEC.** Read-only. Derives lifecycle state and freshness from artifacts alone
(contract §6). No mutation, no model call. Reports per-input currentness using
the discriminator-aware UX definition (contract §4.4).

### 13.6 Command × durable state

**SPEC.** This table is authoritative. Every valid combination has exactly one
action, one result code and one exit class. "Model call" means an Architect or
Reviewer invocation. Bootstrap states A–E are contract §14.4; cases 1–10 are
contract §14.3.

**SPEC — reading the `rework` / `approve` columns.** In states **A**–**D → case
3** the command cannot resolve a valid current Review Result for its exact
target, so the cell is the 11.1.1 step 2 outcome: `CYCLE_NOT_FOUND` in state
**A**, where no cycle resolves at all, and `REVIEW_NOT_CURRENT` in **B**, **C**
and cases **1**–**3**, where the cycle resolves but the targeted Review does not
exist or is not current. Cases **4**, **8**, **9**, and the stale-inputs,
ambiguous and duplicate rows keep their own more specific code, which also
belongs to step 2.

**SPEC — the table obeys 11.1.1.** Every `rework` and `approve` cell is the
result of applying the frozen precedence of 11.1.1, not an independent rule.
Where no valid current Review Result can be resolved for the exact target, the
cell carries the **target-resolution** outcome of 11.1.1 step 2 — the specific
rule where one governs, otherwise `REVIEW_NOT_CURRENT`. No cell expresses a
boundary refusal, because 11.1.1 defines none. Where the table and 11.1.1 could
be read as disagreeing, 11.1.1 governs and the cell is a defect.

| State | `start` | `resume` | `rework` | `approve` | `inspect` |
|---|---|---|---|---|---|
| **A** no Architecture | create shell → continue · mutate ✔ · model ✔ · `ARCHITECTURE_CYCLE_STARTED` · 0 | `CYCLE_NOT_FOUND` · ✘ · ✘ · 1 | `CYCLE_NOT_FOUND` · ✘ · ✘ · 1 | `CYCLE_NOT_FOUND` · ✘ · ✘ · 1 | `CYCLE_NOT_FOUND` · ✘ · ✘ · 1 |
| **B** shell, no manifest | adopt shell → continue · ✔ · ✔ · `ARCHITECTURE_CYCLE_STARTED` · 0 | `MANIFEST_INPUTS_REQUIRED` · ✘ · ✘ · 1 | `REVIEW_NOT_CURRENT` · ✘ · ✘ · 1 | `REVIEW_NOT_CURRENT` · ✘ · ✘ · 1 | `INSPECT_INCOMPLETE` · ✘ · ✘ · 0 |
| **C** shell, acceptance incomplete | complete acceptance → continue · ✔ · ✔ · `ARCHITECTURE_CYCLE_STARTED` · 0 | `MANIFEST_INPUTS_REQUIRED` · ✘ · ✘ · 1 | `REVIEW_NOT_CURRENT` · ✘ · ✘ · 1 | `REVIEW_NOT_CURRENT` · ✘ · ✘ · 1 | `INSPECT_INCOMPLETE` · ✘ · ✘ · 0 |
| **D → case 1** manifest, no Process | run Architect → Review → boundary · ✔ · ✔ · `ARCHITECTURE_REVIEW_READY` · 0 | same · ✔ · ✔ · `ARCHITECTURE_CYCLE_RESUMED` · 0 | `REVIEW_NOT_CURRENT` · ✘ · ✘ · 1 | `REVIEW_NOT_CURRENT` · ✘ · ✘ · 1 | `INSPECT_CURRENT` · ✘ · ✘ · 0 |
| **D → case 2** Architecture == input | apply `intended_output` → Reviewer → boundary · ✔ · ✔ Reviewer only · `ARCHITECTURE_REVIEW_READY` · 0 | same · ✔ · ✔ Reviewer only · `ARCHITECTURE_CYCLE_RESUMED` · 0 | `REVIEW_NOT_CURRENT` · ✘ · ✘ · 1 | `REVIEW_NOT_CURRENT` · ✘ · ✘ · 1 | `INSPECT_CURRENT` · ✘ · ✘ · 0 |
| **D → case 3** Architecture == output | run Reviewer → boundary · ✔ · ✔ · `ARCHITECTURE_REVIEW_READY` · 0 | same · ✔ · ✔ · `ARCHITECTURE_CYCLE_RESUMED` · 0 | `REVIEW_NOT_CURRENT` · ✘ · ✘ · 1 | `REVIEW_NOT_CURRENT` · ✘ · ✘ · 1 | `INSPECT_CURRENT` · ✘ · ✘ · 0 |
| **D → case 4** neither | `ARCHITECTURE_DIVERGED` · ✘ · ✘ · 1 | same · ✘ · ✘ · 1 | same · ✘ · ✘ · 1 | same · ✘ · ✘ · 1 | `INSPECT_INCOMPLETE` · ✘ · ✘ · 0 |
| **D → case 5** Review exists | stop at boundary · ✘ · ✘ · `ARCHITECTURE_REVIEW_READY` · 0 | same · ✘ · ✘ · `ARCHITECTURE_REVIEW_READY` · 0 | persist REWORK → iteration N+1 · ✔ · ✔ · `ARCHITECTURE_REWORK_RECORDED` · 0 | validate → persist APPROVE · ✔ · ✘ · `ARCHITECTURE_APPROVED` · 0 | `INSPECT_CURRENT` · ✘ · ✘ · 0 |
| **D → case 6** Decision exists (REWORK) | continue at N+1 · ✔ · ✔ · `ARCHITECTURE_CYCLE_RESUMED` · 0 | same · ✔ · ✔ · `ARCHITECTURE_CYCLE_RESUMED` · 0 | §11.1.1 step 4 → `DECISION_ALREADY_RECORDED` 0 **or** `DECISION_CONFLICT` 1 · ✘ · ✘ | §11.1.1 step 4 → `DECISION_CONFLICT` 1 · ✘ · ✘ | `INSPECT_CURRENT` · ✘ · ✘ · 0 |
| **D → case 6** Decision exists (APPROVE) | `CYCLE_APPROVED` · ✘ · ✘ · 0 | `CYCLE_APPROVED` · ✘ · ✘ · 0 | §11.1.1 step 4 → `DECISION_CONFLICT` 1 · ✘ · ✘ | §11.1.1 step 4 → `DECISION_ALREADY_RECORDED` 0 **or** `DECISION_CONFLICT` 1 · ✘ · ✘ | `INSPECT_CURRENT` or `INSPECT_STALE` · ✘ · ✘ · 0 |
| **D → case 7** empty shell child | by shell type, §13.7-7 · see table · see table · see table | same | empty Decision shell → `DECISION_SHELL_UNRECOVERABLE`; any other shell type → `REVIEW_NOT_CURRENT` · ✘ · ✘ · 1 | same · ✘ · ✘ · 1 | `INSPECT_CURRENT` · ✘ · ✘ · 0 |
| **D → case 8** malformed artifact | `ARTIFACT_MALFORMED` · ✘ · ✘ · 1 | same · ✘ · ✘ · 1 | same · ✘ · ✘ · 1 | same · ✘ · ✘ · 1 | `INSPECT_INCOMPLETE` · ✘ · ✘ · 0 |
| **D → case 9** unknown outcome | rediscover, then reclassify · ✘ until classified · ✘ · code of the resolved state | same | same | same | `INSPECT_CURRENT` · ✘ · ✘ · 0 |
| **D → case 10** at boundary, no decision | re-present · ✘ · ✘ · `ARCHITECTURE_REVIEW_READY` · 0 | same · ✘ · ✘ · `ARCHITECTURE_REVIEW_READY` · 0 | persist REWORK · ✔ · ✔ · `ARCHITECTURE_REWORK_RECORDED` · 0 | validate → persist · ✔ · ✘ · `ARCHITECTURE_APPROVED` · 0 | `INSPECT_CURRENT` · ✘ · ✘ · 0 |
| **E** ambiguous / foreign | `CYCLE_AMBIGUOUS` or `CYCLE_FOREIGN_PROJECT` · ✘ · ✘ · 1 | same · ✘ · ✘ · 1 | same · ✘ · ✘ · 1 | same · ✘ · ✘ · 1 | `INSPECT_CURRENT` · ✘ · ✘ · 0 |
| **stale inputs** any state | `INPUTS_STALE` · ✘ · ✘ · 1 | same · ✘ · ✘ · 1 | same · ✘ · ✘ · 1 | same · ✘ · ✘ · 1 | `INSPECT_STALE` · ✘ · ✘ · 0 |
| **duplicate artifact** | `ARTIFACT_DUPLICATE` · ✘ · ✘ · 1 | same · ✘ · ✘ · 1 | same · ✘ · ✘ · 1 | same · ✘ · ✘ · 1 | `INSPECT_CURRENT` · ✘ · ✘ · 0 |

### 13.7 Resolutions the table settles

**SPEC — 1. `resume` in A–C.** `resume` carries no manifest-building arguments,
so in states B and C it cannot supply the selection, UX evidence or acceptance
the cycle still needs. It refuses with `MANIFEST_INPUTS_REQUIRED` and directs the
operator to `start` with the same cycle id. In state A there is nothing to
resume: `CYCLE_NOT_FOUND`.

**SPEC — 2. Repeated `start`, different inputs.** `start` **MUST NOT** build a
fresh manifest with new timestamps and compare digests: `created_at` and the UX
`recorded_at` are generated metadata, so that comparison would differ on every
retry purely because of wall-clock time.

Instead the comparison runs over a **caller-input projection** that contains only
caller-controlled values:

```text
start_input_projection = {
  "cycle_id":            <canonical cycle id>,
  "project_entity_id":   <resolved Project entity id>,
  "requirement_ids":     [<upper-cased, de-duplicated, sorted ascending>],
  "ux":                  { "kind": "APPLICABLE",
                           "document_id": <id>,
                           "content_digest": <digest read now>,
                           "scope_requirement_ids": [<sorted ascending>] }
                         | { "kind": "NOT_APPLICABLE", "reason": <text> },
  "accept_inputs":       true,
  "accept_ux":           true
}

start_input_digest = SHA256(UTF8("sdlc.tsa.start.v1\n"
                                 + canonical_json(start_input_projection))).hexdigest()
```

**SPEC.** No timestamp, no generated id and no persisted metadata enters the
projection, so the **same caller inputs digest identically on every retry
regardless of wall-clock time**.

**SPEC — the prefix.** `start_input_digest` uses the domain tag
`sdlc.tsa.start.v1` followed by a single `\n`, then `canonical_json` of 5.1. It
is **not** an `artifact_digest` (5.2) and **not** a `sub_digest` (5.4): it has no
artifact type and no separate version line, because it digests caller argv, not a
persisted artifact. It never appears inside any artifact body.

**SPEC — normative vectors.** These are normative; an implementation that does
not reproduce them exactly is wrong.

**Vector S-1 — `APPLICABLE`.** Projection:

```text
{"accept_inputs":true,"accept_ux":true,"cycle_id":"tsa-2026-001","project_entity_id":"11111111-2222-3333-4444-555555555555","requirement_ids":["SDLC-FR-0001","SDLC-NFR-0002"],"ux":{"content_digest":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","document_id":"doc-ux-1","kind":"APPLICABLE","scope_requirement_ids":["SDLC-FR-0001"]}}
```

```text
start_input_digest ce3f939e346c905768851348b390b8dab12c84ea24cfdaeca0c7f7e3b8518f0d
```

**Vector S-2 — `NOT_APPLICABLE`.** The same projection with the `ux` branch
replaced:

```text
{"accept_inputs":true,"accept_ux":true,"cycle_id":"tsa-2026-001","project_entity_id":"11111111-2222-3333-4444-555555555555","requirement_ids":["SDLC-FR-0001","SDLC-NFR-0002"],"ux":{"kind":"NOT_APPLICABLE","reason":"No user-facing surface"}}
```

```text
start_input_digest 0613eac534aeee827192771f221d32b4ccd776322eae74a94dc7209aa5af66ef
```

The two differ, so the vectors also pin that the UX branch is inside the digested
projection and cannot be switched without a `MANIFEST_INPUTS_CONFLICT`.

**SPEC.** On repeated `start` against an existing accepted manifest the engine:

1. loads the persisted `manifest_body`;
2. **reuses** its generated metadata — `created_at`, and the UX
   `approval.recorded_at` / `decision.recorded_at` — unchanged;
3. rebuilds the projection from the **current argv** only;
4. rebuilds the same projection from the persisted manifest;
5. compares the two digests.

Equal → proceed as a resume, writing nothing. Different →
`MANIFEST_INPUTS_CONFLICT`, exit 1, nothing written: a changed Requirement
selection, UX evidence or acceptance requires a **new cycle id** (contract §3.2),
never a silent rewrite.

**SPEC — 7. Empty shell recovery, by artifact type.** Every case is decided;
where no safe deterministic completion exists, the answer is refusal.

| Shell type | Action | Mutate | Model | Code | Exit |
|---|---|---|---|---|---|
| Architecture | adopt and write the envelope; this is bootstrap state B | ✔ | ✘ | `ARCHITECTURE_CYCLE_RESUMED` | 0 |
| Input Manifest | **refuse.** An empty shell holds no persisted manifest to compare against, and `start` carries no authority to invent one | ✘ | ✘ | `MANIFEST_SHELL_UNRECOVERABLE` | 1 |
| Process Result | the model output is gone; complete in place by **one** fresh Architect call under the same iteration | ✔ | ✔ | `ARCHITECTURE_CYCLE_RESUMED` | 0 |
| Review Result | complete in place by **one** fresh Reviewer call under the same iteration | ✔ | ✔ | `ARCHITECTURE_CYCLE_RESUMED` | 0 |
| Human Decision | **refuse.** A decision is a human act; no deterministic completion exists | ✘ | ✘ | `DECISION_SHELL_UNRECOVERABLE` | 1 |

**SPEC — exactly one rule per shell type.** The five rows above are the
**complete** set of empty-shell rules, one per artifact type, and no other rule
in this specification decides an empty shell. In particular:

- `DECISION_SHELL_UNRECOVERABLE` applies to an **empty Human Decision shell and
  nothing else**. It is never returned for a Manifest, Process, Review or
  Architecture shell, and never for a durable Decision (that is 11.1.1 step 3).
- `MANIFEST_SHELL_UNRECOVERABLE` applies to an **empty Input Manifest shell and
  nothing else**. It is distinct from `MANIFEST_INPUTS_REQUIRED` (a `resume` that
  carries no manifest arguments, states B–C) and from `MANIFEST_INPUTS_CONFLICT`
  (a `start` whose argv disagrees with a **valid persisted** manifest, 13.7-2).

**SPEC — why the Manifest shell refuses.** An empty Manifest shell has no
`manifest_body`, so there is nothing for `start_input_digest` to be compared
against. Completing it from the current argv would mean **accepting argv as the
manifest without any prior record to agree with** — exactly the silent rewrite
the cycle-id rule forbids (contract §3.2). Recovery is a **new cycle id**; the
empty shell is left untouched for manual inspection, never deleted.

**SPEC — `start_input_digest` has one use.** `start_input_digest` is compared
**only** between the current argv and a **valid, complete, persisted**
`manifest_body` (13.7-2). It is never computed against an empty shell, a
malformed manifest, or a partially written one; in those states the command
refuses before any digest is computed.

**SPEC.** In the three completing rows (Architecture, Process Result, Review
Result) the shell is completed **in place, under its own deterministic id**
(3.5); a second artifact for the same iteration is never created. In the two
refusing rows nothing is written at all.

**SPEC — 3. Case 2 vs case 3 when output == input.** When the Architect's
intended output is byte-identical to the input Architecture, both case
predicates hold. **Case 3 wins.** The apply step is a no-op, so treating it as
"already applied" is correct and avoids a pointless write; the engine advances to
Review. This precedence is fixed and not implementation choice.

**SPEC — 4. Unknown create of a child artifact.** Process, Review and Decision
Documents are created with a client-supplied id (3.5), so an unknown outcome is
resolved by `resolve_document(id)` first, then by listing
`child_documents(architecture_id)` and matching `artifact_type` + `iteration`.
Zero → create permitted; one → adopt; more than one → `ARTIFACT_DUPLICATE`.

**SPEC — 5. `REWORK` after `APPROVE`.** Settled entirely by 11.1.1: the
`APPROVE` durable at the targeted iteration is found at step 3, the decisions
differ, and the result is `DECISION_CONFLICT`, exit 1, nothing written and no
model call. No boundary refusal is reached, because 11.1.1 step 5 is not
evaluated and defines no failure of its own. There is no separate "cycle already
approved" outcome either.

**SPEC — 6.** Every code named anywhere in this specification appears in 13.8.
`REWORK` and `APPROVE` are **not** result codes: they are the closed `decision`
enum of `tsa.human_decision` (4.6.5) and never appear as a command outcome.

### 13.8 Result-code catalogue

**SPEC.** Complete and authoritative. One semantic meaning each, all reachable
from 13.6 or from a validator named in this document. Exit class `0` is a normal
outcome including a correct no-op; `1` is a refusal or failure; `2` is reserved
for argparse usage errors and is never emitted by engine logic.

| Code | Meaning | Exit |
|---|---|---|
| `ARCHITECTURE_CYCLE_STARTED` | A new cycle reached the Review boundary | 0 |
| `ARCHITECTURE_CYCLE_RESUMED` | An existing cycle advanced | 0 |
| `ARCHITECTURE_REVIEW_READY` | Stopped at the Human Decision boundary | 0 |
| `ARCHITECTURE_REWORK_RECORDED` | `REWORK` persisted; iteration N+1 opened | 0 |
| `ARCHITECTURE_APPROVED` | `APPROVE` persisted and read back | 0 |
| `DECISION_ALREADY_RECORDED` | Semantically identical decision already durable | 0 |
| `CYCLE_APPROVED` | Cycle is approved; the command is read-only here | 0 |
| `CYCLE_NOT_FOUND` | No Architecture Document for this cycle id | 1 |
| `CYCLE_AMBIGUOUS` | More than one plausible Architecture candidate | 1 |
| `CYCLE_FOREIGN_PROJECT` | A candidate is owned by another Project | 1 |
| `INVALID_CYCLE_ID` | Cycle id fails the grammar of 3.1 | 1 |
| `ITERATION_LIMIT` | Iteration would exceed 999 | 1 |
| `SELECTION_EMPTY` | No `--requirement` supplied | 1 |
| `SELECTION_DUPLICATE` | A Requirement id or entity id appears twice | 1 |
| `REQUIREMENT_NOT_ADMISSIBLE` | An admission check of contract §2.1 failed | 1 |
| `UX_EVIDENCE_INVALID` | UX evidence missing, unreadable, or digest mismatched | 1 |
| `UX_SCOPE_FOREIGN` | `scope_requirement_ids` names an unselected Requirement | 1 |
| `HUMAN_ACCEPTANCE_REQUIRED` | `--accept-inputs` or `--accept-ux` absent | 1 |
| `MANIFEST_ACCEPTANCE_MISMATCH` | Acceptance digest ≠ manifest digest | 1 |
| `MANIFEST_INPUTS_REQUIRED` | `resume` in state B or C | 1 |
| `MANIFEST_SHELL_UNRECOVERABLE` | An empty Input Manifest shell cannot be completed | 1 |
| `MANIFEST_INPUTS_CONFLICT` | `start` re-run with a different manifest digest | 1 |
| `INPUTS_STALE` | Requirement or UX inputs drifted (contract §4.4, §10) | 1 |
| `INPUT_TOO_LARGE` | Assembled model input exceeds the §15 bound | 1 |
| `ARCHITECTURE_DIVERGED` | Architecture matches neither recorded input nor output | 1 |
| `ARCHITECTURE_RENDER_INVALID` | Rendered document fails 8.1 or 8.3 validation | 1 |
| `ARTIFACT_MALFORMED` | Non-empty artifact fails carrier, schema, digest or lineage | 1 |
| `ARTIFACT_DUPLICATE` | Two artifacts of one type for one iteration | 1 |
| `TRACEABILITY_MISSING_REQUIREMENT` | A selected Requirement has no coverage row | 1 |
| `TRACEABILITY_UNKNOWN_REQUIREMENT` | A coverage row names an unselected Requirement | 1 |
| `TRACEABILITY_DUPLICATE_REQUIREMENT` | A Requirement appears in two coverage rows | 1 |
| `TRACEABILITY_UNKNOWN_ANCHOR` | An anchor is outside `^tsa-s(0[1-9]\|1[0-6])$` (`tsa-s01` … `tsa-s16`) | 1 |
| `TRACEABILITY_DUPLICATE_ANCHOR` | The same anchor twice in one Requirement row | 1 |
| `SECTION_MANDATORY_EMPTY` | A Mandatory heading holds only an N/A form | 1 |
| `REVIEW_COVERAGE_INCOMPLETE` | An Architect claim was not verified | 1 |
| `REVIEW_COVERAGE_DUPLICATE` | A claim was verified twice | 1 |
| `REVIEW_STRUCTURALLY_INVALID` | Derived review status, never waivable | 1 |
| `REVIEW_BLOCKED_ON_WHAT` | Material unresolved WHAT; not waivable in TSA | 1 |
| `DISPOSITION_UNKNOWN_REFERENCE` | Reference fails grammar, range, collection or artifact | 1 |
| `DISPOSITION_DUPLICATE_REFERENCE` | The same reference twice in one decision | 1 |
| `DISPOSITION_FOREIGN_ITERATION` | Reference belongs to another iteration | 1 |
| `DISPOSITION_NOT_WAIVABLE` | A material WHAT was offered as an accepted risk | 1 |
| `DECISION_CONFLICT` | A different decision already exists for the target | 1 |
| `MODEL_RUNTIME_FAILED` | The CLI runtime failed or timed out | 1 |
| `INVALID_MODEL_OUTPUT` | Model response failed its closed contract | 1 |
| `INSPECT_CURRENT` | `inspect`: state derived, all bound inputs current | 0 |
| `INSPECT_STALE` | `inspect`: state derived, at least one bound input drifted | 0 |
| `INSPECT_INCOMPLETE` | `inspect`: state derived but incomplete, malformed or diverged | 0 |
| `DECISION_SHELL_UNRECOVERABLE` | An empty Human Decision shell cannot be completed | 1 |
| `REVIEW_NOT_CURRENT` | Supplied Review Result does not bind the stated target | 1 |
| `WORKSPACE_BUSY` | The workspace guard is held | 1 |
| `FIBERY_READ_FAILED` | A read failed | 1 |
| `FIBERY_WRITE_FAILED` | A write failed | 1 |

## 14. Execution order and recovery

### 14.1 The mutation cycle

**SPEC.** Every remote mutation follows exactly:

```text
prepare payload
→ revalidate preconditions immediately before the write   (contract §14.2)
→ mutate
→ rediscover / read back
→ validate the intended result
→ only then report success
```

A read-back showing drift is **not** a success (contract §14.2).

### 14.2 Write order

**SPEC.** For one Architect iteration, in this order and no other:

1. persist the **Process Result** artifact, carrying both the input Architecture
   fingerprint and the intended output content;
2. apply the output to the **Architecture Document**;
3. read back and compare.

**SPEC.** Persisting before applying is what makes contract §14.3 cases 2 and 3
decidable: after a crash the recorded output can be replayed without another
model call, because it is already durable.

### 14.3 Case mapping

| Observation | Contract case | Action |
|---|---|---|
| Manifest accepted, no Process Result | 1 | Architect call permitted |
| Process Result exists, Architecture == recorded **input** | 2 | Apply recorded output; no model call |
| Process Result exists, Architecture == recorded **output** | 3 | Advance to Review |
| Architecture == neither | 4 | `ARCHITECTURE_DIVERGED`; refuse, report all three fingerprints |
| Review Result exists | 5 | Advance to the boundary; no Reviewer call |
| Human Decision exists | 6 | Honour it |
| Empty shell | 7 | Complete that shell in place, or refuse naming it |
| Non-empty malformed | 8 | `ARTIFACT_MALFORMED`; refuse, no overwrite |
| Unknown transport outcome | 9 | Rediscover first (3.4); never blind retry |
| At human boundary | 10 | Re-present; no model call |

**SPEC.** Cases 2 and 5 are reached **only** when the gate's freshness checks
pass. Stale Requirement or UX inputs block replay (contract §14.1).

### 14.4 Shell and malformed disambiguation

**SPEC.** The two classes are disjoint, and the boundary is the **carrier**, not
the payload:

| Class | Exact condition |
|---|---|
| **EMPTY SHELL** | `read_document_content` returns a string whose `.strip()` is `""` — the body was never written |
| **MALFORMED** | Any **non-empty** content that does not satisfy the carrier and schema, **including non-empty content with no `` ```json `` fence** |

**SPEC.** Non-empty-without-a-fence is **malformed**, not a shell. The earlier
wording folded it into "empty shell" and is corrected here: content a human or a
partial write left behind is evidence, and overwriting it would destroy that
evidence.

**SPEC.** Malformed handling, with no exception: **refuse**; never overwrite;
never repair; never treat as absent (contract §14.3 case 8). Result
`ARTIFACT_MALFORMED`, naming the Document id.

**SPEC.** There is **no permitted partial carrier**. A TSA Document body is
either empty, or one complete `` ```json `` artifact in the shape of 4.1. A
half-written fence, two fences, or a fence plus trailing content is malformed.

### 14.4.1 Crash windows A–F

**SPEC.** Every window is resolved from durable state plus the deterministic id
of 3.5. No window needs a journal, none permits a blind duplicate create, and
none re-calls a model whose output is already durable.

| # | Window | Resolution |
|---|---|---|
| **A** | Process create outcome unknown | Recompute the Process id for iteration `N`; `resolve_placement`. Absent → retry the create with the **same** id. Present and empty → shell recovery, one fresh Architect call (13.7-7). Present and complete → adopt; **no model call**. |
| **B** | Process persisted, Architecture unchanged | Case 2. `render(intended_output, manifest_body)` and apply. **No model call** — the output is durable. |
| **C** | Architecture write outcome unknown | Re-read the Architecture Document and fingerprint it. Equals recorded input → case 2, apply. Equals recorded output → case 3, already applied. Neither → case 4 `ARCHITECTURE_DIVERGED`, refuse. |
| **D** | Architecture written, read-back lost | Identical to **C**: the classification is by content fingerprint, not by whether the response arrived. A second apply of the same `intended_output` is byte-identical, so re-applying is safe and idempotent. |
| **E** | Review create outcome unknown | Recompute the Review id for `N`; resolve. Absent → retry create with the same id. Present and empty → one fresh Reviewer call in place. Present and complete → adopt; **no model call**. |
| **F** | Decision create outcome unknown | Recompute the Decision id for `N`; resolve. Absent → retry create with the same id. Present → §11.2 semantic comparison: equivalent → `DECISION_ALREADY_RECORDED` with the durable `recorded_at` preserved; different → `DECISION_CONFLICT`. Present and empty → `DECISION_SHELL_UNRECOVERABLE`. |

**SPEC.** In **A**, **E** and **F** the retry uses the **same deterministic id**,
so a duplicate artifact for one iteration cannot be created even if the original
request did land after the client gave up.

### 14.5 Staleness during a model call

**SPEC.** Inputs are revalidated immediately before the call and again after it,
before the output is applied (contract §10). Drift detected after the call means
the Process Result is **not** applied and the run reports `INPUTS_STALE`. The
model output is still persisted as history if it was already written; it is never
applied to a stale Architecture.

**SPEC.** No transaction is claimed anywhere. This is optimistic validation
(contract §10).

---

## 15. Runtime configuration

**SPEC.** `config/sdlc.toml` gains exactly two role tables, in the existing
shape:

```toml
[model_runtime.roles.tsa_architect]
runtime = "claude"
# model = "..."   # omitted: use the local CLI default model

[model_runtime.roles.tsa_reviewer]
runtime = "claude"
# model = "..."   # omitted: use the local CLI default model
```

**SPEC.** `model_runtime_config.py` gains two constants,
`TSA_ARCHITECT_ROLE = "tsa_architect"` and `TSA_REVIEWER_ROLE = "tsa_reviewer"`,
alongside the existing three. Selection precedence, the authentication guard and
the reasoning-child restrictions are unchanged (REUSE).

**SPEC.** Codex remains blocked at the execution boundary
(`RUNTIME_ISOLATION_UNAVAILABLE`); no fallback, no relaxed isolation, no
provider API.

**SPEC.** Timeout: `DEFAULT_TIMEOUT_SECONDS` is reused. No TSA-specific override
is introduced in v0.1.

**SPEC — input bound.** The assembled model input is capped at **400,000 Unicode
code points**, and the selection at **100 Requirements**. Overflow is
`INPUT_TOO_LARGE`: **refuse, never truncate.**

---

## 16. Prompt input boundaries

### 16.1 Architect

**SPEC.** Supplied, and nothing else:

- Project code and name (identity only, no Project prose as authority);
- the Input Manifest body;
- the **full normative tree** of every selected Requirement;
- the UX Document content **only** when `kind = APPLICABLE`;
- on rework only: the previous Architecture Document content and the previous
  Review Result findings.

**SPEC.** Previous model prose is supplied as *material to revise*, explicitly
labelled, and **MUST NOT** be presented as authority. The Requirements and the
UX content are the only normative sources.

### 16.2 Reviewer

**SPEC.** Supplied, and nothing else:

- the exact current Architecture Document content;
- the same Input Manifest and Requirement trees the Architect saw;
- the UX content when `APPLICABLE`;
- the persisted Architect Process Result claims.

**SPEC.** A **previous Review Result is never supplied**, mirroring the
Requirement Review independence rule (`review_prompt.py`: previous Review Results
are never sent). A reviewer must not anchor on its own earlier verdict.

---

## 17. Test architecture

**SPEC.** Every one of contract §16's 50 rows maps to a named test or probe, an
evidence class and an owning work item. A `D` test is **never** reported as
evidence for an `M` or `F` row (contract §16); where a row needs more than one
class, each class is listed as its own line with its own owner.

| Row | Test or probe | Class | Owner |
|---|---|---|---|
| 1 | full cycle on fakes, admit → architect → review → approve | D | I13 |
| 1 | live Architect + Reviewer on a synthetic cycle | M | I14 |
| 1 | live Fibery artifact round-trip for the same cycle | F | I03 |
| 2 | UX `APPLICABLE` missing/unapproved → refused before Architect | D | I05 |
| 3 | model-authored `NOT_APPLICABLE` rejected | D | I05 |
| 4 | duplicate id, or selection spanning two Projects | D | I05 |
| 5 | selected Requirement not `Applied` | D | I05 |
| 6 | Root or child changed after freeze → refused at revalidation | D | I10 |
| 7 | `APPLICABLE` UX drift → approval unavailable | D | I10 |
| 8 | Architecture changed after Review → approval unavailable | D | I11 |
| 9 | repeat `start`/`resume`/`approve` recovers durable state | D | I12 |
| 10 | incomplete write → recovery cases 1–9 | D | I10 |
| 11 | no human decision recorded → nothing advances | D | I10 |
| 12 | Requirement set changed → `MANIFEST_INPUTS_CONFLICT`, new cycle | D | I05 |
| 13 | traceability omits a selected Requirement | D | I06 |
| 14 | Architect N/A on an included Requirement | D | I06 |
| 15 | structurally recognisable Task/Epic/estimate/code refused by the validator | D | I07 |
| 16 | material unresolved WHAT → approval unavailable | D | I11 |
| 17 | contradiction surfaced, no silent winner (validator path) | D | I08 |
| 17 | live Reviewer detects a real contradiction | M | I14 |
| 18 | Reviewer write to the Architecture Document refused | D | I08 |
| 19 | approval with a stale Review digest refused | D | I11 |
| 20 | accepted technical risk recorded; approval proceeds | D | I11 |
| 21 | two cooperating commands, same host/user → `WORKSPACE_BUSY` | D | I12 |
| 22 | external Fibery UI edit mid-cycle → detected at revalidation | F | I03 |
| 23 | Project containment, nesting, rediscovery, read-back | F | I03 |
| 24 | Architect returns one integrated architecture, not a catalogue | M | I14 |
| 25 | Reviewer independently disagrees with a real Architect output | M | I14 |
| 26 | only selected ids enter the manifest | D | I05 |
| 27 | missing/legacy/incoherent Requirement evidence → refusal, no backfill | D | I05 |
| 28 | hand-set `Applied` → explicit acceptance required, no Apply claim | D | I05 |
| 29 | valid `NOT_APPLICABLE` current with no UX Document | D | I05 |
| 30 | `test_product_question_evidence_preserved`: evidence persisted in `intended_output` and the Architecture envelope, no Requirement mutation, approval unavailable while a material WHAT stands | D | I11 |
| 30 | live Architect answers a product question instead of HOW → detected | M | I14 |
| 31 | `REWORK` → immutable decision, iteration N+1, history intact | D | I11 |
| 32 | `APPROVE` → exact tuple revalidated, immutable Decision written | D | I11 |
| 33 | model failure → no false success, one explicit retry | D | I07 |
| 34 | approval then input drift → historical, not current; consumer refuses | D | I11 |
| 35 | zero downstream side effects across the cycle | D | I13 |
| 36 | Task/Epic/product invention inside allowed prose → detected | M | I14 |
| 37 | UX digest or scope mismatched at admission | D | I05 |
| 38 | UX Document unreadable, deleted or replaced at admission | D | I05 |
| 39 | zero/one/many Architecture candidates; foreign Project | D | I04 |
| 40 | bootstrap A–C: missing manifest not a gate failure; no model call | D | I04 |
| 41 | stale inputs block replay of a persisted Process output | D | I10 |
| 42 | duplicate Process/Review, conflicting decisions → gate failure | D | I10 |
| 43 | invalid Process output digest → gate failure, no replay | D | I10 |
| 44 | Review bound to a different Process payload | D | I10 |
| 45 | Reviewer defect → evidence persisted, Architecture unchanged, boundary | D | I08 |
| 46 | manifest acceptance missing or bound to another digest | D | I05 |
| 47 | `resume` on an approved cycle → `CYCLE_APPROVED`, no write | D | I12 |
| 48 | `REWORK` after `APPROVE` at that exact target iteration → `DECISION_CONFLICT`, no write, no model call, approved cycle stays closed | D | I11 |
| 49 | disposition reference unknown or duplicated | D | I11 |
| 50 | Requirement drift while `NOT_APPLICABLE` → stale, no UX Document read | D | I10 |

**SPEC.** Rows 1, 17 and 30 carry more than one class; each line is discharged
separately and a `D` line never discharges the `M` or `F` line beside it.

**SPEC.** Class totals: **45 D lines, 6 M lines, 3 F lines** across 50 rows
(54 lines, because rows 1, 17 and 30 are multi-class).

**SPEC — layers.** `D` lines are unit tests (digests, vectors, identities,
schemas, validators), workspace-fake tests with failure injection, or CLI tests
through real `cli.main` with a fake transport. `F` lines are the `P-1` live
Fibery probe family. `M` lines are controlled live-model probes on synthetic
architecture material, never on a real Requirement set.

**SPEC.** Failure injection MUST cover, at minimum: create returns unknown;
write returns unknown; read-back returns different content; two candidates
appear; a payload digest mismatches; an artifact carries an unknown key.

**SPEC — discrepancy rule.** Any live behaviour that contradicts the fake makes
the fake wrong. Correct the fake, add a regression test, and only then record the
capability as verified.

---

## 18. Implementation work items

Derived from the dependency graph, not from a fixed template. Each is
independently reviewable; none is authorized by this document.

| # | Scope | Depends on | Expected files | Acceptance | MUST NOT change |
|---|---|---|---|---|---|
| **I01** | Canonical JSON + digest + envelope + schemas for all five artifacts | — | `src/sdlc/tsa_artifacts.py`, tests | Test vectors 1–5 reproduce; unknown-key and malformed refusal | Requirement fingerprints, `process_result`, `review_result` |
| **I02** | `ArchitectureWorkspace` protocol + HTTP adapter + fake | I01 | `fibery_workspace.py`, `fibery_http.py`, `tests/architecture_fake.py` | Containment, parentage, uniqueness, wrong-project refusal on the fake | Requirement adapters, `create_requirement_document` |
| **I03** | Live Fibery probe `P-1` | I02 | `scripts/` probe, evidence doc | Live containment and nesting confirmed; fake corrected if it differs | Nothing in `src/` without a recorded discrepancy |
| **I04** | Cycle identity, discovery, bootstrap gate, states A–E | I02 | `src/sdlc/tsa_cycle.py`, tests | Zero/one/many candidate classification; no blind duplicate create | Contract lifecycle |
| **I05** | Admission + Input Manifest + acceptance | I01, I04 | `src/sdlc/tsa_admission.py`, tests | All eight admission checks; two-layer digest; UX union both branches | Requirement authority, UX authority |
| **I06** | Architecture Document template + traceability validator | I01 | `src/sdlc/tsa_architecture.py`, tests | 16 headings; coverage exactly once; unknown/duplicate anchor refusal | Heading set |
| **I07** | Architect stage: prompt, output contract, persist, apply | I05, I06, I09 | `src/sdlc/tsa_architect.py`, prompt module, tests | Persist-before-apply; replay without model call | Prompt-independence of Reviewer |
| **I08** | Reviewer stage + derived status | I07 | `src/sdlc/tsa_reviewer.py`, tests | Derived status precedence; no verdict field; no previous review supplied | Reviewer authority |
| **I09** | Runtime roles `tsa_architect`, `tsa_reviewer` | — | `config/sdlc.toml`, `model_runtime_config.py` | Roles resolve; Codex still blocked | Isolation policy |
| **I10** | Normal recovery gate + cases 1–10 + mutation discipline | I01, I04, I05, I07, I08 | `src/sdlc/tsa_recovery.py`, tests | Every case; gate failure ⇒ zero writes | Frozen recovery semantics |
| **I11** | Human Decision, approval binding, dispositions | I01, I06, I08, I10 | `src/sdlc/tsa_decision.py`, tests | Row 49 testable; idempotent re-issue; conflict refusal | Approval authority |
| **I12** | CLI commands and result codes | I05–I11 | `src/sdlc/cli.py`, tests | Explicit acceptance flags; exit-code policy | Existing commands |
| **I13** | Integration tests across the whole cycle | I01–I12 | `tests/test_tsa_lifecycle_e2e.py` | Full cycle on fakes; failure injection | — |
| **I14** | Live model probes | I07, I08, I12 | evidence doc | Rows 24, 25, 30, 36 | — |

**SPEC — dependency reconciliation** after the S1–S11 corrections. The graph
stays acyclic; these are the clarifications the corrections force.

- **I02 provisional vs final.** I02 may be implemented provisionally so I03 can
  run at all. It is **not finalized** until `P-1` reports, and the `I-1` gate
  binds that finalization, not the provisional code.
- **I04 / I05 against the fake.** Both may be developed fully against the fake.
  Neither may **rely on live behaviour** before the `I-1` gate clears.
- **I04 gains the client-supplied document id.** Section 3.5 puts the
  correlation mechanism in I04's scope; I02 must expose `document_id` on
  `create_project_document` for it. I04 therefore depends on I02's **signature**,
  not on its live verification.
- **I10 does not depend on I11.** All five artifact schemas, including
  `tsa.human_decision`, are owned by **I01** (4.6). I10 needs the schema, which
  I01 provides; it does not need I11's command behaviour. Corrected dependency:
  I10 ← I01, I04, I05, I07, I08.
- **I11 depends on I10**, because approval runs through the normal gate.
- **I14 scope.** I14 is **synthetic model probes only**. It does **not**
  constitute full live-cycle verification; rows 1-F, 22 and 23 remain I03's, and
  a green I14 never discharges them.

Resulting order, acyclic: I01 → I02 → I03 → I04 → I05 → I06 → I07 → I08 → I10 →
I11 → I12 → I13 → I14, with **I09** independent of all of them and schedulable
at any point.

---

## 19. Unresolved classification

### 19.1 Closed by this specification

| Item | Closed by |
|---|---|
| **U-3** | Section 2 — protocol methods, Fibery operation mapping, the split root/child placement predicates and their freshness rule, verification obligations, `P-1` probe and the discrepancy rule |
| **U-4** | Sections 4–6 — envelope, canonical serialization, domain-separated digest with normative test vectors, disposition identity |
| **U-7** | Sections 12–13 — exact flags, scope syntax, acceptance flags, the command × state table under the 11.1.1 decision precedence, the result-code catalogue, exit-code policy, per-command semantics |

**Note.** U-3 is closed at the level this document owns — the protocol, the
mapping and the obligations. Its **live behaviour** remains unproven until `P-1`
runs; that is a `PROBE`, not an open design question.

### 19.2 Still intentionally deferred

| Item | Class | Unchanged because |
|---|---|---|
| **U-2** | DEFERRED | Apply-time provenance needs a durable Apply artifact; out of scope for this slice, and no mechanism here invents one |
| **U-6** | DEFERRED | The runtime supplies no authenticated identity; section 11 forbids claiming one |
| **U-8** | DEFERRED | Future `Project Phase` behaviour is not decided; nothing here writes it |

### 19.3 New implementation-level open issues

| # | Issue | Why it is open |
|---|---|---|
| **I-1** | Project **public id** vs entity id for document containment | `create_requirement_document` passes the entity's **public** id as `fibery/container-entity-id` (`fibery_http.py:518-520`). Whether Project containment behaves identically is unverified; `P-1` must confirm which id Fibery accepts before I02 is finalised. |
| **I-2** | Whether a Fibery Document can be **deleted or replaced** under a Project without breaking rediscovery | Contract §4.1 requires detecting a replaced UX Document. The replacement's effect on `documents_attached_to_project` ordering and ids is unverified. |
| **I-3** | Maximum practical payload size for a fenced JSON artifact in one Fibery Document | The 400,000-code-point model bound is separate from the Document write limit, which is unmeasured. |
| **I-4** | Whether `document_fingerprint` over a Document containing a JSON fence is stable across Fibery re-serialization | `canonical_markdown` treats fenced content literally, so it should be; `P-1` must confirm for the Architecture Document specifically, since approval binds that fingerprint. |

None of these is an authority question; each is a measurement that `P-1` or a
narrow follow-up probe settles.

**SPEC — gates.** Each carries an explicit blocking gate. A gate blocks
**finalization and live reliance**, never provisional development against the
fake.

| # | Gate |
|---|---|
| **I-1** | `P-1` **before I02 is finalized**, and before **I04/I05 rely on live behaviour**. I02 may be implemented provisionally to make I03 runnable. |
| **I-2** | Probe **before final freshness and discovery verification in I05/I10/I11**, and before any live cycle relies on replacement detection. |
| **I-3** | Probe **before final verification of live artifact writes in I07/I08/I11**. It must establish the supported payload size, the refusal behaviour above it, and what a partial write leaves behind. |
| **I-4** | `P-1` **before I06/I10/I11 rely on it live**, because the Architecture `content_fingerprint` binds approval and currentness. |

**SPEC.** These gates are measurements. None of them **MAY** be converted into an
authority decision; if a probe contradicts the frozen contract, section 21
applies and the **contract** is revisited.

---

## 20. Acceptance for this specification

Ready for independent review when: no U-3/U-4/U-7 mechanism is ambiguous
(sections 2–6, 12–13); every artifact has a closed schema, version and digest
rule (sections 4–7, 11); every command has deterministic semantics and result
codes (section 13); recovery is executable from durable state with no hidden
intent (section 14); every frozen contract row maps to test or probe evidence
(section 17); and no code has been written.

## 21. Conflicts with the frozen contract

One tension, reported rather than redesigned:

**Contract §5 requires direct Project containment; the current adapter cannot do
it, and the shape of the fix is unverified.** Section 2 specifies the minimal
adapter, but `I-1` records that the exact container-entity-id semantics for a
Project are unconfirmed. If `P-1` shows Fibery does not support an
entity-contained Document on a Project the way it does on a Requirement, then
contract §5 is not implementable as frozen and **the contract — not this
specification — must be revisited**. No alternative storage model is proposed
here.

No other conflict was found. Section 17.3 of the contract already records the
adapter gap, so this is a sharpening of a known item, not a new contradiction.

**Implementation authorized: NO.**
