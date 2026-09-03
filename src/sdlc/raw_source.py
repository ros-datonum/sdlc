"""Validation and fingerprinting of the RAW requirements Markdown artifact.

The contract is the global `requirements-export` skill's `schema.md`. Only
deterministic transport and schema concerns are checked here: this module never
interprets product meaning, and no model is involved.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass

FORMAT_KEY = "Format"
FORMAT_VALUE = "sdlc/raw-requirements"
FORMAT_VERSION_KEY = "Format Version"
SUPPORTED_FORMAT_VERSION = "0.1"

METADATA_SECTION = "Export Metadata"

# schema.md section 4. Order is normative; optional sections may be absent but
# may not appear out of place.
REQUIRED_SECTIONS = (
    METADATA_SECTION,
    "Intent",
    "Context",
    "Desired Outcomes",
    "Requirements and Expected Behavior",
    "Constraints",
    "Accepted Decisions",
    "Open Questions",
    "Deferred / Out of Scope",
)
OPTIONAL_SECTIONS = (
    "Examples and Scenarios",
    "Dependencies and Relationships",
    "Terminology",
)
SECTION_ORDER = (
    METADATA_SECTION,
    "Intent",
    "Context",
    "Desired Outcomes",
    "Requirements and Expected Behavior",
    "Examples and Scenarios",
    "Constraints",
    "Accepted Decisions",
    "Dependencies and Relationships",
    "Open Questions",
    "Deferred / Out of Scope",
    "Terminology",
)

TITLE_PATTERN = re.compile(r"^#\s+(?P<title>\S.*?)\s*$")
SECTION_PATTERN = re.compile(r"^##\s+(?P<name>\S.*?)\s*$")
METADATA_PATTERN = re.compile(r"^-\s+(?P<key>[^:]+):\s*(?P<value>.*?)\s*$")

FINGERPRINT_ALGORITHM = "sha-256"

# Fibery re-serializes Markdown when it stores a document. Verified against the
# live workspace: "-" bullets come back as "*", and a blank line is inserted
# between a paragraph and a list that directly follows it. Content read back is
# therefore compared modulo that re-serialization, never byte for byte.
BULLET_PATTERN = re.compile(r"^(\s*)[*+]\s", flags=re.MULTILINE)
CANONICAL_BULLET = r"\1- "
BLANK_LINE_PATTERN = re.compile(r"\n\s*\n+")
# Fibery stores a soft line break inside a paragraph as a literal <br>, so a
# wrapped paragraph is read back as one line. Verified live, 2026-09-02.
SOFT_BREAK_PATTERN = re.compile(r"<br\s*/?>", re.IGNORECASE)
# A line that continues the previous line's text rather than starting a block.
# Fibery joins it to that line and drops its leading indent, so the indent a
# source artifact uses for a wrapped list item is not a difference in content.
CONTINUATION_INDENT_PATTERN = re.compile(
    r"(?<=\S\n)[ \t]+(?![-*+>]\s|#{1,6}\s|\d+\.\s|```)(?=\S)"
)


class InvalidRequirementSource(ValueError):
    """The artifact does not satisfy the export schema."""


class UnsupportedRequirementsFormat(InvalidRequirementSource):
    """The artifact declares a format or version this command cannot ingest."""


@dataclass(frozen=True)
class RawRequirementSource:
    """One validated RAW Requirement artifact.

    `body` is what is written to the Root Document: the title and every content
    section, with `## Export Metadata` removed. That section is transport
    metadata under schema.md section 5, and Project-Requirement-Add-Spec-v0.3
    section 15 permits removing exactly that.

    `fingerprint` is taken over `body`, so re-exporting the same requirement is
    recognised as a duplicate even though `Exported At` differs.
    """

    title: str
    body: str
    fingerprint: str
    metadata: dict[str, str]

    @property
    def project_code(self) -> str | None:
        return self.metadata.get("Project Code")

    @property
    def project_name(self) -> str | None:
        return self.metadata.get("Project Name")


def parse_raw_requirement(text: str) -> RawRequirementSource:
    """Validate the artifact and return it, or raise InvalidRequirementSource."""
    if not text.strip():
        raise InvalidRequirementSource("The source file is empty.")

    lines = _normalize_line_endings(text).split("\n")
    title = _read_title(lines)
    sections = _read_sections(lines)
    _check_sections(sections)
    metadata = _read_metadata(sections[METADATA_SECTION])
    _check_format(metadata)

    body = _build_body(title, lines, sections)
    return RawRequirementSource(
        title=title,
        body=body,
        fingerprint=fingerprint_of(body),
        metadata=metadata,
    )


def fingerprint_of(body: str) -> str:
    """SHA-256 over the normalized body.

    Normalisation is deterministic and lossless for meaning: NFC, LF line
    endings, trailing whitespace stripped per line, surrounding blank lines
    removed. Whitespace-only reformatting therefore does not defeat duplicate
    detection, while any change of wording does.
    """
    return hashlib.sha256(normalize_for_fingerprint(body).encode("utf-8")).hexdigest()


def normalize_for_fingerprint(body: str) -> str:
    normalized = unicodedata.normalize("NFC", _normalize_line_endings(body))
    return "\n".join(line.rstrip() for line in normalized.split("\n")).strip("\n")


def content_equivalent(stored: str, expected: str) -> bool:
    """Whether Fibery stored the content we wrote.

    Equality is modulo Fibery's own Markdown re-serialization, which is a
    storage detail rather than a change of meaning. Anything Fibery does not
    merely re-serialize still fails this check.
    """
    return canonical_markdown(stored) == canonical_markdown(expected)


def canonical_markdown(text: str) -> str:
    """Canonicalize what Fibery is known to re-serialize.

    Each behaviour below was verified against the live workspace, and each one
    broke post-write validation before it was known:

    - a `-` bullet is stored and returned as `*`;
    - a blank line is inserted before a list that follows a paragraph, and
      after a heading followed directly by anything;
    - a soft line break inside a paragraph comes back as a literal `<br>`, so a
      paragraph wrapped across source lines is returned as one line;
    - the same happens inside a list item, and the indent the source gave the
      wrapped continuation line is dropped along with the break.

    Collapsing blank lines absorbs the insertions and the dropped trailing
    newline together. Every line of actual content is still compared, so
    missing or altered text is still detected.

    This is the single canonical representation. Anything that must agree with
    `content_equivalent` - notably document fingerprints - has to derive from
    this function rather than normalizing separately, or two documents Fibery
    considers identical will fingerprint differently.
    """
    unwrapped = SOFT_BREAK_PATTERN.sub("\n", _normalize_line_endings(text))
    unindented = CONTINUATION_INDENT_PATTERN.sub("", unwrapped)
    bullets = BULLET_PATTERN.sub(
        CANONICAL_BULLET, normalize_for_fingerprint(unindented)
    )
    return BLANK_LINE_PATTERN.sub("\n", bullets)


def _normalize_line_endings(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _read_title(lines: list[str]) -> str:
    """schema.md section 3: the first non-blank line is the level-1 heading."""
    first = next((line for line in lines if line.strip()), "")
    match = TITLE_PATTERN.match(first)
    if match is None:
        raise InvalidRequirementSource(
            "The first non-blank line must be a level-1 heading holding the title."
        )
    headings = [line for line in lines if TITLE_PATTERN.match(line)]
    if len(headings) > 1:
        raise InvalidRequirementSource(
            f"The artifact must contain exactly one level-1 heading, found "
            f"{len(headings)}; one file is one RAW Requirement."
        )
    return match.group("title")


def _read_sections(lines: list[str]) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in lines:
        match = SECTION_PATTERN.match(line)
        if match is not None:
            current = match.group("name")
            if current in sections:
                raise InvalidRequirementSource(
                    f"Section {current!r} appears more than once."
                )
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return sections


def _check_sections(sections: dict[str, list[str]]) -> None:
    missing = [name for name in REQUIRED_SECTIONS if name not in sections]
    if missing:
        raise InvalidRequirementSource(
            "The artifact is missing required sections: " + ", ".join(missing)
        )
    unknown = [
        name
        for name in sections
        if name not in REQUIRED_SECTIONS and name not in OPTIONAL_SECTIONS
    ]
    if unknown:
        raise InvalidRequirementSource(
            "The artifact contains sections the schema does not define: "
            + ", ".join(unknown)
        )
    present = [name for name in SECTION_ORDER if name in sections]
    if list(sections) != present:
        raise InvalidRequirementSource(
            "Sections are out of order. Expected: " + " then ".join(present)
        )


def _read_metadata(metadata_lines: list[str]) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for line in metadata_lines:
        match = METADATA_PATTERN.match(line)
        if match is not None:
            metadata[match.group("key").strip()] = match.group("value").strip("` ")
    return metadata


def _check_format(metadata: dict[str, str]) -> None:
    declared = metadata.get(FORMAT_KEY)
    if declared != FORMAT_VALUE:
        raise UnsupportedRequirementsFormat(
            f"{FORMAT_KEY} must be {FORMAT_VALUE!r}, got {declared!r}."
        )
    version = metadata.get(FORMAT_VERSION_KEY)
    if version != SUPPORTED_FORMAT_VERSION:
        raise UnsupportedRequirementsFormat(
            f"{FORMAT_VERSION_KEY} {version!r} is not supported; this command "
            f"ingests {SUPPORTED_FORMAT_VERSION!r}."
        )


def _build_body(title: str, lines: list[str], sections: dict[str, list[str]]) -> str:
    """Title plus every content section, with Export Metadata removed."""
    kept: list[str] = [f"# {title}", ""]
    for name in SECTION_ORDER:
        if name == METADATA_SECTION or name not in sections:
            continue
        kept.append(f"## {name}")
        kept.extend(sections[name])
    return "\n".join(kept).strip("\n") + "\n"
