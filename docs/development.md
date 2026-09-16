# Development Workflow

## Common Commands

```bash
make install
make lint
make format-check
make test
```

## Run Services

Backend:

```bash
make run-backend
```

Frontend:

```bash
make run-frontend
```

## Code Quality

- Ruff is used for linting.
- Black is used for formatting.
- Pytest is used for tests.

Run before opening pull requests:

```bash
ruff check .
black --check .
pytest
```

## Notes

- Keep changes small and reviewable.
- Avoid committing secrets or personal data.
- Add tests alongside new backend behavior.
