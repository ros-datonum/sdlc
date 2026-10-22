"""The environment a reasoning child process is allowed to see.

The SDLC application runs inside a developer shell that holds unrelated
secrets: the Fibery token, cloud credentials, provider API keys, the settings
of an enclosing Claude Code session. None of that belongs to the model child.
The child gets an explicit minimal environment: what the installed CLI needs
to start and to find its own locally stored login, and nothing else.

Provider, base-URL and API-key variables are excluded by construction, so a
key exported in the shell can never redirect the child away from the user's
subscription login. Configuration may add names to the passthrough list, but
never one of those.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

# What a CLI needs to start: program lookup, the home directory holding its
# login state, temp space and locale.
BASE_PASSTHROUGH = (
    "PATH",
    "HOME",
    "USER",
    "LOGNAME",
    "TMPDIR",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TERM",
)

# Where a CLI keeps its login when the user relocated it. Passed through so
# the child finds the same login the interactive CLI uses.
CREDENTIAL_STORE_LOCATIONS = ("CLAUDE_CONFIG_DIR", "CODEX_HOME")

# Never passed through, not even when configuration lists them: provider
# routing, API keys, enclosing-session state and application secrets.
DENIED_PREFIXES = (
    "ANTHROPIC_",
    "OPENAI_",
    "CLAUDE",
    "CODEX_",
    "AWS_",
    "GOOGLE_",
    "AZURE_",
    "FIBERY_",
)
DENIED_SUFFIXES = ("_API_KEY", "_TOKEN", "_SECRET", "_BASE_URL")

# Values the runtime itself sets in a child of one CLI family, after the
# allowlist (Local-OAuth-Model-Runtime-Claude-2.1.306-Amendment-v0.1 §3). They
# are code constants: never copied from the parent, never listed by
# configuration, and never overridden by a parent value of the same name.
# DISABLE_TELEMETRY: Claude Code's own analytics switch; on 2.1.306 it keeps
# the built-in telemetry plugin unregistered and the core event logger off.
# CLAUDE_CODE_DISABLE_ATTACHMENTS: on 2.1.306 the attachment builder returns
# before any `@` mention in the input is extracted or read, so untrusted text
# can never pull a local file into the model's context (amendment §7).
# CLAUDE_CODE_DISABLE_FILE_MENTIONS: defence in depth; a mention that still
# reached the reader would get a path reference instead of a fresh file read.
FIXED_CHILD_ENVIRONMENT: dict[str, dict[str, str]] = {
    "print": {
        "DISABLE_TELEMETRY": "1",
        "CLAUDE_CODE_DISABLE_ATTACHMENTS": "1",
        "CLAUDE_CODE_DISABLE_FILE_MENTIONS": "1",
    },
    "exec": {},
}
FIXED_NAMES = frozenset(
    name for values in FIXED_CHILD_ENVIRONMENT.values() for name in values
)


class DeniedEnvironmentName(ValueError):
    """Configuration asked to pass through a variable that can redirect the child."""


def is_denied(name: str) -> bool:
    """Whether `name` may never be passed through, regardless of configuration.

    A fixed child value is denied too: the runtime sets it, nothing passes it.
    """
    if name in CREDENTIAL_STORE_LOCATIONS:
        return False
    upper = name.upper()
    return (
        upper.startswith(DENIED_PREFIXES)
        or upper.endswith(DENIED_SUFFIXES)
        or upper in FIXED_NAMES
    )


def require_allowed(names: Sequence[str]) -> tuple[str, ...]:
    """Validate configured extra passthrough names; refuse any denied one."""
    denied = [name for name in names if is_denied(name)]
    if denied:
        raise DeniedEnvironmentName(
            "These variables can redirect or leak into the model child and cannot "
            f"be passed through: {', '.join(sorted(denied))}."
        )
    return tuple(names)


def child_environment(
    parent: Mapping[str, str], extra: Sequence[str] = (), fixed_for: str | None = None
) -> dict[str, str]:
    """Build the child's environment from an explicit allowlist.

    Only listed names present in `parent` are copied. `extra` is the
    configured passthrough list and is validated again here, so a definition
    built by hand cannot bypass the denylist either. `fixed_for` names the CLI
    family whose fixed values are then set, last, so no parent value of the
    same name can reach the child.
    """
    names = (*BASE_PASSTHROUGH, *CREDENTIAL_STORE_LOCATIONS, *require_allowed(extra))
    env = {name: parent[name] for name in names if name in parent}
    if fixed_for is not None:
        # An unknown family has no fixed values; it is refused before any
        # process starts (model_runtime).
        env.update(FIXED_CHILD_ENVIRONMENT.get(fixed_for, {}))
    return env
