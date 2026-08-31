"""RAW Requirement ID derivation.

Format is `<PROJECT_CODE>-RAW-<SEQUENCE>` per
Project-Requirement-Add-Spec-v0.2 section 7. This module is pure; uniqueness is
a Fibery property resolved by the caller.
"""

from __future__ import annotations

import re

RAW_INFIX = "RAW"
SEQUENCE_WIDTH = 4
FIRST_SEQUENCE = 1
# Four digits is the recommended presentation, not a ceiling: a project with
# more than 9999 RAW requirements simply widens the number.
MAX_PADDED_SEQUENCE = 10**SEQUENCE_WIDTH - 1


def raw_requirement_id(project_code: str, sequence: int) -> str:
    """Render one RAW Requirement ID."""
    if sequence < FIRST_SEQUENCE:
        raise ValueError(f"Sequence must be >= {FIRST_SEQUENCE}, got {sequence}.")
    rendered = (
        f"{sequence:0{SEQUENCE_WIDTH}d}"
        if sequence <= MAX_PADDED_SEQUENCE
        else str(sequence)
    )
    return f"{project_code}-{RAW_INFIX}-{rendered}"


def raw_id_prefix(project_code: str) -> str:
    return f"{project_code}-{RAW_INFIX}-"


def sequence_of(project_code: str, requirement_id: str) -> int | None:
    """Return the sequence a RAW id carries, or None if it is not one of ours."""
    pattern = re.compile(
        rf"^{re.escape(raw_id_prefix(project_code))}(?P<sequence>\d+)$"
    )
    match = pattern.match(requirement_id.strip())
    return int(match.group("sequence")) if match else None


def next_sequence(project_code: str, existing_ids: list[str]) -> int:
    """The lowest free sequence above every RAW id already in the Project.

    Allocation continues past gaps rather than filling them: a deleted
    Requirement must not have its identifier reused.
    """
    used = [
        sequence
        for sequence in (sequence_of(project_code, value) for value in existing_ids)
        if sequence is not None
    ]
    return max(used) + 1 if used else FIRST_SEQUENCE
