"""Contract tests for the Requirement Fibery adapter, driven by a stub opener."""

import pytest

from sdlc.fibery_client import FiberyClient
from sdlc.fibery_http import FiberyRequirementWorkspace
from sdlc.fibery_workspace import FiberyError
from test_fibery_http import SETTINGS, StubOpener, ok, rpc

REQUIREMENT_TYPE_ID = "0cbb35c1-b71f-4429-b45e-4a9fd5ada7c2"

REQUIREMENT_SCHEMA = {
    "fibery/types": [
        {
            "fibery/name": "SDLC/Requirement",
            "fibery/id": REQUIREMENT_TYPE_ID,
            "fibery/fields": [
                {"fibery/name": "SDLC/Requirement ID", "fibery/type": "fibery/text"},
                {"fibery/name": "SDLC/Title", "fibery/type": "fibery/text"},
                {"fibery/name": "SDLC/Revision", "fibery/type": "fibery/int"},
                {
                    "fibery/name": "SDLC/Source Fingerprint",
                    "fibery/type": "fibery/text",
                },
                {"fibery/name": "SDLC/Project", "fibery/type": "SDLC/Project"},
                {
                    "fibery/name": "SDLC/Type",
                    "fibery/type": "SDLC/Type_Agentic SDLC/Requirement",
                },
                {
                    "fibery/name": "workflow/state",
                    "fibery/type": "workflow/state_SDLC/Requirement",
                },
            ],
        }
    ]
}


def build(payloads):
    opener = StubOpener([ok(REQUIREMENT_SCHEMA), *payloads])
    workspace = FiberyRequirementWorkspace(
        FiberyClient(SETTINGS, url_opener=opener), "SDLC", "space-uuid"
    )
    return workspace, opener


def build_views(payloads):
    """For view operations that never resolve the Requirement schema."""
    opener = StubOpener(list(payloads))
    workspace = FiberyRequirementWorkspace(
        FiberyClient(SETTINGS, url_opener=opener), "SDLC", "space-uuid"
    )
    return workspace, opener


# -- schema ----------------------------------------------------------------


def test_requirement_fields_are_resolved_from_the_schema():
    workspace, opener = build([ok([])])

    workspace.read_requirement("r1")

    query = opener.requests[1]["body"][0]["args"]["query"]
    assert query["q/from"] == "SDLC/Requirement"
    assert "SDLC/Requirement ID" in query["q/select"]
    assert "SDLC/Source Fingerprint" in query["q/select"]


def test_missing_source_fingerprint_field_is_reported():
    schema = {
        "fibery/types": [
            {
                "fibery/name": "SDLC/Requirement",
                "fibery/id": REQUIREMENT_TYPE_ID,
                "fibery/fields": [
                    {
                        "fibery/name": "SDLC/Requirement ID",
                        "fibery/type": "fibery/text",
                    },
                    {"fibery/name": "SDLC/Title", "fibery/type": "fibery/text"},
                    {"fibery/name": "SDLC/Revision", "fibery/type": "fibery/int"},
                    {"fibery/name": "SDLC/Project", "fibery/type": "SDLC/Project"},
                    {"fibery/name": "workflow/state", "fibery/type": "workflow/x"},
                    {"fibery/name": "SDLC/Type", "fibery/type": "enum"},
                ],
            }
        ]
    }
    opener = StubOpener([ok(schema)])
    workspace = FiberyRequirementWorkspace(
        FiberyClient(SETTINGS, url_opener=opener), "SDLC", "space-uuid"
    )

    with pytest.raises(FiberyError, match="source fingerprint"):
        workspace.read_requirement("r1")


# -- entities ---------------------------------------------------------------


def test_create_requirement_sends_the_specified_initial_fields():
    workspace, opener = build(
        [
            ok({"fibery/id": "r1"}),
            ok(
                [
                    {
                        "fibery/id": "r1",
                        "fibery/public-id": "7",
                        "SDLC/Requirement ID": "SDLC-RAW-0001",
                        "SDLC/Title": "T",
                        "SDLC/Revision": 1,
                        "SDLC/Source Fingerprint": "abc",
                        "SDLC/Project": {"fibery/id": "p1"},
                    }
                ]
            ),
        ]
    )

    record = workspace.create_requirement("p1", "SDLC-RAW-0001", "T", 1, "abc")

    entity = opener.requests[1]["body"][0]["args"]["entity"]
    assert entity == {
        "SDLC/Requirement ID": "SDLC-RAW-0001",
        "SDLC/Title": "T",
        "SDLC/Revision": 1,
        "SDLC/Source Fingerprint": "abc",
        "SDLC/Project": {"fibery/id": "p1"},
    }
    assert record.public_id == "7"


def test_create_requirement_never_writes_the_readonly_name_field():
    """SDLC/Name is a formula of Requirement ID and Title."""
    workspace, opener = build(
        [ok({"fibery/id": "r1"}), ok([{"fibery/id": "r1", "fibery/public-id": "7"}])]
    )

    workspace.create_requirement("p1", "SDLC-RAW-0001", "T", 1, "abc")

    entity = opener.requests[1]["body"][0]["args"]["entity"]
    assert "SDLC/Name" not in entity


def test_setting_type_resolves_the_option_entity_first():
    workspace, opener = build(
        [ok([{"fibery/id": "opt-raw", "enum/name": "Raw"}]), ok({"fibery/id": "r1"})]
    )

    workspace.set_requirement_type("r1", "Raw")

    option_query = opener.requests[1]["body"][0]["args"]["query"]
    assert option_query["q/from"] == "SDLC/Type_Agentic SDLC/Requirement"
    update = opener.requests[2]["body"][0]["args"]["entity"]
    assert update["SDLC/Type"] == {"fibery/id": "opt-raw"}


def test_unknown_type_option_is_reported():
    workspace, _ = build([ok([])])

    with pytest.raises(FiberyError, match="no option named 'Raw'"):
        workspace.set_requirement_type("r1", "Raw")


def test_fingerprint_lookup_scopes_to_the_project():
    workspace, opener = build([ok([])])

    workspace.find_requirement_by_fingerprint("p1", "abc")

    where = opener.requests[1]["body"][0]["args"]["query"]["q/where"]
    assert where[0] == "q/and"
    assert ["=", ["SDLC/Project", "fibery/id"], "$project"] in where
    assert ["=", ["SDLC/Source Fingerprint"], "$fingerprint"] in where


# -- documents --------------------------------------------------------------


def test_document_is_created_in_the_folder_and_attached_by_public_id():
    """Fibery rejects the entity uuid here with parent-entity-not-found."""
    import json as _json

    from test_fibery_http import StubResponse

    sent = {}

    def echoing(request, timeout):
        body = (
            _json.loads(request.data.decode("utf-8"))
            if request.data is not None
            else None
        )
        if request.full_url.endswith("/api/commands"):
            payload = ok(REQUIREMENT_SCHEMA)
        elif body["method"] == "create-views":
            sent["view"] = body["params"]["views"][0]
            payload = rpc([])
        else:
            payload = rpc([dict(sent["view"])])
        return StubResponse(_json.dumps(payload).encode("utf-8"))

    workspace = FiberyRequirementWorkspace(
        FiberyClient(SETTINGS, url_opener=echoing), "SDLC", "space-uuid"
    )

    node = workspace.create_requirement_document("SDLC-RAW-0001 — T", "folder-raw", "7")

    view = sent["view"]
    assert view["fibery/type"] == "document"
    assert view["fibery/Folder"] == {"fibery/id": "folder-raw"}
    assert view["fibery/container-type"] == "object"
    assert view["fibery/container-entity-type"] == {"fibery/id": REQUIREMENT_TYPE_ID}
    assert view["fibery/container-entity-id"] == "7"
    assert node.id == view["fibery/id"]
    # Fibery allocates no secret; the client supplies one at create time.
    assert view["fibery/meta"]["documentSecret"]
    assert node.secret == view["fibery/meta"]["documentSecret"]
    assert node.folder_id == "folder-raw"
    assert node.entity_public_id == "7"


def test_created_document_is_read_back_not_assumed():
    workspace, _ = build([rpc([]), rpc([])])

    with pytest.raises(FiberyError, match="could not be read back"):
        workspace.create_requirement_document("N", "folder-raw", "7")


def test_attached_documents_match_the_requirement_type_and_public_id():
    workspace, _ = build_views(
        [
            rpc(
                [
                    {
                        "fibery/id": "d1",
                        "fibery/name": "mine",
                        "fibery/type": "document",
                        "fibery/container-entity-id": "7",
                        "fibery/container-entity-type": {
                            "fibery/id": REQUIREMENT_TYPE_ID
                        },
                        "fibery/meta": {},
                    },
                    {
                        "fibery/id": "d2",
                        "fibery/name": "other requirement",
                        "fibery/type": "document",
                        "fibery/container-entity-id": "8",
                        "fibery/container-entity-type": {
                            "fibery/id": REQUIREMENT_TYPE_ID
                        },
                        "fibery/meta": {},
                    },
                    {
                        "fibery/id": "d3",
                        "fibery/name": "a project document",
                        "fibery/type": "document",
                        "fibery/container-entity-id": "7",
                        "fibery/container-entity-type": {"fibery/id": "another-type"},
                        "fibery/meta": {},
                    },
                ]
            ),
            ok(REQUIREMENT_SCHEMA),
        ]
    )

    attached = workspace.documents_attached_to_requirement("7")

    assert [node.id for node in attached] == ["d1"]


def test_content_is_written_and_read_through_the_documents_endpoint():
    workspace, opener = build_views([{}, {"content": "# T\n"}])

    workspace.write_document_content("s1", "# T\n")
    assert workspace.read_document_content("s1") == "# T\n"

    put = opener.requests[0]
    assert put["method"] == "PUT"
    assert put["url"].endswith("/api/documents/s1?format=md")
    assert put["body"] == {"content": "# T\n"}
    assert opener.requests[1]["method"] == "GET"


def test_child_folders_are_matched_on_the_parent_id():
    workspace, _ = build_views(
        [
            rpc(
                [
                    {
                        "fibery/id": "f1",
                        "fibery/name": "Raw",
                        "fibery/Parent Folder": {"fibery/id": "req"},
                    },
                    {
                        "fibery/id": "f2",
                        "fibery/name": "Raw",
                        "fibery/Parent Folder": {"fibery/id": "elsewhere"},
                    },
                ]
            )
        ]
    )

    children = workspace.child_folders("req")

    assert [node.id for node in children] == ["f1"]


def test_document_is_created_with_a_client_supplied_secret():
    """Fibery allocates none; without it the Document has no addressable body."""
    import json as _json

    from test_fibery_http import StubResponse

    seen = {}

    def opener(request, timeout):
        body = (
            _json.loads(request.data.decode("utf-8"))
            if request.data is not None
            else None
        )
        if request.full_url.endswith("/api/commands"):
            return StubResponse(_json.dumps(ok(REQUIREMENT_SCHEMA)).encode())
        if body["method"] == "create-views":
            seen["view"] = body["params"]["views"][0]
            return StubResponse(_json.dumps(rpc([])).encode())
        return StubResponse(_json.dumps(rpc([dict(seen["view"])])).encode())

    workspace = FiberyRequirementWorkspace(
        FiberyClient(SETTINGS, url_opener=opener), "SDLC", "space-uuid"
    )

    first = workspace.create_requirement_document("A", "folder-raw", "7")
    second = workspace.create_requirement_document("B", "folder-raw", "8")

    assert first.secret and second.secret
    assert first.secret != second.secret
