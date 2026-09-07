#!/usr/bin/env bash
# Local model authentication diagnostic.
#
# Reports, for every runtime in config/sdlc.toml, whether its local CLI login
# satisfies the SDLC authentication policy, and whether that runtime is
# permitted for SDLC reasoning execution. Being authenticated is not the same
# as being eligible.
#
# The check goes through the runtime's own validator (LocalCliModelRuntime
# .preflight), so there is one authentication policy. It runs the CLI's
# status command only: no model call, no login, no logout, no configuration
# or credential change. CLI output is captured and validated, never printed;
# only SDLC-authored summaries appear here.
set -u

cd "$(dirname "$0")/.." || exit 1

uv run --locked --quiet python - <<'PYTHON'
import sys

from sdlc.model_runtime import LocalCliModelRuntime, ModelRuntimeError
from sdlc.model_runtime_config import (
    ModelRuntimeConfigError,
    RuntimeSelection,
    load_model_runtime_config,
    runtime_definition,
)

try:
    config = load_model_runtime_config()
    names = sorted(config.get("runtimes") or {})
except ModelRuntimeConfigError as error:
    print(f"FAIL configuration: {error}")
    sys.exit(1)

status = 0
for name in names:
    selection = RuntimeSelection(
        role="auth-check", definition=runtime_definition(config, name), model=None
    )
    try:
        print(f"OK   {LocalCliModelRuntime(selection).preflight()}")
    except ModelRuntimeError as error:
        print(f"FAIL {name}: authentication could not be verified: {error}")
        status = 1

print()
print("Note: SDLC runtime requires subscription/OAuth CLI authentication.")
print("It must not fall back to API keys or OpenRouter.")
print("Authenticated is not the same as eligible: a runtime reported as not")
print("eligible for SDLC reasoning execution (RUNTIME_ISOLATION_UNAVAILABLE) is")
print("logged in but blocked for model calls.")
sys.exit(status)
PYTHON
