FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend/src ./src

# Create non-root user for security
RUN useradd -m appuser
USER appuser

# Expose FastAPI port
EXPOSE 8000

# Default command to run the application
CMD ["uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "8000"]