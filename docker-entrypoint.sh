#!/bin/sh
set -o errexit
set -o nounset
set -o pipefail

export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-dfv_project.settings.production}"
echo "Using settings module: ${DJANGO_SETTINGS_MODULE}"
if [ -z "${DJANGO_SECRET_KEY:-}" ]; then
  echo "DJANGO_SECRET_KEY not set; generating ephemeral key for this container"
  DJANGO_SECRET_KEY="$(python - <<'PY'
import secrets
alphabet = "abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*(-_=+)"
print(''.join(secrets.choice(alphabet) for _ in range(50)), end="")
PY
)"
  export DJANGO_SECRET_KEY
fi
if [ -z "${DJANGO_ALLOWED_HOSTS:-}" ]; then
  echo "DJANGO_ALLOWED_HOSTS not set; defaulting to localhost,127.0.0.1"
  export DJANGO_ALLOWED_HOSTS="localhost,127.0.0.1,.onrender.com"
fi

if [ -z "${DJANGO_SECURE_SSL_REDIRECT:-}" ]; then
  export DJANGO_SECURE_SSL_REDIRECT="false"
fi

if [ -z "${DJANGO_SESSION_COOKIE_SECURE:-}" ]; then
  export DJANGO_SESSION_COOKIE_SECURE="false"
fi

if [ -z "${DJANGO_CSRF_COOKIE_SECURE:-}" ]; then
  export DJANGO_CSRF_COOKIE_SECURE="false"
fi


if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  echo "Applying database migrations"
  python manage.py migrate --noinput
fi

if [ "${RUN_COLLECTSTATIC:-true}" = "true" ]; then
  echo "Collecting static files"
  python manage.py collectstatic --noinput
fi

if [ "${IMPORT_DUMPS:-true}" = "true" ]; then
  if [ "${IMPORT_DUMPS_FORCE:-false}" = "true" ]; then
    echo "Importing CSV dumps with --force"
    python manage.py import_dumps --force
  else
    echo "Importing CSV dumps if database is empty"
    python manage.py import_dumps
  fi
fi

if [ "$#" -eq 0 ]; then
  set -- gunicorn
fi

if [ "$1" = "gunicorn" ]; then
  shift
  PORT="${PORT:-8000}"
  WORKERS="${GUNICORN_WORKERS:-3}"
  echo "Starting Gunicorn on port ${PORT} with ${WORKERS} worker(s)"
  set -- gunicorn dfv_project.wsgi:application --bind "0.0.0.0:${PORT}" --workers "${WORKERS}" "$@"
fi

exec "$@"
