import pytest

from raw_fixtures import TITLE, VALID_SOURCE, source_without
from sdlc.raw_source import (
    InvalidRequirementSource,
    UnsupportedRequirementsFormat,
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
