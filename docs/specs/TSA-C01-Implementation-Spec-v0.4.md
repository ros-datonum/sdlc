# TSA-C01 — Implementation Specification v0.4 (delta to v0.3)

**Status:** FROZEN.
**Human approval:** explicit instruction approving the Rule S mechanism, the
refusal policy and the bounded I06 alignment below, given for repository
snapshot `6c5fe619bf8333e66994c1abb271f0bfaf0b0739`.
**Implementation authorization:** GRANTED ONLY FOR THE BOUNDED I06 ALIGNMENT DESCRIBED HERE.
**Authority source:** `docs/architecture/TSA-C01-Contract-v0.2.md` (frozen), unchanged.
**Base:** `docs/specs/TSA-C01-Implementation-Spec-v0.3.md` (frozen), unchanged.

The approval record is that instruction. No signature or authenticated
identity is claimed for it.

## 1. Relation to v0.3

This document is a **delta**. Implementation Spec v0.3 applies in full, except
for the additions in sections 2–7 below. Nothing in v0.3 is restated, amended or
replaced. In particular these stay exactly as v0.3 froze them:

- P1: the mapping `[124] → [92, 124]`, the four normative vectors and every
  other escaping, normalization and digest rule;
- Rule S and its CommonMark 0.31.2 reference, Rule X, the acceptance matrix
  E01–E14 and its outcomes;
- the stage boundaries: I07 checks each complete decoded string value before
  strip and escaping (`INVALID_MODEL_OUTPUT`), I06 checks the normative
  Markdown it forms and the normative Markdown of a handed-in Document
  (`ARCHITECTURE_RENDER_INVALID`), and the trailing envelope stays under I01;
- every other rule, result code, schema and work-item boundary of v0.3.

Contract v0.2 is unchanged. The files of v0.1, v0.2 and v0.3 are unchanged.

v0.3 left one decision open: how rule S is computed, to be chosen before the
code alignment. v0.4 makes that choice (section 2), states when a
classification counts as complete (section 3), and authorizes one bounded
alignment of I06 (section 6).

## 2. The selected mechanism for rule S

**SPEC.** Rule S is computed with **`markdown-it-py==4.2.0`**, a direct runtime
dependency pinned exactly. Its required transitive dependency `mdurl` is
recorded in `uv.lock` only, never as a direct dependency. No extra of the
package is installed.

**SPEC — configuration.**

- A **new** `MarkdownIt("commonmark")` is constructed for **each**
  classification. No parser instance or parser configuration is shared,
  cached or mutated.
- The `commonmark` preset is used as shipped: no plugin, no extra, no table
  extension, no linkify, no highlighting, no rule enabled or disabled.
- `maxNesting` stays at the preset's value, **20**. Neither it nor the
  interpreter's recursion limit is raised, and no other depth or size setting
  is added.
- Only `parse` is used. The parser never renders HTML, never re-serializes
  Markdown, and never takes over rendering, escaping, the traceability table,
  traceability agreement, fingerprints or I01 carrier parsing.

**SPEC — what is read.** The flat block-token stream that `parse` returns. A
**code block** is a token of type `fence` or `code_block`, at any `level`, so
blocks inside list items and block quotes are included. The `children` of
`inline` tokens are not read and do not stand in for the block-token stream.

**SPEC — input.** The text is passed whole, as received. It is not stripped,
re-indented, split or otherwise cleaned first, so indentation, line breaks and
container context reach the parser intact. The parser's own `normalize` core
rule (line endings, NUL) is part of the selected preset and not a
pre-cleaning step of this specification.

**Not permitted:** a separate CommonMark parser, vendoring or copying the
parser's source, patching the installed library, or any fallback to a weaker
detector when the parser cannot classify.

## 3. Completeness guard and refusal policy

**Problem.** In the pinned version, the block tokenizer stops reading a block
once its nesting level reaches `maxNesting` and skips the rest of that block
without any error (`markdown_it/parser_block.py`, `ParserBlock.tokenize`). A
code block below that point is then absent from the token stream. Absence of
code tokens alone is therefore not evidence that there is no code block.

**SPEC — the predicate.** After `parse`, and **before** any code token is
looked for, the classification checks the flat block-token stream returned by
`parse`:

```text
any(token.nesting == 1 and token.level >= maxNesting - 1 for token in tokens)
```

With `maxNesting = 20` that is an opening token at `level >= 19`. If the
predicate holds, the result is **UNCLASSIFIABLE**, never "no code block".

**Why it suffices, for the pinned version only.** The source-based assumption
is: the tokenizer skips content only when the state's level is at least
`maxNesting`, and the level rises only when an opening token (`nesting == 1`)
is pushed at the current level. A skip therefore requires an opening token at
level `maxNesting - 1` in the stream. Probes over nested quotes and lists
agree; they are examples, not a formal proof of CommonMark conformance.

**Conservative by design.** The predicate is an indicator that parsing may be
incomplete, not evidence that content was cut off or that it contains code.
Some deeply nested Documents without any code block are therefore refused.
That consequence is accepted. The boundary is the exact token condition above;
no count of lists, quotes or indentation is a norm of this specification.

**Re-verification.** Changing the parser version or its configuration voids
this assumption: the guard has to be re-checked against the new source before
the change is used. A dependency upgrade is not authorized by this document.

## 4. The local classifier

**SPEC.** One pure function, `classify_code_blocks(markdown: str)`, in
`src/sdlc/tsa_markdown.py`, returns exactly one of:

| Result | Meaning |
|---|---|
| `NO_CODE_BLOCK` | The classification completed and found no code block. Rule S holds for this text; nothing else is implied |
| `CODE_BLOCK` | The classification completed and found a code block; it carries the block's first line where the parser reports one |
| `UNCLASSIFIABLE` | The classification could not be completed; it carries a fixed reason: `NESTING_LIMIT` (the predicate of section 3 held) or `PARSER_ERROR` (constructing the parser or parsing raised) |

The order is fixed: construct a new parser; parse the complete text; check the
predicate; only then look for `fence` and `code_block`; return.

The function performs no IO, reads no clock, uses no randomness, does not
mutate its input and keeps no state.

**SPEC — parser errors.** An ordinary `Exception` raised while the parser is
constructed or while it parses becomes `UNCLASSIFIABLE` with reason
`PARSER_ERROR`. The catch covers that boundary only, never the renderer or the
rest of validation, and never `BaseException`, `KeyboardInterrupt` or
`SystemExit`. No exception text, input text or token is carried into the
result or any diagnostic. A parser error is never a pass, and no fallback
detector runs.

`UNCLASSIFIABLE` never reports that a code block was found.

**These results are internal.** None of them is a new result code, CLI code,
artifact field or lifecycle state. Each stage maps them onto its existing
frozen code (section 5).

## 5. Mapping by stage

**I06 (authorized by this document).** The classifier is applied separately to:

- the complete normative Markdown that `render` forms;
- the normative Markdown of a handed-in post-apply Document, separated from
  the trailing envelope by the existing carrier path after I01 has accepted
  the carrier.

The whole Document, envelope included, is never passed: the envelope is itself
the one permitted JSON fence (E14). The fingerprint region and I01's carrier,
schema and digest checks are unchanged.

| Classifier result | I06 outcome |
|---|---|
| `CODE_BLOCK` | `ARCHITECTURE_RENDER_INVALID`, stating that a code block is present |
| `UNCLASSIFIABLE` | `ARCHITECTURE_RENDER_INVALID`, stating that the block structure could not be classified, and why |
| `NO_CODE_BLOCK` | rule S holds; every other check of I06 still applies |

Rule X stays a separate check of each line, with backticks and tildes treated
alike. A violation of rule S **or** of rule X is sufficient for refusal. A
backtick or tilde inside a line is not refused by a blanket rule. The other
checks of I06 keep their own specific codes; they are not folded into this
one.

**I07 (not authorized here).** The future Architect stage reuses the same
classifier on each complete decoded string value of the raw response, before
strip and before `escape_markdown`, and maps `CODE_BLOCK` and `UNCLASSIFIABLE`
to `INVALID_MODEL_OUTPUT` (v0.3 section 9.2). No wiring, model call or
response pipeline is authorized by this document.

## 6. Bounded authorization

**Authorized:** the I06 alignment only, in these files:

- new: `src/sdlc/tsa_markdown.py`, `tests/test_tsa_markdown.py`;
- existing: `src/sdlc/tsa_architecture.py`, `tests/test_tsa_architecture.py`,
  `pyproject.toml`, `uv.lock`, `README.md`.

Within it: the classifier of section 4; its integration into I06 (section 5);
rule X made symmetric for backticks and tildes; tests; the dependency of
section 2; and a correction of the README statement about runtime
dependencies, stating the parser-only purpose of the new dependency.

The two policy-dependent controls named in v0.3 change from acceptance to the
block refusal: a closed tilde block in a handed-in Document, and a comment
marker inside such a block. The invariants established by findings F1–F5 and
unrelated coverage are kept.

**Not authorized:** I07 or any other work item; changes to I01–I05, adapters,
schemas, runtime, CLI, worker or settings; any dependency other than section 2,
or an upgrade of it; live Fibery, live model or worker runs; merge.

## 7. New acceptance boundary and no migration

The only acceptance change beyond v0.3 is the refusal of section 3: a
normative Markdown for which the predicate holds is refused by I06 with
`ARCHITECTURE_RENDER_INVALID`, whether or not it contains a code block.

A change of acceptance policy is not a change of wire schema. No persisted
Document is migrated or rewritten, no artifact is re-sealed, and no accepted
input is changed.
