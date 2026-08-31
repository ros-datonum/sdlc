"""End-to-end `sdlc project init` against an in-process stand-in for Fibery."""

import json

import pytest

from sdlc import cli
from sdlc.config import ENV_HOST, ENV_SPACE, ENV_SPACE_ID, ENV_TOKEN
from sdlc.fibery_client import FiberyClient
from test_fibery_http import PROJECT_SCHEMA, StubResponse

ENVIRONMENT = {
    ENV_HOST: "example.fibery.io",
    ENV_TOKEN: "test-token",
    ENV_SPACE: "SDLC",
    ENV_SPACE_ID: "space-uuid",
}

PROJECT_DATABASE = "SDLC/Project"
PLANNED_STATE_ID = "state-planned"


class FiberyStandIn:
    """Answers the Commands, Views and Documents endpoints from memory."""

    def __init__(self, existing_projects=()):
        self.projects = {
            record["fibery/id"]: dict(record) for record in existing_projects
        }
        self.folders = {}
        self.next_id = 1

    def __call__(self, request, timeout):
        body = json.loads(request.data.decode("utf-8"))
        if request.full_url.endswith("/api/commands"):
            payload = [{"success": True, "result": self._command(body[0])}]
        else:
            payload = {"jsonrpc": "2.0", "id": 1, "result": self._views(body)}
        return StubResponse(json.dumps(payload).encode("utf-8"))

    def _command(self, envelope):
        name, args = envelope["command"], envelope.get("args", {})
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
        self.projects[project_id] = {"fibery/id": project_id, **args["entity"]}
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
        if body["method"] == "create-folders":
            for folder in body["params"]["values"]:
                self.folders[folder["fibery/id"]] = folder
            return []
        if body["method"] == "query-folders":
            wanted = body["params"].get("filter", {}).get("ids")
            return [
                folder
                for folder in self.folders.values()
                if wanted is None or folder["fibery/id"] in wanted
            ]
        raise AssertionError(f"Unexpected views method {body['method']}")


@pytest.fixture
def fibery(monkeypatch):
    stand_in = FiberyStandIn()
    for name, value in ENVIRONMENT.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(
        cli,
        "FiberyClient",
        lambda settings: FiberyClient(settings, url_opener=stand_in),
    )
    return stand_in


def run(argv, capsys):
    exit_code = cli.main(argv)
    captured = capsys.readouterr()
    return exit_code, captured.out, captured.err


def test_initializes_a_new_project_end_to_end(fibery, capsys):
    exit_code, out, _ = run(["project", "init", "--name", "SDLC"], capsys)

    assert exit_code == cli.EXIT_SUCCESS
    assert out.splitlines()[0] == "PROJECT_INITIALIZED"
    assert "✓ SDLC/Requirements/Approved" in out


def test_end_to_end_run_leaves_the_expected_fibery_state(fibery, capsys):
    run(["project", "init", "--name", "SDLC"], capsys)

    [project] = fibery.projects.values()
    assert project["SDLC/Name"] == "SDLC"
    assert project["SDLC/Code"] == "SDLC"
    assert project["workflow/state"] == {"enum/name": "Planned"}

    root_id = project["SDLC/Documents Root Folder ID"]
    assert root_id in fibery.folders
    assert fibery.folders[root_id]["fibery/name"] == "SDLC"
    assert "fibery/Parent Folder" not in fibery.folders[root_id]

    by_name = {f["fibery/name"]: f for f in fibery.folders.values()}
    assert sorted(by_name) == ["Approved", "Draft", "Raw", "Requirements", "SDLC"]
    requirements = by_name["Requirements"]
    assert requirements["fibery/Parent Folder"] == {"fibery/id": root_id}
    for stage in ("Raw", "Draft", "Approved"):
        assert by_name[stage]["fibery/Parent Folder"] == {
            "fibery/id": requirements["fibery/id"]
        }


def test_rerunning_reports_already_exists_and_changes_nothing(fibery, capsys):
    run(["project", "init", "--name", "SDLC"], capsys)
    before = (json.dumps(fibery.projects, sort_keys=True), len(fibery.folders))

    exit_code, out, _ = run(["project", "init", "--name", "SDLC"], capsys)

    assert exit_code == cli.EXIT_SUCCESS
    assert out.splitlines()[0] == "PROJECT_ALREADY_EXISTS"
    assert (
        json.dumps(fibery.projects, sort_keys=True),
        len(fibery.folders),
    ) == before


def test_supplied_code_already_in_use_fails_on_stderr(fibery, capsys):
    run(["project", "init", "--name", "SDLC"], capsys)

    exit_code, _, err = run(
        ["project", "init", "--name", "Other", "--code", "SDLC"], capsys
    )

    assert exit_code == cli.EXIT_FAILURE
    assert err.splitlines()[0] == "PROJECT_CODE_COLLISION"
