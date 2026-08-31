#!/usr/bin/env python
"""Read-only probe answering the Project Init Fibery integration spike.

This is a spike instrument, not part of the `sdlc` capability. It performs no
writes, so it is safe to run against the real workspace.

It answers the three open integration questions from
`docs/fibery/Fibery-API-Constraints-v0.1.md`:

1. how a parent/child Document hierarchy is represented, if at all;
2. whether ``fibery/type: "document"`` is the value this workspace uses;
3. what the ``Project.Documents Root`` Field type is and what it stores.

Run it once the FIBERY_* environment variables are set:

    uv run python scripts/fibery_document_probe.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter

# `Any` is unavoidable here: the probe exists precisely to discover the shape of
# Fibery's view JSON, so it cannot presuppose a narrower type for it.
from typing import Any

from sdlc.config import ConfigurationError, load_fibery_settings
from sdlc.fibery_client import FiberyClient
from sdlc.fibery_workspace import FiberyError

PROJECT_DATABASE_NAME = "Project"
SAMPLE_VIEWS_PER_TYPE = 3
NESTING_KEY_HINTS = ("parent", "folder", "container", "tree", "path", "ancestor")
SEPARATOR = "=" * 72


def main() -> int:
    try:
        settings = load_fibery_settings()
    except ConfigurationError as error:
        print(error, file=sys.stderr)
        print(
            "\nThe probe needs read access to the real workspace. It writes nothing.",
            file=sys.stderr,
        )
        return 1

    client = FiberyClient(settings)
    try:
        views = _report_views(client)
        _report_nesting_evidence(views)
        _report_project_schema(client, settings.space)
    except FiberyError as error:
        print(f"\nFibery call failed: {error}", file=sys.stderr)
        return 1
    return 0


def _report_views(client: FiberyClient) -> list[dict[str, Any]]:
    """Question 2: which fibery/type values does this workspace actually use?"""
    _heading("1. View types present in the workspace")
    views = client.views_rpc("query-views", {}) or []
    counts = Counter(view.get("fibery/type") for view in views)
    for type_name, count in counts.most_common():
        print(f"  {count:4d}  fibery/type = {type_name!r}")
    print(f"\n  'document' present: {'document' in counts} (total views: {len(views)})")

    _heading("2. Full JSON of sample views, per type")
    print("Every key is shown. A parent/child relationship, if one exists,")
    print("must appear here — most plausibly inside 'fibery/meta'.\n")
    for type_name in counts:
        print(f"--- fibery/type = {type_name!r} ---")
        for view in _samples(views, type_name):
            print(json.dumps(view, indent=2, sort_keys=True, ensure_ascii=False))
        print()
    return views


def _report_nesting_evidence(views: list[dict[str, Any]]) -> None:
    """Question 1: does any key look like it encodes hierarchy?"""
    _heading("3. Keys that could encode hierarchy")
    top_level = sorted({key for view in views for key in view})
    meta_keys = sorted(
        {
            key
            for view in views
            if isinstance(view.get("fibery/meta"), dict)
            for key in view["fibery/meta"]
        }
    )
    print("Top-level view keys:")
    for key in top_level:
        print(f"  {key}{_hint(key)}")
    print("\nKeys seen inside 'fibery/meta':")
    for key in meta_keys or ["  (fibery/meta was empty on every view)"]:
        print(f"  {key}{_hint(key)}" if meta_keys else key)

    suspects = [k for k in top_level + meta_keys if _hint(k)]
    print(f"\n  Candidate hierarchy keys: {suspects or 'NONE — no key names a parent'}")
    print(
        "  Names containing '/' would indicate the slash-path emulation the\n"
        "  current implementation uses, not real nesting."
    )


def _report_project_schema(client: FiberyClient, space: str) -> None:
    """Question 3: what type is Documents Root, and what do Projects store?"""
    _heading("4. Project database Fields")
    database = f"{space}/{PROJECT_DATABASE_NAME}"
    schema = client.command("fibery.schema/query")
    fields = next(
        (
            entry.get("fibery/fields", [])
            for entry in (schema or {}).get("fibery/types", [])
            if entry.get("fibery/name") == database
        ),
        None,
    )
    if fields is None:
        print(f"  Database {database!r} not found in the workspace schema.")
        return
    for field in sorted(fields, key=lambda f: f.get("fibery/name", "")):
        print(f"  {field.get('fibery/name')!r}: {field.get('fibery/type')!r}")

    _heading("5. Values existing Projects store in Documents Root")
    root_field = next(
        (
            field.get("fibery/name")
            for field in fields
            if field.get("fibery/name", "").split("/")[-1].lower() == "documents root"
        ),
        None,
    )
    if root_field is None:
        print("  No 'Documents Root' Field exists on the Project database.")
        return
    rows = (
        client.command(
            "fibery.entity/query",
            {
                "query": {
                    "q/from": database,
                    "q/select": ["fibery/id", root_field],
                    "q/limit": 20,
                }
            },
        )
        or []
    )
    if not rows:
        print("  No Project entities exist yet, so the field is unproven.")
    for row in rows:
        print(f"  {row.get('fibery/id')} -> {row.get(root_field)!r}")


def _samples(views: list[dict[str, Any]], type_name: str) -> list[dict[str, Any]]:
    matching = [view for view in views if view.get("fibery/type") == type_name]
    return matching[:SAMPLE_VIEWS_PER_TYPE]


def _hint(key: str) -> str:
    lowered = key.lower()
    return (
        "   <-- possible hierarchy"
        if any(hint in lowered for hint in NESTING_KEY_HINTS)
        else ""
    )


def _heading(title: str) -> None:
    print(f"\n{SEPARATOR}\n{title}\n{SEPARATOR}")


if __name__ == "__main__":
    raise SystemExit(main())
