FROM node:22-alpine AS frontend-build
WORKDIR /app/frontend
COPY wind-forecast-dashboard/frontend/package*.json ./
RUN npm install
COPY wind-forecast-dashboard/frontend/ ./
RUN npm run build
FROM python:3.11-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000
WORKDIR /app
COPY wind-forecast-dashboard/backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY wind-forecast-dashboard/backend/ ./backend/
COPY wind-forecast-dashboard/app.py ./app.py
COPY --from=frontend-build /app/frontend/dist ./frontend/dist
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
