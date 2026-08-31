# Fibery API Constraints v0.1

Constraints observed in the current public Fibery API while implementing
`project init`. Recorded so later capabilities do not rediscover them.

## Endpoints used

| Purpose | Endpoint |
| --- | --- |
| Schema and entities | `POST /api/commands` (batched array of commands) |
| Documents and folders in the sidebar | `POST /api/views/json-rpc` |
| Rich text content | `PUT /api/documents/<secret>?format=md` |

Authentication is `Authorization: Token <token>`. Rate limits are 3 requests per
second per token and 7 per second per workspace.

## Constraint 1 — sidebar Documents cannot be nested through the API

Fibery Documents in a Space are Views of `fibery/type: "document"`.

`create-views` accepts `fibery/container-app` (the Space) and nothing else that
expresses a parent. Fibery's own documented view types contain no `folder` type,
and neither the Views API nor the Fibery MCP `create_view` tool exposes a parent
document, folder or ordering parameter.

Verified against the published Views API reference: `create-views` documents
exactly `fibery/id`, `fibery/name`, `fibery/type`, `fibery/meta` and
`fibery/container-app`, and none of them expresses a parent.

Consequence: the hierarchy required by `Project-Init-Spec-v0.3` section 9 cannot
be created as nested folders. `project init` creates one document View per node
and encodes the hierarchy in the View name as a path:

```text
SDLC
SDLC/Requirements
SDLC/Requirements/Raw
SDLC/Requirements/Draft
SDLC/Requirements/Approved
```

Paths are the addressing scheme for later capabilities: `project requirement add`
locates `<Project Name>/Requirements/Raw` by name. If Fibery later publishes a
nesting API, only `sdlc.fibery_http.create_document` and `find_document` change.

Because the path separator is load-bearing, `project init` rejects a Project Name
containing `/` as `INVALID_INPUT`. Without that guard a Project named
`SDLC/Requirements` addresses nodes inside the `SDLC` Project's structure and
reports success while aliasing another Project's documents.

### Not yet verified against a live workspace

The published Views API reference does not enumerate legal `fibery/type` values;
only `board` appears in its examples. The value `document` used by
`sdlc.fibery_http.DOCUMENT_VIEW_TYPE` is therefore **inferred, not confirmed**,
and must be checked against a real workspace before the first live run. It is
the single most likely cause of a first-run failure.

The same applies to the nesting question itself. `fibery/meta` is documented as
an opaque object, and it is the one place a parent reference could plausibly
live. Reading an existing, manually nested Document and inspecting its
`fibery/meta` is the decisive experiment. `scripts/fibery_document_probe.py`
performs exactly that, read-only, and needs only the `FIBERY_*` variables.

## Constraint 1a — the Fibery MCP server cannot create Documents at all

Checked against the official `Fibery-inc/fibery-mcp-server`, v0.1.8, commit
`3d21ca04e771bad91aa2d9799d29ed3583362326` (2026-05-13).

It registers exactly seven tools:

```text
current_date
list_databases
describe_database
query_database
create_entity
create_entities_batch
update_entity
```

Its client touches only `/api/schema`, `/api/commands`, `/api/documents/<secret>`
and `/api/documents/commands`. The source contains no reference to
`views/json-rpc`, `create-views`, `query-views`, `container-app`, `folder`,
`parent` or any hierarchy concept.

"Document" in that server's vocabulary means the rich text Field type
`Collaboration~Documents/Document` on an entity — not a sidebar Document View.

Consequence: MCP is not an escape hatch for the nesting problem. It is strictly
weaker than the HTTP Views API `project init` already uses, so routing Document
creation through MCP would lose capability rather than gain it.

Incidental finding: that server writes rich text through
`POST /api/documents/commands` with `create-or-update-documents` /
`create-or-append-documents`, where `sdlc` uses `PUT /api/documents/<secret>`.
Both are first-party; no reason to switch.

## Constraint 2 — Views cannot be filtered by name

`query-views` filters on `ids`, `publicIds`, `isPrivate` and `container` only
(verified against the published reference). Locating a document by path requires
listing views and matching client side.

## Constraint 3 — a Space name and a Space id are both needed

Database names are qualified by Space *name* (`SDLC/Project`), while
`create-views` needs the Space *id* (a UUID). Fibery publishes no command that
maps one to the other, so both are configured (`FIBERY_SPACE`,
`FIBERY_SPACE_ID`).

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
