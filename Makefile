.PHONY: dev test test-unit test-integration test-e2e test-functional test-security \
        smoke-test lint build docker-build docker-push deploy-dev deploy-prod \
        seed-mock-data clean pre-commit run-ai-local check-docs grpc-dev-certs

# Dev-only self-signed CA + server/client cert pair for the gRPC transport
# TLS required by every service in docker-compose.yml (security audit A02).
# Idempotent -- skips regeneration if certs/grpc-dev is already populated.
grpc-dev-certs:
	@bash scripts/setup/generate_dev_grpc_certs.sh

dev: grpc-dev-certs
	docker-compose up

build:
	docker-compose build

docker-build: build

docker-push:
	$(error docker-push is CI-only — beta/prod images built by GitHub Actions from release branches)

lint:
	@bash scripts/lint.sh

check-docs:
	@bash scripts/check-doc-refs.sh

test:
	@$(MAKE) test-unit

test-unit:
	@echo "Running unit tests..."
	@bash tests/k8s/alpha/05-unit-tests.sh

test-integration:
	@echo "Running integration tests..."
	@test -d tests/integration || { echo "tests/integration directory not found" >&2; exit 1; }
	@bash scripts/test-api-all.sh

test-e2e:
	@echo "Running e2e tests..."
	@test -f scripts/e2e-test-alpha.sh || { echo "scripts/e2e-test-alpha.sh not found" >&2; exit 1; }
	@bash scripts/e2e-test-alpha.sh

test-functional:
	$(error test-functional is not yet implemented — add pytest tests/functional/ -v after creating tests/functional directory)

test-security:
	@bash scripts/security-scan.sh

smoke-test:
	@echo "Running smoke tests..."
	@test -f tests/alpha-smoke-test.sh || { echo "tests/alpha-smoke-test.sh not found" >&2; exit 1; }
	@bash tests/alpha-smoke-test.sh

seed-mock-data:
	@echo "Seeding mock data..."
	@test -f scripts/seed-admin.sh || { echo "scripts/seed-admin.sh not found" >&2; exit 1; }
	@bash scripts/seed-admin.sh

clean:
	docker-compose down -v
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true

deploy-dev:
	@echo "Deploy to dev/alpha environment..."
	@test -f scripts/deploy-alpha.sh || { echo "scripts/deploy-alpha.sh not found" >&2; exit 1; }
	@bash scripts/deploy-alpha.sh

deploy-prod:
	$(error deploy-prod requires CI — tag a release to trigger the production pipeline)

run-ai-local: ## Run ai_interaction_module container locally (standalone, 1 worker)
	docker build -f action/interactive/ai_interaction_module/Dockerfile -t waddlebot/ai-interaction:local . && \
	docker run --rm \
	  --name ai-interaction-local \
	  --add-host=host.docker.internal:host-gateway \
	  --env-file action/interactive/ai_interaction_module/.env.local \
	  -e HYPERCORN_WORKERS=1 \
	  -p 8005:8005 \
	  waddlebot/ai-interaction:local

pre-commit:
	@echo "=== Pre-commit checks ==="
	@$(MAKE) lint
	@$(MAKE) test-security
	@$(MAKE) test
	@echo "=== Pre-commit complete ==="

# --- Gazer Mobile 2.0 (mobile/gazer) -----------------------------------
# Every target below runs inside the gazer-toolchain image -- never on the
# host. Host Flutter (snap) is never invoked directly; see docs/superpowers/
# specs/2026-09-07-gazer-mobile-v2-design.md Toolchain, CI, Versioning.
.PHONY: mobile-toolchain mobile-run mobile-lint mobile-test mobile-test-android mobile-build mobile-security mobile-codegen mobile-clean mobile-test-integration mobile-screenshots seed-mock-data-mobile
# mobile-test-integration is added later by Task 21; mobile-screenshots and
# seed-mock-data-mobile are added later by Task 26 -- pre-declared phony here
# (harmless before those targets exist) so the whole mobile-* target set is
# uniformly a .PHONY gate from the very first commit.

MOBILE_IMAGE := gazer-toolchain:3.47.2
MOBILE_RUN := docker run --rm --user $(shell id -u):$(shell id -g) \
	-v $(CURDIR)/mobile/gazer:/work \
	-v gazer-pub-cache:/home/appuser/.pub-cache \
	-v gazer-gradle:/home/appuser/.gradle \
	-w /work $(MOBILE_IMAGE)

mobile-toolchain:
	docker build -t $(MOBILE_IMAGE) mobile/gazer

mobile-run:
	@test -n "$(CMD)" || { echo "usage: make mobile-run CMD=\"<command>\"" >&2; exit 1; }
	$(MOBILE_RUN) bash -lc "$(CMD)"

mobile-lint:
	$(MOBILE_RUN) bash -lc "set -euo pipefail; flutter analyze; dart format --set-exit-if-changed .; if [ -d android ]; then cd android && ./gradlew ktlintCheck lint; fi"

mobile-test:
	$(MOBILE_RUN) bash -lc "set -euo pipefail; flutter test --coverage; bash scripts/coverage_gate.sh 90 coverage/lcov.info lcov"

mobile-test-android:
	$(MOBILE_RUN) bash -lc "set -euo pipefail; cd android && ./gradlew testDebugUnitTest jacocoTestReport && cd .. && bash scripts/coverage_gate.sh 90 android/app/build/reports/jacoco/jacocoTestReport/jacocoTestReport.xml jacoco"

mobile-build:
	$(MOBILE_RUN) bash -lc "set -euo pipefail; flutter build apk --split-per-abi --obfuscate --split-debug-info=build/symbols; flutter build appbundle --obfuscate --split-debug-info=build/symbols"

# Gates on android/app/gradle.lockfile, which locks only the classpaths :app actually ships
# (controller ruling R23) -- osv-scanner never sees build-tooling-only dependencies (AGP's
# Unified Test Platform, ktlint, kotlin compiler tooling), which this project cannot meaningfully
# remediate and which never reach a device. R23 Step 3 also asked for a non-gating advisory scan
# of the FULL dependency graph (all configurations, tooling included) alongside this gate.
# Omitted: Gradle's dependency-locking writer has no supported option to target a lockfile path
# other than the project's own gradle.lockfile, so a second full-graph scan would require either
# repeatedly toggling lockAllConfigurations() on and off across separate ./gradlew invocations (a
# multi-minute round trip on every `make mobile-security`, and disruptive to the real,
# shipped-classpath lockfile this target gates on) or a bespoke Gradle init script/plugin to
# redirect the lock output -- both too invasive to add reliably within this task. Noted here per
# R23's explicit escape hatch rather than left unexplained.
mobile-security:
	$(MOBILE_RUN) bash -lc "set -euo pipefail; bash scripts/osv_scan_assert.sh pubspec.lock; bash scripts/osv_scan_assert.sh android/app/gradle.lockfile; semgrep --config auto --error .; gitleaks detect --source . --no-git -v"

mobile-codegen:
	$(MOBILE_RUN) bash -lc "set -euo pipefail; dart run pigeon --input pigeons/pipeline.dart; dart run build_runner build --delete-conflicting-outputs; flutter gen-l10n"

mobile-clean:
	$(MOBILE_RUN) bash -lc "set -euo pipefail; flutter clean; if [ -d android ]; then cd android && ./gradlew clean; fi"
