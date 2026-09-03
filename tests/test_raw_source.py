import pytest

from raw_fixtures import TITLE, VALID_SOURCE, source_without
from sdlc.raw_source import (
    InvalidRequirementSource,
    UnsupportedRequirementsFormat,
    canonical_markdown,
    content_equivalent,
    fingerprint_of,
    normalize_for_fingerprint,
    parse_raw_requirement,
)

# -- valid artifacts -------------------------------------------------------


def test_accepts_a_conforming_export_artifact():
    parsed = parse_raw_requirement(VALID_SOURCE)

    assert parsed.title == TITLE
    assert parsed.project_code == "SDLC"
    assert parsed.project_name == "SDLC"


def test_optional_sections_are_allowed_in_their_defined_position():
    text = VALID_SOURCE.replace(
        "## Constraints",
        "## Examples and Scenarios\n\n- sdlc project init --name SDLC\n\n## Constraints",
    )

    assert parse_raw_requirement(text).title == TITLE


def test_body_drops_export_metadata_but_keeps_every_content_section():
    body = parse_raw_requirement(VALID_SOURCE).body

    assert "## Export Metadata" not in body
    assert "Format Version" not in body
    assert body.startswith(f"# {TITLE}")
    for section in (
        "## Intent",
        "## Context",
        "## Desired Outcomes",
        "## Requirements and Expected Behavior",
        "## Constraints",
        "## Accepted Decisions",
        "## Open Questions",
        "## Deferred / Out of Scope",
    ):
        assert section in body


def test_body_preserves_content_verbatim():
    body = parse_raw_requirement(VALID_SOURCE).body

    assert "Model calls go through locally authenticated CLIs only." in body
    assert "The CLI must run without network access in tests." in body


# -- invalid artifacts -----------------------------------------------------


@pytest.mark.parametrize(
    "section",
    [
        "Export Metadata",
        "Intent",
        "Context",
        "Desired Outcomes",
        "Requirements and Expected Behavior",
        "Constraints",
        "Accepted Decisions",
        "Open Questions",
        "Deferred / Out of Scope",
    ],
)
def test_every_required_section_is_required(section):
    with pytest.raises(InvalidRequirementSource, match="missing required sections"):
        parse_raw_requirement(source_without(section))


@pytest.mark.parametrize("text", ["", "   \n\n", "\n"])
def test_empty_source_is_invalid(text):
    with pytest.raises(InvalidRequirementSource):
        parse_raw_requirement(text)


def test_missing_title_is_invalid():
    text = VALID_SOURCE.replace(f"# {TITLE}", "Not a heading")

    with pytest.raises(InvalidRequirementSource, match="level-1 heading"):
        parse_raw_requirement(text)


def test_two_level_1_headings_are_invalid():
    """One Markdown file is exactly one RAW Requirement."""
    text = VALID_SOURCE + "\n# A second requirement\n"

    with pytest.raises(InvalidRequirementSource, match="exactly one level-1 heading"):
        parse_raw_requirement(text)


def test_duplicate_section_is_invalid():
    text = VALID_SOURCE + "\n## Intent\n\nAgain.\n"

    with pytest.raises(InvalidRequirementSource, match="more than once"):
        parse_raw_requirement(text)


def test_sections_out_of_order_are_invalid():
    text = VALID_SOURCE.replace(
        "## Intent\n\nHand the repository over cleanly.\n\n", ""
    ).replace("## Constraints", "## Intent\n\nHand over.\n\n## Constraints")

    with pytest.raises(InvalidRequirementSource, match="out of order"):
        parse_raw_requirement(text)


def test_unknown_section_is_invalid():
    text = VALID_SOURCE + "\n## Implementation Plan\n\n- do things\n"

    with pytest.raises(InvalidRequirementSource, match="does not define"):
        parse_raw_requirement(text)


def test_wrong_format_is_unsupported():
    text = VALID_SOURCE.replace("`sdlc/raw-requirements`", "`something/else`")

    with pytest.raises(UnsupportedRequirementsFormat, match="Format must be"):
        parse_raw_requirement(text)


def test_unsupported_format_version_is_rejected():
    text = VALID_SOURCE.replace("- Format Version: `0.1`", "- Format Version: `0.2`")

    with pytest.raises(UnsupportedRequirementsFormat, match="not supported"):
        parse_raw_requirement(text)


def test_unsupported_format_is_a_kind_of_invalid_source():
    """So a caller may catch either specifically or generally."""
    assert issubclass(UnsupportedRequirementsFormat, InvalidRequirementSource)


# -- fingerprint -----------------------------------------------------------


def test_fingerprint_is_deterministic():
    assert fingerprint_of("abc") == fingerprint_of("abc")


def test_fingerprint_is_sha256_hex():
    value = fingerprint_of("abc")

    assert len(value) == 64
    assert set(value) <= set("0123456789abcdef")


def test_fingerprint_ignores_line_endings_and_trailing_space():
    assert fingerprint_of("a\r\nb  \n") == fingerprint_of("a\nb\n")


def test_fingerprint_ignores_surrounding_blank_lines():
    assert fingerprint_of("\n\nbody\n\n") == fingerprint_of("body")


def test_fingerprint_changes_when_wording_changes():
    assert fingerprint_of("The CLI must be fast.") != fingerprint_of(
        "The CLI must be slow."
    )


def test_fingerprint_ignores_the_export_timestamp():
    """Re-exporting the same requirement must still count as a duplicate."""
    later = VALID_SOURCE.replace("`2026-08-31T10:00:00Z`", "`2027-01-01T00:00:00Z`")

    assert (
        parse_raw_requirement(later).fingerprint
        == parse_raw_requirement(VALID_SOURCE).fingerprint
    )


def test_fingerprint_tracks_the_stored_body():
    parsed = parse_raw_requirement(VALID_SOURCE)

    assert parsed.fingerprint == fingerprint_of(parsed.body)


def test_normalization_is_idempotent():
    once = normalize_for_fingerprint(VALID_SOURCE)

    assert normalize_for_fingerprint(once) == once


# -- content equivalence ---------------------------------------------------


def test_content_equivalence_tolerates_fiberys_bullet_reserialization():
    """Fibery stores "-" bullets and returns "*" ones."""
    written = "## Intent\n\n- one\n- two\n"
    stored = "## Intent\n\n* one\n* two"

    assert content_equivalent(stored, written)


def test_content_equivalence_preserves_indentation():
    assert content_equivalent("- a\n  * nested", "- a\n  - nested")


def test_content_equivalence_still_rejects_changed_wording():
    assert not content_equivalent("* one", "- two")


def test_content_equivalence_still_rejects_missing_content():
    assert not content_equivalent("", "- one")


def test_content_equivalence_does_not_confuse_bullets_with_emphasis():
    assert not content_equivalent("*emphasis*", "- emphasis")


# -- soft line breaks -------------------------------------------------------


def test_a_wrapped_paragraph_survives_fibery_soft_breaks():
    """The live defect: a wrapped paragraph came back joined by <br>.

    Post-write validation compared it against the source and failed forever,
    exactly as the bullet and blank-line cases did before it.
    """
    written = "Nothing ends an idle session, and\nattempts are not recorded.\n"
    stored = "Nothing ends an idle session, and<br>attempts are not recorded."
    assert content_equivalent(stored, written)


def test_a_soft_break_does_not_change_the_fingerprint():
    """Fingerprints must agree with content_equivalent by construction."""
    written = "One line, and\nanother line.\n"
    stored = "One line, and<br>another line."
    assert canonical_markdown(stored) == canonical_markdown(written)


@pytest.mark.parametrize("tag", ["<br>", "<br/>", "<br />", "<BR>"])
def test_every_spelling_of_the_tag_is_a_line_break(tag):
    assert content_equivalent(f"a{tag}b", "a\nb")


def test_changed_wording_still_fails_despite_the_soft_break_rule():
    """Normalization must not make two different documents look equal."""
    assert not content_equivalent("a a<br>b b", "a a\nc c\n")


def test_a_wrapped_list_item_survives_fibery_soft_breaks():
    """The live defect found during Ready acceptance.

    Fibery joins a wrapped list item with <br> exactly as it joins a wrapped
    paragraph, and drops the indent the source gave the continuation line.
    Post-write validation kept the indent and failed forever.
    """
    written = (
        "- The CLI must print the result code as the first line,\n"
        "  so that scripts can branch on it.\n"
        "- Every command must be safe to retry: a second\n"
        "  invocation must report the already-done outcome and\n"
        "  change nothing.\n"
    )
    stored = (
        "* The CLI must print the result code as the first line,<br>"
        "so that scripts can branch on it.\n"
        "* Every command must be safe to retry: a second<br>"
        "invocation must report the already-done outcome and<br>change nothing."
    )
    assert content_equivalent(stored, written)
    assert canonical_markdown(stored) == canonical_markdown(written)


def test_a_nested_bullet_is_not_a_continuation():
    """Only text continuing a line loses its indent; a nested item keeps it."""
    assert canonical_markdown("- one\n  - two\n") == "- one\n  - two"


def test_changed_wording_in_a_wrapped_list_item_still_fails():
    assert not content_equivalent("* a a<br>b b", "- a a\n  c c\n")


# -- fenced blocks are literal -----------------------------------------------

FENCED_JSON_FOUR = '# X\n\n```json\n{\n    "name": "x"\n}\n```\n'
FENCED_JSON_TWO = '# X\n\n```json\n{\n  "name": "x"\n}\n```\n'


def test_indentation_inside_a_fence_is_a_real_difference():
    """Freeze review B1: the continuation-indent rule reached inside fences.

    Fibery returns fenced content verbatim, so an indentation change inside a
    fenced example is a change to the document, and it must move the
    fingerprint a Review Result is bound to.
    """
    assert not content_equivalent(FENCED_JSON_FOUR, FENCED_JSON_TWO)
    assert canonical_markdown(FENCED_JSON_FOUR) != canonical_markdown(FENCED_JSON_TWO)


FENCED_DIFFERENCES = [
    (
        "leading indentation",
        "```\nif x:\n    y()\n    z()\n```",
        "```\nif x:\n    y()\nz()\n```",
    ),
    ("blank line", "```\na\n\nb\n```", "```\na\nb\n```"),
    ("dash versus star", "```\n- item\n```", "```\n* item\n```"),
    ("plus versus dash", "```\n+ item\n```", "```\n- item\n```"),
    ("br tag", "```\na<br>b\n```", "```\na\nb\n```"),
    ("heading-like text", "```\n# title\n```", "```\n#  title\n```"),
    ("nested-looking markdown", "```\n- one\n  - two\n```", "```\n- one\n- two\n```"),
    ("trailing space", "```\na \n```", "```\na\n```"),
    ("info string", "```json\n{}\n```", "```yaml\n{}\n```"),
]


@pytest.mark.parametrize(("label", "a", "b"), FENCED_DIFFERENCES)
def test_a_literal_difference_inside_a_fence_is_never_equivalent(label, a, b):
    assert not content_equivalent(a, b)
    assert canonical_markdown(a) != canonical_markdown(b)


def test_a_fence_is_kept_verbatim_in_the_canonical_form():
    fence = '```json\n{\n    "a": "x<br>y",\n  "b": "- \\n*\\n+"\n}\n```'
    assert canonical_markdown(fence) == fence
    assert canonical_markdown(f"# X\n\n{fence}\n\nTail.\n") == f"# X\n{fence}\nTail."


def test_prose_around_a_fence_is_still_normalized():
    """Fibery's re-serialization outside the fence is still absorbed."""
    written = "Intro:\n- item,\n  wrapped\n\n```\n  literal\n```\n\nafter a\nwrap\n"
    stored = "Intro:\n\n* item,<br>wrapped\n\n```\n  literal\n```\n\nafter a<br>wrap"
    assert content_equivalent(stored, written)


def test_inline_backticks_are_not_a_fence():
    """Only a fence at the start of a line opens literal content."""
    written = "Use ```x``` here,\n  wrapped\n"
    stored = "Use ```x``` here,<br>wrapped"
    assert content_equivalent(stored, written)


def test_an_unclosed_fence_runs_to_the_end_and_stays_literal():
    assert canonical_markdown("```\n  a\n- b\n") == "```\n  a\n- b\n"
    assert not content_equivalent("```\n  a\n- b\n", "```\na\n- b\n")


def test_wrapped_list_items_outside_a_fence_still_match_the_live_form():
    """The live-verified compatibility case must survive the fence split."""
    written = "- first line,\n  continuation line\n- next item\n\n```\n  kept\n```\n"
    stored = "* first line,<br>continuation line\n* next item\n\n```\n  kept\n```"
    assert content_equivalent(stored, written)
    assert canonical_markdown(stored) == canonical_markdown(written)


OUTSIDE_FENCE_SEMANTIC_CHANGES = [
    ("removed continuation text", "- item\n  continuation\n- next\n", "* item\n* next"),
    (
        "changed continuation wording",
        "- item\n  continuation\n- next\n",
        "* item<br>continuatiom\n* next",
    ),
    (
        "changed next item",
        "- item\n  continuation\n- next\n",
        "* item<br>continuation\n* nxt",
    ),
    (
        "reordered items",
        "- item\n  continuation\n- next\n",
        "* next\n* item<br>continuation",
    ),
    ("merged items", "- item\n  continuation\n- next\n", "* item<br>continuation next"),
    ("dropped negation", "- item\n  not continuation\n", "* item<br>continuation"),
    ("flattened nested list", "- one\n  - two\n", "* one\n* two"),
    ("continuation became nested bullet", "- one\n  two\n", "* one\n  * two"),
    ("removed section", "## A\n\nx\n\n## B\n\ny\n", "## A\n\nx"),
    ("changed heading", "## Non-Goals\n\nx\n", "## Non Goals\n\nx"),
    (
        "single line versus wrapped item",
        "- item\n  continuation\n",
        "* item continuation",
    ),
]


@pytest.mark.parametrize(("label", "written", "other"), OUTSIDE_FENCE_SEMANTIC_CHANGES)
def test_semantic_changes_outside_a_fence_are_still_detected(label, written, other):
    assert not content_equivalent(other, written)


# -- RAW transport identity is untouched ------------------------------------

TRANSPORT_SAMPLE = (
    "# T\r\n\r\n## Requirements and Expected Behavior\r\n\r\n- must do A,\r\n"
    '  wrapped here.  \r\n- must do B.\r\n\r\n```json\r\n{\r\n    "v": 1\r\n}\r\n```\r\n'
)
# Computed with the frozen implementation at 5064db7. The Source Fingerprint is
# RAW transport identity, not content comparison, and must stay byte-compatible.
TRANSPORT_FINGERPRINT = (
    "cf46691c6acc31f8198c8e07b267a969d532f2c0084da3c5c16b68a34078c591"
)


def test_the_source_fingerprint_is_unchanged_by_content_canonicalization():
    assert fingerprint_of(TRANSPORT_SAMPLE) == TRANSPORT_FINGERPRINT
    assert normalize_for_fingerprint("- a\n  b\n") == "- a\n  b"
