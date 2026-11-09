# Specification Quality Checklist: Choosing the default LLM by measurement

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-11-09
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

- **Implementation details.** The spec names models, digests, the dataset checksum, the gated
  metrics, `make test-integration` and the documents to update. They are the feature's subject and
  its deliverables, as the decision rule has to be exact before any run. It names no module, class
  or code structure. How the confirmation runs only two variants, how the probe times the first
  visible word and counts whole prompts, how the judge gets pulled and how a profile marks a
  tokenizer as approximate are left to the plan.
- **Stakeholders.** The only stakeholder is the owner, as researcher, reader and maintainer
  (Assumptions), so the spec uses the project's own terms: abstention, paired interval, judge.
- **Clarifications.** Three were asked and answered on 2026-11-09, and are recorded in the spec's
  Clarifications section:
  - the first default's reason, from `.TASK/task.md` § 3.1;
  - a gated metric worse blocks the switch outright;
  - only probe failures where gemma4 does worse than gpt-oss block it.

  The handoff's other open questions got informed defaults, stated in Assumptions:
  - answers against summaries, settled by the rule being a conjunction;
  - the acceptable extra wait, 1 s;
  - the confirmation judged alone (FR-003);
  - the owner as sole user.
- **Found while writing.** Today's dataset checksum (`767e4cceb315…`) differs from the earlier
  generation run's (`f69da2332857…`). The only difference is the key points, which the generation
  experiment doesn't read, so FR-004 names today's checksum. The Context says why.
- **Success criteria.** They cite `docs/decisions.md` and `make test-integration` because those
  are how the owner checks the outcome. SC-008 restates what the rule guarantees on a switch, so
  the reader-facing gains are stated measurably.
- **Optional steps.** Per `AGENTS.md`, this feature touches no lifecycle, journal, fingerprint,
  prompt, citation parsing, judge or metric. So `/speckit-clarify`, `/speckit-checklist` and
  `/speckit-analyze` aren't required. The three clarifications above were settled here. One
  caveat for the plan: FR-002 (b) pairs summary seconds and steps, which `benchmark-report` doesn't
  pair today. If the plan adds them to the report, it changes a metric, and the extra steps apply.
  The same holds if it turns the probe into a benchmark experiment.
- Items marked incomplete require spec updates before `/speckit-clarify` or `/speckit-plan`.
