"""Model runtime selection from `config/sdlc.toml`.

Implements the precedence in Local-OAuth-Model-Runtime-Spec-v0.1 section 4:

    explicit run override
    -> role runtime/model
    -> project default runtime/model
    -> local CLI default model when no model is configured

Model ids are configuration data. Nothing here hard-codes a runtime or a model.
"""

from __future__ import annotations

import re
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
QUALIFIED_BINARY_KEY = "qualified_binary"
QUALIFIED_SHA256_KEY = "sha256"
QUALIFIED_VERSION_KEY = "version"
QUALIFIED_PLUGINS_KEY = "builtin_plugins"
QUALIFIED_CAPABILITIES_KEY = "protocol_capabilities"
QUALIFIED_KEYS = frozenset(
    {
        QUALIFIED_SHA256_KEY,
        QUALIFIED_VERSION_KEY,
        QUALIFIED_PLUGINS_KEY,
        QUALIFIED_CAPABILITIES_KEY,
    }
)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")

RAW_REQUIREMENT_PROCESSOR_ROLE = "raw_requirement_processor"
STANDARD_REQUIREMENT_PROCESSOR_ROLE = "standard_requirement_processor"
STANDARD_REQUIREMENT_REVIEWER_ROLE = "standard_requirement_reviewer"
TSA_ARCHITECT_ROLE = "tsa_architect"
TSA_REVIEWER_ROLE = "tsa_reviewer"


class ModelRuntimeConfigError(Exception):
    """The runtime configuration is missing or unusable."""


@dataclass(frozen=True)
class QualifiedBinary:
    """The one CLI build an operator qualified for SDLC reasoning execution.

    Local-OAuth-Model-Runtime-Claude-2.1.306-Amendment-v0.1: the build is
    identified by the SHA-256 of the resolved executable file, not by its path
    or version string; `version`, `builtin_plugins` and `protocol_capabilities`
    are what that build must report in its own session initialization under
    the SDLC restrictions. The capabilities are the SDK control-protocol
    features the CLI would honour from a host over `--input-format
    stream-json`, which SDLC never opens; they are not model tools.
    """

    sha256: str
    version: str
    builtin_plugins: frozenset[str]
    protocol_capabilities: frozenset[str]


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
    # The operator-qualified build; None means no build is qualified, and a
    # family that requires one refuses to execute.
    qualified_binary: QualifiedBinary | None = None


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
        qualified_binary=_qualified_binary(name, defined.get(QUALIFIED_BINARY_KEY)),
    )


def _qualified_binary(name: str, table: object) -> QualifiedBinary | None:
    """`[model_runtime.runtimes.<name>.qualified_binary]`, validated whole."""
    if table is None:
        return None
    where = f"Runtime {name!r} {QUALIFIED_BINARY_KEY}"
    if not isinstance(table, dict):
        raise ModelRuntimeConfigError(f"{where} must be a table.")
    if set(table) != QUALIFIED_KEYS:
        raise ModelRuntimeConfigError(
            f"{where} must define exactly {sorted(QUALIFIED_KEYS)}."
        )
    sha256 = table[QUALIFIED_SHA256_KEY]
    if not isinstance(sha256, str) or not SHA256_PATTERN.match(sha256):
        raise ModelRuntimeConfigError(
            f"{where} {QUALIFIED_SHA256_KEY} must be 64 lowercase hex characters."
        )
    version = table[QUALIFIED_VERSION_KEY]
    if not isinstance(version, str) or not version.strip():
        raise ModelRuntimeConfigError(
            f"{where} {QUALIFIED_VERSION_KEY} must be non-empty text."
        )
    plugins = _distinct_names(table, QUALIFIED_PLUGINS_KEY, where)
    capabilities = _distinct_names(table, QUALIFIED_CAPABILITIES_KEY, where)
    return QualifiedBinary(sha256, version, plugins, capabilities)


def _distinct_names(table: dict[str, Any], key: str, where: str) -> frozenset[str]:
    values = table[key]
    if (
        not isinstance(values, list)
        or not all(isinstance(item, str) and item for item in values)
        or len(set(values)) != len(values)
    ):
        raise ModelRuntimeConfigError(
            f"{where} {key} must be a list of distinct names."
        )
    return frozenset(values)
