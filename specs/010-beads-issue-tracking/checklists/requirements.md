# Specification Quality Checklist: Issues found during development, tracked in beads

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-11-26
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

- Items marked incomplete require spec updates before `/speckit-clarify` or `/speckit-plan`
- The tool is the feature: beads, its `refs/dolt/data` default, GitHub, `CLAUDE.md`, Spec Kit's
  flows and the project's `make` targets are named because the owner's request and the
  constitution name them, as earlier specs here name `ask`, `doctor` and `config/models.yaml`. How
  the tracker is wired (a redirect, routing, an environment variable), what `bd setup` and
  `bd hooks` write, and how kinds map to beads' types are left to the plan.
- The success criteria name `make install`, `make test`, `make lint-check` and
  `make speckit-upgrade` as the project's own interfaces, the things a developer runs, not as
  implementation choices.
- Three questions were open after the first draft. The owner answered them on 2026-11-26
  (Clarifications): a vulnerability is fixed in a security advisory's temporary private fork
  (User Story 3, FR-019); the open part of the existing backlog seeds the tracker (FR-031,
  SC-009); beads aren't mirrored to GitHub Issues (FR-026). Re-validated after the answers: every
  item passes.
- Left to the plan, as the spec says: whether `main`'s branch rules let an advisory's private fork
  merge, since Actions don't run there (Edge Cases); the list of what the backlog seeds and leaves
  out (FR-031); whether the rule belongs in the constitution (FR-030).
- Re-validated after the plan changed the spec on 2026-11-26 (Clarifications, plan session). The
  repository had been made private, so the vulnerability path now depends on visibility (User
  Story 3, FR-017 to FR-019, SC-008). FR-025 now allows a unit test of the hook script. Every
  item still passes.
- The repository was public again later that day. No requirement changed. User Story 3's test and
  SC-008 now run the advisory path up to the merge. Every item still passes.
