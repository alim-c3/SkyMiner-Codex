.PHONY: setup install install-live install-dev smoke-test run test test-cov lint clean help

# Default target
.DEFAULT_GOAL := help

## setup: Create output directories and copy .env.example to .env if not present
setup:
	@mkdir -p outputs/reports outputs/plots outputs/candidates outputs/logs
	@if [ ! -f .env ]; then cp .env.example .env && echo "Created .env from .env.example"; else echo ".env already exists, skipping"; fi

## install: Install core package in editable mode (no live-data extras)
install:
	pip install -e .

## install-live: Install with live-data extras (lightkurve + astroquery for TESS/MAST)
install-live:
	pip install -e ".[live]"

## install-dev: Install with live-data and development extras (pytest, coverage, mocks)
install-dev:
	pip install -e ".[live,dev]"

## smoke-test: Run the offline smoke test using bundled sample data (no network required)
smoke-test:
	python -m skyminer.cli smoke-test

## run: Run the full pipeline in local/offline mode
run:
	python -m skyminer.cli run-pipeline --mode local

## test: Run the full test suite with verbose output
test:
	pytest tests/ -v

## test-cov: Run tests with line-level coverage report
test-cov:
	pytest tests/ --cov=skyminer --cov-report=term-missing

## lint: Lint source and test code (uses ruff if available, falls back to flake8)
lint:
	@if command -v ruff >/dev/null 2>&1; then \
		echo "Running ruff..."; \
		python -m ruff check src/ tests/; \
	elif command -v flake8 >/dev/null 2>&1; then \
		echo "ruff not found, falling back to flake8..."; \
		python -m flake8 src/ tests/; \
	else \
		echo "No linter found. Install ruff: pip install ruff"; \
		exit 1; \
	fi

## clean: Remove Python caches, pytest artifacts, and the outputs directory
clean:
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@find . -type f -name "*.pyo" -delete 2>/dev/null || true
	@rm -rf .pytest_cache
	@rm -rf .coverage htmlcov
	@rm -rf dist build
	@find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@rm -rf outputs/reports outputs/plots outputs/candidates outputs/logs
	@rm -f outputs/skyminer.sqlite
	@echo "Clean complete."

## help: Print this help message listing all available targets
help:
	@echo ""
	@echo "SkyMiner Makefile targets:"
	@echo ""
	@grep -E '^## ' Makefile | sed 's/## /  /' | column -t -s ':'
	@echo ""
