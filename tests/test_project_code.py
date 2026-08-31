import pytest

from sdlc.project_code import (
    GENERATED_CODE_MAX_LENGTH,
    PROJECT_CODE_MAX_LENGTH,
    InvalidProjectCode,
    UnusableProjectName,
    candidate_project_codes,
    derive_project_code,
    normalize_project_code,
    validate_project_code,
)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("SDLC", "SDLC"),
        ("sdlc", "SDLC"),
        ("Design System", "DES"),
        ("Rostyslav Bachyk Home", "RBH"),
        ("Memory", "MEMORY"),
        ("Extraordinarily Long Single", "ELS"),
        ("3D Printer", "PRINTE"),
        # Two-word names whose initials are too short fall back to the
        # first word, so "DS" becomes "DES".
        ("Padded  Name", "PAD"),
    ],
)
def test_derives_a_code_from_the_project_name(name, expected):
    assert derive_project_code(name) == expected


def test_derived_codes_are_valid_and_within_the_recommended_length():
    for name in ("SDLC", "Design System", "Memory", "Rostyslav Bachyk Home"):
        code = derive_project_code(name)
        assert validate_project_code(code) == code
        assert len(code) <= GENERATED_CODE_MAX_LENGTH


def test_derivation_is_deterministic():
    assert derive_project_code("Design System") == derive_project_code("Design System")


@pytest.mark.parametrize("name", ["", "   ", "2024", "---", "42 7"])
def test_names_without_letters_cannot_produce_a_code(name):
    with pytest.raises(UnusableProjectName):
        derive_project_code(name)


@pytest.mark.parametrize(
    ("supplied", "expected"),
    [("sdlc", "SDLC"), ("  des  ", "DES"), ("A1", "A1"), ("X9Y8", "X9Y8")],
)
def test_accepts_and_normalizes_valid_supplied_codes(supplied, expected):
    assert validate_project_code(supplied) == expected


@pytest.mark.parametrize(
    "supplied",
    [
        "",
        "   ",
        "1SDLC",
        "SD LC",
        "SD-LC",
        "SD_LC",
        "SDLÇ",
        "S" * (PROJECT_CODE_MAX_LENGTH + 1),
    ],
)
def test_rejects_invalid_supplied_codes(supplied):
    with pytest.raises(InvalidProjectCode):
        validate_project_code(supplied)


def test_normalization_only_trims_and_uppercases():
    assert normalize_project_code("  sd lc  ") == "SD LC"


def test_collision_candidates_start_with_the_derived_code():
    candidates = list(candidate_project_codes("SDLC"))
    assert candidates[:3] == ["SDLC", "SDLC2", "SDLC3"]


def test_every_collision_candidate_is_a_valid_unique_code():
    candidates = list(candidate_project_codes("Design System"))
    assert len(candidates) == len(set(candidates))
    for candidate in candidates:
        assert validate_project_code(candidate) == candidate
        assert len(candidate) <= GENERATED_CODE_MAX_LENGTH


def test_collision_candidates_are_finite():
    assert 1 < len(list(candidate_project_codes("SDLC"))) < 200
