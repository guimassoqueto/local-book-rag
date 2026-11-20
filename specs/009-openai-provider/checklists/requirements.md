# Specification Quality Checklist: OpenAI models for chat and summaries, opt-in

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

- First pass, one fix: SC-008's "OpenAI's other environment settings" named nothing testable; it
  now names `OPENAI_BASE_URL`, the other setting that OpenAI's library reads on its own.
- The spec names the app's own commands, settings and files (`doctor`, `reindex-all`, `--model`,
  `.env`, `config/models.yaml`, `make test-integration`), as the project's earlier specs do. It
  also names what the owner's input fixed: the provider registered next to Anthropic, OpenAI's own
  library, never Ollama's OpenAI-compatible endpoint, and no change to the services, the tabs or
  the commands, which SC-011 checks by their directories. It names no class or API call of its
  own.
- The rules that `specs/008` set for every provider are referenced, not copied (Requirements'
  preamble); the requirements restate the parts a reader needs to check OpenAI, and add what
  OpenAI brings: a name allowed by two providers (FR-006), mixed sequences (FR-007, User Story 3),
  no stored request and no tool (FR-012), an account out of credit (FR-014), reasoning that may not
  come back (FR-015), the key read on its own by OpenAI's library (FR-020), and the token estimate
  measured (SC-009).
- One marker, in FR-003: which kind of OpenAI models the single profile serves. It decides the
  profile, what the Research tab can show, and whether Principle I would need an amendment.
- Second pass, after the owner's answer (A): the profile serves models that reason, the GPT-5 line
  and later, with an effort set and a summary of the reasoning asked for; a model that doesn't
  reason fails as rejected. Recorded in FR-003, the Clarifications and the Assumptions. No marker
  remains, and all items pass.
- Items marked incomplete require spec updates before `/speckit-clarify` or `/speckit-plan`
