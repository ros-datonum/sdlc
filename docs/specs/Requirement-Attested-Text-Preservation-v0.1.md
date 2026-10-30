# Requirement Attested-Text Preservation — v0.1 (delta)

**Status:** IMPLEMENTED ON BRANCH `fix/attested-normalization-preservation`; NOT LIVE-VERIFIED. Gate 3L5 independent review returned FIX_REQUIRED (F01–F06), corrected under Gate 3L6. Gate 3L7 returned FIX_REQUIRED (G7-01–G7-03 in scope), corrected under Gate 3L8. Re-review pending.
**Authorization:** human instructions "SDLC Gate 3L4 — Enforce Verbatim Preservation of Operator-Attested Normative Text", for baseline `6e93d554fb7d8973e7f0b5f742cf8c584fc3ea77`, "SDLC Gate 3L6 — Correct Independent Review Findings F01–F06", and "SDLC Gate 3L8 — Correct Remaining Attested-Text Structural Bypasses". The approval record is those instructions; no signature is claimed.
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
- its **kind**: the leaf block with the quotes and lists around it (for example `paragraph`, `fence`, `code_block`, `html_block`, `blockquote/paragraph`, `bullet_list/list_item/paragraph`, `blockquote/blockquote/paragraph`);
- whether the occurrence **covers it whole**: all of the block's text, ignoring only spaces and tabs around it.

A text inside one paragraph has one component; a text of two paragraphs has two, compared one by one and in order. Turning only one of them into a quote, a list item or code changes that component, so it is a change even where the characters are all still there. An occurrence that touches no block (only blank space) has one component of kind `outside blocks`.

The output must have the same placements, the same number of times, as the input. That means it holds the text:

1. **character for character**: no rewording, re-punctuation, split, merge, shortening or extension, however equivalent in meaning;
2. **as many times as the input does**: not deleted, not duplicated;
3. **in the same sections**: not moved;
4. **in the same blocks**: each component block of the same kind, in the same order, covered whole exactly where the input's was. It may not be merged into, extended within or split across paragraphs, and no component may move into or out of code, a quote, a list or an HTML block, or change its nesting.

A protected text the input does not contain must stay absent from the output. Process never inserts one, and a model that inserts one is refused. Text that is not protected is normalized as before.

### 2.1 How the documents are read

- **Characters.** Occurrences are found by exact string search on each document exactly as read: the input as Fibery returned it (the rendered Markdown, as for citations), and the output as the Root it renders to, from the sections the model returned. Nothing is normalized first: line endings (CR LF, CR, LF), U+2028, U+2029, Unicode composition, backslashes and Markdown escapes all count as written. No model or similarity measure judges equality.
- **One structural reading.** Each document is parsed once, with the pinned CommonMark parser the TSA code-block rule already uses (`markdown-it-py`, preset `commonmark`, through that rule's completeness guard, `tsa_markdown.block_tokens`). That one token stream gives both the sections and the blocks. The parser is used only to find where blocks begin and end. Those line positions are mapped onto offsets in the untouched document, splitting lines only where the parser does (CR LF, CR, LF). It is never the text the comparison reads.
- **Sections are the schema's, or unestablished.** A document's sections are established only when all of these hold:
  - the top-level level-1 and level-2 headings the parser reads are, after at most one leading level-1 title, exactly the seven Standard section headings, in schema order;
  - each of them is written exactly as the Standard renderer writes it (`## Constraints & Edge Cases`), not as a setext heading or with other spacing or closing hashes;
  - no other line of the document, in code or anywhere else, is a copy of one of those seven lines.

  A section is then identified by its schema heading, which is unique, so a repeated, unknown, misspelled or reordered heading can never collide with or stand in for one. A heading inside fenced or indented code, a quote or a list opens no section. Level-3 and deeper headings are content.
- **Why the copy rule.** The Standard field validator reads each returned section on its own, with its own backtick-fence grammar (`raw_source.FENCED_BLOCK_PATTERN`). It hides a heading inside a fence opener that CommonMark rejects (```` ```bad`info ````). It also passes a section that ends in an unclosed fence, which then swallows the next real heading in the rendered document. In both cases the two readers can disagree about which line opens a section. The two readers place the seven sections alike only where each heading line is unique and the parser confirms it, and that is what the rule requires. A copy of a heading line even inside a well-formed fence is therefore refused, conservatively, when protected text is involved. The field validator is unchanged.
- **Paragraph boundaries.** These are CommonMark's: a line holding only spaces or tabs is a blank line and ends a paragraph, and a line with no blank line before it continues one.
- **Unestablished structure.** Every protected text that occurs in either document is refused, with nothing written:
  - `STRUCTURE_UNREADABLE` when either document cannot be read: the parser raises (its message is dropped), its completeness guard says a block may have been skipped (for example quotes nested past its limit), or it reports a line the document does not have;
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
- `SECTIONS_AMBIGUOUS`: either document's sections are not exactly the seven schema sections, each opened by its one heading line (§2.1).

`PARAGRAPH_CHANGED` also covers a change to any one component block of a multi-block text: its kind, its nesting, its order or whether it is covered whole.

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
- **Copies of heading lines.** A protected Requirement whose Root or output carries a copy of a schema heading line anywhere (for example quoted inside a code sample) is refused as `SECTIONS_AMBIGUOUS` until the copy is removed (§2.1). This is deliberate: the alternative is trusting one of two readers that disagree.

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
