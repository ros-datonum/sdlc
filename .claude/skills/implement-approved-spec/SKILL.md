---
name: implement-approved-spec
description: Use when implementing one approved SDLC specification from docs/specs. Do not use for architecture ideation.
---

1. Identify the newest non-superseded specification for the requested capability.
2. Read `docs/fibery/Fibery-Schema-v0.1.md` when Fibery is involved.
3. Read `docs/runtime/Local-OAuth-Model-Runtime-Spec-v0.1.md` when model execution is involved.
4. State the bounded implementation target.
5. Inspect existing repository state before editing.
6. Implement the smallest sufficient change.
7. Add/update deterministic tests.
8. Run relevant checks.
9. Inspect the final diff.
10. Report what changed, tests run, and any spec gap.

Never add API/OpenRouter model calls.
Never modify project permission/edit-mode settings.
