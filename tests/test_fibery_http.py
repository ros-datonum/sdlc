"""Contract tests for the Fibery HTTP adapter, driven by a stub URL opener."""

import io
import json
import urllib.error

import pytest

from sdlc.config import FiberySettings
from sdlc.fibery_client import FiberyClient
from sdlc.fibery_http import FiberyHttpWorkspace
from sdlc.fibery_workspace import FiberyError

SETTINGS = FiberySettings(
    host="example.fibery.io",
    token="test-token",
    space="SDLC",
    space_id="space-uuid",
)

PROJECT_SCHEMA = {
    "fibery/types": [
        {
            "fibery/name": "SDLC/Project",
            "fibery/fields": [
                {"fibery/name": "fibery/id", "fibery/type": "fibery/uuid"},
                {"fibery/name": "SDLC/Name", "fibery/type": "fibery/text"},
                {"fibery/name": "SDLC/Code", "fibery/type": "fibery/text"},
                {
                    "fibery/name": "SDLC/Description",
                    "fibery/type": "Collaboration~Documents/Document",
                },
                {
                    "fibery/name": "SDLC/Documents Root Folder ID",
                    "fibery/type": "fibery/text",
                },
                {
                    "fibery/name": "workflow/state",
                    "fibery/type": "workflow/state_SDLC/Project",
                },
            ],
        }
    ]
}


class StubResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()
        return False


class StubOpener:
    """Answers requests from a queue of canned payloads and records them."""

    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.requests = []

    def __call__(self, request, timeout):
        self.requests.append(
            {
                "method": request.method,
                "url": request.full_url,
                "headers": dict(request.headers),
                "body": json.loads(request.data.decode("utf-8")),
            }
        )
        if not self.payloads:
            raise AssertionError(f"Unexpected request to {request.full_url}")
        return StubResponse(json.dumps(self.payloads.pop(0)).encode("utf-8"))


def ok(result):
    return [{"success": True, "result": result}]


def rpc(result):
    return {"jsonrpc": "2.0", "id": 1, "result": result}


def build_workspace(payloads):
    """Build a workspace whose first call resolves the Project schema."""
    return _build([ok(PROJECT_SCHEMA), *payloads])


def build_views_workspace(payloads):
    """Build a workspace for view operations, which never read the schema."""
    return _build(payloads)


def _build(payloads):
    opener = StubOpener(payloads)
    workspace = FiberyHttpWorkspace(
        FiberyClient(SETTINGS, url_opener=opener),
        space=SETTINGS.space,
        space_id=SETTINGS.space_id,
    )
    return workspace, opener


# -- transport -------------------------------------------------------------


def test_requests_carry_the_token_and_target_the_commands_endpoint():
    workspace, opener = build_workspace([ok([])])

    workspace.find_project_by_name("SDLC")

    schema_request = opener.requests[0]
    assert schema_request["url"] == "https://example.fibery.io/api/commands"
    assert schema_request["headers"]["Authorization"] == "Token test-token"
    assert schema_request["body"] == [{"command": "fibery.schema/query"}]


def test_unsuccessful_envelope_becomes_a_fibery_error():
    opener = StubOpener(
        [[{"success": False, "result": {"name": "entity.error/x", "message": "nope"}}]]
    )
    client = FiberyClient(SETTINGS, url_opener=opener)

    with pytest.raises(FiberyError, match="entity.error/x"):
        client.command("fibery.schema/query")


def test_http_error_becomes_a_fibery_error():
    def failing(request, timeout):
        raise urllib.error.HTTPError(
            request.full_url, 401, "Unauthorized", {}, io.BytesIO(b"Unauthorized")
        )

    client = FiberyClient(SETTINGS, url_opener=failing)

    with pytest.raises(FiberyError, match="401"):
        client.command("fibery.schema/query")


def test_json_rpc_error_becomes_a_fibery_error():
    opener = StubOpener([{"jsonrpc": "2.0", "id": 1, "error": {"message": "bad"}}])
    client = FiberyClient(SETTINGS, url_opener=opener)

    with pytest.raises(FiberyError, match="bad"):
        client.views_rpc("query-views", {})


# -- schema resolution -----------------------------------------------------


def test_field_names_are_resolved_from_the_workspace_schema():
    workspace, opener = build_workspace([ok([])])

    workspace.find_project_by_name("SDLC")

    query = opener.requests[1]["body"][0]["args"]["query"]
    assert query["q/from"] == "SDLC/Project"
    assert query["q/select"][1:4] == [
        "SDLC/Name",
        "SDLC/Code",
        "SDLC/Documents Root Folder ID",
    ]
    assert query["q/where"] == ["=", ["SDLC/Name"], "$name"]


def test_missing_project_database_is_reported():
    opener = StubOpener([ok({"fibery/types": []})])
    workspace = FiberyHttpWorkspace(
        FiberyClient(SETTINGS, url_opener=opener), "SDLC", "space-uuid"
    )

    with pytest.raises(FiberyError, match="SDLC/Project"):
        workspace.find_project_by_name("SDLC")


def test_missing_required_field_is_reported():
    schema = {
        "fibery/types": [
            {
                "fibery/name": "SDLC/Project",
                "fibery/fields": [
                    {"fibery/name": "SDLC/Name", "fibery/type": "fibery/text"},
                    {"fibery/name": "workflow/state", "fibery/type": "workflow/x"},
                ],
            }
        ]
    }
    opener = StubOpener([ok(schema)])
    workspace = FiberyHttpWorkspace(
        FiberyClient(SETTINGS, url_opener=opener), "SDLC", "space-uuid"
    )

    with pytest.raises(FiberyError, match="'code'"):
        workspace.find_project_by_name("SDLC")


# -- entities --------------------------------------------------------------


def test_project_rows_are_mapped_onto_records():
    workspace, _ = build_workspace(
        [
            ok(
                [
                    {
                        "fibery/id": "p1",
                        "SDLC/Name": "SDLC",
                        "SDLC/Code": "SDLC",
                        "SDLC/Documents Root Folder ID": "folder-1",
                        "workflow/state": {"enum/name": "Planned"},
                    }
                ]
            )
        ]
    )

    record = workspace.find_project_by_name("SDLC")

    assert (record.id, record.code, record.state) == ("p1", "SDLC", "Planned")
    assert record.documents_root_folder_id == "folder-1"


def test_missing_project_returns_none():
    workspace, _ = build_workspace([ok([])])

    assert workspace.find_project_by_name("SDLC") is None


def test_create_project_sends_name_and_code_and_returns_the_id():
    workspace, opener = build_workspace([ok({"fibery/id": "p1"})])

    assert workspace.create_project("SDLC", "SDLC") == "p1"

    args = opener.requests[1]["body"][0]["args"]
    assert args["type"] == "SDLC/Project"
    assert args["entity"] == {"SDLC/Name": "SDLC", "SDLC/Code": "SDLC"}


def test_create_project_without_an_id_is_an_error():
    workspace, _ = build_workspace([ok({})])

    with pytest.raises(FiberyError, match="did not return an id"):
        workspace.create_project("SDLC", "SDLC")


def test_setting_state_resolves_the_state_entity_first():
    workspace, opener = build_workspace(
        [
            ok([{"fibery/id": "state-1", "enum/name": "Planned"}]),
            ok({"fibery/id": "p1"}),
        ]
    )

    workspace.set_project_state("p1", "Planned")

    state_query = opener.requests[1]["body"][0]["args"]["query"]
    assert state_query["q/from"] == "workflow/state_SDLC/Project"
    update = opener.requests[2]["body"][0]["args"]["entity"]
    assert update["workflow/state"] == {"fibery/id": "state-1"}


def test_unknown_state_is_reported():
    workspace, _ = build_workspace([ok([])])

    with pytest.raises(FiberyError, match="no state named 'Planned'"):
        workspace.set_project_state("p1", "Planned")


def test_root_folder_id_is_stored_on_the_project():
    workspace, opener = build_workspace([ok({"fibery/id": "p1"})])

    workspace.set_documents_root_folder("p1", "folder-1")

    entity = opener.requests[1]["body"][0]["args"]["entity"]
    assert entity == {
        "fibery/id": "p1",
        "SDLC/Documents Root Folder ID": "folder-1",
    }


def test_description_is_written_through_the_documents_endpoint():
    workspace, opener = build_workspace(
        [
            ok(
                [
                    {
                        "fibery/id": "p1",
                        "SDLC/Description": {
                            "Collaboration~Documents/secret": "secret-1"
                        },
                    }
                ]
            ),
            {},
        ]
    )

    workspace.set_project_description("p1", "Bootstrap.")

    put = opener.requests[2]
    assert put["method"] == "PUT"
    assert put["url"].endswith("/api/documents/secret-1?format=md")
    assert put["body"] == {"content": "Bootstrap."}


# -- folders ---------------------------------------------------------------


def test_creating_a_root_folder_omits_the_parent():
    workspace, opener = build_views_workspace([rpc([])])

    node = workspace.create_folder("SDLC", None)

    body = opener.requests[0]["body"]
    assert opener.requests[0]["url"].endswith("/api/views/json-rpc")
    assert body["method"] == "create-folders"
    # create-folders takes "values"; create-views takes "views".
    [value] = body["params"]["values"]
    assert value["fibery/name"] == "SDLC"
    assert value["fibery/container-app"] == {"fibery/id": "space-uuid"}
    assert "fibery/Parent Folder" not in value
    assert value["fibery/id"] == node.id
    assert node.parent_id is None


def test_creating_a_child_folder_sends_the_parent_folder():
    workspace, opener = build_views_workspace([rpc([])])

    node = workspace.create_folder("Requirements", "root-1")

    [value] = opener.requests[0]["body"]["params"]["values"]
    assert value["fibery/Parent Folder"] == {"fibery/id": "root-1"}
    assert node.parent_id == "root-1"


def test_finding_a_folder_matches_name_and_parent():
    workspace, _ = build_views_workspace(
        [
            rpc(
                [
                    {
                        "fibery/id": "f1",
                        "fibery/name": "Raw",
                        "fibery/Parent Folder": {"fibery/id": "req-1"},
                        "fibery/container-app": {"fibery/id": "space-uuid"},
                    },
                    {
                        "fibery/id": "f2",
                        "fibery/name": "Raw",
                        "fibery/Parent Folder": {"fibery/id": "other-1"},
                        "fibery/container-app": {"fibery/id": "space-uuid"},
                    },
                ]
            )
        ]
    )

    assert workspace.find_folder("Raw", "req-1").id == "f1"
    assert workspace.find_folder("Raw", "other-1").id == "f2"
    assert workspace.find_folder("Raw", "missing") is None


def test_finding_a_root_folder_matches_a_null_parent():
    workspace, _ = build_views_workspace(
        [
            rpc(
                [
                    {
                        "fibery/id": "f1",
                        "fibery/name": "SDLC",
                        "fibery/Parent Folder": None,
                        "fibery/container-app": {"fibery/id": "space-uuid"},
                    }
                ]
            )
        ]
    )

    assert workspace.find_folder("SDLC", None).id == "f1"


def test_folders_from_other_spaces_are_ignored():
    workspace, _ = build_views_workspace(
        [
            rpc(
                [
                    {
                        "fibery/id": "f1",
                        "fibery/name": "SDLC",
                        "fibery/Parent Folder": None,
                        "fibery/container-app": {"fibery/id": "another-space"},
                    }
                ]
            )
        ]
    )

    assert workspace.find_folder("SDLC", None) is None


def test_the_folder_listing_is_fetched_once_and_refreshed_after_a_create():
    workspace, opener = build_views_workspace(
        [
            rpc([]),
            rpc([]),
            rpc(
                [
                    {
                        "fibery/id": "f9",
                        "fibery/name": "SDLC",
                        "fibery/Parent Folder": None,
                        "fibery/container-app": {"fibery/id": "space-uuid"},
                    }
                ]
            ),
        ]
    )

    workspace.find_folder("SDLC", None)
    workspace.find_folder("SDLC", None)
    workspace.create_folder("SDLC", None)

    assert workspace.find_folder("SDLC", None).id == "f9"
    assert len(opener.requests) == 3


def test_query_folders_sends_no_filter():
    """query-folders accepts no filter, so narrowing happens client side."""
    workspace, opener = build_views_workspace([rpc([])])

    workspace.find_folder("SDLC", None)

    body = opener.requests[0]["body"]
    assert body["method"] == "query-folders"
    assert body["params"] == {}
