---
name: review-approved-spec
description: Use to review implementation against the current approved SDLC spec without redesigning it.
---

1. Resolve the current approved specification.
2. Compare the implementation and tests against every normative behavior in the spec.
3. Check for unsupported scope and missing failure handling.
4. For model runtime code, verify local authenticated CLI transport only.
5. Verify project Claude/Codex config does not override global permission/edit-mode/auth settings.
6. Return findings ordered by severity with file references.
