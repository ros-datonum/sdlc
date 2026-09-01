"""RAW Requirement ID derivation.

The numeric component is Fibery's `fibery/public-id`, which Fibery allocates
atomically when the entity is created. Two concurrent writers therefore receive
different public ids and cannot derive the same Requirement ID.

Deriving the number instead of counting existing Requirements is what makes the
identifier safe: an allocator that reads the highest id in use and adds one has
a read-then-write race that no amount of post-write checking can close.
Numbering is consequently sparse per Project, which
Project-Requirement-Add-Spec-v0.3 section 7 accepts.
"""

from __future__ import annotations

RAW_INFIX = "RAW"
# Presentation width, not a ceiling. Larger public ids keep all their digits.
MINIMUM_DIGITS = 4


class InvalidPublicId(ValueError):
    """Fibery returned a public id that is not the expected numeric form."""


def namespaced_requirement_id(project_code: str, infix: str, public_id: str) -> str:
    """Render `<PROJECT_CODE>-<INFIX>-<public id>`, zero padded to four digits.

    The infix names the kind of Requirement: RAW for ingested artifacts, and
    FR / NFR / CON for the Standard Requirements a RAW decomposes into.
    """
    digits = (public_id or "").strip()
    if not digits.isdigit():
        raise InvalidPublicId(
            f"Fibery public id {public_id!r} is not numeric, so no "
            "Requirement ID can be derived from it."
        )
    return f"{project_code}-{infix}-{int(digits):0{MINIMUM_DIGITS}d}"


def raw_requirement_id(project_code: str, public_id: str) -> str:
    """Render `<PROJECT_CODE>-RAW-<public id>`, zero padded to four digits."""
    return namespaced_requirement_id(project_code, RAW_INFIX, public_id)
