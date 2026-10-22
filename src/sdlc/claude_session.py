"""Validation of a Claude Code reasoning child's stream-json session.

Implements Local-OAuth-Model-Runtime-Claude-2.1.306-Amendment-v0.1 §4. The
SDLC child runs `claude -p ... --output-format stream-json --verbose`, so its
stdout is one JSON event per line: the session's own `system/init` record,
the assistant turn, and one final `result`. The model's answer is returned
only after the whole stream is shown to be the session the operator
qualified:

- one `system/init`, before any assistant or result event, for this working
  directory and this build, with exactly the qualified built-in plugins and
  SDK control-protocol capabilities, no tool, MCP server, skill, slash
  command, memory path, extra directory, plugin error or API-key source, and
  with analytics reported disabled;
- every event of the closed allowlist below and of that session;
- assistant content of text and thinking only, never a tool call;
- one successful `result`, last, carrying non-empty text.

Anything else is refused. The schema is closed on purpose: an event type
this build was not qualified with is evidence of a different session, not
noise. A refusal names a fixed reason code and, at most, field names and
plugin identifiers; it never quotes the prompt, the model's text or any
other received value.

`SessionValidator.feed` accepts one line at a time so a runner can stop the
child at the first violation; `finish` returns the answer. Validating the
complete stdout with a fresh validator is the authoritative check either way.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

# The reasoning child's stream-json output, on the CLI's command line after
# the restrictions. Output format only: no restriction depends on it.
STREAM_OUTPUT_FLAGS = ("--output-format", "stream-json", "--verbose")

# Event types a qualified tool-less one-turn session emits. `system` events are
# allowed by subtype only; everything else, `user` (tool results, attachments)
# and `stream_event` included, is refused.
SYSTEM_TYPE = "system"
ASSISTANT_TYPE = "assistant"
RESULT_TYPE = "result"
RATE_LIMIT_TYPE = "rate_limit_event"
ALLOWED_TYPES = frozenset({SYSTEM_TYPE, ASSISTANT_TYPE, RESULT_TYPE, RATE_LIMIT_TYPE})
INIT_SUBTYPE = "init"
# Lifecycle notices with no capability: token accounting, a transient API
# retry, turn timing and status. Hook, memory, attachment, permission, task,
# tool-host, model-fallback and command subtypes are deliberately absent.
ALLOWED_SYSTEM_SUBTYPES = frozenset(
    {INIT_SUBTYPE, "thinking_tokens", "api_retry", "status", "turn_duration"}
)
ALLOWED_CONTENT_TYPES = frozenset({"text", "thinking", "redacted_thinking"})
RESULT_SUCCESS_SUBTYPE = "success"

# init fields that must be present and empty, and fields that must be absent
# or empty: any of them non-empty is a capability the boundary excludes.
EMPTY_INIT_LISTS = ("tools", "mcp_servers", "skills", "slash_commands")
ABSENT_INIT_FIELDS = (
    "terminal_slash_commands",
    "plugin_errors",
    "plugin_warnings",
    "mcp_server_errors",
    "memory_paths",
    "additional_directories",
)
REQUIRED_API_KEY_SOURCE = "none"
BUILTIN_PLUGIN_PATH = "builtin"
BUILTIN_SOURCE_SUFFIX = "@builtin"
# Plugin identifiers are named in a refusal only when they look like one.
REPORTABLE_NAME = re.compile(r"^[a-z0-9][a-z0-9._@-]{0,63}$")


class SessionRejected(Exception):
    """The child's stream is not the qualified session; its answer is discarded.

    `code` is a fixed reason; the message carries no received content.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass(frozen=True)
class ExpectedSession:
    """What this one invocation's session must report about itself."""

    cwd: str
    version: str
    builtin_plugins: frozenset[str]
    protocol_capabilities: frozenset[str]


class SessionValidator:
    """Checks one child's stream-json events in order."""

    def __init__(self, expected: ExpectedSession) -> None:
        self._expected = expected
        self._session_id: str | None = None
        self._answer: str | None = None
        self._events = 0

    def feed(self, line: str) -> None:
        """Check one stdout line; raise SessionRejected at the first violation."""
        if not line.strip():
            return
        if self._answer is not None:
            raise SessionRejected("EVENT_AFTER_RESULT", "an event followed the result.")
        try:
            event = json.loads(line)
        except ValueError as error:
            raise SessionRejected(
                "MALFORMED_EVENT", "a stdout line is not a JSON event."
            ) from error
        if not isinstance(event, dict):
            raise SessionRejected("MALFORMED_EVENT", "an event is not a JSON object.")
        self._events += 1
        kind = event.get("type")
        if kind not in ALLOWED_TYPES:
            raise SessionRejected(
                "UNEXPECTED_EVENT", f"event type {_reportable(kind)} is not allowed."
            )
        if kind == SYSTEM_TYPE:
            self._system(event)
        elif self._session_id is None:
            raise SessionRejected(
                "INIT_MISSING", "an event arrived before the session init record."
            )
        self._same_session(event)
        if kind == ASSISTANT_TYPE:
            _assistant(event)
        elif kind == RESULT_TYPE:
            self._answer = _result(event)

    def finish(self) -> str:
        """The model's answer, once the whole stream has been accepted."""
        if self._session_id is None:
            raise SessionRejected(
                "INIT_MISSING", "the stream has no session init record."
            )
        if self._answer is None:
            raise SessionRejected("RESULT_MISSING", "the stream has no final result.")
        return self._answer

    def _system(self, event: dict[str, Any]) -> None:
        subtype = event.get("subtype")
        if subtype not in ALLOWED_SYSTEM_SUBTYPES:
            raise SessionRejected(
                "UNEXPECTED_EVENT",
                f"system subtype {_reportable(subtype)} is not allowed.",
            )
        if subtype != INIT_SUBTYPE:
            if self._session_id is None:
                raise SessionRejected(
                    "INIT_MISSING", "a system event arrived before the init record."
                )
            return
        if self._session_id is not None:
            raise SessionRejected(
                "INIT_DUPLICATED", "the stream has a second init record."
            )
        self._session_id = _init(event, self._expected)

    def _same_session(self, event: dict[str, Any]) -> None:
        if "session_id" in event and event["session_id"] != self._session_id:
            raise SessionRejected(
                "SESSION_MISMATCH", "an event belongs to another session."
            )


def validate_stream(stdout: str, expected: ExpectedSession) -> str:
    """Validate a complete stdout and return the answer, or raise SessionRejected."""
    validator = SessionValidator(expected)
    # Events are newline-delimited: split on "\n" only. str.splitlines would
    # also split on U+2028, U+2029 and U+0085, which JSON leaves raw inside
    # strings, and refuse a legitimate answer quoting one.
    for line in stdout.split("\n"):
        validator.feed(line)
    return validator.finish()


def _init(event: dict[str, Any], expected: ExpectedSession) -> str:
    """The init record's session id, once every security field is as qualified."""
    session_id = event.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        raise SessionRejected("INIT_INVALID", "the init record has no session id.")
    if event.get("cwd") != expected.cwd:
        raise SessionRejected(
            "INIT_INVALID", "the init record is not for this invocation's directory."
        )
    if event.get("claude_code_version") != expected.version:
        raise SessionRejected(
            "BINARY_NOT_QUALIFIED", "the session reports a build that is not qualified."
        )
    for field in EMPTY_INIT_LISTS:
        if event.get(field) != []:
            raise SessionRejected(
                "CAPABILITY_EXPOSED", f"the session exposes {field} (must be empty)."
            )
    for field in ABSENT_INIT_FIELDS:
        if event.get(field) not in (None, [], {}):
            raise SessionRejected(
                "CAPABILITY_EXPOSED", f"the session reports {field} (must be absent)."
            )
    if event.get("apiKeySource") != REQUIRED_API_KEY_SOURCE:
        raise SessionRejected(
            "AUTHENTICATION_NOT_QUALIFIED", "the session uses an API-key source."
        )
    if event.get("analytics_disabled") is not True:
        raise SessionRejected(
            "TELEMETRY_NOT_DISABLED", "the session does not report analytics disabled."
        )
    _plugins(event.get("plugins"), expected.builtin_plugins)
    _capabilities(event.get("capabilities"), expected.protocol_capabilities)
    return session_id


def _plugins(plugins: object, qualified: frozenset[str]) -> None:
    """Exactly the qualified built-in plugins, each loaded as built-in."""
    if not isinstance(plugins, list) or not all(isinstance(p, dict) for p in plugins):
        raise SessionRejected("INIT_INVALID", "the init record has no plugin list.")
    names = [p.get("name") for p in plugins]
    for plugin, name in zip(plugins, names, strict=True):
        if (
            not isinstance(name, str)
            or plugin.get("path") != BUILTIN_PLUGIN_PATH
            or plugin.get("source") != f"{name}{BUILTIN_SOURCE_SUFFIX}"
        ):
            raise SessionRejected(
                "PLUGIN_NOT_QUALIFIED",
                f"plugin {_reportable(name)} is not loaded as a built-in plugin.",
            )
    if len(set(names)) != len(names):
        raise SessionRejected("PLUGIN_NOT_QUALIFIED", "a plugin is listed twice.")
    unexpected = sorted(set(names) - qualified)
    missing = sorted(qualified - set(names))
    if unexpected or missing:
        raise SessionRejected(
            "PLUGIN_NOT_QUALIFIED",
            "the plugin set is not the qualified one: unexpected "
            f"{[_reportable(n) for n in unexpected]}, missing {missing}.",
        )


def _capabilities(capabilities: object, qualified: frozenset[str]) -> None:
    """Exactly the qualified SDK control-protocol capabilities, no more, no fewer.

    They are what the CLI would accept from an SDK host over `--input-format
    stream-json`; SDLC never opens that channel, so none of them can be
    exercised. A changed set means a different build or remote configuration,
    which needs its own qualification.
    """
    if not isinstance(capabilities, list) or not all(
        isinstance(item, str) for item in capabilities
    ):
        raise SessionRejected(
            "INIT_INVALID", "the init record has no protocol capability list."
        )
    if len(set(capabilities)) != len(capabilities):
        raise SessionRejected(
            "CAPABILITY_NOT_QUALIFIED", "a capability is listed twice."
        )
    unexpected = sorted(set(capabilities) - qualified)
    missing = sorted(qualified - set(capabilities))
    if unexpected or missing:
        raise SessionRejected(
            "CAPABILITY_NOT_QUALIFIED",
            "the protocol capability set is not the qualified one: unexpected "
            f"{[_reportable(c) for c in unexpected]}, missing {missing}.",
        )


def _assistant(event: dict[str, Any]) -> None:
    message = event.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list):
        raise SessionRejected(
            "MALFORMED_EVENT", "an assistant event has no content list."
        )
    for item in content:
        kind = item.get("type") if isinstance(item, dict) else None
        if kind not in ALLOWED_CONTENT_TYPES:
            raise SessionRejected(
                "TOOL_USE_ATTEMPTED"
                if isinstance(kind, str) and "tool_use" in kind
                else "UNEXPECTED_EVENT",
                f"assistant content {_reportable(kind)} is not allowed.",
            )


def _result(event: dict[str, Any]) -> str:
    if (
        event.get("subtype") != RESULT_SUCCESS_SUBTYPE
        or event.get("is_error") is not False
    ):
        raise SessionRejected(
            "RESULT_NOT_SUCCESS", "the session did not end in success."
        )
    answer = event.get("result")
    if not isinstance(answer, str) or not answer.strip():
        raise SessionRejected("RESULT_EMPTY", "the session ended without an answer.")
    return answer


def _reportable(value: object) -> str:
    """A received identifier as it may appear in a refusal, or a placeholder."""
    return (
        repr(value)
        if isinstance(value, str) and REPORTABLE_NAME.match(value)
        else "(unrecognized)"
    )
