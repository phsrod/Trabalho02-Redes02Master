#!/bin/bash
set -euo pipefail

IFACE="${IFACE:-eth0}"
SCEN_U=$(echo "${SCENARIO:-A}" | tr "[:lower:]" "[:upper:]")

tc qdisc del dev "$IFACE" root 2>/dev/null || true
case "$SCEN_U" in
  A) tc qdisc add dev "$IFACE" root netem delay 10ms loss 0% ;;
  B) tc qdisc add dev "$IFACE" root netem delay 50ms loss 5% ;;
  C) tc qdisc add dev "$IFACE" root netem delay 100ms loss 10% ;;
  *)
    echo "SCENARIO inválido: ${SCENARIO} (use A, B ou C)" >&2
    exit 1
    ;;
esac

sleep 2

HOST_SERVER="${HOST_SERVER:-server}"
TRANSFER_MODE="${TRANSFER_MODE:-tcp}"
RUN_ID="${RUN_ID:-0}"

dd if=/dev/urandom of=/data/payload.bin bs=1M count=1 status=none 2>/dev/null || dd if=/dev/urandom of=/data/payload.bin bs=1M count=1

python3 -m src.client \
  --mode "$TRANSFER_MODE" \
  --host "$HOST_SERVER" \
  --port 9000 \
  --file /data/payload.bin \
  --csv /data/metrics_app.csv \
  --run-id "$RUN_ID" \
  --scenario "$SCEN_U"
