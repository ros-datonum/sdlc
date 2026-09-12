# Implementation Start

**Status:** HISTORICAL / SUPERSEDED. This recorded the original bootstrap-era
implementation order, when only the first three capabilities were in scope. All
three were built, and the SDLC Rewrite v0.2 then added project bootstrap, the
corrected Requirement abstraction and the state-driven lifecycle.

For current implementation status and scope use
`docs/architecture/SDLC-MVP-v0.5-Current-Architecture.md` and
`docs/architecture/Requirement-Lifecycle-v0.2-Current.md`.

The original content follows, unchanged.

## Implement now (historical)

In this order:

1. `project init` from `docs/specs/Project-Init-Spec-v0.3.md`
2. `project requirement add` from `docs/specs/Project-Requirement-Add-Spec-v0.3.md`
3. RAW Requirement Processor, bounded by `docs/specs/RAW-Requirement-Processor-Decision-v0.1.md`

## Do not design next

Do not implement:
- Standard Requirement revision/update semantics;
- Project Phase planner;
- backlog agents;
- GitHub workflow;
- deployment;
- non-Git implementation adapters.

First make the three current capabilities work against the actual Fibery schema.

## Model runtime

The first two capabilities should be deterministic and must not invoke a model.

The RAW Requirement Processor is the first reasoning component and must use the local OAuth CLI runtime defined in `docs/runtime/Local-OAuth-Model-Runtime-Spec-v0.1.md`.
