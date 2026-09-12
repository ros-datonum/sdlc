# RW-D01 — Documentation Reconciliation Boundary v0.1

**Status:** FROZEN IMPLEMENTATION BOUNDARY  
**Work item:** `RW-D01 — Reconcile canonical docs and README`  
**Frozen plan:** `d54db975e5cff73a2522598dfb1bc0727f45a523`  
**Date:** 2026-09-12

## 1. Purpose

RW-D01 is the final documentation reconciliation step of the rewrite. It changes documentation only. It must describe the behavior already independently verified in Blocks A–E and must not introduce new product behavior, lifecycle semantics, commands, Fibery schema, or downstream engines.

The documentation must make one distinction unambiguous:

```text
verified/current implementation
!=
future SDLC lifecycle architecture
```

The full Project lifecycle remains the product architecture, but this rewrite implements only the corrected Requirement foundation, state-driven Requirement lifecycle, project bootstrap, and their verified supporting primitives.

## 2. Exact primary documentation set

RW-D01 must reconcile these files:

```text
README.md

docs/architecture/SDLC-MVP-v0.4-Frozen-Architecture.md
docs/architecture/Requirement-Lifecycle-v0.1-Checkpoint.md

docs/specs/Standard-Requirement-Process-Spec-v0.1.md
docs/specs/Standard-Requirement-Review-Spec-v0.1.md
docs/specs/Standard-Requirement-Ready-Spec-v0.1.md
docs/specs/Standard-Requirement-Apply-Spec-v0.1.md

docs/specs/Project-Init-Spec-v0.3.md
docs/specs/Project-Requirement-Add-Spec-v0.3.md
```

Create these two versioned current documents:

```text
docs/architecture/SDLC-MVP-v0.5-Current-Architecture.md
docs/architecture/Requirement-Lifecycle-v0.2-Current.md
```

Do not create another architecture version or lifecycle checkpoint name.

Additional docs may be edited only for a concrete stale cross-reference found while reconciling this exact set. Every additional file must be named and justified in the completion report.

Expected production/test code changes:

```text
NONE
```

## 3. Historical-doc policy

Do not rewrite history.

`SDLC-MVP-v0.4-Frozen-Architecture.md` remains the historical frozen architecture that described the pre-rewrite baseline. Change only its top status/front-matter area enough to state clearly:

```text
HISTORICAL / SUPERSEDED FOR CURRENT REQUIREMENT OPERATIONS
Current successor: SDLC-MVP-v0.5-Current-Architecture.md
```

Its historical body may remain intact.

`Requirement-Lifecycle-v0.1-Checkpoint.md` likewise remains historical. Change only its top status/front-matter area enough to state clearly:

```text
HISTORICAL / SUPERSEDED FOR CURRENT REQUIREMENT OPERATIONS
Current successor: Requirement-Lifecycle-v0.2-Current.md
```

Do not rewrite its old lifecycle body to pretend the earlier manual flow never existed.

Any other old design document discovered during D01 may remain unchanged when it is already clearly historical/superseded and no current document links to it as operational authority.

## 4. Current architecture v0.5

`SDLC-MVP-v0.5-Current-Architecture.md` is the concise current architecture index.

It must preserve the full intended Project lifecycle as roadmap:

```text
REQUIREMENTS
→ UX / PRODUCT DESIGN (optional)
→ TECHNICAL SOLUTION ARCHITECTURE
→ DELIVERY PLANNING
→ DEVELOPMENT
→ SYSTEM VERIFICATION & HARDENING
→ RELEASE PREPARATION
→ DEPLOYMENT
→ POST-DEPLOY VALIDATION
→ ACTIVE
```

But it must label implementation status explicitly:

```text
VERIFIED NOW:
- project bootstrap
- RAW Requirement ingestion
- corrected RAW decomposition
- Standard Requirement Process
- Standard Requirement Review
- Ready human decision boundary
- deterministic Apply
- state-driven Requirement worker orchestration

NOT IMPLEMENTED BY THIS REWRITE:
- UX/Product Design engine
- Technical Solution Architecture engine
- Delivery Planner / backlog builder
- Epic/Story/Task implementation workflow
- System Verification engine
- Release Preparation engine
- Deployment engine
- Post-Deploy Validation engine
```

The Requirements section must use current concepts only:

```text
exported RAW source
→ Raw Draft
→ human Draft -> Process
→ RAW processing
→ 0..N Standard candidates
→ automatic candidate Process
→ automatic Review
→ Ready
→ HUMAN: Ready -> Process or Ready -> Apply
→ deterministic Apply -> Applied
```

It must explicitly state:

```text
Requirement = WHAT must be true
Technical Solution Architecture = HOW approved Requirements are satisfied
Delivery Planning = solution-specific executable decomposition
Task = concrete implementation/configuration/test/deployment work
```

Use `Standard-Requirement-Abstraction-v0.2.md` as authority for that boundary.

Fibery remains the canonical source of truth. Repositories contain code and code-native artifacts, not canonical Requirement mirrors.

Requirement lifecycle placement is `Type + State`; physical Document folders are not lifecycle semantics.

## 5. Current Requirement lifecycle v0.2

`Requirement-Lifecycle-v0.2-Current.md` is the operational/current lifecycle checkpoint.

It must describe the verified normal flow exactly:

```text
requirements-export (external)
→ sdlc project bootstrap
→ Project + initial RAW Draft + local consumer SDLC metadata/context
→ HUMAN: Raw Draft -> Process
→ worker: RAW Process
→ candidate Standard Draft
→ dispatcher automatically progresses exactly produced candidates Draft -> Process
→ worker: Standard Process -> Review
→ reset automation starts the Review processing cycle
→ worker: Standard Review -> Ready
→ STOP
→ HUMAN:
     Ready -> Process   REWORK
     Ready -> Apply     APPROVE
→ worker:
     Process path creates a new immutable Process/Review iteration and stops at Ready
     Apply path deterministically revalidates and moves Apply -> Applied
```

The only human-owned normal Requirement transitions are:

```text
Raw Draft -> Process
Standard Ready -> Process
Standard Ready -> Apply
```

Do **not** list Standard Draft -> Process as a human transition for candidates of an authorized RAW cycle.

Document `Processing Status` exactly as:

```text
Not Processed
Processing
Succeeded
Failed
```

Document the verified reset targets only:

```text
Raw + Process
Standard + Process
Standard + Review
Standard + Apply
```

Do not claim resets at Raw Review, Standard Ready, or Standard Applied.

Document the Standard Process -> Review handoff carefully:

- Process changes State to Review;
- workspace automation resets Processing Status for the new Review cycle;
- runner must not overwrite that reset with Succeeded for the old Process cycle;
- Review then runs as its own processing cycle.

Document that Failed is not automatically retried and stale/stuck Processing is not automatically stolen/recovered in v0.1.

Document `sdlc worker run` as the normal machine executor after a human State transition, not as lifecycle authority.

## 6. README exact operating story

Remove the stale claim:

```text
Only three capabilities are approved for the first implementation cycle
```

Replace the scope section with the actual verified foundation.

README must teach the primary project-start path first:

```bash
sdlc project bootstrap \
  --name "<Project Name>" \
  --requirements <RAW_REQUIREMENTS_FILE.md> \
  --context <PROJECT_CONTEXT_FILE.md> \
  [--target <PROJECT_DIRECTORY>] \
  [--code <PROJECT_CODE>] \
  [--description "..."]
```

Then explain that these remain deterministic inner/admin primitives:

```text
sdlc project init
sdlc project requirement add
```

Do not present `project init` + `requirement add` as the preferred normal onboarding sequence.

README must list the four managed consumer-project paths:

```text
.sdlc/project.yaml
.sdlc/project-context.md
AGENTS.md
.claude/CLAUDE.md
```

and state that bootstrap does not create model/auth/permission override files, skills directories, a RAW source copy, or a local canonical Requirements mirror.

README must teach State-driven Requirement execution as the normal flow.

The manual commands remain documented only under a heading such as:

```text
Admin / diagnosis / recovery commands
```

They include the existing processor/reviewer/apply and Ready compatibility commands, but wording must not say that manual invocation is an equivalent normal production workflow when the runner is absent.

If the worker is not running, automated machine stages simply do not progress; the operator may use bounded admin/recovery commands deliberately, but that does not change lifecycle ownership.

README must state the live prerequisite for the runner:

- `Processing Status` field/configuration exists;
- reset automation is configured and enabled;
- runner validates field/options but does not create/verify the automation on every startup;
- setup contract is in `docs/fibery/Worker-Runner-Setup-v0.1.md`.

Remove the stale sentence that RW-O04 E2E "is not claimed here". O04 is independently verified.

## 7. Process / Review / Ready / Apply specs

Do not rewrite their normative contracts.

Update stale top-level status/amendment notes so a reader is not told that verified capabilities are unimplemented.

### Process

`Standard-Requirement-Process-Spec-v0.1.md` must say the contract is implemented and independently verified after RW-R03/RW-O02/RW-O04, while retaining historical amendment traceability.

Add a short current control-surface note near lifecycle position or entry condition:

- in normal operation, state-driven dispatcher/runner invokes Process;
- a candidate produced by an authorized RAW cycle is progressed Draft -> Process by the dispatcher;
- manual normalize/process command is admin/recovery, not lifecycle authority.

### Review

`Standard-Requirement-Review-Spec-v0.1.md` must say implemented and independently verified after RW-R04/RW-O04.

Add a short note that normal Review begins automatically after successful Process moves State to Review and the Processing Status reset creates the new Review cycle.

### Ready

`Standard-Requirement-Ready-Spec-v0.1.md` must say implemented and independently verified after RW-O01/RW-O04.

Its existing normal-vs-admin distinction is retained.

Make explicit that after human `Ready -> Process` or `Ready -> Apply`, normal machine execution is picked up by the worker; the human does not invoke Process/Apply to make the decision authoritative.

### Apply

`Standard-Requirement-Apply-Spec-v0.1.md` remains deterministic/model-free.

Add a short current execution note that `Standard + Apply + Not Processed` is picked up by the state-driven worker and successful Apply reaches `Applied / Succeeded`.

Do not change Apply evidence/staleness semantics.

## 8. Project Init / Requirement Add positioning

Do not change the deterministic primitive contracts.

In both:

```text
docs/specs/Project-Init-Spec-v0.3.md
docs/specs/Project-Requirement-Add-Spec-v0.3.md
```

add a concise positioning note near Purpose/Command:

- the command remains directly supported;
- it is an inner deterministic primitive reused by `sdlc project bootstrap`;
- the normal new-project flow uses the outer bootstrap when both exported RAW requirements and project context are available;
- direct invocation remains valid for admin/incremental workflows within the primitive's existing contract.

Do not change primitive behavior or result codes.

For Requirement Add, do not imply that every later additional RAW must use bootstrap; `project requirement add` remains the normal primitive for adding an additional RAW source to an existing Project.

## 9. Physical Folder semantics

Current operational docs must state:

```text
Requirement Type + State = lifecycle placement
Requirement-contained Documents = canonical documents
fibery/Folder = not lifecycle authority
```

The old physical `Requirements/{Raw,Draft,Approved}` tree may be mentioned only as retired historical behavior.

Smart Folder/context views are optional human navigation and not runtime dependencies.

Do not reintroduce folder creation/move instructions.

## 10. Admin / recovery wording

Keep useful manual commands and recovery options documented.

But every current doc must distinguish:

```text
normal user intent = State transition in Fibery
normal machine execution = state-driven runner/dispatcher
admin/recovery = explicit CLI capability when deliberately invoked
```

Do not say that a CLI command owns human approval/rework authority.

Do not say that a Review verdict owns authority.

## 11. Downstream roadmap wording

The full architecture may describe future stages, but all current docs must label them as unimplemented where implementation status is discussed.

Do not claim current implementations for:

```text
UX/Product Design
Technical Solution Architecture
Delivery Planning
Development agent workflow
System Verification & Hardening
Release Preparation
Deployment
Post-Deploy Validation
```

Historical checkpoints may explain the intended next vertical slice, but current operational docs must not imply that slice was implemented by this rewrite.

## 12. Cross-reference authority

Current docs should preferentially link to:

```text
docs/specs/Standard-Requirement-Abstraction-v0.2.md
docs/architecture/Requirement-Lifecycle-Ownership-v0.2.md
docs/architecture/Requirement-State-Worker-Contract-v0.1.md
docs/architecture/Project-Bootstrap-Contract-v0.1.md
docs/rewrite/RW-B02-Verification-v0.1.md
docs/rewrite/RW-B03-Verification-v0.1.md
docs/rewrite/RW-B04-Verification-v0.1.md
docs/rewrite/RW-B05-Verification-v0.1.md
docs/rewrite/RW-O04-Verification-v0.1.md
docs/rewrite/RW-V03-Verification-v0.1.md
```

Do not make moving-plan status text the only evidence that a capability is current/verified.

## 13. Verification scans

D01 must include repository-wide text scans over current documentation for stale operational claims.

At minimum inspect matches for:

```text
Only three capabilities
No implementation exists yet
Not yet implemented
Standard Draft -> Process
Requirements/{Raw,Draft,Approved}
manual worker
project init
project requirement add
worker run
```

A matching string is not automatically wrong: historical/superseded docs may retain old prose. The implementation report must classify remaining matches as:

```text
CURRENT AND CORRECT
HISTORICAL / SUPERSEDED
FIXED
```

Do not mechanically delete historical evidence merely to make grep empty.

## 14. Gates

No live Fibery mutation is required by D01.

Run at least:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
```

Also perform Markdown/link/path sanity checks sufficient to prove every newly named canonical path exists.

Expected code/test changes:

```text
NONE
```

## 15. Completion evidence

The D01 implementation report must provide:

- exact changed docs;
- exact newly created current docs;
- stale-claim inventory and disposition;
- normal user flow as documented after reconciliation;
- admin/recovery flow distinction;
- bootstrap positioning;
- Requirement WHAT/HOW statement;
- physical-Folder retirement statement;
- explicit list of downstream phases still unimplemented;
- full regression result;
- confirmation no production/test code changed.

D01 ends `IMPLEMENTED_UNVERIFIED`; independent review performs the final repository documentation freeze and only then may record the rewrite completion marker.
