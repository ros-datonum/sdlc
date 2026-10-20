"""Ready delegation: the only authority for an automatic Ready decision.

Implements Requirement-Autonomous-Ready-v0.1 section 3. Delegation lives in
the SDLC runtime configuration, `config/sdlc.toml`, table `[ready_decisions]`,
next to and separate from `[autonomy]`. The two are different permissions:
an approved `[autonomy]` policy lets Process adopt a delegated product default
and authorizes no State transition; only an entry here lets the runner decide
at Ready, and only for the Project it names.

Approval is the operator recording the exact fingerprint of the authorization
they approved under `mode = "enabled"`. Content that no longer hashes to that
fingerprint is refused when the configuration loads. The fingerprint is
SHA-256 over the canonical content: change detection, not a signature, and
not proof that a human approved anything.

The default, and what this repository ships, is `mode = "disabled"`: no
Project has automatic Ready decisions. A configuration without the table is
the same. Every keyed limit must be stated; nothing here has a default value.
"""

from __future__ import annotations

import hashlib
import json
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sdlc.autonomy_policy import (
    FINGERPRINT_PATTERN,
    IDENTIFIER_PATTERN,
    MODE_DISABLED,
    MODE_ENABLED,
)
from sdlc.config import ConfigurationError
from sdlc.model_runtime_config import DEFAULT_CONFIG_PATH
from sdlc.project_code import InvalidProjectCode, validate_project_code

READY_KEY = "ready_decisions"
MODE_KEY = "mode"
PROJECTS_KEY = "projects"
READY_KEYS = frozenset({MODE_KEY, PROJECTS_KEY})
AUTHORIZATION_KEYS = frozenset(
    {
        "authorization_id",
        "approved_by",
        "approved_fingerprint",
        "auto_approve",
        "auto_rework",
        "max_rework_rounds",
        "max_issue_repeats",
    }
)
#: The most rework rounds any authorization may allow. A rework round is one
#: completed Review followed by another Process, whoever started it.
MAX_REWORK_ROUNDS_CEILING = 5
#: The most consecutive later Reviews that may report one open issue again.
MAX_ISSUE_REPEATS_CEILING = 2


class ReadyDelegationError(ConfigurationError):
    """The `[ready_decisions]` configuration is missing a rule or breaks one."""


@dataclass(frozen=True)
class ReadyAuthorizationBinding:
    """Which authorization a decision relied on: identity and fingerprint."""

    authorization_id: str
    fingerprint: str


@dataclass(frozen=True)
class ReadyAuthorization:
    """One Project's delegated Ready authority, exactly as it was approved."""

    project_code: str
    authorization_id: str
    approved_by: str
    auto_approve: bool
    auto_rework: bool
    max_rework_rounds: int
    max_issue_repeats: int

    @property
    def fingerprint(self) -> str:
        """SHA-256 of the canonical content: what an operator approves."""
        canonical = json.dumps(
            {
                "project_code": self.project_code,
                "authorization_id": self.authorization_id,
                "auto_approve": self.auto_approve,
                "auto_rework": self.auto_rework,
                "max_rework_rounds": self.max_rework_rounds,
                "max_issue_repeats": self.max_issue_repeats,
            },
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @property
    def binding(self) -> ReadyAuthorizationBinding:
        return ReadyAuthorizationBinding(self.authorization_id, self.fingerprint)


@dataclass(frozen=True)
class ReadyDelegation:
    """Every approved Ready authorization, by Project code. Empty is default deny."""

    authorizations: tuple[ReadyAuthorization, ...] = ()

    @property
    def is_enabled(self) -> bool:
        return bool(self.authorizations)

    @property
    def identity(self) -> tuple[ReadyAuthorizationBinding, ...]:
        """What a decision made under this snapshot depends on, and nothing else.

        `approved_by` is outside the fingerprint and outside the identity.
        """
        return tuple(authorization.binding for authorization in self.authorizations)

    def for_project(self, project_code: str | None) -> ReadyAuthorization | None:
        """The Project's authorization, or None: Ready stays a human boundary."""
        return next(
            (
                authorization
                for authorization in self.authorizations
                if project_code and authorization.project_code == project_code
            ),
            None,
        )


#: No Project has automatic Ready decisions.
NOT_DELEGATED = ReadyDelegation()


def load_ready_delegation(path: Path | None = None) -> ReadyDelegation:
    """Read `[ready_decisions]` from the runtime configuration, or refuse it whole."""
    config_path = DEFAULT_CONFIG_PATH if path is None else path
    try:
        raw = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ReadyDelegationError(
            f"No runtime configuration at {config_path}."
        ) from error
    except (OSError, UnicodeDecodeError) as error:
        raise ReadyDelegationError(
            f"The runtime configuration at {config_path} cannot be read: "
            f"{type(error).__name__}."
        ) from error
    except tomllib.TOMLDecodeError as error:
        raise ReadyDelegationError(
            f"{config_path} is not valid TOML: {error}"
        ) from error
    return parse_ready_delegation(raw.get(READY_KEY))


def parse_ready_delegation(section: object) -> ReadyDelegation:
    """The `[ready_decisions]` table as authorizations; absent means disabled."""
    if section is None:
        return NOT_DELEGATED
    if not isinstance(section, dict):
        raise ReadyDelegationError(f"[{READY_KEY}] must be a table.")
    _reject_unknown(section, READY_KEYS, f"[{READY_KEY}]")
    mode = section.get(MODE_KEY)
    projects = section.get(PROJECTS_KEY)
    if mode == MODE_DISABLED:
        if projects:
            raise ReadyDelegationError(
                f"[{READY_KEY}] is {MODE_DISABLED!r} but names projects; a "
                "disabled configuration delegates nothing."
            )
        return NOT_DELEGATED
    if mode != MODE_ENABLED:
        raise ReadyDelegationError(
            f"[{READY_KEY}] {MODE_KEY} must be {MODE_DISABLED!r} or "
            f"{MODE_ENABLED!r}, got {mode!r}."
        )
    if not isinstance(projects, dict) or not projects:
        raise ReadyDelegationError(
            f"[{READY_KEY}] is {MODE_ENABLED!r} but authorizes no project."
        )
    authorizations = tuple(
        _read_authorization(code, entry) for code, entry in sorted(projects.items())
    )
    identities = [authorization.authorization_id for authorization in authorizations]
    if len(set(identities)) != len(identities):
        raise ReadyDelegationError(
            "An authorization_id is used by more than one project."
        )
    return ReadyDelegation(authorizations)


def _read_authorization(raw_code: str, entry: Any) -> ReadyAuthorization:
    where = f"[{READY_KEY}.{PROJECTS_KEY}.{raw_code}]"
    try:
        code = validate_project_code(raw_code)
    except InvalidProjectCode as error:
        raise ReadyDelegationError(f"{where}: {error}") from error
    if code != raw_code:
        raise ReadyDelegationError(f"{where} must name the Project code exactly.")
    if not isinstance(entry, dict):
        raise ReadyDelegationError(f"{where} must be a table.")
    _reject_unknown(entry, AUTHORIZATION_KEYS, where)
    missing = sorted(AUTHORIZATION_KEYS - set(entry))
    if missing:
        raise ReadyDelegationError(f"{where} is missing: " + ", ".join(missing))
    authorization = ReadyAuthorization(
        project_code=code,
        authorization_id=_identifier(entry["authorization_id"], where),
        approved_by=_text(entry["approved_by"], f"{where} approved_by"),
        auto_approve=_flag(entry["auto_approve"], f"{where} auto_approve"),
        auto_rework=_flag(entry["auto_rework"], f"{where} auto_rework"),
        max_rework_rounds=_bounded(
            entry["max_rework_rounds"],
            f"{where} max_rework_rounds",
            1,
            MAX_REWORK_ROUNDS_CEILING,
        ),
        max_issue_repeats=_bounded(
            entry["max_issue_repeats"],
            f"{where} max_issue_repeats",
            0,
            MAX_ISSUE_REPEATS_CEILING,
        ),
    )
    if not authorization.auto_approve and not authorization.auto_rework:
        raise ReadyDelegationError(
            f"{where} delegates neither auto_approve nor auto_rework; remove it."
        )
    approved = entry["approved_fingerprint"]
    if not isinstance(approved, str) or not FINGERPRINT_PATTERN.match(approved):
        raise ReadyDelegationError(
            f"{where} approved_fingerprint must be 64 lowercase hex characters."
        )
    if authorization.fingerprint != approved:
        raise ReadyDelegationError(
            f"{where} content is not the content that was approved: its "
            f"fingerprint is {authorization.fingerprint}, but approved_fingerprint "
            f"is {approved}. Changed delegation must be approved again."
        )
    return authorization


def _reject_unknown(entry: dict, allowed: frozenset[str], where: str) -> None:
    unknown = sorted(set(entry) - allowed)
    if unknown:
        raise ReadyDelegationError(
            f"{where} has keys the Ready delegation schema does not define: "
            + ", ".join(unknown)
        )


def _identifier(value: object, where: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER_PATTERN.match(value):
        raise ReadyDelegationError(f"{where} authorization_id must be an identifier.")
    return value


def _text(value: object, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReadyDelegationError(f"{where} must be non-empty text.")
    return value.strip()


def _flag(value: object, where: str) -> bool:
    if not isinstance(value, bool):
        raise ReadyDelegationError(f"{where} must be true or false.")
    return value


def _bounded(value: object, where: str, low: int, high: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not low <= value <= high
    ):
        raise ReadyDelegationError(
            f"{where} must be a whole number from {low} to {high}, got {value!r}."
        )
    return value
