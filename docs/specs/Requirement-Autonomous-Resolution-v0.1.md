# Requirement Autonomous Resolution — v0.1 (delta)

**Status:** IMPLEMENTED ON BRANCH `impl/requirements-autonomous-resolution`; NOT LIVE-VERIFIED. No autonomy policy is active anywhere.
**Authorization:** human instruction "Implement WI-5 — Autonomous Requirement Resolution Policy", for baseline `0bd43220437644db5c03611deff4e9deacbc7ea4`. The approval record is that instruction; no signature is claimed. It authorizes decision *capability* only: it does not enable autonomous approval or rework, and it does not create or activate any delegated-decision policy.
**Amends, narrowly and only as stated here:**
- Standard-Requirement-Process-Spec-v0.1 §5 (input context) and its output contract;
- Standard-Requirement-Review-Spec-v0.1 §5 and §7 (contract) and the Review Result shape;
- Standard-Requirement-Ready-Spec-v0.1 and Standard-Requirement-Apply-Spec-v0.1 (one more currentness check each);
- Requirement-Material-WHAT-Gate-v0.1 §4–§6 (resolutions are a further input to the derived WHAT status);
- Requirement-Rework-Brief-v0.1 §4–§6 (one more item category; rework responses bind evidence);
- Requirement-Dependency-Bindings-v0.1 §8 (a dependency-grounded resolution clears only through a verified, bound dependency);
- TSA-C01-Contract-v0.2 §2.1 (admission check 9 also checks resolution currentness).

Those documents are unchanged on disk. Where this delta and they disagree, this delta governs for the listed points only. WI-1's non-waivable material-WHAT gate, WI-2's Rework Brief and WI-4's dependency bindings are preserved.

## 1. Purpose and boundary

Standard Process may now *resolve* a product question itself when it has sufficient authoritative evidence, or when an explicitly approved human policy delegates that exact class of low-risk decision. Every such resolution is structured evidence that the independent Reviewer must verify. A resolution the Reviewer does not confirm can never establish WHAT clearance.

Unchanged: the lifecycle and its States (RAW → Decomposition → Process → Review → Ready → Apply → Applied → TSA), human authority at Ready, the relation types, the databases, the Fibery schema, the dispatcher and runner, and the single model call per Process and per Review. No new agent, model role, State, database, store, automatic transition, automatic rework or automatic approval. A Requirement with only confirmed resolutions and WHAT CLEAR still stops at Ready for a human (WI-6 is a separate work item).

## 2. Decision classification

A closed set, `ResolutionClass`. Classes are decision classifications, not States or roles.

| Class | Meaning | Where it is recorded |
|---|---|---|
| A `SOURCE_GROUNDED` | An authoritative source already available to Process settles the answer: the originating RAW, or this Requirement's own normative input (which holds any earlier human clarification). | `resolutions[]` |
| B `DEPENDENCY_GROUNDED` | A DEPENDS_ON dependency owns the definition. The Requirement refers to it and does not copy it. | `resolutions[]` |
| C `DELEGATED_DEFAULT` | No source settles it, but a clause of the approved policy (§3) explicitly delegates this outcome. | `resolutions[]` |
| D `HUMAN_REQUIRED` | Critical, changes material business intent, conflicts between authoritative sources without an established resolution, or beyond delegated authority. | `product_questions[].authority` |
| E `INSUFFICIENT_EVIDENCE` | No source and no policy settle it. At least two alternatives are recorded. | `product_questions[].authority` |
| F `TECHNICAL_HOW` | An implementation choice that does not alter a required outcome. It belongs to TSA. | Recorded nowhere: it is neither a resolution nor a product question. A Reviewer rejects a question as `TECHNICAL_HOW` exactly as before. |

Only A, B and C appear in `resolutions`. D and E stay unanswered product questions under the WI-1 gate, and the normative content never adopts an answer to them. A material D or E question keeps the Requirement `BLOCKED_ON_WHAT`.

**Human-only domains.** Whatever a policy says, a decision affecting any of the following is D: security guarantees; privacy and personal data; legal or regulatory obligations; financial commitments; irreversible data loss; major product scope; a conflict between authoritative sources without an established resolution. Code renders this list as a non-overridable exclusion of every policy clause, in both prompts. The policy schema has no key that could lift it. Whether a decision touches one of these domains is semantic: the Reviewer judges it.

## 3. Autonomy policy (Class C authority)

### 3.1 Authority boundary

The policy lives in the SDLC repository's runtime configuration, `config/sdlc.toml`, table `[autonomy]`. This is the existing trusted, operator-controlled configuration boundary: it already selects which model executes reasoning, and the consumer-repository descriptor (RW-B03) deliberately has no key for a policy. Nothing else establishes delegation:
- not a Fibery Document, whatever its name;
- not a model's assertion;
- not Project metadata.

Approval is the operator recording, in that file, the exact SHA-256 fingerprint of the policy content they approved, under `mode = "enabled"`. That record is the approval. It is not an authenticated signature: like a Fibery State transition, it attests that the operator's configuration says so.

### 3.2 Shape (closed; unknown keys refused)

```toml
[autonomy]
mode = "disabled"            # or "enabled"

[autonomy.projects.<PROJECT_CODE>]          # only under mode = "enabled"
policy_id = "<identifier>"
approved_by = "<who approved it>"
approved_fingerprint = "<64 hex>"           # SHA-256 of the canonical content

[[autonomy.projects.<PROJECT_CODE>.clauses]]
clause_id = "<identifier>"
applies_when = "<applicability conditions>"
permitted_decision = "<the one outcome it permits>"
boundaries = "<limits of the permitted decision>"
exclusions = ["<excluded case>", ...]       # may be empty
evidence_required = "<applicability evidence the Process must cite>"
```

- **Canonical content:** the project code, the policy id and the clauses in order. It is serialized as sorted-key, compact UTF-8 JSON and hashed with SHA-256.
- **Load refusals:** the configuration fails to load (a configuration error, before any Fibery read) when:
  - the computed fingerprint is not `approved_fingerprint`;
  - a policy id or clause id is repeated;
  - an identifier or Project code is invalid;
  - any text is empty;
  - `mode` is missing or unknown;
  - `mode = "disabled"` still carries projects.
- **Absence:** the `[autonomy]` table missing entirely is the same as `mode = "disabled"`.
- **When it is read:** as each command invocation starts, and as each Standard stage of a running worker starts (§3.4). It is immutable for that stage only.

### 3.3 Default deny and activation

- No active policy is the default state, and is the state this commit ships (`mode = "disabled"`, no projects).
- With no policy, Classes A and B still operate when their evidence suffices. Class C is unavailable: a C resolution is refused deterministically.
- A clause authorizes only what it states. Paraphrase, broadening or a generic "low risk" claim authorizes nothing, and the Reviewer judges scope.
- No test fixture is configuration: the Class C test policies exist only in the test suite.

### 3.4 Policy lifetime

Five things are kept apart:

| | What it is | How long it lives |
|---|---|---|
| A | **Worker lifetime:** one `sdlc worker run` process. | Hours or days. It carries **no** policy authority. |
| B | **Stage invocation:** one claimed machine stage (Standard Process, Review or Apply) of one Requirement, or one single-shot command. | From the stage's start to its result. |
| C | **Stage snapshot:** the policies read from `config/sdlc.toml` as B starts. Every model prompt, deterministic check and currentness check in B uses it. | B only. Never reused by a later stage. |
| D | **Bound evidence:** the `{policy_id, fingerprint}` a Process Result records (§5) and a Review Result copies (§6). | As long as the artifact. Never rebound or reinterpreted. |
| E | **Effective operator policy:** whatever `config/sdlc.toml` holds now. | Until the operator edits it. |

**Invariant.** No new machine-stage operation is authorized under a policy that was already changed, disabled, removed or broken before that operation began.

**Refresh boundary.** The worker resolves its Fibery workspace and model roles once at start, as before. It also reads the policies once at start, only so that a broken table stops the runner before any claim. That read authorizes nothing. Each Standard Process, Review and Apply stage then reads the policies again, after its claim and before it reads Fibery or invokes a model, and uses only that snapshot (C). RAW processing reads no policy. An idle worker reads nothing. Model runtime selection is unaffected: it stays resolved at start.

**Snapshot identity.** A snapshot is identified only by each policy's `policy_id` and content fingerprint. `approved_by` is outside the fingerprint and outside the identity. Changing it neither revokes a policy nor grants anything, and it is never an authentication.

**Revocation.** Each operator change takes effect at the next stage start:
- `mode = "disabled"`, the table removed, or the Project's policy removed: the next Process offers the model no policy, and a Class C resolution is refused (`INVALID_MODEL_OUTPUT`). Review, Ready, Apply and TSA refuse P1-bound evidence as `RESOLUTION_EVIDENCE_STALE` / `REQUIREMENT_NOT_ADMISSIBLE`.
- A different approved policy P2: new work may use P2 and is bound to P2. P1-bound evidence is stale as above.
- Bound evidence (D) keeps its P1 binding. It never becomes current again because some process still holds P1.

**Configuration failure.** Malformed TOML, an unknown `mode`, content that does not hash to `approved_fingerprint`, a changed `approved_fingerprint`, or an unreadable file all make the stage refuse with `AUTONOMY_POLICY_INVALID`. In that case the stage reads nothing from Fibery, invokes no model and writes nothing. There is no fallback: no cached policy, no last-known-good policy, and no substitute. The refusal names the configuration error only, never clause text. At runner start the same failure is `WORKER_RUNNER_CONFIGURATION_INVALID`, and nothing is claimed.

**Recovery.** A refusal happens after the runner's claim (RW-C04), so the existing semantics apply unchanged. The dispatch is `WORKER_FAILED`, Processing Status becomes Failed in the claimed State, the State is not changed, and there is no automatic retry and no second model call. The operator corrects the configuration and resets Processing Status, and the stage then runs under the policy current at that moment. A refusal before the claim would need policy knowledge in the generic runner, so it is not done.

**In-flight changes.** A snapshot is immutable inside its stage, so a change made while a stage runs is seen by the next stage, not by this one:
- *Changed during a Process model call:* the Process Result may persist bound to the revoked policy. The next Review refuses it as stale before invoking its model.
- *Changed during a Review model call:* the Review Result may persist and move the Requirement to Ready. Ready approval, a worker Apply (each with its own fresh snapshot) and TSA admission refuse it as stale.
- *Changed between Review and Apply:* Apply's fresh snapshot refuses it before any relation or State write.
- *Changed after Apply's snapshot, before its Applied transition:* this window is **not closed**. Apply checks currentness before and after its writes, but both checks use the snapshot taken as the stage started. The window spans Apply's own Fibery reads and writes, with no model call, as it always has for single-shot `sdlc requirement apply`. A Requirement applied in this window is still refused at TSA admission, which reads the policy afresh.

Revocation is therefore effective at the next stage start, not instantaneously. No configuration transaction or file watcher is introduced.

## 4. Structured resolution evidence (Process contract)

The model may now return `resolutions`:

```json
{ "class": "SOURCE_GROUNDED" | "DEPENDENCY_GROUNDED" | "DELEGATED_DEFAULT",
  "issue": "the question or defect resolved, one line",
  "answer": "the adopted answer",
  "affected_sections": ["requirement", "detailed_behavior", ...],
  "sources": [ { "kind": "RAW" | "REQUIREMENT" | "DEPENDENCY",
                 "requirement_id": "<RAW or dependency ID; omitted for REQUIREMENT>",
                 "quote": "verbatim source text" } ],
  "policy_clause": "<clause_id, Class C only>",
  "justification": "concise semantic justification" }
```

**Product questions.** Each product question now carries `authority`, either `HUMAN_REQUIRED` or `INSUFFICIENT_EVIDENCE`, and `alternatives`, a list of single-line decision options. An `INSUFFICIENT_EVIDENCE` question needs at least two alternatives. Unresolved questions are never turned into resolutions.

**Deterministic checks.** Code checks the model's output before anything is persisted. Any failure is `INVALID_MODEL_OUTPUT` and nothing is written.

- **Shape:**
  - `issue`, `answer` and `justification` must be non-empty;
  - `affected_sections` must be a non-empty set of normalized section keys;
  - at least one source;
  - every quote at least 12 characters.
- **Class A:** sources are `RAW` or `REQUIREMENT` only, with no clause.
- **Class B:** at least one `DEPENDENCY` source, with no clause.
- **Class C:** an active policy for this Project, a `policy_clause` that names one of its clauses, and at least one source as applicability evidence.
- **`RAW` source:**
  - it must name an originating RAW of this Requirement (`Derived From`) that has exactly one attached Document;
  - the quote must occur in that RAW's Root content after whitespace normalization;
  - code records the RAW's entity id and the SHA-256 fingerprint of its content.
- **`REQUIREMENT` source:**
  - the quote must occur in this Requirement's *input* normative content: the Root and normative children Process consumed, never its own output;
  - code records the input-tree fingerprint.
- **`DEPENDENCY` source:**
  - it must name an existing DEPENDS_ON target, or a DEPENDS_ON this output proposes;
  - an AFFECTS-only peer is refused, because AFFECTS gives no normative authority;
  - the target must be a same-Project Standard in the comparison context;
  - the quote must occur in its normative tree as rendered for the model (Root and children);
  - code records its entity id and that rendered text's fingerprint.

The model never supplies an entity id or a fingerprint; code binds both. These checks prove identity, integrity, availability and citation existence only. A substring match is not semantic support, and a fingerprint is change detection, not a signature. Semantic justification and authority are the Reviewer's job (§6).

## 5. Process Result 0.6

0.6 is 0.5 plus:

- **`resolutions`:** each resolution as above, with its sources bound (`kind`, `requirement_id`, `entity_id`, `fingerprint`, `quote`).
- **`autonomy_policy`:** `{policy_id, fingerprint}` of the active policy for the Project when this iteration ran, or `null`. One binding per Result, not per resolution.
- **`product_questions[]`:** each carries `authority` and `alternatives`.
- **`rework_responses[]`:** each carries `resolution_index` (`null` or the index of the resolution it relies on) and `evidence` (citations, the same shape as resolution sources).
- **`run_input_identity`:** also covers the policy fingerprint when a policy is bound. With no policy it is the 0.5 digest, so an unchanged run with no policy is still recognised as nothing new.

On read-back, a 0.6 Result is held to its closed shapes and its class, clause and source-kind rules. A Class C resolution requires a bound policy. Its rework coverage rules are re-checked against the bound Brief (§7). Older versions stay readable under their own semantics. They carry none of these keys and are never read as having resolution evidence.

**Recovery.**
- `--resume-result` replays a persisted 0.6 iteration without a model call, exactly as recorded, bindings included. It is refused with `RESOLUTION_EVIDENCE_STALE` when the Result has a Class C resolution and the active policy is no longer the one it bound.
- A run whose policy changed is a new run input, so it is processed again rather than reported as unchanged.

## 6. Independent Review (Review Result 0.7)

**Before the reviewer runs**, for a 0.6 Process Result, code re-establishes every citation against current Fibery and the current policy:
- each RAW is still an originating RAW, with the same entity, fingerprint and quote;
- each DEPENDENCY is still a DEPENDS_ON edge or proposal, with the same entity, the fingerprint of its current rendered normative tree the recorded one, and the quote present;
- each REQUIREMENT citation carries the Result's own input-tree fingerprint;
- for Class C, the active policy is the bound one and still has the clause.

A changed source or policy is `RESOLUTION_EVIDENCE_STALE`. A mismatched identity, or a quote absent from an unchanged source (a forged or corrupted Result), is `RESOLUTION_EVIDENCE_INVALID`. Either way the reviewer is not invoked and nothing is written.

**The reviewer** receives each resolution as a claim, with its bound sources and, for Class C, the bound clauses and the human-only domains. It must return exactly one `resolution_verifications` entry per resolution:

```json
{ "resolution_index": 0, "outcome": "CONFIRMED" | "REJECTED" | "UNRESOLVED",
  "severity": "REJECTED only",
  "checks": { "issue_identified", "source_supports_answer", "authority_class_correct",
              "within_policy_clause", "consistent_with_raw", "consistent_with_related",
              "no_unsupported_obligation", "no_new_contradiction",
              "no_material_what_open", "testable_at_what_level" },
  "reason": "..." }
```

Each check is `PASS`, `FAIL` or `UNCERTAIN`. `within_policy_clause` is `NOT_APPLICABLE` exactly for Classes A and B. The outcome must agree with the checks:
- **CONFIRMED:** every check passes.
- **REJECTED:** at least one fails, and a severity is graded, which counts in the derived verdict like a confirmed finding.
- **UNRESOLVED:** none fails, at least one is uncertain, and no severity is given.

A response that does not agree with its checks is refused. So the Reviewer cannot confirm by assertion, and it cannot accept Process's class without checking authority, scope and support.

**What 0.7 adds.** Review Result 0.7 is 0.6 plus:
- `reviewed_resolutions`, an exact copy;
- `reviewed_autonomy_policy`;
- `resolution_verifications`;
- the extended question and rework-response shapes.

Every consumer checks the copies against the bound Process Result. The Reviewer still never rewrites content and never states a verdict or a WHAT status.

## 7. WHAT clearance and Rework

**WHAT status.** It is derived by code (WI-1) and is `BLOCKED_ON_WHAT` when anything WI-1, WI-2 or WI-4 already blocks on, or when:
- a resolution is not CONFIRMED; or
- a CONFIRMED Class B resolution cites a dependency that is not a verified, bound direct DEPENDS_ON of this review (WI-4 §8). An AFFECTS peer, a rejected or unbindable proposal, or a transitive dependency never clears.

A confirmed resolution clears nothing by itself: it only stops being a blocker. Any open material question still blocks. The status is recomputed and checked on every read-back.

**Rework (WI-2 preserved).**
- **Brief item:** a resolution the Review did not confirm becomes a Brief item of category `RESOLUTION` (reference letter `A`, blocks WHAT). It carries the class, issue, adopted answer, the outcome, the reviewer's reason, and a severity exactly when it was rejected.
- **Coverage:** every Brief item still receives exactly one response.
- **Rules for a 0.6 Process:**
  - `RESOLVED` of a material-WHAT item must name the resolution (`resolution_index`) that answers it. An unsupported RESOLVED is refused.
  - `resolution_index` appears only on RESOLVED.
  - `REBUTTED` must cite at least one evidence source, which is held to the checks of §4.
  - `ESCALATED` keeps the material question, as before.
  - An answer to an item that re-raises an unconfirmed resolution (a `RESOLUTION` item, or a claim re-raising one) needs authority outside the Requirement's own text. That text now holds the unconfirmed answer the earlier iteration wrote, so it cannot become its own source. RESOLVED must name a resolution that cites the RAW or a dependency, or is a delegated default. REBUTTED must cite the RAW or a dependency.
- Rework iteration authority and the Ready → Process route are unchanged; nothing reworks automatically.

## 8. Currentness

Smallest checks, reusing WI-1 and WI-4:

| Point | Check |
|---|---|
| Process persistence | The policy snapshot is read as the stage starts (§3.4); the deterministic citation checks of §4 run against the captured input; the existing input re-read guards stay. |
| Process recovery | `--resume-result` refuses a changed policy for a Class C Result (§5). |
| Review | Every citation and the policy are re-established (§6). |
| Ready approval, Apply (before and after its writes), TSA admission | The Review must verify exactly the bound Process Result's resolutions and policy binding. For a Class C resolution, the active policy must still be the bound one (changed, removed, revoked or disabled → stale). Every RAW and DEPENDENCY citation must still resolve to the same entity with the same fingerprint (changed → stale). WI-4 continues to bind dependency trees. |

Refusal codes:
- **Ready, Apply:** `RESOLUTION_EVIDENCE_STALE`, `FIBERY_READ_FAILED` when a source cannot be read, or `INVALID_REVIEW_RESULT` when a citation's identity or quote does not hold against an unchanged source.
- **TSA:** `REQUIREMENT_NOT_ADMISSIBLE`, with `CycleResultCode.FIBERY_READ_FAILED` for a read failure.

A historical resolution is never reinterpreted under a newer policy. Any change refuses until a new Process and Review bind the current one.

## 9. Historical compatibility

- Process Results 0.1–0.5 and Review Results 0.1–0.6 stay readable and are never rewritten.
- None of them carries resolution evidence, and none is interpreted as having any.
- A 0.6 Process Result reviewed by anything other than a 0.7 Review Result is incoherent and refused.
- Consumers check resolution currentness only for 0.7 evidence. Older evidence is governed by the WI-1 and WI-4 rules exactly as before.

## 10. Refusal codes

| Code | Where | Meaning |
|---|---|---|
| `INVALID_MODEL_OUTPUT` | Process, Review | A resolution, citation, policy clause, question authority, rework binding or resolution verification fails the closed contract or the deterministic checks. |
| `RESOLUTION_EVIDENCE_STALE` | Process (resume), Review, Ready, Apply | A cited source or the bound policy changed, was removed or is no longer active. |
| `RESOLUTION_EVIDENCE_INVALID` | Review | A persisted citation's identity or quote does not hold against an unchanged source. |
| `AUTONOMY_POLICY_INVALID` | worker Process, Review, Apply | The policy configuration could not be read or validated as the stage started (§3.4). Single-shot commands report the same failure as a configuration error before any Fibery read. |
| `INVALID_PROCESS_RESULT`, `INVALID_REVIEW_RESULT` | all | A persisted 0.6/0.7 artifact is malformed or the copies disagree with the bound Result. |
| `REQUIREMENT_NOT_ADMISSIBLE` | TSA | Any of the above at admission. |

## 11. Required human decisions before any activation

1. Which Project(s) may receive delegated defaults.
2. The exact clauses: applicability, the single permitted outcome, boundaries, exclusions and required evidence. Each must stay clear of the human-only domains.
3. Who may approve, and how that approval is recorded beyond the operator configuration, if the configuration attestation is judged insufficient.
4. Whether WI-6 may act on Ready automatically at all, and under which verdicts and WHAT statuses. This delta grants none.

## 12. Non-goals and limits

- **Not built:** WI-6, automatic Ready decisions, automatic Rework or Approval, Applied-Requirement revision, new States, roles, databases or relation types, a generalized policy engine, Delivery Planning and TSA formatting.
- **What each citation is checked against.** A RAW citation is checked against the RAW's Root Document. A dependency citation is checked against the dependency's rendered normative tree, the same text the model was shown. Children of a RAW are not read, as before.
- **REQUIREMENT citations are checked once, at Process.** Their existence is checked at Process against the input it consumed. Once Process rewrites the Root that input is gone, so Review and later consumers check only that the citation carries the Result's own input-tree fingerprint.
- **The policy attestation is not authenticated.** It is the operator configuration, as above. `approved_by` is a record outside the fingerprint, so changing it needs no re-approval.
- **Earlier unreviewed model text.** Text a Process iteration wrote into the Requirement is that iteration's output. Code keeps a rejected or unresolved resolution from citing itself back (§7), and both prompts tell the models such text is not authority. An answer written outside `resolutions` (unchanged since WI-1) remains a reviewer judgement and is not checked by code.
- **Non-Applied dependencies.** At Process, a dependency citation needs only an existing or proposed DEPENDS_ON to a same-Project Standard. Approved standing is enforced later: clearance needs a verified, bound dependency (WI-4), and Apply refuses one that is not Applied.
- **TSA policy carriage.** Admission reads the policies from `PolicyBoundEvidence`. A reader that does not carry them delegates nothing, so a delegated default is refused as stale.
- **Revocation is per stage, not instantaneous.** A change made during a stage is seen by the next stage. The one window no later stage gate covers before a State write is Apply's, between its snapshot and its Applied transition. TSA admission still refuses there (§3.4).
- **Nothing is live-verified.** No model has been run against the new prompts and no Fibery round-trip of the 0.6/0.7 payloads has been made.
