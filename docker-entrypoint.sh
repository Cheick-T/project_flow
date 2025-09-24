#!/bin/sh
set -o errexit
set -o nounset
set -o pipefail

export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-dfv_project.settings.production}"
echo "Using settings module: ${DJANGO_SETTINGS_MODULE}"

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  echo "Applying database migrations"
  python manage.py migrate --noinput
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
