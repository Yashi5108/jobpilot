# JobPilot Architecture

## Layers

- API routes: request/response boundary, validation, HTTP errors
- Services: orchestration, lifecycle, business rules
- AI/browser/connectors: integration boundaries
- Database models: persistence
- Schemas: typed contracts

Core direction:

- routes -> services -> database
- services -> AI / browser / connectors

## Implemented Modules

- `backend/connectors/`: safe manual and structured import connectors
- `backend/ai/`: resume/job analysis and application drafting prompts
- `backend/services/matching/`: deterministic matching engine
- `backend/services/application_preparation_service.py`: preparation orchestration
- `backend/browser/`: conservative field mapping and Playwright assistant
- `backend/services/application_service.py`: lifecycle transitions and event logging
- `backend/services/analytics_service.py`: local read-only analytics

## Functional Flow

1. Resume -> parser -> ResumeAnalysis
2. Job source connector -> normalized job -> dedupe -> Job
3. Job -> JobAnalysis
4. ResumeAnalysis + JobAnalysis -> deterministic matching -> JobMatch
5. Match + resume + job -> application preparation drafts
6. `READY_FOR_REVIEW` payload for human approval
7. Browser assistant maps/fills known fields
8. Human submits externally
9. Explicit confirmation sets `APPLIED`
10. Application tracker + analytics consume stored local data

## Human-Approval Guard

`APPLIED` is protected:

- status patch cannot directly set `APPLIED`
- explicit user approval endpoint is required
- explicit submission-confirmation endpoint is required
- browser assistant never triggers `APPLIED`

## Browser Assistant Safety

- Never bypasses CAPTCHA/authentication/MFA.
- Unknown required fields are returned as `unknown_fields`.
- File upload/custom widgets remain manual.
- Final submission is always manual.

## Privacy

- Local-first storage and AI by default.
- No external analytics export.
- No automated scraping or credential collection.
