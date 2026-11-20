# Specification Quality Checklist: Cloud models for chat and summaries, opt-in

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-11-20
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

- First pass, two fixes. The Assumptions named the interface's framework where the setting
  `GRADIO_BIND_ADDRESS` is enough, and FR-017's "no provider configured" was ambiguous next to
  FR-002's provider with one setting only. It now reads "when no provider has either setting".
- The spec names the app's own commands, settings and files (`doctor`, `reindex-all`, `--model`,
  `.env`, `config/models.yaml`, `make test`), as the project's earlier specs do: they are what the
  owner, its one user, sees and runs. It names no library, class or API call.
- No markers were needed. The choice with two reasonable readings, what `reindex-all` does with a
  summary that a cloud model wrote, is decided in FR-023 (left as it was, and listed), from "never
  calls a cloud model" and "never answers with another model without saying so". `/speckit-clarify`,
  which `AGENTS.md` requires for this feature, can revisit it.
- Second pass, after the owner added fallbacks before the first commit. They are User Story 3,
  FR-007 to FR-010 and FR-016 to FR-020, and SC-006 to SC-008. The first draft's rule that no other
  model answers, and that a failure ends the request, gave way to a sequence that the user defines
  and the local model ends. The description's "never answers with another model without saying
  so" still holds through FR-016 and FR-018, and Principle I through FR-015: a model in the
  sequence is a model the user chose. All items pass again.
- Third pass: the owner asked for streamed responses. Answers already stream, and FR-013 asks the
  same of cloud models. Streaming summaries is left out and recorded in the Assumptions: it would
  change local summaries too, against SC-001. All items still pass.
- Items marked incomplete require spec updates before `/speckit-clarify` or `/speckit-plan`
