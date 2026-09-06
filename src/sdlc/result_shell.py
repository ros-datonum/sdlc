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

from collections.abc import Sequence

from sdlc.fibery_workspace import DocumentNode, RequirementRecord

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


def eligibility_drift(
    captured: RequirementRecord,
    root: DocumentNode,
    current: RequirementRecord | None,
    attached: Sequence[DocumentNode],
    type_name: str,
    state: str,
) -> tuple[str, ...]:
    """How a freshly read Requirement differs from the one a stage captured.

    `current` and `attached` must come from reads taken immediately before
    the recovered body is written; the captured context is never reused as
    the current state. The Root is the same only when it is still the single
    attached Document with the same identity and content secret.
    """
    if current is None:
        return ("the Requirement can no longer be read",)
    drift: list[str] = []
    if current.type_name != type_name:
        drift.append(f"Type is now {current.type_name!r}")
    if current.state != state:
        drift.append(f"State is now {current.state!r}")
    if current.requirement_id != captured.requirement_id:
        drift.append(
            f"Requirement ID changed from {captured.requirement_id!r} to "
            f"{current.requirement_id!r}"
        )
    if len(attached) != 1 or attached[0].id != root.id:
        drift.append(
            "the Root Document is no longer the single attached Document "
            f"({len(attached)} attached now)"
        )
    elif attached[0].secret != root.secret:
        drift.append("the Root Document's content secret changed")
    return tuple(drift)
