"""I02 — ArchitectureWorkspace protocol, HTTP adapter and fake.

Driven entirely by the stub opener and the in-memory fake. Nothing here calls
live Fibery: the probe that would confirm live behaviour is `P-1`, which belongs
to I03, so every claim below is D-class only.
"""

from __future__ import annotations

import pytest

from architecture_fake import (
    OTHER_DATABASE_TYPE_ID,
    PROJECT_TYPE_ID,
    FakeArchitectureWorkspace,
    project,
)
from sdlc.fibery_client import FiberyClient
from sdlc.fibery_http import (
    FiberyArchitectureWorkspace,
    FiberyRawProcessorWorkspace,
    FiberyRequirementWorkspace,
)
from sdlc.fibery_workspace import (
    ArchitectureWorkspace,
    DocumentPlacement,
    FiberyError,
    ProjectRecord,
    is_valid_child_placement,
    is_valid_root_placement,
)
from test_fibery_http import (
    PROJECT_SCHEMA,
    SETTINGS,
    SPACE_ID,
    SPACE_ROWS,
    StubOpener,
    ok,
    resolved_client,
    rpc,
    unpaced,
)
from test_fibery_requirement_http import REQUIREMENT_SCHEMA, REQUIREMENT_TYPE_ID

PROJECT_PUBLIC_ID = "7"
PROJECT_ENTITY_ID = "project-1"
ARCHITECTURE_ID = "0576efe5-1d70-515e-b587-0a39f85ce6f2"
CHILD_ID = "3800ce1f-893d-5324-8539-d2e2e842ad55"
SCHEMA_TYPE_ID = PROJECT_SCHEMA["fibery/types"][0]["fibery/id"]


def echoing(build, schema=PROJECT_SCHEMA, views=None):
    """An opener routed by endpoint, the pattern the Requirement tests use.

    `create-views` is recorded and echoed back by the following `query-views`,
    which is how a real create is confirmed. `views` overrides what a
    `query-views` returns, so a read-back failure can be exercised.
    """
    import json as _json

    from test_fibery_http import StubResponse

    seen: dict = {"queries": []}

    def opener(request, timeout):
        body = _json.loads(request.data.decode("utf-8")) if request.data else None
        if request.full_url.endswith("/api/commands"):
            resolving = body[0]["command"] == "fibery.entity/query"
            payload = ok(SPACE_ROWS) if resolving else ok(schema)
        elif body["method"] == "create-views":
            seen["view"] = body["params"]["views"][0]
            payload = rpc([])
        else:
            seen["queries"].append(body["params"])
            if views is not None:
                payload = rpc(views)
            else:
                payload = rpc([dict(seen["view"])] if "view" in seen else [])
        return StubResponse(_json.dumps(payload).encode("utf-8"))

    return build(resolved_client(opener), "SDLC"), seen


def architecture_workspace(views=None, schema=PROJECT_SCHEMA):
    return echoing(FiberyArchitectureWorkspace, schema=schema, views=views)


def malformed_read_back(**overrides):
    """An adapter whose create read-back echoes the created view, corrupted.

    Exercises the read-back of a create: the view really is the one just
    written, with one field returned in a shape the Views API would not use.
    """
    import json as _json

    from test_fibery_http import StubResponse

    seen: dict = {"queries": []}

    def opener(request, timeout):
        body = _json.loads(request.data.decode("utf-8")) if request.data else None
        if request.full_url.endswith("/api/commands"):
            resolving = body[0]["command"] == "fibery.entity/query"
            payload = ok(SPACE_ROWS) if resolving else ok(PROJECT_SCHEMA)
        elif body["method"] == "create-views":
            seen["view"] = body["params"]["views"][0]
            payload = rpc([])
        else:
            payload = rpc([{**seen["view"], **overrides}] if "view" in seen else [])
        return StubResponse(_json.dumps(payload).encode("utf-8"))

    return FiberyArchitectureWorkspace(resolved_client(opener), "SDLC"), seen


def document_view(
    document_id: str,
    name: str = "Architecture",
    *,
    container_type: str | None = SCHEMA_TYPE_ID,
    container_entity: str | None = PROJECT_PUBLIC_ID,
    parent: str | None = None,
    secret: str | None = "secret-1",
    view_type: str = "document",
) -> dict:
    view: dict = {
        "fibery/id": document_id,
        "fibery/name": name,
        "fibery/type": view_type,
    }
    if secret is not None:
        view["fibery/meta"] = {"documentSecret": secret}
    if container_type is not None:
        view["fibery/container-entity-type"] = {"fibery/id": container_type}
    if container_entity is not None:
        view["fibery/container-entity-id"] = container_entity
    if parent is not None:
        view["fibery/parent-page-id"] = parent
    return view


def placement(**overrides) -> DocumentPlacement:
    fields = {
        "document_id": ARCHITECTURE_ID,
        "secret": "secret-1",
        "name": "Architecture",
        "container_entity_type": PROJECT_TYPE_ID,
        "container_entity_id": PROJECT_PUBLIC_ID,
        "parent_document_id": None,
    }
    return DocumentPlacement(**{**fields, **overrides})


# ==========================================================================
# ProjectRecord.public_id
# ==========================================================================


def test_project_reads_carry_the_public_id():
    opener = StubOpener(
        [
            ok(PROJECT_SCHEMA),
            ok(
                [
                    {
                        "fibery/id": PROJECT_ENTITY_ID,
                        "fibery/public-id": PROJECT_PUBLIC_ID,
                        "SDLC/Name": "SDLC",
                        "SDLC/Code": "SDLC",
                        "workflow/state": {"enum/name": "Planned"},
                    }
                ]
            ),
        ]
    )
    from sdlc.fibery_http import FiberyHttpWorkspace

    workspace = FiberyHttpWorkspace(
        FiberyClient(SETTINGS, url_opener=opener, **unpaced()), "SDLC"
    )

    record = workspace.read_project(PROJECT_ENTITY_ID)

    assert record is not None
    assert record.id == PROJECT_ENTITY_ID
    assert record.public_id == PROJECT_PUBLIC_ID
    assert record.public_id != record.id


def test_public_id_is_requested_from_fibery():
    opener = StubOpener([ok(PROJECT_SCHEMA), ok([])])
    from sdlc.fibery_http import FiberyHttpWorkspace

    workspace = FiberyHttpWorkspace(
        FiberyClient(SETTINGS, url_opener=opener, **unpaced()), "SDLC"
    )
    workspace.read_project(PROJECT_ENTITY_ID)

    query = opener.requests[1]["body"][0]["args"]["query"]
    assert "fibery/public-id" in query["q/select"]


def test_a_project_without_a_public_id_is_refused():
    """It is never inferred from the entity id, the name or the code."""
    opener = StubOpener(
        [
            ok(PROJECT_SCHEMA),
            ok([{"fibery/id": PROJECT_ENTITY_ID, "SDLC/Name": "SDLC"}]),
        ]
    )
    from sdlc.fibery_http import FiberyHttpWorkspace

    workspace = FiberyHttpWorkspace(
        FiberyClient(SETTINGS, url_opener=opener, **unpaced()), "SDLC"
    )
    with pytest.raises(FiberyError, match="public-id"):
        workspace.read_project(PROJECT_ENTITY_ID)


# ==========================================================================
# Protocol conformance
# ==========================================================================


#: The FULL frozen surface: section 2.1 plus the two placement reads of 2.2.1.
ARCHITECTURE_METHODS = (
    "read_project",
    "create_project_document",
    "create_tsa_child_document",
    "create_child_document",
    "documents_attached_to_project",
    "child_documents",
    "child_placements",
    "resolve_placement",
    "resolve_document",
    "read_document_content",
    "write_document_content",
)


@pytest.mark.parametrize("method", ARCHITECTURE_METHODS)
def test_adapter_structurally_satisfies_the_protocol(method):
    workspace, _ = architecture_workspace()
    assert callable(getattr(workspace, method))
    assert callable(getattr(FakeArchitectureWorkspace(), method))


def test_both_implementations_expose_lock_scope():
    workspace, _ = architecture_workspace()
    assert workspace.lock_scope == f"example.fibery.io/{SPACE_ID}"
    assert isinstance(FakeArchitectureWorkspace().lock_scope, str)


def test_the_protocol_declares_exactly_the_frozen_surface():
    declared = {
        name
        for name in vars(ArchitectureWorkspace)
        if not name.startswith("_") and name != "lock_scope"
    }
    assert declared == set(ARCHITECTURE_METHODS)


# ==========================================================================
# create_project_document
# ==========================================================================


def created_view(seen: dict) -> dict:
    return seen["view"]


def test_project_document_is_created_at_the_caller_id():
    workspace, seen = architecture_workspace()

    node = workspace.create_project_document(
        ARCHITECTURE_ID, "Architecture", PROJECT_PUBLIC_ID
    )

    sent = created_view(seen)
    assert sent["fibery/id"] == ARCHITECTURE_ID
    assert node.id == ARCHITECTURE_ID


def test_project_document_uses_the_project_type_id_and_public_id():
    workspace, seen = architecture_workspace()

    workspace.create_project_document(
        ARCHITECTURE_ID, "Architecture", PROJECT_PUBLIC_ID
    )

    sent = created_view(seen)
    assert sent["fibery/container-entity-type"] == {"fibery/id": SCHEMA_TYPE_ID}
    assert sent["fibery/container-entity-id"] == PROJECT_PUBLIC_ID
    assert sent["fibery/container-type"] == "object"
    assert sent["fibery/container-app"] == {"fibery/id": SPACE_ID}


def test_project_document_sends_no_folder():
    workspace, seen = architecture_workspace()

    workspace.create_project_document(
        ARCHITECTURE_ID, "Architecture", PROJECT_PUBLIC_ID
    )

    assert "fibery/Folder" not in created_view(seen)


def test_project_document_carries_a_generated_secret():
    workspace, seen = architecture_workspace()

    workspace.create_project_document(
        ARCHITECTURE_ID, "Architecture", PROJECT_PUBLIC_ID
    )

    secret = created_view(seen)["fibery/meta"]["documentSecret"]
    assert secret and secret != ARCHITECTURE_ID


def test_project_document_read_back_failure_is_an_error():
    workspace, _ = architecture_workspace(views=[])

    with pytest.raises(FiberyError, match="could not be read back"):
        workspace.create_project_document(
            ARCHITECTURE_ID, "Architecture", PROJECT_PUBLIC_ID
        )


def test_the_project_type_id_is_resolved_from_schema_not_the_database_name():
    workspace, _ = architecture_workspace()

    assert workspace.project_type_id == SCHEMA_TYPE_ID
    assert workspace.project_type_id != "SDLC/Project"
    assert workspace.project_type_id != PROJECT_ENTITY_ID


# ==========================================================================
# create_tsa_child_document
# ==========================================================================


def test_child_document_is_created_at_the_caller_id():
    workspace, seen = architecture_workspace()

    node = workspace.create_tsa_child_document(CHILD_ID, "Manifest", ARCHITECTURE_ID)

    sent = created_view(seen)
    assert sent["fibery/id"] == CHILD_ID
    assert node.id == CHILD_ID


def test_child_document_sends_the_exact_parent():
    workspace, seen = architecture_workspace()

    workspace.create_tsa_child_document(CHILD_ID, "Manifest", ARCHITECTURE_ID)

    sent = created_view(seen)
    assert sent["fibery/parent-page-id"] == ARCHITECTURE_ID
    assert "fibery/container-entity-id" not in sent


def test_child_document_does_not_generate_an_internal_uuid():
    """Every create carries exactly the caller's id, never a fresh uuid4."""
    workspace, seen = architecture_workspace()

    workspace.create_tsa_child_document(CHILD_ID, "Manifest", ARCHITECTURE_ID)

    assert created_view(seen)["fibery/id"] == CHILD_ID


def test_child_document_read_back_failure_is_an_error():
    workspace, _ = architecture_workspace(views=[])

    with pytest.raises(FiberyError, match="could not be read back"):
        workspace.create_tsa_child_document(CHILD_ID, "Manifest", ARCHITECTURE_ID)


# ==========================================================================
# Placement reads
# ==========================================================================


def test_every_placement_field_is_mapped():
    workspace, _ = architecture_workspace(
        views=[document_view(CHILD_ID, "Manifest", parent=ARCHITECTURE_ID)]
    )

    found = workspace.resolve_placement(CHILD_ID)

    assert found == DocumentPlacement(
        document_id=CHILD_ID,
        secret="secret-1",
        name="Manifest",
        container_entity_type=SCHEMA_TYPE_ID,
        container_entity_id=PROJECT_PUBLIC_ID,
        parent_document_id=ARCHITECTURE_ID,
    )


def test_missing_container_fields_stay_none():
    workspace, _ = architecture_workspace(
        views=[
            document_view(
                CHILD_ID, container_type=None, container_entity=None, secret=None
            )
        ]
    )

    found = workspace.resolve_placement(CHILD_ID)

    assert found is not None
    assert found.container_entity_type is None
    assert found.container_entity_id is None
    assert found.secret is None


def test_resolve_placement_returns_none_when_absent():
    workspace, _ = architecture_workspace(views=[])
    assert workspace.resolve_placement(CHILD_ID) is None


def test_project_listing_filters_a_non_document_view():
    workspace, _ = architecture_workspace(
        views=[document_view(ARCHITECTURE_ID, view_type="board")]
    )
    assert workspace.documents_attached_to_project(PROJECT_PUBLIC_ID) == []


def test_project_listing_filters_a_foreign_project():
    workspace, _ = architecture_workspace(
        views=[document_view(ARCHITECTURE_ID, container_entity="999")]
    )
    assert workspace.documents_attached_to_project(PROJECT_PUBLIC_ID) == []


def test_project_listing_filters_a_foreign_database():
    workspace, _ = architecture_workspace(
        views=[document_view(ARCHITECTURE_ID, container_type=REQUIREMENT_TYPE_ID)]
    )
    assert workspace.documents_attached_to_project(PROJECT_PUBLIC_ID) == []


def test_project_listing_returns_the_matching_document():
    workspace, _ = architecture_workspace(views=[document_view(ARCHITECTURE_ID)])

    found = workspace.documents_attached_to_project(PROJECT_PUBLIC_ID)

    assert [item.document_id for item in found] == [ARCHITECTURE_ID]


def test_child_listing_filters_a_different_parent():
    workspace, _ = architecture_workspace(
        views=[document_view(CHILD_ID, parent="other-doc")]
    )
    assert workspace.child_placements(ARCHITECTURE_ID) == []


def test_child_listing_does_not_require_the_childs_own_project_container():
    workspace, _ = architecture_workspace(
        views=[
            document_view(
                CHILD_ID,
                container_type=None,
                container_entity=None,
                parent=ARCHITECTURE_ID,
            )
        ]
    )

    found = workspace.child_placements(ARCHITECTURE_ID)

    assert [item.document_id for item in found] == [CHILD_ID]


def test_project_listing_is_filtered_client_side():
    """The repository primitive is a full listing plus a Python filter."""
    workspace, seen = architecture_workspace(views=[document_view(ARCHITECTURE_ID)])

    workspace.documents_attached_to_project(PROJECT_PUBLIC_ID)

    assert seen["queries"] == [{}]


# ==========================================================================
# Placement predicates
# ==========================================================================


def test_a_valid_root_passes():
    assert is_valid_root_placement(placement(), PROJECT_TYPE_ID, PROJECT_PUBLIC_ID)


@pytest.mark.parametrize(
    ("label", "overrides"),
    [
        ("wrong Project Database", {"container_entity_type": OTHER_DATABASE_TYPE_ID}),
        ("wrong Project public id", {"container_entity_id": "999"}),
        ("root with a parent", {"parent_document_id": ARCHITECTURE_ID}),
        ("unset container type", {"container_entity_type": None}),
        ("unset container id", {"container_entity_id": None}),
        ("empty container type", {"container_entity_type": ""}),
        ("empty container id", {"container_entity_id": ""}),
    ],
)
def test_invalid_roots_fail(label, overrides):
    assert not is_valid_root_placement(
        placement(**overrides), PROJECT_TYPE_ID, PROJECT_PUBLIC_ID
    )


def test_a_child_of_a_valid_root_passes():
    child = placement(
        document_id=CHILD_ID,
        container_entity_type=None,
        container_entity_id=None,
        parent_document_id=ARCHITECTURE_ID,
    )
    assert is_valid_child_placement(
        child, placement(), ARCHITECTURE_ID, PROJECT_TYPE_ID, PROJECT_PUBLIC_ID
    )


def test_a_child_of_a_different_parent_fails():
    child = placement(document_id=CHILD_ID, parent_document_id="other-doc")
    assert not is_valid_child_placement(
        child, placement(), ARCHITECTURE_ID, PROJECT_TYPE_ID, PROJECT_PUBLIC_ID
    )


def test_a_child_whose_root_is_foreign_fails():
    """Ownership runs through the root, so a foreign root fails every child."""
    child = placement(document_id=CHILD_ID, parent_document_id=ARCHITECTURE_ID)
    foreign_root = placement(container_entity_id="999")
    assert not is_valid_child_placement(
        child, foreign_root, ARCHITECTURE_ID, PROJECT_TYPE_ID, PROJECT_PUBLIC_ID
    )


def test_a_child_whose_supplied_root_is_a_different_document_fails():
    child = placement(document_id=CHILD_ID, parent_document_id=ARCHITECTURE_ID)
    other_root = placement(document_id="some-other-root")
    assert not is_valid_child_placement(
        child, other_root, ARCHITECTURE_ID, PROJECT_TYPE_ID, PROJECT_PUBLIC_ID
    )


def test_a_childs_own_project_container_cannot_stand_in_for_the_root():
    """A child carrying the Project container is still judged by its root."""
    child = placement(document_id=CHILD_ID, parent_document_id=ARCHITECTURE_ID)
    foreign_root = placement(container_entity_type=OTHER_DATABASE_TYPE_ID)
    assert is_valid_root_placement(child, PROJECT_TYPE_ID, PROJECT_PUBLIC_ID) is False
    assert not is_valid_child_placement(
        child, foreign_root, ARCHITECTURE_ID, PROJECT_TYPE_ID, PROJECT_PUBLIC_ID
    )


# ==========================================================================
# Existing Requirement / RAW compatibility
# ==========================================================================


def requirement_workspace(views=None):
    return echoing(FiberyRequirementWorkspace, schema=REQUIREMENT_SCHEMA, views=views)


def raw_workspace(views=None):
    return echoing(FiberyRawProcessorWorkspace, schema=REQUIREMENT_SCHEMA, views=views)


def test_create_requirement_document_still_generates_its_own_id():
    workspace, seen = requirement_workspace()

    workspace.create_requirement_document("Root", "42")

    sent = created_view(seen)
    assert sent["fibery/container-entity-id"] == "42"
    assert sent["fibery/container-entity-type"] == {"fibery/id": REQUIREMENT_TYPE_ID}
    assert "fibery/Folder" not in sent
    assert sent["fibery/id"]  # generated internally, not supplied by the caller


def test_create_child_document_still_generates_its_own_id():
    workspace, seen = raw_workspace()

    workspace.create_child_document("Child", "root-doc")

    sent = created_view(seen)
    assert sent["fibery/parent-page-id"] == "root-doc"
    assert sent["fibery/id"] not in ("root-doc", "")


def test_requirement_attachment_listing_is_unchanged():
    workspace, _ = raw_workspace(
        views=[
            document_view(
                "doc-1", container_type=REQUIREMENT_TYPE_ID, container_entity="42"
            ),
            document_view(
                "doc-2", container_type=REQUIREMENT_TYPE_ID, container_entity="99"
            ),
        ]
    )

    found = workspace.documents_attached_to_requirement("42")

    assert [node.id for node in found] == ["doc-1"]


def test_child_documents_behaviour_is_unchanged():
    workspace, _ = raw_workspace(
        views=[
            document_view("doc-1", parent="root-doc"),
            document_view("doc-2", parent="other"),
        ]
    )

    found = workspace.child_documents("root-doc")

    assert [node.id for node in found] == ["doc-1"]


def test_document_node_now_reports_its_parent_truthfully():
    """The field was always declared; the view always carried the value."""
    workspace, _ = raw_workspace(views=[document_view("doc-1", parent="root-doc")])

    node = workspace.resolve_document("doc-1")

    assert node is not None
    assert node.parent_document_id == "root-doc"


def test_a_root_document_still_reports_no_parent():
    workspace, _ = raw_workspace(views=[document_view("doc-1")])

    node = workspace.resolve_document("doc-1")

    assert node is not None
    assert node.parent_document_id is None


# ==========================================================================
# The fake
# ==========================================================================


def fake() -> FakeArchitectureWorkspace:
    return FakeArchitectureWorkspace(
        projects=[project(PROJECT_ENTITY_ID, PROJECT_PUBLIC_ID)]
    )


def test_fake_preserves_caller_supplied_ids():
    workspace = fake()

    root = workspace.create_project_document(
        ARCHITECTURE_ID, "Architecture", PROJECT_PUBLIC_ID
    )
    child = workspace.create_tsa_child_document(CHILD_ID, "Manifest", ARCHITECTURE_ID)

    assert root.id == ARCHITECTURE_ID
    assert child.id == CHILD_ID


def test_fake_project_exposes_a_distinct_public_id():
    record = fake().read_project(PROJECT_ENTITY_ID)
    assert record is not None
    assert record.public_id == PROJECT_PUBLIC_ID
    assert record.public_id != record.id


def test_fake_placement_matches_the_adapter_contract():
    workspace = fake()
    workspace.create_project_document(
        ARCHITECTURE_ID, "Architecture", PROJECT_PUBLIC_ID
    )
    workspace.create_tsa_child_document(CHILD_ID, "Manifest", ARCHITECTURE_ID)

    root = workspace.resolve_placement(ARCHITECTURE_ID)
    child = workspace.resolve_placement(CHILD_ID)

    assert root is not None and child is not None
    assert is_valid_root_placement(root, PROJECT_TYPE_ID, PROJECT_PUBLIC_ID)
    assert child.container_entity_type is None
    assert child.container_entity_id is None
    assert is_valid_child_placement(
        child, root, ARCHITECTURE_ID, PROJECT_TYPE_ID, PROJECT_PUBLIC_ID
    )


def test_fake_listings_match_the_adapter_filters():
    workspace = fake()
    workspace.create_project_document(
        ARCHITECTURE_ID, "Architecture", PROJECT_PUBLIC_ID
    )
    workspace.create_tsa_child_document(CHILD_ID, "Manifest", ARCHITECTURE_ID)
    workspace.place_foreign_document(
        "foreign", container_entity_type=OTHER_DATABASE_TYPE_ID, container_entity_id="7"
    )

    attached = workspace.documents_attached_to_project(PROJECT_PUBLIC_ID)
    children = workspace.child_placements(ARCHITECTURE_ID)

    assert [item.document_id for item in attached] == [ARCHITECTURE_ID]
    assert [item.document_id for item in children] == [CHILD_ID]


def test_fake_refuses_a_second_create_at_the_same_id():
    workspace = fake()
    workspace.create_project_document(
        ARCHITECTURE_ID, "Architecture", PROJECT_PUBLIC_ID
    )

    with pytest.raises(FiberyError, match="already exists"):
        workspace.create_project_document(
            ARCHITECTURE_ID, "Architecture", PROJECT_PUBLIC_ID
        )


def test_fake_read_back_failure_matches_the_adapter():
    workspace = fake()
    workspace.swallow_creates = True

    with pytest.raises(FiberyError, match="could not be read back"):
        workspace.create_project_document(
            ARCHITECTURE_ID, "Architecture", PROJECT_PUBLIC_ID
        )


def test_fake_round_trips_document_content():
    workspace = fake()
    node = workspace.create_project_document(
        ARCHITECTURE_ID, "Architecture", PROJECT_PUBLIC_ID
    )
    assert node.secret is not None

    workspace.write_document_content(node.secret, "# Architecture\n")

    assert workspace.read_document_content(node.secret) == "# Architecture\n"


def test_fake_models_no_cycle_or_manifest_behaviour():
    """It is transport and state only; lifecycle belongs to later work items."""
    forbidden = ("cycle", "manifest", "iteration", "architect", "review", "decision")
    surface = [
        name for name in dir(FakeArchitectureWorkspace) if not name.startswith("_")
    ]
    assert not [name for name in surface if any(f in name.lower() for f in forbidden)]


def test_fake_is_not_richer_than_the_real_adapter():
    """Every public fake method exists on the adapter too."""
    workspace, _ = architecture_workspace()
    extra = {
        name
        for name in dir(FakeArchitectureWorkspace)
        if not name.startswith("_") and not hasattr(workspace, name)
    }
    assert extra <= {
        "place_foreign_document",
        "documents",
        "content",
        "calls",
        "mutations",
        "failures",
        "swallow_creates",
        "projects",
    }


# ==========================================================================
# Identity confusions the adapter must not make
# ==========================================================================


def test_project_entity_id_is_never_sent_as_the_container_entity():
    workspace, seen = architecture_workspace()

    workspace.create_project_document(
        ARCHITECTURE_ID, "Architecture", PROJECT_PUBLIC_ID
    )

    sent = created_view(seen)
    assert sent["fibery/container-entity-id"] != PROJECT_ENTITY_ID


def test_the_database_name_is_never_used_as_the_type_id():
    workspace, seen = architecture_workspace()

    workspace.create_project_document(
        ARCHITECTURE_ID, "Architecture", PROJECT_PUBLIC_ID
    )

    container_type = created_view(seen)["fibery/container-entity-type"]
    assert container_type["fibery/id"] != "SDLC/Project"


def test_a_record_built_without_a_public_id_is_visibly_empty():
    """The default never pretends to be an identity."""
    assert ProjectRecord(id="p", name="n", code="c", state="s").public_id == ""


# ==========================================================================
# H1 — exact-id resolution is type-safe and unambiguous
# ==========================================================================


def board_view(document_id: str = ARCHITECTURE_ID) -> dict:
    return {"fibery/id": document_id, "fibery/name": "Board", "fibery/type": "board"}


def test_a_non_document_at_the_id_is_an_error_not_an_absence():
    workspace, _ = architecture_workspace(views=[board_view()])

    with pytest.raises(FiberyError, match="not a document"):
        workspace.resolve_placement(ARCHITECTURE_ID)


def test_two_identical_documents_at_one_id_are_ambiguous():
    """Identical contents do not make the id unambiguous."""
    view = document_view(ARCHITECTURE_ID)
    workspace, _ = architecture_workspace(views=[view, dict(view)])

    with pytest.raises(FiberyError, match="does not identify one Document"):
        workspace.resolve_placement(ARCHITECTURE_ID)


def test_two_documents_at_one_id_with_different_owners_are_ambiguous():
    workspace, _ = architecture_workspace(
        views=[
            document_view(ARCHITECTURE_ID, container_entity=PROJECT_PUBLIC_ID),
            document_view(ARCHITECTURE_ID, container_entity="999"),
        ]
    )

    with pytest.raises(FiberyError, match="does not identify one Document"):
        workspace.resolve_placement(ARCHITECTURE_ID)


def test_exactly_one_document_resolves():
    workspace, _ = architecture_workspace(views=[document_view(ARCHITECTURE_ID)])

    found = workspace.resolve_placement(ARCHITECTURE_ID)

    assert found is not None
    assert found.document_id == ARCHITECTURE_ID


def test_no_rows_is_a_legitimate_absence():
    workspace, _ = architecture_workspace(views=[])
    assert workspace.resolve_placement(ARCHITECTURE_ID) is None
    assert workspace.resolve_document(ARCHITECTURE_ID) is None


def test_a_row_at_another_id_is_not_adopted():
    workspace, _ = architecture_workspace(views=[document_view("some-other-id")])
    assert workspace.resolve_placement(ARCHITECTURE_ID) is None


def test_resolve_document_is_strict_too():
    workspace, _ = architecture_workspace(views=[board_view()])

    with pytest.raises(FiberyError, match="not a document"):
        workspace.resolve_document(ARCHITECTURE_ID)


@pytest.mark.parametrize(
    ("label", "views", "message"),
    [
        ("no row", [], "could not be read back"),
        ("wrong type", [board_view()], "not a document"),
        (
            "ambiguous",
            [document_view(ARCHITECTURE_ID), document_view(ARCHITECTURE_ID)],
            "does not identify one Document",
        ),
    ],
)
def test_project_document_read_back_refuses(label, views, message):
    workspace, _ = architecture_workspace(views=views)

    with pytest.raises(FiberyError, match=message):
        workspace.create_project_document(
            ARCHITECTURE_ID, "Architecture", PROJECT_PUBLIC_ID
        )


@pytest.mark.parametrize(
    ("label", "views", "message"),
    [
        ("no row", [], "could not be read back"),
        ("wrong type", [board_view(CHILD_ID)], "not a document"),
        (
            "ambiguous",
            [document_view(CHILD_ID), document_view(CHILD_ID)],
            "does not identify one Document",
        ),
    ],
)
def test_child_document_read_back_refuses(label, views, message):
    workspace, _ = architecture_workspace(views=views)

    with pytest.raises(FiberyError, match=message):
        workspace.create_tsa_child_document(CHILD_ID, "Manifest", ARCHITECTURE_ID)


def test_legacy_resolve_document_semantics_are_untouched():
    """The Requirement adapter keeps its first-match behaviour."""
    workspace, _ = raw_workspace(views=[board_view("doc-1")])

    node = workspace.resolve_document("doc-1")

    assert node is not None and node.name == "Board"


# ==========================================================================
# M1 — the full frozen surface, with the two creators distinct
# ==========================================================================


def test_the_adapter_exposes_the_legacy_child_creator():
    workspace, seen = architecture_workspace()

    workspace.create_child_document("Child", ARCHITECTURE_ID)

    sent = created_view(seen)
    assert sent["fibery/parent-page-id"] == ARCHITECTURE_ID
    assert sent["fibery/id"] not in (ARCHITECTURE_ID, CHILD_ID, "")
    assert "fibery/container-entity-id" not in sent
    assert sent["fibery/meta"]["documentSecret"]


def test_the_two_child_creators_stay_distinct():
    """One generates its id, the other is handed one."""
    workspace, seen = architecture_workspace()
    workspace.create_child_document("Legacy", ARCHITECTURE_ID)
    generated = created_view(seen)["fibery/id"]

    workspace, seen = architecture_workspace()
    workspace.create_tsa_child_document(CHILD_ID, "Deterministic", ARCHITECTURE_ID)

    assert generated != CHILD_ID
    assert created_view(seen)["fibery/id"] == CHILD_ID


def test_the_adapter_lists_child_documents_as_nodes():
    workspace, _ = architecture_workspace(
        views=[
            document_view(CHILD_ID, parent=ARCHITECTURE_ID),
            document_view("other", parent="elsewhere"),
        ]
    )

    found = workspace.child_documents(ARCHITECTURE_ID)

    assert [node.id for node in found] == [CHILD_ID]
    assert found[0].parent_document_id == ARCHITECTURE_ID


def test_child_documents_and_child_placements_agree_on_membership():
    workspace, _ = architecture_workspace(
        views=[document_view(CHILD_ID, parent=ARCHITECTURE_ID)]
    )
    nodes = workspace.child_documents(ARCHITECTURE_ID)

    workspace, _ = architecture_workspace(
        views=[document_view(CHILD_ID, parent=ARCHITECTURE_ID)]
    )
    placements = workspace.child_placements(ARCHITECTURE_ID)

    assert [node.id for node in nodes] == [item.document_id for item in placements]


def test_the_fake_exposes_the_full_surface_too():
    workspace = fake()
    workspace.create_project_document(
        ARCHITECTURE_ID, "Architecture", PROJECT_PUBLIC_ID
    )

    legacy = workspace.create_child_document("Legacy", ARCHITECTURE_ID)
    deterministic = workspace.create_tsa_child_document(
        CHILD_ID, "Manifest", ARCHITECTURE_ID
    )

    assert legacy.id != CHILD_ID
    assert deterministic.id == CHILD_ID
    assert {node.id for node in workspace.child_documents(ARCHITECTURE_ID)} == {
        legacy.id,
        CHILD_ID,
    }


# ==========================================================================
# M2 — controlled failures in the new schema and placement paths
# ==========================================================================


def schema_without_type_id(value=...):
    import copy

    schema = copy.deepcopy(PROJECT_SCHEMA)
    if value is ...:
        schema["fibery/types"][0].pop("fibery/id")
    else:
        schema["fibery/types"][0]["fibery/id"] = value
    return schema


@pytest.mark.parametrize("value", [..., None, "", "   ", 7])
def test_an_unusable_project_type_id_is_refused(value):
    workspace, _ = architecture_workspace(schema=schema_without_type_id(value))

    with pytest.raises(FiberyError, match="no usable fibery/id"):
        assert workspace.project_type_id


def test_a_valid_project_type_id_resolves():
    workspace, _ = architecture_workspace()
    assert workspace.project_type_id == SCHEMA_TYPE_ID


def test_no_create_is_attempted_without_a_usable_project_type_id():
    workspace, seen = architecture_workspace(schema=schema_without_type_id())

    with pytest.raises(FiberyError, match="no usable fibery/id"):
        workspace.create_project_document(
            ARCHITECTURE_ID, "Architecture", PROJECT_PUBLIC_ID
        )

    assert "view" not in seen


MALFORMED_VIEWS = [
    (
        "meta is a string",
        {"fibery/id": "d1", "fibery/type": "document", "fibery/meta": "x"},
    ),
    (
        "meta is a list",
        {"fibery/id": "d1", "fibery/type": "document", "fibery/meta": [1]},
    ),
    (
        "container type is a string",
        {
            "fibery/id": "d1",
            "fibery/type": "document",
            "fibery/container-entity-type": "x",
        },
    ),
    (
        "container type id is not scalar",
        {
            "fibery/id": "d1",
            "fibery/type": "document",
            "fibery/container-entity-type": {"fibery/id": ["x"]},
        },
    ),
    (
        "container entity id is structured",
        {
            "fibery/id": "d1",
            "fibery/type": "document",
            "fibery/container-entity-id": {"fibery/id": "7"},
        },
    ),
    (
        "parent page id is structured",
        {
            "fibery/id": "d1",
            "fibery/type": "document",
            "fibery/parent-page-id": {"fibery/id": "p"},
        },
    ),
    (
        "secret is not scalar",
        {
            "fibery/id": "d1",
            "fibery/type": "document",
            "fibery/meta": {"documentSecret": ["s"]},
        },
    ),
    (
        "name is not scalar",
        {"fibery/id": "d1", "fibery/type": "document", "fibery/name": 7},
    ),
    ("id is missing", {"fibery/type": "document"}),
    ("id is None", {"fibery/id": None, "fibery/type": "document"}),
    ("id is empty", {"fibery/id": "", "fibery/type": "document"}),
    ("id is not scalar", {"fibery/id": ["d1"], "fibery/type": "document"}),
]


@pytest.mark.parametrize(("label", "view"), MALFORMED_VIEWS)
def test_malformed_placement_views_are_refused(label, view):
    from sdlc.fibery_http import _to_document_placement

    with pytest.raises(FiberyError):
        _to_document_placement(view)


def test_a_malformed_row_at_an_exact_id_is_refused_through_the_adapter():
    workspace, _ = architecture_workspace(
        views=[
            {
                "fibery/id": ARCHITECTURE_ID,
                "fibery/type": "document",
                "fibery/meta": "x",
            }
        ]
    )

    with pytest.raises(FiberyError, match="fibery/meta"):
        workspace.resolve_placement(ARCHITECTURE_ID)


def test_absent_optional_placement_metadata_is_still_none():
    """Controlled parsing must not start inventing values."""
    from sdlc.fibery_http import _to_document_placement

    found = _to_document_placement({"fibery/id": "d1", "fibery/type": "document"})

    assert found.secret is None
    assert found.container_entity_type is None
    assert found.container_entity_id is None
    assert found.parent_document_id is None
    assert found.name == ""


def test_a_container_type_object_without_an_id_stays_none():
    from sdlc.fibery_http import _to_document_placement

    found = _to_document_placement(
        {
            "fibery/id": "d1",
            "fibery/type": "document",
            "fibery/container-entity-type": {},
        }
    )

    assert found.container_entity_type is None


# ==========================================================================
# The fake's duplicate-id behaviour is an assumption, not evidence
# ==========================================================================


def test_fake_duplicate_id_behaviour_is_labelled_provisional():
    import inspect

    import architecture_fake

    source = inspect.getsource(architecture_fake)
    assert "PROVISIONAL ASSUMPTION, pending P-1" in source
    # The claim is a wrapped comment block, so strip the markers and the line
    # breaks before asserting on it.
    flattened = " ".join(source.replace("#", " ").split())
    assert (
        "Nothing here is evidence that the live Views API behaves this way" in flattened
    )
    assert "BEFORE the capability is recorded as verified" in flattened


# ==========================================================================
# M2 — no malformed Views response reaches a caller as a raw exception
# ==========================================================================

MALFORMED_FIELDS = [
    ("meta is a string", {"fibery/meta": "x"}),
    ("meta is a list", {"fibery/meta": ["x"]}),
    ("secret is not scalar", {"fibery/meta": {"documentSecret": ["s"]}}),
    ("container entity type is a string", {"fibery/container-entity-type": "x"}),
    (
        "container entity type id is not scalar",
        {"fibery/container-entity-type": {"fibery/id": ["x"]}},
    ),
    ("container entity id is structured", {"fibery/container-entity-id": {"a": 1}}),
    ("parent page id is structured", {"fibery/parent-page-id": {"a": 1}}),
    ("folder is a string", {"fibery/Folder": "x"}),
    ("name is not scalar", {"fibery/name": 7}),
]


@pytest.mark.parametrize(("label", "corruption"), MALFORMED_FIELDS)
def test_resolve_document_refuses_a_malformed_row(label, corruption):
    workspace, _ = architecture_workspace(
        views=[{**document_view(ARCHITECTURE_ID), **corruption}]
    )

    with pytest.raises(FiberyError):
        workspace.resolve_document(ARCHITECTURE_ID)


@pytest.mark.parametrize(("label", "corruption"), MALFORMED_FIELDS)
def test_resolve_placement_refuses_a_malformed_row(label, corruption):
    workspace, _ = architecture_workspace(
        views=[{**document_view(ARCHITECTURE_ID), **corruption}]
    )

    with pytest.raises(FiberyError):
        workspace.resolve_placement(ARCHITECTURE_ID)


def test_project_document_refuses_a_malformed_read_back():
    workspace, _ = malformed_read_back(**{"fibery/meta": "x"})

    with pytest.raises(FiberyError, match="fibery/meta"):
        workspace.create_project_document(
            ARCHITECTURE_ID, "Architecture", PROJECT_PUBLIC_ID
        )


def test_tsa_child_document_refuses_a_malformed_read_back():
    workspace, _ = malformed_read_back(**{"fibery/meta": "x"})

    with pytest.raises(FiberyError, match="fibery/meta"):
        workspace.create_tsa_child_document(CHILD_ID, "Manifest", ARCHITECTURE_ID)


def test_legacy_child_document_refuses_a_malformed_read_back():
    workspace, _ = malformed_read_back(**{"fibery/meta": "x"})

    with pytest.raises(FiberyError, match="fibery/meta"):
        workspace.create_child_document("Child", ARCHITECTURE_ID)


def test_child_documents_refuses_a_malformed_candidate():
    workspace, _ = architecture_workspace(
        views=[document_view(CHILD_ID, parent=ARCHITECTURE_ID) | {"fibery/meta": "x"}]
    )

    with pytest.raises(FiberyError, match="fibery/meta"):
        workspace.child_documents(ARCHITECTURE_ID)


def test_child_documents_refuses_a_malformed_parent_shape():
    """A malformed parent is a refusal, never silently filtered out."""
    workspace, _ = architecture_workspace(
        views=[document_view(CHILD_ID) | {"fibery/parent-page-id": {"a": 1}}]
    )

    with pytest.raises(FiberyError, match="parent-page-id"):
        workspace.child_documents(ARCHITECTURE_ID)


def test_child_documents_returns_a_valid_child():
    workspace, _ = architecture_workspace(
        views=[document_view(CHILD_ID, parent=ARCHITECTURE_ID)]
    )

    assert [node.id for node in workspace.child_documents(ARCHITECTURE_ID)] == [
        CHILD_ID
    ]


def test_project_listing_refuses_a_malformed_container_type():
    workspace, _ = architecture_workspace(
        views=[document_view(ARCHITECTURE_ID) | {"fibery/container-entity-type": "x"}]
    )

    with pytest.raises(FiberyError, match="container-entity-type"):
        workspace.documents_attached_to_project(PROJECT_PUBLIC_ID)


def test_project_listing_refuses_a_malformed_meta():
    workspace, _ = architecture_workspace(
        views=[document_view(ARCHITECTURE_ID) | {"fibery/meta": "x"}]
    )

    with pytest.raises(FiberyError, match="fibery/meta"):
        workspace.documents_attached_to_project(PROJECT_PUBLIC_ID)


def test_project_listing_still_filters_a_valid_foreign_project():
    workspace, _ = architecture_workspace(
        views=[document_view(ARCHITECTURE_ID, container_entity="999")]
    )
    assert workspace.documents_attached_to_project(PROJECT_PUBLIC_ID) == []


def test_project_listing_still_filters_a_valid_foreign_type():
    workspace, _ = architecture_workspace(
        views=[document_view(ARCHITECTURE_ID, container_type=REQUIREMENT_TYPE_ID)]
    )
    assert workspace.documents_attached_to_project(PROJECT_PUBLIC_ID) == []


def test_child_placements_refuses_a_malformed_candidate():
    workspace, _ = architecture_workspace(
        views=[document_view(CHILD_ID) | {"fibery/parent-page-id": {"a": 1}}]
    )

    with pytest.raises(FiberyError, match="parent-page-id"):
        workspace.child_placements(ARCHITECTURE_ID)


def test_child_placements_still_filters_a_valid_other_parent():
    workspace, _ = architecture_workspace(
        views=[document_view(CHILD_ID, parent="elsewhere")]
    )
    assert workspace.child_placements(ARCHITECTURE_ID) == []


def test_a_non_list_views_response_is_refused():
    workspace, _ = architecture_workspace(views={"not": "a list"})

    with pytest.raises(FiberyError, match="a list"):
        workspace.documents_attached_to_project(PROJECT_PUBLIC_ID)


def test_the_tsa_document_converter_is_separate_from_the_legacy_one():
    """Two converters: the TSA one validates, the legacy one is untouched.

    The legacy converter is deliberately NOT hardened — its frozen Requirement
    and RAW callers keep exactly the behaviour they were reviewed with — so it
    is only exercised here on a well-formed view.
    """
    from sdlc.fibery_http import _to_document, _to_tsa_document

    assert _to_document is not _to_tsa_document

    well_formed = {
        "fibery/id": "d1",
        "fibery/name": "A",
        "fibery/meta": {"documentSecret": "s"},
        "fibery/parent-page-id": "root",
    }
    assert _to_document(well_formed) == _to_tsa_document(well_formed)

    with pytest.raises(FiberyError):
        _to_tsa_document({"fibery/id": "d1", "fibery/meta": "x"})


def test_legacy_requirement_paths_are_not_hardened():
    """A malformed row still flows through the Requirement adapter unchanged."""
    workspace, _ = raw_workspace(
        views=[{"fibery/id": "doc-1", "fibery/type": "document", "fibery/name": "A"}]
    )

    node = workspace.resolve_document("doc-1")

    assert node is not None and node.name == "A"


# ==========================================================================
# M2 — the exact-id response itself is validated before anything is classified
# ==========================================================================

#: `None` is the established adapter reading of "no rows": `views_rpc` returns
#: `response["result"]`, which is absent on an empty JSON-RPC envelope, and
#: every listing in the module already reads it as empty.
EMPTY_RESPONSES = [("result is None", None), ("result is an empty list", [])]

MALFORMED_RESPONSES = [
    ("result is an object", {}),
    ("result is a populated object", {"fibery/id": ARCHITECTURE_ID}),
    ("result is a string", "x"),
    ("result is an integer", 7),
    ("a row is None", [None]),
    ("a row is a list", [[]]),
    ("a row is an integer", [7]),
    ("a row is a string", ["x"]),
    ("a row has no id", [{"fibery/type": "document"}]),
    ("a row id is None", [{"fibery/id": None, "fibery/type": "document"}]),
    ("a row id is empty", [{"fibery/id": "", "fibery/type": "document"}]),
    ("a row id is whitespace", [{"fibery/id": "   ", "fibery/type": "document"}]),
    ("a row id is not a string", [{"fibery/id": ["x"], "fibery/type": "document"}]),
]


@pytest.mark.parametrize(("label", "response"), EMPTY_RESPONSES)
def test_an_empty_response_is_a_genuine_absence(label, response):
    workspace, _ = architecture_workspace(views=response)

    assert workspace.resolve_document(ARCHITECTURE_ID) is None
    assert workspace.resolve_placement(ARCHITECTURE_ID) is None


@pytest.mark.parametrize(("label", "response"), MALFORMED_RESPONSES)
def test_resolve_document_refuses_a_malformed_response(label, response):
    workspace, _ = architecture_workspace(views=response)

    with pytest.raises(FiberyError):
        workspace.resolve_document(ARCHITECTURE_ID)


@pytest.mark.parametrize(("label", "response"), MALFORMED_RESPONSES)
def test_resolve_placement_refuses_a_malformed_response(label, response):
    workspace, _ = architecture_workspace(views=response)

    with pytest.raises(FiberyError):
        workspace.resolve_placement(ARCHITECTURE_ID)


def test_a_malformed_row_is_never_read_as_a_different_document():
    """A broken row must not become an absence: absence authorises a create."""
    workspace, _ = architecture_workspace(views=[{"fibery/type": "document"}])

    with pytest.raises(FiberyError, match="without a usable fibery/id"):
        workspace.resolve_document(ARCHITECTURE_ID)


def test_a_valid_row_at_another_id_is_still_a_genuine_absence():
    workspace, _ = architecture_workspace(views=[document_view("some-other-id")])

    assert workspace.resolve_document(ARCHITECTURE_ID) is None
    assert workspace.resolve_placement(ARCHITECTURE_ID) is None


def test_one_valid_exact_document_still_resolves():
    workspace, _ = architecture_workspace(views=[document_view(ARCHITECTURE_ID)])

    assert workspace.resolve_document(ARCHITECTURE_ID) is not None
    assert workspace.resolve_placement(ARCHITECTURE_ID) is not None


CREATE_CALLS = [
    (
        "create_project_document",
        lambda w: w.create_project_document(
            ARCHITECTURE_ID, "Architecture", PROJECT_PUBLIC_ID
        ),
    ),
    (
        "create_tsa_child_document",
        lambda w: w.create_tsa_child_document(CHILD_ID, "Manifest", ARCHITECTURE_ID),
    ),
    (
        "create_child_document",
        lambda w: w.create_child_document("Child", ARCHITECTURE_ID),
    ),
]

REPRESENTATIVE_MALFORMED = [
    ("result is an object", {}),
    ("result is a string", "x"),
    ("a row is None", [None]),
    ("a row has no id", [{"fibery/type": "document"}]),
]


@pytest.mark.parametrize(("creator", "call"), CREATE_CALLS)
@pytest.mark.parametrize(("label", "response"), REPRESENTATIVE_MALFORMED)
def test_creators_refuse_a_malformed_read_back_response(creator, call, label, response):
    workspace, seen = architecture_workspace(views=response)

    with pytest.raises(FiberyError):
        call(workspace)

    # The mutation really was attempted: the refusal is a read-back failure, so
    # a caller is told the durable state is unknown rather than told it worked.
    assert "view" in seen


@pytest.mark.parametrize(("creator", "call"), CREATE_CALLS)
def test_creators_refuse_an_empty_read_back(creator, call):
    workspace, seen = architecture_workspace(views=[])

    with pytest.raises(FiberyError, match="could not be read back"):
        call(workspace)

    assert "view" in seen


def test_listings_refuse_a_malformed_response_too():
    """The listing path shares the same response guard."""
    for response in ({}, "x", [None], [7]):
        workspace, _ = architecture_workspace(views=response)
        with pytest.raises(FiberyError):
            workspace.documents_attached_to_project(PROJECT_PUBLIC_ID)


def test_listings_treat_an_empty_response_as_empty():
    for response in (None, []):
        workspace, _ = architecture_workspace(views=response)
        assert workspace.documents_attached_to_project(PROJECT_PUBLIC_ID) == []
        assert workspace.child_placements(ARCHITECTURE_ID) == []
        assert workspace.child_documents(ARCHITECTURE_ID) == []


def test_the_exact_id_helper_does_not_reimplement_field_parsing():
    """It validates only what classification needs; parsing stays in one place."""
    import inspect

    from sdlc.fibery_http import FiberyArchitectureWorkspace

    source = inspect.getsource(FiberyArchitectureWorkspace._exact_document_view)
    assert "DocumentPlacement(" not in source
    assert "DocumentNode(" not in source
    assert "DOCUMENT_SECRET_META_KEY" not in source
