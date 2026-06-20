#!/bin/bash
set -euo pipefail

SCEN_U=$(echo "${SCENARIO:-A}" | tr "[:lower:]" "[:upper:]")

TRANSFER_MODE="${TRANSFER_MODE:-tcp}"
RUN_ID="${RUN_ID:-0}"
DNS_HOST="${DNS_HOST:-dns}"
WEB_DOMAIN="${WEB_DOMAIN:-www.web.local}"
FILE_SIZE="${FILE_SIZE:-1m}"

case "$FILE_SIZE" in
  100k|100K) HTTP_PATH="/files/test_100k.bin" ;;
  500k|500K) HTTP_PATH="/files/test_500k.bin" ;;
  1m|1M) HTTP_PATH="/files/test_1m.bin" ;;
  *)
    echo "FILE_SIZE inválido: ${FILE_SIZE} (use 100k, 500k ou 1m)" >&2
    exit 1
    ;;
esac

python3 -m src.web_client \
  --mode "$TRANSFER_MODE" \
  --domain "$WEB_DOMAIN" \
  --path "$HTTP_PATH" \
  --dns-host "$DNS_HOST" \
  --dns-port 53 \
  --http-port 8080 \
  --file-size "$FILE_SIZE" \
  --out "/data/download_${FILE_SIZE}.bin" \
  --csv /data/metrics_app.csv \
  --run-id "$RUN_ID" \
  --scenario "$SCEN_U"
