"""An empty Result Document: a shell whose body was never stored.

Every model-backed stage creates its Result as a child Document first and
writes the body second. When the body write fails after the create returned,
Fibery is left holding a named, correctly placed, empty Document. That shell
is not a Result: it parses as nothing and blocks the stage until an operator
names it explicitly for completion in place.

Only the mechanics that are genuinely identical across the three stages live
here. Eligibility, naming and iteration rules stay with each stage.
"""

from __future__ import annotations

from sdlc.fibery_workspace import DocumentNode

RECOVERY_OPTION = "--recover-empty-result"


def is_empty_body(text: str | None) -> bool:
    """Whether a Document body holds nothing at all.

    Only whitespace counts as empty. Truncated JSON, a bare heading or any
    other partial content is not empty and is never recovered over.
    """
    return not (text or "").strip()


def document_label(node: DocumentNode) -> str:
    """Name and id, never the content secret."""
    return f"{node.name} ({node.id})"


def recovery_hint(node: DocumentNode) -> str:
    return (
        f"Its body was never stored. If no other run is working on this item, "
        f"pass {RECOVERY_OPTION} {node.id} to complete it in place; that runs the "
        "model again and does not reconstruct the earlier response."
    )
