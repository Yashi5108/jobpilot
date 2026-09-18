.PHONY: install lint format format-check test run-backend run-frontend

install:
	pip install -e ".[dev]"

lint:
	.venv/bin/ruff check .

format:
	.venv/bin/black .

format-check:
	.venv/bin/black --check .

test:
	.venv/bin/pytest -q

run-backend:
	.venv/bin/uvicorn backend.main:app --reload --app-dir $(CURDIR)

run-frontend:
	.venv/bin/streamlit run $(CURDIR)/frontend/app.py
