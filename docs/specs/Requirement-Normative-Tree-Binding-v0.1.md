# Requirement Normative Tree Binding v0.1

**Status:** approved design contract for audit finding A5, with the decisions
recorded in section 13. Not yet implemented: nothing in this document changes
running code, persisted artifacts or the Fibery schema until implemented under
its own review.

## 1. The defect, as verified in the merged repository

The intended Requirement model is one directly associated Root Document plus
its normative child Documents, recursively. The implemented capabilities do
not share that model:

```text
Standard Process   reads the Root and its direct children only; grandchildren
                   are never read; children are sent to the model but no
                   binding to them is persisted (input_fingerprint and
                   output_fingerprint cover the Root alone)
Standard Review    reads the Root only; children never reach the reviewer
Ready APPROVE      compares the Root fingerprint, the Process iteration and
                   the Process output fingerprint
Apply              the same three bindings, plus "the set of direct child ids
                   did not change while the Root moved"
RAW Process        reads the whole tree recursively, excluding its own
                   Processing Result by a name suffix
```

Consequences:

- Root unchanged, a normative child edited after Review: every binding still
  matches, APPROVE certifies content nobody reviewed, Apply applies it.
- Process reasons over direct children that Review never sees, so a Review
  verdict can neither confirm nor reject what Process concluded from them.
- A child added, removed, replaced or re-parented after Review is invisible
  to APPROVE; Apply notices only a change in the direct-child id set, and
  only during the Root move.

A6 supplies peer Root Documents as comparison material; peer children are
outside its scope for the same reason.

The contract: one normative-tree reader used by every consumer, one
canonical snapshot of that tree, and that snapshot bound wherever the Root
fingerprint is bound today. The tree snapshot is additional to, never a
replacement for, each stage's Type, State, Revision and structure checks.

## 2. Normative scope and artifact exclusion

### 2.1 What is normative

For a Requirement:

```text
the single Document directly associated with the entity     the Root
every Document nested under the Root, at any depth            a normative child
```

except the process-control artifacts of section 2.2. Names carry no meaning
beyond the artifact contract: a child called "Review notes", "Process",
"Result" or anything else is normative content.

The same reader serves the target Requirement and every peer Requirement of
the A6 comparison context.

### 2.2 What is excluded, and by what rule

A child is a process-control artifact only when all of the following hold,
which is exactly the contract the artifacts are written under today:

```text
its name parses as   <Requirement ID> — Process Result NNNN
                  or <Requirement ID> — Review Result NNNN
                  or <Requirement ID> — Processing Result       (RAW only)
the parsed Requirement ID equals the owning Requirement's Requirement ID
it is a direct child of the Root
```

No substring test replaces this. The RAW processor's current
`endswith("Processing Result")` skip is replaced by the same rule.

Within an excluded artifact:

- a valid payload is history or evidence, never normative content;
- a malformed payload is an invalid artifact; the existing
  `INVALID_PROCESSING_RESULT`, `INVALID_PROCESS_RESULT` and
  `INVALID_REVIEW_RESULT` behaviour is unchanged;
- an empty A3 shell is neither normative content nor valid evidence. It is
  excluded from the snapshot and its presence alone does not change the
  snapshot; the A3 eligibility and recovery rules stay independently
  enforced (section 8).

### 2.3 Unsupported placement and conflicts

These situations are refused explicitly rather than guessed, with the
stage's `NORMATIVE_TREE_INVALID` (section 9) naming the Document id and name
in the details, and no model call or protected write follows:

```text
a direct child whose name parses as an artifact name of a DIFFERENT
Requirement ID
a Document whose name parses as this Requirement's artifact name but is not
a direct child of the Root
a Document nested below a process-control artifact
```

Ordinary content is never silently hidden because of where it sits; the
operator moves it, and the run is repeated. A Document nested under an
ordinary normative child is ordinary content at any depth.

### 2.4 Admission limits and traversal

The reader visits breadth-first from the Root, ordering siblings by
Document id, and keeps the set of visited ids. Initial application limits:

```text
maximum normative depth        16 parent edges from the Root (Root depth 0)
maximum normative Documents    100, including the Root
maximum tree text              400,000 Unicode code points, the sum over
                               included Documents of len(name) + len(body)
```

A Document id listed twice, a Document that is its own ancestor, a depth
beyond 16, a 101st Document or tree text beyond the bound refuses with
`NORMATIVE_TREE_INVALID`. Traversal that stopped at a limit is not a
snapshot and is never used as one; nothing is truncated, no model is
invoked, no protected mutation follows. These are early admission checks:
the A6 bound of 400,000 code points on the complete assembled model input
still applies afterwards and is never replaced by them. No per-model
capacity setting and no tokenizer are introduced.

No Fibery Field, relation or Database is added. Classification uses Document
name, Requirement identity and parentage only.

## 3. The normative snapshot

### 3.1 Manifest

One versioned, deterministic manifest of an observed tree:

```text
normative_tree_version   1
requirement_id           the Requirement ID
root_document_id         the Root's Document id
documents                one entry per included Document, sorted by
                         document_id:
  document_id
  parent_document_id     null for the Root, otherwise the parent's id
  name                   the Document name; it is sent to the model as
                         hierarchy context, so it is bound
  content_fingerprint    document_fingerprint(body), section 3.3
normative_tree_fingerprint
                         sha-256 over the canonical serialization of the
                         fields above: JSON with sorted keys, entries in
                         document_id order, no insignificant whitespace,
                         UTF-8
```

Excluded on purpose: Document secrets, Folder location, timestamps,
modification and presentation metadata, view metadata, Process and Review
artifact contents, and the shells of section 2.2. Because the Folder is
excluded, moving the same Root from `Requirements/Draft` to
`Requirements/Approved` does not change the snapshot. Because parent ids are
included, re-parenting changes it; because Document ids are included,
replacing a child with a new Document of identical content changes it;
because the Root id is included, replacing the Root changes it; because
names are included, renaming changes it.

### 3.2 What the snapshot detects and does not

Detected: Root replacement; child addition, removal, replacement; content
change at any depth; parentage change; rename.

Not detected, by design: anything Fibery's own Markdown re-serialization
changes (section 3.3); a change made between the observation and a
subsequent write, because the tree is observed through several reads and is
not an atomic database snapshot; anything outside the tree.

### 3.3 Content fingerprint and its limits

`content_fingerprint` is the existing `document_fingerprint`, that is
`fingerprint_of(canonical_markdown(body))`. This reuses the frozen Markdown
equivalence policy unchanged. Precisely: two bodies that differ only in what
Fibery is known to re-serialize (bullet marker, blank lines around lists and
headings, soft line breaks and continuation indent outside fenced blocks,
line endings, trailing whitespace, NFC form) fingerprint the same; fenced
blocks are literal; the open edge cases already recorded for
`canonical_markdown` apply to children exactly as to the Root. This is
equivalence under that policy, not a byte-exact hash of every original
byte, and the contract claims no more.

The legacy `input_fingerprint`, `output_fingerprint`,
`reviewed_document_fingerprint` and the RAW Source Fingerprint keep their
current meaning and algorithm. The tree fingerprint is an additional binding
in its own field; no Root-hash field ever carries a tree hash.

### 3.4 Shared reader

One module owns traversal, classification, limits and the manifest:

```text
read_normative_tree(workspace, requirement, root) -> NormativeTree
  NormativeTree.snapshot        the manifest of section 3.1
  NormativeTree.documents       (node, body) in manifest order, for rendering
  NormativeTree.artifacts       the excluded process-control children, for
                                the stage history readers
render_normative_tree(tree)     Root first, then descendants in manifest
                                order, each under a marker naming the
                                Document, its id and its parent id, so the
                                hierarchy and identity boundaries are
                                visible in the prompt
```

The reader raises one structured error; each stage maps it to
`NORMATIVE_TREE_INVALID` or `FIBERY_READ_FAILED`.

## 4. Persisted evidence: Process Result 0.2 and Review Result 0.2

### 4.1 Fields

```text
Process Result   process_result_version "0.2"
                 all 0.1 fields, unchanged in name, meaning and algorithm
                 + normative_input_tree    manifest observed at load
                 + normative_output_tree   intended outcome: the input manifest
                                           with only the Root entry's
                                           content_fingerprint replaced by
                                           output_fingerprint
Review Result    review_result_version "0.2"
                 all 0.1 fields, unchanged
                 + reviewed_normative_tree manifest observed at load
```

Writers emit 0.2 only. Historical artifacts are immutable: no rewrite, no
in-place upgrade, no mutation during parsing or inspection.

### 4.2 Parser classification

Parsers return one of three outcomes and nothing in between:

```text
valid legacy evidence      version 0.1, all 0.1 rules satisfied; tree fields
                           absent; classified LEGACY_ROOT_ONLY
valid tree-bound evidence  version 0.2, all 0.1 rules and the 0.2
                           consistency checks satisfied
invalid evidence           anything else: the existing INVALID_* codes
```

Parsing legacy evidence never synthesizes a tree from the current workspace
and never attaches one to the artifact. There is exactly one manifest
representation; a consumer cannot choose between a stored digest and a
stored structure, because both must agree or the artifact is invalid.

### 4.3 0.2 consistency checks, all deterministic

```text
manifest structure         version 1; every field present with its type;
                           document ids unique; exactly one entry with a
                           null parent and it is root_document_id; every
                           other parent id is an entry in the manifest;
                           no entry is its own ancestor
ownership                  manifest.requirement_id equals the artifact's
                           requirement_id; root_document_id is the Root
                           the artifact is nested under (checked by the
                           consumer against the current Root)
digest                     normative_tree_fingerprint equals the hash
                           recomputed from the canonical serialization
Root agreement             input tree's Root content_fingerprint equals
                           input_fingerprint; output tree's Root
                           content_fingerprint equals output_fingerprint;
                           a Review's reviewed tree Root entry equals
                           reviewed_document_fingerprint
intended output            normative_output_tree equals
                           normative_input_tree in every entry except the
                           Root's content_fingerprint: same ids, parents,
                           names and child fingerprints. Process is
                           authorized to normalize only the Root.
review coherence           reviewed_normative_tree equals the
                           normative_output_tree of the Process Result
                           iteration named by reviewed_process_iteration,
                           which must itself be 0.2
```

An artifact failing any check is invalid evidence, reported with the
existing invalid-artifact code of the stage, and is never repaired.

## 5. Stage responsibilities and fresh checks

### 5.1 Standard Process

```text
load        read the normative tree T_in with the shared reader; artifacts,
            shells and history come from NormativeTree.artifacts
model       receives the Root and every normative descendant with hierarchy
            markers (today: Root plus direct children only), the RAW
            provenance and the A6 peers
persist     Process Result 0.2 with T_in and T_out, before any Root rewrite
writes      the Root only; no normative child is written or deleted
```

The three independently tested fresh checks stay and grow from "Root content
equivalent" to "tree snapshot equal":

```text
after model output validation, before Result persistence      == T_in
immediately before the Root rewrite, new or supported resume  == T_in
immediately before Process -> Review                          == T_out
```

Iteration selection on entry, when the latest usable Process Result is 0.2:

```text
current tree == latest.normative_input_tree    resume the rewrite, no model
current tree == latest.normative_output_tree   NO_CHANGES_TO_PROCESS
otherwise                                      new iteration
```

A child-only edit starts a new iteration, which is correct: the children
are input. Section 6 covers a latest result that is 0.1.

### 5.2 Standard Review

```text
load        read the current tree T_rev with the same reader; the latest
            usable Process Result must be 0.2 (section 7)
model       receives the Root and every normative descendant, the persisted
            Process claims and the A6 peers
persist     Review Result 0.2 with T_rev, which must equal the bound Process
            Result's normative_output_tree
re-check    before Review -> Ready: the three legacy bindings and T_rev
no-change   requires the tree binding to match as well
writes      none to any normative Document, as today
```

### 5.3 Ready

APPROVE re-reads the tree and requires, in addition to the three existing
bindings:

```text
current normative_tree_fingerprint == latest Review Result.reviewed_normative_tree
```

Child-only drift is `REVIEW_RESULT_STALE`, naming the drifted Documents
(added, removed, re-parented, renamed, changed), and nothing is written.
There is no fallback to Root-only validation. REWORK remains non-certifying,
reads no tree and is unchanged.

### 5.4 Apply

Before the first normative write and again before `Apply -> Applied`, Apply
requires the same four bindings. The Root move keeps tree identity because
the Folder is not part of the snapshot; the existing direct-child-set check
during the move stays as the more specific error. Additive relation
semantics, partial results, no rollback and resume are unchanged; detected
drift after the first write is `PARTIAL_APPLY` naming `REVIEW_RESULT_STALE`
with the durable steps kept, as today.

### 5.5 Common rules

Creating a correctly placed Process or Review Result never changes the
snapshot, because those children are excluded; a Requirement does not become
stale by being processed or reviewed. On a missing, unreadable, ambiguous or
invalid tree at any checkpoint the stage fails explicitly, never falls back
to a Root-only comparison, and makes no protected write. Reads and writes
are not compare-and-set and do not protect against concurrent writers; the
accepted window is between an observation and the write it guards.

## 6. Legacy Process behaviour

A 0.1 Process Result cannot prove the state of the children when its output
was produced, so matching the current Root to its old `input_fingerprint`
is not sufficient evidence to apply that output at tree level. Automatic
replay of a legacy Root rewrite is therefore removed from the tree-bound
processing path.

When Standard Process is legitimately entered in State Process and the
latest usable Process Result is 0.1:

```text
preserve the legacy artifact untouched
read and validate the CURRENT complete normative tree
treat the absent tree evidence as a new iteration, whatever the Root says
invoke the writer normally with the current input
persist Process Result 0.2 before any Root rewrite
apply the fresh checks of section 5.1 with the new tree bindings
```

No Root edit and no flag is required. The old normalized output is never
rendered into the Root automatically, and the new snapshot is never
presented as something the old invocation observed. This also covers a
legacy result whose earlier rewrite may have been incomplete: automatic
replay of unbound output is traded for one explicit fresh iteration. The
separate historical input/resume ambiguity of the Process specification is
not resolved here for 0.2 iterations.

## 7. Legacy Review, Ready, Apply and Applied

```text
Situation                                       Behaviour
----------------------------------------------- -----------------------------------------------
Review, latest Process Result is 0.1            refused, NORMATIVE_TREE_EVIDENCE_REQUIRED, with
                                                the instruction to run Process; no model call,
                                                no write
Review, Process 0.2, latest Review Result 0.1   a new Review iteration runs and persists 0.2;
                                                no text edit is required
Review, Process 0.2, Review 0.2, all bindings   NO_CHANGES_TO_REVIEW, as today
equal
APPROVE, any evidence not coherent 0.2 (legacy  refused, NORMATIVE_TREE_EVIDENCE_REQUIRED, zero
Process or legacy Review), even when the        mutations; REWORK remains available and stays
Requirement currently has no children           non-certifying
Apply, any evidence not coherent 0.2            refused, NORMATIVE_TREE_EVIDENCE_REQUIRED before
                                                any mutation; the existing "no Apply-level
                                                rework" limitation applies: the operator moves
                                                the Requirement back manually, no edge is
                                                deleted, no Document is moved back
Applied with legacy evidence                    immutable history: payloads stay readable,
                                                already-Applied keeps its zero-mutation result,
                                                nothing is labelled tree-verified, nothing is
                                                mutated by parsing or inspection
```

Present absence of children is never taken as evidence of past absence.
Approval and application commands never run Process or Review themselves. A
full evidence upgrade for a legacy Requirement normally requires a new
Process invocation and a new independent Review, so at least two model
calls, not one.

## 8. Empty A3 shells during the version transition

An empty body carries no payload version and no historical evidence. The
explicit `--recover-empty-result` eligibility checks stay exactly as frozen
under A3. For an eligible terminal empty shell:

```text
recovery writes the current supported 0.2 payload
the shell keeps its id, parent, name and reserved iteration
the input is the freshly captured normative tree of this run
no earlier unpersisted output is treated as recoverable evidence
```

Review-shell recovery additionally needs eligible current Process 0.2
evidence (section 7). Recovery never overwrites a non-empty 0.1 or malformed
artifact; the normal legacy upgrade creates a new iteration and never
repurposes a completed historical artifact.

## 9. Result vocabulary

Two additions, in the Process, Review, Ready and Apply code sets where the
situation can arise:

```text
NORMATIVE_TREE_INVALID           unsupported placement, foreign artifact name,
                                 misplaced artifact, cycle, duplicate listing,
                                 depth, count or tree-text bound
NORMATIVE_TREE_EVIDENCE_REQUIRED the applicable evidence is legacy or not
                                 coherent 0.2 and the operation needs
                                 tree-bound evidence
```

`REVIEW_RESULT_STALE` and `PROCESSING_STATE_CONFLICT` keep their meaning and
gain tree drift among their causes. Details name Document ids and names,
never content.

## 10. A6 comparison context and RAW

Peer entries are built with the same reader and rendered with the same
hierarchy and identity markers; artifacts are excluded by the rule of
section 2.2 and are never fed back as source text. Unchanged from A6:
same-Project Standard scope, candidate versus Applied standing, complete
evidence or explicit refusal (a peer whose tree is invalid or unreadable
refuses the run), the 100-peer admission, the final 400,000-code-point
bound on the assembled input, no truncation, no summarization, no peer
hydration on paths that invoke no model, and the limitation that a peer
change does not invalidate an existing Result.

RAW Process reuses the classifier and traversal for its own tree and for
its peers. Its candidate UUIDs, its Processing Result binding and version
and its resume semantics are not changed by this contract.

## 11. Required tests

Context:
- a child and a grandchild obligation reach the Process model context and
  the Review model context with markers identifying their place in the tree;
- Review receives the same normative children Process read;
- a peer's child obligation reaches the A6 comparison context;
- a rendered context lets a reader identify the source Document of a passage.

Legacy:
- a 0.1 latest Process Result triggers a fresh 0.2 iteration even with an
  unchanged Root, and the legacy normalized output is not replayed;
- the current children reach that fresh writer invocation;
- Review refuses a 0.1 Process Result and accepts eligible Process 0.2;
- Review runs a new iteration over a 0.1 Review Result without an edit;
- APPROVE and Apply refuse legacy evidence with zero mutations, including on
  a Requirement that currently has no children;
- a present Root-only shape does not upgrade old evidence;
- historical artifacts remain byte-for-byte unchanged through every path;
- an eligible empty shell recovers with 0.2 in place, without replacement;
- recovery never overwrites a non-empty legacy or malformed artifact;
- Applied history stays readable and already-Applied stays zero-mutation.

New bindings:
- 0.2 render/parse round-trip; each consistency check of section 4.3 fails
  its own invalid fixture;
- child and grandchild edit, addition, deletion, rename, re-parenting, and
  replacement by a same-content Document are detected;
- a correctly placed Process or Review artifact does not change the
  snapshot;
- casual titles are preserved;
- foreign-ID artifact names, misplaced artifacts and Documents nested under
  artifacts refuse explicitly;
- out-of-order API responses yield the same manifest and fingerprint;
- the Draft -> Approved Root move preserves the binding;
- failed traversal, unreadable child, duplicate listing, cycle, depth, count
  and tree-text bounds refuse with zero model calls, zero writes and no
  partial input, and traversal terminates on cyclic fake data.

Stage protection:
- tree drift during Process's model call is preserved and refused before
  persistence;
- drift before the Root rewrite and before Process -> Review is refused at
  the respective checkpoint;
- Ready catches child-only changes;
- Apply catches post-approval drift before the first write and mid-Apply
  drift as PARTIAL_APPLY;
- no stage writes child bodies or historical Result content; Review, Ready
  and Apply write no normative body.

Fake fidelity and live probe, before implementation freeze: the fake must
model nesting at depth and listing order; one narrow live probe must confirm
nested listing at depth two or more, the folder of nested Documents
following the Root move, and that a Document nested under an artifact is
listed as that artifact's child. No probe runs as part of this design.

## 12. Implementation boundaries

One implementation path:

1. `src/sdlc/normative_tree.py`: reader, classifier, limits, manifest,
   renderer, over the existing workspace protocol methods.
2. Process Result and Review Result 0.2: fields, consistency checks, parsers
   accepting 0.1 as legacy and 0.2 as tree-bound.
3. Standard Process: tree read and context, tree-based iteration selection,
   the legacy rule of section 6, the fresh checks with tree bindings, 0.2
   persistence.
4. Standard Review: tree read and context, tree binding, coherence with
   Process 0.2, the legacy rules of section 7, no-change rule.
5. Ready and Apply: the fourth binding and `NORMATIVE_TREE_EVIDENCE_REQUIRED`.
6. A6 comparison and RAW: peer trees and the shared exclusion rule.
7. Fakes, the tests of section 11, one live probe, updates to the four stage
   specifications and the checkpoint.

Out of scope, explicitly: new lifecycle States, new Fibery Fields or
Databases, a generic snapshot or event system, retrieval or summarization
agents, peer-change invalidation, Requirement revision or supersession,
general concurrent-writer safety, the historical old-input ambiguity of the
Process and Review specifications, RAW rebinding, Technical Architecture and
Delivery Planning.

## 13. Decisions recorded

1. Legacy Root-only output is never replayed automatically; a legacy latest
   Process Result yields a fresh 0.2 iteration (section 6).
2. APPROVE and Apply refuse anything but coherent 0.2 evidence, regardless of
   the present child set (section 7).
3. Review requires Process 0.2 and refuses a legacy Process Result with an
   evidence-required result (section 7).
4. Foreign-ID artifact names, misplaced artifacts and Documents nested under
   artifacts are refused (section 2.3).
5. Limits: depth 16, 100 Documents including the Root, 400,000 code points of
   tree text, in addition to the assembled-input bound (section 2.4).
6. Document names are bound because they reach the model; renaming is drift
   (section 3.1).
7. A3 shell recovery writes 0.2 from the freshly captured tree and never
   overwrites a non-empty artifact (section 8).
