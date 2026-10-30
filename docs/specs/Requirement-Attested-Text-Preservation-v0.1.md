# Requirement Attested-Text Preservation — v0.1 (delta)

**Status:** IMPLEMENTED ON BRANCH `fix/attested-normalization-preservation`; NOT LIVE-VERIFIED. Gate 3L5 independent review returned FIX_REQUIRED (F01–F06), corrected under Gate 3L6. Gate 3L7 returned FIX_REQUIRED (G7-01–G7-03 in scope), corrected under Gate 3L8. The next independent review returned FIX_REQUIRED (G9-01, G9-02), corrected under Gate 3M1. Re-review pending.
**Authorization:** human instructions "SDLC Gate 3L4 — Enforce Verbatim Preservation of Operator-Attested Normative Text", for baseline `6e93d554fb7d8973e7f0b5f742cf8c584fc3ea77`, "SDLC Gate 3L6 — Correct Independent Review Findings F01–F06", "SDLC Gate 3L8 — Correct Remaining Attested-Text Structural Bypasses", and "SDLC Gate 3M1 — Close Final Structural Preservation Review Findings". The approval record is those instructions; no signature is claimed.
**Amends, narrowly and only as stated here:**
- Standard-Requirement-Process-Spec-v0.1, its normalization contract: what the normalized output must keep;
- Requirement-Human-Attestation-v0.1 §5, by adding one Process check beside the authority check.

Those documents are unchanged on disk. Where this delta and they disagree, this delta governs for the listed points only. The attestation format, its identity, the authority rule (Human Attestation §4), Review, Ready, Apply and TSA admission are unchanged.

## 1. The defect

Human Attestation v0.1 settles *who decided* a text: a material Brief item may be answered from this Requirement's own text only by quoting an operator attestation. It never said that the decided text must survive normalization.

ARP1 Gate 3L3 met the gap live. ARP1-FR-0129's Root held the attested D6-A paragraph verbatim, and Process 4 split its last sentence ("…segments, does not permit…" became "…segments. It does not permit…"). Process 4's output passed every check, so the Root now carried a model paraphrase of a human decision, with nothing to show it.

Proving authority and preserving text are two different controls. This delta adds the second.

## 2. The rule

Let the **protected texts** of a Process run be the attestations of exactly this Requirement: entity id and Requirement ID both match, as in Human Attestation §3. An attestation of another Requirement protects nothing here and authorizes nothing here.

For each protected text, compare the Root Document as this run read it (the **input**) with the Root that is about to be written (the **output**). Every occurrence of the text is located, overlapping occurrences included (in `x ababa y`, `aba` occurs twice). Each occurrence has a **placement**: the sequence, in document order, of every block the occurrence touches. For each of those **component blocks** it records:

- its **section**: the schema section it lies in (§2.1), or the part before the first one;
- its **kind**: the leaf block with the quotes and lists around it (for example `paragraph`, `hr`, `fence`, `code_block`, `html_block`, `blockquote/paragraph`, `bullet_list/list_item/hr`, `blockquote/blockquote/paragraph`);
- whether the occurrence **covers it whole**: all of the block's text, ignoring only spaces and tabs around it.

A text inside one paragraph has one component; a text of two paragraphs has two, compared one by one and in order. Turning only one of them into a quote, a list item or code changes that component, so it is a change even where the characters are all still there. An occurrence that touches no block (only blank space) has one component of kind `outside blocks`.

**Every component is placed.** Each block token the pinned parser emits is one of a known, closed set: the leaf blocks `paragraph`, `heading`, `fence`, `code_block`, `html_block` and `hr` (a thematic break); the containers `blockquote`, `bullet_list`, `ordered_list` and `list_item`; and the parts that only close a leaf or carry its inline text. A token of any other type, or a block whose lines cannot be mapped, leaves the document's structure unread (`STRUCTURE_UNREADABLE`): no component is ever dropped because its type is not listed. A nonblank line that no leaf block holds (a quote marker on a line of its own, an empty list item, a link reference definition, which the parser consumes without a token) is a component of kind `line in no block`, inside the innermost container around it. Every nonblank character of a document therefore lies in exactly one component. So a thematic break that moves into a quote, a list item or code, or a reference definition that moves into a quote, is a changed component even though every character is still there.

The output must have the same placements, the same number of times, as the input. That means it holds the text:

1. **character for character**: no rewording, re-punctuation, split, merge, shortening or extension, however equivalent in meaning;
2. **as many times as the input does**: not deleted, not duplicated;
3. **in the same sections**: not moved;
4. **in the same blocks**: each component block of the same kind, in the same order, covered whole exactly where the input's was. It may not be merged into, extended within or split across paragraphs, and no component (a paragraph, a thematic break or any other) may move into or out of code, a quote, a list or an HTML block, or change its nesting.

A protected text the input does not contain must stay absent from the output. Process never inserts one, and a model that inserts one is refused. Text that is not protected is normalized as before.

### 2.1 How the documents are read

- **Characters.** Occurrences are found by exact string search on each document exactly as read: the input as Fibery returned it (the rendered Markdown, as for citations), and the output as the Root it renders to, from the sections the model returned. Nothing is normalized first: line endings (CR LF, CR, LF), U+2028, U+2029, Unicode composition, backslashes and Markdown escapes all count as written. No model or similarity measure judges equality.
- **One structural reading.** Each document is parsed once, with the pinned CommonMark parser the TSA code-block rule already uses (`markdown-it-py`, preset `commonmark`, through that rule's completeness guard, `tsa_markdown.block_tokens`). That one token stream gives both the sections and the blocks. The parser is used only to find where blocks begin and end. Those line positions are mapped onto offsets in the untouched document, splitting lines only where the parser does (CR LF, CR, LF). It is never the text the comparison reads.
- **Sections are the schema's, or unestablished.** A document's sections are established only when all of these hold:
  - the top-level level-1 and level-2 headings the parser reads are, after at most one leading level-1 title, exactly the seven Standard section headings, in schema order;
  - each of them is written exactly as the Standard renderer writes it (`## Constraints & Edge Cases`), not as a setext heading or with other spacing or closing hashes;
  - the **two readers agree**: those parser headings are on exactly the lines the Document Schema reads as level-1 or level-2 headings (Standard-Requirement-Document-Schema-v0.1 §5: an ATX heading line outside a fenced block, where a fenced block is the backtick grammar `raw_source.FENCED_BLOCK_PATTERN` that decides document structure and that the field validator `reserved_heading` uses);
  - for the output, which code renders from the returned sections, each section opens on the line where the renderer wrote its heading.

  A section is then identified by its schema heading at a position both readers confirm, never by a display label that another line could repeat. So a repeated, unknown, misspelled or reordered heading can never collide with or stand in for one. A heading inside a quote or a list, or inside indented code, opens no section to either reader. Level-3 and deeper headings are content.
- **Supported fenced examples.** A properly closed backtick fence is literal example text to both readers, so a schema heading line quoted inside one (for example a Markdown example in Acceptance & Verification) is content, as the Document Schema already allows. Such a Requirement is processed, requalified and replayed normally, and its example may be kept, changed or dropped like any unattested text. (Gate 3L8 refused any copy of a heading line, even in such an example; Gate 3M1 replaced that blanket rule with the agreement rule above, which keeps the property the copy rule protected.)
- **Malformed and unclosed fences.** Where the readers disagree, nothing is trusted:
  - a fence opener CommonMark rejects (```` ```bad`info ````) hides a heading from the schema reading but not from the parser;
  - a fence the schema grammar opens but never closes (a four-backtick or malformed closing line) runs, for the schema reading, over the following headings;
  - a tilde fence or an HTML block hides a heading from the parser but not from the schema reading.

  Each of these is `SECTIONS_AMBIGUOUS`. The unclosed-fence case can also be built so that both readers agree: the field validator reads each returned section on its own, so a section ending in an open fence and a following section that closes it and then repeats the next heading both pass it. Reading the whole rendered document, both readers then put the real heading inside the fence and take the copy as the section. The renderer wrote the real heading elsewhere, so the rendered-position condition refuses it, also as `SECTIONS_AMBIGUOUS`. The input Root was not rendered by this run, so for it the two readers' agreement is the boundary. The field validator is unchanged.
- **Paragraph boundaries.** These are CommonMark's: a line holding only spaces or tabs is a blank line and ends a paragraph, and a line with no blank line before it continues one.
- **Unestablished structure.** Every protected text that occurs in either document is refused, with nothing written:
  - `STRUCTURE_UNREADABLE` when either document cannot be read: the parser raises (its message is dropped), its completeness guard says a block may have been skipped (for example quotes nested past its limit), it reports a line the document does not have, or it emits a block token outside the known set;
  - `SECTIONS_AMBIGUOUS` when either document's sections are not established as above.

  Nothing is parsed, and nothing changes, when no protected text occurs in either document.

## 3. Where it is checked

| Path | Check | Refusal |
|---|---|---|
| Fresh analysis: a new iteration, `--new-iteration-after`, `--recover-empty-result` | After the output is parsed, its citations bound and the authority rule checked; before the Process Result Document is created or filled, its body stored, the Root rewritten or the State moved to Review. | `INVALID_MODEL_OUTPUT`; nothing written |
| Replay: `--resume-result` | After the existing replay guards (latest Result, input matched and output not, unreviewed, bound Brief, bound policy); before the Root rewrite, the State move, or any other write. No model is run and the persisted Result is not changed. | `PROCESSING_STATE_CONFLICT`; nothing written |

These are the only three ways a Process Result reaches the Root rewrite. Fresh output passes through the analysis check, and a persisted Result reaches the rewrite only through replay.

A replay refusal uses `PROCESSING_STATE_CONFLICT` because no model ran: `INVALID_MODEL_OUTPUT` would misdescribe the operation. That code is also how this processor already refuses every other replay that would not be recovery (an iteration already reviewed, or a Brief that changed). The message says replaying is not recovery and names `--new-iteration-after <id>`, so the operator knows a fresh iteration is needed. No new result code is needed.

### 3.1 Diagnostics

For each failing attestation the details give:
- the attestation's fingerprint, first 12 hex digits;
- one category;
- the sections affected.

The fresh-analysis message names the normalized output; the replay message names the Result being replayed.

Sections are labelled with the schema's own headings (for example `Constraints & Edge Cases`), `before the first section` or `the whole document`. A document's own heading text is never echoed. Neither the attested text, the model output nor the Root content appears, so the details stay bounded by the number of attestations.

The categories:

- `ALTERED_OR_DELETED`: fewer exact occurrences than the input. This covers paraphrased, re-punctuated, shortened, split and deleted text alike, which code cannot tell apart.
- `DUPLICATED`: more exact occurrences than the input, counting overlapping ones.
- `MOVED`: the same number, but not in the same sections.
- `PARAGRAPH_CHANGED`: the same occurrences in the same sections, but in another kind of block, or no longer a whole paragraph where it was one.
- `INSERTED`: present in the output, absent from the input.
- `STRUCTURE_UNREADABLE`: either document's structure could not be read (§2.1).
- `SECTIONS_AMBIGUOUS`: either document's sections are not exactly the seven schema sections, or the two readers (or, for the output, the renderer) do not agree where they open (§2.1).

`PARAGRAPH_CHANGED` also covers a change to any one component block of a multi-block text: its kind, its nesting, its order, how many blocks it spans, or whether it is covered whole. `MOVED` compares the sections an occurrence lies in, each once and in order, so a change in how many blocks of one section it spans is `PARAGRAPH_CHANGED`, not `MOVED`.

**Prompt.** The Standard Process instruction says that an attested text in the current document is a human decision to reproduce verbatim, in place, as often as it occurs and as its own paragraph where it is one, and that none may be added. The prompt only helps prevent violations; the code check decides.

## 4. What does not change

- The authority rule, its refusals and its staleness (Human Attestation §4, §5) are unchanged. A material answer citing attested text still passes, and one citing unattested text is still refused, whether or not the text is preserved.
- SOURCE_GROUNDED and DEPENDENCY_GROUNDED source-kind rules, citation binding, Rework Brief obligations and lineage are unchanged.
- No Result schema, field, State, configuration key, result code or attestation changes. Persisted Process Results are never rewritten or re-certified, and all of them stay readable. One is re-checked only when `--resume-result` asks to apply it again (§3).
- Preservation never promotes text to human authority. Only an attestation in the configuration attests.
- Child documents of the normative tree are not rewritten by Process, so they are outside this check.

## 5. Not covered

- **Existing paraphrases.** An attested text that an earlier iteration already paraphrased is absent from the current input, so it is not protected (§2). Process will not restore it. Restoring it is an operator edit of the Root, followed by a new iteration.
- **Review, Ready, Apply and TSA admission** add no preservation check. The persisted evidence does not keep the input Root's content, so a later stage cannot recompute what the input held. A Review of an output persisted before this rule judges it as before.
- **Root edits outside Process**: anything that edits the Root directly, in Fibery or elsewhere, is outside this rule, as for Human Attestation §2. This Process-level guard does not prevent such edits; it only compares what Process itself writes with what it read.
- **Model-output headings in other refusals (Gate 3L7 G7-04, open).** The existing schema check that refuses a level-1 or level-2 heading inside a returned section quotes that heading line in its message. A heading line holding attested text is therefore echoed there. That check is older than this rule, is unchanged, and this delta does not fix it; it awaits a separate decision. The same check reads only backtick fences as literal, so a tilde-fenced section heading in returned output is refused there, before preservation is judged.
- **Fence forms the schema does not read as literal.** A Requirement whose Root quotes a schema heading line inside a tilde fence, a four-backtick fence or an HTML block is refused as `SECTIONS_AMBIGUOUS` when protected text is involved, because the two readers disagree about that line (§2.1). A properly closed backtick fence is the supported form. A returned section whose last line ends in a bare CR is counted by the renderer-position check as the parser counts it once rendered, which can join it with the next line ending; such output is refused rather than trusted.
- **Same refusal in both paths.** Fresh analysis and replay call the same comparison (§3); without an attestation of this Requirement in either document, nothing is parsed and behaviour is as before this rule.

## 6. Recovery from a Result persisted before this rule (offline-verified only)

A probe against the fake workspace, using the production dispatcher, processor and reviewer, gave these results for the durable state class ARP1-FR-0129 is in after Gate 3L3: Review / Not Processed; an unreviewed Process Result whose applied output paraphrased an attested paragraph; the latest Review older than that Result.

- **The State-driven route from there is Review.** The reviewer passed the paraphrased output; it has no preservation check (§5).
- **A deliberate `Review -> Process` with the Root unchanged** processes a new iteration. The paraphrase is not protected, so it can survive.
- **`Review -> Process` with only the attested paragraph restored verbatim**, when the earlier iteration also changed other text, gives a tree that is neither that Result's input nor its output. The dispatcher's ordinary route then runs a new iteration:
  - a paraphrase is refused (`INVALID_MODEL_OUTPUT`);
  - the exact text is processed;
  - the Rework Brief still comes from the latest Review;
  - the unreviewed Result stays unchanged history;
  - the next Review reviews the new iteration, and the Ready evidence is current.
- **If the restored tree equals that Result's input exactly**, Process refuses with `PROCESSING_STATE_CONFLICT`. Only the existing admin option `normalize --new-iteration-after <id>` continues, and the dispatcher cannot pass it. `--resume-result` of that Result is refused too when its output paraphrased the restored text (§3).

`Review -> Process` is not on the normal semantic path of Requirement-Lifecycle-Ownership-v0.2. Standard-Requirement-Process-Spec-v0.1 §11 acknowledges it as a deliberate human move, followed by an edit and a new run. Both the transition and the Root edit therefore need explicit operator authorization. This delta adds no recovery command and no lineage exception.

## 7. Non-goals

- No new Fibery database, field, State, relation type, configuration key or command.
- No repair of model output, and no automatic restoration of attested text.
- No equivalence weaker than exact strings.
- Nothing is live-verified.
