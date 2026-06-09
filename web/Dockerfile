# syntax=docker/dockerfile:1
FROM node:22-slim AS frontend
WORKDIR /app/web/frontend
COPY web/frontend/package*.json ./
RUN npm install
COPY web/frontend ./
RUN npm run build

FROM python:3.12-slim AS backend
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080
WORKDIR /app
COPY requirements-runner.txt ./requirements-runner.txt
COPY web/requirements.txt ./web/requirements.txt
RUN pip install --no-cache-dir -r web/requirements.txt
COPY a11y_runner ./a11y_runner
COPY a11y_testkit ./a11y_testkit
COPY mechanical_rules.py ./mechanical_rules.py
COPY web/backend ./web/backend
COPY --from=frontend /app/web/frontend/dist ./web/frontend/dist
EXPOSE 8080
CMD ["sh", "-c", "uvicorn web.backend.app:app --host 0.0.0.0 --port ${PORT:-8080}"]
