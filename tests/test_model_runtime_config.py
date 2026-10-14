"""Runtime/model selection precedence from config/sdlc.toml."""

import copy
from pathlib import Path

import pytest

from sdlc.model_runtime_config import (
    RAW_REQUIREMENT_PROCESSOR_ROLE,
    ROLES_KEY,
    STANDARD_REQUIREMENT_PROCESSOR_ROLE,
    STANDARD_REQUIREMENT_REVIEWER_ROLE,
    TSA_ARCHITECT_ROLE,
    TSA_REVIEWER_ROLE,
    ModelRuntimeConfigError,
    load_model_runtime_config,
    runtime_definition,
    select_runtime,
)

PROJECT_CONFIG = Path("config/sdlc.toml")

CONFIG = {
    "transport": "local_cli_oauth",
    "default": {"runtime": "claude"},
    "runtimes": {
        "claude": {"executable": "claude", "invocation_mode": "print"},
        "codex": {"executable": "codex", "invocation_mode": "exec"},
    },
    "roles": {RAW_REQUIREMENT_PROCESSOR_ROLE: {"runtime": "claude"}},
}


def with_config(**changes):
    return {**CONFIG, **changes}


# -- the shipped configuration ---------------------------------------------


def test_the_project_config_defines_the_processor_role():
    config = load_model_runtime_config(PROJECT_CONFIG)

    selection = select_runtime(config, RAW_REQUIREMENT_PROCESSOR_ROLE)

    assert selection.definition.executable in {"claude", "codex"}
    assert selection.role == RAW_REQUIREMENT_PROCESSOR_ROLE


def test_the_project_config_declares_the_local_cli_transport():
    """A configuration that routed models elsewhere must not load."""
    assert load_model_runtime_config(PROJECT_CONFIG)["transport"] == "local_cli_oauth"


# -- precedence -------------------------------------------------------------


def test_role_runtime_beats_the_project_default():
    config = with_config(
        default={"runtime": "claude"},
        roles={RAW_REQUIREMENT_PROCESSOR_ROLE: {"runtime": "codex"}},
    )

    assert (
        select_runtime(config, RAW_REQUIREMENT_PROCESSOR_ROLE).definition.name
        == "codex"
    )


def test_an_unconfigured_role_falls_back_to_the_project_default():
    assert select_runtime(CONFIG, "some_other_role").definition.name == "claude"


def test_an_explicit_override_beats_role_and_default():
    selection = select_runtime(
        CONFIG, RAW_REQUIREMENT_PROCESSOR_ROLE, runtime_override="codex"
    )

    assert selection.definition.name == "codex"


def test_a_model_override_beats_everything():
    config = with_config(
        roles={RAW_REQUIREMENT_PROCESSOR_ROLE: {"runtime": "claude", "model": "role-m"}}
    )

    selection = select_runtime(
        config, RAW_REQUIREMENT_PROCESSOR_ROLE, model_override="explicit-m"
    )

    assert selection.model == "explicit-m"


def test_an_omitted_model_means_the_cli_chooses():
    selection = select_runtime(CONFIG, RAW_REQUIREMENT_PROCESSOR_ROLE)

    assert selection.model is None
    assert selection.uses_cli_default_model


def test_a_role_model_is_used_when_configured():
    config = with_config(
        roles={RAW_REQUIREMENT_PROCESSOR_ROLE: {"runtime": "codex", "model": "m-1"}}
    )

    assert select_runtime(config, RAW_REQUIREMENT_PROCESSOR_ROLE).model == "m-1"


def test_a_runtime_override_discards_a_model_chosen_for_another_runtime():
    """A model id is meaningless to a runtime it was not chosen for."""
    config = with_config(
        roles={RAW_REQUIREMENT_PROCESSOR_ROLE: {"runtime": "claude", "model": "m-1"}}
    )

    selection = select_runtime(
        config, RAW_REQUIREMENT_PROCESSOR_ROLE, runtime_override="codex"
    )

    assert selection.definition.name == "codex"
    assert selection.model is None


def test_the_default_model_applies_when_no_role_is_configured():
    config = with_config(default={"runtime": "claude", "model": "default-m"}, roles={})

    assert select_runtime(config, "unconfigured").model == "default-m"


# -- failures ---------------------------------------------------------------


def test_a_missing_config_file_is_reported():
    with pytest.raises(ModelRuntimeConfigError, match="No runtime configuration"):
        load_model_runtime_config(Path("config/does-not-exist.toml"))


def test_a_non_local_transport_is_refused(tmp_path):
    """Guards the boundary: models run only through local CLIs."""
    path = tmp_path / "sdlc.toml"
    path.write_text('[model_runtime]\ntransport = "openrouter"\n')

    with pytest.raises(ModelRuntimeConfigError, match="local_cli_oauth"):
        load_model_runtime_config(path)


def test_a_config_without_a_model_runtime_section_is_refused(tmp_path):
    path = tmp_path / "sdlc.toml"
    path.write_text("version = 1\n")

    with pytest.raises(ModelRuntimeConfigError, match="model_runtime"):
        load_model_runtime_config(path)


def test_invalid_toml_is_reported(tmp_path):
    path = tmp_path / "sdlc.toml"
    path.write_text("this is not toml = = =")

    with pytest.raises(ModelRuntimeConfigError, match="not valid TOML"):
        load_model_runtime_config(path)


def test_an_undefined_runtime_is_reported():
    config = with_config(roles={RAW_REQUIREMENT_PROCESSOR_ROLE: {"runtime": "ghost"}})

    with pytest.raises(ModelRuntimeConfigError, match="ghost"):
        select_runtime(config, RAW_REQUIREMENT_PROCESSOR_ROLE)


def test_a_role_with_no_runtime_and_no_default_is_reported():
    config = with_config(default={}, roles={})

    with pytest.raises(ModelRuntimeConfigError, match="No runtime configured"):
        select_runtime(config, "orphan")


def test_a_runtime_missing_its_executable_is_reported():
    config = with_config(runtimes={"claude": {"invocation_mode": "print"}})

    with pytest.raises(ModelRuntimeConfigError, match="executable"):
        runtime_definition(config, "claude")


def test_the_reviewer_role_resolves_independently_of_the_processor(tmp_path):
    """Separate roles are what make Review independent, even on one model."""
    config = tmp_path / "sdlc.toml"
    config.write_text(
        """
[model_runtime]
transport = "local_cli_oauth"

[model_runtime.default]
runtime = "claude"

[model_runtime.runtimes.claude]
executable = "claude"
invocation_mode = "print"

[model_runtime.runtimes.codex]
executable = "codex"
invocation_mode = "exec"

[model_runtime.roles.standard_requirement_processor]
runtime = "claude"

[model_runtime.roles.standard_requirement_reviewer]
runtime = "codex"
"""
    )
    loaded = load_model_runtime_config(config)
    processor = select_runtime(loaded, STANDARD_REQUIREMENT_PROCESSOR_ROLE)
    reviewer = select_runtime(loaded, STANDARD_REQUIREMENT_REVIEWER_ROLE)

    assert processor.definition.name == "claude"
    assert reviewer.definition.name == "codex"


def test_the_project_configures_a_reviewer_role():
    """The shipped configuration must actually define the role."""
    loaded = load_model_runtime_config(PROJECT_CONFIG)
    selection = select_runtime(loaded, STANDARD_REQUIREMENT_REVIEWER_ROLE)
    assert selection.definition.executable in {"claude", "codex"}


# -- the TSA-C01 runtime roles (Implementation Spec v0.3 section 15) -----------

TSA_ROLES = (TSA_ARCHITECT_ROLE, TSA_REVIEWER_ROLE)
REQUIREMENT_ROLES = (
    RAW_REQUIREMENT_PROCESSOR_ROLE,
    STANDARD_REQUIREMENT_PROCESSOR_ROLE,
    STANDARD_REQUIREMENT_REVIEWER_ROLE,
)
# Each TSA role paired with the other one, to show they are configured apart.
TSA_ROLE_PAIRS = [
    (TSA_ARCHITECT_ROLE, TSA_REVIEWER_ROLE),
    (TSA_REVIEWER_ROLE, TSA_ARCHITECT_ROLE),
]


def shipped_config():
    """A private copy of the shipped configuration, safe to change in a test."""
    return copy.deepcopy(load_model_runtime_config(PROJECT_CONFIG))


def with_role(config, role, **table):
    config[ROLES_KEY][role] = table
    return config


def test_the_tsa_role_names_are_the_ones_the_spec_fixes():
    assert (TSA_ARCHITECT_ROLE, TSA_REVIEWER_ROLE) == ("tsa_architect", "tsa_reviewer")


@pytest.mark.parametrize("role", TSA_ROLES)
def test_the_shipped_config_defines_the_tsa_role_explicitly(role):
    """Resolving is not enough: an unknown role also resolves, via the default."""
    roles = load_model_runtime_config(PROJECT_CONFIG)[ROLES_KEY]

    assert role in roles
    assert roles[role] == {"runtime": "claude"}, "runtime explicit, no model key"


@pytest.mark.parametrize("role", TSA_ROLES)
def test_the_shipped_tsa_role_selects_claude_print_with_the_cli_default_model(role):
    selection = select_runtime(load_model_runtime_config(PROJECT_CONFIG), role)

    assert selection.role == role
    assert (
        selection.definition.name,
        selection.definition.executable,
        selection.definition.invocation_mode,
    ) == ("claude", "claude", "print")
    assert selection.model is None
    assert selection.uses_cli_default_model


@pytest.mark.parametrize("role", TSA_ROLES)
def test_tsa_explicit_overrides_beat_the_role_table(role):
    config = with_role(shipped_config(), role, runtime="claude", model="role-m")

    runtime_only = select_runtime(config, role, runtime_override="codex")
    both = select_runtime(
        config, role, runtime_override="codex", model_override="explicit-m"
    )
    model_only = select_runtime(config, role, model_override="explicit-m")

    assert (runtime_only.definition.name, runtime_only.model) == ("codex", None)
    assert (both.definition.name, both.model) == ("codex", "explicit-m")
    assert (model_only.definition.name, model_only.model) == ("claude", "explicit-m")


@pytest.mark.parametrize("role", TSA_ROLES)
def test_a_configured_tsa_role_model_is_used(role):
    config = with_role(shipped_config(), role, runtime="claude", model="role-m")

    selection = select_runtime(config, role)

    assert (selection.definition.name, selection.model) == ("claude", "role-m")


@pytest.mark.parametrize("role", TSA_ROLES)
def test_a_tsa_runtime_override_discards_the_configured_role_model(role):
    config = with_role(shipped_config(), role, runtime="claude", model="role-m")

    selection = select_runtime(config, role, runtime_override="claude")

    assert (selection.definition.name, selection.model) == ("claude", None)


@pytest.mark.parametrize("role", TSA_ROLES)
def test_a_missing_tsa_role_table_falls_back_to_the_project_default(role):
    config = shipped_config()
    del config[ROLES_KEY][role]
    config["default"] = {"runtime": "codex", "model": "default-m"}

    selection = select_runtime(config, role)

    assert (selection.role, selection.definition.name) == (role, "codex")
    assert selection.model == "default-m"


@pytest.mark.parametrize(("role", "other"), TSA_ROLE_PAIRS)
def test_one_tsa_role_is_configured_independently_of_the_other(role, other):
    before = select_runtime(load_model_runtime_config(PROJECT_CONFIG), other)
    config = with_role(shipped_config(), role, runtime="codex", model="changed-m")

    changed = select_runtime(config, role)
    untouched = select_runtime(config, other)

    assert (changed.definition.name, changed.model) == ("codex", "changed-m")
    assert untouched == before
    assert (untouched.definition.name, untouched.model) == ("claude", None)


@pytest.mark.parametrize("role", REQUIREMENT_ROLES)
def test_the_shipped_requirement_roles_are_unchanged(role):
    config = load_model_runtime_config(PROJECT_CONFIG)

    selection = select_runtime(config, role)

    assert config[ROLES_KEY][role] == {"runtime": "claude"}
    assert (selection.role, selection.definition.name) == (role, "claude")
    assert selection.model is None


def test_the_shipped_roles_and_default_are_exactly_the_expected_set():
    config = load_model_runtime_config(PROJECT_CONFIG)

    assert set(config[ROLES_KEY]) == {*REQUIREMENT_ROLES, *TSA_ROLES}
    assert config["default"] == {"runtime": "claude"}
    assert set(config["runtimes"]) == {"claude", "codex"}


# -- the authentication guard is not configuration -----------------------------


def test_legacy_auth_keys_are_ignored_and_cannot_weaken_anything():
    """Older configurations listed the auth command and policy booleans. The
    guard is now a property of the CLI family, so these keys change nothing."""
    config = with_config(
        runtimes={
            "claude": {
                "executable": "claude",
                "invocation_mode": "print",
                "auth_check_args": [],
                "forbid_console_api_auth": False,
                "require_chatgpt_oauth": False,
            }
        }
    )

    definition = runtime_definition(config, "claude")

    assert not hasattr(definition, "auth_check_args")
    assert not hasattr(definition, "forbid_console_api_auth")
    assert definition.environment_passthrough == ()


def test_environment_passthrough_accepts_harmless_names():
    config = with_config(
        runtimes={
            "claude": {
                "executable": "claude",
                "invocation_mode": "print",
                "environment_passthrough": ["HTTPS_PROXY", "NO_PROXY"],
            }
        }
    )

    assert runtime_definition(config, "claude").environment_passthrough == (
        "HTTPS_PROXY",
        "NO_PROXY",
    )


@pytest.mark.parametrize(
    "name",
    [
        "ANTHROPIC_API_KEY",
        "OPENAI_BASE_URL",
        "FIBERY_TOKEN",
        "CLAUDE_CODE_USE_BEDROCK",
        "AWS_PROFILE",
        "MY_SECRET",
    ],
)
def test_environment_passthrough_refuses_provider_and_secret_names(name):
    config = with_config(
        runtimes={
            "claude": {
                "executable": "claude",
                "invocation_mode": "print",
                "environment_passthrough": [name],
            }
        }
    )

    with pytest.raises(ModelRuntimeConfigError, match=name):
        runtime_definition(config, "claude")


def test_environment_passthrough_must_be_a_list_of_names():
    config = with_config(
        runtimes={
            "claude": {
                "executable": "claude",
                "invocation_mode": "print",
                "environment_passthrough": "HTTPS_PROXY",
            }
        }
    )

    with pytest.raises(ModelRuntimeConfigError, match="list"):
        runtime_definition(config, "claude")
