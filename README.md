# EDITH — Wind Forecast Intelligence

A decision-time-safe wind forecast evaluation dashboard for the Gridbricks case study. EDITH compares UK national wind forecasts with actual generation for January 2026 using Elexon BMRS data.

## Features

- React dashboard with forecast-vs-actual charts, coverage, interval audit table, and CSV export.
- Elexon BMRS WINDFOR forecast publications and FUELHH actual generation filtered to fuel type WIND.
- Independent forecast selection for every expected hourly interval using the latest valid publication at or before the configured UTC cutoff on the preceding day.
- Exact UTC interval matching, MAE, RMSE, forecast-minus-actual bias, MAPE, and coverage.
- Missing observations remain missing; no zero-fill and no hardcoded sample metrics.
- FastAPI endpoints, Docker deployment, automated tests, and GitHub Actions CI.

Forecasts are hourly in the source data, while FUELHH actuals are half-hourly. EDITH aggregates each complete pair of half-hour actuals to an hourly mean; an hour is excluded from actual matching if either half-hour is missing.\n\n## Project layout

- `wind-forecast-dashboard/frontend/`: React, Vite, Recharts, Lucide icons.
- `wind-forecast-dashboard/backend/src/app.py`: FastAPI API.
- `wind-forecast-dashboard/backend/src/api/elexon_client.py`: Elexon HTTP client.
- `wind-forecast-dashboard/backend/src/services/`: normalization, selection, matching, metrics.
- `wind-forecast-dashboard/Dockerfile`: multi-stage frontend and Python image.
- `Dockerfile`: root-context Docker build.
- `wind-forecast-dashboard/vercel.json`: Vercel configuration for the configured project root.
- `.github/workflows/edith-ci.yml`: tests and frontend build.

## Run locally

Requirements: Python 3.11+ and Node.js 20+.

```bash
cd wind-forecast-dashboard
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux:
source .venv/bin/activate
pip install -r backend/requirements.txt
npm --prefix frontend install
npm --prefix frontend run build
uvicorn app:app --reload --port 8000
```

Open http://localhost:8000. API docs are at http://localhost:8000/docs. For frontend-only development, run `npm --prefix frontend run dev`; Vite proxies `/api` to localhost:8000.

## Tests

From `wind-forecast-dashboard/`:

```bash
npm --prefix frontend install
npm --prefix frontend run build
pytest -q
```

The tests cover timestamp parsing, generation normalization, WIND filtering, cutoff eligibility, interval matching, missingness, metric definitions, and API validation. Live Elexon behavior should be smoke-tested in the deployed environment as well.

## Docker

From the repository root:

```bash
docker build -t edith-wind-intelligence .
docker run --rm -p 8000:8000 edith-wind-intelligence
```

## Vercel

The connected project should use `wind-forecast-dashboard` as its Root Directory, with the FastAPI framework preset. That folder contains the Vercel configuration and build command for the React assets. Pushes to the configured branch trigger a deployment. After deployment, verify the frontend, `/api/health`, and `/api/overview` before sharing the URL.

## API

- `GET /api/health`: health status.
- `GET /api/overview?decision_date_from=2026-01-01&decision_date_to=2026-01-31&cutoff_time=12:00`: evaluation metrics and interval series.
- `GET /api/forecast-history/2026-01-15?decision_cutoff=2026-01-14T12:00:00Z`: all forecast publications and selected forecast per interval for one delivery date.

Evaluation dates are restricted to January 2026. All timestamps and decision cutoffs are UTC. Bias is forecast minus actual; positive bias indicates over-forecasting. MAPE excludes matched intervals with zero actual generation. Coverage is matched intervals divided by all expected hourly intervals.

## Limitations and submission checklist

- Metrics depend on records returned by Elexon and its API availability.
- Check the deployment logs and live data endpoint before final submission.
- Record the required customer pitch and technical walkthrough, keep the video unlisted and within the challenge's time limits, and verify all submission links in an incognito window.
