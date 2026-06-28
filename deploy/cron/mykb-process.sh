#!/usr/bin/env bash
# Cron-Wrapper für 'mykb process'. Cron lädt keine .env und kein venv —
# das erledigt dieser Wrapper. Pfad ggf. anpassen (Annahme: Repo unter ~/mykb).
set -euo pipefail

REPO="${MYKB_HOME:-$HOME/mykb}"
cd "$REPO"

# .env laden (alle Variablen exportieren).
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

exec .venv/bin/python -m mykb process
