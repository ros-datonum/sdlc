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


class DeniedEnvironmentName(ValueError):
    """Configuration asked to pass through a variable that can redirect the child."""


def is_denied(name: str) -> bool:
    """Whether `name` may never reach the child, regardless of configuration."""
    if name in CREDENTIAL_STORE_LOCATIONS:
        return False
    upper = name.upper()
    return upper.startswith(DENIED_PREFIXES) or upper.endswith(DENIED_SUFFIXES)


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
    parent: Mapping[str, str], extra: Sequence[str] = ()
) -> dict[str, str]:
    """Build the child's environment from an explicit allowlist.

    Only listed names present in `parent` are copied. `extra` is the
    configured passthrough list and is validated again here, so a definition
    built by hand cannot bypass the denylist either.
    """
    names = (*BASE_PASSTHROUGH, *CREDENTIAL_STORE_LOCATIONS, *require_allowed(extra))
    return {name: parent[name] for name in names if name in parent}
