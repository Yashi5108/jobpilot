# JobPilot

AI Job Search & Application Assistant

## Status

Early development.

JobPilot currently provides only a clean project foundation. Business features such as AI workflows, job search integrations, automation, and application tracking are planned for future tasks.

## Planned Architecture

- `backend/`: FastAPI service, core configuration, logging, APIs, and service layer.
- `frontend/`: Streamlit dashboard shell for user interaction.
- `data/`: Local, non-committed runtime artifacts (resumes/exports placeholders only).
- `docs/`: Architecture, setup, and development guidance.
- `tests/`: Automated tests for backend behavior.

## Planned Features

- Resume and profile management
- AI-assisted matching and recommendations
- Job discovery connectors
- Application workflow orchestration
- Exportable reports and tracking

Note: The above items are not implemented yet.

## Technology Stack

- Python 3.12+
- FastAPI + Uvicorn
- Pydantic + pydantic-settings
- SQLAlchemy
- Streamlit
- Pytest
- Ruff
- Black

## Local Setup

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -e ".[dev]"
```

3. Copy `.env.example` to `.env` and update values for your environment.

## Run Backend

```bash
uvicorn backend.main:app --reload
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

## Run Frontend

```bash
streamlit run frontend/app.py
```

## Run Tests

```bash
pytest
```

## Project Structure

```text
jobpilot/
├── backend/
├── frontend/
├── tests/
├── data/
├── docs/
├── pyproject.toml
└── README.md
```

## Roadmap

- Foundation and tooling setup (current)
- Core domain models and database layer
- API surface expansion
- Frontend flows and integrations
- AI and automation modules
- Hardening, testing expansion, and release process