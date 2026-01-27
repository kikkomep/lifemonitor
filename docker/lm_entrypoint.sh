#!/bin/bash

# Copyright (c) 2020-2026 CRS4
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

set -o nounset
set -o errexit

export POSTGRESQL_USERNAME="${POSTGRESQL_USERNAME:-lm}"
export POSTGRESQL_DATABASE="${POSTGRESQL_DATABASE:-lm}"
export KEY=${LIFEMONITOR_TLS_KEY:-/certs/lm.key}
export CERT=${LIFEMONITOR_TLS_CERT:-/certs/lm.crt}
export GUNICORN_CONF="${GUNICORN_CONF:-/lm/gunicorn.conf.py}"

# wait for services
wait-for-postgres.sh
wait-for-redis.sh

if [[ "${LIFEMONITOR_ENV}" == "development" || "${LIFEMONITOR_ENV}" == "testingSupport" ]]; then
  printf "Staring app in DEV mode (Flask built-in web server with auto reloading)"
  python "${HOME}/app.py"
else
  PROMETHEUS_MULTIPROC_DIR=${PROMETHEUS_MULTIPROC_DIR:-}
  if [[ -z ${PROMETHEUS_MULTIPROC_DIR} ]]; then
    metrics_base_path="/tmp/lifemonitor/metrics"
    mkdir -p ${metrics_base_path}
    export PROMETHEUS_MULTIPROC_DIR=$(mktemp -d ${metrics_base_path}/backend.XXXXXXXX)
  fi

# Compute the number of recommended workers based on the number of CPU cores
# Formula: (number of cores * 2) + 1
# This is a common recommendation for Gunicorn to optimize performance
# Reference: https://docs.gunicorn.org/en/stable/design.html#how-many-workers
# Note: This is a heuristic and may need adjustment based on the specific application and workload
# For example, if you have 4 CPU cores, the recommended number of workers would be 9
# (4 * 2) + 1 = 9  
RECOMMENDED_WORKERS=$(( $(nproc) * 2 + 1 ))

  # gunicorn settings
  export GUNICORN_SERVER="true"
  export GUNICORN_WORKERS="${GUNICORN_WORKERS:-$RECOMMENDED_WORKERS}"
  export GUNICORN_THREADS="${GUNICORN_THREADS:-2}"
  export GUNICORN_WORKER_CLASS="${GUNICORN_WORKER_CLASS:-sync}"
  export GUNICORN_MAX_REQUESTS="${GUNICORN_MAX_REQUESTS:-0}"
  export GUNICORN_MAX_REQUESTS_JITTER="${GUNICORN_MAX_REQUESTS_JITTER:-0}"
  export GUNICORN_WORKER_CONNECTIONS="${GUNICORN_WORKER_CONNECTIONS:-1000}"
  export GUNICORN_TIMEOUT="${GUNICORN_TIMEOUT:-30}"
  export GUNICORN_GRACEFUL_TIMEOUT="${GUNICORN_GRACEFUL_TIMEOUT:-30}"
  export GUNICORN_KEEPALIVE="${GUNICORN_KEEPALIVE:-10}"

  # run app with gunicorn
  printf "Starting app in PROD mode (Gunicorn)"
  gunicorn  --workers "${GUNICORN_WORKERS}"  \
            --threads "${GUNICORN_THREADS}" \
            --max-requests "${GUNICORN_MAX_REQUESTS}" \
            --max-requests-jitter "${GUNICORN_MAX_REQUESTS_JITTER}" \
            --worker-connections "${GUNICORN_WORKER_CONNECTIONS}" \
            --worker-class "${GUNICORN_WORKER_CLASS}" \
            --timeout "${GUNICORN_TIMEOUT}" \
            --graceful-timeout "${GUNICORN_GRACEFUL_TIMEOUT}" \
            --keep-alive "${GUNICORN_KEEPALIVE}" \
            --config "${GUNICORN_CONF}" \
            --certfile="${CERT}" --keyfile="${KEY}" \
            -b "0.0.0.0:8000" \
            "app"
fi
