"""RW-B04: the one outer project bootstrap action, composed end to end.

The suite runs the real composition over the existing deterministic
primitives: real `project_init`, real `requirement_add`, the real B02 template
and the real B03 descriptor, against the existing in-memory Fibery fakes and a
real temporary directory. Nothing here re-implements a primitive's logic, and
no model, live Fibery or CLI is involved.

`linked_workspaces` is the only new double: it keeps the Project-side and
Requirement-side fakes looking at one shared set of Projects, which is what a
single Fibery workspace does.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from fibery_fake import FakeFiberyWorkspace
from requirement_fake import FakeRequirementWorkspace
from sdlc import project_bootstrap
from sdlc.consumer_template import (
    AGENTS_GUIDANCE_PATH,
    CLAUDE_GUIDANCE_PATH,
    CONTEXT_PATH,
    DESCRIPTOR_PATH,
    MANAGED_BLOCK,
    MANAGED_PATHS,
    GuidanceDisposition,
    plan_agent_guidance,
)
from sdlc.fibery_workspace import FiberyError, ProjectRecord
from sdlc.project_bootstrap import (
    BootstrapCode,
    BootstrapStep,
    bootstrap_project,
)
from sdlc.project_code import candidate_project_codes
from sdlc.project_descriptor import (
    new_project_descriptor,
    parse_descriptor,
    render_descriptor,
)
from sdlc.project_init import initialize_project, preflight_project_code
from sdlc.results import AddResultCode, InitResult, ResultCode

NAME = "Example Project"
# What the existing project_code derivation produces for that Name: the
# two-word initials "EP" are shorter than the minimum, so it falls back to the
# truncated first word. Bootstrap never invents its own code.
CODE = "EXA"
CONTEXT_BYTES = b"# Project context\n\nWhat this project is about.\n"
RAW_TITLE = "Initial requirements"

RAW_SOURCE = """# Initial requirements

## Export Metadata

- Format: `sdlc/raw-requirements`
- Format Version: `0.1`
- Project Name: `Example Project`

## Intent

Ship a thing.

## Context

There is no thing yet.

## Desired Outcomes

A thing exists.

## Requirements and Expected Behavior

The thing must exist.

## Constraints

None.

## Accepted Decisions

Build it.

## Open Questions

None.

## Deferred / Out of Scope

Everything else.
"""

EXCLUDED_PATHS = (
    ".codex/config.toml",
    ".claude/settings.json",
    ".agents",
    ".claude/agents",
    ".claude/skills",
    ".env",
)


class LinkedProjectWorkspace(FakeFiberyWorkspace):
    """The Project-side fake, mirroring creations into the Requirement side.

    One Fibery workspace holds one set of Projects; the two existing fakes
    model the two adapters, so bootstrap tests need them to agree.
    """

    def __init__(self, requirement_workspace, **options):
        super().__init__(**options)
        self.requirement_workspace = requirement_workspace

    def create_project(self, name: str, code: str) -> str:
        project_id = super().create_project(name, code)
        self.requirement_workspace.projects.append(
            ProjectRecord(id=project_id, name=name, code=code, state=None)
        )
        return project_id

    def set_project_state(self, project_id: str, state: str) -> None:
        super().set_project_state(project_id, state)
        self._mirror(project_id)

    def _mirror(self, project_id: str) -> None:
        stored = self.projects[project_id]
        projects = self.requirement_workspace.projects
        for index, record in enumerate(projects):
            if record.id == project_id:
                projects[index] = stored
                return


def linked_workspaces(projects: list[ProjectRecord] | None = None):
    """The two adapters of one workspace, sharing the same Projects."""
    requirement_workspace = FakeRequirementWorkspace(projects=list(projects or []))
    project_workspace = LinkedProjectWorkspace(
        requirement_workspace,
        projects=list(projects or []),
    )
    return project_workspace, requirement_workspace


@pytest.fixture
def inputs(tmp_path):
    """The two exported artifacts a bootstrap consumes."""
    requirements = tmp_path / "raw-requirements.md"
    requirements.write_text(RAW_SOURCE, encoding="utf-8")
    context = tmp_path / "project-context.md"
    context.write_bytes(CONTEXT_BYTES)
    return requirements, context


def run(tmp_path, inputs, target=None, projects=None, **options):
    """One bootstrap attempt over a fresh pair of linked workspaces."""
    requirements, context = inputs
    project_workspace, requirement_workspace = linked_workspaces(projects)
    result = bootstrap_project(
        project_workspace,
        requirement_workspace,
        name=options.pop("name", NAME),
        requirements_path=requirements,
        context_path=context,
        target=target if target is not None else tmp_path / "consumer",
        **options,
    )
    return result, project_workspace, requirement_workspace


def consumer(tmp_path) -> pathlib.Path:
    directory = tmp_path / "consumer"
    directory.mkdir()
    return directory


def managed(directory: pathlib.Path) -> dict[str, bytes]:
    return {
        relative: (directory / relative).read_bytes()
        for relative in MANAGED_PATHS
        if (directory / relative).exists()
    }


def tree(directory: pathlib.Path) -> dict[str, bytes]:
    """Every file under the target, by relative path."""
    return {
        str(path.relative_to(directory)): path.read_bytes()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


# -- a complete first bootstrap --------------------------------------------------------


def test_an_empty_existing_target_is_bootstrapped_completely(tmp_path, inputs):
    directory = consumer(tmp_path)

    result, _project_workspace, requirement_workspace = run(
        tmp_path, inputs, target=directory
    )

    assert result.code is BootstrapCode.PROJECT_BOOTSTRAPPED, result
    assert result.is_normal
    assert result.project_name == NAME
    assert result.project_code == CODE
    assert result.project_init_code is ResultCode.PROJECT_INITIALIZED
    assert result.requirement_add_code is AddResultCode.RAW_REQUIREMENT_ADDED
    assert set(result.local_created) == set(MANAGED_PATHS)
    assert result.local_updated == () and result.local_reused == ()
    assert sorted(result.managed_directories_created) == [".claude", ".sdlc"]
    assert not result.target_created

    # the four managed artifacts, and nothing else
    assert set(tree(directory)) == set(MANAGED_PATHS)
    descriptor = parse_descriptor((directory / DESCRIPTOR_PATH).read_bytes())
    assert descriptor == new_project_descriptor(NAME, CODE)
    assert (directory / CONTEXT_PATH).read_bytes() == CONTEXT_BYTES
    for relative in (AGENTS_GUIDANCE_PATH, CLAUDE_GUIDANCE_PATH):
        assert MANAGED_BLOCK in (directory / relative).read_text(encoding="utf-8")

    # Fibery: one Project, one RAW Requirement in Raw + Draft
    [project] = requirement_workspace.projects
    assert (project.name, project.code) == (NAME, CODE)
    [requirement] = requirement_workspace.requirements.values()
    assert requirement.project_id == project.id
    assert (requirement.type_name, requirement.state) == ("Raw", "Draft")
    assert result.requirement_id == requirement.requirement_id


def test_an_absent_final_target_directory_is_created(tmp_path, inputs):
    target = tmp_path / "new-consumer"

    result, _, _ = run(tmp_path, inputs, target=target)

    assert result.code is BootstrapCode.PROJECT_BOOTSTRAPPED, result
    assert result.target_created
    assert target.is_dir()
    assert set(tree(target)) == set(MANAGED_PATHS)


def test_the_current_directory_is_the_target_when_none_is_given(
    tmp_path, inputs, monkeypatch
):
    directory = consumer(tmp_path)
    monkeypatch.chdir(directory)
    requirements, context = inputs
    project_workspace, requirement_workspace = linked_workspaces()

    result = bootstrap_project(
        project_workspace,
        requirement_workspace,
        name=NAME,
        requirements_path=requirements,
        context_path=context,
    )

    assert result.code is BootstrapCode.PROJECT_BOOTSTRAPPED, result
    assert set(tree(directory)) == set(MANAGED_PATHS)
    assert pathlib.Path(result.target).resolve() == directory.resolve()


def test_an_absent_target_parent_fails_before_any_mutation(tmp_path, inputs):
    result, project_workspace, _ = run(
        tmp_path, inputs, target=tmp_path / "missing" / "consumer"
    )

    assert result.code is BootstrapCode.BOOTSTRAP_FAILED
    assert result.failed_step is BootstrapStep.RESOLVE_TARGET
    assert not (tmp_path / "missing").exists()
    assert project_workspace.mutations == []


# -- foreign state is preserved ---------------------------------------------------------


def test_unrelated_files_are_untouched_and_guidance_is_appended(tmp_path, inputs):
    directory = consumer(tmp_path)
    (directory / "README.md").write_text("# House\n\nRules.\n", encoding="utf-8")
    (directory / "src").mkdir()
    (directory / "src/example.py").write_text("print('hi')\n", encoding="utf-8")
    (directory / AGENTS_GUIDANCE_PATH).write_text(
        "# Agents\n\nBe kind.\n", encoding="utf-8"
    )
    before = tree(directory)

    result, _, _ = run(tmp_path, inputs, target=directory)

    assert result.code is BootstrapCode.PROJECT_BOOTSTRAPPED, result
    after = tree(directory)
    for unrelated in ("README.md", "src/example.py"):
        assert after[unrelated] == before[unrelated]
    guidance = (directory / AGENTS_GUIDANCE_PATH).read_text(encoding="utf-8")
    assert guidance.startswith("# Agents\n\nBe kind.\n"), "foreign bytes survive"
    assert MANAGED_BLOCK in guidance
    assert AGENTS_GUIDANCE_PATH in result.local_updated
    assert CLAUDE_GUIDANCE_PATH in result.local_created


def test_no_excluded_runtime_or_agent_path_is_ever_created(tmp_path, inputs):
    directory = consumer(tmp_path)

    run(tmp_path, inputs, target=directory)

    for excluded in EXCLUDED_PATHS:
        assert not (directory / excluded).exists()
    assert set(tree(directory)) == set(MANAGED_PATHS), "no fifth managed path"


# -- reuse and rerun ---------------------------------------------------------------------


def test_a_complete_rerun_changes_nothing_and_reports_already_bootstrapped(
    tmp_path, inputs
):
    directory = consumer(tmp_path)
    first, project_workspace, requirement_workspace = run(
        tmp_path, inputs, target=directory
    )
    assert first.code is BootstrapCode.PROJECT_BOOTSTRAPPED
    before = tree(directory)
    project_mutations = list(project_workspace.mutations)
    requirement_mutations = list(requirement_workspace.mutations)
    requirements, context = inputs

    second = bootstrap_project(
        project_workspace,
        requirement_workspace,
        name=NAME,
        requirements_path=requirements,
        context_path=context,
        target=directory,
    )

    assert second.code is BootstrapCode.PROJECT_ALREADY_BOOTSTRAPPED, second
    assert second.is_normal
    assert set(second.local_reused) == set(MANAGED_PATHS)
    assert second.local_created == () and second.local_updated == ()
    assert second.project_init_code is ResultCode.PROJECT_ALREADY_EXISTS
    assert second.requirement_add_code is AddResultCode.REQUIREMENT_ALREADY_ADDED
    assert tree(directory) == before, "no local byte changed"
    assert project_workspace.mutations == project_mutations, "no Fibery write"
    assert requirement_workspace.mutations == requirement_mutations
    assert len(requirement_workspace.projects) == 1, "no duplicate Project"
    assert len(requirement_workspace.requirements) == 1, "no duplicate RAW"
    assert second.requirement_id == first.requirement_id


def test_an_existing_compatible_project_is_reused(tmp_path, inputs):
    existing = ProjectRecord(id="p-1", name=NAME, code=CODE, state="Planned")

    result, project_workspace, _ = run(
        tmp_path, inputs, target=consumer(tmp_path), projects=[existing]
    )

    assert result.code is BootstrapCode.PROJECT_BOOTSTRAPPED, result
    assert result.project_code == CODE
    assert result.project_init_code is ResultCode.PROJECT_ALREADY_EXISTS
    assert "create_project" not in project_workspace.calls


def test_a_descriptor_written_by_a_previous_run_is_reused_unchanged(tmp_path, inputs):
    directory = consumer(tmp_path)
    (directory / ".sdlc").mkdir()
    canonical = render_descriptor(new_project_descriptor(NAME, CODE))
    # accepted formatting variation: CRLF endings
    (directory / DESCRIPTOR_PATH).write_bytes(canonical.replace(b"\n", b"\r\n"))
    existing_bytes = (directory / DESCRIPTOR_PATH).read_bytes()

    result, _, _ = run(tmp_path, inputs, target=directory)

    assert result.code is BootstrapCode.PROJECT_BOOTSTRAPPED, result
    assert DESCRIPTOR_PATH in result.local_reused
    assert (directory / DESCRIPTOR_PATH).read_bytes() == existing_bytes


def test_an_identical_context_file_is_reused_unchanged(tmp_path, inputs):
    directory = consumer(tmp_path)
    (directory / ".sdlc").mkdir()
    (directory / CONTEXT_PATH).write_bytes(CONTEXT_BYTES)

    result, _, _ = run(tmp_path, inputs, target=directory)

    assert result.code is BootstrapCode.PROJECT_BOOTSTRAPPED, result
    assert CONTEXT_PATH in result.local_reused


def test_an_existing_frozen_guidance_block_is_reused_byte_for_byte(tmp_path, inputs):
    directory = consumer(tmp_path)
    guidance = (MANAGED_BLOCK + "\n").encode("utf-8")
    (directory / AGENTS_GUIDANCE_PATH).write_bytes(guidance)

    result, _, _ = run(tmp_path, inputs, target=directory)

    assert result.code is BootstrapCode.PROJECT_BOOTSTRAPPED, result
    assert AGENTS_GUIDANCE_PATH in result.local_reused
    assert (directory / AGENTS_GUIDANCE_PATH).read_bytes() == guidance


# -- conflicts stop before any mutation ---------------------------------------------------

CONFLICTS = {
    "descriptor": (DESCRIPTOR_PATH, b'version: 1\nproject:\n  name: "Other"\n'),
    "context": (CONTEXT_PATH, b"# Someone else's context\n"),
    "agents-block": (
        AGENTS_GUIDANCE_PATH,
        b"<!-- SDLC:BEGIN -->\nchanged\n<!-- SDLC:END -->\n",
    ),
    "claude-block": (CLAUDE_GUIDANCE_PATH, b"<!-- SDLC:BEGIN -->\nno end marker\n"),
}


@pytest.mark.parametrize(
    ("relative", "content"), CONFLICTS.values(), ids=CONFLICTS.keys()
)
def test_an_incompatible_managed_file_conflicts_with_zero_mutation(
    tmp_path, inputs, relative, content
):
    directory = consumer(tmp_path)
    (directory / relative).parent.mkdir(parents=True, exist_ok=True)
    (directory / relative).write_bytes(content)
    before = tree(directory)

    result, project_workspace, requirement_workspace = run(
        tmp_path, inputs, target=directory
    )

    assert result.code is BootstrapCode.BOOTSTRAP_CONFLICT, result
    assert result.failed_step is BootstrapStep.PREFLIGHT_LOCAL
    assert tree(directory) == before, "no local write"
    assert project_workspace.mutations == [] and requirement_workspace.mutations == []
    assert result.local_created == () and result.local_updated == ()


SYMLINKS = {
    "managed-file": AGENTS_GUIDANCE_PATH,
    "sdlc-directory": ".sdlc",
    "claude-directory": ".claude",
}


@pytest.mark.parametrize("relative", SYMLINKS.values(), ids=SYMLINKS.keys())
def test_a_managed_symlink_conflicts_and_is_never_followed(tmp_path, inputs, relative):
    directory = consumer(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (directory / relative).symlink_to(elsewhere)

    result, project_workspace, _ = run(tmp_path, inputs, target=directory)

    assert result.code is BootstrapCode.BOOTSTRAP_CONFLICT, result
    assert (directory / relative).is_symlink(), "the symlink is left alone"
    assert list(elsewhere.iterdir()) == [], "nothing was written through it"
    assert project_workspace.mutations == []


@pytest.mark.parametrize("relative", [".sdlc", ".claude"])
def test_a_managed_parent_that_is_not_a_directory_conflicts(tmp_path, inputs, relative):
    directory = consumer(tmp_path)
    (directory / relative).write_text("not a directory\n", encoding="utf-8")

    result, _, _ = run(tmp_path, inputs, target=directory)

    assert result.code is BootstrapCode.BOOTSTRAP_CONFLICT, result
    assert result.failed_step is BootstrapStep.PREFLIGHT_LOCAL


def test_a_target_that_is_not_a_directory_conflicts(tmp_path, inputs):
    target = tmp_path / "a-file"
    target.write_text("not a directory\n", encoding="utf-8")

    result, _, _ = run(tmp_path, inputs, target=target)

    assert result.code is BootstrapCode.BOOTSTRAP_CONFLICT
    assert result.failed_step is BootstrapStep.RESOLVE_TARGET


def test_a_symlinked_target_conflicts_and_is_not_followed(tmp_path, inputs):
    real = tmp_path / "real"
    real.mkdir()
    target = tmp_path / "link"
    target.symlink_to(real)

    result, _, _ = run(tmp_path, inputs, target=target)

    assert result.code is BootstrapCode.BOOTSTRAP_CONFLICT
    assert list(real.iterdir()) == []


# -- input preflight ----------------------------------------------------------------------


def test_an_invalid_raw_export_stops_before_any_mutation(tmp_path):
    directory = consumer(tmp_path)
    requirements = tmp_path / "bad.md"
    requirements.write_text("# Not an export\n\nNothing here.\n", encoding="utf-8")
    context = tmp_path / "context.md"
    context.write_bytes(CONTEXT_BYTES)
    project_workspace, requirement_workspace = linked_workspaces()

    result = bootstrap_project(
        project_workspace,
        requirement_workspace,
        name=NAME,
        requirements_path=requirements,
        context_path=context,
        target=directory,
    )

    assert result.code is BootstrapCode.BOOTSTRAP_FAILED
    assert result.failed_step is BootstrapStep.READ_INPUTS
    assert tree(directory) == {}
    assert project_workspace.mutations == [] and requirement_workspace.mutations == []


@pytest.mark.parametrize("missing", ["requirements", "context"])
def test_an_unreadable_input_stops_before_any_mutation(tmp_path, inputs, missing):
    requirements, context = inputs
    directory = consumer(tmp_path)
    paths = {"requirements": requirements, "context": context}
    paths[missing] = tmp_path / "absent.md"
    project_workspace, requirement_workspace = linked_workspaces()

    result = bootstrap_project(
        project_workspace,
        requirement_workspace,
        name=NAME,
        requirements_path=paths["requirements"],
        context_path=paths["context"],
        target=directory,
    )

    assert result.code is BootstrapCode.BOOTSTRAP_FAILED
    assert result.failed_step is BootstrapStep.READ_INPUTS
    assert tree(directory) == {}
    assert project_workspace.mutations == []


def test_a_blank_project_name_is_refused(tmp_path, inputs):
    result, project_workspace, _ = run(tmp_path, inputs, name="   ")

    assert result.code is BootstrapCode.BOOTSTRAP_FAILED
    assert project_workspace.mutations == []


# -- identity resolution --------------------------------------------------------------------


def test_the_resolved_code_is_used_by_descriptor_init_and_add(tmp_path, inputs):
    directory = consumer(tmp_path)

    result, _project_workspace, requirement_workspace = run(
        tmp_path, inputs, target=directory
    )

    descriptor = parse_descriptor((directory / DESCRIPTOR_PATH).read_bytes())
    [project] = requirement_workspace.projects
    [requirement] = requirement_workspace.requirements.values()
    assert descriptor.project.code == CODE
    assert descriptor.fibery.project_code == CODE
    assert project.code == CODE
    assert requirement.requirement_id.startswith(f"{CODE}-RAW-")
    assert result.project_code == CODE


def test_a_supplied_code_that_differs_from_the_existing_project_conflicts(
    tmp_path, inputs
):
    existing = ProjectRecord(id="p-1", name=NAME, code=CODE, state="Planned")
    directory = consumer(tmp_path)

    result, project_workspace, _ = run(
        tmp_path, inputs, target=directory, projects=[existing], code="OTHER"
    )

    assert result.code is BootstrapCode.BOOTSTRAP_CONFLICT, result
    assert result.failed_step is BootstrapStep.RESOLVE_IDENTITY
    assert tree(directory) == {}, "no local write"
    assert project_workspace.mutations == []


def test_two_projects_with_the_same_name_conflict(tmp_path, inputs):
    duplicates = [
        ProjectRecord(id="p-1", name=NAME, code=CODE, state="Planned"),
        ProjectRecord(id="p-2", name=NAME, code="OTHER", state="Planned"),
    ]
    directory = consumer(tmp_path)

    result, _, _ = run(tmp_path, inputs, target=directory, projects=duplicates)

    assert result.code is BootstrapCode.BOOTSTRAP_CONFLICT
    assert result.failed_step is BootstrapStep.RESOLVE_IDENTITY
    assert tree(directory) == {}


def test_a_fibery_read_failure_during_identity_resolution_fails_cleanly(
    tmp_path, inputs
):
    directory = consumer(tmp_path)
    requirements, context = inputs
    project_workspace, requirement_workspace = linked_workspaces()
    requirement_workspace.failures["find_projects_by_name"] = FiberyError("down")

    result = bootstrap_project(
        project_workspace,
        requirement_workspace,
        name=NAME,
        requirements_path=requirements,
        context_path=context,
        target=directory,
    )

    assert result.code is BootstrapCode.BOOTSTRAP_FAILED
    assert result.failed_step is BootstrapStep.RESOLVE_IDENTITY
    assert tree(directory) == {}


# -- inner primitive failures ------------------------------------------------------------


def test_a_project_init_failure_after_local_state_is_partial_and_adds_nothing(
    tmp_path, inputs
):
    directory = consumer(tmp_path)
    requirements, context = inputs
    project_workspace, requirement_workspace = linked_workspaces()
    project_workspace.failures["create_project"] = FiberyError("refused")

    result = bootstrap_project(
        project_workspace,
        requirement_workspace,
        name=NAME,
        requirements_path=requirements,
        context_path=context,
        target=directory,
    )

    assert result.code is BootstrapCode.PARTIAL_BOOTSTRAP, result
    assert result.failed_step is BootstrapStep.PROJECT_INIT
    assert result.project_init_code is ResultCode.FIBERY_WRITE_FAILED
    assert result.requirement_add_code is None, "Requirement Add never ran"
    assert set(tree(directory)) == set(MANAGED_PATHS), "local state is left in place"
    assert "create_requirement" not in requirement_workspace.calls
    # The message must not contradict the durable local state it reports.
    assert set(result.local_created) == set(MANAGED_PATHS)
    assert sorted(result.managed_directories_created) == [".claude", ".sdlc"]
    assert "changed nothing else" not in result.message
    assert "stopped before Requirement Add" in result.message


def test_a_requirement_add_failure_is_partial_and_nothing_is_rolled_back(
    tmp_path, inputs
):
    directory = consumer(tmp_path)
    requirements, context = inputs
    project_workspace, requirement_workspace = linked_workspaces()
    requirement_workspace.failures["create_requirement"] = FiberyError("refused")

    result = bootstrap_project(
        project_workspace,
        requirement_workspace,
        name=NAME,
        requirements_path=requirements,
        context_path=context,
        target=directory,
    )

    assert result.code is BootstrapCode.PARTIAL_BOOTSTRAP, result
    assert result.failed_step is BootstrapStep.REQUIREMENT_ADD
    assert result.project_init_code is ResultCode.PROJECT_INITIALIZED
    assert len(requirement_workspace.projects) == 1, "the Project stays"
    assert set(tree(directory)) == set(MANAGED_PATHS), "local state stays"


def test_the_resolved_code_is_never_re_derived_when_it_is_taken_before_init(
    tmp_path, inputs, monkeypatch
):
    """The frozen race: another actor claims the resolved Code before Project Init."""
    directory = consumer(tmp_path)
    requirements, context = inputs
    project_workspace, requirement_workspace = linked_workspaces()
    resolve = project_bootstrap.preflight_project_code
    resolved: list[str] = []

    def claim_after_preflight(workspace, name, requested):
        code = resolve(workspace, name, requested)
        resolved.append(code)
        project_workspace.projects["stolen"] = ProjectRecord(
            id="stolen", name="Another Project", code=code, state="Planned"
        )
        return code

    monkeypatch.setattr(
        project_bootstrap, "preflight_project_code", claim_after_preflight
    )

    result = bootstrap_project(
        project_workspace,
        requirement_workspace,
        name=NAME,
        requirements_path=requirements,
        context_path=context,
        target=directory,
    )

    assert resolved == [CODE]
    assert result.code is BootstrapCode.PARTIAL_BOOTSTRAP, result
    assert result.project_init_code is ResultCode.PROJECT_CODE_COLLISION
    descriptor = parse_descriptor((directory / DESCRIPTOR_PATH).read_bytes())
    assert descriptor.project.code == CODE, "the descriptor keeps the resolved code"
    assert result.requirement_add_code is None, "Requirement Add never ran"
    assert not any(
        record.name == NAME for record in project_workspace.projects.values()
    ), "no Project was created under another code"


# -- composed validation --------------------------------------------------------------


def test_a_local_write_that_does_not_read_back_is_reported_truthfully(
    tmp_path, inputs, monkeypatch
):
    """Every write is confirmed by reading it back; a bad read-back stops here."""
    directory = consumer(tmp_path)
    requirements, context = inputs
    project_workspace, requirement_workspace = linked_workspaces()
    real_read = pathlib.Path.read_bytes

    def corrupt_context_read_back(self):
        if self.name == "project-context.md" and self.parent.name == ".sdlc":
            return b""
        return real_read(self)

    monkeypatch.setattr(pathlib.Path, "read_bytes", corrupt_context_read_back)

    result = bootstrap_project(
        project_workspace,
        requirement_workspace,
        name=NAME,
        requirements_path=requirements,
        context_path=context,
        target=directory,
    )

    assert result.code is BootstrapCode.PARTIAL_BOOTSTRAP, result
    assert result.failed_step is BootstrapStep.MATERIALIZE_LOCAL
    assert set(result.local_created) == {
        AGENTS_GUIDANCE_PATH,
        CLAUDE_GUIDANCE_PATH,
        DESCRIPTOR_PATH,
    }, "what became durable is reported, and nothing is rolled back"
    assert project_workspace.mutations == [], "no Fibery write followed"
    assert requirement_workspace.mutations == []


def test_the_initial_raw_is_validated_against_the_parsed_fingerprint(tmp_path, inputs):
    directory = consumer(tmp_path)

    result, _, requirement_workspace = run(tmp_path, inputs, target=directory)

    [requirement] = requirement_workspace.requirements.values()
    assert requirement.source_fingerprint
    assert result.requirement_id == requirement.requirement_id
    assert requirement.state == "Draft", "bootstrap never starts processing"


def test_bootstrap_never_moves_the_requirement_out_of_draft(tmp_path, inputs):
    _, _, requirement_workspace = run(tmp_path, inputs, target=consumer(tmp_path))

    states = [
        m for m in requirement_workspace.mutations if "set_requirement_state" in m
    ]
    assert states == ["set_requirement_state Draft"]


# -- diagnostics and purity -------------------------------------------------------------


def test_no_result_field_carries_the_raw_or_context_body(tmp_path, inputs):
    directory = consumer(tmp_path)
    (directory / CONTEXT_PATH).parent.mkdir(parents=True, exist_ok=True)
    (directory / CONTEXT_PATH).write_bytes(b"# Secret local context\n")

    result, _, _ = run(tmp_path, inputs, target=directory)

    printed = " ".join([result.message, *result.details, *(result.local_created or ())])
    assert "Ship a thing" not in printed
    assert "Secret local context" not in printed
    assert "What this project is about" not in printed


def test_the_module_never_imports_a_model_runtime_or_fibery_transport():
    tree_ = ast.parse(
        pathlib.Path(project_bootstrap.__file__).read_text(encoding="utf-8")
    )
    imported = {
        node.module or ""
        for node in ast.walk(tree_)
        if isinstance(node, ast.ImportFrom)
    }
    imported |= {
        alias.name
        for node in ast.walk(tree_)
        if isinstance(node, ast.Import)
        for alias in node.names
    }

    forbidden = {
        name for name in imported if "model_runtime" in name or "fibery_http" in name
    }
    assert forbidden == set()
    assert "sdlc.raw_processor" not in imported, "bootstrap starts no processing"


def test_the_managed_manifest_is_exactly_the_b01_four():
    assert set(project_bootstrap.MATERIALIZATION_ORDER) == set(MANAGED_PATHS)
    assert project_bootstrap.MANAGED_PARENTS == (".claude", ".sdlc")


def test_guidance_planning_is_delegated_to_the_b02_contract(tmp_path, inputs):
    directory = consumer(tmp_path)

    run(tmp_path, inputs, target=directory)

    for relative in (AGENTS_GUIDANCE_PATH, CLAUDE_GUIDANCE_PATH):
        plan = plan_agent_guidance((directory / relative).read_bytes())
        assert plan.disposition is GuidanceDisposition.COMPATIBLE


# -- the read-only Project Code preflight added to project_init -----------------------


def test_the_preflight_returns_a_supplied_free_code():
    workspace = FakeFiberyWorkspace()

    assert preflight_project_code(workspace, NAME, "free") == "FREE"
    assert workspace.mutations == []


def test_the_preflight_derives_exactly_what_the_existing_algorithm_would():
    workspace = FakeFiberyWorkspace()

    resolved = preflight_project_code(workspace, NAME, None)

    assert resolved == next(candidate_project_codes(NAME)) == CODE
    assert workspace.mutations == []


def test_the_preflight_follows_the_existing_collision_walk():
    taken = [ProjectRecord(id="t-1", name="Other", code=CODE, state="Planned")]
    workspace = FakeFiberyWorkspace(projects=taken)

    resolved = preflight_project_code(workspace, NAME, None)

    assert resolved == list(candidate_project_codes(NAME))[1]
    assert workspace.mutations == []


PREFLIGHT_FAILURES = {
    "invalid-code": ("1BAD", None, ResultCode.INVALID_PROJECT_CODE),
    "taken-code": (
        CODE,
        [ProjectRecord("t-1", "Other", CODE, "Planned")],
        ResultCode.PROJECT_CODE_COLLISION,
    ),
}


@pytest.mark.parametrize(
    ("requested", "projects", "expected"),
    PREFLIGHT_FAILURES.values(),
    ids=PREFLIGHT_FAILURES.keys(),
)
def test_preflight_failures_map_onto_the_existing_init_results(
    requested, projects, expected
):
    workspace = FakeFiberyWorkspace(projects=list(projects or []))

    result = preflight_project_code(workspace, NAME, requested)

    assert isinstance(result, InitResult)
    assert result.code is expected
    assert result.created == (), "a read-only preflight has an empty journal"
    assert workspace.mutations == []


def test_a_fibery_read_failure_maps_onto_the_existing_init_result():
    workspace = FakeFiberyWorkspace()
    workspace.failures["count_projects_with_code"] = FiberyError("down")

    result = preflight_project_code(workspace, NAME, None)

    assert isinstance(result, InitResult)
    assert result.code is ResultCode.FIBERY_READ_FAILED


def test_a_blank_name_is_refused_by_the_preflight():
    result = preflight_project_code(FakeFiberyWorkspace(), "   ", None)

    assert isinstance(result, InitResult)
    assert result.code is ResultCode.INVALID_INPUT


def test_the_preflight_creates_and_writes_nothing():
    workspace = FakeFiberyWorkspace()

    preflight_project_code(workspace, NAME, None)

    assert workspace.projects == {}
    assert workspace.mutations == []
    assert "create_project" not in workspace.calls
    assert "set_project_state" not in workspace.calls
    assert "set_project_description" not in workspace.calls


def test_initialize_project_still_resolves_its_own_code_when_none_is_supplied():
    """The helper is additive: the existing primitive keeps its behaviour."""
    workspace = FakeFiberyWorkspace()

    result = initialize_project(workspace, name=NAME)

    assert result.code is ResultCode.PROJECT_INITIALIZED
    assert result.project_code == next(candidate_project_codes(NAME))


# -- the target root is re-checked immediately before every local mutation -------------


def test_a_target_that_becomes_a_symlink_after_preflight_is_never_written_through(
    tmp_path, inputs, monkeypatch
):
    """The race the static checks cannot see: an absent target preflights as safe,
    then another actor turns it into a symlink before materialization."""
    outside = tmp_path / "outside"
    outside.mkdir()
    target = tmp_path / "late-symlink"
    requirements, context = inputs
    project_workspace, requirement_workspace = linked_workspaces()
    preflight = project_bootstrap._preflight_local

    def preflight_then_swap(directory, descriptor, context_bytes):
        plans = preflight(directory, descriptor, context_bytes)
        directory.symlink_to(outside, target_is_directory=True)
        return plans

    monkeypatch.setattr(project_bootstrap, "_preflight_local", preflight_then_swap)

    result = bootstrap_project(
        project_workspace,
        requirement_workspace,
        name=NAME,
        requirements_path=requirements,
        context_path=context,
        target=target,
    )

    assert not result.is_normal, result
    assert result.code is BootstrapCode.BOOTSTRAP_FAILED
    assert result.failed_step is BootstrapStep.MATERIALIZE_LOCAL
    assert target.is_symlink(), "the symlink is left exactly as it was found"
    assert list(outside.iterdir()) == [], "nothing was written through it"
    for relative in MANAGED_PATHS:
        assert not (outside / relative).exists()
    assert result.local_created == () and result.local_updated == ()
    assert not result.target_created
    assert project_workspace.mutations == []
    assert requirement_workspace.mutations == []
