FROM python:3.12-slim
WORKDIR /srv/folio
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

COPY backend/pyproject.toml backend/pyproject.toml
COPY backend/app backend/app
RUN python -m pip install --no-cache-dir ./backend
COPY backend/migrations backend/migrations
COPY contracts/exam_schema.sql contracts/exam_schema.sql

USER 65532:65532
CMD ["sh", "-c", "exec python -m uvicorn backend.app.main:create_app --factory --host 0.0.0.0 --port \"${PORT:-8000}\""]
