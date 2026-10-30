"""TSA-C01 — the code-block rules of spec v0.3 8.3 for one Markdown text.

Rule S (no indented or fenced code block, as CommonMark 0.31.2 classifies
them, at any container depth) is computed with the mechanism spec v0.4
selects: a new `MarkdownIt("commonmark")` from the pinned `markdown-it-py`
per classification, `parse` only, then the flat block-token stream. Rule X
(no line opening with three or more backticks or tildes) is a separate line
predicate and is not derived from the parser.

Both are pure and deterministic: no IO, no clock, no state, and the text
is read as given. Neither knows a result code; each stage maps the outcome onto
its own frozen code (I06 `ARCHITECTURE_RENDER_INVALID`, I07
`INVALID_MODEL_OUTPUT`).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from markdown_it import MarkdownIt
from markdown_it.token import Token

__all__ = [
    "BlockClassification",
    "CodeBlockClassification",
    "UnclassifiableReason",
    "block_token_types",
    "block_tokens",
    "classify_code_blocks",
    "has_fence_marker_line",
]

#: The preset spec v0.4 section 2 selects, used as shipped.
PRESET = "commonmark"
NESTING_LIMIT_OPTION = "maxNesting"
CODE_BLOCK_TOKEN_TYPES = frozenset({"fence", "code_block"})
OPENING_NESTING = 1

#: Rule X: up to three spaces, then a run of three backticks or three tildes.
FENCE_MARKER_LINE = re.compile(r" {0,3}(?:`{3}|~{3})")
LINE_ENDING = re.compile(r"\r\n|\r|\n")


class BlockClassification(StrEnum):
    NO_CODE_BLOCK = "NO_CODE_BLOCK"
    CODE_BLOCK = "CODE_BLOCK"
    UNCLASSIFIABLE = "UNCLASSIFIABLE"


class UnclassifiableReason(StrEnum):
    NESTING_LIMIT = "NESTING_LIMIT"
    PARSER_ERROR = "PARSER_ERROR"


@dataclass(frozen=True)
class CodeBlockClassification:
    """The outcome of rule S for one text.

    `line` is the 1-based first line of the first code block, set only for
    `CODE_BLOCK` and only when the parser reports one. `reason` is set only
    for `UNCLASSIFIABLE`. Nothing of the text or of a parser error is kept.
    """

    outcome: BlockClassification
    line: int | None = None
    reason: UnclassifiableReason | None = None


def _may_be_incomplete(tokens: Sequence[Token], nesting_limit: int) -> bool:
    """The completeness guard of spec v0.4 section 3.

    In `markdown-it-py` 4.2.0 the block tokenizer silently skips the rest of a
    block once the state's level reaches `maxNesting`, and the level rises
    only when an opening token is pushed. A skip therefore needs an opening
    token at level `maxNesting - 1` in the stream. This is conservative: it
    also fires where nothing was skipped. The assumption holds for the pinned
    version and configuration only and has to be re-checked against the
    source whenever either changes.
    """
    return any(
        token.nesting == OPENING_NESTING and token.level >= nesting_limit - 1
        for token in tokens
    )


def classify_code_blocks(markdown: str) -> CodeBlockClassification:
    """Rule S for the complete `markdown`, read as one CommonMark document.

    The guard runs before any code token is looked for, so a classification
    that may be incomplete is `UNCLASSIFIABLE`, never `NO_CODE_BLOCK`. An
    ordinary exception from constructing the parser or from parsing is
    `UNCLASSIFIABLE` with `PARSER_ERROR`; its text is dropped and no other
    detector runs. Interrupts and exits propagate. Cost is linear in the text.
    """
    # Any ordinary parser failure must refuse, never pass (spec v0.4 section 4).
    try:
        parser = MarkdownIt(PRESET)
        tokens = parser.parse(markdown)
    except Exception:  # noqa: BLE001
        return CodeBlockClassification(
            BlockClassification.UNCLASSIFIABLE,
            reason=UnclassifiableReason.PARSER_ERROR,
        )
    if _may_be_incomplete(tokens, parser.options[NESTING_LIMIT_OPTION]):
        return CodeBlockClassification(
            BlockClassification.UNCLASSIFIABLE,
            reason=UnclassifiableReason.NESTING_LIMIT,
        )
    for token in tokens:
        if token.type in CODE_BLOCK_TOKEN_TYPES:
            line = token.map[0] + 1 if token.map else None
            return CodeBlockClassification(BlockClassification.CODE_BLOCK, line=line)
    return CodeBlockClassification(BlockClassification.NO_CODE_BLOCK)


def block_token_types(markdown: str) -> tuple[str, ...] | None:
    """The flat block-token types of `markdown`, read as one CommonMark document.

    Spec v0.8: compares the block structure of two texts with the same parser
    and preset rule S uses. `None` when the stream may be incomplete or the
    parser failed, exactly where rule S is `UNCLASSIFIABLE`, so a caller can
    only refuse then. Inline tokens are reported by type only. Linear cost.
    """
    tokens = block_tokens(markdown)
    return None if tokens is None else tuple(token.type for token in tokens)


def block_tokens(markdown: str) -> tuple[Token, ...] | None:
    """The flat token stream behind `block_token_types`, from the same one parse.

    `None` exactly where `block_token_types` is `None`, so a caller that needs
    token positions reads them from a stream the completeness guard vouched
    for, without parsing a second time. Nothing of a parser error is kept.
    """
    # Any ordinary parser failure must refuse, never pass (spec v0.4 section 4).
    try:
        parser = MarkdownIt(PRESET)
        tokens = parser.parse(markdown)
    except Exception:  # noqa: BLE001
        return None
    if _may_be_incomplete(tokens, parser.options[NESTING_LIMIT_OPTION]):
        return None
    return tuple(tokens)


def has_fence_marker_line(text: str) -> bool:
    """Rule X: some line, split on CR LF, CR or LF, opens with a marker run."""
    return any(FENCE_MARKER_LINE.match(line) for line in LINE_ENDING.split(text))
