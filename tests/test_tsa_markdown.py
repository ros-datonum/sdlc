"""Rule S and rule X of TSA-C01 spec v0.3 8.3, with the v0.4 mechanism.

Expected outcomes are written out by hand from the frozen acceptance matrix
and from CommonMark 0.31.2; none is computed by the predicate under test.
The examples themselves are read from the frozen v0.3 document, so a test and
the specification cannot drift apart silently. Everything is a pure
calculation: no Fibery and no model, so every claim is D-class only.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import ClassVar

import markdown_it
import pytest
from markdown_it import MarkdownIt
from markdown_it.token import Token

from sdlc import tsa_markdown
from sdlc.tsa_markdown import (
    BlockClassification,
    UnclassifiableReason,
    classify_code_blocks,
    has_fence_marker_line,
)

SPEC_V03 = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "specs"
    / "TSA-C01-Implementation-Spec-v0.3.md"
)

NO_CODE = BlockClassification.NO_CODE_BLOCK
CODE = BlockClassification.CODE_BLOCK
UNCLASSIFIABLE = BlockClassification.UNCLASSIFIABLE


def frozen_examples() -> dict[str, str]:
    """E01-E13 as the JSON string literals of the frozen acceptance matrix."""
    text = SPEC_V03.read_text(encoding="utf-8")
    matrix = text.split("### Acceptance matrix for P2", 1)[1]
    block = matrix.split("```text\n", 1)[1].split("\n```\n", 1)[0]
    examples = {}
    for line in block.split("\n"):
        key, literal = line[:3], line[5:]
        if literal.startswith('"'):
            examples[key] = json.loads(literal)
    return examples


# Hand-written from the frozen matrix: (input, rule S class, rule X matches).
FROZEN_MATRIX = {
    "E01": ("```\ngraph TD\n```", CODE, True),
    "E02": ("```\ngraph TD", CODE, True),
    "E03": ("~~~\ngraph TD\n~~~", CODE, True),
    "E04": ("~~~\ngraph TD", CODE, True),
    "E05": ("Structure follows.\n~~~mermaid\ngraph TD\n~~~", CODE, True),
    "E06": ("Structure follows.\n\n    graph TD", CODE, False),
    "E07": ("Structure follows.\n    continued text", NO_CODE, False),
    "E08": ("- ~~~\n    ordinary text\n    ~~~", CODE, False),
    "E09": ("- ~~~\n  ordinary text", CODE, False),
    "E10": ("- ordinary ~~~ marker", NO_CODE, False),
    "E11": (
        "| Requirement ID | Gaps |\n|---|---|\n| SDLC-FR-0007 | ~~~ |",
        NO_CODE,
        False,
    ),
    "E12": ("~~~", CODE, True),
    "E13": ("```inline``` then text", NO_CODE, True),
}


def test_the_examples_are_the_ones_frozen_in_v03():
    assert frozen_examples() == {
        key: value for key, (value, _, _) in FROZEN_MATRIX.items()
    }


# --------------------------------------------------------------------------
# A. The frozen examples, rule S and rule X kept apart
# --------------------------------------------------------------------------


@pytest.mark.parametrize("key", sorted(FROZEN_MATRIX))
def test_rule_s_classifies_each_frozen_example_as_the_matrix_does(key):
    _, expected, _ = FROZEN_MATRIX[key]
    assert classify_code_blocks(frozen_examples()[key]).outcome is expected


@pytest.mark.parametrize("key", sorted(FROZEN_MATRIX))
def test_rule_x_is_a_separate_line_predicate(key):
    _, _, expected = FROZEN_MATRIX[key]
    assert has_fence_marker_line(frozen_examples()[key]) is expected


def test_rule_x_alone_and_rule_s_alone_each_refuse_what_the_other_misses():
    # E13: rule X matches although there is no code block.
    assert classify_code_blocks("```inline``` then text").outcome is NO_CODE
    assert has_fence_marker_line("```inline``` then text")
    # E06, E08, E09: code blocks no line of which rule X matches.
    for value in (
        "Structure follows.\n\n    graph TD",
        "- ~~~\n    ordinary text\n    ~~~",
        "- ~~~\n  ordinary text",
    ):
        assert classify_code_blocks(value).outcome is CODE
        assert not has_fence_marker_line(value)


CONTAINED_BLOCKS = {
    "fence in a block quote": "> ~~~\n> graph TD\n> ~~~",
    "backtick fence in an ordered item": "1. ```\n   graph TD\n   ```",
    "indented code in a list item": "- item\n\n      graph TD",
    "list item opening with indented code": "-     graph TD",
    "tab-indented code after a blank line": "Text.\n\n\tgraph TD",
    "fence in a quote in a list": "- > ~~~\n  > graph TD",
}


@pytest.mark.parametrize("label", sorted(CONTAINED_BLOCKS))
def test_code_blocks_inside_containers_are_code_blocks(label):
    assert classify_code_blocks(CONTAINED_BLOCKS[label]).outcome is CODE


NOT_CODE = {
    "inline code span": "Use `x` here.",
    "tilde mid-line": "A ~~~ marker mid-sentence",
    "strikethrough-like": "~~struck~~ then text",
    "lazy continuation": "> quoted\n    still the paragraph",
    "fence-like text in an HTML block": "<div>\n~~~\nx\n~~~\n</div>",
    "empty text": "",
}


@pytest.mark.parametrize("label", sorted(NOT_CODE))
def test_text_without_a_code_block_is_not_one(label):
    assert classify_code_blocks(NOT_CODE[label]).outcome is NO_CODE


def test_the_html_block_case_is_still_caught_by_rule_x():
    assert has_fence_marker_line(NOT_CODE["fence-like text in an HTML block"])


@pytest.mark.parametrize(
    "value", ["   ~~~", "   ```x", "~~~~~", "a\r~~~", "a\r\n```", "x\n```"]
)
def test_rule_x_matches_after_any_line_ending_and_up_to_three_spaces(value):
    assert has_fence_marker_line(value)


@pytest.mark.parametrize("value", ["    ~~~", "~~", "``", "a ~~~", "\t```", "- ~~~"])
def test_rule_x_does_not_match_other_line_starts(value):
    assert not has_fence_marker_line(value)


def test_the_location_is_the_first_line_of_the_first_code_block():
    result = classify_code_blocks("Para.\n\nMore.\n\n~~~\nx\n~~~\n\n    late")
    assert (result.outcome, result.line, result.reason) == (CODE, 5, None)


def test_a_classification_that_found_nothing_carries_no_location_or_reason():
    result = classify_code_blocks("Plain.")
    assert (result.outcome, result.line, result.reason) == (NO_CODE, None, None)


def test_the_envelope_is_a_fence_so_callers_must_exclude_it():
    envelope = '```json\n{"a":1}\n```\n'
    normative = "## 1. Heading\n\nText.\n\n"
    assert classify_code_blocks(normative + envelope).outcome is CODE
    assert classify_code_blocks(normative).outcome is NO_CODE


def test_the_raw_value_is_classified_before_any_strip():
    # The I07 surface of spec 9.2: a value that begins with four spaces is an
    # indented code block; stripping it first would hide that.
    assert classify_code_blocks("    graph TD").outcome is CODE
    assert classify_code_blocks("graph TD").outcome is NO_CODE


def test_the_input_is_not_changed():
    value = "- ~~~\n  x\r\n"
    kept = str(value)
    classify_code_blocks(value)
    assert value == kept


# --------------------------------------------------------------------------
# B. Completeness at the parser's nesting limit (spec v0.4 section 3)
# --------------------------------------------------------------------------


def quoted_fence(depth: int) -> str:
    prefix = "> " * depth
    return f"{prefix}~~~\n{prefix}hidden\n{prefix}~~~\n"


def listed_fence(depth: int) -> str:
    items = "".join("  " * level + "- item\n" for level in range(depth))
    indent = "  " * depth
    return f"{items}{indent}~~~\n{indent}hidden\n{indent}~~~\n"


def mixed_fence(pairs: int) -> str:
    """`pairs` times a block quote holding a list item, then a fence."""
    return "> - " * pairs + "~~~\n"


# Derived by hand from the token levels of the pinned parser: a block quote
# opens one level, a list two (list and item); the guard fires once an
# opening token stands at level 19.
QUOTE_DEPTHS = {1: CODE, 18: CODE, 19: CODE, 20: UNCLASSIFIABLE, 30: UNCLASSIFIABLE}
LIST_DEPTHS = {1: CODE, 8: CODE, 9: CODE, 10: UNCLASSIFIABLE, 40: UNCLASSIFIABLE}
MIXED_PAIRS = {3: CODE, 6: CODE, 7: UNCLASSIFIABLE}


@pytest.mark.parametrize("depth", sorted(QUOTE_DEPTHS))
def test_a_fence_in_nested_quotes_is_classified_until_the_guard_fires(depth):
    assert classify_code_blocks(quoted_fence(depth)).outcome is QUOTE_DEPTHS[depth]


@pytest.mark.parametrize("depth", sorted(LIST_DEPTHS))
def test_a_fence_in_nested_lists_is_classified_until_the_guard_fires(depth):
    assert classify_code_blocks(listed_fence(depth)).outcome is LIST_DEPTHS[depth]


@pytest.mark.parametrize("pairs", sorted(MIXED_PAIRS))
def test_a_fence_in_mixed_containers_is_classified_until_the_guard_fires(pairs):
    assert classify_code_blocks(mixed_fence(pairs)).outcome is MIXED_PAIRS[pairs]


def raw_tokens(text: str) -> list[Token]:
    return MarkdownIt("commonmark").parse(text)


@pytest.mark.parametrize("text", [quoted_fence(20), listed_fence(10), mixed_fence(7)])
def test_a_fence_the_parser_drops_at_its_limit_is_never_a_pass(text):
    # The witness: the pinned parser itself returns no code token here.
    assert not any(token.type in ("fence", "code_block") for token in raw_tokens(text))
    result = classify_code_blocks(text)
    assert result.outcome is UNCLASSIFIABLE
    assert result.reason is UnclassifiableReason.NESTING_LIMIT
    assert result.line is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("> " * 18 + "text", NO_CODE),
        ("> " * 19 + "text", UNCLASSIFIABLE),
        ("".join("  " * level + "- item\n" for level in range(9)), NO_CODE),
        ("".join("  " * level + "- item\n" for level in range(10)), UNCLASSIFIABLE),
    ],
)
def test_code_free_text_at_the_threshold_gets_the_approved_refusal(text, expected):
    assert classify_code_blocks(text).outcome is expected


def test_the_guard_runs_before_any_code_token_is_reported():
    text = "~~~\nvisible\n~~~\n\n" + quoted_fence(25)
    assert any(token.type == "fence" for token in raw_tokens(text))
    result = classify_code_blocks(text)
    assert (result.outcome, result.reason) == (
        UNCLASSIFIABLE,
        UnclassifiableReason.NESTING_LIMIT,
    )


def test_deep_indentation_without_nesting_does_not_fire_the_guard():
    text = "Para\n" + "".join(" " * width + "word\n" for width in range(0, 400, 7))
    assert classify_code_blocks(text).outcome is NO_CODE


class ScriptedParser:
    """Stands in for `MarkdownIt`: returns a fixed token stream."""

    constructed: ClassVar[list[str]] = []
    tokens: ClassVar[list[Token]] = []

    def __init__(self, preset: str) -> None:
        ScriptedParser.constructed.append(preset)
        self.options = {"maxNesting": 20}

    def parse(self, markdown: str) -> list[Token]:
        return ScriptedParser.tokens


def scripted(monkeypatch, tokens: list[Token]) -> None:
    ScriptedParser.constructed = []
    ScriptedParser.tokens = tokens
    monkeypatch.setattr(tsa_markdown, "MarkdownIt", ScriptedParser)


def token(kind: str, nesting: int, level: int) -> Token:
    made = Token(kind, "", nesting)
    made.level = level
    return made


@pytest.mark.parametrize(
    ("tokens", "expected"),
    [
        ([token("paragraph_open", 1, 18)], NO_CODE),
        ([token("paragraph_open", 1, 19)], UNCLASSIFIABLE),
        ([token("blockquote_open", 1, 40)], UNCLASSIFIABLE),
        ([token("paragraph_close", -1, 19)], NO_CODE),
        ([token("inline", 0, 19)], NO_CODE),
        ([token("fence", 0, 19)], CODE),
        ([token("fence", 0, 0), token("list_item_open", 1, 19)], UNCLASSIFIABLE),
    ],
)
def test_the_guard_is_exactly_the_approved_token_condition(
    monkeypatch, tokens, expected
):
    scripted(monkeypatch, tokens)
    assert classify_code_blocks("ignored").outcome is expected


def test_inline_children_are_not_read_as_block_tokens(monkeypatch):
    inline = token("inline", 0, 0)
    inline.children = [token("fence", 0, 0), token("em_open", 1, 30)]
    scripted(monkeypatch, [inline])
    assert classify_code_blocks("ignored").outcome is NO_CODE


def test_every_classification_constructs_its_own_commonmark_parser(monkeypatch):
    scripted(monkeypatch, [])
    classify_code_blocks("a")
    classify_code_blocks("b")
    assert ScriptedParser.constructed == ["commonmark", "commonmark"]


def test_the_pinned_parser_and_preset_are_the_approved_ones():
    assert markdown_it.__version__ == "4.2.0"
    parser = MarkdownIt("commonmark")
    assert parser.options["maxNesting"] == 20
    assert "table" not in parser.block.ruler.get_active_rules()
    assert "fence" in parser.block.ruler.get_active_rules()
    assert "code" in parser.block.ruler.get_active_rules()


def test_the_module_keeps_no_parser_and_does_no_io():
    source = inspect.getsource(tsa_markdown)
    assert "MarkdownIt(" in source
    assert not any(
        isinstance(value, MarkdownIt) for value in vars(tsa_markdown).values()
    )
    for forbidden in ("open(", "datetime", "random", "subprocess", ".render("):
        assert forbidden not in source


# --------------------------------------------------------------------------
# C. Parser errors
# --------------------------------------------------------------------------

SECRET = "model text that must not leak"


class FailingParser:
    def __init__(self, preset: str) -> None:
        self.options = {"maxNesting": 20}

    def parse(self, markdown: str) -> list[Token]:
        raise RuntimeError(SECRET)


class FailingConstruction:
    def __init__(self, preset: str) -> None:
        raise ValueError(SECRET)


@pytest.mark.parametrize("parser", [FailingParser, FailingConstruction])
def test_a_parser_error_is_unclassifiable_never_a_pass(monkeypatch, parser):
    monkeypatch.setattr(tsa_markdown, "MarkdownIt", parser)
    result = classify_code_blocks(SECRET)
    assert result == tsa_markdown.CodeBlockClassification(
        UNCLASSIFIABLE, reason=UnclassifiableReason.PARSER_ERROR
    )
    assert SECRET not in repr(result)


@pytest.mark.parametrize("interrupt", [KeyboardInterrupt, SystemExit])
def test_an_interrupt_is_not_turned_into_a_classification(monkeypatch, interrupt):
    class Interrupted(FailingParser):
        def parse(self, markdown: str) -> list[Token]:
            raise interrupt

    monkeypatch.setattr(tsa_markdown, "MarkdownIt", Interrupted)
    with pytest.raises(interrupt):
        classify_code_blocks("x")


def test_the_reasons_are_the_two_approved_names():
    assert {reason.value for reason in UnclassifiableReason} == {
        "NESTING_LIMIT",
        "PARSER_ERROR",
    }


# --------------------------------------------------------------------------
# Spec v0.8 — block structure, for comparing a stored line with its canonical
# --------------------------------------------------------------------------


def test_block_token_types_tell_an_inline_tag_from_a_block():
    paragraph = ("paragraph_open", "inline", "paragraph_close")
    assert tsa_markdown.block_token_types('{"a": &lt;b&gt;}') == paragraph
    assert tsa_markdown.block_token_types('{"a": <b>}') == paragraph
    assert tsa_markdown.block_token_types("<div>x</div>") == ("html_block",)
    assert tsa_markdown.block_token_types("> x")[0] == "blockquote_open"


def test_block_token_types_refuse_a_stream_that_may_be_incomplete():
    assert tsa_markdown.block_token_types(">" * 100 + " deep") is None
