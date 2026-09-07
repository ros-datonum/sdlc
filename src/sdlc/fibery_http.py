"""FiberyWorkspace implemented against the live Fibery HTTP API.

Field names are resolved from the workspace schema rather than assumed, because
Fibery prefixes Fields with a Space name and mixes in Fields owned by other
Spaces (``workflow/state``, ``Collaboration~Documents/secret``).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sdlc.comparison_context import COMPARISON_RECORD_LIMIT
from sdlc.fibery_client import FiberyClient
from sdlc.fibery_workspace import (
    DocumentNode,
    FiberyError,
    FolderNode,
    ProjectRecord,
    RequirementRecord,
    RequirementRelations,
)

PROJECT_DATABASE_NAME = "Project"
REQUIREMENT_DATABASE_NAME = "Requirement"

FIELD_LABEL_REQUIREMENT_ID = "requirement id"
FIELD_LABEL_TITLE = "title"
FIELD_LABEL_TYPE = "type"
FIELD_LABEL_REVISION = "revision"
FIELD_LABEL_PROJECT = "project"
FIELD_LABEL_SOURCE_FINGERPRINT = "source fingerprint"
FIELD_LABEL_CATEGORY = "category"
FIELD_LABEL_DERIVED_FROM = "derived from"
FIELD_LABEL_DEPENDS_ON = "depends on"
FIELD_LABEL_AFFECTS = "affects"
STANDARD_TYPE_NAME = "Standard"
VIEW_PARENT_PAGE_KEY = "fibery/parent-page-id"

PUBLIC_ID_FIELD = "fibery/public-id"
DOCUMENT_VIEW_TYPE = "document"
VIEW_TYPE_KEY = "fibery/type"
VIEW_META_KEY = "fibery/meta"
VIEW_FOLDER_KEY = "fibery/Folder"
VIEW_CONTAINER_TYPE_KEY = "fibery/container-type"
VIEW_CONTAINER_ENTITY_TYPE_KEY = "fibery/container-entity-type"
VIEW_CONTAINER_ENTITY_ID_KEY = "fibery/container-entity-id"
CONTAINER_TYPE_OBJECT = "object"
DOCUMENT_SECRET_META_KEY = "documentSecret"
QUERY_VIEWS_METHOD = "query-views"
CREATE_VIEWS_METHOD = "create-views"
CREATE_VIEWS_PARAM = "views"
# Constraint 24: the same shape as update-folders, and it moves the same
# Document entity between Folders in place.
UPDATE_VIEWS_METHOD = "update-views"
UPDATE_VIEWS_PARAM = "updates"
ADD_COLLECTION_ITEMS_COMMAND = "fibery.entity/add-collection-items"
# Two rows distinguish "exactly one" from "more than one" without listing.
AMBIGUITY_QUERY_LIMIT = 2
REQUIREMENT_QUERY_LIMIT = 1000
# Two more than the comparison corpus admits: the rows may include the target
# itself, and the extra row past that makes overflow visible instead of
# letting a cut list pass as the whole Project.
COMPARISON_QUERY_LIMIT = COMPARISON_RECORD_LIMIT + 2

FIELD_LABEL_NAME = "name"
FIELD_LABEL_CODE = "code"
FIELD_LABEL_DESCRIPTION = "description"
FIELD_LABEL_DOCUMENTS_ROOT_FOLDER = "documents root folder id"

ID_FIELD = "fibery/id"
FIELD_NAME_KEY = "fibery/name"
FIELD_TYPE_KEY = "fibery/type"
TYPES_KEY = "fibery/types"
FIELDS_KEY = "fibery/fields"

WORKFLOW_STATE_FIELD = "workflow/state"
ENUM_NAME_FIELD = "enum/name"
DOCUMENT_SECRET_FIELD = "Collaboration~Documents/secret"

VIEW_NAME_KEY = "fibery/name"
VIEW_CONTAINER_APP_KEY = "fibery/container-app"

# Folders carry the hierarchy. See Fibery-API-Constraints-v0.1 constraint 1:
# these json-rpc methods are undocumented, and create-folders takes "values"
# where create-views takes "views".
FOLDER_PARENT_KEY = "fibery/Parent Folder"
QUERY_FOLDERS_METHOD = "query-folders"
FOLDER_FILTER_KEY = "filter"
FOLDER_IDS_FILTER_KEY = "ids"
CREATE_FOLDERS_METHOD = "create-folders"
CREATE_FOLDERS_PARAM = "values"

# Callers only need to distinguish "none", "exactly one" and "more than one".
PROJECT_CODE_COUNT_LIMIT = 2
EXISTENCE_QUERY_LIMIT = 2
NAME_AMBIGUITY_LIMIT = 5
SINGLE_ROW_LIMIT = 1


@dataclass(frozen=True)
class _ProjectSchema:
    """Resolved API names for the Project Database this command writes to."""

    name_field: str
    code_field: str
    documents_root_folder_field: str
    description_field: str | None
    state_type: str


class FiberyHttpWorkspace:
    """Reads and writes the Project bootstrap state in a Fibery workspace."""

    def __init__(self, client: FiberyClient, space: str, space_id: str) -> None:
        self._client = client
        self._space = space
        self._space_id = space_id
        self._schema: _ProjectSchema | None = None

    @property
    def project_database(self) -> str:
        return f"{self._space}/{PROJECT_DATABASE_NAME}"

    def find_project_by_name(self, name: str) -> ProjectRecord | None:
        schema = self._project_schema()
        rows = self._query_projects(
            schema,
            ["=", [schema.name_field], "$name"],
            {"$name": name},
            EXISTENCE_QUERY_LIMIT,
        )
        return self._to_record(schema, rows[0]) if rows else None

    def find_project_by_code(self, code: str) -> ProjectRecord | None:
        """Return the Project with this exact Code, or None."""
        schema = self._project_schema()
        rows = self._query_projects(
            schema,
            ["=", [schema.code_field], "$code"],
            {"$code": code},
            EXISTENCE_QUERY_LIMIT,
        )
        return self._to_record(schema, rows[0]) if rows else None

    def find_projects_by_name(self, name: str) -> list[ProjectRecord]:
        """Every Project with this exact Name, so ambiguity can be detected."""
        schema = self._project_schema()
        rows = self._query_projects(
            schema,
            ["=", [schema.name_field], "$name"],
            {"$name": name},
            NAME_AMBIGUITY_LIMIT,
        )
        return [self._to_record(schema, row) for row in rows]

    def count_projects_with_code(self, code: str) -> int:
        schema = self._project_schema()
        rows = self._query_projects(
            schema,
            ["=", [schema.code_field], "$code"],
            {"$code": code},
            PROJECT_CODE_COUNT_LIMIT,
        )
        return len(rows)

    def read_project(self, project_id: str) -> ProjectRecord | None:
        schema = self._project_schema()
        rows = self._query_projects(
            schema, ["=", [ID_FIELD], "$id"], {"$id": project_id}, SINGLE_ROW_LIMIT
        )
        return self._to_record(schema, rows[0]) if rows else None

    def create_project(self, name: str, code: str) -> str:
        schema = self._project_schema()
        created = self._client.command(
            "fibery.entity/create",
            {
                "type": self.project_database,
                "entity": {schema.name_field: name, schema.code_field: code},
            },
        )
        project_id = (created or {}).get(ID_FIELD)
        if not project_id:
            raise FiberyError("Fibery did not return an id for the created Project.")
        return project_id

    def set_project_state(self, project_id: str, state: str) -> None:
        schema = self._project_schema()
        rows = self._client.command(
            "fibery.entity/query",
            {
                "query": {
                    "q/from": schema.state_type,
                    "q/select": [ID_FIELD, ENUM_NAME_FIELD],
                    "q/where": ["=", [ENUM_NAME_FIELD], "$state"],
                    "q/limit": SINGLE_ROW_LIMIT,
                },
                "params": {"$state": state},
            },
        )
        if not rows:
            raise FiberyError(
                f"The {self.project_database} workflow has no state named {state!r}."
            )
        self._update_project(
            project_id, {WORKFLOW_STATE_FIELD: {ID_FIELD: rows[0][ID_FIELD]}}
        )

    def set_project_description(self, project_id: str, description: str) -> None:
        schema = self._project_schema()
        if schema.description_field is None:
            raise FiberyError(
                f"{self.project_database} has no Description Field to write to."
            )
        rows = self._client.command(
            "fibery.entity/query",
            {
                "query": {
                    "q/from": self.project_database,
                    "q/select": [
                        ID_FIELD,
                        {schema.description_field: [DOCUMENT_SECRET_FIELD]},
                    ],
                    "q/where": ["=", [ID_FIELD], "$id"],
                    "q/limit": SINGLE_ROW_LIMIT,
                },
                "params": {"$id": project_id},
            },
        )
        secret = ((rows or [{}])[0].get(schema.description_field) or {}).get(
            DOCUMENT_SECRET_FIELD
        )
        if not secret:
            raise FiberyError("Could not read the Project Description document secret.")
        self._client.put_document(secret, description)

    def set_documents_root_folder(self, project_id: str, folder_id: str) -> None:
        schema = self._project_schema()
        self._update_project(
            project_id, {schema.documents_root_folder_field: folder_id}
        )

    def create_folder(self, name: str, parent_id: str | None) -> FolderNode:
        folder_id = str(uuid.uuid4())
        values: dict[str, Any] = {
            ID_FIELD: folder_id,
            VIEW_NAME_KEY: name,
            VIEW_CONTAINER_APP_KEY: {ID_FIELD: self._space_id},
        }
        if parent_id is not None:
            values[FOLDER_PARENT_KEY] = {ID_FIELD: parent_id}
        self._client.views_rpc(CREATE_FOLDERS_METHOD, {CREATE_FOLDERS_PARAM: [values]})
        return FolderNode(id=folder_id, name=name, parent_id=parent_id)

    def resolve_folder(self, folder_id: str) -> FolderNode | None:
        """Read one Folder back by id.

        query-folders accepts the same {"filter": {"ids": [...]}} shape as
        query-views, so this asks Fibery for exactly one Folder rather than
        matching a name that siblings may share.
        """
        folders = self._client.views_rpc(
            QUERY_FOLDERS_METHOD,
            {FOLDER_FILTER_KEY: {FOLDER_IDS_FILTER_KEY: [folder_id]}},
        )
        for folder in folders or []:
            if folder.get(ID_FIELD) == folder_id:
                return _to_folder(folder)
        return None

    def _update_project(self, project_id: str, values: dict[str, Any]) -> None:
        self._client.command(
            "fibery.entity/update",
            {
                "type": self.project_database,
                "entity": {ID_FIELD: project_id, **values},
            },
        )

    def _query_projects(
        self,
        schema: _ProjectSchema,
        where: list[Any],
        params: dict[str, Any],
        limit: int,
    ) -> list[dict[str, Any]]:
        return (
            self._client.command(
                "fibery.entity/query",
                {
                    "query": {
                        "q/from": self.project_database,
                        "q/select": [
                            ID_FIELD,
                            schema.name_field,
                            schema.code_field,
                            schema.documents_root_folder_field,
                            {WORKFLOW_STATE_FIELD: [ENUM_NAME_FIELD]},
                        ],
                        "q/where": where,
                        "q/limit": limit,
                    },
                    "params": params,
                },
            )
            or []
        )

    def _to_record(self, schema: _ProjectSchema, row: dict[str, Any]) -> ProjectRecord:
        return ProjectRecord(
            id=row[ID_FIELD],
            name=row.get(schema.name_field) or "",
            code=row.get(schema.code_field),
            state=(row.get(WORKFLOW_STATE_FIELD) or {}).get(ENUM_NAME_FIELD),
            documents_root_folder_id=row.get(schema.documents_root_folder_field),
        )

    def _project_schema(self) -> _ProjectSchema:
        if self._schema is None:
            self._schema = self._resolve_project_schema()
        return self._schema

    def _resolve_project_schema(self) -> _ProjectSchema:
        fields = _project_type_fields(
            self._client.command("fibery.schema/query"), self.project_database
        )
        by_label = _index_fields_by_label(fields, self._space)
        by_name = {field.get(FIELD_NAME_KEY): field for field in fields}

        state_field = by_name.get(WORKFLOW_STATE_FIELD)
        if state_field is None:
            raise FiberyError(
                f"{self.project_database} has no {WORKFLOW_STATE_FIELD} Field."
            )

        return _ProjectSchema(
            name_field=_require_field(
                by_label, FIELD_LABEL_NAME, self.project_database
            ),
            code_field=_require_field(
                by_label, FIELD_LABEL_CODE, self.project_database
            ),
            documents_root_folder_field=_require_field(
                by_label, FIELD_LABEL_DOCUMENTS_ROOT_FOLDER, self.project_database
            ),
            description_field=(
                by_label[FIELD_LABEL_DESCRIPTION].get(FIELD_NAME_KEY)
                if FIELD_LABEL_DESCRIPTION in by_label
                else None
            ),
            state_type=state_field[FIELD_TYPE_KEY],
        )


def _project_type_fields(schema: Any, database: str) -> list[dict[str, Any]]:
    for entry in (schema or {}).get(TYPES_KEY, []):
        if entry.get(FIELD_NAME_KEY) == database:
            return entry.get(FIELDS_KEY, [])
    raise FiberyError(f"Database {database!r} was not found in the workspace schema.")


def _index_fields_by_label(
    fields: list[dict[str, Any]], space: str
) -> dict[str, dict[str, Any]]:
    """Index Fields by their label, preferring ones owned by the Project's Space."""
    indexed: dict[str, dict[str, Any]] = {}
    for field in fields:
        name = field.get(FIELD_NAME_KEY, "")
        prefix, _, label = name.partition("/")
        key = label.strip().lower()
        if not key:
            continue
        if key not in indexed or prefix == space:
            indexed[key] = field
    return indexed


def _require_field(
    by_label: dict[str, dict[str, Any]], label: str, database: str
) -> str:
    field = by_label.get(label)
    if field is None:
        raise FiberyError(f"{database} has no {label!r} Field.")
    return field[FIELD_NAME_KEY]


def _to_folder(folder: dict[str, Any]) -> FolderNode:
    return FolderNode(
        id=folder[ID_FIELD],
        name=folder.get(VIEW_NAME_KEY) or "",
        parent_id=(folder.get(FOLDER_PARENT_KEY) or {}).get(ID_FIELD),
    )


@dataclass(frozen=True)
class _RequirementSchema:
    """Resolved API names for the Requirement Database."""

    requirement_id_field: str
    title_field: str
    type_field: str
    type_database: str
    revision_field: str
    project_field: str
    fingerprint_field: str
    state_database: str
    type_id: str
    # Only the RAW processor needs these; requirement add must keep working
    # against a Database that does not expose them.
    category_field: str | None = None
    category_database: str | None = None
    derived_from_field: str | None = None
    depends_on_field: str | None = None
    affects_field: str | None = None


class FiberyRequirementWorkspace:
    """Reads and writes RAW Requirement state in a Fibery workspace.

    Shares the transport with FiberyHttpWorkspace but keeps its own schema
    resolution, so the frozen `project init` adapter is untouched.
    """

    def __init__(self, client: FiberyClient, space: str, space_id: str) -> None:
        self._client = client
        self._space = space
        self._space_id = space_id
        self._projects = FiberyHttpWorkspace(client, space, space_id)
        self._schema: _RequirementSchema | None = None

    @property
    def requirement_database(self) -> str:
        return f"{self._space}/{REQUIREMENT_DATABASE_NAME}"

    # -- projects and folders ------------------------------------------

    def find_project_by_code(self, code: str) -> ProjectRecord | None:
        return self._projects.find_project_by_code(code)

    def find_projects_by_name(self, name: str) -> list[ProjectRecord]:
        return self._projects.find_projects_by_name(name)

    def resolve_folder(self, folder_id: str) -> FolderNode | None:
        return self._projects.resolve_folder(folder_id)

    def child_folders(self, parent_id: str) -> list[FolderNode]:
        folders = self._client.views_rpc(QUERY_FOLDERS_METHOD, {}) or []
        return [
            _to_folder(folder)
            for folder in folders
            if (folder.get(FOLDER_PARENT_KEY) or {}).get(ID_FIELD) == parent_id
        ]

    # -- requirements ---------------------------------------------------

    def find_requirement_by_fingerprint(
        self, project_id: str, fingerprint: str
    ) -> RequirementRecord | None:
        schema = self._requirement_schema()
        rows = self._query_requirements(
            schema,
            [
                "q/and",
                ["=", [schema.project_field, ID_FIELD], "$project"],
                ["=", [schema.fingerprint_field], "$fingerprint"],
            ],
            {"$project": project_id, "$fingerprint": fingerprint},
            2,
        )
        return self._to_requirement(schema, rows[0]) if rows else None

    def create_requirement(
        self, project_id: str, title: str, revision: int, fingerprint: str
    ) -> RequirementRecord:
        schema = self._requirement_schema()
        created = self._client.command(
            "fibery.entity/create",
            {
                "type": self.requirement_database,
                "entity": {
                    schema.title_field: title,
                    schema.revision_field: revision,
                    schema.fingerprint_field: fingerprint,
                    schema.project_field: {ID_FIELD: project_id},
                },
            },
        )
        entity_id = (created or {}).get(ID_FIELD)
        if not entity_id:
            raise FiberyError(
                "Fibery did not return an id for the created Requirement."
            )
        record = self.read_requirement(entity_id)
        if record is None:
            raise FiberyError("The created Requirement could not be read back.")
        return record

    def set_requirement_id(self, entity_id: str, requirement_id: str) -> None:
        schema = self._requirement_schema()
        self._update_requirement(
            entity_id, {schema.requirement_id_field: requirement_id}
        )

    def set_requirement_type(self, requirement_id: str, type_name: str) -> None:
        schema = self._requirement_schema()
        option = self._enum_option(schema.type_database, type_name)
        self._update_requirement(
            requirement_id, {schema.type_field: {ID_FIELD: option}}
        )

    def set_requirement_state(self, requirement_id: str, state: str) -> None:
        schema = self._requirement_schema()
        option = self._enum_option(schema.state_database, state)
        self._update_requirement(
            requirement_id, {WORKFLOW_STATE_FIELD: {ID_FIELD: option}}
        )

    def read_requirement(self, requirement_id: str) -> RequirementRecord | None:
        schema = self._requirement_schema()
        rows = self._query_requirements(
            schema, ["=", [ID_FIELD], "$id"], {"$id": requirement_id}, 1
        )
        return self._to_requirement(schema, rows[0]) if rows else None

    # -- documents ------------------------------------------------------

    def create_requirement_document(
        self, name: str, folder_id: str, requirement_public_id: str
    ) -> DocumentNode:
        document_id = str(uuid.uuid4())
        # Fibery does not allocate a document secret: a Document created
        # without one in fibery/meta comes back with meta {} and has no
        # addressable content. The client supplies it.
        secret = str(uuid.uuid4())
        self._client.views_rpc(
            CREATE_VIEWS_METHOD,
            {
                CREATE_VIEWS_PARAM: [
                    {
                        ID_FIELD: document_id,
                        VIEW_NAME_KEY: name,
                        VIEW_TYPE_KEY: DOCUMENT_VIEW_TYPE,
                        VIEW_META_KEY: {DOCUMENT_SECRET_META_KEY: secret},
                        VIEW_CONTAINER_APP_KEY: {ID_FIELD: self._space_id},
                        VIEW_FOLDER_KEY: {ID_FIELD: folder_id},
                        VIEW_CONTAINER_TYPE_KEY: CONTAINER_TYPE_OBJECT,
                        VIEW_CONTAINER_ENTITY_TYPE_KEY: {
                            ID_FIELD: self._requirement_schema().type_id
                        },
                        # Fibery wants the entity's public id here. Passing the
                        # uuid fails with parent-entity-not-found.
                        VIEW_CONTAINER_ENTITY_ID_KEY: requirement_public_id,
                    }
                ]
            },
        )
        resolved = self.resolve_document(document_id)
        if resolved is None:
            raise FiberyError(f"The created Document {name!r} could not be read back.")
        return resolved

    def resolve_document(self, document_id: str) -> DocumentNode | None:
        views = self._client.views_rpc(
            QUERY_VIEWS_METHOD, {"filter": {"ids": [document_id]}}
        )
        for view in views or []:
            if view.get(ID_FIELD) == document_id:
                return _to_document(view)
        return None

    def documents_attached_to_requirement(self, public_id: str) -> list[DocumentNode]:
        """Documents whose container is this Requirement.

        query-views cannot filter on the container entity, so the document
        views are listed and matched client side (constraint 2).
        """
        views = self._client.views_rpc(QUERY_VIEWS_METHOD, {}) or []
        type_id = self._requirement_schema().type_id
        return [
            _to_document(view)
            for view in views
            if view.get(VIEW_TYPE_KEY) == DOCUMENT_VIEW_TYPE
            and view.get(VIEW_CONTAINER_ENTITY_ID_KEY) == public_id
            and (view.get(VIEW_CONTAINER_ENTITY_TYPE_KEY) or {}).get(ID_FIELD)
            == type_id
        ]

    def write_document_content(self, secret: str, markdown: str) -> None:
        self._client.put_document(secret, markdown)

    def read_document_content(self, secret: str) -> str:
        return self._client.get_document(secret)

    # -- internals ------------------------------------------------------

    def _enum_option(self, database: str, option_name: str) -> str:
        rows = self._client.command(
            "fibery.entity/query",
            {
                "query": {
                    "q/from": database,
                    "q/select": [ID_FIELD, ENUM_NAME_FIELD],
                    "q/where": ["=", [ENUM_NAME_FIELD], "$name"],
                    "q/limit": 1,
                },
                "params": {"$name": option_name},
            },
        )
        if not rows:
            raise FiberyError(f"{database} has no option named {option_name!r}.")
        return rows[0][ID_FIELD]

    def _update_requirement(self, entity_id: str, values: dict[str, Any]) -> None:
        self._client.command(
            "fibery.entity/update",
            {
                "type": self.requirement_database,
                "entity": {ID_FIELD: entity_id, **values},
            },
        )

    def _query_requirements(
        self,
        schema: _RequirementSchema,
        where: list[Any],
        params: dict[str, Any],
        limit: int,
    ) -> list[dict[str, Any]]:
        return (
            self._client.command(
                "fibery.entity/query",
                {
                    "query": {
                        "q/from": self.requirement_database,
                        "q/select": [
                            ID_FIELD,
                            PUBLIC_ID_FIELD,
                            schema.requirement_id_field,
                            schema.title_field,
                            schema.revision_field,
                            schema.fingerprint_field,
                            {schema.type_field: [ENUM_NAME_FIELD]},
                            {WORKFLOW_STATE_FIELD: [ENUM_NAME_FIELD]},
                            {schema.project_field: [ID_FIELD]},
                            *(
                                [{schema.category_field: [ENUM_NAME_FIELD]}]
                                if schema.category_field
                                else []
                            ),
                        ],
                        "q/where": where,
                        "q/limit": limit,
                    },
                    "params": params,
                },
            )
            or []
        )

    def _to_requirement(
        self, schema: _RequirementSchema, row: dict[str, Any]
    ) -> RequirementRecord:
        return RequirementRecord(
            id=row[ID_FIELD],
            public_id=row.get(PUBLIC_ID_FIELD) or "",
            requirement_id=row.get(schema.requirement_id_field),
            title=row.get(schema.title_field),
            type_name=(row.get(schema.type_field) or {}).get(ENUM_NAME_FIELD),
            state=(row.get(WORKFLOW_STATE_FIELD) or {}).get(ENUM_NAME_FIELD),
            revision=row.get(schema.revision_field),
            project_id=(row.get(schema.project_field) or {}).get(ID_FIELD),
            source_fingerprint=row.get(schema.fingerprint_field),
            category=(
                (row.get(schema.category_field) or {}).get(ENUM_NAME_FIELD)
                if schema.category_field
                else None
            ),
        )

    def _requirement_schema(self) -> _RequirementSchema:
        if self._schema is None:
            self._schema = self._resolve_requirement_schema()
        return self._schema

    def _resolve_requirement_schema(self) -> _RequirementSchema:
        schema = self._client.command("fibery.schema/query")
        entry = next(
            (
                candidate
                for candidate in (schema or {}).get(TYPES_KEY, [])
                if candidate.get(FIELD_NAME_KEY) == self.requirement_database
            ),
            None,
        )
        if entry is None:
            raise FiberyError(
                f"Database {self.requirement_database!r} was not found in the "
                "workspace schema."
            )
        fields = entry.get(FIELDS_KEY, [])
        by_label = _index_fields_by_label(fields, self._space)
        by_name = {field.get(FIELD_NAME_KEY): field for field in fields}

        state_field = by_name.get(WORKFLOW_STATE_FIELD)
        if state_field is None:
            raise FiberyError(
                f"{self.requirement_database} has no {WORKFLOW_STATE_FIELD} Field."
            )
        type_field = by_label.get(FIELD_LABEL_TYPE)
        if type_field is None:
            raise FiberyError(f"{self.requirement_database} has no 'type' Field.")
        category_field = by_label.get(FIELD_LABEL_CATEGORY)
        derived_from_field = by_label.get(FIELD_LABEL_DERIVED_FROM)
        depends_on_field = by_label.get(FIELD_LABEL_DEPENDS_ON)
        affects_field = by_label.get(FIELD_LABEL_AFFECTS)

        return _RequirementSchema(
            requirement_id_field=_require_field(
                by_label, FIELD_LABEL_REQUIREMENT_ID, self.requirement_database
            ),
            title_field=_require_field(
                by_label, FIELD_LABEL_TITLE, self.requirement_database
            ),
            type_field=type_field[FIELD_NAME_KEY],
            type_database=type_field[FIELD_TYPE_KEY],
            revision_field=_require_field(
                by_label, FIELD_LABEL_REVISION, self.requirement_database
            ),
            project_field=_require_field(
                by_label, FIELD_LABEL_PROJECT, self.requirement_database
            ),
            fingerprint_field=_require_field(
                by_label, FIELD_LABEL_SOURCE_FINGERPRINT, self.requirement_database
            ),
            state_database=state_field[FIELD_TYPE_KEY],
            type_id=entry[ID_FIELD],
            category_field=(category_field[FIELD_NAME_KEY] if category_field else None),
            category_database=(
                category_field[FIELD_TYPE_KEY] if category_field else None
            ),
            derived_from_field=(
                derived_from_field[FIELD_NAME_KEY] if derived_from_field else None
            ),
            depends_on_field=(
                depends_on_field[FIELD_NAME_KEY] if depends_on_field else None
            ),
            affects_field=(affects_field[FIELD_NAME_KEY] if affects_field else None),
        )


def _to_document(view: dict[str, Any]) -> DocumentNode:
    meta = view.get(VIEW_META_KEY) or {}
    return DocumentNode(
        id=view[ID_FIELD],
        name=view.get(VIEW_NAME_KEY) or "",
        folder_id=(view.get(VIEW_FOLDER_KEY) or {}).get(ID_FIELD),
        entity_public_id=view.get(VIEW_CONTAINER_ENTITY_ID_KEY),
        secret=meta.get(DOCUMENT_SECRET_META_KEY),
    )


class FiberyRawProcessorWorkspace(FiberyRequirementWorkspace):
    """Fibery access for the RAW Requirement Processor.

    Extends the requirement-add adapter with the reads and writes decomposition
    needs. Collections cannot be written during entity creation (constraint 15),
    so provenance is a separate call.
    """

    def read_project(self, project_id: str) -> ProjectRecord | None:
        return self._projects.read_project(project_id)

    def find_requirement_by_requirement_id(
        self, requirement_id: str
    ) -> RequirementRecord | None:
        schema = self._requirement_schema()
        rows = self._query_requirements(
            schema,
            ["=", [schema.requirement_id_field], "$r"],
            {"$r": requirement_id},
            2,
        )
        return self._to_requirement(schema, rows[0]) if rows else None

    def standard_requirements_in_project(
        self, project_id: str
    ) -> list[RequirementRecord]:
        """The Project's Standard Requirements, bounded for comparison.

        Filters on Type at the query so the bound counts Standard rows, and
        asks for two rows more than the comparison corpus admits (the target
        may be one of them): a result with more peers than the limit is a
        lower bound, never a complete Project.
        """
        schema = self._requirement_schema()
        rows = self._query_requirements(
            schema,
            [
                "and",
                ["=", [schema.project_field, ID_FIELD], "$project"],
                ["=", [schema.type_field, ENUM_NAME_FIELD], "$type"],
            ],
            {"$project": project_id, "$type": STANDARD_TYPE_NAME},
            COMPARISON_QUERY_LIMIT,
        )
        records = [self._to_requirement(schema, row) for row in rows]
        return [r for r in records if r.type_name == STANDARD_TYPE_NAME]

    def child_documents(self, parent_document_id: str) -> list[DocumentNode]:
        views = self._client.views_rpc(QUERY_VIEWS_METHOD, {}) or []
        return [
            _to_document(view)
            for view in views
            if view.get(VIEW_TYPE_KEY) == DOCUMENT_VIEW_TYPE
            and view.get(VIEW_PARENT_PAGE_KEY) == parent_document_id
        ]

    def create_child_document(self, name: str, parent_document_id: str) -> DocumentNode:
        """Create a Document nested under another Document.

        `fibery/parent-page-id` is undocumented but accepted and read back.
        """
        document_id = str(uuid.uuid4())
        secret = str(uuid.uuid4())
        self._client.views_rpc(
            CREATE_VIEWS_METHOD,
            {
                CREATE_VIEWS_PARAM: [
                    {
                        ID_FIELD: document_id,
                        VIEW_NAME_KEY: name,
                        VIEW_TYPE_KEY: DOCUMENT_VIEW_TYPE,
                        VIEW_META_KEY: {DOCUMENT_SECRET_META_KEY: secret},
                        VIEW_CONTAINER_APP_KEY: {ID_FIELD: self._space_id},
                        VIEW_PARENT_PAGE_KEY: parent_document_id,
                    }
                ]
            },
        )
        resolved = self.resolve_document(document_id)
        if resolved is None:
            raise FiberyError(f"The child Document {name!r} could not be read back.")
        return resolved

    def create_requirement_with_id(
        self,
        entity_id: str,
        project_id: str,
        title: str,
        revision: int,
        category: str,
    ) -> RequirementRecord:
        """Create a Standard Requirement at an exact caller-chosen id.

        Fibery rejects a second create at the same id, so this doubles as the
        existence check a retry depends on.
        """
        schema = self._requirement_schema()
        if not schema.category_field or not schema.category_database:
            raise FiberyError(
                f"{self.requirement_database} has no Category Field to classify "
                "a Standard Requirement with."
            )
        option = self._enum_option(schema.category_database, category)
        self._client.command(
            "fibery.entity/create",
            {
                "type": self.requirement_database,
                "entity": {
                    ID_FIELD: entity_id,
                    schema.title_field: title,
                    schema.revision_field: revision,
                    schema.project_field: {ID_FIELD: project_id},
                    schema.category_field: {ID_FIELD: option},
                },
            },
        )
        record = self.read_requirement(entity_id)
        if record is None:
            raise FiberyError(
                "The created Standard Requirement could not be read back."
            )
        return record

    def derived_from(self, entity_id: str) -> list[RequirementRecord]:
        """The Requirements this one derives from.

        Collections cannot be selected alongside secured Fields (constraint 18),
        so the ids are read first and the records fetched by id.
        """
        schema = self._requirement_schema()
        if not schema.derived_from_field:
            return []
        rows = (
            self._client.command(
                "fibery.entity/query",
                {
                    "query": {
                        "q/from": self.requirement_database,
                        "q/select": [
                            ID_FIELD,
                            {schema.derived_from_field: [ID_FIELD]},
                        ],
                        "q/where": ["=", [ID_FIELD], "$id"],
                        "q/limit": SINGLE_ROW_LIMIT,
                    },
                    "params": {"$id": entity_id},
                },
            )
            or []
        )
        if not rows:
            return []
        ids = (rows[0].get(schema.derived_from_field) or {}).get(ID_FIELD) or []
        records = [self.read_requirement(value) for value in ids]
        return [record for record in records if record is not None]

    def requirement_relations(self, entity_id: str) -> RequirementRelations:
        """The Depends On and Affects edges this Requirement already has.

        Both collections are read in one query, and only `fibery/id` is
        selected from each: constraint 18 rejects a sub-select that reaches a
        secured Field, so the Requirement IDs are resolved afterwards.
        """
        schema = self._requirement_schema()
        collections = [
            field for field in (schema.depends_on_field, schema.affects_field) if field
        ]
        if not collections:
            return RequirementRelations()
        rows = (
            self._client.command(
                "fibery.entity/query",
                {
                    "query": {
                        "q/from": self.requirement_database,
                        "q/select": [
                            ID_FIELD,
                            *({field: [ID_FIELD]} for field in collections),
                        ],
                        "q/where": ["=", [ID_FIELD], "$id"],
                        "q/limit": SINGLE_ROW_LIMIT,
                    },
                    "params": {"$id": entity_id},
                },
            )
            or []
        )
        if not rows:
            return RequirementRelations()
        return RequirementRelations(
            depends_on=self._related_ids(rows[0], schema.depends_on_field),
            affects=self._related_ids(rows[0], schema.affects_field),
        )

    def _related_ids(self, row: dict[str, Any], field: str | None) -> tuple[str, ...]:
        """Resolve one collection of entity ids to Requirement IDs."""
        if not field:
            return ()
        ids = (row.get(field) or {}).get(ID_FIELD) or []
        records = (self.read_requirement(value) for value in ids)
        return tuple(
            record.requirement_id
            for record in records
            if record is not None and record.requirement_id
        )

    def add_derived_from(self, entity_id: str, raw_entity_id: str) -> None:
        """Link a Standard Requirement to its RAW.

        Fibery populates the inverse `Produces` automatically, because both
        sides share one relation.
        """
        schema = self._requirement_schema()
        if not schema.derived_from_field:
            raise FiberyError(
                f"{self.requirement_database} has no 'Derived From' Field."
            )
        self._add_collection_item(schema.derived_from_field, entity_id, raw_entity_id)

    # -- apply ----------------------------------------------------------

    def find_requirements_by_requirement_id(
        self, requirement_id: str
    ) -> list[RequirementRecord]:
        """Every Requirement with this Requirement ID, bounded to two rows.

        Unlike `find_requirement_by_requirement_id`, which is frozen for its
        callers, this reports ambiguity instead of hiding a second match.
        """
        schema = self._requirement_schema()
        rows = self._query_requirements(
            schema,
            ["=", [schema.requirement_id_field], "$r"],
            {"$r": requirement_id},
            AMBIGUITY_QUERY_LIMIT,
        )
        return [self._to_requirement(schema, row) for row in rows]

    def add_depends_on(self, entity_id: str, target_entity_id: str) -> None:
        """Add one Depends On edge; Fibery maintains the inverse Blocks."""
        schema = self._requirement_schema()
        if not schema.depends_on_field:
            raise FiberyError(f"{self.requirement_database} has no 'Depends On' Field.")
        self._add_collection_item(schema.depends_on_field, entity_id, target_entity_id)

    def add_affects(self, entity_id: str, target_entity_id: str) -> None:
        """Add one Affects edge; Fibery maintains the inverse Impacted By."""
        schema = self._requirement_schema()
        if not schema.affects_field:
            raise FiberyError(f"{self.requirement_database} has no 'Affects' Field.")
        self._add_collection_item(schema.affects_field, entity_id, target_entity_id)

    def set_document_folder(self, document_id: str, folder_id: str) -> None:
        """Move the same Document entity into another Folder (constraint 24)."""
        self._client.views_rpc(
            UPDATE_VIEWS_METHOD,
            {
                UPDATE_VIEWS_PARAM: [
                    {
                        "id": document_id,
                        "values": {VIEW_FOLDER_KEY: {ID_FIELD: folder_id}},
                    }
                ]
            },
        )

    def _add_collection_item(self, field: str, entity_id: str, item_id: str) -> None:
        """Additive membership; a repeated add is a no-op (constraint 26)."""
        self._client.command(
            ADD_COLLECTION_ITEMS_COMMAND,
            {
                "type": self.requirement_database,
                "field": field,
                "entity": {entity_id: [item_id]},
            },
        )
