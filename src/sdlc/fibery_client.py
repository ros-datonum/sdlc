"""HTTP transport for the three Fibery endpoints the capabilities need.

- ``/api/commands`` for schema and entity commands
- ``/api/views/json-rpc`` for document views and folders
- ``/api/documents/<secret>`` for rich text content

Every outbound request passes through ``_request``, which is where the one
transport policy lives:

- **Pacing.** Request starts are at least ``DEFAULT_MIN_INTERVAL_SECONDS``
  apart, measured on a monotonic clock, for every endpoint family and for
  reads and writes alike. The first request of a client observes the same
  interval, so a new process cannot open with a burst on the heels of the
  previous one; idle time earns no credit; a failed attempt takes a slot; a
  request that already outlasted the interval delays nothing further.
- **Bounded read-only retry.** Only a request whose semantics are explicitly
  known to be read-only is retried after a top-level HTTP 429, at most
  ``MAX_ATTEMPTS`` attempts in total, with bounded backoff, within a finite
  wait budget, honouring a valid ``Retry-After`` and never retrying earlier
  than it permits. Everything else is attempted exactly once: a mutation, a
  batch that is not entirely read-only, an unknown command, a validation or
  authentication failure, a 200 carrying a failed command, a timeout or a
  connection error. A rejected write is not proven unapplied, so it is left
  to the callers' partial-state and recovery logic.

The policy is per client instance, so per process. Simultaneous SDLC
processes and unrelated clients share the workspace's limits without
coordination; the supported rule is one active SDLC command per workspace.

The URL opener, clock and sleeper are injected so the transport and its
policy can be exercised without network access or real waiting.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from email.utils import parsedate_to_datetime
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

# Diagnostics are authored here from a fixed vocabulary: endpoint family,
# HTTP status, operation category, attempt count and a JSON-RPC integer code.
# Response bodies, vendor error names and messages, request paths and
# exception text are never relayed: a body can echo requirement prose or a
# document secret, and an unknown vendor name is not safe just because it is
# short.
FAMILY_COMMANDS = "commands"
FAMILY_VIEWS = "views"
FAMILY_DOCUMENTS = "documents"
FAMILY_UNKNOWN = "unknown endpoint"
FAILURE_TIMED_OUT = "the connection timed out"
FAILURE_UNREACHABLE = "the connection failed"
WITHHELD = "the server's response is not reported"

# Fibery documents 3 requests/second per token and 7 per workspace. Half a
# second between starts stays under the per-token limit with margin for the
# server's own accounting and for the previous process's tail.
DEFAULT_MIN_INTERVAL_SECONDS = 0.5

RATE_LIMIT_STATUS = 429
RETRY_AFTER_HEADER = "Retry-After"
# Total attempts including the first; the backoff before attempt 2 and 3.
MAX_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = (1.0, 2.0)
# The most a single request may spend waiting for retries, all attempts
# together. A server delay beyond what is left of it ends the request.
MAX_RETRY_WAIT_SECONDS = 10.0

# The only operations known to be replay-safe. Fibery uses POST for queries
# and mutations alike, so the HTTP method says nothing; these names do.
READ_ONLY_COMMANDS = frozenset({"fibery.schema/query", "fibery.entity/query"})
READ_ONLY_VIEW_METHODS = frozenset({"query-folders", "query-views"})

CATEGORY_READ_ONLY = "read-only"
CATEGORY_NOT_REPLAYABLE = "not replayable"

UrlOpener = Callable[[urllib.request.Request, float], Any]
Clock = Callable[[], float]
Sleeper = Callable[[float], None]


def _open_url(request: urllib.request.Request, timeout: float) -> Any:
    return urllib.request.urlopen(request, timeout=timeout)


class RequestPacer:
    """Keeps request starts at least one interval apart on a monotonic clock.

    The first slot opens one interval after construction. Each slot is taken
    from the actual start time, never from a schedule, so waiting idle earns
    nothing and a slow request that already spanned the interval pays nothing.
    """

    def __init__(self, min_interval: float, clock: Clock, sleeper: Sleeper) -> None:
        self._interval = min_interval
        self._clock = clock
        self._sleep = sleeper
        self._next_start = clock() + min_interval

    def wait_for_slot(self) -> None:
        now = self._clock()
        if now < self._next_start:
            self._sleep(self._next_start - now)
            now = max(self._clock(), self._next_start)
        self._next_start = now + self._interval


class FiberyClient:
    """Speaks Fibery's HTTP protocols and raises FiberyError on any failure."""

    def __init__(
        self,
        settings: FiberySettings,
        url_opener: UrlOpener = _open_url,
        clock: Clock = time.monotonic,
        sleeper: Sleeper = time.sleep,
        wall_clock: Clock = time.time,
        min_interval_seconds: float = DEFAULT_MIN_INTERVAL_SECONDS,
    ) -> None:
        self._settings = settings
        self._open = url_opener
        self._sleep = sleeper
        self._wall_clock = wall_clock
        self._pacer = RequestPacer(min_interval_seconds, clock, sleeper)

    @property
    def workspace_identity(self) -> str:
        """Host and Space id, the stable non-secret identity of this workspace."""
        return f"{self._settings.host.strip().lower()}/{self._settings.space_id}"

    def command(self, name: str, args: dict[str, Any] | None = None) -> Any:
        """Run one Commands API command and return its unwrapped result."""
        payload: dict[str, Any] = {"command": name}
        if args is not None:
            payload["args"] = args
        envelope = self.commands([payload])[0]
        if not envelope.get("success"):
            raise FiberyError(
                f"Command {name!r} failed: Fibery returned an error envelope; "
                f"{WITHHELD}."
            )
        return envelope.get("result")

    def commands(self, batch: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
        """Send one Commands API batch and return its envelopes.

        The batch may be replayed after a rate-limit response only when every
        command in it is explicitly known to be read-only. A batch is not
        transactional (constraint 16), so a 200 carrying a failed envelope is
        the caller's to interpret and is never resent from here.
        """
        replayable = bool(batch) and all(
            entry.get("command") in READ_ONLY_COMMANDS for entry in batch
        )
        envelopes = self._request("POST", COMMANDS_PATH, list(batch), replayable)
        if not isinstance(envelopes, list) or len(envelopes) != len(batch):
            raise FiberyError("The Commands API returned an unexpected response.")
        return envelopes

    def views_rpc(self, method: str, params: dict[str, Any]) -> Any:
        """Run one Views API JSON-RPC method and return its result."""
        response = self._request(
            "POST",
            VIEWS_RPC_PATH,
            {
                "jsonrpc": JSON_RPC_VERSION,
                "id": JSON_RPC_REQUEST_ID,
                "method": method,
                "params": params,
            },
            method in READ_ONLY_VIEW_METHODS,
        )
        if not isinstance(response, dict):
            raise FiberyError(
                f"Views method {method!r} returned an unexpected response."
            )
        if "error" in response:
            raise FiberyError(
                f"Views method {method!r} failed: Fibery returned a JSON-RPC error"
                f"{_rpc_code(response['error'])}; {WITHHELD}."
            )
        return response.get("result")

    def put_document(self, secret: str, content: str) -> None:
        """Replace a collaborative document's Markdown content."""
        self._request(
            "PUT",
            f"{DOCUMENTS_PATH}/{secret}?format={DOCUMENT_FORMAT}",
            {"content": content},
            False,
        )

    def get_document(self, secret: str) -> str:
        """Read a collaborative document's Markdown content."""
        body = self._request(
            "GET", f"{DOCUMENTS_PATH}/{secret}?format={DOCUMENT_FORMAT}", None, True
        )
        return (body or {}).get("content", "")

    # -- the transport policy ----------------------------------------------

    def _request(self, method: str, path: str, payload: Any, replayable: bool) -> Any:
        """Send one request under pacing, retrying only what is replay-safe."""
        family = _family(path)
        category = CATEGORY_READ_ONLY if replayable else CATEGORY_NOT_REPLAYABLE
        waited = 0.0
        for attempt in range(1, MAX_ATTEMPTS + 1):
            self._pacer.wait_for_slot()
            try:
                return self._send(method, path, payload)
            except urllib.error.HTTPError as error:
                if error.code != RATE_LIMIT_STATUS:
                    raise FiberyError(
                        f"Fibery {category} {method} {family} request failed "
                        f"(HTTP {error.code}) on attempt {attempt}; {WITHHELD}."
                    ) from error
                if not replayable:
                    raise FiberyError(
                        f"Fibery rate-limited (HTTP {error.code}) a {category} "
                        f"{method} {family} request. It was attempted once and not "
                        "replayed: a replay could apply the change twice. Wait, "
                        "then rerun the command; it resumes from durable state."
                    ) from error
                if attempt == MAX_ATTEMPTS:
                    raise FiberyError(
                        f"Fibery rate-limited (HTTP {error.code}) a {category} "
                        f"{method} {family} request on all {attempt} attempts "
                        f"(waited {waited:.1f}s between them). Wait, then rerun."
                    ) from error
                delay = max(
                    RETRY_BACKOFF_SECONDS[attempt - 1], self._retry_after(error)
                )
                if waited + delay > MAX_RETRY_WAIT_SECONDS:
                    raise FiberyError(
                        f"Fibery rate-limited (HTTP {error.code}) a {category} "
                        f"{method} {family} request; the {delay:.0f}s delay it "
                        f"asks for after {attempt} attempt(s) exceeds the "
                        f"{MAX_RETRY_WAIT_SECONDS:.0f}s retry budget, so it was not "
                        "retried early. Wait, then rerun."
                    ) from error
                self._sleep(delay)
                waited += delay
        raise AssertionError("unreachable: every attempt returns or raises")

    def _send(self, method: str, path: str, payload: Any) -> Any:
        request = urllib.request.Request(
            url=f"{self._settings.base_url}{path}",
            method=method,
            data=None if payload is None else json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"{AUTH_SCHEME} {self._settings.token}",
                "Content-Type": CONTENT_TYPE,
            },
        )
        try:
            with self._open(request, self._settings.timeout_seconds) as response:
                body = response.read()
        except urllib.error.HTTPError:
            raise
        except OSError as error:
            raise FiberyError(
                f"Could not reach Fibery ({method} {_family(path)}): "
                f"{_failure_kind(error)}; the request was attempted once."
            ) from error

        if not body:
            return None
        try:
            return json.loads(body)
        except ValueError as error:
            raise FiberyError(
                f"Fibery returned a non-JSON body for {method} {_family(path)}."
            ) from error

    def _retry_after(self, error: urllib.error.HTTPError) -> float:
        """The server's minimum delay in seconds, or 0 when absent or malformed.

        Supported forms are delta-seconds and an HTTP-date. Anything else is
        treated as no guidance and the bounded local backoff applies.
        """
        raw = error.headers.get(RETRY_AFTER_HEADER) if error.headers else None
        if raw is None:
            return 0.0
        text = raw.strip()
        if text.isdigit():
            return float(text)
        try:
            due = parsedate_to_datetime(text)
        except (TypeError, ValueError):
            return 0.0
        if due.tzinfo is None:
            return 0.0
        return max(0.0, due.timestamp() - self._wall_clock())


def _family(path: str) -> str:
    """Name the endpoint family; never the path, which can carry a secret."""
    if path.startswith(DOCUMENTS_PATH):
        return FAMILY_DOCUMENTS
    if path == VIEWS_RPC_PATH:
        return FAMILY_VIEWS
    if path == COMMANDS_PATH:
        return FAMILY_COMMANDS
    return FAMILY_UNKNOWN


def _failure_kind(error: OSError) -> str:
    """Classify a transport failure without quoting the exception."""
    reason = getattr(error, "reason", None)
    if isinstance(error, TimeoutError) or isinstance(reason, TimeoutError):
        return FAILURE_TIMED_OUT
    return FAILURE_UNREACHABLE


def _rpc_code(error: Any) -> str:
    """Only an integer JSON-RPC code is a machine category worth naming."""
    code = error.get("code") if isinstance(error, dict) else None
    if isinstance(code, int) and not isinstance(code, bool):
        return f" (code {code})"
    return ""
