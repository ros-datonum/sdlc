import pytest

from sdlc.requirement_id import (
    MINIMUM_DIGITS,
    InvalidPublicId,
    raw_requirement_id,
)


@pytest.mark.parametrize(
    ("code", "public_id", "expected"),
    [
        ("SDLC", "1", "SDLC-RAW-0001"),
        ("SDLC", "37", "SDLC-RAW-0037"),
        ("SDLC", "137", "SDLC-RAW-0137"),
        ("SDLC", "9999", "SDLC-RAW-9999"),
        ("DES", "42", "DES-RAW-0042"),
        ("A1", "7", "A1-RAW-0007"),
    ],
)
def test_pads_the_public_id_to_four_digits(code, public_id, expected):
    assert raw_requirement_id(code, public_id) == expected


@pytest.mark.parametrize(
    ("public_id", "expected"),
    [
        ("10000", "SDLC-RAW-10000"),
        ("12045", "SDLC-RAW-12045"),
        ("987654321", "SDLC-RAW-987654321"),
    ],
)
def test_larger_public_ids_keep_every_digit(public_id, expected):
    """Four digits is a presentation width, never a ceiling."""
    assert raw_requirement_id("SDLC", public_id) == expected


def test_the_public_id_is_recoverable_from_the_requirement_id():
    for public_id in ("1", "137", "12045"):
        rendered = raw_requirement_id("SDLC", public_id)
        assert int(rendered.rsplit("-", 1)[1]) == int(public_id)


def test_surrounding_whitespace_is_tolerated():
    assert raw_requirement_id("SDLC", "  137  ") == "SDLC-RAW-0137"


def test_leading_zeros_are_canonicalized():
    assert raw_requirement_id("SDLC", "0007") == raw_requirement_id("SDLC", "7")


@pytest.mark.parametrize("public_id", ["", "   ", "abc", "12a", "1.0", "-1", None])
def test_a_non_numeric_public_id_is_refused(public_id):
    """Rather than inventing a fallback allocator."""
    with pytest.raises(InvalidPublicId):
        raw_requirement_id("SDLC", public_id)


def test_distinct_public_ids_always_give_distinct_requirement_ids():
    """The property that makes the allocator concurrency safe."""
    rendered = {raw_requirement_id("SDLC", str(n)) for n in range(1, 500)}

    assert len(rendered) == 499


def test_ids_are_namespaced_by_project_code():
    assert raw_requirement_id("AAA", "1") != raw_requirement_id("BBB", "1")


def test_minimum_width_is_four():
    assert MINIMUM_DIGITS == 4
