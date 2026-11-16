# Hibiscus Station developer entry points. `make help` lists the targets.
# Python tooling strips ROS paths (PYTHONPATH / AMENT_PREFIX_PATH); Node tooling runs in a
# node:22.12 container through web/scripts/node.sh when `pnpm` is not installed.

SHELL := /bin/bash
.SHELLFLAGS := -euo pipefail -c
.DEFAULT_GOAL := help

UV      := env -u PYTHONPATH -u AMENT_PREFIX_PATH uv
UVRUN   := $(UV) run
PNPM    := $(if $(shell command -v pnpm 2>/dev/null),cd web && pnpm,web/scripts/node.sh pnpm)
VARIANT ?= cpu

.PHONY: help
help: ## show this help
	@grep -hE '^[a-zA-Z0-9_.-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

.PHONY: sync web-install
sync: ## create / update the Python venv (uv.lock)
	$(UV) sync --locked
web-install: ## install the web dependencies (pnpm-lock.yaml)
	$(PNPM) install --frozen-lockfile

.PHONY: lint typecheck test py-check web-check check
lint: ## ruff + eslint + prettier
	$(UVRUN) ruff check . && $(UVRUN) ruff format --check .
	$(PNPM) lint && $(PNPM) format:check
typecheck: ## mypy --strict + tsc
	$(UVRUN) mypy --strict hibiscus_station
	$(PNPM) typecheck
test: ## pytest (mock hardware) + vitest
	$(UVRUN) pytest -q
	$(PNPM) test
py-check: ## every Python check, as in CI
	$(UVRUN) ruff check . && $(UVRUN) ruff format --check .
	$(UVRUN) mypy --strict hibiscus_station
	$(UVRUN) pytest -q
	$(UVRUN) hibiscus-station openapi /tmp/hibiscus-station-openapi.json && diff -u openapi.json /tmp/hibiscus-station-openapi.json
web-check: ## every web check, as in CI (lint, format, types, generated API types, tests, build + CSP check)
	$(PNPM) lint && $(PNPM) format:check && $(PNPM) typecheck && $(PNPM) check:api && $(PNPM) test && $(PNPM) build
check: py-check web-check ## all checks

.PHONY: openapi web wheel e2e run
openapi: ## regenerate openapi.json and the UI's TypeScript types
	$(UVRUN) hibiscus-station openapi openapi.json
	$(PNPM) gen:api
web: ## build the UI into web/dist
	$(PNPM) build
wheel: ## build the sdist and the wheel (UI included) into dist/
	$(UV) build --out-dir dist
e2e: ## Playwright end-to-end test of the built UI against hibiscus-station --mock
	$(UVRUN) pytest -q tests/e2e -m e2e
run: ## hibiscus-station --mock on 127.0.0.1:18210
	$(UVRUN) hibiscus-station --mock

.PHONY: image shellcheck
image: ## build an image: make image VARIANT=cpu|cuda|jetson [PLATFORM=linux/amd64,linux/arm64]
	docker/build.sh $(VARIANT) $(if $(PLATFORM),--platform $(PLATFORM))
shellcheck: ## shellcheck the deploy and build scripts
	docker run --rm -v "$(CURDIR)":/mnt -w /mnt koalaman/shellcheck:v0.11.0 -x -S style \
	  deploy/install.sh deploy/hibiscus-station-ctl docker/build.sh docker/requirements-from-lock.sh \
	  web/scripts/node.sh web/scripts/sync-assets.sh
