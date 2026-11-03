# TSA-C01 — Implementation Specification v0.9.1 (delta to v0.3 + v0.4 + v0.5 + v0.6 + v0.7 + v0.8 + v0.9)

**Status:** FROZEN ON COMMIT; LIVE BEHAVIOUR UNVERIFIED (section 10).
**Human approval:** explicit operator approval in ARP1 Gate 3N18 of this exact
text, for the v0.9 implementation snapshot
`041aa66ef2f76d420c5b8c24950e528168188205` (branch
`impl/tsa-c01-v09-stored-form-guard`, on specification commit
`72bb85895e516458bc11633d100fbedb0c589e74`).
**Implementation authorization:** GRANTED ONLY FOR THE BOUNDED CORRECTION OF
SECTIONS 4–8, in a separately authorized implementation gate.
**Authority source:** `docs/architecture/TSA-C01-Contract-v0.2.md` (frozen),
unchanged.
**Base:** `docs/specs/TSA-C01-Implementation-Spec-v0.3.md` to `-v0.9.md` (all
frozen), unchanged.

The approval record is those instructions. No signature or authenticated
identity is claimed for them.

## 1. Relation to v0.3–v0.9

**SPEC.** This document is a **delta**. v0.3–v0.9 remain authoritative and
apply in full, except that the Architect response contract gains the two
write-time rules of section 4, the Architect prompt gains the text of
section 6, and the test fake gains the correction of section 7. v0.9's prose
check (its section 4) still applies unchanged. In particular:

- canonical emission is unchanged: `render_architecture`, `escape_markdown`
  (v0.3 8.3.1), the table, the generated lists and the carrier produce the
  same bytes as before;
- the read path is unchanged: v0.7's table rule, v0.8's prose rule,
  `validate_architecture_document`, `document_fingerprint` and
  `canonical_markdown`;
- no result code is added, removed or re-meant; `INVALID_MODEL_OUTPUT` keeps
  its meaning;
- no wire schema, artifact schema, digest, Input Manifest, Process Result,
  Review Result or Human Decision meaning, recovery case or durable lifecycle
  state changes;
- no persisted Document is migrated, rewritten, repaired or re-sealed.

**SPEC — amendments to v0.9.** Rule R deliberately amends v0.9 section 4's
informative accepted list and the corresponding offline item of v0.9 section
9: `&amp;` in a prose value is now refused. The v0.9 test case that accepts it
moves to the refused set; it is not deleted. v0.9 section 8's limit for table
cells and generated list items is superseded by rule T, and the observation
v0.9 section 9 required for them was made in Gate 3N17 (section 2).

## 2. The observed defect

**EVIDENCE.** ARP1 Gate 3N17 (2026-11-03) wrote six synthetic Architecture
carriers, rendered by the v0.9 implementation from the repository's test
fixture, as Project-root Documents of the scratch Project `27` and read each
back once. Fibery decoded every `&lt;` and `&gt;` outside a fence in every
context: prose lines, prose lines that begin with a list marker (`- `, `* `,
`1. `), the generated list items of sections 14–16 and the section 2 table
cells. In a table row the renderer's own `<br>` became one space, while a
decoded model `&lt;br&gt;` stayed `<br>`. A `- ` line became `* `.

**EVIDENCE.** Two outputs that v0.9 accepts were refused on read-back with
`ARCHITECTURE_RENDER_INVALID`: one with `<`, `>`, `<br>` and `&lt;br&gt;` in
traceability cells, one with them in assumptions, risks and open architecture
questions. v0.7 and v0.8 refuse a decoded entity in a table cell or a
generated list item (v0.8 section 4). The defect class of v0.9 section 2
therefore remained open for these values.

**EVIDENCE.** A prose section that is itself a `- ` list line holding `<x>`,
beside another decoded prose line, was read back valid: Fibery decodes it as
v0.9 section 3 specifies. Its earlier offline failure came from the test
fake, which kept entities in `- ` lines, table rows and list items.

**EVIDENCE.** A literal `&` in text was stored unchanged in prose, a table
cell and a list item (v0.8 evidence). No live Document has held `&amp;`,
`&quot;`, a numeric character reference, a reference without `;`, an inline
code span, a `\`, a `\|`, emphasis markers, or a structured text value with
more than one newline in a row.

## 3. Affected model-authored values

**SPEC.** The **structured text values** are exactly these strings of the
normalized `intended_output`:

| Value | Rendered as |
|---|---|
| `traceability[i].how_satisfied` | section 2 table, column 4 |
| `traceability[i].constraints[j]` | section 2 table, column 5 |
| `traceability[i].gaps[j]` | section 2 table, column 6 |
| `assumptions[j]` | section 14 list item |
| `risks[j].detail` | section 15 list item |
| `open_architecture_questions[j]` | section 16 list item |

**SPEC.** Not structured text values: `traceability[i].requirement_id` and
`traceability[i].anchors[j]` (the existing coverage and anchor rules already
restrict them to selected Requirement ids and `tsa-s01`–`tsa-s16`),
`risks[j].impact` (an enum), and `product_questions` (not rendered outside the
fenced envelope, which Fibery stores verbatim). Renderer-owned text — headings,
the Source column, the `<br>` that joins the items of one cell, the
`— Impact:` suffix and `None identified.` — is not model-authored and is not
checked by section 4.

**SPEC.** The **prose values** are the twelve `sections` strings (v0.9
section 4).

## 4. Write-time rules

**SPEC — rule T (structured text).** A structured text value is refused when
it contains `<`, `>`, `&lt;` or `&gt;`. After 8.3.1 escaping, such a value is
exactly one whose rendered cell or item holds `&lt;` or `&gt;`, which Fibery
decodes and the unchanged reader refuses. A newline in a structured text value
stays allowed. In a table cell a single newline between non-space text renders
as the renderer's `<br>`, the same bytes as the item separator, which was
observed stored as one space and read back valid. Every other newline form
(two in a row, a newline followed by spaces, a newline in a list item) is
unobserved and is observed by section 10.

**SPEC — rule R (unverified character references).** A prose value or a
structured text value is refused when it contains a character reference other
than, in a prose value only, `&lt;` and `&gt;`. Case-sensitively, a character
reference is `&` followed by one of: `#` and 1–7 ASCII digits `0`–`9`; `#x` or
`#X` and 1–6 hexadecimal digits `0`–`9`, `a`–`f`, `A`–`F`; or an ASCII letter
(`A`–`Z`, `a`–`z`) and up to 31 further ASCII letters or digits; and then
`;`. The numeric forms are exactly CommonMark's; the named form is a superset of
CommonMark's named references, which decode only valid HTML5 entity names. It is conservative: their stored form is unobserved
(section 2), and a decoded one would be refused on read-back. A `&` that does
not begin such a reference, including a reference-like form without `;`, stays
allowed.

**SPEC — placement and order.** `validate_architect_output` applies rule T and
then rule R after its trial render and after the v0.9 prose check, so every
earlier refusal keeps its own frozen code. Both rules read the normalized
`intended_output` values (the persisted form), not the rendered Markdown, so
renderer-owned markup is never judged. The visit order is: `sections` in
heading order, then each traceability row in `requirement_id` order
(`how_satisfied`, `constraints`, `gaps`), then `assumptions`, `risks` and
`open_architecture_questions`. Rule T is applied to every structured text
value in this order, and then rule R to every prose and structured text value
in this order. The check runs only there: not in
`render_architecture`, `build_architecture_carrier`, the replay of a recorded
output, or any reader.

**SPEC — refusal.** The first refused value refuses the whole response with
`INVALID_MODEL_OUTPUT`, naming the rule and the value by its path in the
normalized `intended_output` (for example `sections.solution_structure`,
`traceability[0].constraints[1]` together with that row's `requirement_id`,
`assumptions[2]` or `risks[0].detail`). The value is not repaired,
normalized, re-requested or persisted. Both rules are pure and deterministic.

**INFORMATIVE.** Refused by rule T: `limit < 8000`, `a<br>b`, `&lt;br&gt;`,
`x > y`, `a -> b` in any structured text value. Refused by rule R:
`Tom &amp; Jerry`, `&quot;q&quot;`, `&#60;`, `&#x3C;` in any prose or
structured text value. Accepted: a newline in any value; `R&D`, `A & B`,
`?a=1&not=2`; `less than 8000`; in prose, everything v0.9 accepts except a
character reference other than `&lt;` and `&gt;`.

## 5. Mutation boundary and failure

**SPEC.** v0.9 section 5 applies unchanged to rules T and R: the check
precedes the Process Result write and every Architecture write, for
iteration 1 of `start` and for every REWORK iteration; on refusal one
Architect call was made, nothing is written, the Architecture keeps its
previous valid content, the Input Manifest and every durable Human Decision
are unchanged, the Reviewer is not invoked, nothing is retried, and a further
Architect call is made only by a separately invoked `resume`.

## 6. Architect prompt

**SPEC.** The "Text rules for every string value" list of the Architect
instructions gains these two items after the two items of v0.9 section 6,
verbatim:

```text
- in traceability, assumptions, risks and open_architecture_questions,
  never write the characters "<" or ">" (including arrows such as -> or
  =>), an HTML tag or <br>; write "less than", "greater than" or "to"
  instead;
- never write a character reference such as &amp;, &lt;, &quot; or &#60;;
  write the plain character, except where the rule above forbids it.
```

**SPEC.** The prompt is guidance only; section 4 and v0.9 section 4 decide
acceptance. The prompt text is not part of any digest or fingerprint.

## 7. Test fake correction

**SPEC.** `tests/architecture_fake.py::fibery_stored` MUST reproduce the
observed stored form and nothing more. Outside a fence:

- a table row: each literal `<br>` becomes one space, **then** each `&lt;`
  becomes `<` and each `&gt;` becomes `>`;
- a line beginning `- `: it becomes `* `, then `&lt;` and `&gt;` are decoded;
- every other line: `&lt;` and `&gt;` are decoded;
- separator spacing, the blank line before a fence and the dropped final
  newline are unchanged.

No other character reference is decoded by the fake (unobserved). Decoding
inside an inline code span is unobserved; a test that relies on it records an
assumption that section 10 must confirm.

**SPEC — evidence.** Exactly these twelve files of Gate 3N17 (synthetic
fixture content and identity only) MUST be committed byte for byte, with no
final newline added, as `docs/specs/TSA-C01-v0.9.1-evidence/`: the
`*.emitted.md` and `*.stored.md` of `L2-valid`, `L3-table`, `L3-lists`,
`L3-M1-exact`, `L3-M1-alone` and `L3-marker-div`, each pinned to the sha256
its probe recorded. The `*.predicted.md` files, the `L1` case and the probe's
`evidence.json` (which holds real Fibery ids) are not committed. A test checks
that `fibery_stored` maps each emitted Document onto its stored one byte for
byte. Every existing test whose expectation depended on the old fake behaviour
is corrected to the observed behaviour; none is deleted to make the suite
pass, and no production rule is added to match an old fake result.

## 8. Required tests

**SPEC.** Offline, through the production functions and the corrected fake:

- rule T: each structured text value × {`<`, `>`, `&lt;`, `&gt;`, `<br>`,
  `&lt;br&gt;`} is refused `INVALID_MODEL_OUTPUT` naming its path, and the
  unguarded pipeline (rules off, write through the corrected fake, unchanged
  reader) refuses the same output after its writes;
- rule R: `&amp;`, `&quot;`, `&#60;` and `&#x3C;` are refused in a prose value
  and in a structured text value; `R&D`, `A & B` and `?a=1&not=2` are
  accepted;
- accepted controls: newlines in every structured text value, multiple items
  per cell, `less than`, and every v0.9 accepted prose case except `&amp;`
  read back valid through the corrected fake;
- the Gate 3N17 evidence: the corrected fake reproduces all six stored
  Documents; `L2-valid`, `L3-M1-exact` and `L3-M1-alone` validate, and
  `L3-table`, `L3-lists` and `L3-marker-div` are refused with
  `ARCHITECTURE_RENDER_INVALID`, as live;
- lifecycle: an unsafe structured value on `start` makes no write and no
  Reviewer call; on REWORK the Human Decision is kept and nothing else is
  written; a later `resume` calls the Architect once; a valid start and a
  valid REWORK complete; the replay of a recorded output never runs the rules;
- the accepted Document of section 10, run offline through the corrected fake
  and the reader before the live run, so its prediction exists; and `&LT;` is
  refused in a prose value (case-sensitivity);
- historical: the v0.7 and v0.8 evidence Documents and every other accepted
  v0.9 case still validate; the prompt carries the section 6 items verbatim;
- the full suite, `ruff check` and `ruff format --check` on changed files.

## 9. Historical compatibility and limits

**SPEC.** No persisted Document changes and the reader is unchanged, so every
Document that validates today validates after this delta. No TSA-01–TSA-04
Process Result or v0.7/v0.8 evidence output holds a value rules T or R would
refuse. The `arp1-tsa-04` Architecture stays refused (contract 14.3 case 8);
recovery remains a new cycle.

**SPEC — limits.** Not observed and not claimed: the stored form of `&amp;`,
`&quot;`, numeric and other named character references (refused by rule R
instead); of a reference-like form without `;` such as `&not` or `&copy`; of
an inline code span holding `<`, `>` or a character reference; of `\` (emitted
`\\`), `\|` and emphasis markers, in prose, table cells and list items; of a
structured text value with two newlines in a row, a newline followed by
spaces, or a newline in a list item; payload size (gate I-3). The guarantee
that a refusal makes no Fibery mutation is verified offline (the check is pure
and precedes every write); it was not exercised through a live `start`.

## 10. Verification state

**SPEC.** Required before an Architecture cycle relies on v0.9 and this
delta: section 8 offline, an independent implementation review, and, on the
scratch Project `27` under separate authorization, a live re-probe that
writes through the implementation of this delta and the production adapter:

- one output accepted by v0.9 and rules T and R holding, in every structured
  text value (table cells, and list items of sections 14–16 including a risk
  detail), a single newline, two consecutive newlines, and a newline followed
  by two spaces and `- `; and holding, in a prose line, a table cell and a
  list item, a code span (with `<` in prose, plain text elsewhere), a `\`, a
  `|`, `*x*`, `R&D` and `?a=1&not=2&copy=3`; read back valid, its stored form
  equal to the corrected fake;
- the M1 exact case and a `- ` prose line holding `<x>`, read back valid;
- one Document per refused class of section 8, written with the rules
  switched off, to record that the corrected fake predicts its stored form;
- one Document holding `&amp;`, `&quot;`, `&#60;`, `&#x3C;` and `&amp`
  without `;` in a prose line, a table cell and a list item, to record their
  stored form.

If an observation differs from the corrected fake, a further delta is required
before reliance; a difference confined to content rule R refuses requires
only a fake and evidence update. Until then, live behaviour is UNVERIFIED.
