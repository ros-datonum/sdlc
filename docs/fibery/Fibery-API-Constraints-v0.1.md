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

Consequence: `project init` must create real Folders. Slash-path emulation is
not a permitted substitution, and the Project Name guard added to protect it
(`name_is_addressable`) exists only because of it.

## Constraint 2 — Views and Folders cannot be filtered by name

`query-views` filters on `ids`, `publicIds`, `isPrivate` and `container` only.
`query-folders` accepts no filter at all. Locating a Document or Folder by name
requires listing and matching client side.

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

## Constraint 8 — `Project.Documents Root` does not exist — VERIFIED

`Fibery-Schema-v0.1.md` specifies `Documents Root - URL/reference` on Project.
**No such Field exists in the workspace.** The Project Database's Fields are:

```text
SDLC/Name            fibery/text
SDLC/Code            fibery/text
SDLC/Description     Collaboration~Documents/Document
SDLC/Phases          SDLC/Project Phase
SDLC/Requirements    SDLC/Requirement
SDLC/Milestones      SDLC/Milestone
SDLC/Epics           SDLC/Epic
SDLC/User Stories    SDLC/User Story
SDLC/Tasks           SDLC/Task
workflow/state       workflow/state_SDLC/Project
documents/documents  fibery/view          (collection, Fibery-internal)
Collaboration~Documents/References
fibery/id, fibery/public-id, fibery/rank, fibery/created-by,
fibery/creation-date, fibery/modification-date
```

`documents/documents` is a Fibery-internal collection of Views. It is **not**
usable as a substitute: `fibery.entity/query` rejects selecting it with
`entity.error/schema-type-field-relation-not-found` - "There is no relation for
\"SDLC/Project\" database \"documents/documents\" field."

Consequence: `project init` cannot store the root reference until this is
resolved. It currently fails at schema resolution before any mutation, which is
the correct loud failure, but it means the command cannot run against this
workspace as it stands.

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
