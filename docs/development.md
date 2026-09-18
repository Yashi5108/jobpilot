# Development Workflow

## Common Commands

```bash
make install
make lint
make format-check
make test
```

## Direct Commands

```bash
.venv/bin/ruff check .
.venv/bin/black --check .
.venv/bin/pytest -q
```

## Migration Workflow

- Never edit old migrations.
- Add a new migration for each schema change.
- Validate against a clean database:

```bash
.venv/bin/alembic upgrade head
```

## Service Design Rules

- Keep business logic in services.
- Keep route handlers thin.
- Keep matching deterministic and pure.
- Validate AI outputs before persistence.

## Safety Rules

- No scraping/credential harvesting/captcha bypass.
- No auto-submit behavior.
- Human approval is mandatory before `APPLIED`.
- Avoid sensitive logging (resume text, secrets, auth state).

## Testing Rules

- Mock Ollama in unit/integration tests.
- Mock or dry-run browser-assistant behavior.
- Use temp SQLite databases in tests.
- Preserve and extend existing tests.
