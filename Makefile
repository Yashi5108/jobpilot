.PHONY: install lint format format-check test run-backend run-frontend

install:
	pip install -e ".[dev]"

lint:
	ruff check .

format:
	black .

format-check:
	black --check .

test:
	pytest

run-backend:
	uvicorn backend.main:app --reload

run-frontend:
	streamlit run frontend/app.py
