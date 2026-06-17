# AI Content Demand Capture Agent (MVP)

Production-minded MVP for capturing and prioritizing SEO/AEO/GEO demand with FastAPI + Celery + Postgres + Next.js.

## Repo Layout

- `apps/api`: FastAPI backend, adapters, scoring, detection, migrations, tests
- `apps/web`: Next.js App Router frontend with dashboard, inbox, brief editor, scheduler, settings
- `worker`: Celery worker + beat scheduler jobs
- `sample_data`: CSV/JSON/XML mock inputs for no-key local execution
- `scripts/seed_data.py`: creates demo user and ingests sample data

## Run Locally

1. Copy env file:

```bash
cp .env.example .env
```

2. Start stack:

```bash
docker compose up --build
```

3. Seed data (in another shell):

```bash
docker compose exec api sh -c "PYTHONPATH=/app/apps/api python scripts/seed_data.py"
```

4. Open web app: `http://localhost:3000`

Demo credentials:
- email: `demo@zeni.ai`
- password: `demo1234`

Note:
- API startup auto-seeds demo user and sample opportunities when DB is empty (`AUTO_SEED_ON_STARTUP=true`).

## API Credentials

Set optional real credentials in `.env`:
- `GSC_SITE_URL`
- `GSC_CREDENTIALS_JSON`
- `SEMRUSH_API_KEY`
- `AHREFS_API_KEY`
- `OPENAI_API_KEY`
- `OPENAI_MODEL` (default `gpt-4.1-mini`)
- `GOOGLE_OAUTH_CLIENT_ID`
- `GOOGLE_OAUTH_CLIENT_SECRET`
- `GOOGLE_OAUTH_REDIRECT_URI` (default `http://localhost:3000/oauth/google/callback`)
- `SOURCE_ENCRYPTION_KEY` (used to encrypt stored source secrets)

MVP defaults to sample file adapters when keys are absent.

## Source Integrations (Settings page)

- Google Search Console:
  - Uses OAuth 2.0 (`Connect Google Account` in Settings).
  - Callback URL must match `GOOGLE_OAUTH_REDIRECT_URI` exactly.
  - `Test connection` calls Search Console Sites API.
- SEMrush:
  - API key flow (provider does not expose standard user OAuth flow for this MVP path).
- Ahrefs:
  - API key flow (provider does not expose standard user OAuth flow for this MVP path).
- AI Citations:
  - Configurable provider + optional API key + tracked prompts/competitors/brand terms.
  - Mock mode works without keys.


## Brief -> Article Generation

- Open any brief at `/briefs/{id}` and click `Generate content`.
- If `OPENAI_API_KEY` is set, the API generates publication-ready markdown via OpenAI.
- If no key is set, the app uses a deterministic local template fallback so the flow still works offline.
- Generated article output is persisted on the opportunity and shown to end users in the Brief page.

## Scheduler Jobs

Celery beat schedules:
- Nightly ingestion (dev cadence currently every 60s)
- Hourly trend detection (dev cadence every 60s)
- Weekly competitor velocity (dev cadence every 300s)

## Add New Adapters

1. Create adapter under `apps/api/app/services/adapters/` implementing:
   - `validate_config()`
   - `fetch()`
   - `normalize()`
2. Register it in `apps/api/app/services/ingestion.py`
3. Add source config via `/sources` endpoint and settings UI
4. Add unit tests in `apps/api/app/tests/`

## REST Endpoints

- `POST /auth/register`
- `POST /auth/login`
- `GET /opportunities`
- `PATCH /opportunities/{id}`
- `GET /opportunities/{id}/brief`
- `GET /opportunities/{id}/content`
- `POST /opportunities/{id}/content/generate`
- `GET /runs`
- `GET /metrics`
- `GET/POST /sources`
- `POST /admin/run-ingestion`

## Tests

Run API tests:

```bash
docker compose exec api sh -c "pip install -r apps/api/requirements.txt && PYTHONPATH=/app/apps/api pytest apps/api/app/tests -q"
```
