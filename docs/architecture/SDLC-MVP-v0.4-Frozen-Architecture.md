# SDLC MVP v0.4 — Frozen Architecture

**Status:** Current baseline for MVP implementation.

## 1. Project Lifecycle

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

This is iterative, not waterfall. Project Phase identifies the dominant class of decision currently being stabilized. Later phases may rewind to Requirements, UX, Technical Architecture, or Development when the defect originated there.

## 2. Requirements

```text
CHAT / IDEATION
→ PROJECT INBOX
→ PROCESS
→ REQUIREMENT DRAFTS
→ VALIDATE / ANALYZE / LINK
→ REVIEW / REWORK
→ HUMAN APPLY
→ CANONICAL FIBERY REQUIREMENTS
```

- Project Inbox stores structured input extracted from free-form discussion.
- Inbox Processor transforms an Inbox Item into zero, one, or many Requirement Drafts.
- Requirement Drafts are staging proposals, not canonical requirements.
- Draft Validator / Requirements Analyst validates completeness, consistency, gaps, dependencies, impact relations, duplication and testability.
- Human transition to APPLY authorizes canonical mutation.
- Fibery owns canonical Requirements and Requirement Documents.
- Repository never stores canonical requirements or requirement mirrors.

## 3. UX / Product Design

Runs before technical architecture when meaningful human interaction exists, including customer UI, operator UI, or admin dashboards.

Outputs may include:
- user journeys;
- information architecture;
- navigation;
- screens/views;
- flows and states;
- roles/permissions UX;
- admin workflows;
- empty/error/loading states;
- wireframes/mockups.

Internal loop:

```text
DRAFT → REVIEW → REVISE → REVIEW → APPROVE
```

## 4. Technical Solution Architecture

Runs after canonical Requirements and approved UX/Product Design when applicable.

Determines:
- technology choices;
- databases/storage;
- hosting and deployment model;
- high-level modules and responsibilities;
- interfaces and data flows;
- external integrations;
- authentication/authorization;
- infrastructure and observability;
- security/recovery boundaries;
- migration implications;
- implementation targets;
- major technical risks.

Internal loop:

```text
ARCHITECTURE DRAFT
→ REVIEW FINDINGS
→ REVISION
→ REVIEW
→ ...
→ APPROVED ARCHITECTURE
```

Reviewers return findings; one architecture owner integrates them.

## 5. Delivery Planning

Only after Requirements + applicable UX + Technical Architecture are approved:

```text
Requirements + UX + Architecture
→ Epics
→ Stories
→ Tasks
```

Hierarchy collapses when appropriate; small work may be Requirement → Task.

Delivery planning creates:
- AC and DoD;
- execution dependencies;
- change-impact relations;
- requirement traceability;
- architecture traceability;
- implementation target assignment.

## 6. Development

Task-level loop:

```text
READY
→ IMPLEMENTING
→ READY_FOR_TEST
→ TESTING
→ READY_FOR_REVIEW
→ REVIEWING
→ DONE
```

Rework returns through NEEDS_FIX → IMPLEMENTING.

Task testing/review remains inside Development. It does not replace whole-system verification.

## 7. Implementation Target abstraction

Core SDLC is not Git-only.

Supported MVP target classes:

```text
GITHUB
WINDMILL
N8N
MAKE
ZAPIER
```

Common revision identity:

```text
Working Revision
Tested Revision
Reviewed Revision
Released Revision
```

Before approval:

```text
Working Revision = Tested Revision = Reviewed Revision
```

The identifier is adapter-specific: Git SHA, platform version, immutable revision, or exported snapshot hash.

## 8. System Verification & Hardening

Whole-system phase after feature-complete development.

As relevant:
- integration tests;
- E2E tests;
- cross-module behavior;
- realistic data;
- failure scenarios;
- performance;
- security/permissions;
- migration/upgrade tests;
- recovery/concurrency;
- UX/UI polish;
- observability and operational behavior.

Rewind rules:

```text
implementation defect → DEVELOPMENT
technical-design defect → TECHNICAL SOLUTION ARCHITECTURE → replan → develop
UX defect → UX / PRODUCT DESIGN → downstream impact
requirement defect → REQUIREMENTS → downstream impact
```

## 9. Release Preparation

Includes as relevant:

**Data:** migrations, seeds, backfills, cleanup, rehearsal, backup, rollback.

**DevOps:** production environment, DNS/TLS, secrets, runtime, networking, CI/CD, monitoring, logging, alerts, backups, health checks, scaling.

**Release:** version, deployment order, downtime, feature flags, rollback procedure, checklist, release notes.

## 10. Deployment

Deploy the approved release revision to actual target(s): application, n8n workflow, Make scenario, Zapier Zap, Windmill app/flow/script, etc.

## 11. Post-Deploy Validation

Verify the deployed system using smoke tests, critical E2E, health/integration checks, migration verification, logs/errors and critical business flows.

Success:

```text
Release = VALIDATED
Project Phase = ACTIVE
```

## 12. Central Architecture Principle

```text
Simple stable Project Lifecycle
        ↓
phase-specific local workflows
        ↓
task workflows where applicable
```

Complexity stays local to the phase that needs it.
