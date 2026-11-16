<!-- Thanks for contributing to Hibiscus Station! 🌺  Title: Conventional Commits, e.g. `feat(programs): loop counter block` -->

## What and why

<!-- What does this PR change, and why? Link the issue it resolves. -->

Closes #

## How was it tested?

<!-- Commands you ran and their result (`make check`, `make e2e`), and for anything that moves the
arm: what you ran on real hardware (arms, machine, install type) or why mocks are enough. -->

## Screenshots

<!-- UI changes: before / after, day and night themes, and 390 px mobile width if the layout changed. -->

## Checklist

- [ ] `make check` passes locally (ruff, mypy, pytest, eslint, prettier, tsc, vitest, build)
- [ ] New behaviour is covered by tests on the mocks; hardware-only behaviour has a line in the hardware checklist
- [ ] Every motion path still goes through the safety filter, thermal guard and e-stop
- [ ] API changes: `openapi.json` and `web/src/station/api/schema.d.ts` regenerated (`make openapi`)
- [ ] New UI strings exist in both `vi` and `en`
- [ ] No secrets, tokens, private hostnames or personal paths in code, tests, fixtures or logs
- [ ] Docs and `CHANGELOG.md` (`## [Unreleased]`) updated for user-visible changes
