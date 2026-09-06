"""Model runtime selection from `config/sdlc.toml`.

Implements the precedence in Local-OAuth-Model-Runtime-Spec-v0.1 section 4:

    explicit run override
    -> role runtime/model
    -> project default runtime/model
    -> local CLI default model when no model is configured

Model ids are configuration data. Nothing here hard-codes a runtime or a model.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sdlc.model_runtime_environment import DeniedEnvironmentName, require_allowed

DEFAULT_CONFIG_PATH = Path("config/sdlc.toml")

MODEL_RUNTIME_KEY = "model_runtime"
TRANSPORT_KEY = "transport"
REQUIRED_TRANSPORT = "local_cli_oauth"
DEFAULT_KEY = "default"
ROLES_KEY = "roles"
RUNTIMES_KEY = "runtimes"
RUNTIME_KEY = "runtime"
MODEL_KEY = "model"

EXECUTABLE_KEY = "executable"
INVOCATION_MODE_KEY = "invocation_mode"
ENVIRONMENT_PASSTHROUGH_KEY = "environment_passthrough"

RAW_REQUIREMENT_PROCESSOR_ROLE = "raw_requirement_processor"
STANDARD_REQUIREMENT_PROCESSOR_ROLE = "standard_requirement_processor"
STANDARD_REQUIREMENT_REVIEWER_ROLE = "standard_requirement_reviewer"


class ModelRuntimeConfigError(Exception):
    """The runtime configuration is missing or unusable."""


@dataclass(frozen=True)
class RuntimeDefinition:
    """How to reach one local CLI runtime.

    The authentication check and the child-process boundary are properties of
    the CLI family named by `invocation_mode`, not configuration: nothing in
    this file can switch them off. `environment_passthrough` may add variable
    names the CLI needs in a particular environment; provider, API-key and
    application-secret names are refused when the configuration loads.
    """

    name: str
    executable: str
    invocation_mode: str
    environment_passthrough: tuple[str, ...] = ()


@dataclass(frozen=True)
class RuntimeSelection:
    """The runtime and model resolved for one role.

    `model` is None when no model is configured, which means the local CLI
    chooses: the spec says to omit the --model flag entirely in that case.
    """

    role: str
    definition: RuntimeDefinition
    model: str | None

    @property
    def uses_cli_default_model(self) -> bool:
        return self.model is None


def load_model_runtime_config(path: Path | None = None) -> dict[str, Any]:
    """Read and structurally validate the runtime configuration."""
    config_path = DEFAULT_CONFIG_PATH if path is None else path
    try:
        raw = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ModelRuntimeConfigError(
            f"No runtime configuration at {config_path}."
        ) from error
    except tomllib.TOMLDecodeError as error:
        raise ModelRuntimeConfigError(
            f"{config_path} is not valid TOML: {error}"
        ) from error

    section = raw.get(MODEL_RUNTIME_KEY)
    if not isinstance(section, dict):
        raise ModelRuntimeConfigError(
            f"{config_path} has no [{MODEL_RUNTIME_KEY}] section."
        )
    transport = section.get(TRANSPORT_KEY)
    if transport != REQUIRED_TRANSPORT:
        raise ModelRuntimeConfigError(
            f"Model transport must be {REQUIRED_TRANSPORT!r}, got {transport!r}. "
            "SDLC executes models only through locally authenticated CLIs."
        )
    return section


def select_runtime(
    config: dict[str, Any],
    role: str,
    runtime_override: str | None = None,
    model_override: str | None = None,
) -> RuntimeSelection:
    """Resolve the runtime and model for one role."""
    role_config = (config.get(ROLES_KEY) or {}).get(role) or {}
    default_config = config.get(DEFAULT_KEY) or {}

    runtime_name = (
        runtime_override
        or role_config.get(RUNTIME_KEY)
        or default_config.get(RUNTIME_KEY)
    )
    if not runtime_name:
        raise ModelRuntimeConfigError(
            f"No runtime configured for role {role!r} and no project default."
        )

    model = _select_model(role_config, default_config, runtime_override, model_override)

    return RuntimeSelection(
        role=role,
        definition=runtime_definition(config, runtime_name),
        model=model,
    )


def _select_model(
    role_config: dict[str, Any],
    default_config: dict[str, Any],
    runtime_override: str | None,
    model_override: str | None,
) -> str | None:
    """Pick the model, or None to let the local CLI choose.

    A runtime override deliberately discards a configured model: that model was
    chosen for a different runtime and is meaningless to the one now selected.
    """
    if model_override is not None:
        return model_override
    if runtime_override is not None:
        return None
    if role_config.get(RUNTIME_KEY) or MODEL_KEY in role_config:
        return role_config.get(MODEL_KEY)
    return default_config.get(MODEL_KEY)


def runtime_definition(config: dict[str, Any], name: str) -> RuntimeDefinition:
    """Look up one runtime's CLI definition."""
    defined = (config.get(RUNTIMES_KEY) or {}).get(name)
    if not isinstance(defined, dict):
        raise ModelRuntimeConfigError(
            f"Runtime {name!r} is not defined in the runtime configuration."
        )
    executable = defined.get(EXECUTABLE_KEY)
    invocation_mode = defined.get(INVOCATION_MODE_KEY)
    if not executable or not invocation_mode:
        raise ModelRuntimeConfigError(
            f"Runtime {name!r} must define {EXECUTABLE_KEY!r} and "
            f"{INVOCATION_MODE_KEY!r}."
        )
    passthrough = defined.get(ENVIRONMENT_PASSTHROUGH_KEY) or []
    if not isinstance(passthrough, list) or not all(
        isinstance(item, str) for item in passthrough
    ):
        raise ModelRuntimeConfigError(
            f"Runtime {name!r}: {ENVIRONMENT_PASSTHROUGH_KEY!r} must be a list of "
            "environment variable names."
        )
    try:
        allowed = require_allowed(passthrough)
    except DeniedEnvironmentName as error:
        raise ModelRuntimeConfigError(f"Runtime {name!r}: {error}") from error
    return RuntimeDefinition(
        name=name,
        executable=executable,
        invocation_mode=invocation_mode,
        environment_passthrough=allowed,
    )
