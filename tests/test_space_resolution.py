"""Resolving the configured Space's UUID from the workspace itself.

`FIBERY_SPACE_ID` is no longer configuration. The Space id that Documents are
created in, and that scopes the worker lock, is read from the `fibery/app`
Database by the Space name the operator did configure.

The lookup shape here is the one confirmed read-only against a live workspace
on 2026-09-26. Everything in this module runs against a fake transport.
"""

from __future__ import annotations

import email.message
import io
import json
import urllib.error

import pytest

from raw_fixtures import VALID_SOURCE
from sdlc import cli
from sdlc.config import ENV_HOST, ENV_SPACE, ENV_TOKEN, ConfigurationError
from sdlc.fibery_client import FiberyClient
from sdlc.fibery_http import FiberyRawProcessorWorkspace
from test_fibery_http import (
    SETTINGS,
    SPACE_ID,
    SPACE_ROWS,
    StubOpener,
    StubResponse,
    ok,
    unpaced,
)

ENVIRONMENT = {
    ENV_HOST: "example.fibery.io",
    ENV_TOKEN: "test-token",
    ENV_SPACE: "SDLC",
}
OBSOLETE_SPACE_ID_VARIABLE = "FIBERY_SPACE_ID"
FIBERY_VARIABLES = (*ENVIRONMENT, "FIBERY_TIMEOUT_SECONDS", OBSOLETE_SPACE_ID_VARIABLE)


def client_over(payloads):
    opener = StubOpener(payloads)
    return FiberyClient(SETTINGS, url_opener=opener, **unpaced()), opener


# -- the lookup itself -----------------------------------------------------


def test_the_configured_space_is_matched_by_name_among_many():
    client, _ = client_over([ok(SPACE_ROWS)])

    assert client.resolve_space_id() == SPACE_ID


def test_the_query_is_the_confirmed_one():
    """The shape verified read-only against a live workspace; not a variant."""
    client, opener = client_over([ok(SPACE_ROWS)])

    client.resolve_space_id()

    [sent] = [request["body"][0] for request in opener.requests]
    assert sent == {
        "command": "fibery.entity/query",
        "args": {
            "query": {
                "q/from": "fibery/app",
                "q/select": ["fibery/id", "fibery/name"],
                "q/limit": "q/no-limit",
            }
        },
    }


@pytest.mark.parametrize(
    "name",
    ["sdlc", "SDLC ", " SDLC", "SDLC2", "SDL", "SDLC/Requirement"],
    ids=["lowercase", "trailing", "leading", "longer", "prefix", "qualified"],
)
def test_only_an_exact_name_matches(name):
    """A near miss is a different Space; nothing is guessed from a resemblance."""
    client, _ = client_over([ok([{"fibery/id": SPACE_ID, "fibery/name": name}])])

    with pytest.raises(ConfigurationError, match="names 0 of"):
        client.resolve_space_id()


def test_a_workspace_without_the_space_is_refused():
    client, _ = client_over([ok([{"fibery/id": SPACE_ID, "fibery/name": "Other"}])])

    with pytest.raises(ConfigurationError, match=r"FIBERY_SPACE='SDLC' names 0 of"):
        client.resolve_space_id()


def test_two_spaces_of_the_same_name_are_refused():
    """Ambiguity is a refusal: picking one would place Documents at random."""
    rows = [
        {"fibery/id": SPACE_ID, "fibery/name": "SDLC"},
        {"fibery/id": "22222222-3333-4444-8555-666666666666", "fibery/name": "SDLC"},
    ]
    client, _ = client_over([ok(rows)])

    with pytest.raises(ConfigurationError, match="names 2 of"):
        client.resolve_space_id()


@pytest.mark.parametrize(
    "value",
    ["", "not-a-uuid", "19c62a00-7a47-11f1-aba7", SPACE_ID + "-extra"],
    ids=["empty", "text", "truncated", "overlong"],
)
def test_an_id_that_is_not_a_uuid_is_refused(value):
    client, _ = client_over([ok([{"fibery/id": value, "fibery/name": "SDLC"}])])

    with pytest.raises(ConfigurationError, match="is not a UUID"):
        client.resolve_space_id()


@pytest.mark.parametrize(
    ("rows", "expected"),
    [
        ({"spaces": []}, "no list of Spaces"),
        ([{"fibery/name": "SDLC"}], "carries no id"),
        ([{"fibery/id": None, "fibery/name": "SDLC"}], "carries no id"),
        (["SDLC"], "names 0 of"),
    ],
    ids=["not-a-list", "no-id-key", "null-id", "not-objects"],
)
def test_a_malformed_answer_is_refused(rows, expected):
    client, _ = client_over([ok(rows)])

    with pytest.raises(ConfigurationError, match=expected):
        client.resolve_space_id()


def test_an_api_failure_is_reported_without_the_response():
    """The refusal names the endpoint and status, never the body or the token."""
    body = b"{'error': 'token sk-test-token is not authorised for space SDLC'}"
    failure = urllib.error.HTTPError(
        "https://example.fibery.io/api/commands",
        500,
        "err",
        email.message.Message(),
        io.BytesIO(body),
    )

    def refusing(request, timeout):
        raise failure

    client = FiberyClient(SETTINGS, url_opener=refusing, **unpaced())

    with pytest.raises(ConfigurationError) as raised:
        client.resolve_space_id()

    message = str(raised.value)
    assert "Could not read this workspace's Spaces" in message
    assert "HTTP 500" in message
    assert SETTINGS.token not in message
    assert "not authorised" not in message


def test_the_lookup_happens_once_per_client():
    """One invocation pays for one lookup, whatever it goes on to write."""
    client, opener = client_over([ok(SPACE_ROWS)])

    first, second, third = (client.resolve_space_id() for _ in range(3))

    assert first == second == third == SPACE_ID
    assert len(opener.requests) == 1


def test_the_client_and_its_adapters_read_one_resolved_id():
    client, _ = client_over([ok(SPACE_ROWS)])
    client.resolve_space_id()
    workspace = FiberyRawProcessorWorkspace(client, "SDLC")

    assert client.space_id == SPACE_ID
    assert workspace.lock_scope == f"example.fibery.io/{SPACE_ID}"
    assert client.workspace_identity == f"example.fibery.io/{SPACE_ID}"


# -- the command that needs it ---------------------------------------------

REQUIREMENT_TYPE_ID = "0cbb35c1-b71f-4429-b45e-4a9fd5ada7c2"
SCHEMA = {
    "fibery/types": [
        {
            "fibery/name": "SDLC/Project",
            "fibery/fields": [
                {"fibery/name": "SDLC/Name", "fibery/type": "fibery/text"},
                {"fibery/name": "SDLC/Code", "fibery/type": "fibery/text"},
                {
                    "fibery/name": "workflow/state",
                    "fibery/type": "workflow/state_SDLC/Project",
                },
            ],
        },
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
        },
    ]
}
PROJECT_ROW = {
    "fibery/id": "project-1",
    "fibery/public-id": "1",
    "SDLC/Name": "SDLC",
    "SDLC/Code": "SDLC",
    "workflow/state": {"enum/name": "Planned"},
}


class RequirementStandIn:
    """Answers the whole `requirement add` flow from memory, over HTTP shapes.

    It exists to run the real CLI — real configuration, real resolution, real
    adapter — without a network. Only the transport is fake.
    """

    def __init__(self, spaces=None):
        self.spaces = SPACE_ROWS if spaces is None else spaces
        self.requirements = {}
        self.views = {}
        self.documents = {}
        self.commands = []
        self.next_id = 1

    # -- the queue of shapes the adapters speak ---------------------------

    def __call__(self, request, timeout):
        if "/api/documents/" in request.full_url:
            return self._document(request)
        body = json.loads(request.data.decode("utf-8"))
        if request.full_url.endswith("/api/commands"):
            payload = [{"success": True, "result": self._command(body[0])}]
        else:
            payload = {"jsonrpc": "2.0", "id": 1, "result": self._view(body)}
        return StubResponse(json.dumps(payload).encode("utf-8"))

    def _document(self, request):
        secret = request.full_url.rsplit("/", 1)[-1].split("?")[0]
        if request.data is None:
            return StubResponse(
                json.dumps({"content": self.documents.get(secret, "")}).encode()
            )
        self.documents[secret] = json.loads(request.data.decode("utf-8"))["content"]
        return StubResponse(b"{}")

    def _command(self, envelope):
        name, args = envelope["command"], envelope.get("args", {})
        self.commands.append((name, args.get("query", {}).get("q/from")))
        if name == "fibery.schema/query":
            return SCHEMA
        if name == "fibery.entity/query":
            return self._query(args["query"], args.get("params", {}))
        if name == "fibery.entity/create":
            return self._create(args)
        if name == "fibery.entity/update":
            return self._update(args)
        raise AssertionError(f"Unexpected command {name}")

    def _query(self, query, params):
        database = query["q/from"]
        if database == "fibery/app":
            return self.spaces
        if database.startswith(("workflow/state", "SDLC/Type_")):
            return [{"fibery/id": f"option-{params['$name']}"}]
        if database == "SDLC/Project":
            return [PROJECT_ROW]
        if database == "SDLC/Requirement":
            wanted = params.get("$id")
            rows = list(self.requirements.values())
            return [row for row in rows if row["fibery/id"] == wanted] if wanted else []
        raise AssertionError(f"Unexpected Database {database}")

    def _create(self, args):
        entity_id = f"requirement-{self.next_id}"
        self.next_id += 1
        self.requirements[entity_id] = {
            "fibery/id": entity_id,
            "fibery/public-id": str(self.next_id),
            **args["entity"],
        }
        return {"fibery/id": entity_id}

    def _update(self, args):
        """Enum writes come back as Fibery reads them: by option name."""
        entity = dict(args["entity"])
        record = self.requirements[entity.pop("fibery/id")]
        for field, value in entity.items():
            option = value.get("fibery/id") if isinstance(value, dict) else None
            record[field] = (
                {"enum/name": option.removeprefix("option-")}
                if isinstance(option, str) and option.startswith("option-")
                else value
            )
        return {"fibery/id": record["fibery/id"]}

    def _view(self, body):
        method, params = body["method"], body.get("params", {})
        if method == "create-views":
            view = params["views"][0]
            self.views[view["fibery/id"]] = view
            return []
        if method == "query-views":
            wanted = params.get("filter", {}).get("ids")
            views = list(self.views.values())
            return [v for v in views if wanted is None or v["fibery/id"] in wanted]
        raise AssertionError(f"Unexpected views method {method}")

    # -- what the assertions ask -----------------------------------------

    @property
    def space_lookups(self):
        return [database for _, database in self.commands if database == "fibery/app"]

    @property
    def mutations(self):
        return [name for name, _ in self.commands if name != "fibery.schema/query"]


def add_requirement(monkeypatch, tmp_path, stand_in, environment=None):
    """Run the real `sdlc project requirement add` over the fake transport."""
    for name in FIBERY_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    for name, value in (environment or ENVIRONMENT).items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(
        cli,
        "FiberyClient",
        lambda settings: FiberyClient(
            settings, url_opener=stand_in, clock=lambda: 0.0, sleeper=lambda s: None
        ),
    )
    source = tmp_path / "raw-requirements.md"
    source.write_text(VALID_SOURCE, encoding="utf-8")
    arguments = cli.build_parser().parse_args(
        ["project", "requirement", "add", "--project", "SDLC", "--source", str(source)]
    )
    out, error_out = io.StringIO(), io.StringIO()
    code = arguments.handler(arguments, out, error_out)
    return code, out.getvalue(), error_out.getvalue()


def test_requirement_add_runs_without_a_configured_space_id(monkeypatch, tmp_path):
    """CLI -> real configuration -> real resolution -> adapter, end to end.

    Nothing here is stubbed above the transport: `load_fibery_settings` and
    `resolve_space_id` both really run.
    """
    stand_in = RequirementStandIn()

    code, out, error_out = add_requirement(monkeypatch, tmp_path, stand_in)

    assert (code, error_out) == (cli.EXIT_SUCCESS, "")
    assert out.splitlines()[0] == "RAW_REQUIREMENT_ADDED"
    assert len(stand_in.space_lookups) == 1


def test_the_created_document_lands_in_the_resolved_space(monkeypatch, tmp_path):
    stand_in = RequirementStandIn()

    add_requirement(monkeypatch, tmp_path, stand_in)

    [view] = stand_in.views.values()
    assert view["fibery/container-app"] == {"fibery/id": SPACE_ID}
    assert view["fibery/container-type"] == "object"


def test_a_stale_space_id_variable_does_not_steer_the_run(monkeypatch, tmp_path):
    """An old shell or .env may still export it; it is not read."""
    stand_in = RequirementStandIn()
    stale = {**ENVIRONMENT, OBSOLETE_SPACE_ID_VARIABLE: "deadbeef-dead-4dead-8dead"}

    code, _, _ = add_requirement(monkeypatch, tmp_path, stand_in, environment=stale)

    [view] = stand_in.views.values()
    assert code == cli.EXIT_SUCCESS
    assert view["fibery/container-app"] == {"fibery/id": SPACE_ID}


def test_an_unresolvable_space_mutates_nothing(monkeypatch, tmp_path):
    """Resolution precedes the first write, so a refusal leaves no Requirement."""
    stand_in = RequirementStandIn(spaces=[{"fibery/id": SPACE_ID, "fibery/name": "X"}])

    code, _, error_out = add_requirement(monkeypatch, tmp_path, stand_in)

    assert code == cli.EXIT_FAILURE
    assert "names 0 of" in error_out
    assert stand_in.mutations == ["fibery.entity/query"], "the lookup and nothing else"
    assert stand_in.requirements == {} and stand_in.views == {}


def test_the_runner_resolves_once_for_its_whole_life(monkeypatch):
    """No poll cycle and no Document pays for the lookup a second time."""
    stand_in = RequirementStandIn()
    for name in FIBERY_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    for name, value in ENVIRONMENT.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(
        cli,
        "FiberyClient",
        lambda settings: FiberyClient(
            settings, url_opener=stand_in, clock=lambda: 0.0, sleeper=lambda s: None
        ),
    )

    workspace = cli._runner_workspace(cli.load_fibery_settings())
    scopes = [workspace.lock_scope for _ in range(3)]
    for cycle in range(3):
        workspace.create_child_document(f"Processing Result {cycle}", "parent-doc")

    assert stand_in.space_lookups == ["fibery/app"], "one lookup for the runner"
    assert set(scopes) == {f"example.fibery.io/{SPACE_ID}"}
    assert len(stand_in.views) == 3
    assert {
        view["fibery/container-app"]["fibery/id"] for view in stand_in.views.values()
    } == {SPACE_ID}
