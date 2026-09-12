"""RW-B02: the reusable static consumer-project template.

The frozen block and marker text are read back out of
`docs/rewrite/RW-B01-Template-Manifest-v0.1.md`, so these tests compare the
module against RW-B01 itself rather than against a second copy of the same
typing. Everything else is exercised over bytes only: RW-B02 owns no
filesystem, no descriptor schema and no bootstrap composition.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from sdlc import consumer_template
from sdlc.consumer_template import (
    AGENTS_GUIDANCE_PATH,
    BEGIN_MARKER,
    CLAUDE_GUIDANCE_PATH,
    CONTEXT_PATH,
    DESCRIPTOR_PATH,
    END_MARKER,
    LF,
    MANAGED_BLOCK,
    MANAGED_PATHS,
    OPTIONAL_PATHS,
    STATIC_TEMPLATE_PATHS,
    TEMPLATE_PLACEHOLDERS,
    ConflictReason,
    GuidanceDisposition,
    classify_agent_guidance,
    managed_block_bytes,
    plan_agent_guidance,
)

REPOSITORY = pathlib.Path(__file__).resolve().parents[1]
MANIFEST = REPOSITORY / "docs/rewrite/RW-B01-Template-Manifest-v0.1.md"
CRLF = b"\r\n"
FOREIGN = "# House rules\n\nBe kind to the build.\n"
# RW-B01 section 3: paths bootstrap must never create as SDLC participation.
EXCLUDED_PATHS = (
    ".codex/config.toml",
    ".claude/settings.json",
    ".agents/",
    ".claude/agents/",
    ".claude/skills/",
    ".agents/skills/",
    ".env",
)


def frozen_block() -> str:
    """The managed block exactly as RW-B01 froze it.

    The manifest first lists the two markers on their own, so the block is the
    last BEGIN marker and the END marker that follows it.
    """
    text = MANIFEST.read_text(encoding="utf-8")
    start = text.rindex(BEGIN_MARKER)
    end = text.index(END_MARKER, start) + len(END_MARKER)
    return text[start:end]


def block_with(line: str, replacement: str) -> bytes:
    """The frozen block with one line altered, as a rejected near-miss."""
    assert line in MANAGED_BLOCK
    return MANAGED_BLOCK.replace(line, replacement).encode("utf-8")


# -- the closed manifest ----------------------------------------------------------


def test_the_managed_manifest_is_exactly_the_four_b01_paths():
    assert MANAGED_PATHS == (
        ".sdlc/project.yaml",
        ".sdlc/project-context.md",
        "AGENTS.md",
        ".claude/CLAUDE.md",
    )
    assert len(set(MANAGED_PATHS)) == len(MANAGED_PATHS)


def test_the_static_template_paths_are_the_two_agent_guidance_files():
    assert STATIC_TEMPLATE_PATHS == (AGENTS_GUIDANCE_PATH, CLAUDE_GUIDANCE_PATH)
    assert STATIC_TEMPLATE_PATHS == ("AGENTS.md", ".claude/CLAUDE.md")
    assert set(STATIC_TEMPLATE_PATHS) < set(MANAGED_PATHS)
    assert DESCRIPTOR_PATH not in STATIC_TEMPLATE_PATHS, "RW-B03 owns the descriptor"
    assert CONTEXT_PATH not in STATIC_TEMPLATE_PATHS, "RW-B04 copies the context"


def test_there_are_no_optional_paths():
    assert OPTIONAL_PATHS == ()


def test_the_module_declares_no_path_outside_the_manifest():
    declared = {
        value
        for name, attribute in vars(consumer_template).items()
        if name.isupper() and name.endswith(("_PATH", "_PATHS"))
        for value in ((attribute,) if isinstance(attribute, str) else attribute)
    }
    assert declared == set(MANAGED_PATHS)


@pytest.mark.parametrize("path", EXCLUDED_PATHS)
def test_no_excluded_runtime_or_agent_path_is_managed(path):
    assert path not in MANAGED_PATHS
    assert path not in STATIC_TEMPLATE_PATHS


# -- the frozen block -------------------------------------------------------------


def test_the_markers_are_exactly_the_frozen_ones():
    assert BEGIN_MARKER == "<!-- SDLC:BEGIN -->"
    assert END_MARKER == "<!-- SDLC:END -->"
    assert MANAGED_BLOCK.startswith(BEGIN_MARKER)
    assert MANAGED_BLOCK.endswith(END_MARKER)


def test_the_managed_block_is_exactly_the_block_rw_b01_froze():
    assert frozen_block() == MANAGED_BLOCK


def test_the_block_names_both_project_local_artifacts_and_fibery_authority():
    assert DESCRIPTOR_PATH in MANAGED_BLOCK
    assert CONTEXT_PATH in MANAGED_BLOCK
    assert "Fibery" in MANAGED_BLOCK


@pytest.mark.parametrize("syntax", ["{", "}", "${", "%s", "%(", "<<", "{{"])
def test_the_static_block_carries_no_dynamic_placeholder(syntax):
    assert syntax not in MANAGED_BLOCK


def test_the_frozen_placeholder_set_is_empty():
    assert TEMPLATE_PLACEHOLDERS == ()


@pytest.mark.parametrize(
    "secret",
    ["token", "api_key", "apikey", "password", "secret", "bearer", "sk-", "fibery_"],
)
def test_the_block_carries_no_credential_or_account_value(secret):
    assert secret not in MANAGED_BLOCK.lower()


@pytest.mark.parametrize("path", EXCLUDED_PATHS)
def test_the_block_never_points_at_an_excluded_runtime_path(path):
    assert path not in MANAGED_BLOCK


# -- materialization: absent and empty --------------------------------------------


@pytest.mark.parametrize("content", [None, b""], ids=["absent", "empty"])
def test_absent_and_empty_materialize_to_the_block_and_one_newline(content):
    plan = plan_agent_guidance(content)

    assert plan.disposition is GuidanceDisposition.ABSENT
    assert plan.content == MANAGED_BLOCK.encode("utf-8") + LF
    assert plan.requires_write
    assert plan.reason is None


# -- materialization: foreign content ---------------------------------------------

SEPARATION = {
    "no-final-newline": ("# Rules\n\nBe kind.", b"\n\n"),
    "one-final-newline": ("# Rules\n\nBe kind.\n", b"\n"),
    "two-final-newlines": ("# Rules\n\nBe kind.\n\n", b""),
    "three-final-newlines": ("# Rules\n\nBe kind.\n\n\n", b""),
}


@pytest.mark.parametrize(
    ("existing", "separator"), SEPARATION.values(), ids=SEPARATION.keys()
)
def test_foreign_content_is_preserved_and_separated_by_one_blank_line(
    existing, separator
):
    original = existing.encode("utf-8")

    plan = plan_agent_guidance(original)

    assert plan.disposition is GuidanceDisposition.APPENDABLE_FOREIGN_CONTENT
    assert plan.content == original + separator + managed_block_bytes()
    assert plan.content.startswith(original), "every existing byte survives"
    assert plan.requires_write


def test_a_crlf_file_is_appended_to_in_crlf():
    original = b"# Rules\r\n\r\nBe kind.\r\n"

    plan = plan_agent_guidance(original)

    assert plan.content == original + CRLF + managed_block_bytes(CRLF)
    assert plan.content.startswith(original)
    assert LF not in plan.content.replace(CRLF, b""), "no lone LF is introduced"


def test_mixed_line_endings_stay_untouched_and_the_appended_block_uses_lf():
    original = b"# Rules\r\n\r\nBe kind.\n"

    plan = plan_agent_guidance(original)

    assert plan.content == original + LF + managed_block_bytes()
    assert plan.content.startswith(original), "foreign line endings are never rewritten"


def test_an_appended_block_reads_back_as_compatible():
    """One bootstrap appends; a rerun must find the file compatible, not doubled."""
    first = plan_agent_guidance(FOREIGN.encode("utf-8"))

    second = plan_agent_guidance(first.content)

    assert second.disposition is GuidanceDisposition.COMPATIBLE
    assert second.content == first.content
    assert second.content.count(BEGIN_MARKER.encode("utf-8")) == 1


# -- materialization: an existing frozen block -------------------------------------


def test_an_exact_lf_block_is_compatible_and_reused_unchanged():
    original = (MANAGED_BLOCK + "\n").encode("utf-8")

    plan = plan_agent_guidance(original)

    assert plan.disposition is GuidanceDisposition.COMPATIBLE
    assert plan.content == original
    assert not plan.requires_write


def test_an_exact_crlf_block_is_compatible_and_reused_unchanged():
    original = managed_block_bytes(CRLF) + CRLF

    plan = plan_agent_guidance(original)

    assert plan.disposition is GuidanceDisposition.COMPATIBLE
    assert plan.content == original, "the file is never rewritten to LF"


SURROUNDED = {
    "before": "# House rules\n\nBe kind.\n\n" + MANAGED_BLOCK + "\n",
    "after": MANAGED_BLOCK + "\n\n## Local notes\n\nRun the tests.\n",
    "both": "# Top\n\n" + MANAGED_BLOCK + "\n\n# Bottom\n",
}


@pytest.mark.parametrize("existing", SURROUNDED.values(), ids=SURROUNDED.keys())
def test_foreign_content_around_a_valid_block_survives_byte_for_byte(existing):
    original = existing.encode("utf-8")

    plan = plan_agent_guidance(original)

    assert plan.disposition is GuidanceDisposition.COMPATIBLE
    assert plan.content == original


# -- conflicts ---------------------------------------------------------------------

CONFLICTS = {
    "begin-only": (
        f"{BEGIN_MARKER}\n## SDLC participation\n",
        ConflictReason.MISSING_END_MARKER,
    ),
    "end-only": (
        f"Some notes.\n{END_MARKER}\n",
        ConflictReason.MISSING_BEGIN_MARKER,
    ),
    "reversed": (
        f"{END_MARKER}\nmiddle\n{BEGIN_MARKER}\n",
        ConflictReason.MARKERS_REVERSED,
    ),
    "duplicate-begin": (
        f"{MANAGED_BLOCK}\n{BEGIN_MARKER}\n",
        ConflictReason.DUPLICATE_BEGIN_MARKER,
    ),
    "duplicate-end": (
        f"{MANAGED_BLOCK}\n{END_MARKER}\n",
        ConflictReason.DUPLICATE_END_MARKER,
    ),
}


@pytest.mark.parametrize(
    ("existing", "reason"), CONFLICTS.values(), ids=CONFLICTS.keys()
)
def test_malformed_marker_pairs_conflict(existing, reason):
    plan = plan_agent_guidance(existing.encode("utf-8"))

    assert plan.disposition is GuidanceDisposition.CONFLICT
    assert plan.reason is reason
    assert plan.content is None, "a conflict is never materialized over"
    assert not plan.requires_write


NEAR_MISSES = {
    "changed-wording": block_with(
        "This repository participates in SDLC.",
        "This repository takes part in SDLC.",
    ),
    "whitespace-only": block_with("## SDLC participation", "##  SDLC participation"),
    "blank-line-removed": MANAGED_BLOCK.replace(
        "This repository participates in SDLC.\n\n-",
        "This repository participates in SDLC.\n-",
    ).encode("utf-8"),
    "reordered-bullets": block_with(
        "- Project descriptor: `.sdlc/project.yaml`\n"
        "- Project context: `.sdlc/project-context.md`",
        "- Project context: `.sdlc/project-context.md`\n"
        "- Project descriptor: `.sdlc/project.yaml`",
    ),
    "dropped-bullet": block_with(
        "- Do not create or maintain a local canonical Requirements mirror.\n", ""
    ),
    "capitalization": block_with("## SDLC participation", "## SDLC Participation"),
}


@pytest.mark.parametrize("existing", NEAR_MISSES.values(), ids=NEAR_MISSES.keys())
def test_a_block_that_differs_at_all_conflicts_and_is_never_repaired(existing):
    plan = plan_agent_guidance(existing)

    assert plan.disposition is GuidanceDisposition.CONFLICT
    assert plan.reason is ConflictReason.BLOCK_DIFFERS
    assert plan.content is None


def test_invalid_utf8_conflicts():
    plan = plan_agent_guidance(b"# Rules\n\n\xff\xfe not text\n")

    assert plan.disposition is GuidanceDisposition.CONFLICT
    assert plan.reason is ConflictReason.INVALID_UTF8
    assert plan.content is None


def test_a_conflict_reason_names_the_class_and_never_echoes_the_file():
    prose = "PRIVATE ROADMAP: acquire the competitor in Q3."

    plan = plan_agent_guidance(f"{prose}\n{BEGIN_MARKER}\nchanged\n".encode())

    assert plan.disposition is GuidanceDisposition.CONFLICT
    assert plan.reason in set(ConflictReason)
    assert prose not in str(plan.reason)
    assert "competitor" not in str(plan.reason)
    assert len(str(plan.reason)) <= 80


def test_classification_and_planning_agree():
    for content in (None, b"", FOREIGN.encode("utf-8"), MANAGED_BLOCK.encode("utf-8")):
        assert classify_agent_guidance(content).disposition is (
            plan_agent_guidance(content).disposition
        )


# -- the boundary RW-B02 must not cross --------------------------------------------


def test_the_module_imports_nothing_that_could_reach_the_world():
    """No filesystem, no Fibery, no bootstrap input: bytes in, bytes out."""
    tree = ast.parse(
        pathlib.Path(consumer_template.__file__).read_text(encoding="utf-8")
    )
    imported = {
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }
    imported |= {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }

    assert imported <= {"__future__", "dataclasses", "enum"}


@pytest.mark.parametrize(
    "content", [None, b"", FOREIGN.encode("utf-8"), MANAGED_BLOCK.encode("utf-8")]
)
def test_no_materialization_introduces_an_excluded_path_or_placeholder(content):
    plan = plan_agent_guidance(content)
    produced = (plan.content or b"").decode("utf-8")

    for path in EXCLUDED_PATHS:
        assert path not in produced
    for syntax in ("${", "{{", "%s"):
        assert syntax not in produced
