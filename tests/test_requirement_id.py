import pytest

from sdlc.requirement_id import (
    next_sequence,
    raw_id_prefix,
    raw_requirement_id,
    sequence_of,
)


@pytest.mark.parametrize(
    ("code", "sequence", "expected"),
    [
        ("SDLC", 1, "SDLC-RAW-0001"),
        ("SDLC", 2, "SDLC-RAW-0002"),
        ("DES", 42, "DES-RAW-0042"),
        ("A1", 9999, "A1-RAW-9999"),
        ("SDLC", 10000, "SDLC-RAW-10000"),
    ],
)
def test_renders_the_specified_format(code, sequence, expected):
    assert raw_requirement_id(code, sequence) == expected


def test_sequence_below_one_is_rejected():
    with pytest.raises(ValueError, match="Sequence must be"):
        raw_requirement_id("SDLC", 0)


def test_prefix_matches_the_rendered_id():
    assert raw_requirement_id("SDLC", 1).startswith(raw_id_prefix("SDLC"))


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("SDLC-RAW-0001", 1),
        ("SDLC-RAW-0042", 42),
        ("  SDLC-RAW-0007  ", 7),
        ("OTHER-RAW-0001", None),
        ("SDLC-FR-0001", None),
        ("SDLC-RAW-", None),
        ("SDLC-RAW-abc", None),
    ],
)
def test_reads_back_only_this_projects_raw_ids(value, expected):
    assert sequence_of("SDLC", value) == expected


def test_first_allocation_is_one():
    assert next_sequence("SDLC", []) == 1


def test_allocation_follows_the_highest_used_sequence():
    assert next_sequence("SDLC", ["SDLC-RAW-0001", "SDLC-RAW-0002"]) == 3


def test_allocation_does_not_fill_gaps():
    """A deleted Requirement must not have its identifier reused."""
    assert next_sequence("SDLC", ["SDLC-RAW-0001", "SDLC-RAW-0005"]) == 6


def test_allocation_ignores_other_projects_and_other_kinds():
    existing = ["OTHER-RAW-0099", "SDLC-FR-0003", "SDLC-RAW-0002"]

    assert next_sequence("SDLC", existing) == 3


def test_allocation_is_deterministic():
    existing = ["SDLC-RAW-0003", "SDLC-RAW-0001"]

    assert next_sequence("SDLC", existing) == next_sequence("SDLC", existing)
