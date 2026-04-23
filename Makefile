.PHONY: help install scrape parse build-graph embed translate pipeline serve ui test test-unit test-integration lint lint-fix format

help:  ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install:  ## Install all dependencies (requires uv)
	uv sync --all-extras

# ── Pipeline ──────────────────────────────────────────────────────────────────

scrape:  ## Crawl tow.whfb.app and save raw HTML to data/raw/
	python -m pipeline.run_pipeline --stage scrape

parse:  ## Parse raw HTML into structured JSON (data/parsed/)
	python -m pipeline.run_pipeline --stage parse

build-graph:  ## Load parsed JSON into Neo4j, apply constraints and indexes (data/graph/)
	python -m pipeline.run_pipeline --stage graph

embed:  ## Generate embeddings and write to Neo4j node properties
	python -m pipeline.run_pipeline --stage embed

translate:  ## Add/update translations for all supported languages
	python -m pipeline.run_pipeline --stage translate

pipeline:  ## Run full pipeline from scratch
	python -m pipeline.run_pipeline --all

# ── Services ──────────────────────────────────────────────────────────────────

serve:  ## Start FastAPI backend (http://localhost:8000)
	uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8000

ui:  ## Start Streamlit frontend (http://localhost:8501)
	streamlit run frontend/app.py

# ── Quality ───────────────────────────────────────────────────────────────────

test:  ## Run all tests
	pytest tests/ -v

test-unit:  ## Run unit tests only
	pytest tests/unit/ -v

test-integration:  ## Run integration tests only
	pytest tests/integration/ -v

format:  ## Auto-format with ruff
	ruff format .

lint:  ## Run ruff linter
	ruff check .

lint-fix:  ## Format then run ruff linter with autofix
	ruff format .
	ruff check . --fix
