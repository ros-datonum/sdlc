"""TSA artifact wire format: canonical JSON, digests, envelope and schemas.

Frozen authority: `docs/specs/TSA-C01-Implementation-Spec-v0.1.md` sections 4-7,
work item I01. This module is pure: it performs no Fibery call, no model call,
no filesystem access and writes no output. It decides bytes and refusals only.

What this module deliberately does NOT do, because later work items own it:
the Architecture Markdown renderer (I06), Reviewer derived-status derivation
(I08), disposition reference resolution against persisted artifacts (I11) and
any recovery classification (I10). Where a frozen invariant needs one of those,
the pure part is exposed here and the rest is named at the call site.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .normative_tree import NORMATIVE_TREE_VERSION, InvalidTreeManifest, TreeManifest

# ---------------------------------------------------------------------------
# Frozen constants (specification 4.2, 4.3, 4.5, 5.1, 5.2, 5.4, 3.1)
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 1

ARTIFACT_DIGEST_DOMAIN = "sdlc.tsa.v1"
MANIFEST_DIGEST_DOMAIN = "sdlc.tsa.manifest.v1"
START_INPUT_DIGEST_DOMAIN = "sdlc.tsa.start.v1"
REQUIREMENT_INPUT_DIGEST_TAG = "tsa.requirement_input"
UX_EVIDENCE_DIGEST_TAG = "tsa.ux_evidence"

ARCHITECTURE = "tsa.architecture"
INPUT_MANIFEST = "tsa.input_manifest"
PROCESS_RESULT = "tsa.process_result"
REVIEW_RESULT = "tsa.review_result"
HUMAN_DECISION = "tsa.human_decision"

ARTIFACT_TYPES = frozenset(
    {ARCHITECTURE, INPUT_MANIFEST, PROCESS_RESULT, REVIEW_RESULT, HUMAN_DECISION}
)

#: Types carrying `iteration` on the envelope; the other two must omit it (4.5).
ITERATED_ARTIFACT_TYPES = frozenset({PROCESS_RESULT, REVIEW_RESULT, HUMAN_DECISION})

ITERATION_MIN = 1
ITERATION_MAX = 999

ARCHITECT_ROLE = "tsa_architect"
REVIEWER_ROLE = "tsa_reviewer"

DIGEST_LENGTH = 64

#: Every pattern below is applied with `fullmatch`, never `match`: `$` also
#: matches before a trailing newline, which would admit `"<digest>\n"` as a
#: digest. These are whole-token grammars and are matched as such.
KEY_PATTERN = re.compile(r"[a-z][a-z0-9_]*")
DIGEST_PATTERN = re.compile(r"[0-9a-f]{64}")
TIMESTAMP_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
CYCLE_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9-]{1,38}[a-z0-9]")
REFERENCE_PATTERN = re.compile(
    r"(?P<digest>[0-9a-f]{64})#(?P<collection>[a-z_]+)/(?P<index>0|[1-9][0-9]*)"
)

#: CPython refuses to render an integer wider than `sys.get_int_max_str_digits()`
#: and raises `ValueError` from `str()`. No TSA payload holds such a value, so
#: the refusal is ours to make rather than an exception escaping `json.dumps`.
MAX_INTEGER_BIT_LENGTH = 65_536

TREE_MANIFEST_KEY = "tree_manifest"

#: The single reused subtree of schema version 1 (5.1.1), expressed as key paths
#: relative to three different roots. List levels are traversed transparently,
#: so one path covers every element of `requirements`.
_REUSED_IN_PAYLOAD = (("body", "manifest_body", "requirements", TREE_MANIFEST_KEY),)
_REUSED_IN_MANIFEST_BODY = (("requirements", TREE_MANIFEST_KEY),)
_REUSED_IN_REQUIREMENTS = ((TREE_MANIFEST_KEY,),)

ARCHITECTURE_SECTION_KEYS = (
    "scope_and_inputs",
    "solution_structure",
    "components_and_responsibilities",
    "interfaces_and_data_flows",
    "data_storage",
    "external_integrations",
    "security_authn_authz",
    "deployment_runtime_model",
    "failure_recovery",
    "observability",
    "migration_implications",
    "architecture_decisions",
)

IMPACT_VALUES = frozenset({"LOW", "MEDIUM", "HIGH"})
SEVERITY_VALUES = frozenset({"INFO", "WARNING", "BLOCKING"})
VERIFICATION_OUTCOMES = frozenset({"CONFIRMED", "REJECTED", "UNRESOLVED"})
SEVERITY_BEARING_OUTCOME = "CONFIRMED"
DERIVED_STATUS_VALUES = frozenset(
    {
        "REVIEW_STRUCTURALLY_INVALID",
        "REVIEW_BLOCKED_ON_WHAT",
        "REVIEW_BLOCKING",
        "REVIEW_NEEDS_WORK",
        "REVIEW_PASS",
    }
)
DECISION_VALUES = frozenset({"REWORK", "APPROVE"})

UX_APPLICABLE = "APPLICABLE"
UX_NOT_APPLICABLE = "NOT_APPLICABLE"

#: Collection names a reference may address, by source artifact type (6.2).
REFERENCE_COLLECTIONS: dict[str, frozenset[str]] = {
    PROCESS_RESULT: frozenset(
        {"assumptions", "risks", "open_architecture_questions", "product_questions"}
    ),
    REVIEW_RESULT: frozenset(
        {"claim_verifications", "new_findings", "material_unresolved_what"}
    ),
}
#: A disposition may never accept one of these (6.4, contract 9.3).
NON_WAIVABLE_COLLECTION = "material_unresolved_what"


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


class InvalidTsaArtifact(ValueError):
    """A TSA value violates the frozen wire format.

    `code` carries the specification's result code where one governs the
    refusal, so a caller can report it without re-deriving the classification.
    """

    def __init__(self, message: str, code: str = "ARTIFACT_MALFORMED") -> None:
        super().__init__(message)
        self.code = code


class EmptyTsaCarrier(ValueError):
    """The Document carries no payload at all: an empty shell, not malformed.

    Kept distinct from `InvalidTsaArtifact` because 4.4 treats the two
    differently. Deciding what to DO about a shell is recovery (I10), not this
    module's business.
    """


# ---------------------------------------------------------------------------
# Canonical JSON (5.1) and the reused-subtree boundary (5.1.1)
# ---------------------------------------------------------------------------


def _is_integer(value: object) -> bool:
    """True for a real integer. `bool` is a Python `int` and is not one."""
    return isinstance(value, int) and not isinstance(value, bool)


def _describe(path: tuple[str, ...]) -> str:
    return ".".join(path) if path else "<root>"


def _checked_integer(value: int, path: tuple[str, ...]) -> int:
    """Refuse an integer CPython cannot render, before `json.dumps` tries."""
    if value.bit_length() > MAX_INTEGER_BIT_LENGTH:
        raise InvalidTsaArtifact(
            f"{_describe(path)} is an integer too wide to serialize."
        )
    try:
        str(value)
    except ValueError as error:  # CPython's int -> str digit limit
        raise InvalidTsaArtifact(
            f"{_describe(path)} is an integer too wide to serialize."
        ) from error
    return value


def _checked_string(value: str, path: tuple[str, ...]) -> str:
    """Refuse a string that is not encodable UTF-8, such as a lone surrogate."""
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise InvalidTsaArtifact(
            f"{_describe(path)} holds a code point that is not encodable as "
            "UTF-8, such as an unpaired surrogate."
        ) from error
    return value


def _canonical_reused(value: object, path: tuple[str, ...]) -> object:
    """A reused subtree, unchanged: null allowed, no NFC, no key restriction.

    Only serializability is checked. Rewriting a reused value would destroy the
    producing mechanism's own fingerprint (5.1.1), so nothing here normalises.
    """
    if value is None or isinstance(value, bool):
        return value
    if _is_integer(value):
        return _checked_integer(value, path)
    if isinstance(value, str):
        return _checked_string(value, path)
    if isinstance(value, float):
        raise InvalidTsaArtifact(
            f"{_describe(path)} is a floating-point number, which never "
            "serializes deterministically."
        )
    if isinstance(value, list):
        return [_canonical_reused(item, (*path, "[]")) for item in value]
    if isinstance(value, dict):
        for key in value:
            if not isinstance(key, str):
                raise InvalidTsaArtifact(
                    f"{_describe(path)} has a non-string object key {key!r}."
                )
            _checked_string(key, path)
        return {
            key: _canonical_reused(item, (*path, key)) for key, item in value.items()
        }
    raise InvalidTsaArtifact(
        f"{_describe(path)} holds {type(value).__name__}, which is not JSON."
    )


def _canonical_owned(
    value: object, path: tuple[str, ...], reused_paths: frozenset[tuple[str, ...]]
) -> object:
    """A TSA-owned value under rules 2, 3 and 6 of 5.1."""
    if value is None:
        raise InvalidTsaArtifact(
            f"{_describe(path)} is null; an absent optional field is omitted, "
            "never null."
        )
    if isinstance(value, bool):
        return value
    if _is_integer(value):
        return _checked_integer(value, path)
    if isinstance(value, float):
        raise InvalidTsaArtifact(
            f"{_describe(path)} is a floating-point number, which is forbidden."
        )
    if isinstance(value, str):
        return unicodedata.normalize("NFC", _checked_string(value, path))
    if isinstance(value, list):
        return [_canonical_value(item, (*path, "[]"), reused_paths) for item in value]
    if isinstance(value, dict):
        canonical: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not KEY_PATTERN.fullmatch(key):
                raise InvalidTsaArtifact(
                    f"{_describe(path)} has key {key!r}, which is outside "
                    f"^{KEY_PATTERN.pattern}$."
                )
            canonical[key] = _canonical_value(item, (*path, key), reused_paths)
        return canonical
    raise InvalidTsaArtifact(
        f"{_describe(path)} holds {type(value).__name__}, which is not JSON."
    )


def _canonical_value(
    value: object, path: tuple[str, ...], reused_paths: frozenset[tuple[str, ...]]
) -> object:
    """Dispatch one value, entering the reused branch at a declared path.

    A list level does not consume a path element, so one declared path covers
    every element of an array (5.1.1, `requirements[*].tree_manifest`).
    """
    named = tuple(part for part in path if part != "[]")
    if named in reused_paths:
        return _canonical_reused(value, path)
    return _canonical_owned(value, path, reused_paths)


def _canonical_json(
    value: object, reused_paths: tuple[tuple[str, ...], ...] = ()
) -> str:
    """Canonical serialization of 5.1 with 5.1.1 applied at `reused_paths`.

    Private on purpose: `reused_paths` grants a semantic exemption from rules 2,
    3 and 6, and the frozen specification names exactly one place it applies.
    Callers reach this only through an artifact-aware entry point that derives
    the path itself, so no caller can exempt a value of its own choosing.
    """
    prepared = _canonical_value(value, (), frozenset(reused_paths))
    return json.dumps(
        prepared,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def canonical_json(value: object) -> str:
    """The canonical serialization of 5.1, TSA-owned rules only.

    No reused subtree applies here: a `null`, a non-conforming key or a
    decomposed string is refused wherever it appears. The one exemption the
    frozen specification grants is reached through `artifact_digest`,
    `manifest_digest` and `requirement_input_digest`, which know where that
    subtree lives and do not take it from a caller.
    """
    return _canonical_json(value)


def canonical_bytes(value: object) -> bytes:
    """UTF-8 of `canonical_json`: no BOM, no trailing newline (5.1 rule 1)."""
    return canonical_json(value).encode("utf-8")


# ---------------------------------------------------------------------------
# Digest families (5.2, 5.4, 13.7-2)
# ---------------------------------------------------------------------------


def _reused_paths_for(artifact_type: str) -> tuple[tuple[str, ...], ...]:
    """Where 5.1.1 applies inside one artifact payload, rooted at the payload.

    Only `tsa.input_manifest` has one. This is the single place the mapping is
    decided, so no caller supplies it.
    """
    return _REUSED_IN_PAYLOAD if artifact_type == INPUT_MANIFEST else ()


def _digest(prefix: str, value: object, reused: tuple[tuple[str, ...], ...]) -> str:
    return hashlib.sha256(
        (prefix + _canonical_json(value, reused)).encode("utf-8")
    ).hexdigest()


def artifact_digest(
    artifact_type: str, schema_version: int, payload: dict[str, object]
) -> str:
    """Domain-separated digest of one artifact payload (5.2).

    The reused-subtree rule is derived from `artifact_type`, never supplied.
    `artifact_digest` is the only excluded key, so a payload never hashes a
    field containing its own digest.
    """
    known = _require_known_artifact_type(artifact_type)
    body = {key: item for key, item in payload.items() if key != "artifact_digest"}
    prefix = f"{ARTIFACT_DIGEST_DOMAIN}\n{known}\n{schema_version}\n"
    return _digest(prefix, body, _reused_paths_for(known))


def sub_digest(tag: str, value: object) -> str:
    """The generic sub-digest of 5.4. Version is always 1 and is its own line.

    TSA-owned rules only; it grants no exemption.
    """
    return _digest(f"{ARTIFACT_DIGEST_DOMAIN}\n{tag}\n{SCHEMA_VERSION}\n", value, ())


def requirement_input_digest(requirements: list[object]) -> str:
    """Over the whole ordered `manifest_body.requirements` array (5.4)."""
    return _digest(
        f"{ARTIFACT_DIGEST_DOMAIN}\n{REQUIREMENT_INPUT_DIGEST_TAG}\n{SCHEMA_VERSION}\n",
        requirements,
        _REUSED_IN_REQUIREMENTS,
    )


def ux_evidence_digest(ux: dict[str, object]) -> str:
    """Over the whole `manifest_body.ux` object, either branch (5.4).

    The `ux` object holds no reused subtree.
    """
    return sub_digest(UX_EVIDENCE_DIGEST_TAG, ux)


def manifest_digest(manifest_body: dict[str, object]) -> str:
    """The dedicated formula of 5.4: one tag line, no separate version line.

    Deliberately not routed through `sub_digest`: the shapes differ, and the
    specification names this the only definition of the value.
    """
    return _digest(
        f"{MANIFEST_DIGEST_DOMAIN}\n", manifest_body, _REUSED_IN_MANIFEST_BODY
    )


def start_input_digest(projection: dict[str, object]) -> str:
    """Over the caller-input projection of 13.7-2.

    Neither an artifact digest nor a sub-digest: one tag line and nothing else,
    because it digests caller argv rather than a persisted artifact.
    """
    return _digest(f"{START_INPUT_DIGEST_DOMAIN}\n", projection, ())


def start_input_projection(
    *,
    cycle_id: str,
    project_entity_id: str,
    requirement_ids: list[str],
    ux: dict[str, object],
    accept_inputs: bool,
    accept_ux: bool,
) -> dict[str, object]:
    """Build and validate the projection of 13.7-2 from caller inputs.

    Requirement ids are upper-cased, de-duplicated and sorted, so argument order
    never changes the digest. No timestamp and no generated id may enter. This
    consumes caller argv, so the cycle id is normalised here rather than
    required to arrive canonical.
    """
    normalised = sorted({identifier.strip().upper() for identifier in requirement_ids})
    if not normalised:
        raise InvalidTsaArtifact(
            "The start input projection needs at least one Requirement id.",
            code="SELECTION_EMPTY",
        )
    return {
        "accept_inputs": _require_true(accept_inputs, ("accept_inputs",)),
        "accept_ux": _require_true(accept_ux, ("accept_ux",)),
        "cycle_id": canonical_cycle_id(cycle_id),
        "project_entity_id": _require_text(project_entity_id, ("project_entity_id",)),
        "requirement_ids": normalised,
        "ux": _validate_start_projection_ux(ux),
    }


def _validate_start_projection_ux(ux: object) -> dict[str, object]:
    path = ("ux",)
    body = _require_object(ux, path)
    kind = body.get("kind")
    if kind == UX_APPLICABLE:
        _closed_keys(
            body,
            required=("content_digest", "document_id", "kind", "scope_requirement_ids"),
            optional=(),
            path=path,
        )
        scope = _require_string_array(
            body["scope_requirement_ids"], (*path, "scope_requirement_ids"), min_items=1
        )
        return {
            "content_digest": _require_digest(
                body["content_digest"], (*path, "content_digest")
            ),
            "document_id": _require_text(body["document_id"], (*path, "document_id")),
            "kind": UX_APPLICABLE,
            "scope_requirement_ids": sorted(scope),
        }
    if kind == UX_NOT_APPLICABLE:
        _closed_keys(body, required=("kind", "reason"), optional=(), path=path)
        return {
            "kind": UX_NOT_APPLICABLE,
            "reason": _require_text(body["reason"], (*path, "reason")),
        }
    raise InvalidTsaArtifact(
        f"ux.kind must be {UX_APPLICABLE!r} or {UX_NOT_APPLICABLE!r}, not {kind!r}."
    )


# ---------------------------------------------------------------------------
# Cycle id (3.1)
# ---------------------------------------------------------------------------


def canonical_cycle_id(raw: object) -> str:
    """The canonical form of a CALLER-SUPPLIED cycle id: NFC, trimmed, lowered.

    For a value read back from a persisted artifact use
    `require_canonical_cycle_id`: persisted identity must already be canonical
    and is never rewritten on read.
    """
    if not isinstance(raw, str):
        raise InvalidTsaArtifact(
            f"A cycle id must be a string, not {type(raw).__name__}.",
            code="INVALID_CYCLE_ID",
        )
    candidate = unicodedata.normalize("NFC", raw).strip().lower()
    if not CYCLE_ID_PATTERN.fullmatch(candidate):
        raise InvalidTsaArtifact(
            f"Cycle id {raw!r} is outside ^{CYCLE_ID_PATTERN.pattern}$.",
            code="INVALID_CYCLE_ID",
        )
    return candidate


def require_canonical_cycle_id(raw: object, path: tuple[str, ...]) -> str:
    """A persisted cycle id, refused unless it is *already* canonical.

    Normalising on read would silently accept two different stored strings as
    one identity, and the value handed back would no longer be the value
    stored. The stored value is returned unchanged, or the artifact is refused.
    """
    canonical = canonical_cycle_id(raw)
    if raw != canonical:
        raise InvalidTsaArtifact(
            f"{_describe(path)} is stored as {raw!r}, which is not its canonical "
            f"form {canonical!r}; persisted identity is never normalised on read.",
            code="INVALID_CYCLE_ID",
        )
    return canonical


# ---------------------------------------------------------------------------
# Small closed-schema primitives
# ---------------------------------------------------------------------------


def _require_object(value: object, path: tuple[str, ...]) -> dict[str, object]:
    if not isinstance(value, dict):
        raise InvalidTsaArtifact(
            f"{_describe(path)} must be an object, not {type(value).__name__}."
        )
    return value


def _closed_keys(
    value: dict[str, object],
    *,
    required: tuple[str, ...],
    optional: tuple[str, ...],
    path: tuple[str, ...],
) -> None:
    """Reject a missing required key and any key outside the closed set (4.4)."""
    missing = sorted(set(required) - set(value))
    if missing:
        raise InvalidTsaArtifact(f"{_describe(path)} is missing {missing}.")
    unknown = sorted(set(value) - set(required) - set(optional))
    if unknown:
        raise InvalidTsaArtifact(f"{_describe(path)} carries unknown keys {unknown}.")


def _require_text(value: object, path: tuple[str, ...]) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidTsaArtifact(f"{_describe(path)} must be a non-empty string.")
    return value


def _require_digest(value: object, path: tuple[str, ...]) -> str:
    if not isinstance(value, str) or not DIGEST_PATTERN.fullmatch(value):
        raise InvalidTsaArtifact(
            f"{_describe(path)} must be exactly {DIGEST_LENGTH} lowercase hex "
            "characters."
        )
    return value


def _require_timestamp(value: object, path: tuple[str, ...]) -> str:
    if not isinstance(value, str) or not TIMESTAMP_PATTERN.fullmatch(value):
        raise InvalidTsaArtifact(
            f"{_describe(path)} must be RFC-3339 UTC with a Z suffix and "
            "second precision."
        )
    try:
        # The pattern above already pins the shape; this rejects an impossible
        # date such as 2026-02-30. `fromisoformat` reads the `Z` suffix as UTC.
        datetime.fromisoformat(value)
    except ValueError as error:
        raise InvalidTsaArtifact(f"{_describe(path)} is not a real instant.") from error
    return value


def _require_enum(value: object, allowed: frozenset[str], path: tuple[str, ...]) -> str:
    """Type first, then membership: `[] in frozenset` would raise `TypeError`."""
    if not isinstance(value, str):
        raise InvalidTsaArtifact(
            f"{_describe(path)} must be a string naming one of {sorted(allowed)}, "
            f"not {type(value).__name__}."
        )
    if value not in allowed:
        raise InvalidTsaArtifact(
            f"{_describe(path)} must be one of {sorted(allowed)}, not {value!r}."
        )
    return value


def _require_bool(value: object, path: tuple[str, ...]) -> bool:
    if not isinstance(value, bool):
        raise InvalidTsaArtifact(f"{_describe(path)} must be a boolean.")
    return value


def _require_true(value: object, path: tuple[str, ...]) -> bool:
    if _require_bool(value, path) is not True:
        raise InvalidTsaArtifact(f"{_describe(path)} must be true.")
    return True


def _require_integer(
    value: object, path: tuple[str, ...], *, minimum: int | None = None
) -> int:
    if not _is_integer(value):
        raise InvalidTsaArtifact(
            f"{_describe(path)} must be an integer, not {type(value).__name__}."
        )
    _checked_integer(value, path)
    if minimum is not None and value < minimum:
        raise InvalidTsaArtifact(f"{_describe(path)} must be at least {minimum}.")
    return int(value)


def _require_array(value: object, path: tuple[str, ...]) -> list[object]:
    if not isinstance(value, list):
        raise InvalidTsaArtifact(
            f"{_describe(path)} must be an array, not {type(value).__name__}."
        )
    return value


def _require_string_array(
    value: object, path: tuple[str, ...], *, min_items: int = 0
) -> list[str]:
    items = _require_array(value, path)
    if len(items) < min_items:
        raise InvalidTsaArtifact(f"{_describe(path)} needs at least {min_items} items.")
    return [
        _require_text(item, (*path, f"[{index}]")) for index, item in enumerate(items)
    ]


def _require_iteration(value: object, path: tuple[str, ...]) -> int:
    number = _require_integer(value, path, minimum=ITERATION_MIN)
    if number > ITERATION_MAX:
        raise InvalidTsaArtifact(
            f"{_describe(path)} is {number}; the permitted range is "
            f"{ITERATION_MIN}..{ITERATION_MAX}.",
            code="ITERATION_LIMIT",
        )
    return number


def _require_equal(
    actual: object, expected: object, path: tuple[str, ...], expected_from: str
) -> None:
    """One identity spelled in two places must agree exactly."""
    if actual != expected:
        raise InvalidTsaArtifact(
            f"{_describe(path)} is {actual!r} but {expected_from} is {expected!r}; "
            "a duplicated identity must agree."
        )


def _require_known_artifact_type(value: object) -> str:
    """Type first, then membership, so a list never raises `TypeError`."""
    if not isinstance(value, str):
        raise InvalidTsaArtifact(
            f"artifact_type must be a string, not {type(value).__name__}."
        )
    if value not in ARTIFACT_TYPES:
        raise InvalidTsaArtifact(
            f"artifact_type must be one of {sorted(ARTIFACT_TYPES)}, not {value!r}."
        )
    return value


# ---------------------------------------------------------------------------
# Disposition reference grammar (6.1, 6.2)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ArtifactReference:
    """One parsed `<digest>#<collection>/<index>` reference."""

    digest: str
    collection: str
    index: int

    def __str__(self) -> str:
        return f"{self.digest}#{self.collection}/{self.index}"


def parse_reference(raw: object, path: tuple[str, ...] = ("ref",)) -> ArtifactReference:
    """Parse the grammar of 6.1. Structure only.

    Resolving the digest to a persisted artifact and the index to an array
    position is I11; this refuses only what the grammar itself forbids.
    """
    if not isinstance(raw, str):
        raise InvalidTsaArtifact(
            f"{_describe(path)} must be a string.",
            code="DISPOSITION_UNKNOWN_REFERENCE",
        )
    match = REFERENCE_PATTERN.fullmatch(raw)
    if match is None:
        raise InvalidTsaArtifact(
            f"{_describe(path)} {raw!r} is outside the reference grammar of 6.1.",
            code="DISPOSITION_UNKNOWN_REFERENCE",
        )
    collection = match.group("collection")
    known: set[str] = set().union(*REFERENCE_COLLECTIONS.values())
    if collection not in known:
        raise InvalidTsaArtifact(
            f"{_describe(path)} names collection {collection!r}, which no TSA "
            "artifact carries.",
            code="DISPOSITION_UNKNOWN_REFERENCE",
        )
    return ArtifactReference(
        digest=match.group("digest"),
        collection=collection,
        index=int(match.group("index")),
    )


def reference_allows_collection(artifact_type: str, collection: str) -> bool:
    """Whether 6.2 permits `collection` against that source artifact type."""
    return collection in REFERENCE_COLLECTIONS.get(artifact_type, frozenset())


# ---------------------------------------------------------------------------
# Shared body fragments
# ---------------------------------------------------------------------------


def _validate_traceability_rows(value: object, path: tuple[str, ...]) -> None:
    """Rows of 8.2. Anchor grammar and coverage are the renderer's gate (I06)."""
    for index, raw in enumerate(_require_array(value, path)):
        row_path = (*path, f"[{index}]")
        row = _require_object(raw, row_path)
        _closed_keys(
            row,
            required=(
                "anchors",
                "constraints",
                "gaps",
                "how_satisfied",
                "requirement_id",
            ),
            optional=(),
            path=row_path,
        )
        _require_text(row["requirement_id"], (*row_path, "requirement_id"))
        _require_string_array(row["anchors"], (*row_path, "anchors"), min_items=1)
        _require_text(row["how_satisfied"], (*row_path, "how_satisfied"))
        _require_string_array(row["constraints"], (*row_path, "constraints"))
        _require_string_array(row["gaps"], (*row_path, "gaps"))


def _validate_risks(value: object, path: tuple[str, ...]) -> None:
    for index, raw in enumerate(_require_array(value, path)):
        item_path = (*path, f"[{index}]")
        item = _require_object(raw, item_path)
        _closed_keys(item, required=("detail", "impact"), optional=(), path=item_path)
        _require_text(item["detail"], (*item_path, "detail"))
        _require_enum(item["impact"], IMPACT_VALUES, (*item_path, "impact"))


def _validate_product_questions(value: object, path: tuple[str, ...]) -> None:
    for index, raw in enumerate(_require_array(value, path)):
        item_path = (*path, f"[{index}]")
        item = _require_object(raw, item_path)
        _closed_keys(
            item,
            required=("detail", "material", "requirement_id"),
            optional=(),
            path=item_path,
        )
        _require_text(item["detail"], (*item_path, "detail"))
        _require_text(item["requirement_id"], (*item_path, "requirement_id"))
        _require_bool(item["material"], (*item_path, "material"))


def _validate_runtime(value: object, path: tuple[str, ...], role: str) -> None:
    body = _require_object(value, path)
    _closed_keys(body, required=("role",), optional=("model",), path=path)
    if body["role"] != role:
        raise InvalidTsaArtifact(
            f"{_describe(path)}.role must be {role!r}, not {body['role']!r}."
        )
    if "model" in body:
        _require_text(body["model"], (*path, "model"))


def _validate_document_digest_pair(
    value: object, path: tuple[str, ...], *, with_iteration: bool
) -> None:
    body = _require_object(value, path)
    required = ("document_id", "payload_digest")
    if with_iteration:
        required = (*required, "iteration")
    _closed_keys(body, required=required, optional=(), path=path)
    _require_text(body["document_id"], (*path, "document_id"))
    _require_digest(body["payload_digest"], (*path, "payload_digest"))
    if with_iteration:
        _require_iteration(body["iteration"], (*path, "iteration"))


# ---------------------------------------------------------------------------
# Model response schemas (9.1, 10.1)
# ---------------------------------------------------------------------------


def validate_architect_response(value: object, path: tuple[str, ...]) -> None:
    """The closed Architect payload of 9.1. No `findings` array exists (6.2)."""
    body = _require_object(value, path)
    _closed_keys(
        body,
        required=(
            "architecture",
            "assumptions",
            "open_architecture_questions",
            "product_questions",
            "risks",
            "traceability",
        ),
        optional=(),
        path=path,
    )
    _validate_sections(body["architecture"], (*path, "architecture"))
    _validate_traceability_rows(body["traceability"], (*path, "traceability"))
    _require_string_array(body["assumptions"], (*path, "assumptions"))
    _validate_risks(body["risks"], (*path, "risks"))
    _require_string_array(
        body["open_architecture_questions"], (*path, "open_architecture_questions")
    )
    _validate_product_questions(body["product_questions"], (*path, "product_questions"))


def _validate_sections(value: object, path: tuple[str, ...]) -> None:
    """All twelve Architect section keys, required, prose only (9.1)."""
    body = _require_object(value, path)
    _closed_keys(body, required=ARCHITECTURE_SECTION_KEYS, optional=(), path=path)
    for key in ARCHITECTURE_SECTION_KEYS:
        _require_text(body[key], (*path, key))


def validate_reviewer_response(value: object, path: tuple[str, ...]) -> None:
    """The closed Reviewer payload of 10.1. There is no verdict field.

    Deriving the overall status from this payload is I08; this validates shape,
    including that `severity` accompanies exactly the CONFIRMED verifications.
    """
    body = _require_object(value, path)
    _closed_keys(
        body,
        required=(
            "assessment",
            "claim_verifications",
            "material_unresolved_what",
            "new_findings",
            "traceability_verification",
        ),
        optional=(),
        path=path,
    )
    _validate_claim_verifications(
        body["claim_verifications"], (*path, "claim_verifications")
    )
    _validate_outcome_with_reason(
        body["traceability_verification"], (*path, "traceability_verification")
    )
    _validate_new_findings(body["new_findings"], (*path, "new_findings"))
    _validate_material_unresolved(
        body["material_unresolved_what"], (*path, "material_unresolved_what")
    )
    _validate_assessment(body["assessment"], (*path, "assessment"))


def _validate_claim_verifications(value: object, path: tuple[str, ...]) -> None:
    for index, raw in enumerate(_require_array(value, path)):
        item_path = (*path, f"[{index}]")
        item = _require_object(raw, item_path)
        _closed_keys(
            item,
            required=("claim_ref", "outcome", "reason"),
            optional=("severity",),
            path=item_path,
        )
        parse_reference(item["claim_ref"], (*item_path, "claim_ref"))
        outcome = _require_enum(
            item["outcome"], VERIFICATION_OUTCOMES, (*item_path, "outcome")
        )
        _require_text(item["reason"], (*item_path, "reason"))
        _validate_conditional_severity(item, outcome, item_path)


def _validate_conditional_severity(
    item: dict[str, object], outcome: str, path: tuple[str, ...]
) -> None:
    """Severity is present only on CONFIRMED: the other outcomes assert nothing."""
    has_severity = "severity" in item
    if outcome == SEVERITY_BEARING_OUTCOME:
        if not has_severity:
            raise InvalidTsaArtifact(
                f"{_describe(path)} is {SEVERITY_BEARING_OUTCOME} and must carry "
                "a severity."
            )
        _require_enum(item["severity"], SEVERITY_VALUES, (*path, "severity"))
    elif has_severity:
        raise InvalidTsaArtifact(
            f"{_describe(path)} is {outcome} and must not carry a severity."
        )


def _validate_outcome_with_reason(value: object, path: tuple[str, ...]) -> None:
    body = _require_object(value, path)
    _closed_keys(body, required=("outcome", "reason"), optional=(), path=path)
    _require_enum(body["outcome"], VERIFICATION_OUTCOMES, (*path, "outcome"))
    _require_text(body["reason"], (*path, "reason"))


def _validate_new_findings(value: object, path: tuple[str, ...]) -> None:
    for index, raw in enumerate(_require_array(value, path)):
        item_path = (*path, f"[{index}]")
        item = _require_object(raw, item_path)
        _closed_keys(
            item,
            required=("detail", "kind", "requirement_id", "severity"),
            optional=(),
            path=item_path,
        )
        _require_text(item["kind"], (*item_path, "kind"))
        _require_text(item["detail"], (*item_path, "detail"))
        _require_text(item["requirement_id"], (*item_path, "requirement_id"))
        _require_enum(item["severity"], SEVERITY_VALUES, (*item_path, "severity"))


def _validate_material_unresolved(value: object, path: tuple[str, ...]) -> None:
    for index, raw in enumerate(_require_array(value, path)):
        item_path = (*path, f"[{index}]")
        item = _require_object(raw, item_path)
        _closed_keys(
            item, required=("detail", "requirement_id"), optional=(), path=item_path
        )
        _require_text(item["detail"], (*item_path, "detail"))
        _require_text(item["requirement_id"], (*item_path, "requirement_id"))


ASSESSMENT_KEYS = (
    "completeness",
    "implementability",
    "internal_consistency",
    "source_fidelity",
    "traceability",
)


def _validate_assessment(value: object, path: tuple[str, ...]) -> None:
    body = _require_object(value, path)
    _closed_keys(body, required=ASSESSMENT_KEYS, optional=(), path=path)
    for key in ASSESSMENT_KEYS:
        _require_text(body[key], (*path, key))


# ---------------------------------------------------------------------------
# Envelope identity, duplicated into some bodies (4.2, 4.6.1, 7.2)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ArtifactIdentity:
    """The envelope identity a body must agree with wherever it repeats it."""

    workspace_identity: str
    project_entity_id: str
    project_code: str
    cycle_id: str


# ---------------------------------------------------------------------------
# Input Manifest body (7.2, 7.3, 7.4)
# ---------------------------------------------------------------------------


def validate_manifest_body(
    value: object,
    path: tuple[str, ...] = ("manifest_body",),
    identity: ArtifactIdentity | None = None,
) -> None:
    """The immutable input set of 7.2. Carries no acceptance and no digest.

    When `identity` is supplied, the four identity fields 7.2 repeats from the
    envelope must equal it exactly.
    """
    body = _require_object(value, path)
    _closed_keys(
        body,
        required=(
            "created_at",
            "cycle_id",
            "project_code",
            "project_entity_id",
            "requirements",
            "ux",
            "workspace_identity",
        ),
        optional=(),
        path=path,
    )
    _require_text(body["workspace_identity"], (*path, "workspace_identity"))
    _require_text(body["project_code"], (*path, "project_code"))
    _require_text(body["project_entity_id"], (*path, "project_entity_id"))
    require_canonical_cycle_id(body["cycle_id"], (*path, "cycle_id"))
    _require_timestamp(body["created_at"], (*path, "created_at"))
    if identity is not None:
        _require_manifest_identity(body, path, identity)
    requirement_ids = _validate_manifest_requirements(
        body["requirements"], (*path, "requirements")
    )
    _validate_ux(body["ux"], (*path, "ux"), requirement_ids)


def _require_manifest_identity(
    body: dict[str, object], path: tuple[str, ...], identity: ArtifactIdentity
) -> None:
    for key, expected in (
        ("workspace_identity", identity.workspace_identity),
        ("project_entity_id", identity.project_entity_id),
        ("project_code", identity.project_code),
        ("cycle_id", identity.cycle_id),
    ):
        _require_equal(body[key], expected, (*path, key), f"the envelope {key}")


def _validate_manifest_requirements(value: object, path: tuple[str, ...]) -> list[str]:
    """Ordered ascending by `requirement_id`, non-empty, no duplicate identity."""
    items = _require_array(value, path)
    if not items:
        raise InvalidTsaArtifact(
            f"{_describe(path)} must select at least one Requirement.",
            code="SELECTION_EMPTY",
        )
    requirement_ids: list[str] = []
    entity_ids: list[str] = []
    for index, raw in enumerate(items):
        item_path = (*path, f"[{index}]")
        item = _require_object(raw, item_path)
        _closed_keys(
            item,
            required=(
                "entity_id",
                "process_result",
                "requirement_id",
                "review_result",
                "tree_fingerprint",
                "tree_manifest",
            ),
            optional=(),
            path=item_path,
        )
        requirement_id = _require_text(
            item["requirement_id"], (*item_path, "requirement_id")
        )
        requirement_ids.append(requirement_id)
        entity_ids.append(_require_text(item["entity_id"], (*item_path, "entity_id")))
        tree_fingerprint = _require_digest(
            item["tree_fingerprint"], (*item_path, "tree_fingerprint")
        )
        _validate_requirement_tree(
            item["tree_manifest"],
            (*item_path, TREE_MANIFEST_KEY),
            requirement_id=requirement_id,
            tree_fingerprint=tree_fingerprint,
        )
        _validate_document_digest_pair(
            item["process_result"], (*item_path, "process_result"), with_iteration=True
        )
        _validate_document_digest_pair(
            item["review_result"], (*item_path, "review_result"), with_iteration=False
        )
    _refuse_duplicates(requirement_ids, path, "requirement_id")
    _refuse_duplicates(entity_ids, path, "entity_id")
    if requirement_ids != sorted(requirement_ids):
        raise InvalidTsaArtifact(
            f"{_describe(path)} must be ordered by requirement_id ascending, so "
            "argument order never changes the digest."
        )
    return requirement_ids


def _refuse_duplicates(values: list[str], path: tuple[str, ...], field: str) -> None:
    duplicates = sorted({item for item in values if values.count(item) > 1})
    if duplicates:
        raise InvalidTsaArtifact(
            f"{_describe(path)} repeats {field} {duplicates}.",
            code="SELECTION_DUPLICATE",
        )


def validate_reused_tree_manifest(
    value: object, path: tuple[str, ...] = (TREE_MANIFEST_KEY,)
) -> TreeManifest:
    """Validate the one reused subtree through its own producing mechanism.

    `TreeManifest.from_payload` is the authority (REUSE). A manifest it rejects
    makes the whole TSA artifact malformed; nothing here re-implements or
    re-versions manifest v2.
    """
    try:
        return TreeManifest.from_payload(value)
    except InvalidTreeManifest as error:
        raise InvalidTsaArtifact(
            f"{_describe(path)} is not a valid normative tree manifest: {error}"
        ) from error
    except UnicodeEncodeError as error:
        # The manifest fingerprints itself over UTF-8 bytes, so an unpaired
        # surrogate fails inside the producing mechanism rather than in ours.
        raise InvalidTsaArtifact(
            f"{_describe(path)} holds a code point that is not encodable as "
            "UTF-8, such as an unpaired surrogate."
        ) from error


def _validate_requirement_tree(
    value: object,
    path: tuple[str, ...],
    *,
    requirement_id: str,
    tree_fingerprint: str,
) -> TreeManifest:
    """The embedded manifest, then the bindings the outer Requirement row asserts.

    `from_payload` also accepts legacy v1 so history stays readable, but a TSA
    admission artifact must carry the current algorithm: `tree_fingerprint` and
    the Requirement-side digests beside it are v2 values (7.2), and a v1 entry
    fingerprint is not comparable with them.
    """
    manifest = validate_reused_tree_manifest(value, path)
    if manifest.version != NORMATIVE_TREE_VERSION:
        raise InvalidTsaArtifact(
            f"{_describe(path)} is normative tree manifest v{manifest.version}; a "
            f"TSA admission artifact requires v{NORMATIVE_TREE_VERSION}."
        )
    _require_equal(
        manifest.requirement_id,
        requirement_id,
        (*path, "requirement_id"),
        "the Requirement row",
    )
    # `from_payload` guarantees exactly one Root entry and that it is the
    # declared Root, so this lookup cannot fail on a parsed manifest.
    _require_equal(
        manifest.root_entry.content_fingerprint,
        tree_fingerprint,
        (*path, "root content_fingerprint"),
        "the row's tree_fingerprint",
    )
    return manifest


def _validate_ux(
    value: object, path: tuple[str, ...], requirement_ids: list[str]
) -> None:
    """The discriminated union of 7.3, with the branch fields kept apart."""
    body = _require_object(value, path)
    kind = body.get("kind")
    if kind == UX_APPLICABLE:
        _closed_keys(
            body,
            required=(
                "approval",
                "content_digest",
                "document_id",
                "kind",
                "scope_requirement_ids",
            ),
            optional=(),
            path=path,
        )
        _require_text(body["document_id"], (*path, "document_id"))
        _require_digest(body["content_digest"], (*path, "content_digest"))
        scope = _require_string_array(
            body["scope_requirement_ids"], (*path, "scope_requirement_ids"), min_items=1
        )
        foreign = sorted(set(scope) - set(requirement_ids))
        if foreign:
            raise InvalidTsaArtifact(
                f"{_describe(path)}.scope_requirement_ids names {foreign}, which "
                "is outside the manifest selection.",
                code="UX_SCOPE_FOREIGN",
            )
        _validate_ux_acceptance(body["approval"], (*path, "approval"))
        return
    if kind == UX_NOT_APPLICABLE:
        _closed_keys(
            body,
            required=("decision", "kind", "reason", "requirement_input_digest"),
            optional=(),
            path=path,
        )
        _require_text(body["reason"], (*path, "reason"))
        _require_digest(
            body["requirement_input_digest"], (*path, "requirement_input_digest")
        )
        _validate_ux_acceptance(body["decision"], (*path, "decision"))
        return
    raise InvalidTsaArtifact(
        f"{_describe(path)}.kind must be {UX_APPLICABLE!r} or "
        f"{UX_NOT_APPLICABLE!r}, not {kind!r}."
    )


def _validate_ux_acceptance(value: object, path: tuple[str, ...]) -> None:
    body = _require_object(value, path)
    _closed_keys(body, required=("accepted", "recorded_at"), optional=(), path=path)
    _require_true(body["accepted"], (*path, "accepted"))
    _require_timestamp(body["recorded_at"], (*path, "recorded_at"))


def _validate_acceptance(
    value: object, path: tuple[str, ...], expected_digest: str
) -> None:
    """7.4. `accepted` must be true; refusal is the absence of the artifact."""
    body = _require_object(value, path)
    _closed_keys(
        body,
        required=("accepted", "manifest_digest", "recorded_at"),
        optional=(),
        path=path,
    )
    _require_true(body["accepted"], (*path, "accepted"))
    _require_timestamp(body["recorded_at"], (*path, "recorded_at"))
    stored = _require_digest(body["manifest_digest"], (*path, "manifest_digest"))
    if stored != expected_digest:
        raise InvalidTsaArtifact(
            f"{_describe(path)}.manifest_digest does not equal the sibling field, "
            "so the manifest counts as not accepted.",
            code="MANIFEST_ACCEPTANCE_MISMATCH",
        )


# ---------------------------------------------------------------------------
# The five closed body schemas (4.6)
# ---------------------------------------------------------------------------

#: Bootstrap metadata: a newly created Architecture Document carries these and
#: nothing else (4.6.1).
ARCHITECTURE_BOOTSTRAP_KEYS = ("created_at", "cycle_id")

#: The applied-output group of 4.6.1. "Every other key appears when an
#: iteration's output is applied", so these appear together or not at all; an
#: arbitrary partial subset is neither of the two coherent forms.
ARCHITECTURE_APPLIED_KEYS = (
    "assumptions",
    "content_fingerprint",
    "current_iteration",
    "manifest_digest",
    "open_architecture_questions",
    "product_questions",
    "risks",
    "traceability",
)


def _validate_architecture_body(
    value: object, path: tuple[str, ...], identity: ArtifactIdentity
) -> None:
    body = _require_object(value, path)
    _closed_keys(
        body,
        required=ARCHITECTURE_BOOTSTRAP_KEYS,
        optional=ARCHITECTURE_APPLIED_KEYS,
        path=path,
    )
    require_canonical_cycle_id(body["cycle_id"], (*path, "cycle_id"))
    _require_equal(
        body["cycle_id"],
        identity.cycle_id,
        (*path, "cycle_id"),
        "the envelope cycle_id",
    )
    _require_timestamp(body["created_at"], (*path, "created_at"))
    _validate_architecture_applied_group(body, path)


def _validate_architecture_applied_group(
    body: dict[str, object], path: tuple[str, ...]
) -> None:
    """Pre-apply or post-apply, never a partial subset of the applied group."""
    present = [key for key in ARCHITECTURE_APPLIED_KEYS if key in body]
    if not present:
        return
    if len(present) != len(ARCHITECTURE_APPLIED_KEYS):
        missing = sorted(set(ARCHITECTURE_APPLIED_KEYS) - set(present))
        raise InvalidTsaArtifact(
            f"{_describe(path)} holds applied output but omits {missing}; the "
            "applied-output group is absent together or present together."
        )
    _require_digest(body["manifest_digest"], (*path, "manifest_digest"))
    _require_digest(body["content_fingerprint"], (*path, "content_fingerprint"))
    _require_iteration(body["current_iteration"], (*path, "current_iteration"))
    _validate_traceability_rows(body["traceability"], (*path, "traceability"))
    _require_string_array(body["assumptions"], (*path, "assumptions"))
    _validate_risks(body["risks"], (*path, "risks"))
    _require_string_array(
        body["open_architecture_questions"], (*path, "open_architecture_questions")
    )
    _validate_product_questions(body["product_questions"], (*path, "product_questions"))


def _validate_input_manifest_body(
    value: object, path: tuple[str, ...], identity: ArtifactIdentity
) -> None:
    body = _require_object(value, path)
    _closed_keys(
        body,
        required=("acceptance", "manifest_body", "manifest_digest"),
        optional=(),
        path=path,
    )
    validate_manifest_body(body["manifest_body"], (*path, "manifest_body"), identity)
    stored = _require_digest(body["manifest_digest"], (*path, "manifest_digest"))
    recomputed = manifest_digest(body["manifest_body"])
    if stored != recomputed:
        raise InvalidTsaArtifact(
            f"{_describe(path)}.manifest_digest does not match the manifest body "
            "it claims to cover."
        )
    _validate_acceptance(body["acceptance"], (*path, "acceptance"), recomputed)
    _validate_ux_digest_binding(body["manifest_body"], (*path, "manifest_body"))


def _validate_ux_digest_binding(manifest_body: object, path: tuple[str, ...]) -> None:
    """A NOT_APPLICABLE branch stores the requirement-input digest; recompute it.

    Recomputation, never field-to-field comparison: a tampered body carrying a
    matching tampered digest would otherwise pass (5.4).
    """
    body = _require_object(manifest_body, path)
    ux = _require_object(body["ux"], (*path, "ux"))
    if ux.get("kind") != UX_NOT_APPLICABLE:
        return
    recomputed = requirement_input_digest(_require_array(body["requirements"], path))
    if ux["requirement_input_digest"] != recomputed:
        raise InvalidTsaArtifact(
            f"{_describe(path)}.ux.requirement_input_digest does not cover the "
            "manifest's own requirements array."
        )


def _validate_process_result_body(
    value: object, path: tuple[str, ...], identity: ArtifactIdentity
) -> None:
    del identity  # 4.6.3 repeats no envelope identity field
    body = _require_object(value, path)
    _closed_keys(
        body,
        required=(
            "architect_response",
            "architecture_document_id",
            "created_at",
            "input_fingerprint",
            "intended_output",
            "manifest_digest",
            "runtime",
        ),
        optional=(),
        path=path,
    )
    _require_digest(body["manifest_digest"], (*path, "manifest_digest"))
    _require_text(body["architecture_document_id"], (*path, "architecture_document_id"))
    _require_digest(body["input_fingerprint"], (*path, "input_fingerprint"))
    validate_intended_output(body["intended_output"], (*path, "intended_output"))
    validate_architect_response(
        body["architect_response"], (*path, "architect_response")
    )
    _validate_runtime(body["runtime"], (*path, "runtime"), ARCHITECT_ROLE)
    _require_timestamp(body["created_at"], (*path, "created_at"))


def validate_intended_output(
    value: object, path: tuple[str, ...] = ("intended_output",)
) -> None:
    """The complete renderer input of 4.6.3.1: all six keys required.

    Running the renderer over it is I06. This closes the shape so the renderer
    never has to default or invent prose.
    """
    body = _require_object(value, path)
    _closed_keys(
        body,
        required=(
            "assumptions",
            "open_architecture_questions",
            "product_questions",
            "risks",
            "sections",
            "traceability",
        ),
        optional=(),
        path=path,
    )
    _validate_sections(body["sections"], (*path, "sections"))
    _validate_traceability_rows(body["traceability"], (*path, "traceability"))
    _require_string_array(body["assumptions"], (*path, "assumptions"))
    _validate_risks(body["risks"], (*path, "risks"))
    _require_string_array(
        body["open_architecture_questions"], (*path, "open_architecture_questions")
    )
    _validate_product_questions(body["product_questions"], (*path, "product_questions"))


def _validate_review_result_body(
    value: object, path: tuple[str, ...], identity: ArtifactIdentity
) -> None:
    del identity  # 4.6.4 repeats no envelope identity field
    body = _require_object(value, path)
    _closed_keys(
        body,
        required=(
            "architecture_document_id",
            "architecture_fingerprint",
            "created_at",
            "derived_status",
            "manifest_digest",
            "process_result_digest",
            "process_result_document_id",
            "reviewer_response",
            "runtime",
        ),
        optional=(),
        path=path,
    )
    _require_digest(body["manifest_digest"], (*path, "manifest_digest"))
    _require_text(
        body["process_result_document_id"], (*path, "process_result_document_id")
    )
    _require_digest(body["process_result_digest"], (*path, "process_result_digest"))
    _require_text(body["architecture_document_id"], (*path, "architecture_document_id"))
    _require_digest(
        body["architecture_fingerprint"], (*path, "architecture_fingerprint")
    )
    validate_reviewer_response(body["reviewer_response"], (*path, "reviewer_response"))
    _require_enum(
        body["derived_status"], DERIVED_STATUS_VALUES, (*path, "derived_status")
    )
    _validate_runtime(body["runtime"], (*path, "runtime"), REVIEWER_ROLE)
    _require_timestamp(body["created_at"], (*path, "created_at"))


def _validate_human_decision_body(
    value: object, path: tuple[str, ...], identity: ArtifactIdentity
) -> None:
    del identity  # 4.6.5 repeats no envelope identity field
    body = _require_object(value, path)
    _closed_keys(
        body,
        required=(
            "accepted_dispositions",
            "architecture_document_id",
            "architecture_fingerprint",
            "decision",
            "manifest_digest",
            "process_result",
            "recorded_at",
            "review_result",
            "target",
            "ux_evidence_digest",
        ),
        optional=("reason",),
        path=path,
    )
    _require_enum(body["decision"], DECISION_VALUES, (*path, "decision"))
    _validate_decision_target(body["target"], (*path, "target"))
    _require_text(body["architecture_document_id"], (*path, "architecture_document_id"))
    _require_digest(
        body["architecture_fingerprint"], (*path, "architecture_fingerprint")
    )
    _require_digest(body["manifest_digest"], (*path, "manifest_digest"))
    _require_digest(body["ux_evidence_digest"], (*path, "ux_evidence_digest"))
    _validate_document_digest_pair(
        body["process_result"], (*path, "process_result"), with_iteration=False
    )
    _validate_document_digest_pair(
        body["review_result"], (*path, "review_result"), with_iteration=False
    )
    _validate_dispositions(
        body["accepted_dispositions"], (*path, "accepted_dispositions")
    )
    if "reason" in body:
        _require_text(body["reason"], (*path, "reason"))
    _require_timestamp(body["recorded_at"], (*path, "recorded_at"))
    _require_decision_review_agreement(body, path)


def _require_decision_review_agreement(
    body: dict[str, object], path: tuple[str, ...]
) -> None:
    """`target` and `review_result` name one Review Result, so they must agree.

    4.6.5 records the Review Result twice — once as the decision target, once as
    the bound artifact. Two spellings of one identity is exactly where a
    mismatch hides, so it is checked inside the artifact and not only across
    artifacts.
    """
    target = _require_object(body["target"], (*path, "target"))
    review = _require_object(body["review_result"], (*path, "review_result"))
    _require_equal(
        target["review_result_document_id"],
        review["document_id"],
        (*path, "target", "review_result_document_id"),
        "review_result.document_id",
    )
    _require_equal(
        target["review_result_digest"],
        review["payload_digest"],
        (*path, "target", "review_result_digest"),
        "review_result.payload_digest",
    )


def _validate_decision_target(value: object, path: tuple[str, ...]) -> None:
    body = _require_object(value, path)
    _closed_keys(
        body,
        required=("iteration", "review_result_digest", "review_result_document_id"),
        optional=(),
        path=path,
    )
    _require_iteration(body["iteration"], (*path, "iteration"))
    _require_text(
        body["review_result_document_id"], (*path, "review_result_document_id")
    )
    _require_digest(body["review_result_digest"], (*path, "review_result_digest"))


def _validate_dispositions(value: object, path: tuple[str, ...]) -> None:
    """Grammar, duplicates and waivability. Resolution against artifacts is I11."""
    seen: list[str] = []
    for index, raw in enumerate(_require_array(value, path)):
        item_path = (*path, f"[{index}]")
        item = _require_object(raw, item_path)
        _closed_keys(item, required=("reason", "ref"), optional=(), path=item_path)
        reference = parse_reference(item["ref"], (*item_path, "ref"))
        _require_text(item["reason"], (*item_path, "reason"))
        if reference.collection == NON_WAIVABLE_COLLECTION:
            raise InvalidTsaArtifact(
                f"{_describe(item_path)} accepts a material unresolved WHAT, "
                "which is not waivable inside TSA.",
                code="DISPOSITION_NOT_WAIVABLE",
            )
        seen.append(str(reference))
    duplicates = sorted({item for item in seen if seen.count(item) > 1})
    if duplicates:
        raise InvalidTsaArtifact(
            f"{_describe(path)} repeats {duplicates}.",
            code="DISPOSITION_DUPLICATE_REFERENCE",
        )


BODY_VALIDATORS = {
    ARCHITECTURE: _validate_architecture_body,
    INPUT_MANIFEST: _validate_input_manifest_body,
    PROCESS_RESULT: _validate_process_result_body,
    REVIEW_RESULT: _validate_review_result_body,
    HUMAN_DECISION: _validate_human_decision_body,
}


# ---------------------------------------------------------------------------
# Envelope (4.2) and whole-artifact validation (4.4)
# ---------------------------------------------------------------------------

ENVELOPE_REQUIRED = (
    "artifact_digest",
    "artifact_type",
    "body",
    "cycle_id",
    "project_code",
    "project_entity_id",
    "schema_version",
    "workspace_identity",
)


@dataclass(frozen=True)
class TsaArtifact:
    """One validated artifact: schema clean and digest recomputed, not trusted."""

    artifact_type: str
    schema_version: int
    workspace_identity: str
    project_entity_id: str
    project_code: str
    cycle_id: str
    iteration: int | None
    body: dict[str, Any]
    artifact_digest: str

    @property
    def identity(self) -> ArtifactIdentity:
        return ArtifactIdentity(
            workspace_identity=self.workspace_identity,
            project_entity_id=self.project_entity_id,
            project_code=self.project_code,
            cycle_id=self.cycle_id,
        )


def compute_artifact_digest(payload: dict[str, object]) -> str:
    """Recompute the digest of a payload from its own declared type and version.

    The declared fields are read but not trusted: `validate_artifact` decides
    whether they are admissible. The reused-subtree rule is derived from the
    declared type, never supplied.
    """
    artifact_type = _require_known_artifact_type(payload.get("artifact_type"))
    version = payload.get("schema_version")
    if version != SCHEMA_VERSION:
        raise InvalidTsaArtifact(
            f"schema_version {version!r} is refused; this specification defines "
            f"version {SCHEMA_VERSION} only."
        )
    return artifact_digest(artifact_type, SCHEMA_VERSION, payload)


def validate_artifact(payload: object) -> TsaArtifact:
    """Validate one artifact payload: envelope, closed body, then digest (4.4).

    The stored `artifact_digest` is compared against a value recomputed from the
    payload, never against another stored field. Persisted identity is validated
    exactly as stored and is never normalised (3.1).
    """
    envelope = _require_object(payload, ("<payload>",))
    artifact_type = _require_known_artifact_type(envelope.get("artifact_type"))
    iterated = artifact_type in ITERATED_ARTIFACT_TYPES
    _closed_keys(
        envelope,
        required=(*ENVELOPE_REQUIRED, *(("iteration",) if iterated else ())),
        optional=(),
        path=(artifact_type,),
    )
    version = envelope["schema_version"]
    if not _is_integer(version) or version != SCHEMA_VERSION:
        raise InvalidTsaArtifact(
            f"schema_version {version!r} is refused; this specification defines "
            f"version {SCHEMA_VERSION} only."
        )
    iteration = (
        _require_iteration(envelope["iteration"], (artifact_type, "iteration"))
        if iterated
        else None
    )
    identity = ArtifactIdentity(
        workspace_identity=_require_text(
            envelope["workspace_identity"], (artifact_type, "workspace_identity")
        ),
        project_entity_id=_require_text(
            envelope["project_entity_id"], (artifact_type, "project_entity_id")
        ),
        project_code=_require_text(
            envelope["project_code"], (artifact_type, "project_code")
        ),
        cycle_id=require_canonical_cycle_id(
            envelope["cycle_id"], (artifact_type, "cycle_id")
        ),
    )
    stored_digest = _require_digest(
        envelope["artifact_digest"], (artifact_type, "artifact_digest")
    )
    BODY_VALIDATORS[artifact_type](envelope["body"], (artifact_type, "body"), identity)
    recomputed = artifact_digest(artifact_type, SCHEMA_VERSION, envelope)
    if stored_digest != recomputed:
        raise InvalidTsaArtifact(
            f"{artifact_type} carries artifact_digest {stored_digest}, but its "
            f"payload digests to {recomputed}."
        )
    return TsaArtifact(
        artifact_type=artifact_type,
        schema_version=SCHEMA_VERSION,
        workspace_identity=identity.workspace_identity,
        project_entity_id=identity.project_entity_id,
        project_code=identity.project_code,
        cycle_id=identity.cycle_id,
        iteration=iteration,
        body=dict(envelope["body"]),
        artifact_digest=stored_digest,
    )


def sealed_artifact(payload: dict[str, object]) -> dict[str, object]:
    """The same payload with a freshly computed `artifact_digest`, validated.

    Used when writing: the digest is never taken from the caller.
    """
    unsealed = {key: item for key, item in payload.items() if key != "artifact_digest"}
    sealed = {**unsealed, "artifact_digest": compute_artifact_digest(unsealed)}
    validate_artifact(sealed)
    return sealed


# ---------------------------------------------------------------------------
# Carrier payload boundary (4.1, 12)
# ---------------------------------------------------------------------------

#: The fence markers of 4.1. The carrier is parsed by scanning lines rather
#: than by one regex: a regex prefix can absorb an earlier fence, which would
#: let a second payload hide above the one that matched.
JSON_FENCE_OPENER = "```json"
FENCE_MARKER = "```"

#: The heading of the immutable artifact carrier (4.1).
CARRIER_HEADING_PREFIX = "# "


def _refuse_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Refuse a textual object that names one key twice.

    Parser integrity, not a new schema rule: rule 4 of 5.1 sorts keys and emits
    each exactly once, so text carrying a key twice is not the canonical
    serialization of any value. `json.loads` would otherwise silently keep the
    last one, and the digest check could not notice, because the dropped key
    never reaches the re-serialization.
    """
    seen: set[str] = set()
    duplicates: set[str] = set()
    for key, _ in pairs:
        if key in seen:
            duplicates.add(key)
        seen.add(key)
    if duplicates:
        raise InvalidTsaArtifact(
            f"The JSON payload names {sorted(duplicates)} more than once; a "
            "canonical payload carries each key exactly once."
        )
    return dict(pairs)


def _load_payload_object(raw: str) -> dict[str, object]:
    """Decode one payload, turning every expected decoder failure into a refusal.

    `InvalidTsaArtifact` is itself a `ValueError`, so the duplicate-key hook's
    refusal is re-raised before the generic branch can rewrap it. The generic
    branch exists for CPython's integer-conversion limit, which `json.loads`
    raises as a plain `ValueError` rather than a `JSONDecodeError`.
    """
    try:
        payload = json.loads(raw, object_pairs_hook=_refuse_duplicate_keys)
    except InvalidTsaArtifact:
        raise
    except json.JSONDecodeError as error:
        raise InvalidTsaArtifact(
            f"The Document's JSON payload does not parse: {error}"
        ) from error
    except ValueError as error:  # CPython's int -> str digit limit, and kin
        raise InvalidTsaArtifact(
            f"The Document's JSON payload holds a value the decoder refuses: {error}"
        ) from error
    return _require_object(payload, ("<payload>",))


def _split_trailing_envelope(text: str) -> tuple[list[str], str]:
    """Split a carrier into the lines before its envelope and the payload text.

    The whole carrier is examined: there must be exactly **one** `` ```json ``
    opener anywhere in it, it must have a closing fence, and nothing but
    whitespace may follow that closing fence. Counting the openers across the
    entire text is what stops a second payload hiding above the trailing one.
    """
    lines = text.split("\n")
    openers = [
        index for index, line in enumerate(lines) if line.strip() == JSON_FENCE_OPENER
    ]
    if len(openers) != 1:
        raise InvalidTsaArtifact(
            f"The Document carries {len(openers)} ```json fences; exactly one "
            "payload envelope is permitted."
        )
    start = openers[0]
    closing = next(
        (
            index
            for index in range(start + 1, len(lines))
            if lines[index].strip() == FENCE_MARKER
        ),
        None,
    )
    if closing is None:
        raise InvalidTsaArtifact("The Document's ```json fence is never closed.")
    if "\n".join(lines[closing + 1 :]).strip():
        raise InvalidTsaArtifact(
            "The Document carries content after the closing fence; the envelope "
            "must end it."
        )
    return lines[:start], "\n".join(lines[start + 1 : closing])


def _require_artifact_carrier_prefix(prefix: list[str]) -> None:
    """The immutable carrier's prefix: heading, blank, one paragraph, blank (4.1)."""
    shape = (
        "a level-1 heading, one blank line, exactly one prose paragraph, one "
        "blank line, then the envelope"
    )
    if len(prefix) < 4 or prefix[1] != "" or prefix[-1] != "":
        raise InvalidTsaArtifact(
            f"The Document is not the frozen carrier shape: {shape}."
        )
    heading = prefix[0]
    if not heading.startswith(CARRIER_HEADING_PREFIX) or not heading[2:].strip():
        raise InvalidTsaArtifact(
            f"The Document does not open with a non-empty level-1 heading: {shape}."
        )
    prose = prefix[2:-1]
    if not prose or any(not line.strip() for line in prose):
        raise InvalidTsaArtifact(
            f"The Document does not carry exactly one prose paragraph: {shape}."
        )
    if any(FENCE_MARKER in line for line in prose):
        raise InvalidTsaArtifact("The Document's prose paragraph carries a fence.")


def extract_artifact_payload(markdown: str | None) -> dict[str, object]:
    """Read the payload out of an immutable TSA artifact Document (4.1).

    The WHOLE carrier is validated: a level-1 heading, exactly one prose
    paragraph carrying no fence, exactly one `` ```json `` envelope in the
    entire text, and nothing after its closing fence. An entirely empty carrier
    raises `EmptyTsaCarrier`, which 4.4 distinguishes from malformed content.
    What to do about a shell is recovery (I10); reading the Document out of
    Fibery is I02.
    """
    text = markdown or ""
    if not text.strip():
        raise EmptyTsaCarrier("The Document carries no content at all.")
    prefix, payload = _split_trailing_envelope(text)
    _require_artifact_carrier_prefix(prefix)
    return _load_payload_object(payload)


def extract_architecture_envelope(markdown: str | None) -> dict[str, object]:
    """Read the trailing envelope out of an Architecture Document (4.1).

    The Architecture Document has its own carrier rule: rendered Markdown, then
    exactly one `` ```json `` envelope that ends the Document. The rendered
    prefix MAY carry other fenced blocks — the Architect is allowed illustrative
    diagrams (9.1) — but it may carry no second `` ```json `` envelope.
    Validating the prose against the sixteen headings is I06.
    """
    text = markdown or ""
    if not text.strip():
        raise EmptyTsaCarrier("The Document carries no content at all.")
    prefix, payload = _split_trailing_envelope(text)
    if not any(line.strip() for line in prefix):
        raise InvalidTsaArtifact(
            "An Architecture Document carries rendered Markdown before its "
            "envelope; this one carries none."
        )
    return _load_payload_object(payload)


# ---------------------------------------------------------------------------
# Pure structural lineage bindings (4.6.5 invariants 1-5)
# ---------------------------------------------------------------------------


def validate_structural_lineage(
    *,
    architecture: TsaArtifact,
    input_manifest: TsaArtifact,
    process_result: TsaArtifact | None = None,
    review_result: TsaArtifact | None = None,
    human_decision: TsaArtifact | None = None,
    review_document_id: str | None = None,
) -> None:
    """Invariants **1-5 only** of 4.6.5, over artifacts supplied explicitly.

    A clean return is NOT "the lineage is valid": two of the seven frozen
    invariants are deliberately not evaluated here, and a caller must not read
    this as all seven holding. The name says *structural* for that reason.

    Validated here:

    1. every artifact's `cycle_id` and `project_entity_id` equal the
       Architecture Document's;
    2. every `manifest_digest` equals the Input Manifest's;
    3. a Review Result's `process_result_digest` names a Process Result of the
       same `iteration`;
    4. a Human Decision's target names a Review Result of the same `iteration`,
       with the Decision's own envelope `iteration` agreeing too;
    5. a Human Decision's `architecture_fingerprint` equals the Review Result's.

    Deferred, and NOT checked here:

    6. `accepted_dispositions[*].ref` resolves under section 6 — resolving an
       index against a persisted artifact's array needs cycle context this
       module does not have, and belongs to **I11**. Only the reference
       *grammar* is enforced, at schema time.
    7. `render(process_result.intended_output, manifest_body)` reproduces the
       Architecture `content_fingerprint` — needs the renderer, and belongs to
       **I06**.

    `review_document_id` is the Fibery Document id the Review Result actually
    lives at. A TSA artifact does not carry its own Document id — the frozen
    wire format has no such field and this work item may not add one — so the
    caller supplies the durable identity it already knows. Without it, a Human
    Decision naming a Review Document that does not exist would still agree with
    itself. It is **required** whenever a Human Decision and a Review Result are
    validated together, and the call fails closed if it is missing.

    Nothing is fetched and no id is resolved: every artifact compared must
    already be in hand.
    """
    present = [
        artifact
        for artifact in (
            architecture,
            input_manifest,
            process_result,
            review_result,
            human_decision,
        )
        if artifact is not None
    ]
    _validate_cycle_and_project(present, architecture)
    _validate_manifest_binding(present, input_manifest.body["manifest_digest"])
    if review_result is not None and process_result is not None:
        _validate_review_binds_process(review_result, process_result)
    if human_decision is not None and review_result is not None:
        _validate_decision_binds_review(
            human_decision, review_result, review_document_id
        )


def _validate_cycle_and_project(
    artifacts: list[TsaArtifact], architecture: TsaArtifact
) -> None:
    for artifact in artifacts:
        if artifact.cycle_id != architecture.cycle_id:
            raise InvalidTsaArtifact(
                f"{artifact.artifact_type} carries cycle_id "
                f"{artifact.cycle_id!r}, not the Architecture's "
                f"{architecture.cycle_id!r}."
            )
        if artifact.project_entity_id != architecture.project_entity_id:
            raise InvalidTsaArtifact(
                f"{artifact.artifact_type} belongs to a different Project than "
                "the Architecture Document."
            )


def _validate_manifest_binding(artifacts: list[TsaArtifact], expected: object) -> None:
    for artifact in artifacts:
        stored = artifact.body.get("manifest_digest")
        if stored is not None and stored != expected:
            raise InvalidTsaArtifact(
                f"{artifact.artifact_type} binds manifest_digest {stored}, not "
                f"the cycle's {expected}."
            )


def _validate_review_binds_process(
    review_result: TsaArtifact, process_result: TsaArtifact
) -> None:
    if review_result.iteration != process_result.iteration:
        raise InvalidTsaArtifact(
            f"The Review Result of iteration {review_result.iteration} names a "
            f"Process Result of iteration {process_result.iteration}."
        )
    if review_result.body["process_result_digest"] != process_result.artifact_digest:
        raise InvalidTsaArtifact(
            "The Review Result's process_result_digest does not name the "
            "supplied Process Result."
        )


def _validate_decision_binds_review(
    human_decision: TsaArtifact,
    review_result: TsaArtifact,
    review_document_id: str | None,
) -> None:
    """One iteration and one Review Document run through every spelling."""
    if review_document_id is None:
        raise InvalidTsaArtifact(
            "Validating a Human Decision against a Review Result requires the "
            "Review Document's actual id; without it the Decision is only "
            "checked against itself."
        )
    target = human_decision.body["target"]
    if human_decision.iteration != target["iteration"]:
        raise InvalidTsaArtifact(
            f"The Human Decision envelope carries iteration "
            f"{human_decision.iteration} but targets iteration "
            f"{target['iteration']}."
        )
    if target["iteration"] != review_result.iteration:
        raise InvalidTsaArtifact(
            f"The Human Decision targets iteration {target['iteration']} but "
            f"names a Review Result of iteration {review_result.iteration}."
        )
    if target["review_result_digest"] != review_result.artifact_digest:
        raise InvalidTsaArtifact(
            "The Human Decision's target.review_result_digest does not name the "
            "supplied Review Result."
        )
    if human_decision.body["review_result"]["payload_digest"] != (
        review_result.artifact_digest
    ):
        raise InvalidTsaArtifact(
            "The Human Decision's review_result.payload_digest does not name the "
            "supplied Review Result."
        )
    for spelling, stored in (
        ("target.review_result_document_id", target["review_result_document_id"]),
        (
            "review_result.document_id",
            human_decision.body["review_result"]["document_id"],
        ),
    ):
        if stored != review_document_id:
            raise InvalidTsaArtifact(
                f"The Human Decision's {spelling} is {stored!r}, but the Review "
                f"Result actually lives at {review_document_id!r}."
            )
    if (
        human_decision.body["architecture_fingerprint"]
        != review_result.body["architecture_fingerprint"]
    ):
        raise InvalidTsaArtifact(
            "The Human Decision's architecture_fingerprint differs from the "
            "Review Result's."
        )
