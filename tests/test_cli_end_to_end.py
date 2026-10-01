"""End-to-end `sdlc project init` against an in-process stand-in for Fibery."""

import json

import pytest

from sdlc import cli
from sdlc.config import ENV_HOST, ENV_SPACE, ENV_TIMEOUT_SECONDS, ENV_TOKEN
from sdlc.fibery_client import FiberyClient
from test_fibery_http import PROJECT_SCHEMA, StubResponse

# The whole configuration: Database names are qualified by Space name, and the
# command creates no Document and no View, so it resolves no Space UUID.
REQUIRED_ENVIRONMENT = {
    ENV_HOST: "example.fibery.io",
    ENV_TOKEN: "test-token",
    ENV_SPACE: "SDLC",
}
# Retired configuration, exported by some shells and .env files still.
OBSOLETE_SPACE_ID_VARIABLE = "FIBERY_SPACE_ID"
FIBERY_VARIABLES = (
    *REQUIRED_ENVIRONMENT,
    ENV_TIMEOUT_SECONDS,
    OBSOLETE_SPACE_ID_VARIABLE,
)

PROJECT_DATABASE = "SDLC/Project"
PLANNED_STATE_ID = "state-planned"


class FiberyStandIn:
    """Answers the Commands, Views and Documents endpoints from memory."""

    def __init__(self, existing_projects=()):
        self.projects = {
            record["fibery/id"]: dict(record) for record in existing_projects
        }
        self.views_calls = []
        self.requested_urls = []
        self.commands = []
        self.next_id = 1

    def __call__(self, request, timeout):
        self.requested_urls.append(request.full_url)
        body = json.loads(request.data.decode("utf-8"))
        if request.full_url.endswith("/api/commands"):
            payload = [{"success": True, "result": self._command(body[0])}]
        else:
            payload = {"jsonrpc": "2.0", "id": 1, "result": self._views(body)}
        return StubResponse(json.dumps(payload).encode("utf-8"))

    def _command(self, envelope):
        name, args = envelope["command"], envelope.get("args", {})
        self.commands.append((name, args.get("query", {}).get("q/from")))
        if name == "fibery.schema/query":
            return PROJECT_SCHEMA
        if name == "fibery.entity/query":
            return self._query(args)
        if name == "fibery.entity/create":
            return self._create(args)
        if name == "fibery.entity/update":
            return self._update(args)
        raise AssertionError(f"Unexpected command {name}")

    def _query(self, args):
        query, params = args["query"], args.get("params", {})
        if query["q/from"].startswith("workflow/state"):
            return [{"fibery/id": PLANNED_STATE_ID, "enum/name": "Planned"}]
        field, value = query["q/where"][1][0], next(iter(params.values()))
        return [
            record for record in self.projects.values() if record.get(field) == value
        ][: query["q/limit"]]

    def _create(self, args):
        assert args["type"] == PROJECT_DATABASE
        project_id = f"project-{self.next_id}"
        self.next_id += 1
        # Fibery allocates the public id atomically on create; it is a
        # different value from the entity uuid and is what a contained
        # Document's container-entity-id carries.
        self.projects[project_id] = {
            "fibery/id": project_id,
            "fibery/public-id": str(self.next_id - 1),
            **args["entity"],
        }
        return {"fibery/id": project_id}

    def _update(self, args):
        entity = dict(args["entity"])
        record = self.projects[entity.pop("fibery/id")]
        for field, value in entity.items():
            record[field] = (
                {"enum/name": "Planned"} if field == "workflow/state" else value
            )
        return {"fibery/id": record["fibery/id"]}

    def _views(self, body):
        self.views_calls.append(body["method"])
        raise AssertionError(f"Unexpected views method {body['method']}")


def install_fibery(monkeypatch, environment):
    """Point the CLI at an in-process Fibery, with exactly this environment.

    Every Fibery variable is cleared first, so a value in the developer's
    shell or in `.env` can never stand in for one a test deliberately omits.
    """
    stand_in = FiberyStandIn()
    for name in FIBERY_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(
        cli,
        "FiberyClient",
        lambda settings: FiberyClient(
            settings, url_opener=stand_in, clock=lambda: 0.0, sleeper=lambda s: None
        ),
    )
    return stand_in


@pytest.fixture
def fibery(monkeypatch):
    """The reported configuration: host, Space name and token, nothing else."""
    return install_fibery(monkeypatch, REQUIRED_ENVIRONMENT)


@pytest.fixture
def fibery_with_a_stale_space_id(monkeypatch):
    """The same, plus the retired variable an old .env may still export."""
    return install_fibery(
        monkeypatch,
        {**REQUIRED_ENVIRONMENT, OBSOLETE_SPACE_ID_VARIABLE: "stale-uuid"},
    )


def run(argv, capsys):
    exit_code = cli.main(argv)
    captured = capsys.readouterr()
    return exit_code, captured.out, captured.err


def test_initializes_a_new_project_end_to_end(fibery, capsys):
    exit_code, out, _ = run(["project", "init", "--name", "SDLC"], capsys)

    assert exit_code == cli.EXIT_SUCCESS
    assert out.splitlines()[0] == "PROJECT_INITIALIZED"
    assert "State: Planned" in out
    assert "Requirements/" not in out


def test_end_to_end_run_leaves_the_expected_fibery_state(fibery, capsys):
    run(["project", "init", "--name", "SDLC"], capsys)

    [project] = fibery.projects.values()
    assert project["SDLC/Name"] == "SDLC"
    assert project["SDLC/Code"] == "SDLC"
    assert project["workflow/state"] == {"enum/name": "Planned"}
    # The legacy Text Field exists in the schema but is neither written nor
    # required; no Folder or View is touched at all.
    assert "SDLC/Documents Root Folder ID" not in project
    assert fibery.views_calls == []


def test_rerunning_reports_already_exists_and_changes_nothing(fibery, capsys):
    run(["project", "init", "--name", "SDLC"], capsys)
    before = json.dumps(fibery.projects, sort_keys=True)

    exit_code, out, _ = run(["project", "init", "--name", "SDLC"], capsys)

    assert exit_code == cli.EXIT_SUCCESS
    assert out.splitlines()[0] == "PROJECT_ALREADY_EXISTS"
    assert json.dumps(fibery.projects, sort_keys=True) == before
    assert fibery.views_calls == []


def test_supplied_code_already_in_use_fails_on_stderr(fibery, capsys):
    run(["project", "init", "--name", "SDLC"], capsys)

    exit_code, _, err = run(
        ["project", "init", "--name", "Other", "--code", "SDLC"], capsys
    )

    assert exit_code == cli.EXIT_FAILURE
    assert err.splitlines()[0] == "PROJECT_CODE_COLLISION"


# -- no Space UUID is required ---------------------------------------------


def test_init_runs_with_host_space_and_token_only(fibery, capsys):
    """The real entry point, through the real configuration check.

    `load_fibery_settings` is not stubbed: the point of the test is that the
    configuration check itself accepts an environment without a Space UUID.
    """
    exit_code, out, err = run(["project", "init", "--name", "SDLC"], capsys)

    assert (exit_code, err) == (cli.EXIT_SUCCESS, "")
    assert out.splitlines()[0] == "PROJECT_INITIALIZED"


def test_rerunning_without_a_space_id_makes_no_further_mutation(fibery, capsys):
    run(["project", "init", "--name", "SDLC"], capsys)
    before = json.dumps(fibery.projects, sort_keys=True)

    exit_code, out, _ = run(["project", "init", "--name", "SDLC"], capsys)

    assert exit_code == cli.EXIT_SUCCESS
    assert out.splitlines()[0] == "PROJECT_ALREADY_EXISTS"
    assert json.dumps(fibery.projects, sort_keys=True) == before


def test_init_resolves_no_space_id_and_calls_no_views_api(fibery, capsys):
    """No lookup replaces the removed requirement: init has no use for the id.

    Both interfaces that expose a Space UUID stay untouched — the `fibery/app`
    Database the resolver reads, and the Views API a Document would need.
    """
    run(["project", "init", "--name", "SDLC"], capsys)

    assert fibery.views_calls == []
    assert all(url.endswith("/api/commands") for url in fibery.requested_urls)
    assert all(database != "fibery/app" for _, database in fibery.commands)


def test_a_stale_space_id_in_the_environment_changes_nothing(
    fibery_with_a_stale_space_id, capsys
):
    """The retired variable is not read, so an old .env cannot steer the run."""
    exit_code, out, err = run(["project", "init", "--name", "SDLC"], capsys)

    assert (exit_code, err) == (cli.EXIT_SUCCESS, "")
    assert out.splitlines()[0] == "PROJECT_INITIALIZED"
    assert fibery_with_a_stale_space_id.views_calls == []


@pytest.mark.parametrize("value", [None, "", "   "])
@pytest.mark.parametrize("missing", sorted(REQUIRED_ENVIRONMENT))
def test_a_required_variable_stops_init_before_any_request(
    monkeypatch, capsys, missing, value
):
    environment = dict(REQUIRED_ENVIRONMENT)
    if value is None:
        del environment[missing]
    else:
        environment[missing] = value
    stand_in = install_fibery(monkeypatch, environment)

    exit_code, _, err = run(["project", "init", "--name", "SDLC"], capsys)

    assert exit_code == cli.EXIT_FAILURE
    assert missing in err
    assert stand_in.requested_urls == []
