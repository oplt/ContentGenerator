.PHONY: local-dev docker-dev prod-dev fix check install-hooks commit-ready quality-gates \
	regression-unit regression-integration regression e2e-ci line-budget

local-dev:
	$(MAKE) -f Makefile.local local-dev

docker-dev:
	$(MAKE) -f Makefile.docker docker-dev

prod-dev:
	$(MAKE) -f Makefile.deploy prod-dev

fix:
	cd backend && .venv/bin/ruff check . --fix
	cd backend && .venv/bin/ruff format .

line-budget:
	python3 scripts/check_file_line_budget.py

check:
	cd backend && .venv/bin/ruff check .
	cd backend && .venv/bin/mypy .
	cd frontend && npm run lint
	cd frontend && npx tsc --noEmit
	$(MAKE) line-budget

regression-unit:
	cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -q -m "not integration"

regression-integration:
	cd backend && CG_RUN_DB_MIGRATIONS=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -q -m integration

regression: regression-unit
	cd frontend && npm test -- --run
	cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -q tests/benchmarks

e2e-ci:
	cd frontend && npx playwright install --with-deps chromium
	cd frontend && npx playwright test --project=chromium --project=mobile-chrome

quality-gates: check regression-unit
	cd frontend && npm test -- --run
	cd frontend && npm run build
	@tracked="$$(git ls-files)"; \
	for pattern in '^dump\.rdb$$' '\.rdb$$' '^frontend/playwright-report/' '^frontend/test-results/' '^frontend/blob-report/' '\.tsbuildinfo$$'; do \
	  matches="$$(printf '%s\n' "$$tracked" | grep -E "$$pattern" || true)"; \
	  if [ -n "$$matches" ]; then echo "Tracked runtime artifact(s): $$matches"; exit 1; fi; \
	done; \
	echo "repo-hygiene OK"

install-hooks:
	pre-commit install

commit-ready: fix check
