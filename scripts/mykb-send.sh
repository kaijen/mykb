#!/usr/bin/env bash
# Dokumente/Links von unterwegs an den mykb-Capture-Dienst übergeben.
#
# Voraussetzung: MYKB_CAPTURE_URL zeigt auf den über Tailscale veröffentlichten
# Dienst, z. B.:
#   export MYKB_CAPTURE_URL=https://laptop.<tailnet>.ts.net
#
# Verwendung:
#   mykb-send url  <URL> [tag1,tag2] [notiz]
#   mykb-send file <pfad> [document|note] [collection]
set -euo pipefail

: "${MYKB_CAPTURE_URL:?setze MYKB_CAPTURE_URL=https://laptop.<tailnet>.ts.net}"
base="${MYKB_CAPTURE_URL%/}"
cmd="${1:-}"

case "$cmd" in
  url)
    url="${2:?URL fehlt}"
    tags_csv="${3:-}"
    note="${4:-}"
    tags_json="[]"
    if [ -n "$tags_csv" ]; then
      tags_json=$(printf '%s' "$tags_csv" | awk -F, '{printf "["; for(i=1;i<=NF;i++){printf "%s\"%s\"", (i>1?",":""), $i} printf "]"}')
    fi
    curl -fsS -X POST "$base/capture/url" \
      -H "Content-Type: application/json" \
      -d "{\"url\":\"$url\",\"tags\":$tags_json,\"note\":\"$note\"}"
    echo
    ;;
  file)
    path="${2:?Pfad fehlt}"
    kind="${3:-document}"
    collection="${4:-}"
    curl -fsS -X POST "$base/capture/file" \
      -F "kind=$kind" -F "collection=$collection" -F "file=@$path"
    echo
    ;;
  *)
    echo "Verwendung: mykb-send url <URL> [tags] [notiz] | mykb-send file <pfad> [document|note] [collection]" >&2
    exit 2
    ;;
esac
