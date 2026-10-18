# Uppercase Text HTTP Service

## Export Metadata

- Format: `sdlc/raw-requirements`
- Format Version: `0.1`
- Project Name: TSA P-1 SCRATCH — DO NOT USE
- Project Code: `TSAP1`
- Source Context: Synthetic test product for the TSA-C01 live pilot; not a real product.

## Intent

Provide a minimal public HTTP service that returns the uppercase form of a short ASCII word, so that the SDLC pipeline can be exercised end to end on a small, unambiguous requirement.

## Context

This is a synthetic product used only to exercise the SDLC requirement lifecycle and one Technical Solution Architecture cycle on a scratch Project. It has no users, no existing system and no integrations.

## Desired Outcomes

- A caller can obtain the uppercase form of a short ASCII word with one HTTP request.
- Every invalid request receives the same predictable error response.

## Requirements and Expected Behavior

- The service exposes one public endpoint: `GET /v1/uppercase`.
- A request is valid only when its query string, after standard URL decoding, contains exactly one parameter, named `text`, whose value is 1 to 32 ASCII letters (`A` to `Z` and `a` to `z`). Lowercase, uppercase and mixed-case values are all accepted.
- For a valid request the service responds with HTTP status 200 and a JSON body of exactly one member, `uppercase`, whose value is the `text` value with every letter converted to uppercase.
- Every other request to this endpoint is invalid. This includes a missing `text` parameter, an empty value, a value longer than 32 characters, a value containing any character that is not an ASCII letter, a repeated `text` parameter and any additional query parameter.
- For an invalid request the service responds with HTTP status 400 and the JSON body `{"error": "invalid_text"}`, identical for every kind of invalid input.
- Successful and error responses are declared as JSON (`application/json`). Whitespace and other formatting inside the JSON body are not significant; only the members and their values are.
- The response to a request depends only on that request: identical requests always receive identical responses, and no request affects the response to any other request.

## Examples and Scenarios

- `GET /v1/uppercase?text=hello` returns HTTP 200 with `{"uppercase": "HELLO"}`.
- `GET /v1/uppercase?text=MiXeD` returns HTTP 200 with `{"uppercase": "MIXED"}`.
- `GET /v1/uppercase` returns HTTP 400 with `{"error": "invalid_text"}`.
- `GET /v1/uppercase?text=hello1` returns HTTP 400 with `{"error": "invalid_text"}`.
- `GET /v1/uppercase?text=a&text=b` returns HTTP 400 with `{"error": "invalid_text"}`.

## Constraints

- No authentication or authorization is required to call the endpoint.
- The service stores no data persistently and keeps no state between requests.

## Accepted Decisions

- The endpoint is public.
- The service has no user interface and no user accounts.

## Open Questions

- None identified in the source context.

## Deferred / Out of Scope

- Any endpoint or HTTP method other than `GET /v1/uppercase`.
- Non-ASCII text, Unicode case mapping and values longer than 32 characters beyond rejecting them.
- Authentication, user accounts and any user interface.
- Persistent storage, logging or analytics requirements.
- Rate limiting, quotas and abuse protection.
- Performance, availability and scaling targets.
- Hosting, deployment and operational procedures.
