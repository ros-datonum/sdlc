# Requirement Autonomous Ready Decision — v0.1 (delta)

**Status:** IMPLEMENTED ON BRANCH `impl/requirements-autonomous-ready`; OFFLINE-VERIFIED ONLY; NOT LIVE-VERIFIED. No Project is authorized anywhere.
**Authorization:** human instruction "Implement WI-6 — Autonomous Ready Decision", for baseline `70fe70d00e5c8320b951e93dc65a7a51248c2f28`. The approval record is that instruction; no signature is claimed. It authorizes the decision *capability* only. It does not activate automatic Ready decisions for any Project, and no coding agent may activate them.
**Amends, narrowly and only as stated here:**
- Requirement-Lifecycle-Ownership-v0.2 and Requirement-Lifecycle-v0.2-Current §2, §3 and §8: `Standard + Ready` may be decided by the delegated decider (§9), and `State = Apply` no longer necessarily records a human approval (§10);
- Requirement-State-Worker-Contract-v0.1 §8: the runner gains one opt-in Ready step (§9);
- Standard-Requirement-Ready-Spec-v0.1: a delegated caller with a pre-write guard and the new code `DECISION_BASIS_CHANGED` (§11);
- Requirement-Autonomous-Resolution-v0.1 §1, §11.4 and §12, and Requirement-Rework-Brief-v0.1 §1 and §5: "no automatic transition, rework or approval" now holds only where no Ready delegation is approved.

Those documents are unchanged on disk. Where this delta and they disagree, this delta governs for the listed points only. WI-1's material-WHAT gate, WI-2's Rework Brief, WI-4's dependency bindings and WI-5's resolution and policy rules are preserved unchanged.

## 1. Purpose and boundary

The worker may now decide at Ready, deterministically, for a Project whose operator explicitly authorized it. There are exactly three decisions:

| Decision | Effect | Uses |
|---|---|---|
| `AUTO_APPROVE` | `Ready -> Apply` | the existing approval, without acknowledgement |
| `AUTO_REWORK` | `Ready -> Process` | the existing rework transition |
| `HUMAN_REQUIRED` | stays at `Ready` | nothing is written |

There is no new State, database, model role, model call or worker service. The decider never calls a model. It never acknowledges a verdict, overrides WHAT, invents a policy or ignores invalid or stale evidence. The lifecycle is unchanged:

```text
RAW -> Decomposition -> Process -> Review -> Ready
                                               -> Process (REWORK)
                                               -> Apply   (APPROVE) -> Applied -> TSA
```

The existing human transitions in Fibery, and the admin commands `sdlc requirement approve` and `rework`, keep their established behaviour.

## 2. Two separate permissions

| | Table | What it permits |
|---|---|---|
| WI-5 delegated product defaults | `[autonomy]` | Process may adopt a `DELEGATED_DEFAULT` within an approved clause. It permits no State transition. |
| WI-6 delegated Ready transitions | `[ready_decisions]` | The worker may decide at Ready for one Project, within the stated limits. |

Either may be approved without the other:
- A Project may have source-grounded resolutions with no Ready delegation, and Ready delegation with no `[autonomy]` policy. Classes A and B need no policy.
- A WI-5 policy never implies a Ready delegation.
- A Ready delegation never makes a WI-5 default current.

## 3. Ready delegation authority

### 3.1 Boundary and shape

Delegation lives in `config/sdlc.toml`, table `[ready_decisions]`, which is the same operator-controlled boundary as `[autonomy]`. Its shape is closed: unknown keys are refused.

```toml
[ready_decisions]
mode = "disabled"                      # or "enabled"

[ready_decisions.projects.<PROJECT_CODE>]   # only under mode = "enabled"
authorization_id = "<identifier>"
approved_by = "<who approved it>"            # a record, outside the fingerprint
approved_fingerprint = "<64 hex>"            # SHA-256 of the canonical content
auto_approve = true | false
auto_rework = true | false
max_rework_rounds = <1..5>
max_issue_repeats = <0..2>
```

- **Canonical content:** the Project code, `authorization_id`, both flags and both limits. It is serialized as sorted-key, compact UTF-8 JSON and hashed with SHA-256.
- **Load refusals:** the table is refused whole when:
  - the fingerprint differs from `approved_fingerprint`;
  - any key is missing;
  - a limit is out of range or not an integer (a boolean is not an integer);
  - a flag is not a boolean;
  - both flags are false;
  - an `authorization_id` is shared between Projects;
  - an identifier or Project code is invalid;
  - `mode` is missing or unknown;
  - `mode = "disabled"` still names projects.
- **Absence:** a missing table means disabled.
- **No defaults:** every limit must be stated. The ceilings (5 rounds, 2 repeats) are code constants. They bound what any approval can allow; they are not defaults.

### 3.2 What the fingerprint is

The fingerprint is change detection. It shows that the content is the content that was approved. It is not a signature, not an authentication and not independent proof that a human approved anything. The configuration attests delegation exactly as it attests the model runtime. `approved_by` is informational and is outside both the fingerprint and the decision identity.

### 3.3 Default deny and activation

- **Default:** the repository ships `mode = "disabled"`, no Projects. That is the default and the only committed state.
- **No agent activation:** no coding agent may enable delegation by editing this file, a fingerprint or a flag.
- **Fixtures are not configuration:** test fixtures authorize only test Projects inside the test suite.
- **What activation requires:** the operator writes the table, with controlled write access to the file (§16).

## 4. AUTO_APPROVE

`AUTO_APPROVE` is permitted only when every condition holds, checked in this order on a fresh read.

**Identity and authority**
- A. The Requirement is Standard.
- B. It is in Ready with Processing Status `Succeeded`, meaning the runner's own Review cycle completed.
- C. The Project's authorization has `auto_approve = true`.

**Current evidence.** These are the existing Ready approval checks, via `read_ready_evidence`:
- D. The latest Process Result is current-format and current.
- E. The latest Review Result is current-format and current.
- F. The Review binds the latest Process Result's iteration and output fingerprint, the current Root and the current normative tree. Its reviewed tree is that Process Result's output tree.
- L. Every cited RAW and dependency source is unchanged, and the bound WI-5 policy is still active.
- M. Every WI-4 dependency binding is the version reviewed, and the DEPENDS_ON edges are unchanged.
- N. The WHAT, rework and resolution evidence is coherent with the bound Process Result.

**Review content.** Derived by code, never taken from a model:
- G. The derived verdict is `PASS`.
- H. The derived WHAT status is `CLEAR`.
- I and K. No product question was confirmed open by the Review, whether material or not. The Review added no material WHAT question. Process escalated no rework item.
- J. Every resolution verification is `CONFIRMED`.
- The Review left nothing actionable (§5) and nothing unresolved: no verification of any kind is `UNRESOLVED`.
- No earlier Review of the identical normative output derived a different verdict or WHAT status (§8, `CONFLICTING_REVIEWS`).

**The transition.**
- O. The transition goes through `approve_standard_requirement` with no acknowledgement, given a guard (§11).
  - That function re-reads everything and repeats every human-approval check. Without an acknowledgement it refuses anything but `PASS`, so a misclassification cannot approve a non-PASS verdict.
  - Its guard then requires the fresh evidence identity to equal the decided one. It also re-reads the configuration and requires the same Ready authorization binding and the same autonomy-policy identity.
- P. No acknowledgement, exception or risk acceptance is ever made or required.

WI-6 is stricter than human approval:
- An INFO finding is compatible with `PASS`. Anything rejected, unresolved, escalated or confirmed open is not.
- A human may still approve any verdict by acknowledging it. The decider never does.

## 5. AUTO_REWORK

`AUTO_REWORK` is permitted only when:
- the evidence is current (D–F and L–N as above);
- the Review establishes a WHAT status (pre-WHAT-gate evidence goes to a human);
- nothing in the latest Review is for a human (§6) or ambiguous;
- at least one **actionable** item exists:
  - a confirmed Process finding, or a new Review finding, graded WARNING or BLOCKING;
  - a REJECTED relation proposal, rework answer, existing dependency or resolution;
  - a product question REJECTED as answered by another Requirement that is not yet a verified, bound dependency;
- the Project's authorization has `auto_rework = true`;
- the history permits another round (§7–§8).

The transition is `rework_standard_requirement` with a guard. With a guard it reads the evidence again under the decision's policies. The evidence must still be current and identical, and the configuration unchanged.

The next iteration is the existing route: the reset automation sets `Not Processed`, and Standard Process runs as an authorized new cycle (CR-002) with the WI-2 Rework Brief. No model is invoked at Ready.

An automatic rework never:
- creates a Requirement;
- changes a policy;
- chooses an answer;
- sends a confirmed human product decision back to Process.

## 6. HUMAN_REQUIRED

The Requirement stays at Ready, with its State and Processing Status untouched, whenever:

| Reason | When |
|---|---|
| `NOT_DELEGATED` | The Project has no Ready authorization. The evidence is not even read. |
| `APPROVAL_NOT_DELEGATED` | It would be approved, but `auto_approve = false`. |
| `REWORK_NOT_DELEGATED` | It has actionable feedback, but `auto_rework = false`. |
| `EVIDENCE_NOT_CURRENT` | Any refusal of the current-evidence checks: stale Root, child, Process, Review, dependency, source or policy; legacy or incoherent evidence; no WHAT status. The refusal code is reported. |
| `HISTORY_INVALID` | The Review lineage cannot be read or traced (§8). |
| `HUMAN_PRODUCT_DECISION` | A product question was confirmed open, the Review added a material WHAT question, or Process escalated a rework item. |
| `AMBIGUOUS_REVIEW` | Any verification is `UNRESOLVED`. |
| `NOTHING_ACTIONABLE` | Not approvable and nothing that a rework could address. |
| `TRANSITION_REFUSED` | The existing validation refused the transition on its own fresh read. |
| progress stops (§7–§8) | The budget is spent, no progress was made, or the rework oscillates. |

Each record names:
- the Requirement and its entity;
- the Review iteration;
- the reason codes, with item references such as `R0002.F0`;
- a next human action.

There is no Escalated State.

## 7. Bounded iterations

- **Rework rounds** = (number of Review Results) − 1. A round is a completed Review followed by another Process, whoever started it. It is counted from the persisted history, so a restarted worker counts exactly the same. Nothing resets it: not a restart, not a policy change, not a configuration change. Human reworks count too, because the history does not durably say who started a round.
- **`REWORK_BUDGET_EXHAUSTED`:** rounds ≥ `max_rework_rounds`.
- **`max_issue_repeats`:** how many consecutive later Reviews may still report one open issue. With 0, an issue still open after one rework stops automation.

Test fixtures use 2 rounds and 0 repeats. No production default exists.

## 8. Progress and oscillation

All signals are deterministic over the persisted lineage:
- every Review Result, oldest first;
- for each one, the Process Result it binds by iteration and output fingerprint;
- strictly increasing Process iterations.

A model's own claim of progress is never used. An iteration number or a changed fingerprint alone is never progress.

**Open issues.** The open issues of one Review are the actionable items of the WI-2 Brief built from it, excluding:
- findings graded INFO or REJECTED;
- product questions that do not block.

**Issue keys:**
- a relation: its kind and exact target;
- anything else: its family (finding, question or resolution), kind, Requirement ID and normalized text;
- a `REWORK_CLAIM`: the key of the item it originally re-raised, followed through every persisted Brief. A claim whose origin cannot be traced is `HISTORY_INVALID`.

Text keys are exact after normalization. So a reworded issue counts as a new key: that can only miss a repetition, never invent one, and the round budget still bounds every loop.

| Stop | Detects |
|---|---|
| `NO_INDEPENDENT_PROGRESS` | After a rework, the latest Review confirmed no RESOLVED or REBUTTED answer to the previous Review's items. A confirmed escalation is not progress. |
| `UNCHANGED_NORMATIVE_OUTPUT` | The reworked output equals the previous reviewed output. This covers a rework over unchanged input. |
| `RETURNED_TO_EARLIER_OUTPUT` | The output equals an older reviewed output: content oscillation. |
| `REPEATED_ISSUE_SET` | The latest open-issue set equals an earlier one: identical unresolved findings. |
| `REINTRODUCED_ISSUE` | An issue open, then settled, then open again (A, then B, then A). |
| `REPEATED_ISSUE` | An issue open in more than 1 + `max_issue_repeats` consecutive Reviews. This covers repeatedly rejected rework answers, repeated unsupported answers (same resolution issue and answer) and repeated dependency conflicts (same edge). |
| `CONFLICTING_REVIEWS` | Approval only: an earlier Review of identical output concluded differently. |

## 9. Runner integration

- **Composition:**
  - `sdlc worker run` reads `[ready_decisions]` at start. A broken table is `WORKER_RUNNER_CONFIGURATION_INVALID` before any claim.
  - If delegation is disabled or absent at start, no Ready step is composed, and the runner is exactly the RW-C04 runner: no Ready query, no extra read.
  - If it is enabled, the runner holds one `ReadyDecider`.
- **Priority:**
  - Each cycle polls the four machine routes first. Only a cycle with no eligible machine work gives the Ready step its turn, so Process, Review and Apply are never starved.
  - The Ready step runs inside the same workspace lock and sequential loop: no second poller, service or lock.
- **Each Ready step:**
  1. Reads both tables afresh. A disabled table means no decision and an idle cycle. An unreadable or invalid one is `READY_FAILED`, a waiting outcome with no fallback.
  2. Runs one query for `Standard + Ready + Succeeded`: one page, bounded like the machine query (`ELIGIBLE_QUERY_LIMIT`), ordered by `fibery/id` and starting after the decider's in-memory cursor. This is Fibery's documented cursor pagination (`q/order-by` `fibery/id` ascending, `[">", ["fibery/id"], "$after"]`). The machine query is unchanged.
  3. Decides the lowest public id on that page not already decided under the same configuration identity, after re-reading it.
  4. If the page holds nothing left to decide, the cycle is idle. A full page moves the cursor past its last row, and a short (last) page moves it back to the first page.
- **Discovery completeness:**
  - Each call reads exactly one page, so an idle worker never scans the whole workspace in one cycle.
  - Every Ready candidate is reached without a restart, unless a persistently failing candidate is ahead of it (§17). A candidate is decided within as many idle cycles as there are pages, plus one cycle per undecided candidate ahead of it, however many Requirements of other or non-authorized Projects were decided before it. A candidate whose decision ends `READY_FAILED` or `READY_WITHDRAWN` is not remembered, so it is retried after the poll interval.
  - `fibery/id` never changes, so a row leaving Ready does not shift any other row past the cursor. A candidate that appears behind the cursor is reached when the cursor wraps.
- **Eligibility:**
  - Only `Ready + Succeeded` is a candidate: the runner's own Review cycle completed.
  - `Ready + Not Processed` (a Review run outside the runner), `Processing` and `Failed` are not candidates and stay with a human.
- **Processing Status:**
  - The decider never writes Processing Status.
  - Its only write is the State. The RW-C04 reset automation sets `Not Processed` on entering `Process` or `Apply`, exactly as for a human transition.
  - `HUMAN_REQUIRED` leaves `Succeeded` visible.
- **No tight loop:**
  - The decider remembers, in memory only, the entities it decided (`READY_DECIDED`, `READY_ESCALATED`, `READY_UNCERTAIN`) under the current configuration identity. A cycle with nothing new to decide is idle and waits the poll interval.
  - The memory is dropped for an entity when:
    - the runner claims a machine cycle for it (only such a cycle returns it to `Ready + Succeeded`);
    - the Ready page covering its `fibery/id` no longer returns it;
    - the configuration identity changes (Ready authorizations and autonomy policy bindings).
  - It is no lifecycle state: a restart starts empty and decides every Ready Requirement once more from Fibery, under the same durable history and budget.
- **Cycle outcomes:**

| Outcome | Normal | Waits |
|---|---|---|
| `READY_DECIDED` (transition confirmed) | yes | no |
| `READY_ESCALATED` (`HUMAN_REQUIRED`, or the transition was refused by the existing validation) | yes | no |
| `READY_WITHDRAWN` (State, evidence or authority moved; nothing written; not remembered) | yes | yes |
| `READY_UNCERTAIN` (State write failed or did not read back; remembered, not repeated) | no | no |
| `READY_FAILED` (configuration or Fibery read failed; nothing decided) | no | yes |

**Cost.** Each idle cycle with delegation enabled adds:
- one configuration read;
- one bounded Fibery query.

Each decision adds:
- reads of the Requirement and its Project;
- the evidence reads of an approval;
- one content read per earlier Process and Review Result.

A worker start re-decides each Ready Requirement once, including those of non-authorized Projects (`NOT_DELEGATED`, which needs only the Requirement and Project reads).

## 10. Provenance and auditability

**`State = Apply` no longer necessarily means a human approved.** It means an authorized Ready decision was made: a human's, or the decider's under operator delegation. Apply already could not tell which, and it revalidates identically either way.

**What distinguishes them, and where it lives:**

| Evidence | Durable? | What it shows |
|---|---|---|
| The structured decision record (`ReadyDecisionRecord`), printed by the runner for every decision | **No.** It is runner output only. | Requirement ID and entity, Project code and entity, decision, Review iteration and content fingerprint, Process iteration and fingerprint, Root and tree fingerprints, derived verdict and WHAT status, authorization id and fingerprint, bound autonomy policy, the currentness checks, the budget and progress assessment, the reasons, and, separately, the transition outcome, its result code and the State reached. |
| Fibery's own entity history of the State change | Yes, in Fibery. | Which Fibery identity changed the State and when. It distinguishes the worker from a human only if the worker runs under its own Fibery identity. |
| The persisted Process and Review Results, and the configuration | Yes, immutable history. | The decision is a deterministic function of them, so it can be re-derived. That proves what *would* have been decided, not that the worker made the transition. |

- **No durable audit sink:** this delta introduces none. There is no approval artifact, event store or database, and no audit trail is fabricated.
- **Operational logging requirement:** before activation, the operator must retain the runner's output as the decision log, and should run the worker under a dedicated Fibery identity.
- **Content-free records:** no record quotes Requirement content. Reasons carry codes, item references, iterations and counts. A read-failure report carries the refusal code and Fibery's causes, never an evidence message that could name a Document.

## 11. Currentness and concurrency

**Order of checks.** Immediately before its single State write, a decision re-reads:
1. the Requirement;
2. all the evidence, through the existing approval or rework function;
3. the Requirement's Project, and then the configuration, through the guard.

**Final binding.** The guard compares the freshly read Requirement with the one decided on: the same Requirement ID, Type and State, the same Project entity, and Processing Status still `Succeeded`. It then re-reads that Project and requires the same Project Code, and requires the Ready authorization for that Code to be the decided binding. An automatic transition is written only for the same Requirement, in the same authorized Project, in an eligible Processing Status, on the same evidence. An authorization is never carried over to another Project, or to the same Project under another Code.

**On conflict it refuses:**
- a human moved `Ready -> Apply` or `Ready -> Process`;
- another worker or command changed the State;
- the Root, a child, the Process or Review evidence, a dependency or a cited source changed;
- the WI-5 policy or the Ready authorization changed;
- the Requirement moved to another Project, or its Project's Code changed;
- its Processing Status left `Succeeded` (`Processing`, `Failed` or `Not Processed`);
- its Project can no longer be read, or no longer exists.

A Requirement withdrawn this way is decided afresh at a later cycle, under the Project and authorization it then has, if it is still a candidate.

Each refusal is `WITHDRAWN` or `TRANSITION_REFUSED`. It writes nothing and never overwrites a human's later decision. A human's `Ready -> Apply` made first is reported `REQUIREMENT_ALREADY_APPROVED` and left alone.

New code `DECISION_BASIS_CHANGED`: the guard found that the evidence identity, the Requirement's Project or Processing Status, the Project's Code, or the configuration moved between the decision and its write.

**Remaining limit.** Fibery has no compare-and-set. Between the guard's reads (the Requirement with its Project and Processing Status, the Project and the configuration) and the write there is a window of a few milliseconds, the same one the admin `approve` and `rework` commands have always had. A human change landing exactly inside it can be overwritten. No distributed lock is introduced. The workspace runner guard still excludes a second cooperating worker on the same host; multi-host operation remains unsupported.

## 12. Policy lifetime

WI-5 §3.4 is preserved:
- Each decision reads `[ready_decisions]` and `[autonomy]` afresh, as its snapshot.
- A disabled, removed or malformed table never falls back to cached authority.
- A configuration change re-opens remembered decisions, never resets the round budget, and never makes old evidence current.
- Disabling delegation while the worker runs returns Ready to the human boundary at the next idle cycle, without changing any State.
- Enabling it in a worker that started disabled needs a restart.

## 13. Recovery and idempotency

| Failure | Result |
|---|---|
| Ready evidence, history or Project read | `READY_FAILED`. Nothing decided; retried after the poll interval. |
| Configuration read (start / later) | `WORKER_RUNNER_CONFIGURATION_INVALID` / `READY_FAILED`. |
| Immediately before the write (guard) | `DECISION_BASIS_CHANGED`, `WITHDRAWN`. Nothing written. |
| State write raises | `FIBERY_WRITE_FAILED`, `UNCERTAIN`. Reported, remembered, not retried by this worker. |
| Read-back missing or different | `FIBERY_WRITE_FAILED` / `VALIDATION_FAILED`, `UNCERTAIN`. |
| Interrupted worker before the write | Nothing durable happened. The restart decides afresh. |
| Interrupted worker after the write | The State is `Apply` or `Process`, so it is not a Ready candidate. The machine route runs normally and no transition is repeated. |
| Resumed processing after `AUTO_REWORK` | An ordinary Process cycle from `Not Processed`, with the Brief. Its next Ready is decided afresh. |

An uncertain transition is never silently retried by the worker that saw it. If the State still reads Ready after a restart, the restarted worker makes a new decision from fresh evidence. No general recovery engine is introduced, and the RW-C04 recovery rules are unchanged.

## 14. Compatibility

- **WI-1:** `what_clearance`, the derived status and every Ready, Apply and TSA refusal are unchanged. The decider only adds conditions.
- **WI-2:** an automatic rework is the same `Ready -> Process`. The Brief is built and answered exactly as before, and the budget and issue keys are derived from it.
- **WI-4:** dependency currentness is checked by the same `require_current_dependencies` at decision time and again inside the approval.
- **WI-5:**
  - resolution and policy currentness use the same `require_current_resolutions` with a fresh snapshot;
  - the stage snapshots of Process, Review and Apply are untouched;
  - Class C defaults are never activated by WI-6.
- **Human and admin decisions:**
  - Fibery transitions and `sdlc requirement approve` / `rework` are unchanged.
  - The `guard` parameter is used only by the decider.
  - Approval of a non-PASS verdict by named acknowledgement remains a human-only act.
- **Legacy evidence:** pre-0.4 Review Results establish no WHAT status and always go to a human. Older history stays readable and is used only for lineage, never reinterpreted.

## 15. Codes

| Code | Where | Meaning |
|---|---|---|
| `DECISION_BASIS_CHANGED` (new) | Ready decision, delegated only | The guard found the evidence, the Requirement's Project or Processing Status, the Project's Code, or the configuration moved before the write. |
| `READY_DECIDED`, `READY_ESCALATED`, `READY_WITHDRAWN`, `READY_UNCERTAIN`, `READY_FAILED` (new) | Runner cycle | §9. |
| Every existing Ready refusal | Ready decision | Unchanged, and reported as the transition code. |

## 16. Operator decisions required before any live activation

1. Which Project(s), if any, receive Ready delegation, and whether approval, rework or both.
2. The limits (`max_rework_rounds`, `max_issue_repeats`) within the code ceilings.
3. Who may write `config/sdlc.toml`, and how that write access is controlled. The fingerprint is not authentication.
4. Whether the operational decision log (§10) and Fibery's own history are sufficient provenance, or a durable decision artifact is required. That would need a new authorization.
5. Whether the worker runs under a dedicated Fibery identity, so that machine transitions are distinguishable in Fibery's history.
6. Whether to run a live probe first on temporary state:
   - the `Standard + Ready + Succeeded` page query at volume: `q/order-by` on `fibery/id` and the `>` cursor were read live once, read-only (below), but never over more than 100 Ready rows;
   - the reset automation on a machine-made `Ready -> Apply` / `Ready -> Process`;
   - the end-to-end decision path, including Process Result 0.6 and Review Result 0.7 serialization, which remain not live-verified.

## 17. Non-goals and limits

**Not built:**
- new States, databases or roles;
- a Ready model;
- a second orchestrator or scheduler;
- Applied revision;
- autonomous TSA;
- Delivery Planning;
- graph-wide reprocessing;
- policy activation;
- a distributed lock;
- an approval service;
- a durable decision record.

**Limits:**
- **Issue identity is textual.** A reworded issue is new, so repetition can be missed (never invented), and the round budget is the backstop.
- **Human rounds count.** They consume the budget, because the history does not durably record who started a round.
- **Remembered decisions.**
  - A Requirement that leaves `Ready + Succeeded` and returns without passing through this worker's own machine cycle (impossible in single-worker operation, but possible after manual recovery) keeps its remembered decision until the next restart or configuration change. That errs toward the human boundary.
  - The decider's own forgetting compares `fibery/id` values as strings, assuming Fibery orders them the same way. If it does not, the worst case is one extra re-decision or a remembered entry kept until restart. Neither makes a transition without every check.
  - The cursor is in memory: a restart begins at the first page again.
- **A persistently failing candidate.** A Ready candidate whose re-read or evidence read fails every time (`READY_FAILED`) is chosen first on its page at every cycle. That holds back the candidates after it, on its page and on later pages, until the read succeeds, the Requirement leaves `Ready + Succeeded`, or delegation is disabled. Every such cycle is reported `READY_FAILED` with the Requirement named, and the runner waits the poll interval between them, so the stall is visible to the operator and never a tight loop. The machine routes behave the same way with a persistent `CANDIDATE_READ_FAILED`.
- **Concurrency window.** Fibery has no compare-and-set, and the window in §11 remains.
- **Live evidence for the cursor: one read-only probe.** On 2026-10-21 the production `find_eligible_requirements_after` ran against the configured workspace with `fibery.schema/query` and `fibery.entity/query` only, nothing written:
  - the exact Ready query (26 `Standard + Ready + Succeeded` rows) at the production page size, and at page sizes 1, 2, 3, 7 and 13 to force multi-page traversal;
  - the same method over every Type and State route present, for `Succeeded` (31 rows) and `Not Processed` (7 rows), at page sizes 100, 7 and 3;
  - a cursor at the last id, and cursors naming no entity at both ends of the range.
  Every traversal returned exactly the independently read reference set, with no duplicate and no gap, ordered as Python orders the `fibery/id` strings. Pages ended on a short page, an empty page following an exactly full one. Not observed live: more than 100 Ready rows at the production page size, and rows changing between pages (fakes only).
- **Not live-verified otherwise.** No live Fibery write, live model run, live worker run or new Project was made.
