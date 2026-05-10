#!/bin/bash
set -euo pipefail
 
MODES=("tcp" "rudp")
SCENARIOS=("A" "B" "C")
RUNS=3
 
for mode in "${MODES[@]}"; do
  for scenario in "${SCENARIOS[@]}"; do
    for run_id in $(seq 1 $RUNS); do
      echo "=== $mode / $scenario / run $run_id ==="
      bash /app/scripts/docker_client_run.sh "$mode" "$scenario" "$run_id"
      sleep 1
    done
  done
done