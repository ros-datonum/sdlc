"""The reusable static consumer-project template (RW-B02).

RW-B01 froze the consumer manifest: exactly four managed paths, of which only
the two agent-guidance files carry static template content, and one exact
managed block with no dynamic placeholder. This module is that contract as
code, and nothing else.

It is pure and byte-oriented. It never opens, creates, resolves or writes a
path, never contacts Fibery and never reads a bootstrap argument: a caller
supplies the bytes an agent-guidance file currently holds, or None when the
file is absent, and receives the classification plus the exact bytes the file
should hold. RW-B04 owns the filesystem and the bootstrap composition,
`.sdlc/project.yaml` is generated under RW-B03, and `.sdlc/project-context.md`
is copied from the bootstrap input by RW-B04; none of the three is built here.

Compatibility is exact. The only normalization is CRLF -> LF inside a
candidate managed block. Wording, blank lines, bullet order, capitalization
and Markdown structure are never fuzzy-matched, and a block that differs, or a
malformed marker pair, is a conflict this module refuses to repair, replace or
upgrade. Foreign content is preserved byte for byte, before and after the
block.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

# RW-B01 section 2: the closed managed consumer manifest. No other path belongs
# to the reusable template in this rewrite, and there are no optional files.
DESCRIPTOR_PATH = ".sdlc/project.yaml"
CONTEXT_PATH = ".sdlc/project-context.md"
AGENTS_GUIDANCE_PATH = "AGENTS.md"
CLAUDE_GUIDANCE_PATH = ".claude/CLAUDE.md"

MANAGED_PATHS = (
    DESCRIPTOR_PATH,
    CONTEXT_PATH,
    AGENTS_GUIDANCE_PATH,
    CLAUDE_GUIDANCE_PATH,
)
# Only the agent-guidance files have static content here: the descriptor is
# generated under RW-B03, and the context is copied from the bootstrap input by
# RW-B04.
STATIC_TEMPLATE_PATHS = (AGENTS_GUIDANCE_PATH, CLAUDE_GUIDANCE_PATH)
OPTIONAL_PATHS: tuple[str, ...] = ()
# RW-B01 section 7: the block is static, so nothing is ever substituted into
# it. An empty set is the frozen answer, not an omission.
TEMPLATE_PLACEHOLDERS: tuple[str, ...] = ()

BEGIN_MARKER = "<!-- SDLC:BEGIN -->"
END_MARKER = "<!-- SDLC:END -->"

MANAGED_BLOCK = """<!-- SDLC:BEGIN -->
## SDLC participation

This repository participates in SDLC.

- Project descriptor: `.sdlc/project.yaml`
- Project context: `.sdlc/project-context.md`
- Canonical product Requirements and Requirement lifecycle State live in Fibery.
- Do not create or maintain a local canonical Requirements mirror.
- Treat `.sdlc/project-context.md` as non-canonical project context, not as competing Requirement truth.
- Human lifecycle authority is the Requirement State in Fibery; do not infer approval or rework from model output or Review verdict alone.
- Project-local guidance must not set or override the user's global model/provider, authentication, approval, permission, sandbox, or edit-policy configuration.
<!-- SDLC:END -->"""

ENCODING = "utf-8"
LF = b"\n"
CRLF = b"\r\n"
# One blank line separates preserved foreign content from the appended block.
SEPARATOR_NEWLINES = 2


class GuidanceDisposition(StrEnum):
    """What an agent-guidance file's current bytes are."""

    # Nothing to preserve: the file is absent, or exists and is empty. The
    # filesystem distinction belongs to RW-B04, which knows which it saw.
    ABSENT = "ABSENT"
    # Foreign UTF-8 content carrying neither marker; it is kept and appended to.
    APPENDABLE_FOREIGN_CONTENT = "APPENDABLE_FOREIGN_CONTENT"
    # Exactly one well-formed frozen block; the file is reused byte for byte.
    COMPATIBLE = "COMPATIBLE"
    # Anything else. RW-B02 never repairs or replaces what it did not write.
    CONFLICT = "CONFLICT"


class ConflictReason(StrEnum):
    """Why a file conflicts: the class of problem, never the file's content."""

    INVALID_UTF8 = "invalid UTF-8"
    MISSING_BEGIN_MARKER = "missing BEGIN marker"
    MISSING_END_MARKER = "missing END marker"
    MARKERS_REVERSED = "END marker before BEGIN marker"
    DUPLICATE_BEGIN_MARKER = "duplicate BEGIN marker"
    DUPLICATE_END_MARKER = "duplicate END marker"
    BLOCK_DIFFERS = "managed SDLC block differs from the frozen template"


@dataclass(frozen=True)
class GuidanceClassification:
    """What the supplied bytes are, and why when they conflict."""

    disposition: GuidanceDisposition
    reason: ConflictReason | None = None


@dataclass(frozen=True)
class GuidancePlan:
    """The classification and the exact bytes the file should end up holding.

    `content` is None for a conflict, because nothing may be written over
    foreign or malformed managed content. It is the supplied bytes unchanged
    when the file already carries the frozen block.
    """

    disposition: GuidanceDisposition
    content: bytes | None = None
    reason: ConflictReason | None = None

    @property
    def is_conflict(self) -> bool:
        return self.disposition is GuidanceDisposition.CONFLICT

    @property
    def requires_write(self) -> bool:
        """Whether RW-B04 would have to write `content` to the path."""
        return self.disposition in (
            GuidanceDisposition.ABSENT,
            GuidanceDisposition.APPENDABLE_FOREIGN_CONTENT,
        )


def managed_block_bytes(newline: bytes = LF) -> bytes:
    """The frozen block, rendered in one newline convention."""
    return MANAGED_BLOCK.encode(ENCODING).replace(LF, newline)


def classify_agent_guidance(content: bytes | None) -> GuidanceClassification:
    """Classify what an agent-guidance path currently holds."""
    if not content:
        return GuidanceClassification(GuidanceDisposition.ABSENT)
    try:
        text = content.decode(ENCODING)
    except UnicodeDecodeError:
        return GuidanceClassification(
            GuidanceDisposition.CONFLICT, ConflictReason.INVALID_UTF8
        )
    begins = text.count(BEGIN_MARKER)
    ends = text.count(END_MARKER)
    if begins == 0 and ends == 0:
        return GuidanceClassification(GuidanceDisposition.APPENDABLE_FOREIGN_CONTENT)
    problem = _marker_problem(text, begins, ends)
    if problem is not None:
        return GuidanceClassification(GuidanceDisposition.CONFLICT, problem)
    return GuidanceClassification(GuidanceDisposition.COMPATIBLE)


def plan_agent_guidance(content: bytes | None) -> GuidancePlan:
    """The deterministic materialization of one agent-guidance path."""
    classification = classify_agent_guidance(content)
    disposition = classification.disposition
    if disposition is GuidanceDisposition.CONFLICT:
        return GuidancePlan(disposition, None, classification.reason)
    if disposition is GuidanceDisposition.COMPATIBLE:
        return GuidancePlan(disposition, content)
    if disposition is GuidanceDisposition.ABSENT:
        return GuidancePlan(disposition, managed_block_bytes() + LF)
    existing = content or b""
    newline = _appended_newline(existing)
    separator = newline * _separator_newlines(existing)
    return GuidancePlan(
        disposition, existing + separator + managed_block_bytes(newline)
    )


def _marker_problem(text: str, begins: int, ends: int) -> ConflictReason | None:
    """The RW-B01 conflict case this marker pair falls into, if any."""
    if begins > 1:
        return ConflictReason.DUPLICATE_BEGIN_MARKER
    if ends > 1:
        return ConflictReason.DUPLICATE_END_MARKER
    if ends == 0:
        return ConflictReason.MISSING_END_MARKER
    if begins == 0:
        return ConflictReason.MISSING_BEGIN_MARKER
    start = text.index(BEGIN_MARKER)
    end = text.index(END_MARKER) + len(END_MARKER)
    if end < start:
        return ConflictReason.MARKERS_REVERSED
    if text[start:end].replace("\r\n", "\n") != MANAGED_BLOCK:
        return ConflictReason.BLOCK_DIFFERS
    return None


def _appended_newline(content: bytes) -> bytes:
    """CRLF only when the existing content is CRLF throughout; never a rewrite."""
    if CRLF in content and LF not in content.replace(CRLF, b""):
        return CRLF
    return LF


def _separator_newlines(content: bytes) -> int:
    """How many newline sequences to add for one blank-line separation."""
    return max(SEPARATOR_NEWLINES - _trailing_newlines(content), 0)


def _trailing_newlines(content: bytes) -> int:
    """Trailing LF or CRLF sequences, counted only up to what a separator needs."""
    count = 0
    tail = content
    while count < SEPARATOR_NEWLINES:
        if tail.endswith(CRLF):
            tail = tail[: -len(CRLF)]
        elif tail.endswith(LF):
            tail = tail[: -len(LF)]
        else:
            break
        count += 1
    return count
