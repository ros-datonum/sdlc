"""HTTP transport for the three Fibery endpoints `project init` needs.

- ``/api/commands`` for schema and entity commands
- ``/api/views/json-rpc`` for document views
- ``/api/documents/<secret>`` for rich text content

The URL opener is injected so the transport can be exercised without network
access.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from sdlc.config import FiberySettings
from sdlc.fibery_workspace import FiberyError

COMMANDS_PATH = "/api/commands"
VIEWS_RPC_PATH = "/api/views/json-rpc"
DOCUMENTS_PATH = "/api/documents"

AUTH_SCHEME = "Token"
CONTENT_TYPE = "application/json"
DOCUMENT_FORMAT = "md"
JSON_RPC_VERSION = "2.0"
JSON_RPC_REQUEST_ID = 1
ERROR_BODY_LIMIT = 500

UrlOpener = Callable[[urllib.request.Request, float], Any]


def _open_url(request: urllib.request.Request, timeout: float) -> Any:
    return urllib.request.urlopen(request, timeout=timeout)


class FiberyClient:
    """Speaks Fibery's HTTP protocols and raises FiberyError on any failure."""

    def __init__(
        self, settings: FiberySettings, url_opener: UrlOpener = _open_url
    ) -> None:
        self._settings = settings
        self._open = url_opener

    def command(self, name: str, args: dict[str, Any] | None = None) -> Any:
        """Run one Commands API command and return its unwrapped result."""
        payload: dict[str, Any] = {"command": name}
        if args is not None:
            payload["args"] = args

        envelopes = self._post(COMMANDS_PATH, [payload])
        if not isinstance(envelopes, list) or not envelopes:
            raise FiberyError(f"Command {name!r} returned an unexpected response.")

        envelope = envelopes[0]
        if not envelope.get("success"):
            raise FiberyError(f"Command {name!r} failed: {_describe(envelope)}")
        return envelope.get("result")

    def views_rpc(self, method: str, params: dict[str, Any]) -> Any:
        """Run one Views API JSON-RPC method and return its result."""
        response = self._post(
            VIEWS_RPC_PATH,
            {
                "jsonrpc": JSON_RPC_VERSION,
                "id": JSON_RPC_REQUEST_ID,
                "method": method,
                "params": params,
            },
        )
        if not isinstance(response, dict):
            raise FiberyError(
                f"Views method {method!r} returned an unexpected response."
            )
        if "error" in response:
            raise FiberyError(f"Views method {method!r} failed: {response['error']}")
        return response.get("result")

    def put_document(self, secret: str, content: str) -> None:
        """Replace a collaborative document's Markdown content."""
        self._request(
            "PUT",
            f"{DOCUMENTS_PATH}/{secret}?format={DOCUMENT_FORMAT}",
            {"content": content},
        )

    def _post(self, path: str, payload: Any) -> Any:
        return self._request("POST", path, payload)

    def _request(self, method: str, path: str, payload: Any) -> Any:
        request = urllib.request.Request(
            url=f"{self._settings.base_url}{path}",
            method=method,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"{AUTH_SCHEME} {self._settings.token}",
                "Content-Type": CONTENT_TYPE,
            },
        )
        try:
            with self._open(request, self._settings.timeout_seconds) as response:
                body = response.read()
        except urllib.error.HTTPError as error:
            raise FiberyError(
                f"Fibery returned HTTP {error.code} for {method} {path}: "
                f"{_read_error_body(error)}"
            ) from error
        except OSError as error:
            raise FiberyError(f"Could not reach Fibery at {path}: {error}") from error

        if not body:
            return None
        try:
            return json.loads(body)
        except ValueError as error:
            raise FiberyError(
                f"Fibery returned a non-JSON body for {method} {path}."
            ) from error


def _describe(envelope: dict[str, Any]) -> str:
    result = envelope.get("result")
    if isinstance(result, dict):
        name = result.get("name", "unknown error")
        return f"{name}: {result.get('message', '')}".strip().rstrip(":")
    return str(result)


def _read_error_body(error: urllib.error.HTTPError) -> str:
    return error.read().decode("utf-8", errors="replace")[:ERROR_BODY_LIMIT]
