# RW-V02 — Corrected AMR Dogfood Boundary v0.2

**Status:** FROZEN  
**Work item:** `RW-V02 — Re-run the two AMR RAW sources through corrected Requirement pipeline`  
**Owner:** Human-operated dogfood + independent reviewer  
**Implementation actor:** System under test; no coding implementation actor  
**Depends on:** verified `RW-R05`, verified `RW-O04`, verified `RW-V01`  
**Baseline evidence:** `docs/rewrite/RW-V01-AMR-Baseline-v0.1.md`  
**Supersedes:** `docs/rewrite/RW-V02-Dogfood-Boundary-v0.1.md`  
**Semantic change to frozen RW-V02:** NONE — this corrects an over-constrained verification proxy in v0.1.  
**Date:** 2026-09-12

## 1. Purpose

This document freezes the non-destructive live procedure for dogfooding the corrected Requirement pipeline against the two real AMR RAW source bodies without modifying the historical AMR corpus.

The system under test is the verified normal state-driven Requirement lifecycle:

```text
human Draft -> Process
        ↓
RAW Processor
        ↓
exact produced Standard candidates Draft -> Process
        ↓
Standard Process
        ↓
Standard Review
        ↓
Ready
        ↓
STOP for human
```

No candidate is approved/applied as part of RW-V02.

---

## 2. Historical AMR corpus is read-only

The following live historical entities are protected throughout RW-V02:

```text
AMR-RAW-0053
AMR-RAW-0077
and the 28 old Standard Requirements listed in RW-V01-AMR-Baseline-v0.1.md
```

RW-V02 must not:

- change their State;
- change their Processing Status;
- edit their Requirement content/Documents;
- change their relations;
- delete them;
- use either historical RAW entity itself as the dogfood execution target.

Before the dogfood begins, capture a read-only integrity snapshot for all 30 protected Requirements sufficient to prove after the run that their ids, Requirement IDs, Type, State and modification timestamps remain unchanged.

If practical through the existing authenticated document APIs, also capture stable hashes of the historical RAW Root Document bodies. This is supporting evidence, not permission to copy secrets/document ids into public evidence.

---

## 3. Isolated reference corpus

Run corrected dogfood in one new, clearly disposable/reference Fibery Project.

Example identity:

```text
Project Name: ZZ RW-V02 AMR Corrected Dogfood <unique suffix>
Project Code: explicit unique valid code
```

Before mutation prove by bounded read-only queries that the exact Name and Code do not already exist.

Do not use the production `ai-model-runner` Project for corrected processing.

The reference Project is intentionally retained after a successful RW-V02 run until RW-V03 comparison/cleanup is complete. It must not be deleted at the end of RW-V02 unless the human explicitly changes this decision.

This keeps the corrected corpus inspectable while the old active corpus remains untouched.

---

## 4. Source identity and reconstruction from Fibery

### 4.1 Why v0.1 fingerprint parity is superseded

The historical `Source Fingerprint` was calculated when the original exported artifact was ingested.

Fibery subsequently re-serializes Markdown when a Document is read back. Verified examples already handled by `canonical_markdown` / `content_equivalent` include:

- `-` bullets returned as `*`;
- inserted blank lines;
- wrapped soft line breaks returned as `<br>`;
- other explicitly verified Markdown storage transformations outside fenced blocks.

Therefore the historical artifact fingerprint is an **ingestion-time provenance identifier**, not a round-trip hash that can necessarily be recomputed from the later Fibery-rendered Markdown body.

RW-V02 v0.1 incorrectly required:

```text
fingerprint_of(historical Root body read back from Fibery)
== historical Source Fingerprint
```

That proxy is not required by the frozen RW-V02 plan and is unsatisfiable for the two protected AMR RAWs even though their recovered bodies are content-equivalent to valid reconstructed source artifacts.

RW-V02 must **not** change `fingerprint_of`, migrate existing fingerprints, or invent fingerprint-versioning under this dogfood item. Changing that algorithm could alter duplicate-detection behavior for existing Requirements and is outside RW-V02.

### 4.2 Historical provenance anchor

For each historical RAW, prove before reconstruction:

```text
historical entity Requirement ID == the exact RW-V01 Requirement ID
historical entity Source Fingerprint == the exact RW-V01 baseline fingerprint
historical Root Document belongs to that exact entity
historical Root Document title/body are the expected source document
```

This proves the recovered Document is anchored to the historical RAW whose ingestion fingerprint RW-V01 records.

### 4.3 Reconstruct a transport-valid artifact without semantic edits

For each historical RAW:

1. resolve the exact Requirement by the stable Requirement ID from RW-V01;
2. resolve its single normative Root Document under the existing Requirement-document contract;
3. read the Root Document body through the existing authenticated document mechanism;
4. create an ephemeral RAW transport artifact by inserting only a valid `Export Metadata` section into the stored body.

The currently supported transport contract requires at minimum:

```markdown
## Export Metadata
- Format: sdlc/raw-requirements
- Format Version: 0.1
```

The metadata may additionally identify the disposable Project, but metadata must not alter source meaning.

Then require:

```python
parsed = parse_raw_requirement(artifact)
content_equivalent(parsed.body, historical_root_body) is True
canonical_markdown(parsed.body) == canonical_markdown(historical_root_body)
```

No sentence, heading, list item, constraint, decision, open question, example, fenced block, or other semantic source content may be manually rewritten merely to reconstruct the transport artifact.

Record both fingerprints separately:

```text
historical_source_fingerprint
= immutable provenance value stored on the historical RAW and frozen in RW-V01

reference_copy_fingerprint
= parsed.fingerprint computed by the current transport parser over the reconstructed source body
```

The two values are **not required to be equal**.

Their relationship is proven through:

```text
exact historical entity identity
+ historical stored fingerprint == RW-V01 baseline
+ exact historical Root Document relation
+ reconstructed artifact parses successfully
+ parsed body content-equivalent/canonically equal to recovered historical body
+ no semantic edit during reconstruction
```

The ephemeral transport files stay outside the `sdlc` repository and are deleted after ingestion. Their full bodies are not committed to the repository merely for dogfood.

---

## 5. Create the isolated Project through existing deterministic primitives

Use existing user-facing deterministic commands/capabilities only:

```text
sdlc project init
sdlc project requirement add
```

No model is involved in Project creation or RAW ingestion.

Add exactly two RAW Requirements to the disposable Project, one reconstructed from each historical source body.

After ingest verify for each copied RAW:

```text
Type = Raw
State = Draft
Source Fingerprint == the pre-ingest reconstructed parsed.fingerprint
one Root Document
Root content equivalent to the corresponding historical RAW Root body
```

Also record the immutable historical baseline fingerprint beside the copied RAW's new reference-copy fingerprint so later comparison can trace the copied source back to the exact protected historical RAW.

Do not start processing during ingest.

---

## 6. Runner safety before state-driven dogfood

RW-O03's runner watches every Project in the configured workspace.

Before starting `sdlc worker run`:

1. prove no other local `sdlc worker run` process owns the workspace;
2. query the complete current machine-eligible set for:

```text
Raw + Process + Not Processed
Standard + Process + Not Processed
Standard + Review + Not Processed
Standard + Apply + Not Processed
```

3. require that no unrelated Requirement is eligible.

If unrelated eligible work exists, do not start the live runner. Stop and report the blocker rather than processing someone else's state.

Use one foreground runner only.

If the persistent `FIBERY_SPACE_ID` remains empty, the already-verified process-scoped Space-id setup may be used again. Do not edit `.env` or user-global runtime/auth settings merely for dogfood.

---

## 7. Execute one historical source at a time

Process the two copied RAWs sequentially.

For each source:

1. confirm the other copied RAW remains `Draft`;
2. explicitly perform the human-owned state transition on the selected copied RAW:

```text
Draft -> Process
```

This RW-V02 procedure is the human authorization for this transition on the two disposable copied RAWs only.

3. let the normal state-driven runner execute machine-owned stages;
4. do not invoke manual `process`, `normalize` or `review` CLI commands in the normal dogfood path;
5. wait until the copied RAW reaches its completed system state and every candidate produced by that RAW has reached the next human boundary `Ready`, or until a visible failure occurs;
6. stop the runner between sources if necessary to keep the experiment bounded and observable;
7. only then authorize `Draft -> Process` on the second copied RAW.

No `Ready -> Apply` is permitted under RW-V02.

No `Ready -> Process` rework is permitted automatically. If independent review later decides a candidate should be reworked, that is a separate explicit human decision after the first-run evidence is preserved.

---

## 8. Expected lifecycle evidence

For each copied RAW, record:

- copied RAW Requirement ID/entity id;
- historical source Requirement ID/entity id;
- historical source fingerprint from RW-V01;
- copied/reference source fingerprint generated from the reconstructed artifact;
- source-equivalence proof from section 4;
- RAW Processing Result id/name;
- exact produced candidate Requirement IDs/entity ids;
- final copied RAW Type/State/Processing Status;
- model invocation outcome;
- any RAW findings/no-candidate reason.

For every produced Standard candidate, record:

- Requirement ID/entity id;
- title;
- category;
- final State and Processing Status;
- normative Requirement body;
- Process Result iteration/body;
- Review Result iteration/body;
- Review verdict;
- blocking/warnings/verification evidence;
- proposed dependency/impact relations, if any.

Do not expose model/runtime secrets or document secrets in the committed evidence.

The complete corrected Requirement content must remain inspectable either in the retained reference Project or in bounded repository evidence sufficient for independent semantic review.

---

## 9. Independent semantic evaluation

Every corrected Standard candidate is evaluated against the exact semantic dimensions frozen by RW-V01 and the Standard Requirement Abstraction v0.2.

For each candidate answer explicitly:

1. Is it independently meaningful as WHAT must be true?
2. Could multiple valid technical implementations satisfy it unless the source explicitly mandates one?
3. Did implementation mechanics remain downstream?
4. Is Requirement acceptance observable rather than test-code/framework-specific?
5. Were source-mandated technical/product constraints preserved?
6. Were source open questions preserved rather than invented away?
7. Did the pipeline avoid unnecessary fragmentation?
8. Did it avoid merging genuinely independent obligations?
9. Would Technical Solution Architecture still have meaningful HOW decisions left?
10. Did Process/Review add useful quality evidence without demanding architecture detail?

Candidate count is recorded but is **never** a pass/fail criterion.

A corrected corpus of 5, 19, 28, 40 or any other count can pass or fail solely on semantic correctness.

---

## 10. Coverage against the historical corpus

For each corrected candidate, record which old RW-V01 Requirement IDs appear semantically related/overlapping/subsumed, if any.

This is comparison evidence only.

Do not classify an old Requirement for deletion inside RW-V02.

RW-V03 owns the human-reviewed cleanup classifications:

```text
still-needed
obsolete
redundant
over-decomposed
replaced
```

RW-V02 may identify apparent correspondence but does not delete or mutate old items.

---

## 11. Failure handling

Any of the following is a dogfood failure/blocker, not permission to repair production code inside RW-V02:

- runner processes unrelated workspace work;
- historical entity `Source Fingerprint` no longer equals the RW-V01 baseline;
- reconstructed artifact does not parse under the current RAW transport contract;
- reconstructed `parsed.body` is not content-equivalent/canonically equal to the protected historical Root body;
- copied RAW `Source Fingerprint` differs from the reconstructed artifact's pre-ingest `parsed.fingerprint`;
- copied RAW Root content is not content-equivalent to the protected historical Root body;
- state-driven processing requires manual internal worker commands;
- human Ready boundary is crossed automatically;
- candidate remains implementation-leaking under the corrected abstraction;
- source-mandated obligation is lost;
- lifecycle produces a new BLOCKING defect;
- a machine failure falsely advances lifecycle State;
- old AMR corpus is mutated.

A difference between the **historical ingestion fingerprint** and the **reference-copy fingerprint** is not itself a RW-V02 failure when the complete section-4 source-equivalence proof passes.

If a production defect is exposed:

1. stop the dogfood safely;
2. preserve the isolated corpus as evidence;
3. report the exact failing state;
4. identify the owning verified work item;
5. do not patch production code under RW-V02.

---

## 12. Evidence artifact

Commit one evidence document:

```text
docs/rewrite/RW-V02-AMR-Corrected-Dogfood-v0.1.md
```

It must contain:

- date and code baseline;
- disposable/reference Project identity;
- source-copy equivalence proof for both RAWs, including historical and reference-copy fingerprints separately;
- protected old-corpus before/after integrity result;
- runner safety preflight;
- phase-by-phase state-driven lifecycle evidence;
- candidate count per source, marked non-normative;
- candidate-by-candidate semantic evaluation;
- old-corpus correspondence notes;
- Process/Review evidence and verdicts;
- any lifecycle failures;
- runner stop state;
- confirmation no candidate was approved/applied;
- confirmation old AMR corpus was unchanged;
- repository regression gates after the dogfood.

Do not commit full model prompts/responses or secrets merely for completeness.

---

## 13. Reference Project after RW-V02

On successful first-pass dogfood:

- stop the runner;
- leave both copied RAWs and all corrected candidates in the isolated reference Project;
- leave corrected candidates at `Ready`;
- do not Apply them;
- do not delete the reference Project before RW-V03.

This reference Project is comparison data, not the canonical AMR Project.

After RW-V03 completes, disposal of the reference Project is a separate explicit human cleanup decision.

---

## 14. Repository boundary

Expected production-code changes under RW-V02:

```text
NONE
```

Expected test-code changes:

```text
NONE
```

If green dogfood needs production code changes, RW-V02 is not green.

Repository changes should be evidence/status documentation only.

Run the full repository regression gate after live dogfood and before finalizing evidence.

### Non-blocking fingerprint-contract observation

The current repository contains a tension worth preserving for a later explicit owner decision: documentation around Fibery Markdown re-serialization states that fingerprints and `content_equivalent` should derive from one canonical representation, while the current RAW source fingerprint is still the ingestion-artifact fingerprint computed by `fingerprint_of` over its narrower normalization.

RW-V02 neither resolves nor hides that tension. Changing the fingerprint algorithm here is forbidden because existing stored fingerprints and duplicate-detection compatibility may require versioning/migration analysis.

This observation is **not blocking to semantic dogfood** once the source-equivalence proof in section 4 is used.

---

## 15. Verification ownership

The system under test may generate/process/review the disposable candidates, but it does not verify itself.

RW-V02 remains `IMPLEMENTED_UNVERIFIED` / equivalent dogfood-complete state until an independent reviewer reads every produced candidate and its evidence against the semantic criteria above.

No automated Review verdict, including `PASS`, substitutes for independent RW-V02 verification.
