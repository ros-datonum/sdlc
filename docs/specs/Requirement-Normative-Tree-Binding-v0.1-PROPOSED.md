# Requirement Normative Tree Binding v0.1 — PROPOSED

**Status:** proposed design contract for audit finding A5. Not implemented.
Nothing in this document changes running code, persisted artifacts or the
Fibery schema until it is approved and implemented under its own review.

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

The smallest shared contract that closes this is: one normative-tree reader
used by every consumer, one canonical snapshot of that tree, and that
snapshot bound wherever the Root fingerprint is bound today.

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

### 2.2 What is excluded, and by what rule

A child is a process-control artifact only when all of the following hold,
which is exactly the contract the artifacts are written under today:

```text
its name parses as   <Requirement ID> — Process Result NNNN
                  or <Requirement ID> — Review Result NNNN
                  or <Requirement ID> — Processing Result       (RAW only)
the parsed Requirement ID equals this Requirement's Requirement ID
it is a direct child of the Root
```

No substring test replaces this. The RAW processor's current
`endswith("Processing Result")` skip is replaced by the same rule.

Within an excluded artifact:

- a valid payload is history or evidence, never normative content;
- a malformed payload is an invalid artifact: the existing
  `INVALID_PROCESSING_RESULT`, `INVALID_PROCESS_RESULT` and
  `INVALID_REVIEW_RESULT` behaviour is unchanged;
- an empty A3 shell is neither normative content nor valid evidence. It is
  excluded from the snapshot, and its presence alone does not change the
  snapshot; the A3 rules decide whether it blocks or is recoverable.

### 2.3 Unsupported placement and conflicts

Two situations are ambiguous and are refused explicitly rather than guessed:

```text
a Document nested below a process-control artifact
a direct child whose name parses as an artifact name of a DIFFERENT
Requirement ID
```

Both return the stage's `NORMATIVE_TREE_INVALID` (section 9) with the
offending Document's id and name in the details, and no model call or write
follows. Ordinary content is never silently hidden because of where it sits;
the operator moves it, and the run is repeated.

A Document nested under an ordinary normative child is ordinary content at
any depth.

### 2.4 Traversal bounds

The reader visits breadth-first from the Root, keeps a set of visited
Document ids, refuses a Document seen twice (a cycle or a duplicate listing)
and refuses a tree deeper than `NORMATIVE_TREE_MAX_DEPTH = 16` or larger than
`NORMATIVE_TREE_MAX_DOCUMENTS = 200`. Both are application limits chosen far
above any expected Requirement; exceeding them is `NORMATIVE_TREE_INVALID`.
The assembled-input bound of A6 (400,000 code points) still applies to what
is sent to a model.

No Fibery Field, relation or Database is added. Classification uses Document
name, Requirement identity and parentage only.

## 3. The normative snapshot

### 3.1 Content

One versioned, deterministic manifest of an observed tree:

```text
normative_tree_version   1
requirement_id           the Requirement ID
root_document_id         the Root's Document id
documents                one entry per included Document:
  document_id
  parent_document_id     the Root for its direct children, null for the Root
  name                   the Document name; it is sent to the model as
                         hierarchy context, so it is bound
  content_fingerprint    document_fingerprint(content), section 3.3
normative_tree_fingerprint
                         sha-256 of the canonical serialization of the fields
                         above: JSON, sorted keys, entries sorted by
                         document_id, no whitespace
```

Excluded on purpose: document secrets, Folder location, timestamps,
modification metadata, view metadata, Process and Review artifact contents,
and the shells of section 2.2. Because the Folder is excluded, moving the
same Root from `Requirements/Draft` to `Requirements/Approved` does not change
the snapshot. Because parent ids are included, re-parenting within the tree
changes it; because document ids are included, replacing a child with a
new Document of identical content changes it; because the Root id is
included, replacing the Root changes it.

### 3.2 What the snapshot detects and does not

Detected: Root replacement; child addition, removal, replacement; content
change at any depth; parentage change; Document rename.

Not detected, by design: Fibery's own Markdown re-serialization (section
3.3); a change made between the observation and a subsequent write (this is
an observation, not an atomic database snapshot); anything outside the tree.

### 3.3 Content fingerprint

`content_fingerprint` is the existing `document_fingerprint`, that is
`fingerprint_of(canonical_markdown(content))`. This reuses the frozen
Markdown-equivalence policy unchanged: whatever Fibery re-serializes is not a
change, fenced blocks are literal, and the known open edge cases of
`canonical_markdown` (RAW heading inside fenced text, fingerprint equivalence
corner cases already recorded as open) apply to children exactly as they
apply to the Root today. Identity is equivalence under that policy, not
byte-exact identity.

The legacy `input_fingerprint`, `output_fingerprint`,
`reviewed_document_fingerprint` and the RAW Source Fingerprint keep their
current meaning and algorithm. The tree fingerprint is an additional binding,
never a replacement for them and never a new meaning smuggled into an old
field.

### 3.4 Shared reader

One module owns traversal, classification and the manifest:

```text
read_normative_tree(workspace, requirement, root) -> NormativeTree
  NormativeTree.snapshot        the manifest of section 3.1
  NormativeTree.documents       (node, content) in deterministic order, for
                                rendering to a model
  NormativeTree.artifacts       the excluded process-control children, for
                                the stage history readers
render_normative_tree(tree)     Root first, then descendants in manifest
                                order, each under a marker naming the
                                Document, its id and its parent so the
                                hierarchy is identifiable in the prompt
```

Ordering is by document id at every level, never by API response order.
The reader raises one structured error; each stage maps it to its own
`NORMATIVE_TREE_INVALID` or `FIBERY_READ_FAILED`.

## 4. Consumer responsibilities

### 4.1 Standard Process

```text
load        read the normative tree T_in; artifacts and shells are taken from
            NormativeTree.artifacts, as _read_children does today
model       receives the Root and every normative descendant with hierarchy
            markers (today: Root plus direct children only), plus A6 peers
persist     Process Result 0.2 records
              input_fingerprint, output_fingerprint     as today, Root only
              normative_input_tree                      T_in
              normative_output_tree                     T_out
            T_out is T_in with the Root entry's content_fingerprint replaced
            by output_fingerprint and nothing else changed: the intended
            outcome is the new Root plus the same captured children. Process
            never rewrites or deletes a normative child.
guards      the existing fresh-input checks stay and grow from "Root
            content equivalent" to "tree snapshot equal":
              after model output validation, before persistence:   == T_in
              before the Root rewrite, new iteration:               == T_in
              before the Root rewrite, resumed iteration:           == T_in
              before Process -> Review:                             == T_out
```

Iteration selection generalizes the frozen fingerprint rule to the tree:

```text
current tree == latest.normative_input_tree    resume, no model
current tree == latest.normative_output_tree   NO_CHANGES_TO_PROCESS
otherwise                                      new iteration
```

A child-only edit therefore starts a new iteration, which is correct: the
children are input. Section 7 defines what happens when the latest result
carries no tree.

### 4.2 Standard Review

```text
load        read the current normative tree T_rev with the same reader
model       receives the Root and every normative descendant (today: Root
            only), the persisted Process claims and A6 peers
persist     Review Result 0.2 records the three existing bindings plus
              reviewed_normative_tree        T_rev
bindings    the existing re-check before Review -> Ready compares the three
            legacy bindings and the tree; the tree must also equal the
            latest Process Result's normative_output_tree, otherwise the
            reviewer would be certifying a tree Process never produced
no-change   requires the tree binding to match as well as the three legacy
            bindings
writes      none to any normative Document, as today
```

### 4.3 Ready

APPROVE re-reads the tree and requires, in addition to the three existing
bindings:

```text
current normative_tree_fingerprint == latest Review Result.reviewed_normative_tree
```

Child-only drift is `REVIEW_RESULT_STALE`, with the drifted Documents named
in the details (added, removed, re-parented, changed), and nothing is
written. REWORK remains non-certifying and reads no tree.

### 4.4 Apply

Before the first normative write and again before `Apply -> Applied`, Apply
requires the same four bindings. The Root move keeps tree identity because
the Folder is not part of the snapshot; the existing direct-child-set check
during the move is subsumed by comparing the snapshot before and after the
move and stays as the more specific error. Additive relation semantics,
partial results and resume are unchanged.

No new lifecycle stage and no second reviewer are introduced.

## 5. Comparison peers (A6)

Peer entries are built with the same reader: for each admitted peer, its
normative tree is read and rendered with the same hierarchy markers, with
its artifacts excluded by the same rule. Everything else in A6 is unchanged:
same-Project Standard scope, candidate versus Applied standing, complete
evidence or explicit refusal (a peer whose tree is invalid or unreadable
refuses the run), the 100-peer admission, the final 400,000-code-point bound
on the assembled input, no truncation, no summarization, and no peer
hydration on paths that invoke no model.

Peer trees are evidence for one invocation. A change in a peer does not
invalidate an existing Result; that remains a separate limitation.

RAW Process uses the shared reader for its own tree and for its peers so
that its artifact exclusion follows the contract of section 2.2. Its
Processing Result, candidate identity and resume semantics are not changed
by this contract.

## 6. Persisted format changes

```text
Process Result   process_result_version "0.2"
                 + normative_input_tree   (manifest of section 3.1)
                 + normative_output_tree  (manifest of section 3.1)
Review Result    review_result_version "0.2"
                 + reviewed_normative_tree (manifest of section 3.1)
```

All existing fields keep their names, meaning and algorithm. Writers emit
0.2 only. Parsers accept 0.1 and 0.2; a 0.1 payload parses with the tree
fields absent and is classified as a **legacy Root-only binding**. Nothing
rewrites a historical Result Document, and no tree is ever synthesized for a
legacy result from current Fibery state: an absent binding stays absent.

The manifests are small (ids, one name and one hash per Document) and live
inside the existing JSON payload; the artifact naming and placement contract
is untouched.

## 7. Legacy compatibility and revalidation

The rule: **legacy evidence remains readable history and remains sufficient
for the operations the old contract already made safe, and is insufficient
for any certification that the new contract is meant to guarantee.** Current
absence of children never proves they were absent when the legacy evidence
was produced.

```text
Case                                              Behaviour
------------------------------------------------- --------------------------------------------
legacy Process Result, incomplete Root rewrite     resume is allowed: it writes only the Root
(current Root == legacy input_fingerprint)         from the persisted output, under the existing
                                                   Root fresh-input guard; the resumed result
                                                   stays legacy and binds no tree
legacy Process Result, Root == output_fingerprint, NOT no-change. A tree was never bound, so the
State = Process                                    input is new by contract: run a new iteration
                                                   (one model call) and persist 0.2. The result
                                                   details name this as the tree-evidence upgrade.
                                                   No text edit is required to trigger it.
legacy Review Result, State = Review, bindings     NOT no-change: a new review iteration runs and
otherwise matching                                 persists 0.2, for the same reason
legacy Review Result, State = Ready, APPROVE       refused with NORMATIVE_TREE_EVIDENCE_REQUIRED:
                                                   the operator sends it for REWORK, which is
                                                   non-certifying, then Process and Review produce
                                                   tree-bound evidence
legacy Review Result, State = Apply                refused with NORMATIVE_TREE_EVIDENCE_REQUIRED;
                                                   the existing "no Apply-level rework" limitation
                                                   applies and the operator moves the Requirement
                                                   back manually
State = Applied with legacy evidence               immutable history; never revalidated, never
                                                   rewritten, never re-reviewed by this contract
A3 shell (no payload)                              regeneration is a new invocation and persists
                                                   0.2 with the current tree; a shell never
                                                   carries a legacy binding
legacy result on a currently Root-only tree        treated exactly like the rows above; the empty
                                                   child set is an observation, not evidence
```

The upgrade path is therefore the ordinary lifecycle with one honest rule:
a Requirement whose latest evidence binds no tree is treated as changed at
the next Process or Review entry, and cannot be approved or applied until it
carries tree-bound evidence. No migration engine, no bulk rewrite, no
material revision model.

## 8. Fresh observations and staleness checkpoints

```text
Point                                   Expected tree     Behaviour on mismatch
--------------------------------------- ----------------- ---------------------------------------
Process: after model output validated,  T_in              PROCESSING_STATE_CONFLICT; nothing
before Result persistence                                 persisted
Process: before Root rewrite (new)      T_in              PROCESSING_STATE_CONFLICT; Result stays
Process: before Root rewrite (resume)   T_in              as above
Process: before Process -> Review       T_out             PROCESSING_STATE_CONFLICT; Root rewrite
                                                          stays, State stays Process
Review: before Review -> Ready          T_rev, and T_rev  REVIEW_RESULT_STALE; Result stays
                                        == T_out of the
                                        bound Process
Ready APPROVE: before Ready -> Apply    reviewed tree     REVIEW_RESULT_STALE; no write
Apply: before first normative write     reviewed tree     REVIEW_RESULT_STALE; no write
Apply: before Apply -> Applied          reviewed tree     PARTIAL_APPLY naming REVIEW_RESULT_STALE;
                                                          durable steps stay, as today
```

Creating a Process or Review Result child never changes the snapshot,
because those children are excluded by section 2.2; a Requirement does not
become stale by being processed or reviewed.

On a missing, unreadable, ambiguous or invalid normative tree at any of
these points, the stage fails explicitly with `NORMATIVE_TREE_INVALID` or
`FIBERY_READ_FAILED`, never falls back to a Root-only comparison, and makes
no protected write after the failed observation.

Partial-state reporting and the no-rollback philosophy are unchanged. These
reads and writes are not compare-and-set and do not protect against
concurrent writers; the accepted window is between an observation and the
write it guards.

## 9. Result vocabulary

Two additions, each added to the Process, Review, Ready and Apply code sets
where the situation can arise:

```text
NORMATIVE_TREE_INVALID           unsupported placement, foreign artifact name,
                                 cycle, depth or size bound, duplicate listing
NORMATIVE_TREE_EVIDENCE_REQUIRED the latest evidence binds no tree and the
                                 operation is a certification (APPROVE, Apply)
```

`REVIEW_RESULT_STALE` and `PROCESSING_STATE_CONFLICT` keep their meaning and
gain tree drift among their causes. Details name Document ids and names,
never content.

## 10. Required tests

Context:
- a child and a grandchild obligation reach the Process model context and the
  Review model context, with markers identifying their place in the tree;
- a peer's child obligation reaches the A6 comparison context;
- rendered context lets a reader identify which Document a passage came from.

Staleness:
- child-only edit after Review: APPROVE refused, Apply refused, nothing
  written;
- grandchild edit, child added, child deleted, child re-parented, child
  replaced by a same-content Document, Root replaced: all refused at APPROVE
  and Apply, each named in the details;
- a child edited during Process's model call: PROCESSING_STATE_CONFLICT,
  nothing persisted, the edit preserved;
- a child edited between APPROVE and Apply: Apply refuses before the first
  write;
- a child edited during Apply after the first edge: PARTIAL_APPLY, durable
  steps preserved, State stays Apply.

Exclusions and stability:
- a new Process or Review Result does not change the snapshot;
- children named "Review notes", "Process", "Result" are included;
- a foreign-ID artifact name and a Document nested under an artifact refuse;
- API row reordering yields the same manifest and fingerprint;
- Draft -> Approved Root move keeps the snapshot equal;
- an empty A3 shell changes nothing and follows the A3 rules.

Failures:
- unreadable child, duplicate listing, cycle, depth and size bounds refuse
  with zero model calls, zero writes, no partial input;
- traversal terminates on cyclic fake data.

Compatibility:
- each row of section 7 has a test with the stated outcome;
- a 0.1 payload parses as legacy and never acquires a tree from current
  state;
- legacy incomplete resume still writes the Root and nothing else;
- shell recovery persists 0.2 bound to the current tree;
- a 0.2 payload round-trips through render and parse unchanged.

Immutability:
- no child body write in any stage;
- no historical Result rewrite;
- no normative body write in Review, Ready or Apply.

Fake fidelity and live probe (before implementation freeze, not now): the
fake must model nested children at depth and `child_documents` listing order;
one narrow live probe must confirm nested listing at depth two or more, the
folder of nested Documents following the Root move, and that a Document
nested under an artifact is listed as that artifact's child.

## 11. Implementation boundaries

One implementation path:

1. `src/sdlc/normative_tree.py`: reader, classifier, manifest, renderer,
   bounds. Pure over the existing workspace protocol methods
   (`documents_attached_to_requirement`, `child_documents`,
   `read_document_content`).
2. Process Result and Review Result: version 0.2 fields, parsers accepting
   0.1 and 0.2, legacy classification.
3. Standard Process: tree read, full-tree model context, tree-based
   iteration selection, tree guards at the four points, 0.2 persistence,
   the legacy rows of section 7.
4. Standard Review: tree read and context, tree binding, re-check and
   no-change rule, the legacy rows.
5. Ready and Apply: the fourth binding and `NORMATIVE_TREE_EVIDENCE_REQUIRED`.
6. A6 comparison and RAW: peer trees and the shared exclusion rule.
7. Fakes, tests of section 10, one live probe, spec updates to the four
   stage specifications, checkpoint update.

Out of scope, explicitly: new lifecycle States, new Fibery Fields or
Databases, a generic snapshot or event system, retrieval or summarization
agents, peer-change invalidation, Requirement revision or supersession,
general concurrent-writer safety, the historical old-input ambiguity of the
Process and Review specifications, Technical Architecture and Delivery
Planning.

## 12. Decisions needing approval

1. Certification strictness for legacy evidence (section 7): APPROVE and
   Apply refuse legacy Root-only evidence outright. The alternative, admitting
   it when the current tree has no children, would rely on present absence
   as proof of past absence and is not proposed.
2. Upgrade by ordinary iteration (section 7): a legacy latest result is
   treated as changed input at Process and Review entry, costing one model
   call per Requirement instead of a flag or an edit.
3. Foreign-ID artifact names and Documents nested under artifacts are
   refused rather than treated as content (section 2.3).
4. The traversal bounds of section 2.4 (depth 16, 200 Documents).
5. Document names are part of the bound identity because they are sent to
   the model; renaming a child therefore counts as drift.
