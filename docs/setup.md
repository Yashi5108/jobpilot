# Setup Guide

## Prerequisites

- Python 3.12+
- Optional: Ollama for AI analysis/drafting
- Optional: Playwright browsers for non-dry-run browser assistance

## Create Environment

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
```

## Configure Environment

```bash
cp .env.example .env
```

Key variables:

- `DATABASE_URL`
- `OLLAMA_BASE_URL`
- `OLLAMA_MODEL`
- `OLLAMA_TIMEOUT_SECONDS`
- `RESUME_STORAGE_DIR`
- `RESUME_UPLOAD_MAX_BYTES`
- `BROWSER_ASSISTANT_MODE`
- `BROWSER_HEADLESS`

## Database

Run schema migrations:

```bash
.venv/bin/alembic upgrade head
```

## Run Backend

Use absolute paths so commands work even outside repo root:

```bash
/absolute/path/to/jobpilot/.venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000 --app-dir /absolute/path/to/jobpilot
```

Health checks:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/v1/health
```

## Run Frontend

```bash
/absolute/path/to/jobpilot/.venv/bin/streamlit run /absolute/path/to/jobpilot/frontend/app.py --server.headless true --server.port 8501
```

## Ollama (Optional)

```bash
ollama pull llama3.1
```

Features using Ollama:

- resume analysis
- job analysis
- cover letter drafting
- selected screening drafts

Does not use Ollama:

- deterministic matching
- import/dedupe
- tracker/events
- analytics

## Playwright (Optional for live fill)

Install browser binaries:

```bash
.venv/bin/playwright install chromium
```

Recommended default:

- `BROWSER_ASSISTANT_MODE=dry_run`

Switch to live form-fill mode only when needed:

- `BROWSER_ASSISTANT_MODE=playwright`
