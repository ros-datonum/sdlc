"""Conforming and non-conforming RAW requirements artifacts for tests."""

TITLE = "Repository Handoff and Development Workflow"

VALID_SOURCE = f"""# {TITLE}

## Export Metadata

- Format: `sdlc/raw-requirements`
- Format Version: `0.1`
- Project Name: SDLC
- Project Code: `SDLC`
- Exported At: `2026-08-31T10:00:00Z`

## Intent

Hand the repository over cleanly.

## Context

The project is bootstrapped and needs a repeatable workflow.

## Desired Outcomes

- A reviewer can rebuild the environment from the README alone.

## Requirements and Expected Behavior

- The CLI must run without network access in tests.

## Constraints

- Model calls go through locally authenticated CLIs only.

## Accepted Decisions

- Fibery is the source of truth for requirements.

## Open Questions

- None identified in the source context.

## Deferred / Out of Scope

- None identified in the source context.
"""


def source_without(section: str) -> str:
    """The valid artifact with one section removed."""
    lines = VALID_SOURCE.split("\n")
    kept: list[str] = []
    skipping = False
    for line in lines:
        if line.startswith("## "):
            skipping = line == f"## {section}"
        if not skipping:
            kept.append(line)
    return "\n".join(kept)


def source_with_metadata(**overrides: str) -> str:
    """The valid artifact with Export Metadata keys replaced."""
    text = VALID_SOURCE
    for key, value in overrides.items():
        label = key.replace("_", " ").title().replace("Version", "Version")
        text = text.replace(
            f"- {label}: `sdlc/raw-requirements`", f"- {label}: `{value}`"
        )
        text = text.replace(f"- {label}: `0.1`", f"- {label}: `{value}`")
    return text
