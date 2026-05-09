#!/bin/bash
set -euo pipefail
 
MODE=${1:-tcp}
SCENARIO=${2:-A}
RUN_ID=${3:-1}
HOST=${4:-server}
PORT=${5:-9000}
 
# tc rules based on scenario
case $SCENARIO in
  A) tc qdisc add dev eth0 root netem delay 10ms loss 0% ;;
  B) tc qdisc add dev eth0 root netem delay 50ms loss 5% ;;
  C) tc qdisc add dev eth0 root netem delay 100ms loss 10% ;;
  *)
    echo "Unknown scenario: $SCENARIO (use A, B, or C)"
    exit 1
    ;;
esac
 
# start tcpdump in background
mkdir -p /data/pcaps
tcpdump -i eth0 -w "/data/pcaps/${SCENARIO}_${MODE}_run${RUN_ID}.pcap" &
TCPDUMP_PID=$!
sleep 1
 
# run client
python3 -m src.client \
    --mode "$MODE" \
    --host "$HOST" \
    --port "$PORT" \
    --file /data/payload.bin \
    --csv /data/metrics_app.csv \
    --run-id "$RUN_ID" \
    --scenario "$SCENARIO"
 
# stop tcpdump
kill $TCPDUMP_PID 2>/dev/null || true
wait $TCPDUMP_PID 2>/dev/null || true