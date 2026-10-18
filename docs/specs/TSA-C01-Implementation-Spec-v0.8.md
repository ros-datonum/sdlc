# TSA-C01 — Implementation Specification v0.8 (delta to v0.3 + v0.4 + v0.5 + v0.6 + v0.7)

**Status:** FROZEN ON COMMIT; LIVE BEHAVIOUR UNVERIFIED (section 8).
**Human approval:** explicit instructions authorizing a narrow, TSA-specific
read-back equivalence for the Fibery HTML-entity re-serialization observed in
the second live TSA pilot, given for repository snapshot
`b50464b38586030688ce24849561821ce3996b52`.
**Implementation authorization:** GRANTED ONLY FOR THE BOUNDED CORRECTION
DESCRIBED IN SECTIONS 3–5.
**Authority source:** `docs/architecture/TSA-C01-Contract-v0.2.md` (frozen),
unchanged.
**Base:** `docs/specs/TSA-C01-Implementation-Spec-v0.3.md`, `-v0.4.md`,
`-v0.5.md`, `-v0.6.md` and `-v0.7.md` (all frozen), unchanged.

The approval record is those instructions. No signature or authenticated
identity is claimed for them.

## 1. Relation to v0.3–v0.7

**SPEC.** This document is a **delta**. v0.3–v0.7 remain authoritative and
apply in full, except for the one read-back rule below. Nothing in them is
restated, amended or replaced, and their files are unchanged. In particular:

- canonical emission is unchanged: `render_architecture`, `escape_markdown`
  (v0.3 8.3.1, which maps model `<` and `>` to `&lt;` and `&gt;`), the table
  and the carrier produce the same bytes as before;
- no result code is added, removed or re-meant;
- no wire schema, artifact schema, digest, Input Manifest or Process Result
  meaning, or durable lifecycle state changes;
- `document_fingerprint` and `canonical_markdown` are unchanged and remain
  the only fingerprint algorithm;
- no persisted Document is migrated, rewritten or re-sealed;
- v0.7's table rule (its sections 3–4) is unchanged and is a precondition of
  this rule.

## 2. The observed discrepancy

**EVIDENCE.** In the second live TSA pilot (cycle `tsa-pilot-20261018-a`,
2026-10-18) the Input Manifest and Process Result 0001 were persisted and the
post-apply Architecture Document was written. Its read-back was refused with
`ARTIFACT_MALFORMED`: "The envelope's content_fingerprint is not the
fingerprint of the sixteen sections it accompanies." The envelope was intact
and its `content_fingerprint` (`9f68dc95…`) is the fingerprint of the
Markdown that the unchanged renderer emits from the persisted
`intended_output` and the accepted Manifest.

Comparing that emitted Document with the stored one: every difference but one
is a v0.7 rule (separator, `<br>` in table rows, `- ` → `* `, the blank line
before the fence and the dropped final newline). The one other difference is
in section 3 (Solution Structure), a prose section:

| | Emitted | Stored |
|---|---|---|
| E | `{"uppercase": &lt;result&gt;}` | `{"uppercase": <result>}` |

The model text was `<result>`; 8.3.1 escaped it. The Document held no other
character reference. The literal `<br>` of the same prose line (the
renderer's escaped line breaks) was stored unchanged.

**EVIDENCE.** `docs/specs/TSA-C01-v0.8-evidence/` holds that pilot's
`intended_output` and its emitted and stored Architecture Documents, with the
workspace identity, Project entity id and the two tree fingerprints replaced
identically in each (so their envelope digests no longer verify). A test
checks that `tests/architecture_fake.py::fibery_stored`, extended by rule E
for prose lines, maps the emitted one onto the stored one byte for byte.

## 3. Markdown meaning of the two forms

**EVIDENCE.** Parsed by the pinned `markdown-it-py` 4.2.0 `commonmark`
preset, both lines are one paragraph. Their inline content differs:

- emitted: text `{"uppercase": <result>};` — the entity is a character
  reference, so a CommonMark renderer shows the characters `<result>`;
- stored: text `{"uppercase": `, **raw inline HTML** `<result>`, text `};`
  — a CommonMark renderer passes `<result>` through as an HTML tag, which a
  browser does not display.

So the three are distinct:

- A. **Source text.** The stored bytes are not the emitted bytes.
- B. **Markdown meaning.** Read as CommonMark, the stored form is *not*
  equivalent: the placeholder would disappear from a rendered view.
- C. **Fibery transport.** A CommonMark entity always yields a text
  character, so Fibery's own document holds the text `<result>`; its
  Markdown export writes that character without escaping it. This is
  INFERRED from the read-back, not observed in Fibery's interface.

**SPEC.** The normative content of an Architecture Document is its emitted
canonical Markdown, which `content_fingerprint` seals. This rule proves that
the stored Markdown is Fibery's export of exactly that canonical Markdown; it
does not claim that the stored Markdown means the same when rendered by
another CommonMark renderer (section 7).

## 4. Accepted Fibery-stored prose

**SPEC.** A **prose line** is a non-blank content line of one of the eleven
prose sections (headings 1, 3–13). Its **canonical line** is computed from the
stored line: split it at each literal `<br>`, replace in every segment each
`<` with `&lt;` and each `>` with `&gt;`, and join the segments with `<br>`.
Nothing else is changed. A canonical prose line maps onto itself, because
8.3.1 leaves no `<` or `>` in prose other than its own `<br>`.

**SPEC.** A stored prose line whose canonical line differs from it is a
**decoded line**. Decoded lines are accepted only when all of these hold:

1. the section 2 table is in its exact v0.7 Fibery-stored form (a Document
   with the canonical table is read exactly as before v0.8, with no prose
   rewritten);
2. no prose line of the Document holds `&lt;` or `&gt;` (Fibery was observed
   to decode every one; a Document is one form as a whole);
3. for each decoded line, the pinned parser's block-token types of the stored
   line equal those of its canonical line, and neither stream may be
   incomplete (the v0.4 completeness guard). A decoded character that opens
   an HTML block, a block quote or any other block is refused.

A failure of 2 or 3 is `ARCHITECTURE_RENDER_INVALID`.

**SPEC — not accepted.** No other character reference is decoded or
re-encoded (`&amp;`, `&quot;`, numeric references and so on keep v0.7's
behaviour, under which a changed one fails the fingerprint). Generated list
items (sections 14–16) and table cells holding `&lt;` or `&gt;` keep their
v0.3/v0.7 rules: a decoded one is refused, because that context was not
observed. A model `<br>` (emitted `&lt;br&gt;`) that Fibery decodes cannot be
told from the renderer's `<br>`; it is not guessed, and such a Document fails
the fingerprint.

## 5. Fingerprint over the canonical representation

**SPEC.** `content_fingerprint` keeps its v0.3 4.6.1 meaning. v0.7 section 4
is followed with one added step before its step 4: each decoded line is
replaced, **in memory**, by its canonical line; every other line is kept
exactly as read. v0.7's table rebuild is then applied, and
`document_fingerprint` (unchanged) of the result must **equal** the
envelope's `content_fingerprint`. Rules S and X stay checked on the Markdown
as read.

**SPEC.** The fingerprint check, not the mapping, decides acceptance: an
added, removed or altered tag, word, cell or list item still fails, and a
valid `artifact_digest` is never evidence that the displayed Markdown is
unchanged. When the post-apply Architecture is read for recovery, review or a
decision, its fingerprint is the `content_fingerprint` just recomputed and
matched (v0.7 section 4, unchanged in meaning).

**SPEC.** The Reviewer's prompt keeps receiving the Architecture Document as
read (v0.3 16.2, unchanged).

## 6. Recovery

**SPEC.** No recovery case, transition or stage changes. A cycle whose
Architecture holds the current iteration's recorded output in the
Fibery-stored form of sections 4–5 is **case 3 (`OUTPUT_APPLIED`)**: nothing
is re-applied, no Process Result is created and the Architect is not called;
the next step is the Reviewer stage. For cycle `tsa-pilot-20261018-a` this is
reached without any Document repair, because its persisted Architecture,
Input Manifest and Process Result 0001 are used as stored.

**SPEC — refusal.** Everything outside sections 4–5 is refused as before;
nothing here retries, rewrites or re-seals a Document.

## 7. Limits

**SPEC.** This delta accepts exactly the transformation observed once, on one
live Document, in one prose paragraph, at an inline position. The following
were **not** observed and are refused or untouched as stated in section 4:
entities in list items or table cells, other entities, a decoded `<br>`, and
a decoded character at a block position.

**SPEC — residual risk.** The stored Markdown contains raw inline HTML where
the canonical holds a character reference (section 3, B). Any consumer that
renders the *stored* Markdown with a CommonMark renderer would hide or
activate such text: model prose such as `x <span hidden>s</span> y`,
`a <!-- c --> b` or `<http://example>` is accepted in its decoded form and
reads as raw HTML or an autolink there. Model prose that *begins* with a tag
(a block position) is refused once decoded, and such a cycle cannot recover
without a new rule.
That the Fibery interface shows the literal characters is inferred (section
3, C) and requires a live, read-only visual check before it is relied on.

**SPEC — non-goals.** No transport-side encoding is introduced (no double
escaping, backslash escaping or code spans before a write): no evidence shows
that Fibery would keep any of them, and changing what is written would change
existing Documents' read-back. No general HTML unescaping, no change to the
renderer and no repair of persisted Documents.

**SPEC.** Gate I-3 (payload size) is unaffected and remains INCOMPLETE.

## 8. Verification state

**EVIDENCE.** Offline only: the unsanitized live read-back of cycle
`tsa-pilot-20261018-a`, kept outside the repository, validates under this rule
to `content_fingerprint` `9f68dc95…`, and the replay of its persisted Process
Result's `intended_output` has the same fingerprint. That check is not
reproducible from the committed, sanitized evidence; the repository tests
prove the equivalent chain (the fake maps the evidence's emitted Document onto
its stored one, and the re-rendered carrier in stored form validates). No live read,
write, resume or model call was made for this delta. A live resume of that
cycle is the required live verification and needs separate authorization.
