# Provenance — claude_runtime fixtures

## init-2.1.306-hardened.json

- **What:** the `system/init` event that Claude Code 2.1.306 emitted in the SDLC reasoning child, recorded in `pilots/ARP1/diagnostics/final-runtime-canary-2026-10-21T203821+0000.json` (call 1).
- **Build:** binary sha256 `b5d795b7760032d79954b55a9cd1876dcf3a8dc9608fd6bb9f618593f69fd44b`.
- **Configuration:** the production argv and child environment (`DISABLE_TELEMETRY=1`).
- **Sanitized fields:**
  - `cwd` and `session_id` are replaced by the placeholders `<CWD>` and `<SESSION_ID>`.
  - Fields the canary recorded as `null` are left absent, as they were in the live event: `memory_paths` and `plugin_errors`.
- **Recorded subset only:** the canary report kept a fixed subset of fields. The live event also carried `betas`, `output_style`, `uuid` and `product_feedback_disabled`, which this fixture omits. The validator reads only the fields present here.
