# Fibery API Constraints v0.1

Constraints observed in the current Fibery API while implementing `project init`.
Recorded so later capabilities do not rediscover them.

Everything marked **VERIFIED** was established against the live
`rb-ventures.fibery.io` workspace on 2026-08-31, by request and read-back.

## Endpoints used

| Purpose | Endpoint |
| --- | --- |
| Schema and entities | `POST /api/commands` (batched array of commands) |
| Views, Documents and Folders | `POST /api/views/json-rpc` |
| Rich text content | `PUT /api/documents/<secret>?format=md` |

Authentication is `Authorization: Token <token>`. Rate limits are 3 requests per
second per token and 7 per second per workspace.

## Constraint 1 — WITHDRAWN: Documents *can* be nested, via Folders

**An earlier revision of this document claimed sidebar Documents could not be
nested through the API, and that `project init` therefore had to encode the
hierarchy as a `/`-delimited path in the Document name. That claim is false.**

It was inferred from the published Views API reference, which documents neither
Folders nor the `fibery/Folder` field. The live API supports both.

### The real representation — VERIFIED

Hierarchy is carried by **Folders**, which are separate first-class objects, not
Views:

- a Folder nests under another Folder through `fibery/Parent Folder`
  (self-referencing, `null` at the root);
- a Document (a View of `fibery/type: "document"`) is placed into a Folder
  through its `fibery/Folder` field;
- both belong to a Space through `fibery/container-app`.

The structure required by `Project-Init-Spec-v0.3` section 9 already exists in
the workspace, built by hand, and reads back as:

```text
SDLC              cfcfba13-a215-456e-9cc9-d0b94f497844   Parent Folder = null
- Requirements    acd6b4a4-dad0-4ae4-8bb4-c71cd040bfc9   Parent = SDLC
  - Raw           e3d7abe6-533f-42c1-ab51-be542fca4332   Parent = Requirements
  - Draft         347ceeac-553c-42d1-8849-6ea71faca90d   Parent = Requirements
  - Approved      20cf275a-172f-4fed-b68a-716309426bd5   Parent = Requirements
```

The Document `SDLC-RAW-0001` carries `fibery/Folder = e3d7abe6...`, placing it
in `Raw`.

### The Folder API — VERIFIED, undocumented

`POST /api/views/json-rpc` exposes Folder methods that appear in no published
documentation. Their parameter shapes, as reported by the server's own
validation errors:

```text
query-folders    params: {}                       -> all folders
create-folders   params.values:  [{ fibery/id?, fibery/name?, fibery/rank?,
                                    fibery/container-app?, fibery/Parent Folder?,
                                    fibery/container-entity-type?,
                                    fibery/container-entity-id?,
                                    fibery/private??, fibery/created-by?,
                                    fibery/owner?, fibery/public-id? }]
update-folders   params.updates: [{ id: string, values: {...} }]
delete-folders   params.ids:     string[]
```

Note `create-folders` takes **`values`**, while `create-views` takes **`views`**.

A round trip was executed and verified by read-back: a root Folder, a child
Folder carrying `fibery/Parent Folder`, and a Document carrying `fibery/Folder`
were all created, read back with correct parentage, then deleted with
`delete-views` / `delete-folders`. The workspace was left exactly as found.

Consequence: `project init` creates real Folders. The slash-path emulation and
its `name_is_addressable` guard have been removed; a `/` in a Project Name is
now harmless because names never address anything.

Creating a Field is `fibery.schema/batch` wrapping `schema.field/create` with
`fibery/holder-type`, `fibery/name`, `fibery/type` and `fibery/meta`.

## Constraint 2 — Views and Folders cannot be filtered by name

`query-views` filters on `ids`, `publicIds`, `isPrivate` and `container` only.
Locating a Document or Folder by name requires listing and matching client side.

`query-folders` does accept `{"filter": {"ids": [...]}}`, the same shape as
`query-views` — verified against the workspace, and undocumented. It ignores a
bare `{"ids": [...]}` and returns everything, so the `filter` wrapper matters.

## Constraint 2a — Folder names are not unique — VERIFIED

Fibery permits sibling Folders with the same name under the same parent. The
workspace contains a hand-made top-level Folder named `SDLC`, and `project init`
for a Project named `SDLC` legitimately creates a second one.

Consequence: an object this run created must be read back by its own id.
`project init` resolves each created Folder with
`query-folders {"filter": {"ids": [<id>]}}` and checks its name and parent.
Resolving by `(name, parent)` returned the older Folder and produced a false
`VALIDATION_FAILED` while the created hierarchy was correct.

## Constraint 3 — a Space name and a Space id are both needed

Database names are qualified by Space *name* (`SDLC/Project`), while
`create-views` and `create-folders` need the Space *id* (a UUID). Fibery
publishes no command mapping one to the other, so both are configured
(`FIBERY_SPACE`, `FIBERY_SPACE_ID`).

Deriving the id is still possible: every View and Folder carries
`fibery/container-app`. `scripts/fibery_document_probe.py` reports the candidate
ids using only `FIBERY_HOST` and `FIBERY_TOKEN`.

For this workspace the SDLC Space is `19c62a00-7a47-11f1-aba7-67039973deac`.

## Constraint 4 — Field names must be read from the schema

A Field's prefix is not always its Database's Space: workflow is always
`workflow/state`, document secrets are `Collaboration~Documents/secret`, and
user Fields may be `<Space>/Name` or `<space>/name`. `fibery.schema/query`
resolves them; guessing them does not.

## Constraint 5 — rich text cannot be set when an entity is created

`fibery.entity/create` rejects rich text Fields. The entity is created first,
then its document secret is read and the content written through the documents
endpoint. Project Description therefore costs two extra round trips.

## Constraint 6 — workflow states are per Database entities

The `workflow/state` Field's type is a Database of its own
(`workflow/state_<Space>/<Database>`). Setting a state means querying that
Database for the state whose `enum/name` matches, then writing
`{"fibery/id": <state id>}`.

## Constraint 7 — `fibery/type: "document"` is correct — VERIFIED

Previously inferred, now confirmed. The workspace contains Views of
`fibery/type: "document"` (`SDLC-RAW-0001`, `Getting Started`), and
`create-views` accepted that value.

The View types actually present are `form`, `list`, `dashboard`, `document`,
`vizydrop/chart`, `canvas`, `board`. There is no `folder` View type, because
Folders are not Views.

A Document's content secret is at `fibery/meta.documentSecret` on the View —
distinct from the `Collaboration~Documents/secret` used for an entity's rich
text Field.

## Constraint 8 — the Project Documents field is `documents/documents` — VERIFIED

The Fibery Field is named **Documents**, not "Documents Root". An earlier
revision of this document wrongly concluded the Field was missing, after a
single failed relation query. `Fibery-Schema-v0.1.md` and
`Project-Init-Spec-v0.3.md` have been corrected to say `Documents`.

On `SDLC/Project` it appears as:

```text
documents/documents   fibery/view   { fibery/collection?: true }
```

It is provided by the Fibery mixin `documents/documents-mixin`
(`019ea722-efc4-7033-a7cf-041efa3d475a`), the same mechanism behind
`Requirement.Documents`.

### It is not readable through the entity API

`fibery.entity/query` refuses to select it:

```text
entity.error/schema-type-field-relation-not-found
"There is no relation for \"SDLC/Project\" database \"documents/documents\" field."
```

The membership lives on the **View**, not on the entity. A Document is
associated with an entity by being contained by it:

```text
fibery/container-type          "object"
fibery/container-entity-type   { fibery/id: <Database type id> }
fibery/container-entity-id     <the entity's fibery/public-id>
```

### `container-entity-id` takes the public-id, not the UUID — VERIFIED

This is the least guessable part of the whole interface. Passing the entity's
`fibery/id` (a UUID) fails with `parent-entity-not-found`; passing its
`fibery/public-id` (e.g. `"1"`) succeeds. Verified by creating a Document
against `SDLC/Project` type `2d4bba0c-5eb7-4dc2-b406-0f10404ef31f`, entity
public-id `"1"`, reading it back, then deleting it.

A Document may carry `fibery/Folder` and entity containment at the same time;
both were accepted on one `create-views` call.

### `project init` does not use it

By decision, the Project document root is the Space-level Folder tree, recorded
in the Text Field `SDLC/Documents Root Folder ID`. No placeholder root Document
is created, and `Project.Documents` is left for genuine Project documents.
`Requirement.Documents` remains the mechanism for a Requirement's Root Document,
which is placed in the right Folder through `fibery/Folder`.

### Reading it back

`query-views`'s `container` filter did not return entity-attached Documents in
testing. The reliable read is `query-views` by `ids`, or listing views and
matching `fibery/container-entity-id` client side — consistent with
Constraint 2.

Only the Project Database was audited. The other Databases in
`Fibery-Schema-v0.1.md` may have comparable drift.

## Constraint 9 — the Fibery MCP server cannot create Documents or Folders

Checked against the official `Fibery-inc/fibery-mcp-server`, v0.1.8, commit
`3d21ca04e771bad91aa2d9799d29ed3583362326` (2026-05-13).

It registers exactly seven tools: `current_date`, `list_databases`,
`describe_database`, `query_database`, `create_entity`, `create_entities_batch`,
`update_entity`. Its client touches only `/api/schema`, `/api/commands`,
`/api/documents/<secret>` and `/api/documents/commands`, and the source contains
no reference to `views/json-rpc`, Folders, or any hierarchy concept.

"Document" in that server's vocabulary means the rich text Field type
`Collaboration~Documents/Document` on an entity, not a sidebar Document View.

MCP is therefore strictly weaker than the HTTP API `project init` already uses.

## Constraint 10 — a Document's content secret must be supplied by the client

`create-views` does **not** allocate a `documentSecret`. A Document created with
`fibery/meta: {}` reads back with `fibery/meta: {}` and has no addressable body,
so `PUT /api/documents/<secret>` has nothing to write to.

The client generates the secret and passes it at creation:

```json
"fibery/meta": {"documentSecret": "<uuid>"}
```

It then reads back on the View and works for both `PUT` and `GET`. Verified
live: the first ingest attempt failed with `CONTENT_WRITE_FAILED` precisely
because the created Document exposed no secret.

Note the two different secrets: an entity rich-text Field's secret comes from
`Collaboration~Documents/secret` on the entity (constraint 5), while a sidebar
Document's comes from `fibery/meta.documentSecret` on the View.

## Constraint 11 — Fibery re-serializes stored Markdown

Content read back from `/api/documents/<secret>?format=md` is not byte-identical
to what was written. Verified live, five behaviours:

- `-` list bullets come back as `*`;
- the trailing newline is dropped;
- a blank line is **inserted** between a paragraph and a list that directly
  follows it, so `Intro:\n- item` is stored as `Intro:\n\n* item`;
- a blank line is likewise inserted after a heading followed directly by
  anything, so `## S\nBody` is stored as `## S\n\nBody`;
- a **soft line break inside a paragraph is returned as a literal `<br>`**, so a
  paragraph wrapped across source lines comes back as one line:
  `and\nnothing ends them` is stored as `and<br>nothing ends them`.

A fenced code block is the exception: it is returned verbatim. That is what lets
the JSON payload of a Process Result or a Review Result survive a round trip
unchanged.

Each behaviour was found only by writing real content to the live workspace, and
each broke post-write validation before it was known. The `<br>` case was found
during the Standard Review live acceptance: an ordinary wrapped paragraph in an
ingested RAW artifact failed `requirement add` with VALIDATION_FAILED and could
never have succeeded on retry. Wrapped prose is the normal shape of a written
requirement, so this was not an edge case.

Post-write validation therefore compares content modulo that re-serialization
(`sdlc.raw_source.content_equivalent`) rather than byte for byte. Anything
Fibery does not merely re-serialize still fails the check. Document fingerprints
derive from the same `canonical_markdown`, so a fingerprint and an equivalence
check can never disagree.

## Constraint 12 — Requirement Name is a read-only formula

`SDLC/Name` on Requirement carries `formula/formula?: true` and
`fibery/readonly?: true`. Its expression is:

```text
concat(concat(Requirement ID, " - "), Title)
```

It cannot be written, and it uses a plain hyphen. The Root Document name uses
the em dash the spec shows, so the two differ by design:

```text
entity name    ZZIN2-RAW-0001 - Repository Handoff and Development Workflow
document name  ZZIN2-RAW-0001 — Repository Handoff and Development Workflow
```

## Constraint 13 — Requirement Type option names are `Raw` and `Standard`

`Fibery-Schema-v0.1.md` documents `RAW | STANDARD`. The workspace enum
`SDLC/Type_Agentic SDLC/Requirement` actually holds `Raw` and `Standard`, and
options resolve by exact `enum/name`.

Category previously held a misspelled `NON-FONCTIONAL` option. That has been
corrected in the workspace; the options are now `FUNCTIONAL`, `NON_FUNCTIONAL`
and `CONSTRAINT`, matching `Fibery-Schema-v0.1.md`. No Requirement had used the
misspelled option, so no data was affected and no adapter mapping is needed.

Requirement workflow states are `Draft`, `Process`, `Review`, `Ready`, `Apply`,
`Applied`, and `Draft` is already the Fibery default.

## Constraint 14 — no field-level uniqueness on this plan; public-id is the safe allocator

`Requirement ID` carries no uniqueness constraint, and Fibery does not enforce
one. Verified by creating two Requirements with the same `SDLC/Requirement ID`:
both returned `success: true` and both persisted. (Both deleted.)

Fibery does support unique text fields through
`fibery/meta: {"fibery/case-insensitive-text-unique?": true}`, but this
workspace cannot use it:

```text
commands.error/account-capability-was-revoked
Workspace capability "uniqueFieldValues" is missing. Upgrade your license plan.
```

Consequence: a "highest id in use plus one" allocator is unsafe here, and
post-write duplicate detection does not rescue it — a collision created after
validation runs is never observed, so one writer can report success while a
duplicate exists.

`fibery/public-id` is the workable atomic counter. It is `fibery/text`, readonly,
allocated by Fibery on entity creation, and holds a digit string. RAW Requirement
IDs derive from it, which makes numbering sparse per Project and safe under
concurrency.

## Constraint 15 — `entity/create` silently ignores collection fields

A collection Field passed inside `fibery.entity/create` is accepted and
discarded. The command returns `success: true` and the collection reads back
empty.

Verified live on `SDLC/Derived From`: an entity created with
`"SDLC/Derived From": [{"fibery/id": <raw>}]` returned success, and the field
read back as `{"fibery/id": []}`. The same entity linked afterwards through
`fibery.entity/add-collection-items` read back as
`{"fibery/id": ["<raw>"]}`, which calibrates the read and proves the create
wrote nothing.

There is no error to detect. Code that sets a relation during creation and
trusts the success flag will silently produce unlinked entities.

Collections are written with:

```text
fibery.entity/add-collection-items
  args: { type, field, entity: { "<entity uuid>": ["<item uuid>", ...] } }
```

(the command is plural; `add-collection-item` does not exist). Setting one side
populates the inverse automatically, since `Produces` and `Derived From` share
relation id `8002c1d0-9e2c-11f1-91a5-45a5f32849ca`.

## Constraint 16 — `/api/commands` batches are not transactional

The endpoint takes an array of commands and executes them in order, but a
failure part-way through does **not** roll back earlier commands.

Verified live: a batch of `[create valid entity, create into a nonexistent
database]` returned `[true, false]`, and the first entity was still present
afterwards.

Consequence: `[create entity, add-collection-items]` in one request is *not* an
atomic way to create an entity with its relation. There is a real window in
which the entity exists without its provenance.

## Constraint 17 — the client may supply `fibery/id` on create

`fibery.entity/create` accepts a caller-generated `fibery/id` and honours it,
the same way `create-views` and `create-folders` do. Verified live.

This makes entity identity client-determined, which is the usual way to make a
create idempotent without a server-side uniqueness constraint.

## Constraint 18 — collection sub-selects cannot include secured Fields

`q/select` of the form `{"SDLC/Produces": ["fibery/id", "SDLC/Title"]}` fails
with `entity.error/query-with-permissions-field-expression-invalid`, because
`SDLC/Title` is `fibery/secured?`. Selecting `["fibery/id"]` alone works and
returns `{"fibery/id": [...]}` — an object wrapping the list, not a list of
objects.

## Constraint 19 — Documents can nest under Documents

`create-views` accepts `fibery/parent-page-id` pointing at another Document, and
reads it back. Verified live. A nested child carries no `fibery/Folder`: its
placement comes from its parent.

This is what makes a per-RAW process artifact possible without a new Database.
It appears in no published documentation, like the Folder API.

## Constraint 20 — a duplicate `fibery/id` create is rejected

Creating an entity at an id that already exists fails with
`entity.error/schema-field-unique-failed`, and the existing entity is left
untouched. Verified live.

Combined with constraint 17 (the client may choose the id) this makes
`create` a safe existence check: a caller can derive an entity id
deterministically and retry a create without risking a duplicate.

## Constraint 21 — deleting a single-select Field is a four-step cascade

Removing a single-select Field is not one command. Verified live while removing
the unused `Requirement.Operation` Field:

1. delete the option entities from the option database, or
   `commands.error/schema-delete-type-having-entities-failed`;
2. delete the Field itself, **and** the matching relation end on the option
   database, in one batch, or `entity.error/schema-relation-invalid` naming the
   dangling end;
3. delete the option database in the same batch, or
   `commands.error/schema-type-components-orphans`;
4. `schema.field/delete` takes `holder-type` and `name`;
   `schema.type/delete` takes `name`. Neither accepts the `fibery/`-prefixed
   forms that `schema.field/create` uses.

A single-select Field is modelled as a relation to a per-Field option Database
(`<Space>/<Field>_<Space>/<Database>`), which is why the cascade exists.

## Constraint 22 — Depends On / Affects are read like any other collection

`SDLC/Depends On` and `SDLC/Affects` are ordinary N:N self relations on the
Requirement Database. Reading them follows constraint 18: select only
`fibery/id` inside the sub-select, then resolve each id to a record.

Each pair shares one relation, so reading the forward side alone is complete —
`Blocks` and `Impacted By` report the same edges from the other end. Verified
live by adding one `Depends On` edge, reading it back as a Requirement ID, and
confirming the inverse side reports no separate forward edge.

## Constraint 23 — `delete-views` removes a Document

The Views JSON-RPC method is `delete-views`, taking `{"ids": [...]}`.
`delete-view`, `remove-view` and `remove-views` all return
`method ... was not found`.
