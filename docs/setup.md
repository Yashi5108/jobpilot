# Setup Guide

## Prerequisites

- Python 3.12+
- Docker + Docker Compose (optional, for containerized run)
- Optional: Ollama for AI analysis/drafting
- Optional: Playwright browser binaries for live form-fill mode

## Step 1: Create the environment

```bash
cd /path/to/jobpilot
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
```

## Step 2: Copy the sample config

```bash
cp .env.example .env
```

Review the key variables in `.env`:

- `DATABASE_URL`
- `RESUME_STORAGE_DIR`
- `OLLAMA_BASE_URL`
- `OLLAMA_MODEL`
- `BROWSER_ASSISTANT_MODE`
- `BROWSER_AUTO_SUBMIT_ENABLED` (keep `false` unless you explicitly want a reviewed/manual flow)
- `BROWSER_RESTRICTED_HOSTS`

## Step 3: Apply database migrations

```bash
.venv/bin/alembic upgrade head
```

## Step 4: Start the API

```bash
/absolute/path/to/jobpilot/.venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000 --app-dir /absolute/path/to/jobpilot
```

Test the health endpoints:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/v1/health
```

## Step 5: Start the Streamlit app

```bash
/absolute/path/to/jobpilot/.venv/bin/streamlit run /absolute/path/to/jobpilot/frontend/app.py --server.headless true --server.port 8501
```

Open:

- Frontend: http://localhost:8501
- Backend: http://localhost:8000

## Optional: run with Ollama

```bash
ollama pull llama3.1
```

This enables AI resume/job analysis and drafting functions.

## Optional: run with Playwright

```bash
.venv/bin/playwright install chromium
```

Recommended default when you are testing locally:

- `BROWSER_ASSISTANT_MODE=playwright`
- `BROWSER_AUTO_SUBMIT_ENABLED=false`

This keeps the browser flow safe and review-oriented.

## Docker run

From the project root:

```bash
docker compose up --build
```

Optional Ollama service:

```bash
docker compose --profile ollama up --build
```

Stop the stack:

```bash
docker compose down
```

Reset volumes if needed:

```bash
docker compose down -v
```
