.PHONY: help install check test npm-test npm-typecheck packages-check contracts contracts-check host-sdks client-api sdk-docs clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# igni's SDKs, one repository, released in lockstep (docs/PUBLISHING_THE_SDKS.md).
#
#   Python   packages/igni-service, packages/igni-extension, packages/igni-client
#   npm      packages/extension-bridge, packages/ui-react, clients/ui
#
# Each Python SDK is a package of its own with its own environment, which uv
# makes from its pyproject. The repository root has one more, for the host
# generator and the tests that hold the SDKs to igni-core's contracts.

install: ## Make the root environment and install the npm workspaces
	uv sync
	npm ci

check: test packages-check npm-typecheck npm-test ## Everything CI runs

test: ## The repository's own tests: generated SDKs, contracts, docs, lint rules
	uv run ruff check tests tools scripts
	uv run ruff format --check tests tools scripts
	uv run pytest -q

npm-test: ## The npm SDKs' tests
	npx vitest run

npm-typecheck: ## Type-check the npm SDKs
	npx tsc --noEmit -p .

# The contracts this repository builds against are igni-core's: it publishes
# them, contracts/ holds copies (scripts/sync_contracts.py).
contracts: ## Refresh contracts/ from igni-core (../igni-core or IGNI_CORE_DIR), then regenerate
	uv run python scripts/sync_contracts.py
	$(MAKE) --no-print-directory host-sdks
	$(MAKE) --no-print-directory client-api
	$(MAKE) --no-print-directory sdk-docs

contracts-check: ## Fail when a copy in contracts/ differs from igni-core's
	uv run python scripts/sync_contracts.py --check

# The host object model is described once, in igni-core, and both SDKs'
# `host` objects are generated from contracts/host-schema.json.
# tests/test_the_host_sdks_are_generated.py fails when what is checked in is
# stale; this regenerates it.
host-sdks: ## Regenerate the SDKs' host objects from contracts/host-schema.json
	uv run python -c "from pathlib import Path; from tools.host_codegen import HostSdks; [print('wrote', p) for p in HostSdks(Path('.')).write()]"

# igni-client's models and methods are generated from igni-core's RPC
# contract, contracts/rpc-contract.json, as is the API reference in its
# README. tests/test_the_client_api_is_generated.py fails when what is
# checked in is stale; this regenerates it.
client-api: ## Regenerate igni-client's models, methods and API reference from contracts/rpc-contract.json
	uv run python -m tools.client_codegen

# The SDKs' documentation on igni's site (ignite-ember.sh/docs/sdk), a page
# per topic: each README cut at its sections, igni-client's reference from
# the contract, igni-service's and igni-extension's from their code. The
# site copies docs/site/ (scripts/sync-sdk-docs.mjs there).
# tests/test_the_sdk_docs_are_generated.py fails when it is stale.
sdk-docs: ## Regenerate the SDKs' site pages in docs/site/ from the READMEs, the contract and the code
	uv run python -m tools.sdk_docs

PY_PACKAGES := packages/igni-service packages/igni-extension packages/igni-client

packages-check: ## Lint, type-check and test the Python SDKs
	@for pkg in $(PY_PACKAGES); do \
		echo "== $$pkg"; \
		uv run --directory $$pkg ruff check src tests || exit 1; \
		uv run --directory $$pkg ruff format --check src tests || exit 1; \
		uv run --directory $$pkg mypy || exit 1; \
		uv run --directory $$pkg pytest -q || exit 1; \
	done

clean: ## Remove build artifacts and caches
	rm -rf dist/
	find . -type d -name __pycache__ -not -path "*/node_modules/*" -exec rm -rf {} + 2>/dev/null || true
	find . -type d \( -name .mypy_cache -o -name .pytest_cache -o -name .ruff_cache \) -exec rm -rf {} + 2>/dev/null || true

# ── Publishing the SDKs ─────────────────────────────────────────────────
#
# Six packages, one version — docs/PUBLISHING_THE_SDKS.md. Python, on
# PyPI: igni-service, igni-extension, igni-client. npm, on npmjs:
# @ignite-ember/extension-bridge, @ignite-ember/ui-react, and the
# stylesheet @ignite-ember/ui-css (clients/ui), which @ignite-ember/ui-react's
# README tells an extension to install beside it. They are released
# together by pushing the tag `sdk-v<version>`
# (.github/workflows/sdk-release.yml), which runs `sdk-build` and then
# publishes what it made with PyPI's and npm's trusted publishing — no
# token is kept anywhere, so there is no publish target here.
SDK_PY_PACKAGES := $(PY_PACKAGES)
SDK_NPM_PACKAGES := packages/extension-bridge packages/ui-react clients/ui
SDK_DIST := dist/sdk

# Every manifest's version, checked to be one version. The npm form is
# the canonical spelling (`0.2.0`, `0.2.0-rc.1`) and the tag's; a
# pyproject may carry the same version normalised the PEP 440 way
# (`0.2.0rc1`), which is what `uv version` writes.
define SDK_VERSIONS_PY
import json, pathlib, re, sys, tomllib
want, py, npm = sys.argv[1], sys.argv[2].split(), sys.argv[3].split()
SEMVER = re.compile(r"\d+\.\d+\.\d+(-(alpha|beta|rc)\.\d+)?")
def pep440(v):
    return re.sub(r"-(alpha|beta|rc)\.(\d+)", lambda m: dict(alpha="a", beta="b", rc="rc")[m[1]] + m[2], v)
found = {p + "/pyproject.toml": tomllib.loads(pathlib.Path(p, "pyproject.toml").read_text())["project"]["version"] for p in py}
found.update({p + "/package.json": json.loads(pathlib.Path(p, "package.json").read_text())["version"] for p in npm})
for path, version in found.items():
    print(f"  {version:<16}{path}")
npm_versions = {found[p + "/package.json"] for p in npm}
if len(npm_versions) != 1 or {pep440(v) for v in found.values()} != {pep440(v) for v in npm_versions}:
    sys.exit("The SDK versions disagree. They are released in lockstep: make sdk-version VERSION=<x.y.z>")
version = npm_versions.pop()
if not SEMVER.fullmatch(version):
    sys.exit(f"{version} is not x.y.z or x.y.z-(alpha|beta|rc).N, the forms both npm and PEP 440 read the same way")
if want and want != version:
    sys.exit(f"The SDK version is {version}, not {want}")
print(f"SDK version {version}")
endef
export SDK_VERSIONS_PY

.PHONY: sdk-version sdk-version-check sdk-build

sdk-version-check: ## Check the six SDK packages carry one version (and VERSION=, when given)
	@uv run --no-project --python 3.12 python -c "$$SDK_VERSIONS_PY" "$(VERSION)" "$(SDK_PY_PACKAGES)" "$(SDK_NPM_PACKAGES)"

sdk-version: ## Set the six SDK packages' version: make sdk-version VERSION=0.2.0
	@test -n "$(VERSION)" || { echo "VERSION=<x.y.z> is required"; exit 1; }
	@for pkg in $(SDK_PY_PACKAGES); do uv version --directory $$pkg --no-sync "$(VERSION)" || exit 1; done
	@for pkg in $(SDK_NPM_PACKAGES); do \
		(cd $$pkg && npm version --no-git-tag-version --allow-same-version "$(VERSION)" >/dev/null) || exit 1; \
	done
	@$(MAKE) --no-print-directory sdk-version-check VERSION="$(VERSION)"

sdk-build: sdk-version-check ## Build the six SDK packages into dist/sdk/ (wheels, sdists, npm tarballs)
	rm -rf $(SDK_DIST)
	@for pkg in $(SDK_PY_PACKAGES); do \
		uv build --no-sources --out-dir $(SDK_DIST)/python $$pkg || exit 1; \
	done
	@mkdir -p $(SDK_DIST)/npm
	@for pkg in $(SDK_NPM_PACKAGES); do \
		(cd $$pkg && npm pack --silent --pack-destination $(abspath $(SDK_DIST))/npm) || exit 1; \
	done
	@ls -1 $(SDK_DIST)/python $(SDK_DIST)/npm
