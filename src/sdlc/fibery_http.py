"""FiberyWorkspace implemented against the live Fibery HTTP API.

Field names are resolved from the workspace schema rather than assumed, because
Fibery prefixes Fields with a Space name and mixes in Fields owned by other
Spaces (``workflow/state``, ``Collaboration~Documents/secret``).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sdlc.fibery_client import FiberyClient
from sdlc.fibery_workspace import FiberyError, FolderNode, ProjectRecord

PROJECT_DATABASE_NAME = "Project"

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
