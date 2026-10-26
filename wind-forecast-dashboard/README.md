# EDITH — Wind Forecast Intelligence

EDITH is a decision-time-safe wind forecast evaluation dashboard for the Gridbricks case study. It compares UK national wind forecasts with actual generation for January 2026 using Elexon BMRS data.

## What it does

- Retrieves WINDFOR forecast publications and FUELHH generation records from Elexon BMRS.
- Filters actual generation to fuel type WIND.
- Evaluates every expected hourly delivery interval in January 2026.
- Selects the latest valid forecast published at or before the configured UTC cutoff on the preceding day, independently for each interval.
- Matches forecast and actual records by exact UTC interval start.
- Reports MAE, RMSE, signed bias, MAPE (excluding zero actuals), coverage, missingness, and interval-level provenance.
- Preserves missing values as missing; absent observations are never replaced with zero.
- Provides a React dashboard, interval audit table, CSV export, and methodology page.

Forecasts are hourly in the source data, while FUELHH actuals are half-hourly. EDITH aggregates each complete pair of half-hour actuals to an hourly mean; an hour is excluded from actual matching if either half-hour is missing.\n\n## Architecture

- frontend/: React, Vite, Recharts, Lucide icons.
- backend/src/app.py: FastAPI routes.
- backend/src/api/elexon_client.py: Elexon HTTP client.
- backend/src/services/: normalization, forecast selection, matching, and metrics.
- Dockerfile: multi-stage frontend build plus Python runtime.
- vercel.json and app.py: Vercel FastAPI entrypoint and frontend build configuration.

## Run locally

Requirements: Python 3.11+ and Node.js 20+.

    cd wind-forecast-dashboard
    python -m venv .venv
    # Windows: .venv\\Scripts\\activate
    # macOS/Linux:
    source .venv/bin/activate
    pip install -r backend/requirements.txt
    npm --prefix frontend install
    npm --prefix frontend run build
    uvicorn app:app --reload --port 8000

Open http://localhost:8000. API docs are at http://localhost:8000/docs.

For frontend-only development, run npm --prefix frontend run dev; Vite proxies /api to localhost:8000.

## Tests

From wind-forecast-dashboard/:

    pytest -q

Tests cover timestamp normalization, zero/missing-value behavior, wind filtering, cutoff eligibility, exact interval matching, metrics, and API input validation. The live Elexon integration should also be smoke-tested in the target deployment environment.

## Docker

    docker build -t edith-wind-intelligence .
    docker run --rm -p 8000:8000 edith-wind-intelligence

## Vercel deployment

Set the Vercel project's Root Directory to wind-forecast-dashboard. Keep the FastAPI framework preset and allow the project to build the React frontend using vercel.json. Pushes to the configured Git branch trigger a deployment. After the build, smoke-test the frontend, /api/health, and /api/overview on the deployed URL.

If the Vercel project currently uses a different root directory or custom build command, align its project settings with this folder before relying on deployment status.

## API

- GET /api/health: health response.
- GET /api/overview?decision_date_from=2026-01-01&decision_date_to=2026-01-31&cutoff_time=12:00: period metrics and interval series.
- GET /api/forecast-history/2026-01-15?decision_cutoff=2026-01-14T12:00:00Z: publication history and selected forecast per interval for a delivery date.

Dates are restricted to January 2026 for this case study. The cutoff is UTC and represents the previous day's decision time. All metric values are based on records returned by Elexon; the dashboard does not fabricate demo values.

## Metric interpretation and limitations

- MAE and RMSE are measured in MW; lower values indicate smaller errors.
- Bias is forecast minus actual; positive means over-forecasting.
- Coverage is valid matched intervals divided by all expected intervals in the selected date range.
- MAPE excludes zero actual-generation intervals to avoid division by zero.
- Results depend on Elexon's returned records and API availability. A successful health check does not prove data-source availability.
- Verify the deployed app against live BMRS responses before final submission.
