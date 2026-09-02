"""Runtime/model selection precedence from config/sdlc.toml."""

from pathlib import Path

import pytest

from sdlc.model_runtime_config import (
    RAW_REQUIREMENT_PROCESSOR_ROLE,
    STANDARD_REQUIREMENT_PROCESSOR_ROLE,
    STANDARD_REQUIREMENT_REVIEWER_ROLE,
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
        "claude": {
            "executable": "claude",
            "auth_check_args": ["auth", "status"],
            "invocation_mode": "print",
            "forbid_console_api_auth": True,
        },
        "codex": {
            "executable": "codex",
            "auth_check_args": ["login", "status"],
            "invocation_mode": "exec",
            "require_chatgpt_oauth": True,
        },
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
auth_check_args = ["auth", "status"]
invocation_mode = "print"

[model_runtime.runtimes.codex]
executable = "codex"
auth_check_args = ["login", "status"]
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
