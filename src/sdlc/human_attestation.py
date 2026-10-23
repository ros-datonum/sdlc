"""Operator attestations: the only proof that Requirement text is a human decision.

Implements Requirement-Human-Attestation-v0.1. A Requirement's normative text
is either what an earlier Process iteration wrote or what someone edited into
it between iterations, and nothing persisted tells the two apart: Fibery
records no author for Document content, and the SDLC writes with the
operator's own account. A textual difference between a Process output and a
later input proves only that no Process iteration wrote it, not that a human
decided it.

An attestation is the operator recording, in the SDLC runtime configuration
(`config/sdlc.toml`, table `[attestations]`), the exact text they decided for
one Requirement, bound to its Project, Requirement ID and entity id, with the
SHA-256 fingerprint of that content. It is the same operator-controlled
boundary that approves an autonomy policy, and like it it is change
detection, not a signature. It settles who decided; whether the text answers
the question is still the independent Reviewer's judgement.

An attestation is never a delegated policy, never a DELEGATED_DEFAULT and
never part of a policy's identity: it travels in the same per-stage
configuration snapshot only so every stage reads it at the same moment.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from sdlc.config import ConfigurationError
from sdlc.project_code import InvalidProjectCode, validate_project_code

ATTESTATIONS_KEY = "attestations"
CLARIFICATIONS_KEY = "clarifications"
ATTESTATIONS_TABLE_KEYS = frozenset({CLARIFICATIONS_KEY})
CLARIFICATION_KEYS = frozenset(
    {
        "project_code",
        "requirement_id",
        "entity_id",
        "text",
        "approved_by",
        "approved_fingerprint",
    }
)
ENTITY_ID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
FINGERPRINT_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class HumanAttestationError(ConfigurationError):
    """The `[attestations]` configuration is missing a rule or breaks one.

    Refused whole, before any Fibery read, like a broken autonomy policy:
    a stage never runs with a guessed attestation.
    """


@dataclass(frozen=True)
class HumanAttestation:
    """One operator-decided text for one Requirement, exactly as approved."""

    project_code: str
    requirement_id: str
    entity_id: str
    text: str
    approved_by: str

    @property
    def fingerprint(self) -> str:
        return attestation_fingerprint(
            self.project_code, self.requirement_id, self.entity_id, self.text
        )


def attestation_fingerprint(
    project_code: str, requirement_id: str, entity_id: str, text: str
) -> str:
    """SHA-256 of the canonical content: what the operator approves."""
    canonical = json.dumps(
        {
            "project_code": project_code,
            "requirement_id": requirement_id,
            "entity_id": entity_id,
            "text": text,
        },
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class HumanAttestations:
    """Every attestation in the configuration. Empty attests nothing."""

    attestations: tuple[HumanAttestation, ...] = ()

    def for_requirement(
        self, entity_id: str, requirement_id: str
    ) -> tuple[HumanAttestation, ...]:
        """The attestations of exactly this Requirement: entity and ID both match.

        An attestation names one Requirement; it never authorizes another,
        not one with the same ID under a different entity, nor the reverse.
        """
        return tuple(
            attestation
            for attestation in self.attestations
            if attestation.entity_id == entity_id
            and attestation.requirement_id == requirement_id
        )


#: Nothing is attested.
NO_ATTESTATIONS = HumanAttestations()


def parse_human_attestations(section: object) -> HumanAttestations:
    """The `[attestations]` table; absent means nothing is attested."""
    if section is None:
        return NO_ATTESTATIONS
    where = f"[{ATTESTATIONS_KEY}]"
    if not isinstance(section, dict):
        raise HumanAttestationError(f"{where} must be a table.")
    _reject_unknown(section, ATTESTATIONS_TABLE_KEYS, where)
    entries = section.get(CLARIFICATIONS_KEY, [])
    if not isinstance(entries, list):
        raise HumanAttestationError(
            f"{where} {CLARIFICATIONS_KEY} must be an array of tables."
        )
    attestations = tuple(
        _read_clarification(entry, f"{where} {CLARIFICATIONS_KEY} {index}")
        for index, entry in enumerate(entries)
    )
    fingerprints = [attestation.fingerprint for attestation in attestations]
    if len(set(fingerprints)) != len(fingerprints):
        raise HumanAttestationError(f"{where} repeats an attestation.")
    return HumanAttestations(attestations)


def _read_clarification(entry: Any, where: str) -> HumanAttestation:
    if not isinstance(entry, dict):
        raise HumanAttestationError(f"{where} must be a table.")
    _reject_unknown(entry, CLARIFICATION_KEYS, where)
    missing = sorted(CLARIFICATION_KEYS - set(entry))
    if missing:
        raise HumanAttestationError(f"{where} is missing: " + ", ".join(missing))
    raw_code = entry["project_code"]
    if not isinstance(raw_code, str):
        raise HumanAttestationError(f"{where} project_code must be text.")
    try:
        code = validate_project_code(raw_code)
    except InvalidProjectCode as error:
        raise HumanAttestationError(f"{where} project_code: {error}") from error
    if code != raw_code:
        raise HumanAttestationError(f"{where} must name the Project code exactly.")
    requirement_id = _text(entry["requirement_id"], f"{where} requirement_id")
    if not requirement_id.startswith(f"{code}-"):
        raise HumanAttestationError(
            f"{where} requirement_id {requirement_id!r} is not a Requirement of "
            f"Project {code}."
        )
    entity_id = entry["entity_id"]
    if not isinstance(entity_id, str) or not ENTITY_ID_PATTERN.match(entity_id):
        raise HumanAttestationError(f"{where} entity_id must be a lowercase UUID.")
    attestation = HumanAttestation(
        project_code=code,
        requirement_id=requirement_id,
        entity_id=entity_id,
        text=_text(entry["text"], f"{where} text"),
        approved_by=_text(entry["approved_by"], f"{where} approved_by"),
    )
    approved = entry["approved_fingerprint"]
    if not isinstance(approved, str) or not FINGERPRINT_PATTERN.match(approved):
        raise HumanAttestationError(
            f"{where} approved_fingerprint must be 64 lowercase hex characters."
        )
    if attestation.fingerprint != approved:
        raise HumanAttestationError(
            f"{where} content is not the content that was approved: its "
            f"fingerprint is {attestation.fingerprint}, but approved_fingerprint is "
            f"{approved}. A changed decision must be approved again."
        )
    return attestation


def _reject_unknown(entry: dict, allowed: frozenset[str], where: str) -> None:
    unknown = sorted(set(entry) - allowed)
    if unknown:
        raise HumanAttestationError(
            f"{where} has keys the attestation schema does not define: "
            + ", ".join(unknown)
        )


def _text(value: object, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HumanAttestationError(f"{where} must be non-empty text.")
    return value.strip()


def render_attestation_section(attestations: tuple[HumanAttestation, ...]) -> str:
    """This Requirement's attested texts as a prompt section, or that there are none."""
    header = "# OPERATOR-ATTESTED CLARIFICATIONS"
    if not attestations:
        return (
            f"{header}\n(none: no text of this Requirement is attested as a human "
            "decision)"
        )
    lines = [
        header,
        (
            "Code verified that the operator's configuration attests each text "
            "below, exactly, as a human decision for this Requirement. It "
            "establishes who decided, not that the decision is correct or "
            "consistent."
        ),
    ]
    for attestation in attestations:
        lines += [
            (
                f"[attested by {attestation.approved_by}, "
                f"fingerprint {attestation.fingerprint[:12]}]"
            ),
            attestation.text,
        ]
    return "\n".join(lines)
