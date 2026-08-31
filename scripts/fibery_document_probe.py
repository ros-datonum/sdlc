#!/usr/bin/env python
"""Read-only probe answering the Project Init Fibery integration spike.

This is a spike instrument, not part of the `sdlc` capability. It performs no
writes, so it is safe to run against the real workspace.

It answers the three open integration questions from
`docs/fibery/Fibery-API-Constraints-v0.1.md`:

1. how a parent/child Document hierarchy is represented, if at all;
2. whether ``fibery/type: "document"`` is the value this workspace uses;
3. what the ``Project.Documents Root`` Field type is and what it stores.

Only FIBERY_HOST and FIBERY_TOKEN are required. Section 0 reports the
candidate FIBERY_SPACE_ID values, because Fibery documents no command that maps
a Space name to its UUID:

    uv run python scripts/fibery_document_probe.py
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter

# `Any` is unavoidable here: the probe exists precisely to discover the shape of
# Fibery's view JSON, so it cannot presuppose a narrower type for it.
from typing import Any

from sdlc.config import (
    ENV_HOST,
    ENV_SPACE,
    ENV_TOKEN,
    FiberySettings,
)
from sdlc.fibery_client import FiberyClient
from sdlc.fibery_workspace import FiberyError

PROJECT_DATABASE_NAME = "Project"
CONTAINER_APP_KEY = "fibery/container-app"
ID_KEY = "fibery/id"
NAME_KEY = "fibery/name"
VIEWS_PER_SPACE = 12
SAMPLE_VIEWS_PER_TYPE = 3
NESTING_KEY_HINTS = ("parent", "folder", "container", "tree", "path", "ancestor")
SEPARATOR = "=" * 72


def main() -> int:
    """Probe the workspace read-only.

    Only FIBERY_HOST and FIBERY_TOKEN are required. FIBERY_SPACE_ID is
    deliberately not required: discovering it is one of the things the probe
    is for, and Fibery documents no command mapping a Space name to its id.
    """
    host = (os.environ.get(ENV_HOST) or "").strip()
    token = (os.environ.get(ENV_TOKEN) or "").strip()
    space = (os.environ.get(ENV_SPACE) or "").strip()
    if not host or not token:
        print(
            f"Set {ENV_HOST} and {ENV_TOKEN}. {ENV_SPACE} additionally enables "
            "the Project schema sections.",
            file=sys.stderr,
        )
        print("\nThe probe only reads. It writes nothing.", file=sys.stderr)
        return 1

    client = FiberyClient(
        FiberySettings(host=host, token=token, space=space, space_id="")
    )
    try:
        views = _report_views(client)
        _report_space_ids(views)
        _report_nesting_evidence(views)
        if space:
            _report_project_schema(client, space)
        else:
            _heading("4-5. Project schema — skipped")
            print(f"  Set {ENV_SPACE} to the Space name to include these sections.")
    except FiberyError as error:
        print(f"\nFibery call failed: {error}", file=sys.stderr)
        return 1
    return 0


def _report_space_ids(views: list[dict[str, Any]]) -> None:
    """Answer 'what is my FIBERY_SPACE_ID?' from the views themselves.

    Every View names the Space that contains it, so grouping Views by their
    container yields each Space's UUID. The View names printed under each id
    identify which Space it is.
    """
    _heading("0. Space ids (candidate FIBERY_SPACE_ID values)")
    by_space: dict[str | None, list[str]] = {}
    for view in views:
        container = view.get(CONTAINER_APP_KEY)
        space_id = container.get(ID_KEY) if isinstance(container, dict) else None
        by_space.setdefault(space_id, []).append(str(view.get(NAME_KEY)))

    if not by_space:
        print("  No views returned, so no Space id could be derived.")
        return
    if list(by_space) == [None]:
        print(
            f"  query-views did not return {CONTAINER_APP_KEY!r}.\n"
            "  Read the raw JSON in section 2 for another field carrying the Space."
        )
        return

    for space_id, names in sorted(by_space.items(), key=lambda item: -len(item[1])):
        print(f"\n  FIBERY_SPACE_ID = {space_id}   ({len(names)} views)")
        for name in sorted(names)[:VIEWS_PER_SPACE]:
            print(f"      - {name}")
        if len(names) > VIEWS_PER_SPACE:
            print(f"      ... and {len(names) - VIEWS_PER_SPACE} more")
    print("\n  Pick the id whose view names match the Space holding your Databases.")


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
