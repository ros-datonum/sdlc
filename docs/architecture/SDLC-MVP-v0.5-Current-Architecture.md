# SDLC MVP v0.5 — Current Architecture

**Status:** CURRENT. Describes what is implemented and independently verified today.  
**Supersedes for current operations:** `SDLC-MVP-v0.4-Frozen-Architecture.md` (retained as historical architecture)  
**Date:** 2026-09-13

This is a concise current architecture index, not a new design document. It
separates two things that were previously conflated:

```text
the product architecture      the full Project lifecycle SDLC is aimed at
the implemented foundation    what this rewrite actually built and verified
```

Naming a phase below does not mean an engine exists for it. Section 3 is the
authoritative implementation-status list.

## 1. Full intended Project lifecycle — product architecture

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

This is the **product architecture**, not the implementation-completeness list.
It is iterative, not waterfall: Project Phase identifies the dominant class of
decision currently being stabilized, and a later phase may rewind to an earlier
one when a defect originated there.

The full phase reasoning is retained in the historical
`SDLC-MVP-v0.4-Frozen-Architecture.md`. It remains the roadmap; it is not a
claim about implementation.

## 2. What this rewrite implemented

The rewrite built one vertical slice: the corrected Requirement foundation, the
state-driven Requirement lifecycle, and project bootstrap.

```text
requirements-export (external skill)
→ sdlc project bootstrap
→ Fibery Project + initial Raw Requirement (Draft) + consumer-project metadata/context
→ HUMAN: Raw Draft -> Process
→ RAW processing → 0..N Standard candidates
→ automatic candidate Process → automatic Review
→ Ready  (human decision boundary)
→ HUMAN: Ready -> Process (rework) or Ready -> Apply (approve)
→ deterministic Apply → Applied
```

The operational detail of that flow is `Requirement-Lifecycle-v0.2-Current.md`.

## 3. Implementation status

### Verified now

Implemented and independently verified:

```text
project bootstrap
RAW Requirement ingestion
corrected RAW decomposition
Standard Requirement Process
Standard Requirement Review
Ready human decision boundary
deterministic Standard Apply
state-driven Requirement dispatcher/runner
Processing Status / reset semantics
```

### Not implemented by this rewrite

These are architecture, not capability. No engine exists for any of them:

```text
UX / Product Design engine
Technical Solution Architecture engine
Delivery Planning / backlog builder
Epic / Story / Task implementation workflow
System Verification & Hardening engine
Release Preparation engine
Deployment engine
Post-Deploy Validation engine
```

Nothing in this repository generates architecture, plans delivery, decomposes
work into Epics/Stories/Tasks, runs a coding agent, verifies a system, prepares
a release, deploys, or validates a deployment.

## 4. The Requirement abstraction boundary

Authority: `docs/specs/Standard-Requirement-Abstraction-v0.2.md`.

```text
Requirement
= WHAT must be true

Technical Solution Architecture
= HOW the approved Requirement is satisfied

Delivery Planning
= solution-specific executable decomposition

Task
= concrete code / configuration / test / deployment work
```

A valid Standard Requirement normally remains true when the implementation is
replaced by a different valid technical solution.

**The one exception, which must not be simplified away:**

```text
a technical mechanism explicitly mandated by the source
may remain Requirement-level truth
```

So "Requirements can never contain technical detail" is the wrong rule. When
the source itself makes a mechanism part of the obligation — or when an
externally consumed contract is itself the product interface — that mechanism
is legitimate Requirement content and is recorded as a Constraint. When it is
unclear whether a mechanism is mandatory, the uncertainty is preserved as an
Open Question rather than promoted to a Requirement.

## 5. Source of truth

```text
Fibery            canonical Requirements, Requirement Documents, lifecycle State
consumer repo     code and code-native artifacts, plus project-local SDLC
                  participation metadata and non-canonical project context
```

A consumer repository never stores a canonical Requirements mirror. The four
managed consumer paths are listed in `README.md` and frozen by
`docs/rewrite/RW-B01-Template-Manifest-v0.1.md`.

## 6. Requirement placement

```text
Requirement Type + State        = lifecycle placement
Requirement-contained Documents = canonical Requirement documents
fibery/Folder                   != lifecycle authority
```

The historical physical `Requirements/{Raw,Draft,Approved}` Document tree is
**retired**. Fibery does not list entity-contained Documents in a Folder
sidebar, so that tree never worked as navigation and duplicated a signal the
Requirement already carries. Documents created before the correction keep an
inert `fibery/Folder`; nothing reads, writes, moves, repairs or migrates it.

Smart Folder / context views remain optional human navigation configured once
in the Fibery UI. They are not runtime dependencies.

## 7. Current authority documents

Contracts:

```text
docs/specs/Standard-Requirement-Abstraction-v0.2.md
docs/architecture/Requirement-Lifecycle-Ownership-v0.2.md
docs/architecture/Requirement-State-Worker-Contract-v0.1.md
docs/architecture/Project-Bootstrap-Contract-v0.1.md
docs/architecture/Requirement-Lifecycle-v0.2-Current.md
docs/fibery/Worker-Runner-Setup-v0.1.md
```

Independent verification:

```text
docs/rewrite/RW-O04-Verification-v0.1.md   Requirement lifecycle end to end
docs/rewrite/RW-B02-Verification-v0.1.md   consumer template
docs/rewrite/RW-B03-Verification-v0.1.md   project descriptor
docs/rewrite/RW-B04-Verification-v0.1.md   outer bootstrap composition
docs/rewrite/RW-B05-Verification-v0.1.md   live bootstrap gate
docs/rewrite/RW-V03-Verification-v0.1.md   corrected-pipeline dogfood cleanup
```

A capability is current because an independent verification record says so, not
because a status field in the moving rewrite plan says so.

## 8. Historical documents

Retained, not rewritten:

```text
SDLC-MVP-v0.4-Frozen-Architecture.md          pre-rewrite frozen architecture
Requirement-Lifecycle-v0.1-Checkpoint.md      pre-rewrite lifecycle checkpoint
```

They record what was designed and built before the rewrite, including the
manual per-candidate lifecycle and the retired folder model. They are history,
not current operating instructions.
