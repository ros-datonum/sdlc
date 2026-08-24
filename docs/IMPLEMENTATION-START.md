# Implementation Start

## Implement now

In this order:

1. `project init` from `docs/specs/Project-Init-Spec-v0.3.md`
2. `project requirement add` from `docs/specs/Project-Requirement-Add-Spec-v0.2.md`
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
