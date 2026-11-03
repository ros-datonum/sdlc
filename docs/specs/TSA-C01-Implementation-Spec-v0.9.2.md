# TSA-C01 — Implementation Specification v0.9.2 (delta to v0.3 + v0.4 + v0.5 + v0.6 + v0.7 + v0.8 + v0.9 + v0.9.1)

**Status:** PROPOSED; LIVE BEHAVIOUR UNVERIFIED (section 11).
**Human approval:** pending, ARP1 Gate 3N22, for the v0.9.1 implementation
snapshot `a4252d5f93c3f6a8d9616aca0155b5b7e7fe2a29` (branch
`impl/tsa-c01-v091-stored-form-guard`, on specification commit
`4e1f05374b5a8bfede613bfc15332420e7f6ebfc`).
**Implementation authorization:** none by this document. Sections 4–10 may be
implemented only in a separately authorized implementation gate.
**Authority source:** `docs/architecture/TSA-C01-Contract-v0.2.md` (frozen),
unchanged.
**Base:** `docs/specs/TSA-C01-Implementation-Spec-v0.3.md` to `-v0.9.1.md`
(all frozen), unchanged.

## 1. Relation to v0.3–v0.9.1

**SPEC.** This document is a **delta**. v0.3–v0.9.1 remain authoritative and
apply in full, except that the Architect response contract gains the five
write-time rules of section 4, the Architect prompt gains the text of
section 6, the test fake contract of v0.9.1 section 7 is replaced by
section 7, the live probe gains the stop rule of section 10, and v0.9.1
section 10 is replaced by section 11. v0.9's prose check and v0.9.1's rules T
and R still apply unchanged. In particular:

- canonical emission is unchanged: `render_architecture`, `escape_markdown`
  (v0.3 8.3.1), the table, the generated lists and the carrier produce the
  same bytes as before;
- the read path is unchanged: v0.7's table rule, v0.8's prose rule,
  `validate_architecture_document`, `document_fingerprint` and
  `canonical_markdown`;
- no result code is added, removed or re-meant; `INVALID_MODEL_OUTPUT` keeps
  its meaning;
- no wire schema, artifact schema, digest, fingerprint algorithm, Input
  Manifest, Process Result, Review Result or Human Decision meaning, recovery
  case or durable lifecycle state changes;
- no persisted Document is migrated, rewritten, repaired or re-sealed.

**SPEC — amendments to v0.9.1.** A prose value holding `<`, `>`, `&lt;` or
`&gt;` inside an inline code span, which v0.9.1 accepts, is now refused
(rule C). v0.9.1 section 10's accepted re-probe composition, which held a `|`
in prose and in list items and a `<` in a prose code span, is now refused
(rules P and C); its offline test is corrected to that refusal, not deleted.

**SPEC — amendment to v0.9.** v0.9 section 4's informative accepted list
names "an autolink". A prose value holding an angle form together with
`://` or `www.`, such as `<https://example.com> is the base.`, is now refused
(rule C); the two v0.9 test cases that accept it move to the refused set and
are not deleted.

## 2. Observed and derived defects

**EVIDENCE.** ARP1 Gate 3N21 (2026-11-03) wrote six synthetic Architecture
carriers, rendered by the v0.9.1 implementation from the repository's test
fixture, as Project-root Documents of the scratch Project `27`, and read each
back once. Observed, against the v0.9.1 fake:

1. **Pipe outside a table row.** The renderer emits a model `|` as `\|`
   (8.3.1). Fibery stored `\|` as `|` in a prose line and in the list items of
   sections 14–16, and kept `\|` in a table cell.
2. **Inline code span.** Fibery kept `&lt;` and `&gt;` inside an inline code
   span of a prose line, while decoding them outside it.
3. **Leading `>`.** A table cell or a list item whose text begins with `>`
   (a decoded `&gt;`) was stored with `\>`.
4. **Character references.** `&amp;`, `&quot;`, `&#60;`, `&#x3C;` and `&LT;`
   were stored as `&`, `"`, `<`, `<` and `<` in a prose line, a table cell and
   a list item; `&amp` without `;` was kept.

Verified unchanged: a single newline, two in a row and a newline followed by
two spaces and `- ` in table cells and list items; `\` (emitted `\\`), `*x*`,
`R&D`, `A & B` and `?a=1&not=2&copy=3` in all three contexts; a plain-text
code span in all three contexts; and the v0.9.1 `L3-M1-exact` Document, whose
emitted and stored bytes equal Gate 3N17's.

**EVIDENCE — D1, verified.** The `L2-composite` output, accepted by v0.9.1,
was refused on live read-back with `ARCHITECTURE_RENDER_INVALID`. Offline,
with only observation 1 applied, a `|` in a prose value is refused by the
unchanged reader with `ARTIFACT_MALFORMED` (fingerprint), and a `|` in an
assumption, a risk detail or an open architecture question with
`ARCHITECTURE_RENDER_INVALID`; a `|` in a table cell reads back valid.

**EVIDENCE — D2, derived.** The `L2-codespan` output (code spans holding `<`,
`>` and a model `&lt;`, and no other angle bracket) read back valid. Offline,
with observation 2 and the v0.8 decoding applied to a prose value holding a
code span with `<` and another prose location holding a decoded `<`, the
unchanged reader refuses with `ARCHITECTURE_RENDER_INVALID` under v0.8's
one-form rule, in the same value, in another section, for `>`, and for a
model `&lt;` in the span. Each input transformation was observed live; the
combined Document was not written. D2 follows deterministically from the
unchanged reader and is not live-verified.

**EVIDENCE — historical corpus.** No value of the v0.7 and v0.8 pilot
outputs or of the TSA-01–TSA-04 Process Results holds a `|`, a backtick, a
`\`, a control character, a task box, `[` together with an angle form, or a
value beginning with a marker that section 4 refuses. Their prose
values begin lines with `- ` and `N. ` after a newline, and one prose value
begins with `1. `; their table cells hold a newline followed by `- `. Every
one of those Documents read back valid live except the `arp1-tsa-04`
iteration 2 Architecture, which was refused for its model `<br>` (v0.9
section 2).

## 3. Representation boundary

**SPEC.** Every string the Architect authors reaches Fibery through exactly
one of the following contexts. A value appears outside a fenced JSON block
only as listed; inside one (the Architecture envelope, and the Process Result
Document, which holds the whole response) Fibery stores every value verbatim.

| Value | Rendered context | Rendered form |
|---|---|---|
| `sections.*` (12) | prose: one line after its heading | 8.3.1-escaped; newline → `<br>` |
| `traceability[i].how_satisfied` | table cell, column 4 | 8.3.1-escaped |
| `traceability[i].constraints[j]`, `.gaps[j]` | table cell, columns 5 and 6 | each 8.3.1-escaped, joined by `<br>` |
| `assumptions[j]`, `open_architecture_questions[j]` | list item `- {v}` | 8.3.1-escaped |
| `risks[j].detail` | list item `- {v} — Impact: {impact}` | 8.3.1-escaped |
| `traceability[i].requirement_id`, `.anchors[j]` | table cells, columns 1–3 | restricted to selected ids and `tsa-s01`–`tsa-s16` |
| `risks[j].impact` | list item suffix | enum `LOW`, `MEDIUM`, `HIGH` |
| `product_questions[*]` | fenced JSON only | JSON |

Renderer-owned text — headings and anchor comments, the table header and
separator, the Source column, the `<br>` joins, the `- ` bullet, the
`— Impact:` suffix and `None identified.` — is not model-authored and is not
judged by any write-time rule.

**SPEC.** The stored form of each context, and the rules that close it:

| Context | Fibery transformation (section 2 and earlier evidence) | Reader | Closed by |
|---|---|---|---|
| prose | `&lt;`/`&gt;` decoded outside code spans (v0.8, 3N21); kept inside spans (3N21); `\|` stored as `|` (3N21); `- ` → `* ` (v0.1) | v0.8 one-form rule, `canonical_markdown` fingerprint | v0.9 prose check, rules R, U, K, P, C, L |
| table cell | `<br>` → space; `&lt;`/`&gt;` decoded (3N17); `\|` kept (3N21); leading `>` → `\>` (3N21) | exact stored row (v0.7) | rules T, R, U, K, P, L |
| list item | `- ` → `* `; `&lt;`/`&gt;` decoded (3N17); `\|` → `|` (3N21); leading `>` → `\>` (3N21) | exact item after bullet canonicalization | rules T, R, U, K, P, L |
| character references | the five observed decoded in all three contexts (3N21) | changes the fingerprint or the exact row or item | rule R |

## 4. Write-time rules

**SPEC — definitions.** The **prose values**, the **structured text values**
and their visit order are those of v0.9.1 sections 3 and 4. The **list-item
values** are `assumptions[j]`, `risks[j].detail` and
`open_architecture_questions[j]`; the **cell values** are
`traceability[i].how_satisfied`, `.constraints[j]` and `.gaps[j]`. The
**angle forms** are `<`, `>`, `&lt;` and `&gt;`. The **segments** of a value are its parts between line breaks (line feed, carriage return, or the
pair). Once rule K holds, the **code spans** of a value are, in each segment,
the text between its first and second backtick, its third and fourth, and so
on; they have exactly the boundaries of the CommonMark code spans of the
rendered value (their content is the 8.3.1-escaped text), because
every backtick run is one backtick, every segment pairs its own backticks so
no span crosses a renderer `<br>` or a cell's item join, and the renderer
emits no backtick and never leaves a model backtick backslash-escaped. For a
value, `t` is the value with leading and trailing whitespace removed, and
**whitespace** is what Python's `str.strip` and `str.isspace` treat as
whitespace, as in 8.3.1's strip. A
text **begins with a marker** when its first character is one of `#`, `-`,
`+`, `*`, `_`, `~` and `=`, or when it begins with 1–9 ASCII digits and then
`.` or `)` followed by a space, a tab or the end of the text. A
**thematic break** is three or more of the same character `-`, `*` or `_`,
optionally separated by spaces or tabs, and nothing else. A **task box** is
`[ ]`, `[x]` or `[X]` followed by a space, a tab or the end of the text.

**SPEC — rule U (control characters).** A prose value or a structured text
value is refused when it contains U+0000–U+0009, U+000B, U+000C,
U+000E–U+001F, U+007F–U+009F, U+2028 or U+2029. Line feed and carriage return stay
allowed.

**SPEC — rule K (code-span shape).** A prose value or a structured text
value is refused when it contains two adjacent backticks, when one of its
segments holds an odd number of backticks, or when one of its code spans
begins or ends with a space.

**SPEC — rule P (pipe).**

- P1: a prose value or a list-item value is refused when it contains `|`.
- P2: a cell value is refused when it contains `\` immediately followed by
  `|`, or when one of its code spans contains `|`.

A `|` elsewhere in a cell value stays allowed: rendered `\|`, it was observed
stored unchanged and read back valid.

**SPEC — rule C (code span and link).** A prose value is refused when one
of its code spans contains an angle form, or when it contains an angle form
together with `[`, `://`, `www.`, `@` or `$`. Every angle form of an
accepted prose value therefore lies outside every code span, link
destination, link title, reference definition, URL or email autolink and
dollar-delimited span, where Fibery decodes it as v0.8 and v0.9
specify, so v0.9's stored-form model is exact for it.

**SPEC — rule L (leading block structure).** A structured text value is
refused when its `t` begins with a marker or a task box, or is a thematic
break. A prose value is refused when its `t` is a thematic break. Otherwise
it is refused when its `t` begins with a marker or a task box, unless `t`
begins with `- `, `* ` or `1. ` immediately followed by a character that is
not whitespace and the text after that prefix neither begins with a marker
or a task box nor is a thematic break. A marker after a line break inside a
value is not judged. (A prose value beginning with 1–6 `#` and a space is
already refused by the trial render's frozen heading check, which keeps its
own refusal.)

**SPEC — placement and order.** `validate_architect_output` applies rules U,
K, P, C and L, in that order, after rule R of v0.9.1, so every earlier refusal
keeps its own code and message. Each rule reads the normalized
`intended_output` values, never the rendered Markdown, and visits values in
v0.9.1 visit order: U and K the prose values then the structured text
values; P1 the prose values then the list-item values; P2 the cell values; C
the prose values; L the structured text values then the prose values. The rules run only there: not in
`render_architecture`, `build_architecture_carrier`, the replay of a recorded
output, or any reader.

**SPEC — refusal.** The first refused value refuses the whole response with
`INVALID_MODEL_OUTPUT`, naming the rule as `spec v0.9.2 rule U`, `K`, `P1`,
`P2`, `C` or `L`, and the value by its path in the normalized
`intended_output` as in v0.9.1 section 4 (for a cell value, with that row's
`requirement_id`). Nothing is repaired, normalized, re-requested or
persisted. The rules are pure and deterministic, with cost linear in the
output.

**INFORMATIVE.** Refused: `a | b` and `a \| b` in any prose or list-item
value; `` `a|b` `` and `a \| b` in a cell; a code span across a line break, a
double-backtick span and `` ` a ` `` in any value; `` Use `a<b` ``,
`` `&lt;x&gt;` ``, `[a](x<y)`, `See https://example.invalid/?q=a<b` and
`<https://example.com> is the base.` and `Page ops@example.invalid if p > 2`
in prose; a tab, NUL or U+0085 in any value; `- x`, `-x`, `--dry-run`,
`# x`, `#1`, `*x*`, `_x_`, `1. x`, `2) x`, `[ ] x` and `---` as a structured
text value; `+ x`, `-1`, `3. x`, `1) x`, `-`, `1.`, `- [ ] x`, `- - x`,
`- -x`, `- --`, `1. - x`, `* 2) x` and `***` as a prose value. Accepted:
`a | b` in a cell; several complete code spans on several lines of one value
or in several items of one cell; `` Call `run()` if x < y `` and
`` `a` < `b` `` and `see [a](https://example.invalid/x)` in prose; `1.5 s`
as any value; `- x`, `* x`, `1. x` as a prose value; a line break followed by
`- ` or `1. ` inside any value. Refused although derived safe: `[1] x < y`,
`a@b`, `$5 if x < y` and other non-link text beside an angle form in
prose; structured text
values beginning with `-`, `*`, `#` or `_` that are not CommonMark block
markers; refused
although observed safe live: the `L2-codespan` Document.

## 5. Mutation boundary and failure

**SPEC.** v0.9 section 5 applies unchanged to rules U, K, P, C and L: the check
precedes the Process Result write and every Architecture write, for iteration
1 of `start` and for every REWORK iteration; on refusal one Architect call
was made, nothing is written, the Architecture keeps its previous valid
content, the Input Manifest and every durable Human Decision are unchanged,
the Reviewer is not invoked, nothing is retried, and a further Architect call
is made only by a separately invoked `resume`.

## 6. Architect prompt

**SPEC.** The "Text rules for every string value" list of the Architect
instructions gains these five items after the two items of v0.9.1 section 6,
verbatim:

```text
- never write a tab or another control character; use spaces and line
  breaks only;
- write code in single backticks only, close every backtick on the same
  line and in the same item, and never start or end code with a space;
- never write the character "|" in architecture sections, assumptions,
  risks or open_architecture_questions; in traceability write it only
  outside backticks and never with "\" directly before it;
- in architecture sections, never put "<", ">", "&lt;" or "&gt;" inside
  backticks, and never write them in a section that contains "[", "://",
  "www.", "@" or "$"; write such comparisons in words;
- begin every traceability, assumption, risk and open question value with
  a word, never with "#", "-", "+", "*", "_", "~", "=", a number followed
  by "." or ")", or "[ ]"; begin an architecture section with a word, or
  with "- ", "* " or "1. " followed by a word.
```

**SPEC.** The prompt is guidance only; section 4, v0.9 section 4 and v0.9.1
section 4 decide acceptance. The prompt text is not part of any digest or
fingerprint.

## 7. Test fake correction

**SPEC.** `tests/architecture_fake.py::fibery_stored` MUST reproduce the
observed stored form and nothing more. Definitions for the fake only: a
**code span** is a backtick, then zero or more characters other than a
backtick, then a backtick, matched left to right on one line; the **observed
references** are `&lt;` → `<`, `&gt;` → `>`, `&amp;` → `&`, `&quot;` → `"`,
`&#60;` → `<`, `&#x3C;` → `<` and `&LT;` → `<`, replaced in one left-to-right
pass whose output is never re-scanned. Outside a fence, each line:

1. the canonical table separator becomes the spaced separator (unchanged);
2. a table row (beginning `| `): each literal `<br>` becomes one space; then,
   outside code spans, the observed references are decoded; then every cell,
   split at each `|` not preceded by an unpaired `\`, whose text after its one
   leading space begins with `>` gains a `\` before that `>`; `\|` is kept;
3. a line beginning `- `: the `- ` becomes `* `; then, in the rest and
   outside code spans, the observed references are decoded and each `\|`
   becomes `|`; then, if the rest begins with `>`, a `\` is inserted before it;
4. every other line: outside code spans, the observed references are decoded
   and each `\|` becomes `|`.

The blank line before a fence opener that follows text and the dropped final
newline are unchanged; fenced lines are kept verbatim. No other reference is
decoded, no other character is escaped or unescaped, and nothing inside a code
span is changed (observed in prose; in a cell or item no accepted value has an
angle form or a character reference, rules T and R, so the step never decides
an accepted output there). Step 3 also applies to a prose line beginning `- `, where a
following `>` is refused by v0.9's block-structure check, so the step never
decides an accepted output. A code span delimited by more than one backtick,
padded with a space, crossing a line break or holding `|`; an angle form in a
link destination, link title or autolink; a control character; and a leading
marker or task box other than `>` in a cell or item, or a nested one
after a prose list marker, are outside the fake's contract: rules U, K, P, C
and L refuse every value whose stored form would depend on them. Emphasis
with `**` or `_`, and the other constructs of section 9's limit list, are
outside it too and are verified by section 11 W3.

**SPEC — evidence.** These ten files of Gate 3N21 (synthetic fixture content
and identity only) MUST be committed byte for byte, with no final newline
added, as `docs/specs/TSA-C01-v0.9.2-evidence/`, each pinned to its sha256:

| File | sha256 |
|---|---|
| `L2-composite.emitted.md` | `1d13a1bafc60d6b20b145b81f5372ac4fc92a1b04cf2028ae66247e671d22b01` |
| `L2-composite.stored.md` | `bb0320cfcbe7caf980eae01cc56e5a1883afa43c6a57e9efe9d1fb7c5f841f22` |
| `L2-codespan.emitted.md` | `b5b9b5c65126202afec892b994f4d4966bdcf069983891b9ea1182ee708c64bc` |
| `L2-codespan.stored.md` | `a6f88b4c7679d7c868d4138e07f79921543f69d21e8e5ef3a953faf8d79c09ac` |
| `L4-T-table.emitted.md` | `4772f9ef1dbfcdab99a4208e717d188e060bfbd9c122becfcb1563d1725654eb` |
| `L4-T-table.stored.md` | `8ba212b8a4aef7c52dc1f9d8a225f203f2e064a10b1f14832a46a15229870796` |
| `L4-T-lists.emitted.md` | `766a12fb41b43858aaf8903fb2e01794edccaefbd0a42f8788b7f9a867bdfa5c` |
| `L4-T-lists.stored.md` | `8fd5ff24fc308a81c9d1d665ce1388cc3c136782347011080462734db0d04927` |
| `L5-refs.emitted.md` | `37357ae5be0f96bf7f1e3f9728d5f313199337702ed140e93137c649edc430b9` |
| `L5-refs.stored.md` | `34426b9111a8d03b49aca905d621301a5f6061a7a917048b337e84a986409cd4` |

Gate 3N21's `L3-M1-exact` pair is byte-identical to the committed Gate 3N17
pair and is not committed again. The predicted files, the `L1` cases and the
probe's `evidence.json` (which holds real Fibery ids) are not committed.

**SPEC — tests that change.** A test whose expectation depended on the
v0.9.1 fake or on an output rules U, K, P, C or L now refuse is corrected to the
observed behaviour; none is deleted to make the suite pass, and no production
rule is added to match an old fake result. At the v0.9.1 snapshot these are
exactly: in `tests/test_tsa_architecture.py`,
`test_cells_fibery_keeps_verbatim_are_accepted_only_as_the_canonical_text`
(its fixture's prose `\|` is now stored as `|` and refused, the cell `\|` is
kept) and `test_another_decoded_entity_is_never_accepted` (the fake now
decodes `&amp;`); in `tests/test_tsa_v091_structured_values.py`,
`test_the_section_10_accepted_document_is_predicted_valid_offline` (now
expecting the rule P1 refusal of `sections.solution_structure`) and the
three lifecycle tests that use its response as the valid one
(`test_a_valid_start_applies_once_and_reads_back`,
`test_a_separate_resume_after_a_refused_rework_calls_the_architect_once`,
`test_a_valid_rework_reaches_the_next_boundary`), which take an output
accepted by v0.9.2; in `tests/test_tsa_v09_stored_form.py`, the `autolink`
case of `test_u1_an_output_that_survives_storage_is_accepted` and of
`test_u3_an_accepted_output_is_kept_verbatim_with_its_fingerprint`, which
moves to the refused set (rule C).

## 8. Required tests

**SPEC.** Offline, through the production functions and the corrected fake:

- **matrix:** for each prose value class, each cell value (column 4, 5 and 6)
  and each list-item value, with the outcome section 4 gives: safe text; raw
  `|`; source `\|`; `|` inside a code span; `\` and `|` apart and adjacent;
  `\\`; each angle form outside and inside a code span, in a link
  destination and in a URL; `[`, `://` and `www.` with and without an angle
  form; a plain code span; several complete code spans on several lines of
  one value and in several items of one cell; a code span across a line
  break, two adjacent backticks, an odd backtick count in a segment and a
  padded span; each rule U character, tab and U+0085 included, and an
  accepted line feed and carriage return; each marker, thematic break
  and task box, bare and followed by text, at the start of a structured text
  value and of a prose value, and nested after `- `, `* ` and `1. ` in prose;
  each other marker character (`-x`, `#1`, `*x*`, `_x_`, `~x`, `=x`) at the
  start of a structured text value and after an accepted prose prefix
  (refused), the accepted `1.5 s` and the accepted prose starts (`- x`,
  `* x`, `1. x`); an email address and a `$` with and without an angle form in prose;
  `*x*`, `R&D`, `?a=1&not=2&copy=3` in mid-text; and the newline forms of v0.9.1 section 10. Each refusal names its rule and path;
  each acceptance renders, passes through the corrected fake and reads back
  valid with an artifact equal to the emitted one;
- **oracle:** for each D1 and D2 class, the unguarded pipeline (every
  write-time stored-form check off, write through the corrected fake,
  unchanged reader) refuses the output after its writes, with
  `ARTIFACT_MALFORMED` for a prose `|`, `ARCHITECTURE_RENDER_INVALID` for a
  list-item `|`, and `ARCHITECTURE_RENDER_INVALID` for D2 as a complete
  Document (a span `<` and a decoded `<` in another section, and in the same
  value), while rules P and C refuse it before any write;
- **order:** a value refused by an earlier rule (S, X, the render, v0.9, T,
  R) keeps that refusal; among U, K, P, C and L the first in section 4 order is
  named; the refusal is deterministic;
- **evidence:** the corrected fake reproduces all twelve Gate 3N17 files and
  all ten Gate 3N21 files byte for byte; the unchanged reader classifies each
  stored Document as live did (`L2-composite`, `L4-T-table`, `L4-T-lists` and
  `L5-refs` refused, `L2-codespan` valid); v0.9.2 refuses `L2-composite` (rule
  P1), `L2-codespan` (rule C) and every case live refused, and accepts
  `L2-valid`, `L3-M1-exact` and `L3-M1-alone`; a table-cell `|` is accepted;
- **negative controls:** the v0.9.1 fake fails on `L2-composite`,
  `L2-codespan`, `L4-T-table`, `L4-T-lists` and `L5-refs`; a fake that decodes
  inside code spans fails on `L2-codespan`;
- **lifecycle:** an output refused by each of U, K, P, C and L on `start` makes
  no Architect-stage write and no Reviewer call; on REWORK the Human Decision
  is kept, no Process Result is written and the previous Architecture is
  unchanged; nothing is retried; a later `resume` calls the Architect once; a
  valid start and a valid REWORK complete; the replay of a recorded output
  never runs rules U, K, P, C or L;
- **historical:** the v0.7 and v0.8 evidence Documents validate and their
  outputs, and every TSA-01–TSA-04 Process Result output available to the
  implementation gate, pass rules U, K, P, C and L; the `arp1-tsa-04`
  Architecture stays refused; every v0.9 and v0.9.1 test passes, corrected
  only as section 7 lists;
- **prompt:** the start and REWORK prompts carry the section 6 items
  verbatim after the v0.9.1 items;
- **probe harness:** the section 10 stop rule, through an injected in-memory
  workspace;
- the full suite, `ruff check` and `ruff format --check` on changed files.

## 9. Historical compatibility and limits

**SPEC.** No persisted Document changes and the reader is unchanged, so every
Document that validates today validates after this delta. No TSA-01–TSA-04
Process Result or v0.7/v0.8 evidence output holds a value rules U, K, P, C or
L would refuse. The `arp1-tsa-04` Architecture stays refused (contract 14.3 case
8); recovery remains a new cycle.

**SPEC — limits.** Not observed and not claimed, and covered by section 11
W3: the stored form, in each of prose, table cell and list item, of `!`, `#`,
`$`, `@`, `[`, `]`, `^`, `~` and a lone `*` in mid-text, and of `%` in a cell
and an item (`%` and `_` in prose were stored unchanged in the v0.7 pilot); of
a value beginning with a digit that is not a marker, such as `1.5 s`, with
`[` such as `[^1]: note`, or ending with `\`; of a prose value beginning
`* `; of a
link, an image, a reference definition, a bare URL, a `www.` address and an
email address (without an angle form); of `**x**`, `__x__`, `_x_`, `~~x~~`, `$x$`, `@name`, `#tag` and
`[[x]]`; of U+00A0, U+200B, U+FEFF, `é` and U+1F600 (the normalized `intended_output`
is in NFC form before any rule); of a table cell beginning or ending with `|` or
holding `||`; of a backslash inside a code span and `\*x*`; and of a line
break followed directly by `- `, `# `, `1) ` or `+ ` inside a list item.
Rules U, K, P2, C's link and URL clause and L are conservative: they refuse
forms whose stored form is unobserved, by the mechanisms of section 2
(context-dependent pipe escaping, entities kept in non-text inline nodes,
escaping of a paragraph-leading marker, block-marker re-serialization). D2 is
derived, not live-verified, until W2 of section 11.

## 10. Live probe stop rule

**SPEC.** Gate 3N21's probe continued after its first read-back failure
because it recorded each outcome without comparing it with an expected one.
A probe that writes Architecture carriers to Fibery for this specification
MUST:

- declare, before any write, for every case: the expected guard outcome
  (accept, or the refusing rule), whether it is written, the expected stored
  form (the corrected fake of its emitted Document), the expected reader
  outcome (valid, or the refusal code) and, for an accepted case, that the
  read-back artifact equals the emitted one;
- process cases in their declared order and, after each case, compare every
  declared expectation, a reader refusal being an outcome to compare and not
  a failure of the probe; on the first difference, or on any unexpected
  exception, record the observation, mark every later case `NOT RUN`, and
  make no further create, write or read for a later case;
- never retry, delete or clean up;
- report the writes made, the cases not run and the persistent Document ids;
- take its workspace as a parameter, so a test can drive it with the
  in-memory workspace and a deliberately wrong stored form, and assert that a
  difference in case 1 leaves exactly one create, one write and every later
  case `NOT RUN`, and that a declared reader refusal that occurs does not
  stop the run.

The stop rule is part of the probe, not of production code.

## 11. Verification state

**SPEC.** Required before an Architecture cycle relies on v0.9, v0.9.1 and
this delta: section 8 offline, an independent implementation review, and, on
the scratch Project `27` under separate authorization, one probe run under
section 10 that writes through the implementation of this delta and the
production adapter, in this order:

1. **W2, D2 direct:** the D2 Document of section 8 (a prose code span holding
   `<` and a decoded `<` in another section), refused by rule C and written
   with the write-time checks off. Expected: stored form equal to the
   corrected fake, reader refusal `ARCHITECTURE_RENDER_INVALID`.
2. **W1, accepted composite of observed forms:** one output accepted by
   v0.9.2 holding the v0.9.1 newline forms in every structured text value; a
   `|` inside the text of a table cell; a plain code span, a `\`, `*x*`,
   `R&D` and `?a=1&not=2&copy=3` in prose, a cell and an item, none at the
   start of a value; a prose value
   with a code span and a decoded `<` outside every code span; and the
   M1 exact values. Expected: read back valid, stored form equal to the
   corrected fake, artifact equal to the emitted one.
3. **W3, unobserved constructs:** one output accepted by v0.9.2 holding each
   construct of section 9's limit list in prose, a table cell and a list
   item, each where v0.9.2 accepts it (no marker at the start of a value), with every link, image and reference target under
   `https://example.invalid/` and every mention, tag and wiki-link naming no
   existing entity. Expected: read back valid, stored form equal to the
   corrected fake, artifact equal to the emitted one.

At most three creates and three writes. D1 and the refused classes of rules
T, R and P1 are not written again. If any expectation differs, the probe stops
under section 10. A difference in W2 or W1 requires a further delta before
reliance; a difference confined to W3 constructs requires a further delta that
refuses or models them. Until all three pass, live behaviour is UNVERIFIED and
v0.9.2 is not cleared for integration.
