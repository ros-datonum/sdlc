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

    with pytest.raises(FiberyError, match="entity.error/x"):
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
