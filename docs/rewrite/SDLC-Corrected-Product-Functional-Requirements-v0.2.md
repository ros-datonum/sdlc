<!--
format: sdlc/raw-requirements
version: 0.2
-->

# SDLC — Corrected Product and Functional Requirements

## Intent

Build an AI-first software delivery system that helps a human take a project from an idea to a validated, operational result while preserving the original intent through requirements, design, planning, implementation, verification, release, and post-deployment validation.

The system must automate repeatable delivery work without transferring product authority to automation or coding agents. Human decisions must remain explicit at the points where the user accepts, rejects, reworks, or changes what should be built.

This document defines **what the SDLC must do and how it must behave from the user's and workflow's perspective**. It intentionally does not define internal implementation mechanisms.

## Context

The SDLC already has a partially implemented requirements workflow and Fibery-based project state. Real-project dogfood showed two important product-level problems that must be corrected:

1. Standard Requirements can become too detailed and absorb material that belongs to technical architecture, delivery planning, stories, tasks, or test implementation.
2. Normal operation has been exercised through many explicit internal commands, while the intended user experience is that the user controls lifecycle decisions through project/work-item state and the system performs the corresponding machine-owned processing automatically.

The correction must preserve the useful behavior already established by the project while restoring the intended separation between Requirements, Technical Solution Architecture, Delivery Planning, and Development.

Existing implementation is evidence of current behavior, not authority over this document. Where current behavior conflicts with these requirements, these requirements describe the desired behavior.

## Desired Outcomes

- A user can initialize a new SDLC project through one explicit project-setup action.
- A newly initialized project is ready to participate in the SDLC without requiring the user to manually assemble its delivery context from multiple unrelated setup steps.
- The user can add new source requirements to an existing project at any time.
- Free-form ideas and source material can be preserved as RAW requirements without prematurely turning technical detail into canonical product requirements.
- Standard Requirements describe required outcomes, capabilities, constraints, and observable system behavior rather than choosing implementation mechanisms.
- Technical Solution Architecture remains responsible for deciding how canonical Requirements will be satisfied.
- Delivery Planning remains responsible for decomposing approved requirements and architecture into executable work.
- Fibery presents the current project, requirement, planning, and delivery state to the user and acts as the primary lifecycle control surface.
- Explicit human lifecycle decisions can be made in Fibery, or through an authorized assistant acting on an explicit user instruction, without changing the meaning or authority of the decision.
- Machine-owned processing begins as a consequence of the relevant lifecycle state and does not require the user to manually invoke each internal processing step during normal operation.
- Human approval/rework boundaries are never crossed autonomously.
- Coding agents receive bounded implementation work and do not decide what the product requirements are, approve requirements, or control project lifecycle authority.
- Requirements, architecture, delivery work, implementation, verification, and release remain traceable to one another.
- The lifecycle remains iterative: defects or new information can return work to the phase where the underlying problem originated.
- Historical source, analysis, reviews, decisions, and superseded state remain inspectable rather than being silently replaced by newer derived state.

## Requirements and Expected Behavior

### Project setup and project entry

- The user must be able to start a new SDLC project through a single explicit project-setup action.
- Project setup must create or establish the project in the SDLC source of truth and leave it in a valid initial lifecycle state.
- Project setup must give the project a stable identity that can be used consistently across later SDLC stages.
- When initial project context and source requirements are supplied as part of setup, the system must make them available to the new project without requiring the user to recreate the same information manually.
- Repeating project setup for an already initialized project must not silently create a duplicate project or overwrite valid existing project state.
- If setup cannot complete, the user must be able to see that the project is incomplete rather than being shown a successful initialization.
- The user must be able to add additional RAW requirements after project initialization.

### RAW requirements and source preservation

- RAW requirements must preserve the intent and source material supplied by the user before it is converted into canonical Standard Requirements.
- A RAW requirement may contain business context, desired outcomes, functional behavior, constraints, accepted decisions, open questions, explicit exclusions, and terminology.
- RAW material may contain technical observations from the source, but those observations must not automatically become separate Standard Requirements merely because they are present.
- The system must preserve meaningful source gaps and unresolved questions instead of inventing answers during requirements processing.
- Processing a RAW requirement may produce zero, one, or multiple Standard Requirement candidates.
- The system must be able to identify when new RAW material appears to duplicate, conflict with, change, or supersede existing requirements without silently modifying those existing requirements.
- The user must be able to inspect the source relationship between a Standard Requirement and the RAW material from which it was derived.

### Standard Requirement abstraction

- A Standard Requirement must describe **what must be true**, not the internal mechanism by which it will be made true.
- A Standard Requirement may define:
  - a user or system capability;
  - a required outcome;
  - required observable behavior;
  - a business or system constraint;
  - an invariant that the delivered system must preserve.
- A Standard Requirement must remain valid across multiple possible technical implementations whenever the source does not explicitly require one implementation mechanism.
- A technical mechanism may be mandatory in a Standard Requirement only when the source explicitly makes that mechanism part of the required constraint or product behavior.
- A separate Standard Requirement must not be created merely for:
  - an implementation component;
  - a function, class, module, library, or framework;
  - an algorithm or internal execution sequence;
  - a field-level implementation detail that does not represent an independently meaningful obligation;
  - a specific test implementation;
  - a deployment mechanism;
  - a low-level implementation edge case that belongs to architecture or delivery work.
- Requirements that share one meaningful capability must not be fragmented into many requirements solely because the source describes multiple implementation details of that capability.
- Independent product or system obligations must not be merged merely because they appear in the same source section.
- Acceptance information at the Requirement level must describe observable evidence that the Requirement is satisfied, not prescribe the internal test code or test framework used to prove it.
- A Standard Requirement must not silently resolve an open product decision that the source leaves undecided.
- Standard Requirement processing may improve clarity and organization but must not change source intent or introduce new product obligations.
- Requirement analysis must be able to surface incompleteness, ambiguity, inconsistency, non-atomicity, poor testability, duplication, conflict, possible change, possible supersession, dependencies, and impact relationships for human review.
- Findings and proposed relationships must remain analysis until the lifecycle explicitly makes them canonical.

### Requirement lifecycle and human authority

- Requirement lifecycle state must make the current position of a Requirement visible to the user.
- A newly added RAW Requirement must wait for explicit human intent before its first processing cycle begins.
- The human initiates RAW processing by moving the RAW Requirement into its processing state.
- Once RAW processing has been authorized, Standard Requirement candidates produced from that RAW source must automatically continue through machine-owned Standard Process and Standard Review until they reach the next human decision boundary.
- A separate human activation must not be required for each Standard Requirement candidate created by an already-authorized RAW processing cycle.
- Successful Standard Process must automatically continue into Standard Review.
- Successful Standard Review must move the Standard Requirement to the human Ready decision boundary.
- Machine-owned processing must not require a second manual command when the relevant lifecycle state or already-authorized upstream action expresses the user's intent to run that processing.
- After successful machine-owned processing, the system must record the result and move the Requirement to the next appropriate lifecycle state.
- The system must stop at a human decision boundary when human approval or rework is required.
- A human decision to approve a ready Standard Requirement must be represented by moving it into the lifecycle state that authorizes application.
- A human decision to rework a ready Standard Requirement must return it to the lifecycle state where it can be revised and processed again.
- An authorized assistant may perform the same lifecycle state change only when the user explicitly instructs it to do so; the assistant must not acquire independent approval authority.
- Moving a Standard Requirement into the application state must cause the system to perform the corresponding deterministic application work.
- A Standard Requirement becomes canonical only after the authorized application step completes successfully.
- The system must not automatically approve a Requirement on behalf of the human.
- Each Requirement that participates in automated processing must visibly indicate the outcome of its current processing cycle separately from the lifecycle State.
- Entering or re-entering a lifecycle state that requires new automated processing must reset any prior processing outcome for that new cycle before processing starts.
- While automated work is running, the Requirement must visibly indicate that processing is in progress.
- After successful automated work, the Requirement must visibly indicate success.
- After failed automated work, the Requirement must visibly indicate failure and must not falsely advance to a lifecycle state that implies successful completion.
- Repeated processing of the same unchanged lifecycle event must not create duplicate canonical outcomes.
- If automated processing fails, the failure must remain visible and the work must be recoverable without silently discarding valid prior state.

### Canonical requirements and change

- Canonical Requirements must remain available as the authoritative statement of what the project must satisfy.
- Later information may reveal that an existing canonical Requirement needs revision, replacement, or supersession.
- Changing an already canonical Requirement must preserve the historical requirement and the fact that it was previously accepted.
- A change to a canonical Requirement must make affected downstream work discoverable so the relevant design, planning, implementation, or verification can be reconsidered.
- The system must not treat previously produced downstream artifacts as automatically valid after a requirement they depend on materially changes.

### UX / Product Design

- Projects with meaningful human interaction may include a UX / Product Design stage before Technical Solution Architecture.
- UX / Product Design must describe user-facing behavior such as journeys, navigation, views, flows, states, permissions experience, administrative workflows, and relevant empty/error/loading behavior.
- UX / Product Design must be reviewable and revisable before it is treated as approved input to technical architecture.
- Projects without meaningful human interaction must be able to skip this stage without inventing unnecessary design work.

### Technical Solution Architecture

- Technical Solution Architecture must consume canonical Requirements and approved UX / Product Design when applicable.
- Technical Solution Architecture is responsible for deciding **how** the approved requirements will be satisfied.
- Architecture may define technical structure, system boundaries, responsibilities, interfaces, data flows, integrations, security boundaries, operational concerns, and implementation targets as needed by the project.
- Architecture must not redefine product intent merely to simplify implementation.
- If architecture exposes a missing, contradictory, or materially changed product requirement, the issue must return to Requirements rather than being silently resolved as an implementation choice.
- Technical architecture must be reviewable and revisable before it becomes approved input to Delivery Planning.

### Delivery Planning

- Delivery Planning must begin from approved Requirements, applicable approved UX / Product Design, and approved Technical Solution Architecture.
- Delivery Planning must transform that approved context into executable delivery work.
- Delivery work may be organized as Epics, Stories, and Tasks when useful; the hierarchy must be allowed to collapse for small work.
- Delivery work must contain the implementation-level detail needed to execute the approved requirements and architecture.
- Detailed acceptance criteria, definition of done, implementation dependencies, and implementation targets belong at the delivery-work level when they are specific to the chosen solution.
- Delivery work must remain traceable to the Requirements and architecture decisions that justify it.
- The system must make relevant dependencies and change impact visible so work can be ordered or revisited correctly.

### Development

- Development must operate on delivery work that is ready for implementation.
- A work item's lifecycle state must make its current development position visible.
- When a work item enters a state requiring automated implementation, testing, or review, the corresponding bounded work must be able to start without the user manually invoking the internal worker.
- Coding agents must implement the assigned delivery work against the approved requirements and technical context.
- Coding agents must not change requirements, approve requirements, or redefine architecture as part of implementing a task.
- If implementation reveals that the approved requirement or architecture is insufficient or contradictory, the system must surface the issue and return work to the appropriate upstream phase instead of hiding the problem inside a code-level workaround.
- Testing must verify the implementation being proposed for review.
- Review must evaluate the same implementation revision that was tested.
- Rework identified by testing or review must return to implementation without losing the relationship to the originating task and requirements.
- Development completion at task level must not substitute for whole-system verification.

### Implementation targets

- The core SDLC must support projects whose deliverable is not limited to a conventional source-code repository.
- Delivery work must be able to identify the target in which the implementation is produced.
- The system must be able to track which implementation revision was worked on, tested, reviewed, and ultimately released in a way appropriate to that target.
- Approval for release must not silently refer to a different implementation revision than the one that was tested and reviewed.

### System verification, release, deployment, and validation

- After development is feature-complete, the system must support whole-system verification appropriate to the project.
- Whole-system verification may evaluate integration behavior, end-to-end flows, realistic data, failure behavior, performance, permissions, migration behavior, recovery, usability, observability, and operational behavior when relevant.
- A defect found during verification must be able to return work to the phase where the underlying defect originated:
  - implementation defects to Development;
  - technical-design defects to Technical Solution Architecture and downstream replanning;
  - UX defects to UX / Product Design and downstream impact handling;
  - requirement defects to Requirements and downstream impact handling.
- The system must support preparation of a releasable project state before deployment.
- The system must support deployment to the project's actual implementation target.
- After deployment, the system must support validation of the deployed result using the project's critical expected behavior.
- A project must reach its active/operational state only after the deployed result has been validated successfully.

### Traceability and history

- The user must be able to trace meaningful delivery state from source requirements through canonical requirements, design, architecture, delivery work, implementation, verification, and release.
- Historical processing and review results must remain distinguishable from the current accepted state.
- Rework must preserve prior history instead of pretending the earlier state never existed.
- Derived artifacts must not silently replace or erase the source material or prior accepted decisions from which they were produced.
- The system must make the current authoritative state clear without requiring historical records to be deleted.
- Relationships used for dependency or impact analysis must be reviewable before they become canonical.

## Constraints

- Requirements must remain at the level of required product/system behavior and must not absorb downstream implementation design.
- Technical Architecture owns solution design; Delivery Planning owns executable decomposition; Development owns implementation.
- Human approval authority must remain explicit and must not be inferred from an automated worker's output.
- Automation may execute work after an authorized lifecycle transition but must not manufacture the human decision that authorizes that transition.
- Fibery is the canonical source of project, requirement, planning, design, and delivery state for the current SDLC product.
- Source repositories contain implementation artifacts rather than canonical mirrors of product Requirements.
- Historical source and accepted state must be preserved when later revisions are created.
- The lifecycle must permit rewind when a defect originates upstream; downstream patching must not be the only available response.
- The current implementation must not be treated as a requirement when it conflicts with the behavior defined in this document.

## Accepted Decisions

- The stable top-level project lifecycle is:

  `REQUIREMENTS → UX / PRODUCT DESIGN (optional) → TECHNICAL SOLUTION ARCHITECTURE → DELIVERY PLANNING → DEVELOPMENT → SYSTEM VERIFICATION & HARDENING → RELEASE PREPARATION → DEPLOYMENT → POST-DEPLOY VALIDATION → ACTIVE`.

- The lifecycle is iterative rather than a one-way waterfall.
- Fibery is the canonical project and delivery state and the primary human lifecycle control surface.
- The user explicitly initiates creation/setup of a project.
- The user explicitly initiates RAW processing and the human-owned Requirement decisions that request rework or authorize application.
- Standard Requirement candidates created by an authorized RAW processing cycle automatically continue through Standard Process and Standard Review until the Ready human decision boundary.
- Successful Standard Process automatically continues into Standard Review; there is no separate human decision between those machine-owned stages.
- System-owned work reacts to lifecycle state and already-authorized lifecycle flow and records its results back into the project state.
- Automated processing outcome is visible on the Requirement; starting a new processing cycle resets the prior outcome, and the current cycle visibly reports in-progress, success, or failure.
- A human can make the same explicit state decision directly in Fibery or instruct an authorized assistant to perform that state change on the human's behalf.
- Standard Requirements define **what must be true**. Technical Solution Architecture defines **how it will be achieved**.
- Stories and Tasks carry solution-specific execution detail that should not be promoted into Requirements.
- Acceptance at Requirement level describes observable satisfaction; implementation-specific test design belongs downstream.
- Coding agents execute bounded development work; they do not own requirement approval or project lifecycle authority.
- The SDLC is not limited to Git-based software projects and must be able to represent other implementation targets.
- Requirement history and later revisions/supersession must be preservable.
- Existing useful infrastructure may be reused during correction, but its current structure does not define the required product behavior.

## Open Questions

- What is the desired user experience for bulk approval or bulk rework when one RAW source produces several independently reviewable Standard Requirements?
- What visible workflow should the user use to revise or supersede an already canonical Requirement while preserving history?
- What level of relationship management should require explicit human confirmation before dependency and impact relations become canonical?
- Which project-setup inputs are mandatory for every project and which may be added later?
- Which stages should support an explicit manual override or retry action in the normal user interface, as distinct from administrative/recovery tooling?

## Deferred / Out of Scope

The following are intentionally **not requirements in this export** and must be decided or specified downstream:

- programming language, framework, package, library, class, module, or function choices;
- internal repository or directory layout;
- configuration file names, schemas, or serialization formats;
- the internal structure of a reusable project template;
- the mechanism used to observe lifecycle state changes;
- webhook, polling, queue, scheduler, or event-delivery design;
- worker process topology and hosting;
- model provider, model name, CLI/API choice, prompt structure, or runtime isolation mechanism;
- exact Fibery API calls or transport behavior;
- hashing, fingerprint, manifest, locking, retry, rate-limit, or recovery algorithms;
- internal CLI command layout for worker/admin operations;
- Git branch, worktree, commit, pull-request, or merge mechanics;
- exact test framework, test fixtures, or test implementation;
- concrete deployment implementation for individual target platforms;
- exact internal representation of revision/supersession and impact propagation;
- implementation of downstream Technical Architecture, Delivery Planning, Development, verification, release, deployment, and post-deployment workers as part of the immediate Requirements-layer correction;
- migration strategy for the existing dogfood Requirement corpus.

The existing AMR dogfood corpus remains useful as evidence of the previous requirements behavior, but it does not define the corrected Requirement abstraction.

## Terminology

**Project** — a delivery effort managed through the SDLC from requirements to an active validated result.

**RAW Requirement** — source-preserving project input that has not yet been accepted as a canonical Standard Requirement.

**Standard Requirement** — an independently meaningful statement of what the project must make true: a capability, outcome, required behavior, constraint, or invariant.

**Canonical Requirement** — a Standard Requirement that has passed the required lifecycle and has been explicitly authorized by the human for application.

**Requirement abstraction boundary** — the boundary separating what must be true from the technical design and implementation used to make it true.

**Human decision boundary** — a lifecycle point that automation may prepare but may not cross without an explicit human decision.

**Lifecycle state** — the visible state of a project or work item that communicates where it currently is in its workflow.

**Processing status** — the visible outcome of the current automated processing cycle for a Requirement. It is reset when a new processing cycle is requested and shows whether automated work is pending/in progress, successful, or failed without replacing lifecycle State.

**Human-owned transition** — a lifecycle transition whose meaning is an explicit user decision or authorization.

**System-owned transition** — a lifecycle transition produced by successful automated processing after the required human intent already exists.

**Worker** — bounded automated processing associated with a lifecycle state. The term defines responsibility, not implementation technology.

**Apply** — the lifecycle point at which a human-approved Standard Requirement is authorized to become canonical.

**Applied** — the state indicating that the authorized application of a Standard Requirement completed successfully.

**UX / Product Design** — optional product-level design of meaningful human interaction before technical solution design.

**Technical Solution Architecture** — the phase that determines how approved Requirements and applicable product design will be satisfied technically.

**Delivery Planning** — the phase that turns approved Requirements and architecture into executable Epics, Stories, and Tasks or a smaller collapsed hierarchy when appropriate.

**Coding Agent** — an automated development actor that implements bounded delivery work but does not own product intent, requirement approval, or lifecycle authority.

**Implementation Target** — the system or platform in which a delivery work item produces its implementation result.

**Implementation Revision** — the identifiable version of implementation that can be worked on, tested, reviewed, released, and validated.

**Rework** — returning work to an earlier appropriate lifecycle state because the current result needs correction.

**Supersession** — replacement of a previously accepted requirement or other artifact by a newer accepted version while preserving historical state.

**Traceability** — the ability to follow why a downstream artifact exists and which upstream requirements, design, or work it satisfies.
