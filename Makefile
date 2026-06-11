PYTHON ?= python
DIST_DIR ?= dist
PYTEST := PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 $(PYTHON) -m pytest

.PHONY: test test-cov lint secret-scan security validate-data validate-metadata build pre-commit ci

test:
	$(PYTEST) tests/ -q

test-cov:
	$(PYTEST) -p pytest_cov tests/ -q --cov=src --cov-report=xml --cov-report=term-missing

lint:
	$(PYTHON) -m ruff check papertools.py src/ tests/ scripts/ --output-format=github
	$(PYTHON) -m ruff format papertools.py src/ tests/ scripts/ --check

secret-scan:
	$(PYTHON) scripts/check_secrets.py

security: secret-scan
	$(PYTHON) -m bandit -r src/ papertools.py -c pyproject.toml -f txt --severity-level medium --confidence-level high

validate-data:
	$(PYTHON) scripts/validate_published_payloads.py

validate-metadata:
	$(PYTHON) scripts/check_dependency_metadata.py

build:
	rm -rf $(DIST_DIR)
	$(PYTHON) -m pip wheel . --no-deps --wheel-dir $(DIST_DIR)

pre-commit:
	$(PYTHON) -m pre_commit run --all-files

ci: pre-commit lint test-cov security validate-data validate-metadata build
