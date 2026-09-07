"""Fixtures for normative Document trees (Requirement-Normative-Tree-Binding)."""

from __future__ import annotations

from dataclasses import replace

from sdlc.fibery_workspace import DocumentNode


def add_child(ws, parent, name, content, document_id=None, secret=None):
    """Nest a Document under `parent`, as a human would in Fibery."""
    document_id = document_id or f"doc-{name}"
    secret = secret or f"secret-{document_id}"
    node = DocumentNode(
        id=document_id,
        name=name,
        folder_id=None,
        entity_public_id=None,
        secret=secret,
        parent_document_id=parent.id,
    )
    ws.documents.append(node)
    ws.content[secret] = content
    return node


def replace_node(ws, node, **changes):
    """Rename or re-parent a Document in place, as an external actor would."""
    index = next(i for i, d in enumerate(ws.documents) if d.id == node.id)
    ws.documents[index] = replace(ws.documents[index], **changes)
    return ws.documents[index]


def remove_node(ws, node):
    ws.documents[:] = [d for d in ws.documents if d.id != node.id]


def edit(ws, node, content):
    ws.content[node.secret] = content


def chain(ws, root, depth, name="level"):
    """A straight line of `depth` Documents beneath the Root."""
    parent = root
    nodes = []
    for level in range(1, depth + 1):
        parent = add_child(ws, parent, f"{name}-{level}", f"Level {level}.\n")
        nodes.append(parent)
    return nodes
