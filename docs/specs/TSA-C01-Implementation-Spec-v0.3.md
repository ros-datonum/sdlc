# TSA-C01 — Implementation Specification v0.3 (draft)

**Status:** DRAFT — HUMAN APPROVAL REQUIRED.
**Implementation authorized:** NO.
**Authority source:** `docs/architecture/TSA-C01-Contract-v0.2.md` (frozen), unchanged.
**Proposed successor to:** `docs/specs/TSA-C01-Implementation-Spec-v0.2.md` (frozen, still in force).
**Repository baseline:** `ros-datonum/sdlc`, `main` at `0c790816ce862a4c2fa873885bf13958bd21ace9` (carried over from v0.2).
**Code baseline for the impact assessment:** `impl/tsa-c01-i06-architecture` at `2fe6770134584e332814a1e9b3eb0829e407b5ae`.

This document closes the **implementation-level** decisions the frozen contract
leaves open. It decides mechanism, never authority. Where the contract froze a
rule, this specification restates only enough to bind the mechanism to it, and
**MUST NOT** be read as amending it. No code is written here, and completing this
document does not authorize writing any.

## Draft v0.3 — status and proposed changes

### Status of this draft

- This draft does **not** supersede Implementation Spec v0.2. v0.2 remains the
  frozen specification until a human approves a successor.
- The two decisions below, **P1** and **P2**, are **PROPOSED**, not approved.
  No human approval of either is recorded in this document, and none is
  established retroactively by it. An implementer's account of an interactive
  choice is not an authority record.
- Writing or committing this draft is neither a freeze nor an implementation
  authorization.
- The code baseline named in the header is used only to assess impact. Code is
  not a source of authority for either proposal.
- Contract v0.2 is unchanged and is not amended here. Neither proposal
  contradicts a FROZEN contract provision (section 21).

Everything not listed under "Changed sections" is the text of v0.2, verbatim.
Every changed passage carries the marker **[v0.3 PROPOSED — P1]** or
**[v0.3 PROPOSED — P2]** where it stands.

### Changed sections

| Section | Change | Proposal |
|---|---|---|
| Title and header | Version, draft status, proposed-successor line, code baseline for impact | — |
| Draft v0.3 — status and proposed changes | New section: status, summary, impact, acceptance matrix and examples | P1, P2 |
| Version and supersession | One italic note added: the section is carried over from v0.2 and describes v0.2's relation to v0.1. The v0.2 text below it is verbatim | — |
| 8.3 Deterministic rendering | New rule: no code block in the normative sections — a structural rule tied to CommonMark 0.31.2 and a separate strict prefix rule | P2 |
| 8.3.1 Escaping | Mapping table restated in code points; normative vectors added. The pipe row of v0.2 is replaced | P1 |
| 9.1 Response shape | The "other than illustrative diagrams" exception is removed for this slice | P2 |
| 9.2 Deterministic vs semantic | States how a code block is recognised in a raw response value, and the result code | P2 |
| 18.1 Ownership | One clarification of the I06 / I07 boundary for the code-block rules | P2 |
| 21 Conflicts with the frozen contract | One note: no conflict found for P1 or P2 | P1, P2 |

No other section is changed. In particular 4.6.1, 4.6.3.1, 8.1, 8.2, 13.8, 17 and
the work-item table of 18 are verbatim v0.2.

### P1 — the exact replacement for the vertical bar

**Problem.** The v0.2 escaping table wrote the vertical-bar row inside a
Markdown table, where a vertical bar must itself be escaped to be shown. Read as
source text and read as rendered text, that row yields two different
replacements: one backslash then the bar, or two backslashes then the bar. The
second leaves the bar unescaped in a table cell.

**Proposed rule.** `escape_markdown` maps the single code point `[124]` to the
two code points `[92, 124]`: one literal backslash, then the literal vertical
bar. Section 8.3.1 states the whole mapping in code points, so the rule no
longer depends on how any Markdown table is displayed.

**Rationale.** The renderer of 8.3 writes traceability as a pipe table, and
model text reaches its cells through `escape_markdown`. A backslash placed
before a vertical bar is the escape that pipe-table syntax itself provides for
a literal bar in a cell, and the existing backslash mapping `[92] → [92, 92]`
keeps a source backslash distinguishable from that escape. The mapping is
proposed because it fits the renderer this slice already defines and adds no
second escaping mechanism. This draft does not claim that no other encoding of
a vertical bar could work; it proposes this one. How Fibery re-serializes it is
a live-evidence matter and is not asserted here.

**Unchanged by P1.** The backslash mapping; stripping; single-pass application;
the `\r\n`, `\r`, `\n`, `<` and `>` rules; per-element escaping of arrays and
the literal `<br>` join; Unicode normalization; canonical JSON;
`document_fingerprint`; `artifact_digest`; every wire schema version.

### P2 — no fenced diagrams in the first slice

**Problem.** v0.2 section 9.1 excepts "illustrative diagrams" from its ban on
code blocks, while 8.3.1 escapes every newline of every model-supplied string.
A diagram block cannot survive that escaping as a block, and v0.2 defines no
other representation for one.

**Proposed rule.** The first TSA-C01 slice does not support code blocks in the
normative Architecture sections, including illustrative diagrams, whether
closed or not. This **changes** what v0.2 allowed: the exception in 9.1 is
removed for this slice. It was not always forbidden.

Two independent rules refuse; either one is sufficient, and neither stands in
for the other. Their normative text is in 8.3 and 9.2.

- **Rule S — structural.** No indented code block and no fenced code block, as
  CommonMark 0.31.2 classifies them, at the top level or inside any container
  block. The reference to CommonMark is itself part of this proposal; neither
  the contract nor a recorded human decision established it.
- **Rule X — strict prefix.** No line whose first characters, after at most
  three spaces, are three or more consecutive backticks or three or more
  consecutive tildes. This is a deliberately stricter format restriction that
  also refuses some lines rule S reads as inline text. It needs approval in its
  own right.

**Rationale and consequence.**

- `escape_markdown` stays the only escaping rule; no per-context variant, no
  passthrough.
- No diagram parser, diagram renderer or diagram passthrough is introduced.
- Architectural explanation stays text in the existing twelve Architect
  sections.
- Support for native diagram blocks is deferred. This draft creates no work
  item for it.

**The four cases, kept apart.**

| | Case | Status under P2 |
|---|---|---|
| A | A structural code block in a normative section: fenced with backticks or tildes, or indented; at the top level or inside a list item or block quote; closed or not; illustrative or not | Not supported. Backtick and tilde have the same status. Being inside a list or next to a table is not an exemption |
| B | The trailing `` ```json `` envelope (4.1, 8.3.1) | Required and allowed, exactly as in v0.2. The existing carrier path separates it; it is outside the scope of both rules and keeps its I01 schema and digest validation |
| C | Backticks or tildes inside a line of text, or a mention of them | Not a code block for that reason alone, and no character is banned. Allowed only where neither rule S nor rule X is broken and every other representation rule holds |
| D | Input that would need case A | Refused. Never stripped, never closed automatically, never rewritten, never re-expressed as prose by code or by a second model call |

**Stages and result codes.**

| Stage | What is checked | Violation |
|---|---|---|
| I07, raw response (9.2) | Each model-supplied string value, complete and decoded, before stripping and before `escape_markdown` | `INVALID_MODEL_OUTPUT` |
| I06, formed Markdown (8.3) | The normative Markdown `render` produces | `ARCHITECTURE_RENDER_INVALID` |
| I06, handed-in Document (8.3) | The normative Markdown of a persisted post-apply Document, with no assumption that it ever passed I07 | `ARCHITECTURE_RENDER_INVALID` |
| I01, carrier | The trailing envelope: carrier, schema, digest, lineage | The I01 taxonomy, unchanged (`ARTIFACT_MALFORMED` and the codes of 13.8) |

I06 does not reconstruct a raw response from escaped text and does not claim to
have performed the response-stage check. The pre-apply bootstrap carrier
(4.1.1) is outside section 8 and is not affected.

P2 adds no result code, schema field, diagram entity, heading, requirement or
approval rule. It adopts CommonMark's classification for two block types only;
it does not make CommonMark the grammar of the Document.

### Acceptance matrix for P2

Each input is written as a JSON string literal: `\n` is one LF (code point 10),
every space shown inside the quotes is one space (code point 32), and nothing
outside the quotes belongs to the input. The indentation of this document's own
tables and lists describes nothing.

```text
E01  "```\ngraph TD\n```"
E02  "```\ngraph TD"
E03  "~~~\ngraph TD\n~~~"
E04  "~~~\ngraph TD"
E05  "Structure follows.\n~~~mermaid\ngraph TD\n~~~"
E06  "Structure follows.\n\n    graph TD"
E07  "Structure follows.\n    continued text"
E08  "- ~~~\n    ordinary text\n    ~~~"
E09  "- ~~~\n  ordinary text"
E10  "- ordinary ~~~ marker"
E11  "| Requirement ID | Gaps |\n|---|---|\n| SDLC-FR-0007 | ~~~ |"
E12  "~~~"
E13  "```inline``` then text"
E14  the trailing envelope: "```json\n" + canonical artifact JSON + "\n```\n"
```

"Surface" names the surface the row is stated for. Rules S and X apply the same
way on every surface in scope, so a row stated for one surface also fixes the
classification on the others; the owning stage and the code are those of the
surface.

| Input | Surface | Rule S: CommonMark 0.31.2 class | Rule X | P2 outcome | Owner | Result code |
|---|---|---|---|---|---|---|
| E01 | raw model value | fenced code block, closed | match | refused | I07 | `INVALID_MODEL_OUTPUT` |
| E02 | raw model value | fenced code block, unclosed | match | refused | I07 | `INVALID_MODEL_OUTPUT` |
| E03 | normative Markdown, handed-in | fenced code block, closed | match | refused | I06 | `ARCHITECTURE_RENDER_INVALID` |
| E04 | normative Markdown, handed-in | fenced code block, unclosed | match | refused | I06 | `ARCHITECTURE_RENDER_INVALID` |
| E05 | raw model value, multi-line | fenced code block interrupting a paragraph | match | refused | I07 | `INVALID_MODEL_OUTPUT` |
| E06 | normative Markdown, handed-in | indented code block after a blank line | no match | refused, by rule S alone | I06 | `ARCHITECTURE_RENDER_INVALID` |
| E07 | normative Markdown, handed-in | paragraph continuation; no code block | no match | not refused by P2 | I06 | — |
| E08 | normative Markdown, handed-in | fenced code block inside a list item, closed | no match | refused, by rule S alone | I06 | `ARCHITECTURE_RENDER_INVALID` |
| E09 | normative Markdown, handed-in | fenced code block inside a list item, unclosed | no match | refused, by rule S alone | I06 | `ARCHITECTURE_RENDER_INVALID` |
| E10 | normative Markdown, formed or handed-in | paragraph inside a list item; no code block | no match | not refused by P2 | I06 | — |
| E11 | normative Markdown, formed or handed-in: a table row whose cell is the literal marker | no code block | no match | not refused by P2 | I06 | — |
| E12 | raw model value | fenced code block, empty and unclosed | match | refused | I07 | `INVALID_MODEL_OUTPUT` |
| E13 | raw model value, or normative Markdown | paragraph with inline code; no code block | match | refused, by rule X alone | I07 or I06, by surface | `INVALID_MODEL_OUTPUT` or `ARCHITECTURE_RENDER_INVALID`, by surface |
| E14 | trailing envelope | out of scope of rules S and X | out of scope | unaffected | I01 | the I01 taxonomy |

Notes on the matrix.

- E11 and E12 are different surfaces and get different outcomes on purpose. A
  cell that already stands in a table row is not a code block. The raw value
  `"~~~"` is one, and I07 refuses it before anything is rendered; E11 is
  therefore reachable in a handed-in Document, not through a response I07
  accepted.
- E08 and E09 are refused although no line of them matches rule X. That is why
  rule X is not a check for code blocks, and why a list is not an exemption.
- E13 is refused although it holds no code block. That is the whole effect of
  rule X beyond rule S, and it is what needs approving with rule X.
- "Not refused by P2" says only that. Such input still has to pass every other
  validator: E07 and E10, for example, are still subject to the heading,
  section-class, table and list agreement rules of 8.1–8.3.

The classifications of E01–E13 were checked once against an independent
CommonMark parser (markdown-it-py 4.2.0, `commonmark` preset) in a probe kept
outside the repository; all thirteen agreed with the table. That confirms the
examples. It is not a source of approval, it is not a dependency, and it says
nothing about how Fibery stores or returns such text.

### Bounded impact on the code baseline

Assessed against `2fe6770134584e332814a1e9b3eb0829e407b5ae` only. The
independent review of that candidate closed findings F1–F5 for the defects it
examined; that closure stands for those defects and says nothing about
conformance to this draft.

**P1.**

- The candidate already maps `[124]` to `[92, 124]`.
- After approval the work is to check the four normative vectors of 8.3.1
  against the existing function. No new serializer is needed.

**P2.**

- The candidate refuses every line that starts with three backticks, but its
  public Document validator **accepts a closed tilde block** in a normative
  section. It has no classification of indented code blocks and none of code
  blocks inside container blocks. Placed in a prose section of an otherwise
  valid handed-in Document, with both digests recomputed, the candidate
  **accepts E03, E06, E08 and E09**, which this draft refuses; it already
  refuses E01, E04 and E13, and it accepts E07 and E10 as this draft does.
- The candidate is therefore **not** conformant to this draft, and it does not
  become conformant because this document exists. The existing backtick/tilde
  asymmetry does not become correct either.
- The response-stage check of 9.2 belongs to I07, which does not exist yet.
  Nothing in the I06 candidate performs it or should.
- After approval a separate code and test alignment of I06 is required. It is
  not performed here and is not authorized by this draft.

**What that alignment really involves.** Rule X is a line predicate. Rule S is
not: classifying indented and fenced code blocks the way CommonMark does means
following its block structure — container blocks, paragraph continuation, tab
expansion, and the precedence of the other block starts that decide whether a
line can begin a code block at all. One more regular expression does not do
that, and a check built from line shapes would reproduce the gaps this
correction closes. The outcomes are fixed by 8.3 and the matrix above; how they
are computed is not decided here. In particular this draft neither designs a
Markdown engine nor chooses or adds a dependency. That cost, and the choice
between writing the classification and adopting a library for it, has to be
decided before the code alignment starts, not discovered during it.

**Acceptance examples for that later alignment** (not repository tests today):

1. The four pipe vectors of 8.3.1 hold for `escape_markdown`.
2. Supported representations keep passing: the matrix rows E07, E10 and E11,
   and a tilde or backtick in the middle of a line of prose.
3. Rows E01–E06, E08, E09, E12 and E13 get the outcome, owner and code the
   matrix gives; closed backtick and closed tilde blocks get the **same**
   outcome.
4. The trailing JSON envelope is untouched (E14): one envelope, one LF before
   its opener in canonical emission, the same accepted read-back forms.
5. The **invariants** that findings F1–F5 established are kept:
   - no fence or other block takes later sections or the envelope out of the
     Document's structure;
   - every traceability table cell agrees with the envelope;
   - the order of persisted traceability is checked, not repaired;
   - canonical emission has exactly one LF before the envelope opener;
   - a heading hidden inside an HTML comment is not counted as a heading.

   This is not a requirement that every existing assertion stays as written.
   Two controls of the candidate are **policy-dependent** and change with P2:
   the control that a closed tilde block in a handed-in Document is accepted,
   and the control that a literal comment marker inside such a block hides no
   heading and is accepted. After approval both must assert the new block
   refusal (`ARCHITECTURE_RENDER_INVALID`) instead of the old acceptance. That
   does not reopen F1 or F5, and it is no ground for removing unrelated
   coverage: the positive controls for supported representations stay. No test
   is edited by this draft.

**No migration.** A change of acceptance policy is not a change of wire schema.
No persisted Document is rewritten, no artifact is re-sealed, and no accepted
input is changed.

**Invariants this draft does not touch.** The sixteen headings and anchors;
exact traceability coverage; table and envelope agreement; ascending persisted
traceability; one LF before the envelope in canonical emission; the accepted
post-apply read-back normalizations; pure render and replay with unmodified
inputs; the renderer-owned arrays and `product_questions`; the fingerprint
region and the closed artifact schemas; the pre-apply I04 bootstrap boundary;
Requirement, UX and human-approval authority; I01–I05 behaviour and their
accepted evidence. `I-4` remains cleared for the probe that was run; a complete
post-apply Architecture carrier is not live-verified by this document.

## Version and supersession

*Carried over from v0.2 unchanged. It records v0.2's relation to v0.1; the
status of v0.3 is stated in the section above.*

**v0.2 supersedes v0.1 for TSA-C01 implementation work starting with I04.**

Reason: the pre-I04 independent review found contradictions in the
bootstrap-state, Architecture bootstrap-carrier and discovery semantics that
required amendment of FROZEN contract text. The contract amendments are made in
Contract v0.2; this specification follows that contract and amends none of it.
v0.1 is left unchanged as the historical record.

Status of completed work, which this version does not reopen:

- **I01, I02 and I03 remain accepted** implementation and evidence.
- **I02 remains VERIFIED** from the `P-1` live probe.
- **The I03 live evidence remains valid**
  (`docs/specs/TSA-C01-I03-P1-Live-Evidence-v0.1.md`, unchanged).
- v0.2 clarifies the pre-I04 semantics **without changing the completed
  mechanisms** of I01–I03. It closes authority/specification contradictions
  discovered before I04 and governs I04 and every later work item.

Every `contract §n` reference in this document is to Contract **v0.2**. Source
line references into `src/` keep the baselines at which they were verified.

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
    ) -> list[DocumentPlacement]: ...   # DocumentPlacement is defined in 2.2.1

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

**SPEC.** Before the derived Architecture Document id (3.5) is adopted as
machine identity, the implementation MUST verify all of the following. The
placement checks 1 and 2 are the adapter-level facts of this section; the order
in which they are applied, and every outcome, is the single algorithm of 3.4.

1. **Project containment** — `entity_public_id` equals the target Project's
   public id, and the container entity type is the Project type;
2. **Parentage** — for children, `parent_document_id` equals the Architecture
   Document id;
3. **Identity** — the payload's `cycle_id` and `project_entity_id` match the
   command's;
4. **Derived identity** — the Document id **is** the derived id of 3.5. No other
   id is adoptable, however valid its content;
5. **Wrong-project refusal** — a derived id failing 1 aborts the command with
   `CYCLE_FOREIGN_PROJECT`;
6. **Non-derived conflict refusal** — one or more valid non-derived same-cycle
   Architecture artifacts (3.4) abort the command with `CYCLE_AMBIGUOUS`.

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
`documents_attached_to_project` returns it; that `create_tsa_child_document`
nests under it; that `child_documents` returns the child; and that content survives
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

### 3.3 Recognising an Architecture artifact

**SPEC.** A Project-contained Document is a **valid Architecture artifact** for
an expected cycle id when: it has valid root placement under the target Project
entity (2.2.1); its body is non-empty and parses as a TSA envelope with
`artifact_type = "tsa.architecture"` and a valid schema and digest; and its
`cycle_id` and `project_entity_id` equal the expected canonical cycle id and
Project entity id. Only at the **derived** id of 3.5 is such an artifact
adoptable; at any other id it is a non-derived same-cycle candidate (3.4), which
is never adopted. A Document whose body is empty is an **empty shell**, and one
that is non-empty but unparseable is **malformed** — neither is a valid
Architecture artifact, and both are classified by 3.4 and contract §14.4. Before
first apply, the conforming body is the bootstrap carrier of 4.1.1 exactly.

### 3.4 Architecture discovery

**SPEC — one ordered algorithm.** The deterministic Architecture id of 3.5 is the
**only adoptable** machine identity. Project listing is diagnostic and refusal
support only: it **never** authorises a create, **never** authorises adopting a
non-derived id, and **never** substitutes another Document id for the derived
one. This is the algorithm contract §5.1.1 freezes, step for step; the two
documents carry the same eleven steps with the same meaning.

```text
STEP  1  canonicalize the cycle id                                    (3.1)
STEP  2  derive the expected Architecture Document id from
           workspace_identity, project_entity_id, canonical cycle_id,
           and the artifact type "architecture"                       (3.5)
STEP  3  resolve that derived id through the placement-aware lookup
           (resolve_placement, 2.2.1)
STEP  4  if the derived id exists, validate ROOT PLACEMENT FIRST
STEP  5  wrong Project, or wrong Project Database placement
           -> CYCLE_FOREIGN_PROJECT, stop
STEP  6  correct placement, empty body
           -> EMPTY_ARCHITECTURE_SHELL recovery condition (3.4.1);
              the Document exists, so this is NOT state A
STEP  7  correct placement, non-empty, and
           malformed carrier / schema / digest, OR
           structurally valid but
             artifact_type != tsa.architecture, OR
             cycle_id != the expected canonical cycle, OR
             project_entity_id != the expected Project entity id, OR
             before first apply, any external binding of 4.1.1 fails
               (workspace_identity, project_code, body.cycle_id, heading)
           -> ARTIFACT_MALFORMED, stop (never adopted)
STEP  8  independently list Project-contained Documents, ONLY to detect
         additional VALID tsa.architecture artifacts carrying the expected
         project_entity_id, the expected canonical cycle_id, valid root
         placement, and a NON-DERIVED Document id
STEP  9  one or more such non-derived same-cycle valid Architecture
         artifacts exist
           -> CYCLE_AMBIGUOUS, refuse
              (true whether the derived id is absent, an empty shell, or
               valid; a valid same-cycle Architecture at a non-derived id
               is NEVER adopted, even when it is the only one that exists)
STEP 10  derived id physically absent, and none exists
           -> state A; create permitted at the DERIVED id only
STEP 11  derived id valid, and no extra same-cycle candidate exists
           -> adopt the DERIVED id only, then classify B / D / E from the
              Input Manifest Document (3.4.1)
```

**SPEC — the empty shell after step 6.** A correctly placed empty derived-id
Document is not a refusal, it is not yet a valid Architecture, and it is **not**
state A: the Document physically exists. Steps 8 and 9 still run. With no
non-derived same-cycle candidate, discovery reports the
`EMPTY_ARCHITECTURE_SHELL` recovery condition (3.4.1, 4.1.1): the shell is
completed in place at that same derived id, and no second Document is created.

**SPEC — why step 7 refuses rather than adopts.** A structurally valid artifact
whose type, cycle or Project disagrees with the identity it occupies is not a
different cycle's artifact to be ignored: the deterministic id this cycle
*requires* is taken by content inconsistent with that identity. Adopting it would
bind the cycle to the wrong artifact, and creating alongside it is impossible,
because the id is the identity. It is malformed.

**SPEC — what counts as a non-derived candidate.** "Plausible" is not a
criterion anywhere in this specification. All of these must hold, and **names
are not among them**:

```text
valid root placement under the expected Project        AND
a non-empty body                                       AND
a valid TSA carrier                                    AND
a valid tsa.architecture schema and digest             AND
project_entity_id == the expected Project entity id    AND
cycle_id          == the expected canonical cycle id   AND
document id       != the expected deterministic id
```

A name match alone is diagnostic only. A malformed Document does **not** become
an ambiguity candidate merely because its name resembles the expected
Architecture name. **One** candidate satisfying the list is sufficient for
`CYCLE_AMBIGUOUS`.

**SPEC — discovery error precedence** for the derived deterministic id, in this
order:

| | Observation | Classification |
|---|---|---|
| 1 | foreign or wrong root placement | `CYCLE_FOREIGN_PROJECT` |
| 2 | correct placement, non-empty but malformed or identity-inconsistent | `ARTIFACT_MALFORMED` |
| 3 | derived absent, an empty shell, or valid — **plus** any valid non-derived same-cycle Architecture | `CYCLE_AMBIGUOUS` |
| 4 | correct placement, empty body, no valid non-derived same-cycle Architecture | `EMPTY_ARCHITECTURE_SHELL` recovery condition — **not** state A; complete in place |
| 5 | derived physically absent, no valid non-derived same-cycle Architecture | state **A**, create permitted at the derived id |
| 6 | valid derived Architecture alone | adopt, then 3.4.1 |

#### 3.4.1 Durable classification after discovery

**SPEC.** The durable lifecycle state set is exactly **{A, B, D, E}**. Discovery
first produces **either** the `EMPTY_ARCHITECTURE_SHELL` recovery condition
**or** exactly one of those four lifecycle states. `C` is never returned: it is a
command-local phase (contract §14.4).

| State | Exact meaning |
|---|---|
| **A** | The deterministic Architecture Document is **physically absent**: the derived id does not exist, and no valid non-derived same-cycle Architecture exists |
| **B** | Exactly one valid derived-id Architecture **bootstrap** Document exists for the cycle — its bootstrap carrier is durable — and no Input Manifest Document exists that causes a more specific bootstrap refusal or a valid accepted Manifest transition to D |
| **D** | A valid accepted Input Manifest exists. Bootstrap ends; the normal recovery classification applies |
| **E** | A refusing bootstrap state: one of the specific conditions of 13.6 |

**SPEC — state A is physical absence, and nothing else.** State A never means
"no valid Architecture", missing valid Architecture content, an empty
Architecture body or an invalid Architecture body. An existing derived-id
Document with an empty body is `EMPTY_ARCHITECTURE_SHELL`; one with malformed
non-empty content is state E, `ARTIFACT_MALFORMED`. `CYCLE_NOT_FOUND` is
therefore returned only where the deterministic Architecture Document is
physically absent, and never for an empty Architecture shell, a malformed
Architecture, a foreign Architecture or an ambiguous identity.

**SPEC — the `EMPTY_ARCHITECTURE_SHELL` recovery condition.** It holds exactly
when the deterministic Architecture Document exists at the expected derived id,
has valid root placement under the expected Project (2.2.1), and
`read_document_content(...).strip() == ""` (14.4). It is an observable recovery
condition **before B**:

```text
not A, not B, not C, not D, not E
not a persisted marker
not an artifact type
not a lifecycle state letter
not a result code            (13.8 is unchanged)
```

The Document identity is durable; the lifecycle state has not reached B, because
the bootstrap carrier is not yet durable. After the shell has been completed in
place and its read-back validated (4.1.1), the condition resolves to **B**.
Steps 8 and 9 of 3.4 still run: with a valid non-derived same-cycle candidate
the outcome is E, `CYCLE_AMBIGUOUS`, and the shell is not completed.

**SPEC — the Input Manifest decides between B, D and E.** After step 11, I04
resolves the Input Manifest at **its** deterministic id (3.5) with the child
predicate (2.2.1) and classifies it **structurally**, through I01's parser and
digest, without executing any I05 admission or currentness logic:

```text
no Input Manifest Document at all                 -> B
an empty Input Manifest shell                     -> E, MANIFEST_SHELL_UNRECOVERABLE
a non-empty Input Manifest that is malformed,
  including one missing its required acceptance   -> E, ARTIFACT_MALFORMED
acceptance.manifest_digest != body.manifest_digest
  on an otherwise well-formed Manifest (7.4)      -> E, MANIFEST_ACCEPTANCE_MISMATCH
a valid accepted Input Manifest                   -> D
```

**SPEC.** "No valid accepted Manifest" therefore never swallows a malformed or
unrecoverable Manifest into ordinary B, and D never means merely that a Manifest
Document exists, that acceptance is missing, that the Manifest is an empty shell,
or that it is malformed.

**SPEC — `C`, exactly.** `C` exists only inside one live `start` invocation:
**after** the caller's Manifest inputs validate and the required explicit
acceptance flags validate, and **before** the atomic valid `tsa.input_manifest`
artifact becomes durable. No API or CLI command can begin in `C`; no recovery
process rediscovers `C`; no command-table row exists for `C`; no persisted
artifact denotes `C`.

**SPEC.** `ARTIFACT_DUPLICATE` is **not** used for an Architecture identity
conflict. It keeps its existing meaning: a duplicate per-type, per-iteration
artifact in the normal lifecycle, where this specification already assigns it.

**SPEC — the role of names.** The Architecture Document name remains navigation
metadata only. The expected name is

```text
<Project Code> — TSA <cycle-id> — Architecture
```

A name match **may** be reported diagnostically and **may** help a human locate a
suspicious Document. It **never** establishes cycle identity, **never** authorises
adoption, **never** authorises a create, and **never** by itself causes
`CYCLE_AMBIGUOUS`. Only valid machine-readable same-cycle Architecture metadata
under another id creates the non-derived candidate conflict.

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

**SPEC — unknown mutation outcome: two levels, by artifact class.** Recovery is
**not** one procedure for every artifact. After **any** unknown bootstrap
mutation outcome (contract §14.4):

1. perform cycle-level rediscovery/revalidation sufficient to establish the
   current Architecture/cycle identity and bootstrap gate preconditions;
2. rediscover the specific mutation target using that artifact class's
   deterministic identity and placement rules;
3. classify durable state;
4. only then decide whether retry with the **same** deterministic id is
   permitted.

```text
Architecture target   full Architecture discovery (3.4) IS the artifact-specific
                      rediscovery, and is also the cycle-level revalidation
child target          cycle-level revalidation FIRST, then the child's own
                      deterministic-id / parent / schema rediscovery
```

The procedure of one artifact class **MUST NOT** be substituted for another:
Architecture discovery alone never decides whether a child mutation landed, and
a direct child lookup alone never replaces the cycle-level revalidation. After
bootstrap the same two levels apply, with the normal gate (contract §14.1.1) as
the cycle-level revalidation.

**SPEC — `tsa.architecture`.** A direct lookup of the derived id is **not**
sufficient: it would miss the mandatory non-derived-candidate conflict check.
After an unknown Architecture create outcome, or an unknown bootstrap carrier
write outcome:

1. recompute the derived Architecture id from the tuple;
2. rerun the **full** Architecture discovery algorithm of 3.4, all eleven steps;
3. **only if** the derived id is absent **and** no valid non-derived same-cycle
   candidate exists may the create be retried, using **the same derived id**,
   never a new one;
4. derived id present and valid, with no conflict → adopt;
5. an extra valid non-derived same-cycle Architecture exists →
   `CYCLE_AMBIGUOUS`;
6. foreign placement of the derived id → `CYCLE_FOREIGN_PROJECT`;
7. malformed content at the derived id → `ARTIFACT_MALFORMED`.

A derived id that is present, correctly placed and **empty**, with no conflict,
is the `EMPTY_ARCHITECTURE_SHELL` recovery condition of 3.4.1 and 4.1.1 — not
state A: the carrier is written in place, and no create is retried. That is also
the classification after a bootstrap carrier write that did not land.

The two Architecture windows stay distinct:

```text
UNKNOWN create outcome in state A
  -> full discovery; it may observe the derived Document absent, an
     EMPTY_ARCHITECTURE_SHELL, a valid B, malformed, foreign or ambiguous;
     classify and recover from that durable state
KNOWN create success, then UNKNOWN bootstrap carrier write outcome
  -> the Document is already known to exist; cycle-level revalidation and the
     Architecture-target full rediscovery (the same discovery);
     never another create_project_document
```

For this artifact class the full discovery is **both** levels at once: it is the
cycle-level revalidation and the artifact-specific rediscovery. No separate
child procedure applies.

**SPEC — child artifacts** (`tsa.input_manifest`, `tsa.process_result`,
`tsa.review_result`, `tsa.human_decision`). Recovery has **both** levels, in this
order. The artifact-specific level keeps the deterministic-id mechanism, bound to
the expected parent, type and iteration, and **MUST NOT** use the Project
Architecture listing rules of 3.4 as the test of whether the child mutation
landed:

1. **cycle-level revalidation first** — through the gate that applies (the
   bootstrap gate before a valid accepted Manifest exists, the normal gate
   after), re-establish that the deterministic Architecture identity is still
   unambiguous, that its root placement is still valid, that no new foreign or
   non-derived Architecture conflict exists, and that the cycle has not moved
   into a conflicting state. A failure here is that refusal; the child is not
   written;
2. recompute the child's deterministic id from the tuple;
3. `resolve_placement(id)`;
4. if **absent** → the original create did not become durable; a retry is
   permitted only after step 1 and the pre-write revalidation of 14.1, and only
   with **the same deterministic id**, never a new one;
5. if **present** → validate child placement against the expected Architecture
   parent (2.2.1), envelope `artifact_type`, `iteration`, `cycle_id`,
   `project_entity_id` and lineage (4.6);
   - all valid → adopt;
   - malformed, wrongly placed, or lineage-conflicting → **refuse**
     (`ARTIFACT_MALFORMED` / `CYCLE_FOREIGN_PROJECT` / `ARTIFACT_DUPLICATE`);
   - present and **empty** → the shell rule for that artifact type (13.7-7).

The per-type detail — the `child_documents` cross-check for iterated artifacts
and each crash window — is 13.7-4 and 14.4.1. For `tsa.input_manifest` step 4 is
available only to the **same** `start` invocation, which still holds the
validated inputs of its command-local `C` phase; a later invocation that finds no
Manifest Document classifies durable state **B** (3.4.1).

**SPEC — unknown Input Manifest create or write outcome.** After step 1, the
Manifest is rediscovered by its deterministic **child** id, validating the exact
deterministic Input Manifest id, the expected Architecture parent, child
placement, empty versus non-empty, carrier, schema and digest, and the
acceptance binding:

```text
child absent                               -> the create did not become durable;
                                              retry only under step 4, with the
                                              SAME deterministic child id
child present and empty                    -> E, MANIFEST_SHELL_UNRECOVERABLE
child present, non-empty, malformed        -> E, ARTIFACT_MALFORMED
child present with an acceptance mismatch  -> E, MANIFEST_ACCEPTANCE_MISMATCH
child present, valid and accepted          -> D
```

The Project Architecture listing is **not** the artifact-specific test of
whether the Manifest create landed, and the child create is never retried blind.

**SPEC.** A deterministic id **does not by itself prove ownership**. Containment
**MUST** still be validated on the resolved Document: a colliding or
maliciously pre-created id is detected there, not by the derivation.

**SPEC.** Names remain human navigation metadata only (contract §5.1). A name
may be reported diagnostically; it never establishes identity, never authorises
adoption or a create, and never causes ambiguity by itself. Identity is the
derived id.

**SPEC.** Because the id is a pure function of durable inputs, a restart
recomputes it with no journal, and a duplicate create is structurally impossible:
a second create with the same id targets the same Document.

**SPEC.** After an unknown create or write outcome, rediscovery is therefore
always the two levels above, re-run in full: for the Architecture, the complete
discovery of 3.4 (contract §5.1.1), which serves as both levels; for a child,
cycle-level revalidation followed by the deterministic-id and
expected-parent/type/iteration check. It is never a direct lookup alone — not of
the derived Architecture id, and not of a child id. There is **no** local
database, journal or cached intent: every classification is derived from durable
Fibery state.

---

## 4. U-4 — the TSA artifact envelope

### 4.1 Carrier

**SPEC.** Every immutable TSA artifact is one Fibery Document whose Markdown is:
a level-1 heading with the artifact's human name, one short prose paragraph, and
exactly one `` ```json `` fenced payload — the pattern of
`process_result.py:216-227`, parsed back with the same `JSON_FENCE` shape.

**SPEC.** The Architecture Document is different. **After the first Architect
output has been applied** it is human-readable Markdown under the 16 frozen
headings (section 8), **plus** one trailing `` ```json `` envelope carrying its
machine metadata and traceability block. Its prose is the canonical
architecture; the fence is metadata about it. Before first apply it is the
bootstrap carrier of 4.1.1 (contract §8, lifecycle boundary).

#### 4.1.1 The pre-apply bootstrap carrier

**SPEC.** The 16-heading representation applies **after** the first Architect
output has been applied. **Before** first apply — durable state B, and state D
until the first apply lands — the Architecture Document uses exactly this carrier
and nothing else:

````text
# <Project Code> — TSA <cycle-id> — Architecture
<blank>
Bootstrap shell. No Architect output has been applied.
<blank>
```json
<canonical JSON of the sealed tsa.architecture artifact>
```
````

followed by one final newline. Line 3 is that exact sentence, verbatim. The
example above is wrapped in a four-backtick fence only so that the literal
three-backtick `json` envelope can be shown inside it; the carrier itself
contains exactly one three-backtick fence.

**SPEC.** The fenced payload is the **sealed** `tsa.architecture` artifact. Its
envelope carries every common field of 4.2 — `artifact_type`, `schema_version`,
`workspace_identity`, `project_entity_id`, `project_code`, `cycle_id`, `body`,
`artifact_digest` — with `iteration` **absent** (4.5). Its `body` contains exactly
`cycle_id` and `created_at`, and **no** renderer-owned or applied field. In
particular `content_fingerprint` is **not** set in bootstrap state.

**SPEC.** The pre-apply carrier therefore has exactly one level-1 human-name
heading, one frozen bootstrap sentence, one trailing JSON envelope, and **no
level-2 Architecture headings**.

**SPEC — these are not two formats at one lifecycle point.** They are two
lifecycle points:

```text
PRE-APPLY           the bootstrap carrier above
POST-FIRST-APPLY    the full 16-heading Architecture carrier
```

At first apply, I06/I07 replace the bootstrap prefix with the deterministic
16-heading rendered Architecture, **preserving the same Architecture Document
id**. Bootstrap **MUST NOT** populate the mandatory headings with placeholders,
**MUST NOT** use the `N/A` form, and **MUST NOT** invoke the I06 renderer.

**SPEC — bootstrap emission form.** The carrier above, **including** its one
final newline, is the **emission form**: the exact text the bootstrap writer
**MUST** emit. Nothing in this section relaxes it, and the bootstrap artifact's
fields are unchanged.

**SPEC — bootstrap accepted read-back form.** The emission form is **not** what
Fibery returns. The `P-1` live probe (I03 evidence, section 4 "Content round
trip") observed that Fibery re-serializes a stored Document: the emitted final
LF was removed, the JSON fence was preserved byte for byte, and the document
fingerprint was stable. Whole-Markdown byte identity was **not** observed and is
not claimed here. The accepted read-back form is the narrow mechanism that
reflects exactly that verified transport behaviour.

Let `W` be the exact text emitted by the bootstrap writer and `R` the Markdown
returned by Fibery read-back. This is the **only** transport normalization
allowed for bootstrap carrier read-back at I04:

```text
bootstrap_readback_matches(W, R):

    if R == W:
        return true

    if W.endswith("\n") and R == W[:-1]:
        return true

    return false
```

That is: `R == W`, **or** `W` ends with its one final `"\n"` and `R` equals `W`
with that **one** final `"\n"` removed. No other difference is accepted by the
bootstrap lifecycle validator. It is intentionally narrower than general
Markdown equivalence, because the bootstrap carrier has no list or prose
structure that would need broader normalization. In particular none of these is
accepted:

```text
a heading rewrite                  a sentence rewrite
an extra or a missing blank line   a JSON normalization change
an envelope change                 a second fence
additional Markdown
```

The JSON fence payload **MUST** still be byte-for-byte identical.

**SPEC — the trusted expected context.** `W` is never built from identity values
learned from `R`: that would validate the Document against itself. For one I04
bootstrap discovery the engine first fixes these six values, each from a source
**independent of the Document's content**:

| Expected value | Trusted source |
|---|---|
| `expected_workspace_identity` | the current workspace identity the engine uses to derive deterministic TSA ids (3.5) — the I02 workspace identity, exposed by the existing `ArchitectureWorkspace.lock_scope` (2.1) |
| `expected_project_entity_id` | the freshly resolved target `ProjectRecord.id` |
| `expected_project_public_id` | the freshly resolved target `ProjectRecord.public_id`, used for placement validation (2.2.1) |
| `expected_project_code` | the freshly resolved target `ProjectRecord.code` |
| `expected_cycle_id` | the canonical cycle id (3.1) of the caller or of discovery, obtained independently of Document content |
| `expected_architecture_document_id` | the deterministic id of 3.5, derived from `expected_workspace_identity`, `expected_project_entity_id`, `expected_cycle_id` and `architecture` |

The Document's own envelope values are **not** trusted sources for any of them.

**SPEC — one workspace identity source.** `lock_scope` is the already frozen
representation of the same `host/<space-uuid>` identity: the HTTP adapter returns
`FiberyClient.workspace_identity` from it (`fibery_http.py:971-972`). I04 reuses
that exact existing value. No second workspace identity source is introduced, no
protocol field is added, and no new I02 behaviour is required: I02 already
provides the workspace identity, `ProjectRecord.id`, `.public_id` and `.code`,
placement reads, and deterministic-id Document resolution. Comparing the
persisted artifact against the expected context is I04's.

**SPEC — external binding before B.** Before a non-empty pre-apply Architecture
Document can be classified B (or D before first apply), **all** of these must
hold:

```text
placement
  Document id                 == expected_architecture_document_id
  valid Project root placement, using the expected Project type and
    expected_project_public_id                                   (2.2.1)

artifact
  artifact_type               == "tsa.architecture"
  schema_version              == 1
  artifact_digest             valid                              (5.2)
  workspace_identity          == expected_workspace_identity
  project_entity_id           == expected_project_entity_id
  project_code                == expected_project_code
  cycle_id                    == expected_cycle_id
  iteration                   absent

bootstrap body
  keys                        exactly cycle_id + created_at
  body.cycle_id               == expected_cycle_id
  body.created_at             the frozen timestamp shape of the I01 schema
  no applied or renderer-owned field
```

Only after these bindings pass may `W` be reconstructed. A self-consistent
artifact carrying the wrong `workspace_identity`, `project_entity_id`,
`project_code` or `cycle_id` is **not** accepted merely because its
`artifact_digest` recomputes correctly: the digest proves internal consistency,
never ownership or context. A correctly placed non-empty derived Document that
fails any artifact or bootstrap-body binding is `ARTIFACT_MALFORMED` (3.4
step 7; 13.6 row E — malformed non-empty bootstrap artifact): no overwrite, no
repair, no model call, and no other Architecture Document is created. Wrong
placement is **not** malformed: it keeps the precedence of 3.4,
`CYCLE_FOREIGN_PROJECT`.

**SPEC — Project Code is conformance, not machine identity.**

```text
project_entity_id   participates in machine identity (3.5)
project_code        does NOT; the deterministic Document id does not include it
project_code        IS validated carrier metadata and human-navigation content
```

Bootstrap carrier conformance requires
`envelope.project_code == expected_project_code`, and the level-1 heading uses
that same externally resolved value. `expected_project_code` is never derived
from `R`. Where `ProjectRecord.code` is absent, no trusted expected value
exists, the binding cannot hold, and the Document is refused before B is
accepted; a code is never invented.

**SPEC — missing Project Code before a bootstrap mutation.** This is I04
bootstrap-context validation, not I05 Requirement admission: the Project must
provide the trusted metadata needed to construct and validate the Architecture
root carrier. Immediately before any bootstrap create or write that needs the
canonical Architecture name or carrier, I04 requires a freshly resolved
`ProjectRecord.code` that is a non-empty string. If it is `None`, or
`code.strip() == ""`, the command returns:

```text
FIBERY_READ_FAILED, exit 1

no create_project_document
no write_document_content into an existing EMPTY_ARCHITECTURE_SHELL
no invented, fallback or derived Project Code
no model call
no retry
```

The refusal precedes the remote mutation, so nothing is written:

| Path | Refused before | Durable state afterwards |
|---|---|---|
| state A, `start` | `create_project_document` | still A — no Document is created |
| `EMPTY_ARCHITECTURE_SHELL`, `start` or `resume` | the bootstrap carrier write | still `EMPTY_ARCHITECTURE_SHELL` — no transition to B |

In state A the refusal comes before the create on purpose: the invocation
already knows it could not complete the carrier, so it never leaves behind an
empty shell of its own making. `rework`, `approve` and `inspect` under
`EMPTY_ARCHITECTURE_SHELL` attempt no bootstrap write, do not construct `W`, and
keep their cells of 13.6.

**SPEC — why `FIBERY_READ_FAILED`, and why the durable case differs.**
`ProjectRecord.code` is required trusted Project metadata; a Project entity
from which it cannot be established is Fibery data that could not be obtained
in the required usable form (13.8). It is not `ARTIFACT_MALFORMED`, because on
the state A path no Architecture artifact exists; not `FIBERY_WRITE_FAILED`,
because no write was attempted; not `CYCLE_NOT_FOUND`, because no cycle identity
is absent.

```text
PRE-WRITE                   no conforming artifact can be constructed
                            -> FIBERY_READ_FAILED
DURABLE NON-EMPTY DOCUMENT  the artifact exists but cannot satisfy the required
                            external carrier binding
                            -> ARTIFACT_MALFORMED   (unchanged, above)
```

**SPEC — what `W` is.** In the mutation cycle of a bootstrap write, `W` is the
text that write just emitted, itself built from the trusted expected context and
the `created_at` generated for that write. On any later read — discovery
classifying B, or D before first apply — no emitted text is held and no journal
exists, so `W` is reconstructed in exactly this order:

```text
1. validate the carrier and envelope of R sufficiently to obtain the
   candidate artifact
2. validate the candidate artifact against ALL of the trusted expected
   context above (placement and artifact bindings)
3. validate the bootstrap body shape
4. take ONLY the persisted created_at from the now externally bound,
   schema-valid bootstrap artifact
5. construct an EXPECTED bootstrap artifact from trusted context:
     artifact_type       "tsa.architecture"
     schema_version      1
     workspace_identity  expected_workspace_identity
     project_entity_id   expected_project_entity_id
     project_code        expected_project_code
     cycle_id            expected_cycle_id
     iteration           absent
     body                { cycle_id:   expected_cycle_id,
                           created_at: the validated persisted created_at }
6. seal that expected artifact with the frozen artifact-digest algorithm (5.2)
7. require the candidate persisted artifact payload to equal the expected
   sealed bootstrap artifact exactly
8. construct W from
     the heading   # <expected_project_code> — TSA <expected_cycle_id> — Architecture
     the exact frozen bootstrap sentence
     the canonical JSON of the expected sealed artifact
9. bootstrap_readback_matches(W, R):
     R == W, or R == W without exactly one terminal LF
```

Only then is the Document classified B. A failure at any of steps 1–9 is
`ARTIFACT_MALFORMED`; nothing is written.

**SPEC — why `created_at` may come from `R`.** `created_at` differs from the
identity fields. No external journal or local intent record exists from which a
restarted process could recover the original timestamp, so later discovery
reuses the persisted value — but only **after** the artifact has passed schema
and digest validation and every externally knowable identity and context field
has been checked against the trusted expected context (steps 1–3), and only if
the timestamp itself satisfies the frozen timestamp schema. It establishes none
of: workspace identity, Project identity, Project Code, cycle identity, Document
identity. `W` is therefore not self-validating: every identity-bearing byte of
`W` comes from trusted context, and the one byte range that does not carries no
identity.

**SPEC — normative negative examples.** In each, the derived-id Document is
correctly placed, non-empty, and its `artifact_digest` is valid:

```text
workspace_identity wrong                              -> ARTIFACT_MALFORMED
project_entity_id wrong                               -> ARTIFACT_MALFORMED
project_code wrong                                    -> ARTIFACT_MALFORMED
cycle_id wrong                                        -> ARTIFACT_MALFORMED
body.cycle_id wrong                                   -> ARTIFACT_MALFORMED
heading Project Code differs from the trusted
  ProjectRecord.code                                  -> ARTIFACT_MALFORMED
heading cycle differs from the expected canonical
  cycle                                               -> ARTIFACT_MALFORMED
```

**SPEC — the parser boundary.** `extract_architecture_envelope` (I01) continues
to be a low-level carrier-envelope parser only. It is not proof of a
lifecycle-conforming Architecture, and it does **not** decide lifecycle read-back
equivalence. For the pre-apply state, I04 bootstrap lifecycle validation
requires **both**:

```text
1. bootstrap_readback_matches(expected_emitted, actual_readback)
AND
2. envelope parse / schema / digest / identity validation, where identity
   means the external binding against the trusted expected context above
```

`expected_emitted` is always built from trusted context, as above. A read-back
may parse successfully and still fail exact bootstrap lifecycle validation: two
arbitrary non-empty prefixes that the low-level envelope parser accepts are
therefore **not** both conforming bootstrap carriers. A non-empty pre-apply body
that fails either requirement is not durable state B; it is a malformed carrier,
`ARTIFACT_MALFORMED` (3.4 step 7). Inside the mutation cycle that is also the
command's result, never a success (14.1). After first apply, I06's 16-heading
validator governs.

**SPEC — empty Architecture Document.** A remote Document at the derived id whose
body is empty is the **`EMPTY_ARCHITECTURE_SHELL`** recovery condition (3.4.1).
It is **not** state A — the Document physically exists, so the create is never
repeated — and it is not yet state B. The engine adopts that **same**
deterministic Architecture Document id. Once the bootstrap gate succeeds —
including the non-derived conflict check of 3.4 — `start` or `resume` (13.6)
writes the exact emission form above into it, through exactly this mutation
cycle:

```text
fresh placement validation
-> write the exact bootstrap carrier (emission form)
-> read back
-> validate the accepted read-back form and the envelope (both, above)
-> only then B
```

No second Architecture Document is ever created, and no model call is made
merely to recover the shell.

**SPEC — a state A create does not establish B.** `create_project_document`
creates the deterministic Architecture Document with no content. In state A:

```text
1. the bootstrap gate succeeds
2. create_project_document creates the deterministic Architecture Document
3. a successful create alone does NOT establish B
4. before content is written, the new Document is durably observable as
   EMPTY_ARCHITECTURE_SHELL
5. the exact bootstrap carrier is written and validated before B exists

A -> create -> EMPTY_ARCHITECTURE_SHELL -> carrier write + read-back validation -> B
```

No second Document id is ever used. For `start` in state A, create success
**and** carrier validation success give B, and the normal `start` continues;
`ARCHITECTURE_CYCLE_STARTED`, exit 0, is returned only if the complete command
later reaches its normal Review boundary. A successful create response alone
never opens that success path. If carrier validation fails immediately after
the create, the command returns the specific failure of the matrix below.

**SPEC — one bootstrap carrier write contract.** There is exactly one. It
applies identically to an `EMPTY_ARCHITECTURE_SHELL` of either origin:

```text
origin 1   a Document just successfully created by the current state A
           invocation
origin 2   an empty deterministic Architecture Document rediscovered from an
           earlier invocation or crash
```

The origin changes none of: the emitted `W`, the trusted-context validation,
the read-back equivalence, the terminal-LF allowance, the result-code
classification, the retry discipline, the transition-to-B rule. There are no
separate "new-create" and "recovery" write semantics, and the mutation cycle
above is the one cycle for both.

**SPEC — crash between create and carrier.** Where `create_project_document`
landed but the process stopped before a validated carrier write, a restart
discovers `EMPTY_ARCHITECTURE_SHELL` — not A, B, `C`, D or E — and the same
in-place rule completes the **same** deterministic Document.

**SPEC — outcome of the immediate read-back.** Context: a bootstrap carrier
write to an `EMPTY_ARCHITECTURE_SHELL` of either origin — freshly created by the
current state A `start`, or rediscovered from durable state by `start` or
`resume`; the bootstrap gate passed; the engine emitted `W` through
`write_document_content`; and that write call returned normally. The immediate
`read_document_content` then decides the outcome. The four cases are distinct
and are never collapsed. Where the mutation outcome itself is unknown, the
two-level rule of 3.5 applies instead, with no blind retry:

| | Immediate read | Durable observation | Result of the current command |
|---|---|---|---|
| **R-1** | `read_document_content` itself fails | not established by this read | the read-failure and unknown-outcome semantics already frozen (3.5, 14.3 case 9); not redefined here |
| **R-2** | the read succeeds; `R.strip() == ""` — empty or whitespace-only | `EMPTY_ARCHITECTURE_SHELL` | `FIBERY_WRITE_FAILED`, exit 1 |
| **R-3** | the read succeeds; `R` is non-empty but fails carrier, schema, digest, external-binding or read-back-form validation | E — malformed non-empty bootstrap artifact | `ARTIFACT_MALFORMED`, exit 1 |
| **R-4** | the read succeeds; `R` passes `bootstrap_readback_matches` and the artifact and context validation | B | the write is validated; the success path continues (13.6) |

**SPEC — R-2, exactly.** The intended bootstrap write has **not** been validated
as durable, so it is not success:

```text
no transition to B
no model call
no second write and no retry in that mutation cycle or that command
not ARTIFACT_MALFORMED   an empty carrier is a separate class (14.4)
not FIBERY_READ_FAILED   the read succeeded
```

The durable observation remains `EMPTY_ARCHITECTURE_SHELL`. A later command may
rediscover it and run the same in-place recovery again, after gate validation.

**SPEC — R-3, exactly.** No overwrite, no repair, no model call, no transition to
B. `ARTIFACT_MALFORMED` is more specific than the generic `FIBERY_WRITE_FAILED`
and is the one returned.

**SPEC — normative read-back examples.** In each, the write call returned
normally and the read call returned normally. No example performs an automatic
second write:

```text
read returns ""                              -> FIBERY_WRITE_FAILED
read returns only whitespace                 -> FIBERY_WRITE_FAILED
read returns exactly W                       -> bootstrap write validated
read returns W minus its one terminal LF     -> bootstrap write validated
read returns non-empty, wrong heading        -> ARTIFACT_MALFORMED
read returns non-empty, wrong JSON bytes     -> ARTIFACT_MALFORMED
```

```text
derived Document physically absent -> durable state A
empty Architecture Document        -> EMPTY_ARCHITECTURE_SHELL, recoverable in
                                      place; not a state letter
exact bootstrap carrier            -> durable state B (D once a valid accepted
                                      Manifest exists)
full valid post-apply Architecture -> a later lifecycle state
```

The words "Bootstrap shell." in line 3 of the carrier describe the durable
bootstrap carrier of state B. They do not name the `EMPTY_ARCHITECTURE_SHELL`
condition, whose body is empty.

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
handled by contract §14.3 case 7 and section 14.4 here. The two bootstrap shells
are decided before case 7 is reachable, and they are **not** alike: an empty
Architecture shell is the recoverable `EMPTY_ARCHITECTURE_SHELL` condition
(3.4.1, 4.1.1) — never state A — and an empty Input Manifest shell is durable
state E, `MANIFEST_SHELL_UNRECOVERABLE` (3.4.1, 13.7-7) — unrecoverable, yet
still not malformed.

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
body.manifest_digest?            string   absent before first apply
body.content_fingerprint?        string   document_fingerprint of this Document's
                                          Markdown, absent before first apply
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
counts as **not accepted** (contract §3.3). "Not accepted" authorises nothing; it
does not return the cycle to state B. A persisted Manifest in this condition is
durable state **E** (3.4.1, 13.6), as is a non-empty Manifest with **no**
`acceptance` at all, which is `ARTIFACT_MALFORMED`. There is no `accepted =
false` and no partial Manifest representation.

---

## 8. Architecture Document representation

**SPEC — when this section applies.** Everything in section 8 describes the
Architecture Document **after the first Architect output has been applied**.
Before first apply the Document is the pre-apply bootstrap carrier of 4.1.1,
which carries no level-2 heading at all. Contract §8 freezes that lifecycle
boundary and the exemption; this specification only supplies the emitted bytes
and the accepted read-back form (4.1.1).
Bootstrap is not required to satisfy section 8, and must not fabricate
placeholder or `N/A` headings to appear to.

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

**SPEC — no code block in the normative sections. [v0.3 PROPOSED — P2]** In
this slice the sixteen normative sections carry no code block, illustrative
diagrams included. Two independent rules refuse; a Document conforms only when
it breaks neither.

*Scope.* The *normative Markdown* is the Document's Markdown excluding the
trailing envelope (4.6.1), separated by the existing carrier path (4.1). The
envelope is outside the scope of both rules and keeps its I01 carrier, schema
and digest validation unchanged. The pre-apply bootstrap carrier (4.1.1) is not
subject to section 8.

*Rule S — structural code blocks.* **[PROPOSED normative reference]** The
classification is that of CommonMark 0.31.2
(<https://spec.commonmark.org/0.31.2/>): section 2.2 for tabs in block
indentation, section 3 for block structure and precedence, sections 4.4 and 4.5
for indented and fenced code blocks, and section 5 for container blocks. The
normative Markdown, read as one complete document under those sections,
**MUST NOT** contain an indented code block or a fenced code block, at the top
level or inside any container block. What the block is for, its info string and
whether a closing fence exists create no exception.

Rule S is a classification of block structure and is not replaced by a check of
line shapes. None of these is rule S:

- "any line that begins with four spaces" — an indented line that continues a
  paragraph is not a code block;
- "any list marker followed by fence characters" — only a fence that opens a
  block inside the item is one;
- "the line does not begin with a fence, so it is safe" — a code block inside a
  container block need not begin its line with the fence.

The reference serves to classify these two block types unambiguously. It does
not make CommonMark govern the frozen table rendering, escaping, fingerprints
or any other representation rule of this specification, and it asserts nothing
about what Fibery stores or returns; live transport is a separate question.

*Rule X — strict prefix.* The normative Markdown **MUST NOT** contain a line
whose first characters, after at most three spaces of indentation, are three or
more consecutive backticks (code point 96) or three or more consecutive tildes
(code point 126). This is a separate syntactic restriction, not a check for
code blocks. It refuses some lines that rule S classifies as inline text, and
that extra strictness is deliberate and needs approval in its own right. A
Document in which no line matches rule X has not thereby satisfied rule S.

*Where I06 applies the rules.* Separately, on two surfaces:

- **the Markdown it forms** — a `render` whose output would break rule S or
  rule X is refused with `ARCHITECTURE_RENDER_INVALID`. The input is not
  stripped, closed, rewritten or converted;
- **a handed-in persisted Document** — the public Document validator applies
  both rules to the normative Markdown it is given and does not assume that
  text ever passed I07. A violation is `ARCHITECTURE_RENDER_INVALID`.

I06 does not reconstruct a raw model response from escaped text and does not
claim to have performed the response-stage check of 9.2.

*What is not refused.* Backticks and tildes are not banned as characters, and a
literal marker inside a line is not a code block for that reason alone. Neither
a generated list item nor a table row is exempt from rule S: container context
is classified, not waved through. A line that P2 does not refuse still has to
satisfy every other rule of 8.1–8.3. The acceptance matrix in "Draft v0.3 —
status and proposed changes" fixes the outcomes for exact inputs.

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

**[v0.3 PROPOSED — P1]** The mapping is **normative in code points**. The
description column is for the reader only; where a rendering of this table and
the code points disagree, the code points govern.

| Source | Source code points | Replacement code points | Replacement, described |
|---|---|---|---|
| backslash | `[92]` | `[92, 92]` | two backslashes |
| vertical bar | `[124]` | `[92, 124]` | one backslash, then the vertical bar |
| CR LF | `[13, 10]` | `[60, 98, 114, 62]` | `<br>` |
| CR | `[13]` | `[60, 98, 114, 62]` | `<br>` |
| LF | `[10]` | `[60, 98, 114, 62]` | `<br>` |
| less-than | `[60]` | `[38, 108, 116, 59]` | `&lt;` |
| greater-than | `[62]` | `[38, 103, 116, 59]` | `&gt;` |
| any other code point | itself | itself | unchanged |

`\r\n` is consumed as **one** source sequence and yields **one** `<br>`; it does
not produce two.

**SPEC — normative vectors. [v0.3 PROPOSED — P1]** A conforming
`escape_markdown` produces exactly these outputs. Inputs and outputs are
sequences of Unicode code points of the **string value**.

| Input code points | Output code points |
|---|---|
| `[124]` | `[92, 124]` |
| `[92]` | `[92, 92]` |
| `[92, 124]` | `[92, 92, 92, 124]` |
| `[124, 124]` | `[92, 124, 92, 124]` |

These are values of characters, not the bytes of a JSON source literal. A JSON
document that writes a backslash as two characters in its source still carries
one code point `[92]` in the value; how an example is escaped for JSON, for
Markdown or for a programming language does not change the mapping.

v0.2 wrote the vertical-bar row inside a Markdown table, where its source text
and its rendered text name different replacements. That row is replaced by the
code points above. The backslash row and every other row keep their v0.2
meaning.

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
sprint sequencing, implementation assignments, code blocks, or deployment
commands.

**[v0.3 PROPOSED — P2]** v0.2 read "code blocks other than illustrative
diagrams" here. This draft removes that exception for the current slice: an
illustrative fenced diagram is a code block and is not supported (8.3).
Architectural explanation is given as text in the twelve `architecture`
sections. Native diagram blocks are deferred, and no work item is created for
them by this draft.

### 9.2 Deterministic vs semantic

**SPEC.** A validator decides: schema conformance; unknown keys; all 16 sections
produced; traceability coverage (8.2); enum validity; the absence of
structurally recognisable Tasks/Epics/estimates/code blocks; input-size bounds.

**SPEC — code blocks in the raw response. [v0.3 PROPOSED — P2]** The
structurally recognisable code block is decided on the **raw response**, by the
two rules of 8.3 applied to each model-supplied string value:

- the value checked is the complete string after JSON decoding, **before**
  leading and trailing whitespace is stripped and **before** `escape_markdown`.
  Its line breaks, its indentation and its container context are kept;
- **rule S** is applied to that value read as one complete CommonMark 0.31.2
  document. It is not replaced by checking each line on its own;
- **rule X** is applied separately, to each line of the value, the value being
  split on `\r\n`, `\r` or `\n`.

A response in which any model-supplied string value breaks rule S or rule X
fails its closed contract: `INVALID_MODEL_OUTPUT`. The content is not removed,
rewritten or re-requested as prose. No result code is added.

The validator **MUST NOT** rely on later escaping to turn a forbidden block
into one line carrying `<br>`: that would be silent conversion, not refusal.

This check is on the response and belongs to the Architect stage (I07, section
17 row 15). The renderer (I06) does not repeat it and does not stand in for it;
I06 answers for the Markdown it forms and for the Documents it is handed (8.3).

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
          MANIFEST_ACCEPTANCE_MISMATCH /
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
→ validate UX evidence (§4.1/§4.2) → run Architecture discovery (§3.4)
→ bootstrap gate → create, adopt, or complete in place the Architecture
  Document (bootstrap carrier 4.1.1)
→ persist Input Manifest + acceptance as ONE atomic artifact → normal gate
→ Architect → persist Process Result → apply output to Architecture
→ Reviewer → persist Review Result → stop at the Human Decision boundary
```

**SPEC.** If the cycle is already past any of these points, `start` does **not**
repeat it: it classifies durable state (contract §14.4 state D) and continues
from there, exactly as `resume` would. `start` and `resume` differ only in that
`start` carries the inputs needed to create a manifest that does not yet exist.

### 13.2 `resume`

**SPEC.** Guard → classify durable state → run the bootstrap gate (states A or
B, or the `EMPTY_ARCHITECTURE_SHELL` condition) or the normal gate (state D) →
continue. Never a duplicate model call, never a duplicate artifact. `resume` on
an approved cycle is `CYCLE_APPROVED`, read-only.

**SPEC.** Discovery returns the `EMPTY_ARCHITECTURE_SHELL` condition or one of
**A, B, D or E** only. `resume` can therefore never begin from `C`: that phase
is command-local (contract §14.4) and does not survive a restart. A run that stopped before the atomic Manifest create landed is
rediscovered as **B**. In state **E** `resume` refuses with the specific code of
13.6, writing nothing.

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
Reviewer invocation. Bootstrap states are contract §14.4; cases 1–10 are
contract §14.3. **Discovery returns the `EMPTY_ARCHITECTURE_SHELL` recovery
condition or exactly one of A, B, D or E**, so those are the only rows.
`EMPTY_ARCHITECTURE_SHELL` has its **own** row; it is not a state letter and is
**not** routed through row A.

**SPEC — `C` has no row.** `C` is an internal `start` transition only and
therefore has no independent command × durable-state row. It is the phase
*inside* the `start` cell of row **B**, between validating the caller's Manifest
inputs and acceptance flags and the atomic Manifest create becoming durable. No
command can begin in `C`, and a restart rediscovers **B**, **D** or **E**.

**SPEC — reading the `rework` / `approve` columns.** In states **A**, **B** and
**D → cases 1–3** the command cannot resolve a valid current Review Result for
its exact target, so the cell is the 11.1.1 step 2 outcome: `CYCLE_NOT_FOUND` in
state **A**, where the deterministic Architecture Document is physically absent
and no cycle resolves at all, and `REVIEW_NOT_CURRENT` in **B** and cases
**1**–**3**, where the cycle resolves but the targeted Review does not exist or
is not current. The `EMPTY_ARCHITECTURE_SHELL` row is `REVIEW_NOT_CURRENT` as
well: the Architecture Document exists, so `CYCLE_NOT_FOUND` does not apply, and
neither command performs the shell recovery write. Cases **4**, **8**, **9**, every **E** row, and the
stale-inputs and duplicate rows keep their own more specific code, which also
belongs to step 2.

**SPEC — state E is split by condition.** E is not one cell. Each refusing
bootstrap condition has its own row and its own code, and every E row is
**no mutation, no model call** for every command. A malformed bootstrap artifact
is refused in its **E** row; it is **not** routed through **D → case 8** to
obtain `ARTIFACT_MALFORMED`, because without a valid accepted Manifest the
durable state is not D. **D → case 8** keeps its meaning for a malformed artifact
discovered after bootstrap has completed.

**SPEC — `inspect` in every E row.** All five E rows report `INSPECT_INCOMPLETE`,
exit 0, read-only, with no mutation and no model call. The lifecycle state can
be reported, but in E discovery has failed before the complete bound-input
currentness can be established, so no E row is `INSPECT_CURRENT`.

**SPEC — a failed bootstrap carrier write is not a row.** The **A** and
`EMPTY_ARCHITECTURE_SHELL` rows state the **successful** transition, and the
`start` cell of row **A** passes through `EMPTY_ARCHITECTURE_SHELL` after its
create: the same single carrier write contract governs both (4.1.1). For `start`
in state **A**, and for `start` and `resume` under `EMPTY_ARCHITECTURE_SHELL`,
when the immediate read-back of the bootstrap carrier write
succeeds but is empty or whitespace-only, the command returns
`FIBERY_WRITE_FAILED`, exit 1, with no B, no model call and no second write
(4.1.1, R-2); a non-empty non-conforming read-back is `ARTIFACT_MALFORMED`
(4.1.1, R-3). These are execution failures inside the attempted transition, not
durable-state rows, and the cells below are unchanged.

**SPEC — a missing Project Code is not a row either.** Where the freshly
resolved `ProjectRecord.code` is absent or empty, `start` in state **A** refuses
before `create_project_document`, and `start` or `resume` under
`EMPTY_ARCHITECTURE_SHELL` refuses before the bootstrap carrier write:
`FIBERY_READ_FAILED`, exit 1, no mutation, no model call (4.1.1). The durable
state is unchanged, so no row is added and no cell below changes.

**SPEC — the table obeys 11.1.1.** Every `rework` and `approve` cell is the
result of applying the frozen precedence of 11.1.1, not an independent rule.
Where no valid current Review Result can be resolved for the exact target, the
cell carries the **target-resolution** outcome of 11.1.1 step 2 — the specific
rule where one governs, otherwise `REVIEW_NOT_CURRENT`. No cell expresses a
boundary refusal, because 11.1.1 defines none. Where the table and 11.1.1 could
be read as disagreeing, 11.1.1 governs and the cell is a defect.

| State | `start` | `resume` | `rework` | `approve` | `inspect` |
|---|---|---|---|---|---|
| **A** the deterministic Architecture Document is physically absent | create at the derived id (bootstrap carrier 4.1.1) → continue · mutate ✔ · model ✔ · `ARCHITECTURE_CYCLE_STARTED` · 0 | `CYCLE_NOT_FOUND` · ✘ · ✘ · 1 | `CYCLE_NOT_FOUND` · ✘ · ✘ · 1 | `CYCLE_NOT_FOUND` · ✘ · ✘ · 1 | `CYCLE_NOT_FOUND` · ✘ · ✘ · 1 |
| **`EMPTY_ARCHITECTURE_SHELL`** recovery condition, not a state letter: the derived Architecture Document exists, correctly placed, with an empty body | bootstrap gate validates the shell → complete the bootstrap carrier in place at the same id (4.1.1) → B → continue as row **B** with the caller-supplied inputs · ✔ · ✔, never before a valid accepted Manifest exists · `ARCHITECTURE_CYCLE_STARTED` · 0 | bootstrap gate validates the shell → complete the bootstrap carrier in place at the same id (4.1.1) → stop at B · ✔ · ✘ · `ARCHITECTURE_CYCLE_RESUMED` · 0 | `REVIEW_NOT_CURRENT` · ✘ · ✘ · 1 | `REVIEW_NOT_CURRENT` · ✘ · ✘ · 1 | `INSPECT_INCOMPLETE` · ✘ · ✘ · 0 |
| **B** valid derived bootstrap Architecture, no Input Manifest Document | adopt the derived Architecture → validate inputs and acceptance flags (command-local `C`) → atomic Manifest create → continue · ✔ · ✔ · `ARCHITECTURE_CYCLE_STARTED` · 0 | `MANIFEST_INPUTS_REQUIRED` · ✘ · ✘ · 1 | `REVIEW_NOT_CURRENT` · ✘ · ✘ · 1 | `REVIEW_NOT_CURRENT` · ✘ · ✘ · 1 | `INSPECT_INCOMPLETE` · ✘ · ✘ · 0 |
| **D → case 1** manifest, no Process | run Architect → Review → boundary · ✔ · ✔ · `ARCHITECTURE_REVIEW_READY` · 0 | same · ✔ · ✔ · `ARCHITECTURE_CYCLE_RESUMED` · 0 | `REVIEW_NOT_CURRENT` · ✘ · ✘ · 1 | `REVIEW_NOT_CURRENT` · ✘ · ✘ · 1 | `INSPECT_CURRENT` · ✘ · ✘ · 0 |
| **D → case 2** Architecture == input | apply `intended_output` → Reviewer → boundary · ✔ · ✔ Reviewer only · `ARCHITECTURE_REVIEW_READY` · 0 | same · ✔ · ✔ Reviewer only · `ARCHITECTURE_CYCLE_RESUMED` · 0 | `REVIEW_NOT_CURRENT` · ✘ · ✘ · 1 | `REVIEW_NOT_CURRENT` · ✘ · ✘ · 1 | `INSPECT_CURRENT` · ✘ · ✘ · 0 |
| **D → case 3** Architecture == output | run Reviewer → boundary · ✔ · ✔ · `ARCHITECTURE_REVIEW_READY` · 0 | same · ✔ · ✔ · `ARCHITECTURE_CYCLE_RESUMED` · 0 | `REVIEW_NOT_CURRENT` · ✘ · ✘ · 1 | `REVIEW_NOT_CURRENT` · ✘ · ✘ · 1 | `INSPECT_CURRENT` · ✘ · ✘ · 0 |
| **D → case 4** neither | `ARCHITECTURE_DIVERGED` · ✘ · ✘ · 1 | same · ✘ · ✘ · 1 | same · ✘ · ✘ · 1 | same · ✘ · ✘ · 1 | `INSPECT_INCOMPLETE` · ✘ · ✘ · 0 |
| **D → case 5** Review exists | stop at boundary · ✘ · ✘ · `ARCHITECTURE_REVIEW_READY` · 0 | same · ✘ · ✘ · `ARCHITECTURE_REVIEW_READY` · 0 | persist REWORK → iteration N+1 · ✔ · ✔ · `ARCHITECTURE_REWORK_RECORDED` · 0 | validate → persist APPROVE · ✔ · ✘ · `ARCHITECTURE_APPROVED` · 0 | `INSPECT_CURRENT` · ✘ · ✘ · 0 |
| **D → case 6** Decision exists (REWORK) | continue at N+1 · ✔ · ✔ · `ARCHITECTURE_CYCLE_RESUMED` · 0 | same · ✔ · ✔ · `ARCHITECTURE_CYCLE_RESUMED` · 0 | §11.1.1 step 4 → `DECISION_ALREADY_RECORDED` 0 **or** `DECISION_CONFLICT` 1 · ✘ · ✘ | §11.1.1 step 4 → `DECISION_CONFLICT` 1 · ✘ · ✘ | `INSPECT_CURRENT` · ✘ · ✘ · 0 |
| **D → case 6** Decision exists (APPROVE) | `CYCLE_APPROVED` · ✘ · ✘ · 0 | `CYCLE_APPROVED` · ✘ · ✘ · 0 | §11.1.1 step 4 → `DECISION_CONFLICT` 1 · ✘ · ✘ | §11.1.1 step 4 → `DECISION_ALREADY_RECORDED` 0 **or** `DECISION_CONFLICT` 1 · ✘ · ✘ | `INSPECT_CURRENT` or `INSPECT_STALE` · ✘ · ✘ · 0 |
| **D → case 7** empty Process, Review or Decision shell | by shell type, §13.7-7 · see table · see table · see table | same | empty Decision shell → `DECISION_SHELL_UNRECOVERABLE`; empty Process or Review shell → `REVIEW_NOT_CURRENT` · ✘ · ✘ · 1 | same · ✘ · ✘ · 1 | `INSPECT_CURRENT` · ✘ · ✘ · 0 |
| **D → case 8** malformed artifact | `ARTIFACT_MALFORMED` · ✘ · ✘ · 1 | same · ✘ · ✘ · 1 | same · ✘ · ✘ · 1 | same · ✘ · ✘ · 1 | `INSPECT_INCOMPLETE` · ✘ · ✘ · 0 |
| **D → case 9** unknown outcome | rediscover, then reclassify · ✘ until classified · ✘ · code of the resolved state | same | same | same | `INSPECT_CURRENT` · ✘ · ✘ · 0 |
| **D → case 10** at boundary, no decision | re-present · ✘ · ✘ · `ARCHITECTURE_REVIEW_READY` · 0 | same · ✘ · ✘ · `ARCHITECTURE_REVIEW_READY` · 0 | persist REWORK · ✔ · ✔ · `ARCHITECTURE_REWORK_RECORDED` · 0 | validate → persist · ✔ · ✘ · `ARCHITECTURE_APPROVED` · 0 | `INSPECT_CURRENT` · ✘ · ✘ · 0 |
| **E — ambiguous identity**: a valid same-cycle Architecture at a non-derived id (3.4) | `CYCLE_AMBIGUOUS` · ✘ · ✘ · 1 | same · ✘ · ✘ · 1 | same · ✘ · ✘ · 1 | same · ✘ · ✘ · 1 | `INSPECT_INCOMPLETE` · ✘ · ✘ · 0 |
| **E — foreign derived placement**: the derived id under another Project or the wrong Project Database | `CYCLE_FOREIGN_PROJECT` · ✘ · ✘ · 1 | same · ✘ · ✘ · 1 | same · ✘ · ✘ · 1 | same · ✘ · ✘ · 1 | `INSPECT_INCOMPLETE` · ✘ · ✘ · 0 |
| **E — malformed non-empty bootstrap artifact**: the derived Architecture or the Input Manifest is malformed, identity-inconsistent, missing required acceptance, or carries conflicting bootstrap metadata | `ARTIFACT_MALFORMED` · ✘ · ✘ · 1 | same · ✘ · ✘ · 1 | same · ✘ · ✘ · 1 | same · ✘ · ✘ · 1 | `INSPECT_INCOMPLETE` · ✘ · ✘ · 0 |
| **E — Manifest acceptance bound to another digest** (7.4) | `MANIFEST_ACCEPTANCE_MISMATCH` · ✘ · ✘ · 1 | same · ✘ · ✘ · 1 | same · ✘ · ✘ · 1 | same · ✘ · ✘ · 1 | `INSPECT_INCOMPLETE` · ✘ · ✘ · 0 |
| **E — empty Input Manifest shell** | `MANIFEST_SHELL_UNRECOVERABLE` · ✘ · ✘ · 1 | same · ✘ · ✘ · 1 | same · ✘ · ✘ · 1 | same · ✘ · ✘ · 1 | `INSPECT_INCOMPLETE` · ✘ · ✘ · 0 |
| **stale inputs** any state | `INPUTS_STALE` · ✘ · ✘ · 1 | same · ✘ · ✘ · 1 | same · ✘ · ✘ · 1 | same · ✘ · ✘ · 1 | `INSPECT_STALE` · ✘ · ✘ · 0 |
| **duplicate artifact** | `ARTIFACT_DUPLICATE` · ✘ · ✘ · 1 | same · ✘ · ✘ · 1 | same · ✘ · ✘ · 1 | same · ✘ · ✘ · 1 | `INSPECT_CURRENT` · ✘ · ✘ · 0 |

### 13.7 Resolutions the table settles

**SPEC — 1. `resume` in A and B.** `resume` carries no manifest-building
arguments, so in state B it cannot supply the selection, UX evidence or acceptance
the cycle still needs. It refuses with `MANIFEST_INPUTS_REQUIRED` and directs the
operator to `start` with the same cycle id. In state A there is nothing to resume:
the Architecture Document is physically absent, `CYCLE_NOT_FOUND`. `C` never
arises here, because durable discovery never returns it.

**SPEC — 1a. `resume` under `EMPTY_ARCHITECTURE_SHELL`.** Here there **is**
something to resume: the deterministic Architecture Document exists. `resume`
runs the bootstrap gate, completes the bootstrap carrier in place at that same
id, stops at B without any model call, and returns `ARCHITECTURE_CYCLE_RESUMED`,
exit 0 — the existing durable cycle advanced from an empty shell to recoverable
B. It never returns `CYCLE_NOT_FOUND`. A later `resume`, now in state B, is
`MANIFEST_INPUTS_REQUIRED` as above.

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
| Architecture | the `EMPTY_ARCHITECTURE_SHELL` recovery condition (13.6, its own row — never row A): `start` and `resume` write the exact bootstrap carrier (4.1.1) into the same derived id and validate the read-back — the cycle is then state B; `start` continues, `resume` stops at B; `rework` and `approve` write nothing | ✔ `start` and `resume` only | ✘ for the shell write itself | the code of the `EMPTY_ARCHITECTURE_SHELL` row of 13.6 | that row |
| Input Manifest | **refuse**, durable state **E** (13.6). An empty shell holds no persisted manifest to compare against, and `start` carries no authority to invent one. It is not command-local `C` and is never completed from the current argv | ✘ | ✘ | `MANIFEST_SHELL_UNRECOVERABLE` | 1 |
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
  carries no manifest arguments, durable state B) and from
  `MANIFEST_INPUTS_CONFLICT` (a `start` whose argv disagrees with a **valid
  persisted** manifest, 13.7-2). It is durable state **E**, and it applies to
  every mutating command, not to `start` alone.

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
refusing rows nothing is written at all. The Architecture and Input Manifest
rows are bootstrap rows — the `EMPTY_ARCHITECTURE_SHELL` condition and durable
state E respectively — and are decided before **D → case 7** is reachable; that
case covers the Process, Review and Decision shells only. The two are never
interchangeable: the empty Architecture shell is recoverable in place, the empty
Input Manifest shell is not recoverable at all.

**SPEC — 3. Case 2 vs case 3 when output == input.** When the Architect's
intended output is byte-identical to the input Architecture, both case
predicates hold. **Case 3 wins.** The apply step is a no-op, so treating it as
"already applied" is correct and avoids a pointless write; the engine advances to
Review. This precedence is fixed and not implementation choice.

**SPEC — 4. Unknown create of a child artifact.** Process, Review and Decision
Documents are created with a client-supplied id (3.5). An unknown outcome is
resolved at both levels of 3.5: cycle-level revalidation through the gate first,
and only then the artifact-specific rediscovery — `resolve_document(id)`, then
listing
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
| `CYCLE_NOT_FOUND` | No Architecture Document exists for this cycle id: the deterministic Document is physically absent | 1 |
| `CYCLE_AMBIGUOUS` | A valid Architecture for this Project and cycle exists at a non-derived Document id, or more than one valid machine-readable identity claims the same cycle. One valid non-derived same-cycle Architecture is sufficient | 1 |
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
| `MANIFEST_INPUTS_REQUIRED` | `resume` in durable state B | 1 |
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
| `INSPECT_CURRENT` | `inspect`: state derived, and every bound-input currentness check that applies to that state is established current | 0 |
| `INSPECT_STALE` | `inspect`: state derived, at least one bound input drifted | 0 |
| `INSPECT_INCOMPLETE` | `inspect`: state derived but incomplete, malformed or diverged, or a bootstrap condition — an empty Architecture shell, or a conflicting, ambiguous or foreign bootstrap identity — prevents a complete currentness determination | 0 |
| `DECISION_SHELL_UNRECOVERABLE` | An empty Human Decision shell cannot be completed | 1 |
| `REVIEW_NOT_CURRENT` | Supplied Review Result does not bind the stated target | 1 |
| `WORKSPACE_BUSY` | The workspace guard is held | 1 |
| `FIBERY_READ_FAILED` | A required Fibery read failed, or Fibery data required to establish the command's trusted workspace/entity context could not be obtained in the required usable form | 1 |
| `FIBERY_WRITE_FAILED` | A Fibery mutation failed, or its required immediate read-back did not validate that the intended durable result was established | 1 |

## 14. Execution order and recovery

### 14.1 The mutation cycle

**SPEC.** Every remote mutation follows exactly:

```text
prepare payload
→ revalidate preconditions immediately before the write   (contract §14.2)
→ mutate
→ rediscover / read back immediately
→ validate the intended durable result
→ report success only if that validation passes
```

A read-back showing drift is **not** a success (contract §14.2). A write call
that returned normally is not evidence that its result is durable, and no blind
retry occurs within the same command. `FIBERY_WRITE_FAILED` covers a failed
mutation and a required immediate read-back that did not validate the intended
durable result; it does **not** absorb every bad read-back, because a specific
durable refusal state keeps its specific code where one is frozen. For a
bootstrap carrier write — to a shell just created in state A or to a
rediscovered one alike — an empty immediate read-back means the mutation did not
establish its intended durable result: `FIBERY_WRITE_FAILED`, never success,
while a non-empty non-conforming one is `ARTIFACT_MALFORMED` (4.1.1, R-1 … R-4).

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
| Unknown transport outcome | 9 | Rediscover first at both levels of 3.5: cycle-level revalidation, then the artifact-specific rediscovery of the mutation target — for the Architecture, the full discovery of 3.4 is both; never blind retry |
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

**SPEC — both levels, in every window.** The letters A–F here name crash
windows, not the bootstrap states of 3.4.1. Each resolution above is the
**artifact-specific** level only. It is entered only after the cycle-level
revalidation of 3.5 — here the normal gate, since every window lies after a
valid accepted Manifest — and a direct lookup of the child id never replaces
that revalidation. The bootstrap windows — an unknown Architecture root create,
bootstrap carrier write or Input Manifest create — are resolved by 3.5.

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
is introduced in this specification.

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
| 39 | deterministic Architecture discovery, cases (a)–(g) of contract row 39: derived physically absent → A; correctly placed empty derived Document → `EMPTY_ARCHITECTURE_SHELL`, never A; valid derived only → adopt; valid non-derived same-cycle alone or beside the derived id → `CYCLE_AMBIGUOUS`; foreign derived placement → `CYCLE_FOREIGN_PROJECT`; malformed derived content → `ARTIFACT_MALFORMED`; a name-only match decides nothing | D | I04 |
| 40 | bootstrap A and B: missing manifest not a gate failure; no model call; `C` never rediscovered; empty Manifest shell → E `MANIFEST_SHELL_UNRECOVERABLE`; non-empty Manifest missing acceptance → E `ARTIFACT_MALFORMED`; `EMPTY_ARCHITECTURE_SHELL` (deterministic Document exists, body empty): `start` completes the same id in place and continues, `resume` completes the same id to B → `ARCHITECTURE_CYCLE_RESUMED`, `rework`/`approve` do not repair → `REVIEW_NOT_CURRENT`, `inspect` → `INSPECT_INCOMPLETE`, never `CYCLE_NOT_FOUND`, no duplicate Architecture create; bootstrap read-back accepted only as emitted or less its one final newline; immediate post-write read-back empty or whitespace-only → `FIBERY_WRITE_FAILED`, shell remains, no B, no second write; non-empty wrong heading or wrong JSON bytes → `ARTIFACT_MALFORMED`; valid-digest derived bootstrap artifact with wrong `workspace_identity`, `project_entity_id`, `project_code`, `cycle_id`, `body.cycle_id`, heading Project Code or heading cycle → `ARTIFACT_MALFORMED` (the normative examples of 4.1.1); Project Code missing: state A → `FIBERY_READ_FAILED`, exit 1, no Document create, no write, no model; `EMPTY_ARCHITECTURE_SHELL` with `start`/`resume` → `FIBERY_READ_FAILED`, exit 1, the same empty Document remains, no write, no model; non-empty derived Architecture → `ARTIFACT_MALFORMED`, exit 1, no repair, no model; one carrier write contract for both shell origins: state A → create succeeds → read-back exactly `W` → B; → `W` minus its terminal LF → B; → empty or whitespace-only immediate read-back → `FIBERY_WRITE_FAILED`, `EMPTY_ARCHITECTURE_SHELL` remains; → non-empty bad read-back → `ARTIFACT_MALFORMED`; create lands, crash before content → restart discovers `EMPTY_ARCHITECTURE_SHELL`, same id recovered in place, no second create; an existing `EMPTY_ARCHITECTURE_SHELL` follows the same matrix | D | I04 |
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

**SPEC.** Failure injection MUST cover, at minimum: create returns unknown, for
the Architecture root and for the Input Manifest child; write returns unknown;
read-back returns different content; a bootstrap read-back returns the emitted
carrier less its one final newline (accepted) and with any other difference
(refused); a bootstrap write returns normally and its immediate read-back
returns `""` or only whitespace; a self-consistent bootstrap artifact carries a
wrong workspace identity, Project entity id, Project Code or cycle id; the
target Project resolves with no Project Code, in state A and under an empty
Architecture shell; each bootstrap read-back case above for a Document just
created in state A as well as for a rediscovered empty shell; a state A create
that lands with the process stopping before the carrier write; the
derived Architecture Document exists with an empty body; a valid
non-derived same-cycle Architecture appears, alone and beside the derived id; a
payload digest mismatches; an artifact carries an unknown key.

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
| **I04** | Cycle identity, discovery, bootstrap gate, durable states A/B/D/E, the `EMPTY_ARCHITECTURE_SHELL` recovery condition | I02 | `src/sdlc/tsa_cycle.py`, tests | The ordered discovery algorithm of 3.4 including the non-derived same-cycle conflict; the exact bootstrap carrier of 4.1.1 and its accepted read-back form; empty Architecture shell completed in place, never routed through A; two-level rediscovery after an unknown bootstrap outcome; no blind duplicate create | Contract lifecycle |
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

### 18.1 I04 / I05 / I06 ownership, recorded explicitly

**SPEC — I04 owns:**

- caller cycle-id canonicalization, through the I01 primitive;
- deterministic TSA Document-id derivation (3.5);
- Architecture deterministic identity;
- durable discovery and the ordered algorithm of 3.4;
- classification into durable **A / B / D / E**;
- detection of the `EMPTY_ARCHITECTURE_SHELL` recovery condition;
- the command-local `C` phase within one invocation;
- the bootstrap gate;
- Architecture root create or adopt;
- the bootstrap recovery write that completes an empty Architecture shell in
  place;
- writing the exact bootstrap carrier of 4.1.1 and validating its read-back
  equivalence (`bootstrap_readback_matches`, together with the envelope
  validation);
- cycle-level revalidation during unknown bootstrap mutation outcomes (3.5);
- fixing the trusted expected context and comparing the persisted bootstrap
  artifact against it, including the reconstruction of `W` (4.1.1);
- classifying the immediate read-back of a bootstrap carrier write (4.1.1,
  R-1 … R-4);
- refusing before any bootstrap mutation when the required Project Code cannot
  be established (4.1.1).

**SPEC — I04 consumes:** I01's artifact schemas, parsers and digests; I02's
verified workspace and placement API.

**SPEC — I04 MUST NOT implement:** Requirement admission; UX
admission or currentness; Input Manifest construction semantics; human acceptance
semantics; the 16-heading Architecture renderer; Architect or Reviewer model
calls; Process, Review or Decision lifecycle.

**SPEC — I05 owns:** admission; the Input Manifest; the atomic acceptance
binding. **I06 owns:** the 16-heading renderer and traceability/render
validation. **I07 owns:** persisting Process output and applying the first and
later Architect output through the renderer.

**[v0.3 PROPOSED — P2]** The code-block rules of 8.3 follow the same split.
**I07** applies them to the raw Architect response, value by value, and refuses
with `INVALID_MODEL_OUTPUT` (9.2). **I06** applies them to the normative
Markdown it forms and to a handed-in post-apply Document, and refuses with
`ARCHITECTURE_RENDER_INVALID` (8.3). Neither item takes over the other's check,
neither assumes the other ran, and no function for response handling is added
to the renderer.

**SPEC — the bootstrap gate is self-contained with respect to I05.** Before an
accepted Manifest exists, I04 validates only facts that are already durable:

```text
the canonical cycle id
Project identity
root placement of the derived Architecture id
the absence of any valid non-derived same-cycle Architecture
the bootstrap Architecture carrier and its metadata
malformed or conflicting persisted bootstrap artifacts
evidence that the cycle has already progressed
```

I04 does **not** execute I05 admission or currentness logic. It **may**
structurally detect, and only structurally:

```text
no Input Manifest Document     -> B
an empty Input Manifest shell  -> E
a malformed Input Manifest     -> E
a valid accepted Input Manifest -> D
```

That structural inspection of an existing Manifest child is also what I04
contributes when an Input Manifest create outcome is unknown (3.5). Manifest
creation semantics, admission and acceptance — including any retried Manifest
create — remain I05's.

If a structurally valid accepted Input Manifest already exists, I04 recognises
that bootstrap is complete and reports **D** to later orchestration. Semantic
Requirement and UX admission and currentness remain later work.

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

**[v0.3 PROPOSED — P1, P2]** Neither proposal of this draft conflicts with a
FROZEN contract provision. Contract §8.2 forbids "generated code or
configuration", and contract §16 row 15 requires a structurally recognisable
code block to be refused by the validator; the contract carries no exception
for illustrative diagrams, so P2 removes an exception that only v0.2 of this
specification had introduced. P1 fixes bytes below the level the contract
decides. No contract amendment is needed, and none is proposed.

**Implementation authorized: NO.**
