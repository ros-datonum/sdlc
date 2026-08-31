"""Project Code derivation and validation.

Project-Init-Spec-v0.3 section 6 requires Project Codes to be globally unique,
immutable, uppercase alphanumeric and human readable, and recommends (but does
not mandate) a length of 3-6 characters. Uniqueness is a Fibery property and is
resolved by the caller; this module is pure and deterministic.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

PROJECT_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*$")

# The spec's 3-6 range is a recommendation, so it bounds *generation* only.
# The hard limit below only keeps a code short enough to prefix Requirement,
# Milestone, Epic, User Story and Task identifiers.
PROJECT_CODE_MAX_LENGTH = 12
GENERATED_CODE_MIN_LENGTH = 3
GENERATED_CODE_MAX_LENGTH = 6

# Suffixes tried when a derived code is already taken: CODE2 .. CODE99.
COLLISION_SUFFIX_START = 2
COLLISION_SUFFIX_LIMIT = 100

_WORD_PATTERN = re.compile(r"[A-Z0-9]+")


class InvalidProjectCode(ValueError):
    """A Project Code does not satisfy the format rules."""


class UnusableProjectName(ValueError):
    """A Project Name contains nothing a Project Code can be derived from."""


def normalize_project_code(raw: str) -> str:
    """Apply the only normalisation the spec allows: trim and uppercase."""
    return raw.strip().upper()


def validate_project_code(raw: str) -> str:
    """Return the normalized code, or raise InvalidProjectCode."""
    code = normalize_project_code(raw)
    if not code:
        raise InvalidProjectCode("Project Code must not be empty.")
    if len(code) > PROJECT_CODE_MAX_LENGTH:
        raise InvalidProjectCode(
            f"Project Code {code!r} is longer than "
            f"{PROJECT_CODE_MAX_LENGTH} characters."
        )
    if not PROJECT_CODE_PATTERN.match(code):
        raise InvalidProjectCode(
            f"Project Code {code!r} must be uppercase alphanumeric and start "
            "with a letter."
        )
    return code


def derive_project_code(project_name: str) -> str:
    """Derive the first candidate code for a Project Name.

    Multi-word names become the initials of their words; names whose initials
    are too short, and single-word names, are truncated instead.
    """
    words = [
        word
        for word in _WORD_PATTERN.findall(project_name.upper())
        if word[0].isalpha()
    ]
    if not words:
        raise UnusableProjectName(
            f"No Project Code can be derived from {project_name!r}."
        )

    if len(words) > 1:
        initials = "".join(word[0] for word in words)
        base = (
            initials
            if len(initials) >= GENERATED_CODE_MIN_LENGTH
            else words[0][:GENERATED_CODE_MIN_LENGTH]
        )
    else:
        base = words[0]

    return base[:GENERATED_CODE_MAX_LENGTH]


def candidate_project_codes(project_name: str) -> Iterator[str]:
    """Yield the derived code, then collision-resolved variants of it.

    The sequence is finite: exhausting it means PROJECT_CODE_COLLISION.
    """
    base = derive_project_code(project_name)
    yield base
    for suffix in range(COLLISION_SUFFIX_START, COLLISION_SUFFIX_LIMIT):
        marker = str(suffix)
        stem = base[: GENERATED_CODE_MAX_LENGTH - len(marker)]
        if not stem:
            return
        yield f"{stem}{marker}"
