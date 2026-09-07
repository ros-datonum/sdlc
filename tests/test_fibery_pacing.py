"""The one Fibery transport policy: paced requests and bounded read-only retry.

Every scenario drives the real FiberyClient, and where it matters the real
adapters above it, through a recording URL opener and a fake monotonic
clock whose sleeper advances it. Nothing here waits for real time.
"""

import email.message
import io
import json
import urllib.error

import pytest

from sdlc.fibery_client import (
    DEFAULT_MIN_INTERVAL_SECONDS,
    MAX_ATTEMPTS,
    MAX_RETRY_WAIT_SECONDS,
    FiberyClient,
)
from sdlc.fibery_http import FiberyRequirementWorkspace
from sdlc.fibery_workspace import FiberyError
from test_fibery_http import SETTINGS, StubResponse, ok, rpc
from test_fibery_requirement_http import REQUIREMENT_SCHEMA

INTERVAL = DEFAULT_MIN_INTERVAL_SECONDS
START = 1000.0
WALL = 1_700_000_000.0


class FakeClock:
    """A monotonic clock that only moves when something sleeps or works."""

    def __init__(self):
        self.now = START
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        assert seconds > 0
        self.sleeps.append(seconds)
        self.now += seconds


def http_error(code, headers=None, body=b"rate limited"):
    message = email.message.Message()
    for key, value in (headers or {}).items():
        message[key] = value
    return urllib.error.HTTPError("https://x", code, "err", message, io.BytesIO(body))


class Takes:
    """A canned response that also consumes clock time, like a slow request."""

    def __init__(self, seconds, payload):
        self.seconds = seconds
        self.payload = payload


class RecordingOpener:
    """Replays canned outcomes and records when and what was sent."""

    def __init__(self, clock, outcomes):
        self.clock = clock
        self.outcomes = list(outcomes)
        self.requests = []

    def __call__(self, request, timeout):
        self.requests.append(
            {
                "at": self.clock(),
                "method": request.method,
                "url": request.full_url,
                "body": (
                    json.loads(request.data.decode("utf-8"))
                    if request.data is not None
                    else None
                ),
            }
        )
        if not self.outcomes:
            raise AssertionError(
                f"unexpected request {request.method} {request.full_url}"
            )
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Takes):
            self.clock.now += outcome.seconds
            outcome = outcome.payload
        if isinstance(outcome, Exception):
            raise outcome
        return StubResponse(json.dumps(outcome).encode("utf-8"))

    @property
    def starts(self):
        return [entry["at"] for entry in self.requests]

    @property
    def gaps(self):
        return [b - a for a, b in zip(self.starts, self.starts[1:], strict=False)]


def build(outcomes, clock=None, wall=None):
    clock = clock or FakeClock()
    opener = RecordingOpener(clock, outcomes)
    client = FiberyClient(
        SETTINGS,
        url_opener=opener,
        clock=clock,
        sleeper=clock.sleep,
        wall_clock=wall or (lambda: WALL),
    )
    return client, opener, clock


QUERY = ("fibery.entity/query", {"query": {}})
DOC = {"content": "# body"}


# -- pacing -------------------------------------------------------------------


def test_the_first_request_waits_one_interval():
    client, opener, clock = build([ok([])])

    client.command(*QUERY)

    assert clock.sleeps == [INTERVAL]
    assert opener.starts == [START + INTERVAL]


def test_rapid_reads_are_spaced():
    client, opener, _ = build([ok([]), ok([]), ok([])])

    for _ in range(3):
        client.command(*QUERY)

    assert opener.gaps == [INTERVAL, INTERVAL]


def test_rapid_writes_are_spaced():
    client, opener, _ = build([None, None, None])

    for _ in range(3):
        client.put_document("s", "x")

    assert opener.gaps == [INTERVAL, INTERVAL]


def test_command_view_and_content_requests_share_one_interval():
    client, opener, _ = build([ok([]), rpc([]), DOC, None, rpc({})])

    client.command(*QUERY)
    client.views_rpc("query-views", {})
    client.get_document("s")
    client.put_document("s", "x")
    client.views_rpc("create-views", {"views": []})

    assert opener.gaps == [INTERVAL] * 4
    assert [r["url"].rsplit("/", 1)[-1].split("?")[0] for r in opener.requests] == [
        "commands",
        "json-rpc",
        "s",
        "s",
        "json-rpc",
    ]


def test_a_failed_request_consumes_a_slot():
    client, opener, _ = build([http_error(500), ok([])])

    with pytest.raises(FiberyError, match="HTTP 500"):
        client.command(*QUERY)
    client.command(*QUERY)

    assert opener.gaps == [INTERVAL]


def test_idle_time_earns_no_burst():
    client, opener, clock = build([ok([]), ok([]), ok([])])

    client.command(*QUERY)
    clock.now += 60.0
    client.command(*QUERY)
    client.command(*QUERY)

    assert clock.sleeps == [INTERVAL, INTERVAL], "no wait after idling, then paced"
    assert opener.gaps[1] == INTERVAL


def test_a_long_request_delays_the_next_one_no_further():
    client, opener, clock = build([Takes(2.0, ok([])), ok([])])

    client.command(*QUERY)
    client.command(*QUERY)

    assert clock.sleeps == [INTERVAL], "only the initial cooldown"
    assert opener.gaps == [2.0]


def test_a_new_client_gets_no_free_burst_after_a_previous_one():
    clock = FakeClock()
    first, first_opener, _ = build([ok([])], clock=clock)
    first.command(*QUERY)
    second, second_opener, _ = build([ok([])], clock=clock)

    second.command(*QUERY)

    assert second_opener.starts[0] - first_opener.starts[0] >= INTERVAL


def test_retries_stay_paced():
    client, opener, clock = build([http_error(429), http_error(429), ok([1])])

    assert client.command(*QUERY) == [1]

    assert all(gap >= INTERVAL for gap in opener.gaps)
    assert clock.sleeps[0] == INTERVAL and 1.0 in clock.sleeps and 2.0 in clock.sleeps


# -- bounded read-only retry --------------------------------------------------


def test_a_rate_limited_read_recovers_with_the_real_response():
    client, opener, _ = build([http_error(429), ok([{"row": 1}])])

    assert client.command(*QUERY) == [{"row": 1}]
    assert len(opener.requests) == 2


def test_a_rate_limited_document_read_recovers():
    client, opener, _ = build([http_error(429), DOC])

    assert client.get_document("s") == "# body"
    assert [r["method"] for r in opener.requests] == ["GET", "GET"]


def test_a_rate_limited_read_only_view_query_recovers():
    client, opener, _ = build([http_error(429), rpc([{"id": "v"}])])

    assert client.views_rpc("query-folders", {}) == [{"id": "v"}]
    assert len(opener.requests) == 2


def test_repeated_rate_limiting_exhausts_the_attempt_budget():
    """Three attempts in total is the contract, not whatever the constant says."""
    client, opener, clock = build([http_error(429)] * 10)

    with pytest.raises(FiberyError, match="all 3 attempts") as info:
        client.command(*QUERY)

    assert len(opener.requests) == 3
    assert MAX_ATTEMPTS == 3
    assert sum(clock.sleeps) <= MAX_RETRY_WAIT_SECONDS + MAX_ATTEMPTS * INTERVAL
    assert "rate limited" not in str(info.value), "no response body"
    assert "test-token" not in str(info.value)


def test_a_valid_retry_after_is_respected():
    client, opener, clock = build([http_error(429, {"Retry-After": "4"}), ok([])])

    client.command(*QUERY)

    assert 4.0 in clock.sleeps
    assert opener.gaps[0] >= 4.0


def test_an_http_date_retry_after_is_respected():
    due = "Thu, 14 Nov 2023 22:13:28 GMT"  # WALL + 8 seconds
    client, opener, clock = build([http_error(429, {"Retry-After": due}), ok([])])

    client.command(*QUERY)

    assert any(abs(sleep - 8.0) < 0.01 for sleep in clock.sleeps)
    assert opener.gaps[0] >= 8.0


def test_an_excessive_server_delay_fails_instead_of_retrying_early():
    client, opener, clock = build([http_error(429, {"Retry-After": "600"}), ok([])])

    with pytest.raises(FiberyError, match="exceeds the .*retry budget"):
        client.command(*QUERY)

    assert len(opener.requests) == 1
    assert clock.sleeps == [INTERVAL], "no early retry, no waiting for 600s"


def test_the_wait_budget_bounds_the_total_delay():
    client, opener, _ = build(
        [http_error(429, {"Retry-After": "6"}), http_error(429, {"Retry-After": "6"})]
    )

    with pytest.raises(FiberyError, match="retry budget"):
        client.command(*QUERY)

    assert len(opener.requests) == 2


@pytest.mark.parametrize("value", ["soon", "-5", "", "Tue, 99 Foo 2023"])
def test_malformed_retry_after_uses_the_bounded_backoff(value):
    client, opener, clock = build([http_error(429, {"Retry-After": value}), ok([])])

    client.command(*QUERY)

    assert 1.0 in clock.sleeps
    assert len(opener.requests) == 2


def test_a_read_only_batch_is_retried_as_a_whole():
    client, opener, _ = build([http_error(429), [ok([])[0], ok([])[0]]])

    envelopes = client.commands(
        [{"command": "fibery.schema/query"}, {"command": QUERY[0]}]
    )

    assert len(envelopes) == 2 and len(opener.requests) == 2


# -- nothing else is replayed -------------------------------------------------


def test_a_rate_limited_write_is_attempted_once():
    client, opener, _ = build([http_error(429)])

    with pytest.raises(FiberyError, match="not replayed") as info:
        client.put_document("s", "x")

    assert len(opener.requests) == 1
    assert "not replayable" in str(info.value) and "s?format" not in str(info.value)


def test_a_rate_limited_mutation_command_is_attempted_once():
    client, opener, _ = build([http_error(429)])

    with pytest.raises(FiberyError, match="not replayed"):
        client.command("fibery.entity/create", {"type": "x", "entity": {}})

    assert len(opener.requests) == 1


def test_a_rate_limited_mutating_view_method_is_attempted_once():
    client, opener, _ = build([http_error(429)])

    with pytest.raises(FiberyError, match="not replayed"):
        client.views_rpc("update-views", {"updates": []})

    assert len(opener.requests) == 1


def test_a_write_that_times_out_is_attempted_once():
    client, opener, _ = build([TimeoutError("timed out")])

    with pytest.raises(FiberyError, match="Could not reach"):
        client.put_document("s", "x")

    assert len(opener.requests) == 1


def test_a_mixed_batch_is_attempted_once():
    client, opener, _ = build([http_error(429)])

    with pytest.raises(FiberyError, match="not replayed"):
        client.commands([{"command": QUERY[0]}, {"command": "fibery.entity/update"}])

    assert len(opener.requests) == 1


def test_an_unknown_operation_is_attempted_once():
    client, opener, _ = build([http_error(429)])

    with pytest.raises(FiberyError, match="not replayed"):
        client.command("fibery.entity/frobnicate")

    assert len(opener.requests) == 1


def test_an_empty_batch_is_not_replayable():
    client, opener, _ = build([http_error(429)])

    with pytest.raises(FiberyError, match="not replayed"):
        client.commands([])

    assert len(opener.requests) == 1


def test_a_failed_command_inside_a_200_batch_is_not_replayed():
    failed = [{"success": False, "result": {"name": "entity.error/x", "message": "m"}}]
    client, opener, _ = build([failed])

    with pytest.raises(FiberyError, match="error envelope"):
        client.command(*QUERY)

    assert len(opener.requests) == 1


@pytest.mark.parametrize("code", [400, 401, 403, 404, 500, 503])
def test_other_http_failures_are_not_retried(code):
    client, opener, _ = build([http_error(code)])

    with pytest.raises(FiberyError, match=f"HTTP {code}"):
        client.command(*QUERY)

    assert len(opener.requests) == 1


# -- an uncertain write ---------------------------------------------------


def test_a_write_that_lands_but_raises_is_not_repeated():
    """The transport stores the body, then the connection drops."""
    stored = []

    class Storing(RecordingOpener):
        def __call__(self, request, timeout):
            super().__call__(request, timeout)
            stored.append(json.loads(request.data.decode("utf-8"))["content"])
            raise ConnectionResetError("reset after write")

    clock = FakeClock()
    opener = Storing(clock, [None])
    client = FiberyClient(SETTINGS, url_opener=opener, clock=clock, sleeper=clock.sleep)
    workspace = FiberyRequirementWorkspace(client, "SDLC", "space-uuid")

    with pytest.raises(FiberyError, match="Could not reach"):
        workspace.write_document_content("secret-1", "# once")

    assert stored == ["# once"], "applied exactly once"
    assert len(opener.requests) == 1
    # The caller sees a failure; the durable body is what the recovery paths
    # of the processors read back on the next run (tests/test_empty_result_recovery.py).


# -- through the adapters -----------------------------------------------------


def adapter(outcomes, schema=True):
    client, opener, clock = build(
        [*([ok(REQUIREMENT_SCHEMA)] if schema else []), *outcomes]
    )
    return FiberyRequirementWorkspace(client, "SDLC", "space-uuid"), opener, clock


def test_a_transient_rate_limit_during_a_preflight_read_recovers():
    workspace, opener, _ = adapter([http_error(429), ok([])])

    assert workspace.find_requirement_by_fingerprint("project-1", "fp") is None
    assert [r["body"][0]["command"] for r in opener.requests[1:]] == [QUERY[0]] * 2


def test_exhausted_preflight_reads_cause_no_mutation():
    workspace, opener, _ = adapter([http_error(429)] * MAX_ATTEMPTS)

    with pytest.raises(FiberyError, match="attempts"):
        workspace.find_requirement_by_fingerprint("project-1", "fp")

    assert all(
        r["body"][0]["command"] in {"fibery.schema/query", QUERY[0]}
        for r in opener.requests
    )
    assert len(opener.requests) == 1 + MAX_ATTEMPTS


def test_a_failed_read_back_after_a_write_does_not_replay_the_write():
    workspace, opener, _ = adapter(
        [None, *[http_error(429)] * MAX_ATTEMPTS], schema=False
    )

    workspace.write_document_content("secret-1", "# body")
    with pytest.raises(FiberyError, match="attempts"):
        workspace.read_document_content("secret-1")

    assert [r["method"] for r in opener.requests] == [
        "PUT",
        *["GET"] * MAX_ATTEMPTS,
    ]


def test_adapter_traffic_is_paced_across_endpoint_families():
    workspace, opener, _ = adapter([rpc([]), DOC, None], schema=False)

    workspace.child_folders("f")
    workspace.read_document_content("secret-1")
    workspace.write_document_content("secret-1", "# body")

    assert all(gap >= INTERVAL for gap in opener.gaps)


# -- diagnostics carry no server text -----------------------------------------

REQ_MARKER = "REQ-PRIVATE-TEXT-7f21c"
TOKEN_MARKER = "tok-synthetic-3b9c4d5e"
SECRET_MARKER = "docsecret-ab12cd34"
SHORT_MARKER = "zq7private"
PRIVATE = (REQ_MARKER, TOKEN_MARKER, SECRET_MARKER, SHORT_MARKER)
BODY = f'{{"message": "bad value {REQ_MARKER}", "token": "{TOKEN_MARKER}", "secret": "{SECRET_MARKER}"}}'


def assert_withheld(error, *also):
    text = str(error) + repr(error) + "".join(also)
    for marker in PRIVATE:
        assert marker not in text, marker
    assert "/api/" not in text and "test-token" not in text


@pytest.mark.parametrize(
    ("code", "call", "family"),
    [
        (400, lambda c: c.command(*QUERY), "commands"),
        (403, lambda c: c.command("fibery.entity/create", {"entity": {}}), "commands"),
        (400, lambda c: c.put_document(SECRET_MARKER, REQ_MARKER), "documents"),
        (500, lambda c: c.views_rpc("create-views", {"views": []}), "views"),
    ],
    ids=["read-400", "create-403", "put-400", "views-500"],
)
def test_non_429_http_failures_name_status_and_family_only(code, call, family):
    client, opener, _ = build([http_error(code, body=BODY.encode())])

    with pytest.raises(FiberyError, match=f"HTTP {code}") as info:
        call(client)

    assert family in str(info.value) and "attempt 1" in str(info.value)
    assert_withheld(info.value)
    assert len(opener.requests) == 1


def test_a_document_404_never_names_the_secret():
    body = f"Document {SECRET_MARKER} not found".encode()
    client, opener, _ = build([http_error(404, body=body)])

    with pytest.raises(FiberyError, match="HTTP 404") as info:
        client.get_document(SECRET_MARKER)

    assert "documents" in str(info.value) and "GET" in str(info.value)
    assert_withheld(info.value)
    assert SECRET_MARKER in opener.requests[0]["url"], "the request itself was real"


@pytest.mark.parametrize(
    "error",
    [
        {"code": -32602, "message": REQ_MARKER, "data": {"secret": SECRET_MARKER}},
        {"code": SHORT_MARKER, "message": REQ_MARKER},
        {"name": SHORT_MARKER, "message": REQ_MARKER, "data": [TOKEN_MARKER]},
        REQ_MARKER,
    ],
    ids=["int-code", "short-string-code", "short-name", "bare-string"],
)
def test_a_views_rpc_error_relays_no_message_data_or_unknown_code(error):
    client, opener, _ = build([{"jsonrpc": "2.0", "id": 1, "error": error}])

    with pytest.raises(FiberyError, match="JSON-RPC error") as info:
        client.views_rpc("update-views", {"updates": []})

    assert_withheld(info.value)
    assert len(opener.requests) == 1


def test_a_recognized_integer_rpc_code_is_still_reported():
    error = {"code": -32602, "message": REQ_MARKER}
    client, _, _ = build([{"jsonrpc": "2.0", "id": 1, "error": error}])

    with pytest.raises(FiberyError, match=r"code -32602") as info:
        client.views_rpc("query-views", {})

    assert_withheld(info.value)


@pytest.mark.parametrize(
    "result",
    [
        {
            "name": SHORT_MARKER,
            "message": REQ_MARKER,
            "data": {"secret": SECRET_MARKER},
        },
        {"name": "entity.error/validation", "message": f"{TOKEN_MARKER} {REQ_MARKER}"},
        REQ_MARKER,
        None,
    ],
    ids=["short-name", "known-looking-name", "string", "none"],
)
def test_a_failed_command_envelope_relays_no_message_and_is_not_retried(result):
    client, opener, _ = build([[{"success": False, "result": result}]])

    with pytest.raises(FiberyError, match="error envelope") as info:
        client.command("fibery.entity/create", {"entity": {"x": REQ_MARKER}})

    assert_withheld(info.value)
    assert len(opener.requests) == 1


def test_a_mixed_batch_keeps_its_successful_envelopes_and_is_not_replayed():
    envelopes = [
        {"success": True, "result": {"fibery/id": "created-1"}},
        {"success": False, "result": {"name": SHORT_MARKER, "message": REQ_MARKER}},
    ]
    client, opener, _ = build([envelopes])

    returned = client.commands(
        [{"command": "fibery.entity/create"}, {"command": "fibery.entity/update"}]
    )

    assert returned[0]["result"]["fibery/id"] == "created-1", "durable id visible"
    assert returned[1]["success"] is False
    assert len(opener.requests) == 1


@pytest.mark.parametrize(
    ("failure", "kind"),
    [
        (TimeoutError("timed out " + REQ_MARKER), "timed out"),
        (urllib.error.URLError(TimeoutError(REQ_MARKER)), "timed out"),
        (ConnectionResetError(54, REQ_MARKER), "connection failed"),
        (urllib.error.URLError(f"[Errno 61] {REQ_MARKER}"), "connection failed"),
    ],
    ids=["timeout", "url-timeout", "reset", "url-error"],
)
def test_transport_failures_are_classified_without_exception_text(failure, kind):
    client, opener, _ = build([failure])

    with pytest.raises(FiberyError, match=kind) as info:
        client.put_document(SECRET_MARKER, REQ_MARKER)

    assert "attempted once" in str(info.value)
    assert_withheld(info.value)
    assert len(opener.requests) == 1


def test_transport_errors_stay_withheld_through_processor_and_cli(caplog):
    import io
    import logging

    from processor_fake import (
        FakeModelRuntime,
        build_workspace,
        candidate,
        model_output,
    )
    from sdlc import cli
    from sdlc.raw_processor import process_raw_requirement

    caplog.set_level(logging.DEBUG)
    client, _, _ = build([http_error(400, body=BODY.encode())])
    with pytest.raises(FiberyError) as info:
        client.put_document(SECRET_MARKER, REQ_MARKER)
    ws, raw, _ = build_workspace()
    ws.failures["write_document_content"] = info.value

    result = process_raw_requirement(
        ws, FakeModelRuntime([model_output([candidate()])]), raw.id
    )
    rendered = io.StringIO()
    cli.render_process_result(result, rendered)

    assert result.code.value == "PARTIAL_PROCESSING"
    created = " ".join(result.created)
    assert "Processing Result Document" in created and "(doc-" in created, (
        "the created Document id stays reported for recovery"
    )
    assert_withheld(info.value, " ".join(result.details), result.message, created)
    assert_withheld(info.value, rendered.getvalue(), caplog.text)
    assert "HTTP 400" in rendered.getvalue()
