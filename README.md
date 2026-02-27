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

## API Credentials

Set optional real credentials in `.env`:
- `GSC_SITE_URL`
- `GSC_CREDENTIALS_JSON`
- `SEMRUSH_API_KEY`
- `AHREFS_API_KEY`
- `OPENAI_API_KEY`

MVP defaults to sample file adapters when keys are absent.

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
- `GET /runs`
- `GET /metrics`
- `GET/POST /sources`
- `POST /admin/run-ingestion`

## Tests

Run API tests:

```bash
docker compose exec api sh -c "pip install -r apps/api/requirements.txt && PYTHONPATH=/app/apps/api pytest apps/api/app/tests -q"
```
