.PHONY: test test-server test-dashboard test-plugin lint ci smoke

test: test-server test-dashboard test-plugin

test-server:
	pytest server/tests/ -v --tb=short

test-dashboard:
	cd dashboard && npx vitest run --reporter=verbose

test-plugin:
	pytest plugin/tests/ -v --tb=short

lint:
	ruff check server/src/

ci: lint test

smoke:
	pytest server/tests/ -m smoke -v --tb=short
	cd dashboard && npx vitest run --reporter=dot
