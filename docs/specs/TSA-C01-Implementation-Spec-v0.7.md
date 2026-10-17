# TSA-C01 — Implementation Specification v0.7 (delta to v0.3 + v0.4 + v0.5 + v0.6)

**Status:** FROZEN.
**Human approval:** explicit instructions authorizing a narrow, TSA-specific
read-back equivalence for the Fibery table re-serialization observed in the
first live TSA pilot, given for repository snapshot
`a242d5a12935c247a74d1adeeea72195ee85b206`.
**Implementation authorization:** GRANTED ONLY FOR THE BOUNDED CORRECTION
DESCRIBED IN SECTIONS 3–5.
**Authority source:** `docs/architecture/TSA-C01-Contract-v0.2.md` (frozen),
unchanged.
**Base:** `docs/specs/TSA-C01-Implementation-Spec-v0.3.md`, `-v0.4.md`,
`-v0.5.md` and `-v0.6.md` (all frozen), unchanged.

The approval record is those instructions. No signature or authenticated
identity is claimed for them.

## 1. Relation to v0.3–v0.6

**SPEC.** This document is a **delta**. v0.3, v0.4, v0.5 and v0.6 remain
authoritative and apply in full, except for the one read-back rule below.
Nothing in them is restated, amended or replaced, and their files are
unchanged. In particular:

- canonical emission is unchanged: `render_architecture`, the table header,
  the separator `|---|---|---|---|---|---|`, `escape_markdown`, the `<br>`
  join of array-valued cells (v0.3 8.3, 8.3.1) and the carrier (v0.3 4.1,
  4.6.1) produce the same bytes as before;
- no result code is added, removed or re-meant (v0.3 13.8, v0.5, v0.6);
- no wire schema, artifact schema, digest or durable lifecycle state changes;
- `document_fingerprint`, `canonical_markdown` and the RAW source
  canonicalization are unchanged and remain the only fingerprint algorithm;
- no persisted Document is migrated, rewritten or re-sealed.

## 2. The observed discrepancy

**EVIDENCE.** In the first live TSA pilot (cycle `tsa-pilot-20261017-a`,
2026-10-17) the Architect output was persisted and the post-apply
Architecture Document was written. Its read-back was refused with
`ARCHITECTURE_RENDER_INVALID`: "The Requirement Traceability table does not
have the frozen header and one row per envelope traceability row." The
envelope was intact and its `content_fingerprint` was the fingerprint of the
emitted sections.

Rebuilding the emitted Document from the persisted `intended_output` and the
accepted Manifest, and comparing it with the stored Document, showed exactly
four kinds of difference, all Fibery Markdown re-serialization:

| | Emitted | Stored | Before v0.7 |
|---|---|---|---|
| A | table separator `\|---\|---\|---\|---\|---\|---\|` | `\| --- \| --- \| --- \| --- \| --- \| --- \|` | refused |
| B | a literal `<br>` inside a table row | one space | refused |
| C | a `- ` list bullet | `* ` | accepted (generated-list check and `canonical_markdown`) |
| D | the line before the envelope fence | one blank line inserted; the Document's final newline dropped | accepted (blank lines are not content) |

**EVIDENCE.** The deterministic test fake did not model A or B. The test
helper `tests/architecture_fake.py::fibery_stored` models A–D; applied to the
emitted pilot Document it reproduces the stored pilot Document byte for byte.
`docs/specs/TSA-C01-v0.7-evidence/` holds that pilot's `intended_output`
and its emitted and stored Architecture Documents, with the same workspace
identifiers replaced in each (so their envelope digests no longer verify);
a test checks that `fibery_stored` maps the emitted one onto the stored one
byte for byte. The fake's blank-line-before-fence rule was observed on this
Architecture Document only.

## 3. Accepted Fibery-stored traceability table

**SPEC.** When an applied Architecture Document is validated (v0.3 4.6.1,
8.2, 8.3), section 2 is accepted if its table is **exactly one** of:

1. the canonical table, under the unchanged v0.3 rule; or
2. the **Fibery-stored form** of the canonical table, defined below.

**SPEC — the canonical table is computed, never read.** The canonical table is
the existing renderer's table for the **sealed envelope's**
`body.traceability` and the **accepted Input Manifest** (the `Source` column).
Displayed cell text is never parsed for values; it is only compared with an
expected line computed from those trusted inputs.

**SPEC — the Fibery-stored form.** From the canonical table lines
`header, separator, row₁ … rowₙ`, the Fibery-stored form is, line for line:

- `header`, unchanged;
- exactly `| --- | --- | --- | --- | --- | --- |`;
- each `rowᵢ` with every literal `<br>` replaced by exactly one space
  (U+0020), and no other change.

A canonical row's `<br>` can only be renderer output — the `<br>` join of an
array cell or the escaped line break of a cell value — because
`escape_markdown` maps a model-supplied `<` and `>` to `&lt;` and `&gt;`. The
substitution is therefore confined to table cells.

**SPEC — exactness.** The stored table is accepted in the Fibery-stored form
only if its non-blank lines are **equal** to that form: the same header, the
same number of rows in the same order, the same column count and every byte
of every cell. Trailing whitespace on a line and blank lines are not
content, exactly as the existing section reader already treats every
section. The table is one form as a whole: the canonical separator with
Fibery-stored rows, or the Fibery separator with canonical rows, is refused.

**SPEC — refused.** Any other representation is
`ARCHITECTURE_RENDER_INVALID`, in particular: another separator (alignment
colons, partial spacing, other dash counts, another column count); `<br>`
kept, dropped, doubled, turned into `<br/>`, a comma, a new line or any other
text; padded, collapsed or otherwise re-spaced cells; and any changed,
added, removed, duplicated or reordered row, column or cell. A change Fibery
was not observed to make is never accepted.

## 4. Fingerprint over the canonical representation

**SPEC.** `content_fingerprint` keeps its v0.3 4.6.1 meaning: the
`document_fingerprint` of the **emitted** canonical normative Markdown. The
validator establishes it as follows:

1. Validate carrier, schema, digest and Manifest binding (unchanged).
2. Validate headings, sections and the generated lists (unchanged).
3. Validate section 2 under section 3 above.
4. If the table is in the Fibery-stored form, rebuild the normative Markdown
   **in memory**: the lines from the beginning through the section 2 heading
   exactly as read, then one blank line, the canonical table lines of
   section 3, one blank line, then every line from the section 3 heading to
   the envelope exactly as read. Otherwise the normative Markdown is used as
   read.
5. Compute `document_fingerprint` (unchanged algorithm) over that Markdown
   and require it to **equal** the envelope's `content_fingerprint`.
6. Rules S and X (v0.3 8.3, v0.4) remain checked on the Markdown as read.

**SPEC.** Only section 2 is rebuilt. Every other section is fingerprinted in
its observed form, through `canonical_markdown`'s existing equivalence (which
already absorbs C and D), so an edit anywhere else in the normative text
still fails step 5. The stored fingerprint is never trusted without this
recomputation, and a valid `artifact_digest` is never evidence that the
displayed Markdown is unchanged.

**SPEC.** Because step 5 is over the canonical table rebuilt from the
envelope, an envelope whose arrays were regrouped so that their stored
display is unchanged (for example two `constraints` merged into one element
holding a space) still fails: its canonical table differs from the one the
fingerprint was taken over.

**SPEC.** When the post-apply Architecture is read for recovery, review or a
decision, its fingerprint is the `content_fingerprint` that step 5 has just
recomputed and matched. A Fibery-stored applied Architecture therefore
fingerprints exactly as its emitted Markdown, so the frozen comparisons of
v0.3 (Architect cases 2–4, the Review's `architecture_fingerprint`, a
REWORK's bound fingerprint) are unchanged in meaning. The pre-apply bootstrap
carrier is unaffected.

## 5. Recovery

**SPEC.** No recovery case, transition or stage changes (v0.3 13.6, 14,
contract 14.3). A cycle whose Architecture holds the current iteration's
recorded output in the Fibery-stored form is **case 3 (`OUTPUT_APPLIED`)**:
nothing is re-applied, no Process Result is created and the Architect is not
called; the next step is the Reviewer stage. It is not case 2, case 4, a
malformed artifact or an absent Architecture.

## 6. Limits

**SPEC.** This delta accepts exactly the transformations observed once, on
one live Document. How Fibery stores an empty table cell, or `\|`, `\\`,
`&lt;` or `&gt;` inside a cell, was **not** observed. Such a cell is accepted
only exactly as section 3 defines it — its canonical text, unchanged — and
any other storage of it is refused. Any other table shape, or any
re-serialization not listed in section 2, is refused as before; widening this
rule requires new live evidence and a new delta.

**SPEC.** Gate I-3 (payload size) is unaffected and remains INCOMPLETE.
