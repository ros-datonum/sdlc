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
| `create_child_document(name, parent_document_id)` | `fibery_workspace.py:209` | Nesting TSA children |
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
        self, name: str, project_public_id: str
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
(`fibery_http.py:482-524`) with exactly one substitution: the container entity
type is the **Project** Database's type id, resolved from the schema, instead of
the Requirement type id. Everything else is identical and is not re-derived:
client-supplied `fibery/id`, client-supplied `documentSecret`,
`fibery/container-app` from the resolved Space id, `fibery/container-type:
"object"`, `fibery/container-entity-id` = the Project **public** id, no
`fibery/Folder`, then read-back through `resolve_document`.

**SPEC.** `documents_attached_to_project` mirrors
`documents_attached_to_requirement` (`fibery_http.py:239`), filtering
`query-views` on `fibery/container-entity-type` = Project type id and
`fibery/container-entity-id` = the Project public id.

| Protocol method | Fibery operation |
|---|---|
| `create_project_document` | `create-views` (`fibery/type: "document"`, container-type `object`, container-entity-type = Project type id) |
| `documents_attached_to_project` | `query-views` filtered by container entity type + public id |
| `create_child_document` | `create-views` with `fibery/parent-page-id` (unchanged) |
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
| `artifact_digest` | string | Lowercase hex SHA-256, section 6 |

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

---

## 6. Stable finding, risk and disposition identity

Contract §9 binds accepted findings and risks **individually**, and matrix row 49
requires unknown or duplicated references to be refused. That needs identities
that are stable across reads and reproducible from an immutable payload.

**SPEC.** Identity is **derived, not stored as a free-form label**:

```text
<artifact_digest>#<collection>/<index>
```

where `<collection>` is one of `findings`, `risks`, `open_questions`,
`assumptions` (Architect) or `finding_verifications`, `new_findings` (Reviewer),
and `<index>` is the zero-based position in that array of the artifact whose
digest prefixes it.

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
      ├─ canonical_json → sha256 (domain "tsa.input_manifest") → manifest_digest
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
    "anchors": ["3. Solution Structure", "5. Interfaces & Data Flows"],
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
- `anchors` is non-empty and every anchor names one of the 16 headings —
  **one-to-many is allowed**, an unknown anchor is `TRACEABILITY_UNKNOWN_ANCHOR`;
- the Markdown table rows and the JSON rows agree on ids and anchors.

**SPEC.** Whether the architecture *actually satisfies* the Requirement is
Reviewer work and is never claimed by the validator (contract §8.1).

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
A `REWORK` after an `APPROVE` for the same cycle is `CYCLE_ALREADY_APPROVED`.

**SPEC — APPROVE.** Before persist, the exact tuple above is revalidated
(section 14); after persist it is read back and revalidated. Success is reported
only after read-back. It closes the cycle to writes (contract §6).

**SPEC — idempotency.** Re-issuing the identical decision command for the same
cycle and iteration, when a Decision already exists with an identical `body`, is
`DECISION_ALREADY_RECORDED` — a success-shaped no-op that writes nothing.
A decision differing in any bound field is `DECISION_CONFLICT` and fails.

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
sdlc project architecture resume  --project <P> --cycle <id>
sdlc project architecture rework  --project <P> --cycle <id> [--reason <text>]
sdlc project architecture approve --project <P> --cycle <id>
                                  [--accept-risk <ref> --accept-reason <text>]...
                                  --confirm
sdlc project architecture inspect --project <P> --cycle <id> [--json]
```

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

**SPEC.** Permitted only at the Human Decision boundary of a non-approved cycle.
Persists `REWORK`, opens iteration N+1 on the **same** Input Manifest, then runs
Architect → Reviewer → boundary. Outside that state: `REWORK_NOT_AT_BOUNDARY`.

### 13.4 `approve`

**SPEC.** Deterministic and **model-free**. Revalidates the exact tuple, validates
every disposition reference (section 6), persists `APPROVE`, reads back,
revalidates. No downstream side effect of any kind: no Epic, Story, Task, no
Requirement, Project or Project Phase write.

### 13.5 `inspect`

**SPEC.** Read-only. Derives lifecycle state and freshness from artifacts alone
(contract §6). No mutation, no model call. Reports per-input currentness using
the discriminator-aware UX definition (contract §4.4).

### 13.6 Result codes

```text
ARCHITECTURE_CYCLE_STARTED     ARCHITECTURE_REVIEW_READY
ARCHITECTURE_CYCLE_RESUMED     ARCHITECTURE_REWORK_RECORDED
ARCHITECTURE_APPROVED          DECISION_ALREADY_RECORDED
CYCLE_APPROVED                 CYCLE_AMBIGUOUS
CYCLE_FOREIGN_PROJECT          CYCLE_NOT_FOUND
INVALID_CYCLE_ID               SELECTION_DUPLICATE
SELECTION_EMPTY                REQUIREMENT_NOT_ADMISSIBLE
UX_EVIDENCE_INVALID            UX_SCOPE_FOREIGN
HUMAN_ACCEPTANCE_REQUIRED      MANIFEST_ACCEPTANCE_MISMATCH
INPUTS_STALE                   ARCHITECTURE_DIVERGED
ARTIFACT_MALFORMED             ARTIFACT_DUPLICATE
DISPOSITION_UNKNOWN_REFERENCE  DISPOSITION_DUPLICATE_REFERENCE
DISPOSITION_FOREIGN_ITERATION  DECISION_CONFLICT
REWORK_NOT_AT_BOUNDARY         REVIEW_STRUCTURALLY_INVALID
MODEL_RUNTIME_FAILED           INVALID_MODEL_OUTPUT
WORKSPACE_BUSY                 FIBERY_READ_FAILED
FIBERY_WRITE_FAILED
```

---

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

**SPEC.** A Document is an **empty shell** when its content is empty or contains
no `` ```json `` fence. It is **malformed** when a fence exists but the payload
fails parse, schema, unknown-key or digest validation. The two are not
interchangeable: a shell may be completed in place; a malformed artifact may not.

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

**SPEC.** Contract §16's 50 rows map to layers as follows. A `D` test is never
reported as evidence for an `M` or `F` row (contract §16).

| Layer | Rows | Form |
|---|---|---|
| **D — unit** | 5.1–5.3 digests and vectors; 6 identities; 7 schemas; 8.2 traceability validation; 9/10 output validators | pytest, pure functions |
| **D — workspace fake** | 2–8, 10–14, 16–20, 26–35, 37–50 | in-memory `ArchitectureWorkspace` fake, failure injection for cases 1–10 |
| **D — CLI** | 9, 40, 46, 47, 48 | real `cli.main` with a fake transport, as `test_cli_end_to_end.py` does |
| **F — live Fibery** | 22, 23 | `P-1` probe: Project containment, nesting, rediscovery, read-back, partial-write simulation |
| **M — live model** | 24, 25, 30, 36 | controlled probes on synthetic architecture material |

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
| **I10** | Normal recovery gate + cases 1–10 + mutation discipline | I04, I05, I07, I08 | `src/sdlc/tsa_recovery.py`, tests | Every case; gate failure ⇒ zero writes | Frozen recovery semantics |
| **I11** | Human Decision, approval binding, dispositions | I06, I08, I10 | `src/sdlc/tsa_decision.py`, tests | Row 49 testable; idempotent re-issue; conflict refusal | Approval authority |
| **I12** | CLI commands and result codes | I05–I11 | `src/sdlc/cli.py`, tests | Explicit acceptance flags; exit-code policy | Existing commands |
| **I13** | Integration tests across the whole cycle | I01–I12 | `tests/test_tsa_lifecycle_e2e.py` | Full cycle on fakes; failure injection | — |
| **I14** | Live model probes | I07, I08, I12 | evidence doc | Rows 24, 25, 30, 36 | — |

**SPEC.** I03 gates I04–I05 in the sense that a contradicted assumption must be
fixed before admission is built on it, but I04 and I05 may be developed against
the fake in parallel.

---

## 19. Unresolved classification

### 19.1 Closed by this specification

| Item | Closed by |
|---|---|
| **U-3** | Section 2 — protocol methods, Fibery operation mapping, verification obligations, `P-1` probe and the discrepancy rule |
| **U-4** | Sections 4–6 — envelope, canonical serialization, domain-separated digest with normative test vectors, disposition identity |
| **U-7** | Sections 12–13 — exact flags, scope syntax, acceptance flags, result codes, exit-code policy, per-command semantics |

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
