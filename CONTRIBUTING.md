# Contributing to Hibiscus Station

Thank you for helping! 🌺 Bug reports, hardware test results, translations, docs and code are all
welcome. By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md). Security issues go
through [SECURITY.md](SECURITY.md), never through public issues.

## Ways to contribute

* **Report a bug** or **suggest a feature** with the
  [issue forms](https://github.com/Bigkatoan/hibiscus-station/issues/new/choose). Include the
  install type (Docker variant or wheel), the machine (PC, Jetson, Raspberry Pi 5) and the arms.
* **Run the hardware checklist** ([en](docs/user-guide/en/station-hardware-uat.md),
  [vi](docs/user-guide/vi/station-hardware-uat.md)) on your arms and share the results: real
  hardware is what the automated tests cannot cover.
* **Translate**: UI strings live in `web/src/station/i18n/{vi,en}.json` (and the few shared ones in
  `web/src/i18n/`); user docs in `docs/user-guide/{vi,en}`. Every key must exist in both languages.
* **Code**: look for `good first issue` or `help wanted`, and comment before a large change.

## Repository layout

| Path | What | Stack |
|---|---|---|
| `hibiscus_station/` | the app: FastAPI API and WebSockets, hardware owner thread, sessions, programs, mocks | Python 3.12, uv, LeRobot 0.7.1 |
| `tests/` | pytest suite (mock hardware), `tests/e2e` (Playwright), `tests/contract` (Hibiscus API snapshot) | pytest |
| `web/` | the UI, bundled into the wheel as `hibiscus_station/static` | React, TypeScript, Vite, Tailwind, pnpm |
| `docker/` | image Dockerfiles and `build.sh` | Docker Buildx |
| `deploy/` | compose files, `install.sh`, `hibiscus-station-ctl`, udev rule, systemd unit | bash |
| `docs/` | deploy guide, user guide, specs, first-boot checklists | Markdown |

## Development setup

Prerequisites: [uv](https://docs.astral.sh/uv/) ≥ 0.13 and Docker. Node 22 + pnpm 9 for the UI, or
none at all: `web/scripts/node.sh` runs them in a `node:22.12` container.

```bash
git clone https://github.com/Bigkatoan/hibiscus-station.git && cd hibiscus-station
uv sync                                   # Python 3.12 venv with the dev tools
web/scripts/node.sh pnpm install --frozen-lockfile
make help                                 # every target
```

> If your shell exports ROS paths in `PYTHONPATH`, run Python tooling as
> `env -u PYTHONPATH -u AMENT_PREFIX_PATH uv run ...` (the Makefile already does).

Run the app against the UI dev server: `uv run hibiscus-station --mock --no-browser` and, in a second
shell, `web/scripts/node.sh pnpm dev` (http://127.0.0.1:18211, log in through
`http://127.0.0.1:18211/auth?t=<token>` from `uv run hibiscus-station url`). Or the UI alone with an
in-page mock station: `pnpm dev:mock`.

## Checks

```bash
make check        # = the CI jobs below
# Python
uv run ruff check . && uv run ruff format --check .
uv run mypy --strict hibiscus_station
uv run pytest                    # CPU only, mock hardware; `-m slow` / `-m hil` are opt-in
uv run hibiscus-station openapi openapi.json && git diff --exit-code openapi.json
# Web (in web/)
pnpm lint && pnpm typecheck && pnpm format:check && pnpm test && pnpm build   # build includes the CSP check
pnpm check:api                   # TypeScript types match ../openapi.json
# End to end (needs web/dist and `uv run playwright install chromium`)
uv run pytest tests/e2e -m e2e
```

## Ground rules

* **Contract first.** Every wire shape is a pydantic model (`hibiscus_station/api/schemas.py`,
  `hibiscus_station/programs/schemas.py`), exported to `openapi.json`; the UI types are generated
  from it (`pnpm gen:api`). Change both in the same commit.
* **One owner per device.** Only the hardware owner thread touches a serial bus; REST handlers post
  commands to it. Every motion path goes through the same safety filter, thermal guard and e-stop.
* **LeRobot stays unmodified**, pinned to the commit in `pyproject.toml`.
* **Typed and tested.** `mypy --strict`, TypeScript `strict`; new behaviour comes with tests on the
  mocks; hardware-only behaviour gets a line in the hardware checklist.
* **Secure by default.** Loopback only unless LAN mode is configured; no secrets in code, tests or
  logs; tokens are redacted.
* **Bilingual UI.** No hard-coded user-facing strings: add keys to both `vi` and `en`.
* **Artwork** (`web/public/pixel`, `web/public/icons`, `web/src/hibiscus`, favicons) comes from the
  Hibiscus design system and is never edited here (see ASSETS-LICENSE). Maintainers refresh it with
  `web/scripts/sync-assets.sh`.

## Commits and pull requests

* [Conventional Commits](https://www.conventionalcommits.org/): `feat(programs): ...`,
  `fix(hw): ...`, `docs: ...`, `build(docker): ...`.
* One logical change per PR, the PR template filled in, screenshots for UI changes (day and night).
* CI must be green. Add a line under `## [Unreleased]` in [CHANGELOG.md](CHANGELOG.md) for
  user-visible changes.

## Releases (maintainers)

Bump `hibiscus_station/__init__.py`, `pyproject.toml`, `web/package.json`, `CITATION.cff`,
`VERSION` in `deploy/install.sh` and the CHANGELOG; regenerate `openapi.json` and the UI types; tag
`vX.Y.Z`. The tag builds the wheel (GitHub release) and the images (GHCR).

## License of contributions

Hibiscus Station is licensed under the [GNU AGPL v3.0 or later](LICENSE). By submitting a
contribution you agree that it is licensed under the same terms and that you have the right to
submit it. The artwork is **not** under the AGPL; see [ASSETS-LICENSE](ASSETS-LICENSE).
