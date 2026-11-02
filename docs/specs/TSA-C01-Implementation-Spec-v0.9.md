# TSA-C01 — Implementation Specification v0.9 (delta to v0.3 + v0.4 + v0.5 + v0.6 + v0.7 + v0.8)

**Status:** FROZEN ON COMMIT; LIVE BEHAVIOUR UNVERIFIED (section 9).
**Human approval:** explicit operator approval in ARP1 Gate 3N14 of this exact
text, for repository snapshot `cb936688cd18d101b67f9dccbbd7d403cd4732ac`.
**Implementation authorization:** GRANTED ONLY FOR THE BOUNDED CORRECTION OF
SECTIONS 4–6, in a separately authorized implementation gate.
**Authority source:** `docs/architecture/TSA-C01-Contract-v0.2.md` (frozen),
unchanged.
**Base:** `docs/specs/TSA-C01-Implementation-Spec-v0.3.md`, `-v0.4.md`,
`-v0.5.md`, `-v0.6.md`, `-v0.7.md` and `-v0.8.md` (all frozen), unchanged.

The approval record is those instructions. No signature or authenticated
identity is claimed for them.

## 1. Relation to v0.3–v0.8

**SPEC.** This document is a **delta**. v0.3–v0.8 remain authoritative and
apply in full, except that the Architect response contract gains the one
write-time rule of section 4 and the Architect prompt gains the text of
section 6. Nothing else is restated, amended or replaced, and their files are
unchanged. In particular:

- canonical emission is unchanged: `render_architecture`, `escape_markdown`
  (v0.3 8.3.1), the table and the carrier produce the same bytes as before;
- the read path is unchanged: v0.7's table rule and v0.8's prose rule,
  `validate_architecture_document`, `document_fingerprint` and
  `canonical_markdown`;
- no result code is added, removed or re-meant; `INVALID_MODEL_OUTPUT` keeps
  its meaning (the Architect response does not satisfy its closed contract);
- no wire schema, artifact schema, digest, Input Manifest, Process Result,
  Review Result or Human Decision meaning, recovery case or durable lifecycle
  state changes;
- no persisted Document is migrated, rewritten, repaired or re-sealed.

## 2. The observed defect

**EVIDENCE.** In cycle `arp1-tsa-04` (2026-11-02), after Human Decision 0001
(REWORK), the iteration-2 Architect output was validated, Process Result 0002
was persisted, and the post-apply Architecture Document was written. Its
immediate read-back refused `ARTIFACT_MALFORMED`: "The envelope's
content_fingerprint is not the fingerprint of the sixteen sections it
accompanies." The model text held 201 literal `<br>` in prose sections and no
newline. 8.3.1 emitted `&lt;br&gt;`; Fibery stored `<br>`; the v0.8 read rule
keeps every literal `<br>` as the renderer's, so the canonical line differs
from the sealed one. `tests/architecture_fake.py::fibery_stored` maps both
emitted `arp1-tsa-04` Documents (iterations 1 and 2) onto the stored ones byte
for byte. This is the residual named in v0.8 sections 4 and 7.

**EVIDENCE (offline, fake-based).** A second class of the same defect: a
prose section whose text begins with a tag, an HTML comment or `>` is emitted
as an escaped paragraph, stored decoded, and refused by v0.8 section 4
condition 3 (`ARCHITECTURE_RENDER_INVALID`) — the "block position" residual
of v0.8 section 7. Pre-write validation accepts both classes today.

**SPEC.** The defect: the write path validates the emitted form, while the
read path validates the stored form, so the engine can persist a Document its
own read path must refuse — after both irreversible Architect-stage writes.

## 3. Invariant

**SPEC.** An Architect output is accepted only when every prose line of the
normative Markdown it renders, in its specified Fibery-stored form, is
accepted by the unchanged v0.8 read rule and maps back onto exactly the
emitted line. For a prose line the specified stored form is v0.8 rule E: each
`&lt;` becomes `<` and each `&gt;` becomes `>`, and nothing else changes.

## 4. Write-time stored-form check

**SPEC — placement.** `validate_architect_output` applies the check after its
trial render, to the normative Markdown that render produced (the bytes that
`content_fingerprint` seals and that are written). It applies only there: not
in `render_architecture`, `build_architecture_carrier`, the replay of a
recorded output, or any reader, so persisted Process Results and Documents are
read and replayed exactly as before.

**SPEC — predicate.** For every prose line `L` (v0.8 section 4: a non-blank
content line of headings 1, 3–13), let `S` be `L` with each `&lt;` replaced
by `<` and each `&gt;` by `>`. `L` is **storable** only when both hold:

1. the v0.8 canonical line of `S` equals `L`;
2. when `S` differs from `L`, the pinned parser's block-token types of `S`
   equal those of `L` and neither stream is incomplete (v0.8 section 4
   condition 3).

The check MUST call the production functions the reader uses for 1 and 2;
it MUST NOT re-implement them. It is pure and deterministic: same response,
same Manifest, same outcome.

**SPEC — refusal.** A response with any non-storable prose line is refused
`INVALID_MODEL_OUTPUT`, naming the section key of the first such line and
stating that its text would not survive storage. The text is not repaired,
normalized, re-requested or persisted. The read-time code of condition 2
(`ARCHITECTURE_RENDER_INVALID`) is not used for this refusal.

**INFORMATIVE.** Refused: a model `<br>`, a model `&lt;br&gt;`, any mixture
that leaves `&lt;br&gt;` after 8.3.1, and a section text that begins with a
tag, an HTML comment or `>`. Accepted exactly as today: newlines (one or
several), `<BR>`, `<br/>`, `<br >`, `&amp;`, model `&lt;x&gt;`, an inline
tag or `<result>` inside a line, a tag after a newline, `<5 ms`, and an
autolink.

## 5. Mutation boundary and failure

**SPEC.** Because the check is inside `validate_architect_output`, it
precedes the Process Result write — the first irreversible Architect-stage
write — and every Architecture write. Iteration 1 of `start` and every REWORK
iteration use the same case-1 Architect generation, so both are covered.

**SPEC.** When the check refuses:

- exactly one Architect model call was made; no Process Result is created;
- the Architecture Document is unchanged and keeps the previous valid content
  (the previous iteration's applied output, or the bootstrap content);
- the Input Manifest and every durable Human Decision, including a REWORK
  decision written by the same command, are unchanged;
- the Reviewer is not invoked;
- nothing is retried, re-requested, repaired or resumed automatically;
- the cycle is in case 1 for the current iteration (contract 14.3). A further
  Architect call is made only by a separately invoked `resume` under the
  existing lifecycle; no retry mechanism is added;
- the command reports `INVALID_MODEL_OUTPUT` with its existing exit class.
  When the same command durably wrote a REWORK decision first, the existing
  after-progress report states that decision and the refused continuation.
  No success code is reported.

## 6. Architect prompt

**SPEC.** The "Text rules for every string value" list of the Architect
instructions gains these two items, verbatim:

```text
- separate lines with a newline character (\n in JSON); never write <br>,
  &lt;br&gt; or any other markup for a line break. Where the previous
  Architecture Document shows <br>, that marks a line break; it is not text
  to copy;
- do not start a string value with "<" or ">".
```

**SPEC.** The prompt is guidance only; section 4 decides acceptance. The
prompt text is not part of any digest or fingerprint, so no recorded value
changes.

## 7. Existing Documents and recovery

**SPEC.** No repair or new read rule is added. A Document already written in
a refused form (the `arp1-tsa-04` Architecture) stays refused under contract
14.3 case 8 and v0.8; resume and inspect keep refusing it without a model call
or write. Such a cycle is left as incomplete history. The same Requirement
scope continues only under a new cycle id (contract 3.2, 12.1), with its own
admission, Input Manifest and human acceptance.

## 8. Limits

**SPEC.** Model text in the section 2 table cells and in the generated list
items of sections 14–16 is not checked by section 4. Its Fibery-stored form
when it holds `<`, `>` or `<br>` has not been observed: `fibery_stored`
keeps it, and v0.7/v0.8 refuse a decoded one. The live verification of
section 9 MUST observe it before an Architecture cycle relies on v0.9; if
Fibery decodes it, a further delta is required first. v0.8 section 7's
residual on the inline raw-HTML rendering of accepted prose is unchanged.

## 9. Verification state

**SPEC.** Required before an Architecture cycle relies on this delta:

- offline: the check refuses each case in section 4's refused list and
  accepts each case in its accepted list; refusal writes nothing on `start`
  and on REWORK, keeps the Human Decision and calls no Reviewer; a later
  `resume` calls the Architect once; historical Documents (v0.7 and v0.8
  evidence, `arp1-tsa-04` iteration 1) still validate, and the
  `arp1-tsa-04` iteration-2 Document is still refused; the full suite stays
  green;
- live, on a temporary non-pilot cycle under separate authorization: a refused
  output makes no Fibery mutation; an accepted output with newlines and
  inline `<result>` is written, read back valid, and its stored form equals
  `fibery_stored`; and a table cell and a list item holding `<`, `>` and
  `<br>` are written and their stored form is recorded (section 8).

Until the live part is done, live behaviour is UNVERIFIED.
