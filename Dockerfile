FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

RUN useradd --create-home --uid 1000 medslot && chown -R medslot:medslot /app
USER medslot

# DJANGO_ALLOWED_HOSTS and CORS_ALLOWED_ORIGINS are read from the environment
# (see config/settings.py and docker-compose.yml).
EXPOSE 8000

# runserver on purpose: appointments live in an in-memory store, so the app must
# run as ONE process. A multi-worker server (gunicorn -w N) would give each worker
# its own store. --noreload avoids the autoreloader's second process.
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000", "--noreload"]
