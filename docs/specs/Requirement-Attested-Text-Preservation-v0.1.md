# Requirement Attested-Text Preservation — v0.1 (delta)

**Status:** IMPLEMENTED ON BRANCH `fix/attested-normalization-preservation`; NOT LIVE-VERIFIED; independent engineering review pending.
**Authorization:** human instruction "SDLC Gate 3L4 — Enforce Verbatim Preservation of Operator-Attested Normative Text", for baseline `6e93d554fb7d8973e7f0b5f742cf8c584fc3ea77`. The approval record is that instruction; no signature is claimed.
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

For each protected text, compare the Root Document as this run read it (the input) with the Root the normalized output renders (the output), section by section (`## ` headings; text before the first one counts as one more section). In every section, the output must hold the text:

1. **character for character**: no rewording, re-punctuation, split, merge, shortening or extension, however equivalent in meaning;
2. **as many times as the input does**: not deleted, not duplicated;
3. **in the same sections**: not moved;
4. **as a whole paragraph exactly where the input had it as one**: not merged into, or extended within, a paragraph.

A protected text the input does not contain must stay absent from the output. Process never inserts one, and a model that inserts one is refused. Text that is not protected is normalized as before.

The comparison is exact string equality on the input as Process reads it (the rendered Markdown, as for citations) and on the output sections as the model returned them. No model judges equality, nothing is normalized away first, and the model's account of what it kept is never read.

## 3. Where it is checked

| Point | Check | Refusal |
|---|---|---|
| Process | After the output is parsed, its citations bound and the authority rule checked; before the Process Result Document is created, its body stored, the Root rewritten or the State moved to Review. Applies to every model run: a new iteration, `--new-iteration-after`, and `--recover-empty-result`. | `INVALID_MODEL_OUTPUT`; nothing written |

The refusal details name the Requirement, each failing attestation by its fingerprint's first 12 hex digits, the affected section headings and one category:

- `ALTERED_OR_DELETED`: fewer exact occurrences than the input; it covers paraphrased, re-punctuated, shortened and deleted text alike, which code cannot tell apart;
- `DUPLICATED`: more exact occurrences than the input;
- `MOVED`: the same number, in other sections;
- `PARAGRAPH_CHANGED`: the same occurrences, but no longer a whole paragraph where it was one;
- `INSERTED`: present in the output, absent from the input.

Neither the attested text nor the model output appears in the diagnostics.

**Prompt.** The Standard Process instruction now says that an attested text in the current document is a human decision to reproduce verbatim, in place, as often as it occurs and as its own paragraph where it is one, and that none may be added. The prompt only helps prevent violations; the code check decides.

## 4. What does not change

- The authority rule, its refusals and its staleness (Human Attestation §4, §5) are unchanged. A material answer citing attested text still passes, and one citing unattested text is still refused, whether or not the text is preserved.
- SOURCE_GROUNDED and DEPENDENCY_GROUNDED source-kind rules, citation binding, Rework Brief obligations and lineage are unchanged.
- No Result schema, field, State, configuration key or attestation changes. Persisted Process Results are never re-checked, rewritten or re-certified, and all of them stay readable.
- Preservation never promotes text to human authority. Only an attestation in the configuration attests.
- Child documents of the normative tree are not rewritten by Process, so they are outside this check.

## 5. Not covered

- **`--resume-result`** replays persisted output without a model call. That output was produced, and checked, when it was persisted, so it carries no new check. A Result persisted before this rule replays as it was.
- **Existing paraphrases.** An attested text that an earlier iteration already paraphrased is absent from the current input, so it is not protected (§2). Process will not restore it. Restoring it is an operator edit of the Root, followed by a new iteration.
- **Review, Ready, Apply and TSA admission** add no preservation check. The persisted evidence does not keep the input Root's content, so a later stage cannot recompute what the input held. A Review of an output persisted before this rule judges it as before.
- **Root edits outside Process**: anything that edits the Root directly is outside this rule, as for Human Attestation §2.

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
- **If the restored tree equals that Result's input exactly**, Process refuses with `PROCESSING_STATE_CONFLICT`. Only the existing admin option `normalize --new-iteration-after <id>` continues, and the dispatcher cannot pass it.

`Review -> Process` is not on the normal semantic path of Requirement-Lifecycle-Ownership-v0.2. Standard-Requirement-Process-Spec-v0.1 §11 acknowledges it as a deliberate human move, followed by an edit and a new run. Both the transition and the Root edit therefore need explicit operator authorization. This delta adds no recovery command and no lineage exception.

## 7. Non-goals

- No new Fibery database, field, State, relation type, configuration key or command.
- No repair of model output, and no automatic restoration of attested text.
- No equivalence weaker than exact strings.
- Nothing is live-verified.
