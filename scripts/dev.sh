#!/usr/bin/env bash
# Lokaler Dev-Server (ein Prozess, FastAPI serviert das Frontend mit).
# Port 8040 (8000/8010/8020/8030 sind von den anderen Tools belegt).
set -e
cd "$(dirname "$0")/../backend"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi
export HUPSI_PASSWORD="${HUPSI_PASSWORD:-test}"
export KLAVIYO_API_KEY="${KLAVIYO_API_KEY:-}"
export COOKIE_SECURE=0
exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8040 --reload
