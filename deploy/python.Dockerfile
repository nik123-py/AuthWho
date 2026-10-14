# AuthWho Python services: API, worker, research export, retention, migrations and the demo backend.
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN useradd --create-home --uid 10001 authwho \
    && mkdir -p /data/demo /app/data/volunteer \
    && chown -R authwho:authwho /data /app

WORKDIR /app
COPY pyproject.toml README.md ./
COPY server ./server
COPY ml ./ml
COPY demo_app/__init__.py ./demo_app/__init__.py
COPY demo_app/backend ./demo_app/backend
RUN pip install .

USER authwho
EXPOSE 8000 8100
CMD ["python", "-m", "uvicorn", "server.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
