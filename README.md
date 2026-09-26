# JobPilot

AI Job Search & Application Assistant

## Overview

JobPilot is a local-first application that helps you:

- manage resume and profile data
- analyze resumes and jobs with Ollama
- compute deterministic resume-job match scores
- prepare application drafts for human review
- assist form filling with Playwright in safe mode
- track application lifecycle and events
- view local analytics

## Implemented Architecture

- Backend: FastAPI (`backend/main.py`)
- Frontend: Streamlit (`frontend/app.py`)
- ORM/DB: SQLAlchemy + Alembic + SQLite
- AI: Ollama client + strict Pydantic validation
- Browser Assistance: Playwright with manual-submit safeguard
- Quality: pytest + Ruff + Black

## End-to-End Flow

1. Resume upload and parsing
2. Resume AI analysis -> `CandidateProfile`
3. Job creation/import (manual, JSON, CSV)
4. Job AI analysis -> `JobAnalysis`
5. Deterministic matching -> `JobMatch`
6. Application preparation (cover letter + screening drafts)
7. `READY_FOR_REVIEW` human review screen
8. Browser assistance for safe field filling
9. Explicit human confirmation marks `APPLIED`
10. Application tracking and analytics

## Project Structure

```text
jobpilot/
├── backend/
│   ├── ai/
│   ├── api/
│   ├── browser/
│   ├── connectors/
│   ├── core/
│   ├── database/
│   ├── schemas/
│   └── services/
├── frontend/
├── alembic/
├── docs/
└── tests/
```

## Setup

1. Create and activate virtual environment:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install --upgrade pip
pip install -e ".[dev]"
```

3. Copy environment file:

```bash
cp .env.example .env
```

4. Run migrations:

```bash
.venv/bin/alembic upgrade head
```

## Configuration

Important environment variables:

- `DATABASE_URL` (default `sqlite:///./data/jobpilot.db`)
- `OLLAMA_BASE_URL`
- `OLLAMA_MODEL`
- `OLLAMA_TIMEOUT_SECONDS`
- `RESUME_STORAGE_DIR`
- `RESUME_UPLOAD_MAX_BYTES`
- `BROWSER_ASSISTANT_MODE` (`dry_run`, `mock`, or `playwright`)
- `BROWSER_HEADLESS`

## Run Backend

Use an absolute path to avoid working-directory issues:

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

## Ollama Usage

Ollama may be used for:

- resume analysis
- job analysis
- cover letter drafting
- selected screening answer drafting

Deterministic matching does **not** require Ollama.

## Security and Safety Guarantees

JobPilot intentionally does not implement:

- LinkedIn scraping or LinkedIn auto-apply
- CAPTCHA bypass or anti-bot bypass
- credential harvesting
- auto-submission of applications

Browser assistant behavior:

- maps and fills known fields conservatively
- flags unknown fields for user input
- never clicks final submit

Sensitive local files remain excluded by `.gitignore`:

- `.env`
- runtime SQLite DB files
- resume files
- browser auth/session artifacts

## Testing and Quality

```bash
.venv/bin/pytest -q
.venv/bin/ruff check .
.venv/bin/black --check .
```

## Docker

### Prerequisites

- Docker Engine and the Compose plugin
- A configured `.env` copied from `.env.example`
- Ollama available either on the host or through the optional Docker profile

### Environment Setup

Copy the example file and adjust secrets and endpoints:

```bash
cp .env.example .env
```

Set `SEARCH_API_KEY` for discovery if you want web search.
If you are running Ollama on the host, keep `OLLAMA_BASE_URL=http://host.docker.internal:11434`.
If you want Ollama in Docker, change it to `http://ollama:11434` and start the Ollama profile.

### Start the Stack

Backend and frontend:

```bash
docker compose up --build
```

Optional Ollama container:

```bash
docker compose --profile ollama up --build
```

### URLs

- Frontend: http://localhost:8501
- Backend: http://localhost:8000
- Backend health: http://localhost:8000/health
- API health: http://localhost:8000/api/v1/health

### Stop

```bash
docker compose down
```

To remove persistent volumes as well:

```bash
docker compose down -v
```

### Persistent Data

- SQLite data is stored in the named `jobpilot_data` volume
- Resumes are stored under `/data/jobpilot/resumes` inside that volume
- Ollama models are stored in the named `ollama_data` volume when the optional profile is used

### Run Tests

```bash
.venv/bin/pytest -q
.venv/bin/ruff check .
.venv/bin/black --check .
```

## Notes

- Keep all AI outputs validated with Pydantic before persistence.
- Use service-layer orchestration (`routes -> services -> database`).
- Keep business logic out of Streamlit pages and route handlers.
