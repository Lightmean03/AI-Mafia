FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY game/ ./game/
COPY agents/ ./agents/
COPY api/ ./api/

# Optional: copy frontend dist for single-container deploy
# COPY frontend/dist/ ./static/

EXPOSE 8000

ENV PYTHONPATH=/app
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
