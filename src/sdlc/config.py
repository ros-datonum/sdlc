"""Runtime configuration for Fibery access.

Fibery credentials and workspace coordinates are user and environment
specific, so they are read from the environment only and never from a tracked
file.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

ENV_HOST = "FIBERY_HOST"
ENV_TOKEN = "FIBERY_TOKEN"
ENV_SPACE = "FIBERY_SPACE"
ENV_SPACE_ID = "FIBERY_SPACE_ID"
ENV_TIMEOUT_SECONDS = "FIBERY_TIMEOUT_SECONDS"

DEFAULT_TIMEOUT_SECONDS = 30.0


class ConfigurationError(Exception):
    """Required configuration is missing or unusable."""


@dataclass(frozen=True)
class FiberySettings:
    """Everything needed to reach one Fibery workspace.

    `space` qualifies Database names (``<space>/Project``). `space_id` is the
    separate UUID the Views API needs as a container, and Fibery exposes no
    documented mapping between the two, so both are configured.
    """

    host: str
    token: str
    space: str
    space_id: str
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS

    @property
    def base_url(self) -> str:
        return f"https://{self.host}"


def load_fibery_settings(
    environment: Mapping[str, str] | None = None,
) -> FiberySettings:
    """Build settings from the environment, or explain what is missing."""
    source = os.environ if environment is None else environment

    values = {
        name: (source.get(name) or "").strip()
        for name in (ENV_HOST, ENV_TOKEN, ENV_SPACE, ENV_SPACE_ID)
    }
    missing = sorted(name for name, value in values.items() if not value)
    if missing:
        raise ConfigurationError(
            "Missing required environment variables: " + ", ".join(missing)
        )

    return FiberySettings(
        host=values[ENV_HOST],
        token=values[ENV_TOKEN],
        space=values[ENV_SPACE],
        space_id=values[ENV_SPACE_ID],
        timeout_seconds=_read_timeout(source),
    )


def _read_timeout(source: Mapping[str, str]) -> float:
    raw = (source.get(ENV_TIMEOUT_SECONDS) or "").strip()
    if not raw:
        return DEFAULT_TIMEOUT_SECONDS
    try:
        timeout = float(raw)
    except ValueError as error:
        raise ConfigurationError(
            f"{ENV_TIMEOUT_SECONDS} must be a number, got {raw!r}."
        ) from error
    if timeout <= 0:
        raise ConfigurationError(f"{ENV_TIMEOUT_SECONDS} must be positive.")
    return timeout
