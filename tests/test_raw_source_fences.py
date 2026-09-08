"""Audit finding A7: fenced examples are literal to the export schema scan.

Structure comes from headings outside supported fences (FENCED_BLOCK_PATTERN:
a backtick fence at line start, closed by one at line start or running to the
end of the file). Heading-looking text inside a fence is example content, kept
in its enclosing section, and never satisfies, opens or duplicates a section.
"""

from __future__ import annotations

import pytest

from raw_fixtures import TITLE, VALID_SOURCE
from requirement_fake import FakeRequirementWorkspace, planned_project
from sdlc.raw_source import (
    METADATA_SECTION,
    REQUIRED_SECTIONS,
    InvalidRequirementSource,
    UnsupportedRequirementsFormat,
    canonical_markdown,
    parse_raw_requirement,
)
from sdlc.requirement_add import add_raw_requirement
from sdlc.results import AddResultCode

# The existing fixture, fingerprinted by the pre-A7 parser (main at 1141fe0).
PRE_A7_FIXTURE_FINGERPRINT = (
    "2cecafa381611176273a6d4fbefbbdee71f35d583f411aa19247dc9d3ff33d4f"
)

PYTHON_EXAMPLE = '# explanatory code comment\nprint("example")'
SECTION_LIKE_EXAMPLE = "## Requirements\n# another title\nprint(1)"
ALL_SECTIONS_EXAMPLE = "\n".join(f"## {name}" for name in REQUIRED_SECTIONS)
METADATA_LIKE_EXAMPLE = (
    "## Export Metadata\n- Format: `a-different-format`\n- Format Version: `999`"
)


def fenced(code: str, info: str = "python") -> str:
    return f"```{info}\n{code}\n```"


def with_example(section: str, example: str, text: str = VALID_SOURCE) -> str:
    """Append an example block to the end of one section of the fixture."""
    marker = f"## {section}\n"
    head, tail = text.split(marker, 1)
    if "\n## " in tail:
        body, rest = tail.split("\n## ", 1)
        rest = "## " + rest
    else:
        body, rest = tail, ""
    return f"{head}{marker}{body.rstrip()}\n\nExample:\n\n{example}\n\n{rest}"


def outside_fence_headings(body: str) -> list[tuple[int, str]]:
    """Level-2 headings as a test-side fence-aware scan sees them: a fence is
    a line starting with three backticks, toggling until the next such line."""
    headings: list[tuple[int, str]] = []
    in_fence = False
    for index, line in enumerate(body.split("\n")):
        if line.startswith("```"):
            in_fence = not in_fence
        elif not in_fence and line.startswith("## "):
            headings.append((index, line[3:]))
    return headings


def section_lines(body: str, name: str) -> list[str]:
    lines = body.split("\n")
    headings = outside_fence_headings(body)
    start = next(i for i, n in headings if n == name) + 1
    end = next((i for i, _ in headings if i >= start), len(lines))
    return lines[start:end]


def ingest(text: str):
    workspace = FakeRequirementWorkspace(projects=[planned_project()])
    return workspace, add_raw_requirement(workspace, "SDLC", text)


def assert_structure(parsed, example: str, section: str) -> None:
    assert parsed.title == TITLE
    body_sections = [name for _, name in outside_fence_headings(parsed.body)]
    assert body_sections == [n for n in REQUIRED_SECTIONS if n != METADATA_SECTION]
    assert example in "\n".join(section_lines(parsed.body, section))
    assert parsed.metadata["Format"] == "sdlc/raw-requirements"
    assert parsed.metadata["Format Version"] == "0.1"
    assert "Exported At" in parsed.metadata and "## Export Metadata" not in (
        parsed.body.replace(example, "")
    )


# -- accepted: heading-looking text inside a fence is literal ------------------


def test_a_python_comment_inside_a_fence_is_not_a_second_title():
    text = with_example("Requirements and Expected Behavior", fenced(PYTHON_EXAMPLE))
    parsed = parse_raw_requirement(text)
    assert_structure(
        parsed, fenced(PYTHON_EXAMPLE), "Requirements and Expected Behavior"
    )


def test_a_literal_section_heading_inside_a_fence_opens_nothing():
    text = with_example("Constraints", fenced(SECTION_LIKE_EXAMPLE))
    parsed = parse_raw_requirement(text)
    assert_structure(parsed, fenced(SECTION_LIKE_EXAMPLE), "Constraints")
    assert "## Requirements\n# another title" in "\n".join(
        section_lines(parsed.body, "Constraints")
    )


def test_every_required_section_name_inside_one_fence_is_literal():
    text = with_example("Context", fenced(ALL_SECTIONS_EXAMPLE, "markdown"))
    parsed = parse_raw_requirement(text)
    assert_structure(parsed, fenced(ALL_SECTIONS_EXAMPLE, "markdown"), "Context")
    # Each real section still exists exactly once outside the fence.
    assert [n for _, n in outside_fence_headings(parsed.body)].count("Intent") == 1
    assert parsed.body.count("\n## Intent\n") == 2  # the fenced copy is kept


def test_metadata_looking_lines_inside_a_fence_are_neither_metadata_nor_stripped():
    text = with_example("Accepted Decisions", fenced(METADATA_LIKE_EXAMPLE, "markdown"))
    parsed = parse_raw_requirement(text)
    assert_structure(
        parsed, fenced(METADATA_LIKE_EXAMPLE, "markdown"), "Accepted Decisions"
    )
    assert "- Format: `a-different-format`" in parsed.body
    assert parsed.metadata["Format Version"] == "0.1"


def test_a_fenced_example_inside_the_real_metadata_section_carries_no_metadata():
    text = with_example(METADATA_SECTION, fenced(METADATA_LIKE_EXAMPLE, "markdown"))
    parsed = parse_raw_requirement(text)
    assert parsed.metadata["Format"] == "sdlc/raw-requirements"
    assert parsed.metadata["Format Version"] == "0.1"
    assert "a-different-format" not in parsed.body  # transport section removed whole


def test_several_fences_in_different_sections_stay_in_their_sections():
    text = with_example("Intent", fenced("# intent note", "text"))
    text = with_example("Constraints", fenced("## Constraints\nx = 1"), text)
    text = with_example("Open Questions", fenced("- Format: `x`", "markdown"), text)
    parsed = parse_raw_requirement(text)
    assert "# intent note" in "\n".join(section_lines(parsed.body, "Intent"))
    assert "## Constraints\nx = 1" in "\n".join(
        section_lines(parsed.body, "Constraints")
    )
    assert "- Format: `x`" in "\n".join(section_lines(parsed.body, "Open Questions"))
    assert [n for _, n in outside_fence_headings(parsed.body)].count("Constraints") == 1


def test_a_real_section_immediately_after_a_closed_fence_is_structural():
    marker = "## Constraints\n"
    head, tail = VALID_SOURCE.split(marker, 1)
    text = f"{head}```\n## not a section\n```\n{marker}{tail}"
    parsed = parse_raw_requirement(text)
    assert parsed.title == TITLE
    assert "## not a section" in "\n".join(
        section_lines(parsed.body, "Requirements and Expected Behavior")
    )
    assert "\n## Constraints\n" in parsed.body


def test_fence_bodies_are_kept_byte_for_byte_in_the_body():
    example = "```python\n    # deep indent\n\t\ttabbed()\n  ## marker\n```"
    text = with_example("Desired Outcomes", example)
    parsed = parse_raw_requirement(text)
    assert example in parsed.body
    assert canonical_markdown(parsed.body).count(example) == 1


def test_inline_backticks_are_not_a_fence_and_do_not_hide_a_later_error():
    text = VALID_SOURCE.replace(
        "Hand the repository over cleanly.",
        "Use ```make ci``` locally, ``` not at line start.",
    )
    assert parse_raw_requirement(text).title == TITLE
    with pytest.raises(InvalidRequirementSource, match="exactly one level-1"):
        parse_raw_requirement(text + "\n# a second title\n")


# -- accepted through requirement add ------------------------------------------


def test_ingest_stores_the_example_and_creates_exactly_one_requirement():
    text = with_example("Requirements and Expected Behavior", fenced(PYTHON_EXAMPLE))
    workspace, result = ingest(text)
    assert result.code is AddResultCode.RAW_REQUIREMENT_ADDED, result
    assert len(workspace.requirements) == 1 and len(workspace.documents) == 1
    [stored] = workspace.content.values()
    assert fenced(PYTHON_EXAMPLE) in stored
    assert "## Export Metadata" not in stored
    assert not any("model" in m for m in workspace.mutations)


def test_reingesting_an_example_bearing_artifact_is_a_duplicate():
    text = with_example("Constraints", fenced(SECTION_LIKE_EXAMPLE))
    workspace = FakeRequirementWorkspace(projects=[planned_project()])
    first = add_raw_requirement(workspace, "SDLC", text)
    mutations = list(workspace.mutations)
    second = add_raw_requirement(workspace, "SDLC", text)
    assert first.code is AddResultCode.RAW_REQUIREMENT_ADDED
    assert second.code is AddResultCode.REQUIREMENT_ALREADY_ADDED
    assert second.requirement_id == first.requirement_id
    assert workspace.mutations == mutations
    assert len(workspace.requirements) == 1


# -- refused: the outside-fence contract is unchanged ---------------------------


@pytest.mark.parametrize(
    "text, message",
    [
        (VALID_SOURCE + "\n# Second document\n", "exactly one level-1"),
        (VALID_SOURCE + "\n## Constraints\n\nAgain.\n", "more than once"),
        (VALID_SOURCE + "\n## Appendix\n\nUnknown.\n", "does not define"),
        (
            VALID_SOURCE.replace("## Intent", "## Intent-tmp")
            .replace("## Context", "## Intent")
            .replace("## Intent-tmp", "## Context"),
            "out of order",
        ),
    ],
    ids=["second-title", "duplicate-section", "unknown-section", "out-of-order"],
)
def test_outside_fence_structural_errors_are_still_refused(text, message):
    with pytest.raises(InvalidRequirementSource, match=message):
        parse_raw_requirement(text)
    workspace, result = ingest(text)
    assert result.code is AddResultCode.INVALID_REQUIREMENT_SOURCE
    assert workspace.mutations == []


def test_a_required_section_present_only_inside_a_fence_is_missing():
    without = "\n".join(
        line
        for line in VALID_SOURCE.split("\n")
        if line != "## Constraints"
        and line != "- Model calls go through locally authenticated CLIs only."
    )
    text = with_example(
        "Context", fenced("## Constraints\n- fenced", "markdown"), without
    )
    with pytest.raises(
        InvalidRequirementSource, match="missing required sections: Constraints"
    ):
        parse_raw_requirement(text)
    workspace, result = ingest(text)
    assert result.code is AddResultCode.INVALID_REQUIREMENT_SOURCE
    assert workspace.mutations == []


def test_a_title_only_inside_a_fence_is_no_title():
    text = "```markdown\n# " + TITLE + "\n```\n" + VALID_SOURCE.split("\n", 1)[1]
    with pytest.raises(InvalidRequirementSource, match="first non-blank line"):
        parse_raw_requirement(text)
    workspace, result = ingest(text)
    assert result.code is AddResultCode.INVALID_REQUIREMENT_SOURCE
    assert workspace.mutations == []


def test_an_example_before_the_title_violates_the_title_first_rule():
    text = "```python\nprint(1)\n```\n\n" + VALID_SOURCE
    with pytest.raises(InvalidRequirementSource, match="first non-blank line"):
        parse_raw_requirement(text)


@pytest.mark.parametrize(
    "key, value",
    [("Format", "a-different-format"), ("Format Version", "999")],
)
def test_genuine_unsupported_metadata_is_still_unsupported(key, value):
    text = VALID_SOURCE.replace(
        f"- {key}: `{'sdlc/raw-requirements' if key == 'Format' else '0.1'}`",
        f"- {key}: `{value}`",
    )
    with pytest.raises(UnsupportedRequirementsFormat):
        parse_raw_requirement(text)
    workspace, result = ingest(text)
    assert result.code is AddResultCode.UNSUPPORTED_REQUIREMENTS_FORMAT
    assert workspace.mutations == []


def test_an_unclosed_fence_makes_every_later_heading_literal():
    """The shared grammar runs an unclosed fence to the end of the file, so the
    required sections after it are example text and count as missing. Nothing
    is repaired and no closing fence is invented."""
    marker = "## Constraints\n"
    head, tail = VALID_SOURCE.split(marker, 1)
    text = f"{head}```python\nstill_open = True\n\n{marker}{tail}"
    with pytest.raises(InvalidRequirementSource) as raised:
        parse_raw_requirement(text)
    message = str(raised.value)
    assert "missing required sections" in message
    for name in ("Constraints", "Accepted Decisions", "Open Questions"):
        assert name in message
    workspace, result = ingest(text)
    assert result.code is AddResultCode.INVALID_REQUIREMENT_SOURCE
    assert workspace.mutations == []


# -- unchanged identity for previously accepted artifacts ---------------------


def test_the_existing_fixture_keeps_its_pre_a7_fingerprint_and_body():
    parsed = parse_raw_requirement(VALID_SOURCE)
    assert parsed.fingerprint == PRE_A7_FIXTURE_FINGERPRINT
    assert parsed.body.startswith(f"# {TITLE}\n\n## Intent\n")
    assert "## Export Metadata" not in parsed.body
    assert parsed.body.endswith("- None identified in the source context.\n")
