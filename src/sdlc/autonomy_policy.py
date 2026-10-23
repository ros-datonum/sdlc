"""The delegated-decision policy: the only authority for a Class C resolution.

Implements Requirement-Autonomous-Resolution-v0.1 section 3. A policy lives in
the SDLC runtime configuration, `config/sdlc.toml`, table `[autonomy]`: the
existing operator-controlled boundary that already decides which model
executes reasoning. Nothing else delegates a decision — not a Fibery Document,
whatever its name, and never a model's claim that something is approved.

Approval is the operator recording the exact fingerprint of the content they
approved under `mode = "enabled"`. Content that no longer hashes to that
fingerprint is refused when the configuration loads, so a policy cannot be
edited into a broader one without being approved again. The fingerprint is
SHA-256 over the canonical content: change detection, not a signature.

The default, and what this repository ships, is `mode = "disabled"`: no
Project has delegated defaults. A configuration without an `[autonomy]` table
is the same. The policy is read as each invocation or worker stage starts and
is immutable for that stage; a running worker never reuses it for the next one.

The same snapshot carries the operator's attestations of human decisions
(`[attestations]`, Requirement-Human-Attestation-v0.1), read from the same file
at the same moment. They are kept apart: an attestation is never a policy,
never a clause, and never part of a policy's fingerprint or identity.
"""

from __future__ import annotations

import hashlib
import json
import re
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from sdlc.config import ConfigurationError
from sdlc.human_attestation import (
    ATTESTATIONS_KEY,
    NO_ATTESTATIONS,
    HumanAttestationError,
    HumanAttestations,
    parse_human_attestations,
)
from sdlc.model_runtime_config import DEFAULT_CONFIG_PATH
from sdlc.project_code import InvalidProjectCode, validate_project_code

AUTONOMY_KEY = "autonomy"
MODE_KEY = "mode"
PROJECTS_KEY = "projects"
MODE_DISABLED = "disabled"
MODE_ENABLED = "enabled"
AUTONOMY_KEYS = frozenset({MODE_KEY, PROJECTS_KEY})
POLICY_KEYS = frozenset({"policy_id", "approved_by", "approved_fingerprint", "clauses"})
CLAUSE_KEYS = frozenset(
    {
        "clause_id",
        "applies_when",
        "permitted_decision",
        "boundaries",
        "exclusions",
        "evidence_required",
    }
)
CLAUSE_TEXT_KEYS = (
    "applies_when",
    "permitted_decision",
    "boundaries",
    "evidence_required",
)
BINDING_KEYS = frozenset({"policy_id", "fingerprint"})
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9._-]{0,63}$")
FINGERPRINT_PATTERN = re.compile(r"^[0-9a-f]{64}$")

#: Decisions no clause can delegate (section 2). Rendered as a non-overridable
#: exclusion of every clause; the policy schema has no key that lifts it.
HUMAN_ONLY_DOMAINS = (
    "security guarantees",
    "privacy and personal data",
    "legal or regulatory obligations",
    "financial commitments",
    "irreversible data loss",
    "major product scope",
    "a conflict between authoritative sources without an established resolution",
)


class AutonomyPolicyError(ConfigurationError):
    """The `[autonomy]` configuration is missing a rule or breaks one.

    A configuration error like any other: the command refuses before any
    Fibery read rather than running with a guessed delegation.
    """


@dataclass(frozen=True)
class PolicyClause:
    """One explicitly delegated class of low-risk decision."""

    clause_id: str
    applies_when: str
    permitted_decision: str
    boundaries: str
    exclusions: tuple[str, ...]
    evidence_required: str

    def to_payload(self) -> dict[str, object]:
        return {
            "clause_id": self.clause_id,
            "applies_when": self.applies_when,
            "permitted_decision": self.permitted_decision,
            "boundaries": self.boundaries,
            "exclusions": list(self.exclusions),
            "evidence_required": self.evidence_required,
        }


@dataclass(frozen=True)
class PolicyBinding:
    """Which policy content an artifact relied on: identity and fingerprint."""

    policy_id: str
    fingerprint: str

    def to_payload(self) -> dict[str, str]:
        return {"policy_id": self.policy_id, "fingerprint": self.fingerprint}

    @classmethod
    def from_payload(cls, value: object) -> PolicyBinding:
        """A persisted binding, or ValueError; never a best-effort read."""
        if (
            not isinstance(value, dict)
            or set(value) != BINDING_KEYS
            or not isinstance(value["policy_id"], str)
            or not IDENTIFIER_PATTERN.match(value["policy_id"])
            or not isinstance(value["fingerprint"], str)
            or not FINGERPRINT_PATTERN.match(value["fingerprint"])
        ):
            raise ValueError(f"Malformed autonomy policy binding: {value!r}")
        return cls(policy_id=value["policy_id"], fingerprint=value["fingerprint"])


@dataclass(frozen=True)
class AutonomyPolicy:
    """One Project's approved policy, exactly as it was approved."""

    project_code: str
    policy_id: str
    approved_by: str
    clauses: tuple[PolicyClause, ...]

    @property
    def fingerprint(self) -> str:
        return policy_fingerprint(self.project_code, self.policy_id, self.clauses)

    @property
    def binding(self) -> PolicyBinding:
        return PolicyBinding(policy_id=self.policy_id, fingerprint=self.fingerprint)

    def clause(self, clause_id: str) -> PolicyClause | None:
        return next(
            (clause for clause in self.clauses if clause.clause_id == clause_id), None
        )


def policy_fingerprint(
    project_code: str, policy_id: str, clauses: tuple[PolicyClause, ...]
) -> str:
    """SHA-256 of the canonical content: what an operator approves."""
    canonical = json.dumps(
        {
            "project_code": project_code,
            "policy_id": policy_id,
            "clauses": [clause.to_payload() for clause in clauses],
        },
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AutonomyPolicies:
    """Every approved policy, by Project code. Empty is default deny.

    `attestations` are the operator's attested human decisions, read in the
    same snapshot; they delegate nothing and no policy method consults them.
    """

    policies: tuple[AutonomyPolicy, ...] = ()
    attestations: HumanAttestations = NO_ATTESTATIONS

    def for_project(self, project_code: str | None) -> AutonomyPolicy | None:
        """The active policy of a Project, or None: Class C is unavailable."""
        return next(
            (
                policy
                for policy in self.policies
                if project_code and policy.project_code == project_code
            ),
            None,
        )

    def current(self, binding: PolicyBinding) -> AutonomyPolicy | None:
        """The active policy a binding names, only while its content is unchanged.

        None means the bound policy changed, was removed, or delegation was
        disabled: in every case the bound authority no longer exists.
        """
        return next(
            (
                policy
                for policy in self.policies
                if policy.policy_id == binding.policy_id
                and policy.fingerprint == binding.fingerprint
            ),
            None,
        )


#: No Project has delegated defaults.
DISABLED = AutonomyPolicies()


def load_autonomy_policies(path: Path | None = None) -> AutonomyPolicies:
    """Read `[autonomy]` from the runtime configuration, or refuse it whole."""
    config_path = DEFAULT_CONFIG_PATH if path is None else path
    try:
        raw = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise AutonomyPolicyError(
            f"No runtime configuration at {config_path}."
        ) from error
    except (OSError, UnicodeDecodeError) as error:
        # A running worker reads this file again as each stage starts (section
        # 3.4); an unreadable file refuses like any other broken configuration.
        raise AutonomyPolicyError(
            f"The runtime configuration at {config_path} cannot be read: "
            f"{type(error).__name__}."
        ) from error
    except tomllib.TOMLDecodeError as error:
        raise AutonomyPolicyError(
            f"{config_path} is not valid TOML: {error}"
        ) from error
    policies = parse_autonomy_policies(raw.get(AUTONOMY_KEY))
    try:
        attestations = parse_human_attestations(raw.get(ATTESTATIONS_KEY))
    except HumanAttestationError as error:
        # One refusal for the whole snapshot: a stage never runs on part of it.
        raise AutonomyPolicyError(str(error)) from error
    return replace(policies, attestations=attestations)


def parse_autonomy_policies(section: object) -> AutonomyPolicies:
    """The `[autonomy]` table as policies; absent means disabled."""
    if section is None:
        return DISABLED
    if not isinstance(section, dict):
        raise AutonomyPolicyError(f"[{AUTONOMY_KEY}] must be a table.")
    _reject_unknown(section, AUTONOMY_KEYS, f"[{AUTONOMY_KEY}]")
    mode = section.get(MODE_KEY)
    projects = section.get(PROJECTS_KEY)
    if mode == MODE_DISABLED:
        if projects:
            raise AutonomyPolicyError(
                f"[{AUTONOMY_KEY}] is {MODE_DISABLED!r} but names projects; "
                "a disabled configuration delegates nothing."
            )
        return DISABLED
    if mode != MODE_ENABLED:
        raise AutonomyPolicyError(
            f"[{AUTONOMY_KEY}] {MODE_KEY} must be {MODE_DISABLED!r} or "
            f"{MODE_ENABLED!r}, got {mode!r}."
        )
    if not isinstance(projects, dict) or not projects:
        raise AutonomyPolicyError(
            f"[{AUTONOMY_KEY}] is {MODE_ENABLED!r} but approves no project policy."
        )
    policies = tuple(
        _read_policy(code, entry) for code, entry in sorted(projects.items())
    )
    identities = [policy.policy_id for policy in policies]
    if len(set(identities)) != len(identities):
        raise AutonomyPolicyError("A policy_id is used by more than one project.")
    return AutonomyPolicies(policies)


def _read_policy(raw_code: str, entry: Any) -> AutonomyPolicy:
    where = f"[{AUTONOMY_KEY}.{PROJECTS_KEY}.{raw_code}]"
    try:
        code = validate_project_code(raw_code)
    except InvalidProjectCode as error:
        raise AutonomyPolicyError(f"{where}: {error}") from error
    if code != raw_code:
        raise AutonomyPolicyError(f"{where} must name the Project code exactly.")
    if not isinstance(entry, dict):
        raise AutonomyPolicyError(f"{where} must be a table.")
    _reject_unknown(entry, POLICY_KEYS, where)
    missing = sorted(POLICY_KEYS - set(entry))
    if missing:
        raise AutonomyPolicyError(f"{where} is missing: " + ", ".join(missing))
    policy_id = _identifier(entry["policy_id"], f"{where} policy_id")
    clauses = entry["clauses"]
    if not isinstance(clauses, list) or not clauses:
        raise AutonomyPolicyError(f"{where} must approve at least one clause.")
    policy = AutonomyPolicy(
        project_code=code,
        policy_id=policy_id,
        approved_by=_text(entry["approved_by"], f"{where} approved_by"),
        clauses=tuple(
            _read_clause(clause, f"{where} clause {index}")
            for index, clause in enumerate(clauses)
        ),
    )
    ids = [clause.clause_id for clause in policy.clauses]
    if len(set(ids)) != len(ids):
        raise AutonomyPolicyError(f"{where} repeats a clause_id.")
    approved = entry["approved_fingerprint"]
    if not isinstance(approved, str) or not FINGERPRINT_PATTERN.match(approved):
        raise AutonomyPolicyError(
            f"{where} approved_fingerprint must be 64 lowercase hex characters."
        )
    if policy.fingerprint != approved:
        raise AutonomyPolicyError(
            f"{where} content is not the content that was approved: its "
            f"fingerprint is {policy.fingerprint}, but approved_fingerprint is "
            f"{approved}. Changed delegation must be approved again."
        )
    return policy


def _read_clause(entry: Any, where: str) -> PolicyClause:
    if not isinstance(entry, dict):
        raise AutonomyPolicyError(f"{where} must be a table.")
    _reject_unknown(entry, CLAUSE_KEYS, where)
    missing = sorted(CLAUSE_KEYS - set(entry))
    if missing:
        raise AutonomyPolicyError(f"{where} is missing: " + ", ".join(missing))
    exclusions = entry["exclusions"]
    if not isinstance(exclusions, list):
        raise AutonomyPolicyError(f"{where} exclusions must be a list.")
    return PolicyClause(
        clause_id=_identifier(entry["clause_id"], f"{where} clause_id"),
        exclusions=tuple(
            _text(item, f"{where} exclusion {index}")
            for index, item in enumerate(exclusions)
        ),
        **{key: _text(entry[key], f"{where} {key}") for key in CLAUSE_TEXT_KEYS},
    )


def _reject_unknown(entry: dict, allowed: frozenset[str], where: str) -> None:
    unknown = sorted(set(entry) - allowed)
    if unknown:
        raise AutonomyPolicyError(
            f"{where} has keys the policy schema does not define: " + ", ".join(unknown)
        )


def _identifier(value: object, where: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER_PATTERN.match(value):
        raise AutonomyPolicyError(f"{where} must be an identifier.")
    return value


def _text(value: object, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AutonomyPolicyError(f"{where} must be non-empty text.")
    return value.strip()


def render_policy_section(policy: AutonomyPolicy | None) -> str:
    """The policy as a prompt section: its clauses, or why Class C is unavailable."""
    header = "# DELEGATED DECISION POLICY"
    domains = "; ".join(HUMAN_ONLY_DOMAINS)
    if policy is None:
        return (
            f"{header}\n(none approved for this Project: DELEGATED_DEFAULT is "
            "unavailable; a decision no source settles stays a product question)"
        )
    lines = [
        header,
        (
            f"Policy {policy.policy_id}, approved by {policy.approved_by}. A clause "
            "authorizes only what it states; it is never broadened or paraphrased."
        ),
        f"Every clause excludes, whatever it says: {domains}.",
    ]
    for clause in policy.clauses:
        lines += [
            f"[{clause.clause_id}]",
            f"  applies when: {clause.applies_when}",
            f"  permitted decision: {clause.permitted_decision}",
            f"  boundaries: {clause.boundaries}",
            "  exclusions: "
            + ("; ".join(clause.exclusions) if clause.exclusions else "(none stated)"),
            f"  evidence required: {clause.evidence_required}",
        ]
    return "\n".join(lines)
