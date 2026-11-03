#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -d .venv ]; then python3 -m venv .venv; fi
.venv/bin/python -m pip install -r requirements.txt
if [ ! -f .env ]; then
  .venv/bin/python - <<'PY'
from pathlib import Path
import secrets
p=Path('.env');p.write_text(Path('.env.example').read_text().replace('replace-with-a-long-random-local-password',secrets.token_urlsafe(36)));p.chmod(0o600)
PY
fi
.venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 --workers 1
