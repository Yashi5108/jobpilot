# JobPilot Architecture (Planned)

## Status

This document describes the target architecture. Most components below are planned and not yet implemented.

## High-Level Overview

- Frontend (`frontend/app.py`): Streamlit-based user interface shell.
- Backend (`backend/main.py`): FastAPI service exposing API endpoints.
- Core (`backend/core/`): Shared configuration and logging.
- Data (`data/`): Local working files and exports, intentionally excluded from version control except placeholders.

## Planned Components

- API layer (`backend/api/`): HTTP routes grouped by domain.
- Services (`backend/services/`): Business logic and orchestration.
- Schemas (`backend/schemas/`): Pydantic request/response models.
- Database layer (`backend/database/`): SQLAlchemy engine, sessions, models, migrations.
- AI layer (`backend/ai/`): Planned model integrations and prompting workflows.
- Connectors (`backend/connectors/`): Planned external job-platform connectors.
- Automation (`backend/automation/`): Planned browser/task automation workflows.

## Runtime Flow (Planned)

1. Frontend calls backend APIs.
2. Backend routes validate payloads with schemas.
3. Services coordinate database operations and external integrations.
4. Responses are returned to frontend for display.

## Security and Data Safety Principles

- No secrets committed to version control.
- Sensitive user data remains local unless explicitly integrated in future tasks.
- Logging should avoid personal or secret data.
