#!/bin/bash
# Benchmark: DNS + HTTP GET em cenários A/B/C, modos tcp/rudp e tamanhos 100k/500k/1m.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Carrega variáveis do .env (raiz do projeto), se existir
if [ -f "$ROOT/.env" ]; then
  set -a
  source "$ROOT/.env"
  set +a
fi

export MATRICULA NOME_ALUNO

if [ -z "${MATRICULA:-}" ] || [ -z "${NOME_ALUNO:-}" ]; then
  echo "Defina MATRICULA e NOME_ALUNO no arquivo .env ou exporte no ambiente." >&2
  exit 1
fi

PER_COMBO="${1:-10}"
MODES="${MODES:-tcp rudp}"
SCENARIOS="${SCENARIOS:-A B C}"
FILE_SIZES="${FILE_SIZES:-100k 500k 1m}"

bash scripts/generate_www_files.sh

mkdir -p results/inbox results/pcaps
rm -f results/metrics_app.csv

CLIENT_NAME="bench_client_runner"

cleanup() {
  docker rm -f "$CLIENT_NAME" >/dev/null 2>&1 || true
  docker compose down >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker rm -f "$CLIENT_NAME" >/dev/null 2>&1 || true
docker compose run -d --name "$CLIENT_NAME" client sleep infinity >/dev/null

run_id=0
for mode in $MODES; do
  TRANSFER_MODE="$mode" docker compose up -d --build --force-recreate dns web
  sleep 3

  docker exec "$CLIENT_NAME" bash -lc "apt-get update -qq && apt-get install -y -qq tcpdump" 2>/dev/null || true

  for size in $FILE_SIZES; do
    for scen in $SCENARIOS; do
      for _ in $(seq 1 "$PER_COMBO"); do
        run_id=$((run_id + 1))
        echo "=== size=$size cenário=$scen modo=$mode run_id=$run_id ==="

        docker compose exec -T web bash -lc '
          IFACE="${IFACE:-eth0}"
          tc qdisc del dev "$IFACE" root 2>/dev/null || true
          case "'"$scen"'" in
            A) tc qdisc add dev "$IFACE" root netem delay 10ms loss 0% ;;
            B) tc qdisc add dev "$IFACE" root netem delay 50ms loss 5% ;;
            C) tc qdisc add dev "$IFACE" root netem delay 100ms loss 10% ;;
            *)
              echo "SCENARIO inválido: '"$scen"' (use A, B ou C)" >&2
              exit 1
              ;;
          esac
        '
        sleep 0.2

        pcap_dir="results/pcaps/${mode}/${size}/${scen}"
        mkdir -p "$pcap_dir"
        docker exec "$CLIENT_NAME" bash -lc "mkdir -p /data/pcaps/${mode}/${size}/${scen}" 2>/dev/null || true

        TCPDUMP_PID=$(docker exec "$CLIENT_NAME" bash -lc \
          "tcpdump -i any -s 0 -w /data/pcaps/${mode}/${size}/${scen}/capture_${scen}_${mode}_${size}_${run_id}.pcap \
          '(udp port 53) or (port 8080)' >/dev/null 2>&1 & echo \$!")
        sleep 0.5

        docker exec \
          -e SCENARIO="$scen" \
          -e TRANSFER_MODE="$mode" \
          -e RUN_ID="$run_id" \
          -e FILE_SIZE="$size" \
          -e DNS_HOST="dns" \
          -e WEB_DOMAIN="www.web.local" \
          "$CLIENT_NAME" \
          /bin/bash /app/scripts/docker_client_run.sh || echo "run $run_id falhou"

        sleep 0.5
        docker exec "$CLIENT_NAME" bash -lc "kill ${TCPDUMP_PID} 2>/dev/null || true"
        docker exec "$CLIENT_NAME" bash -lc "pgrep tcpdump >/dev/null 2>&1 && pkill -9 tcpdump || true"
      done
    done
  done
done

if command -v python3 >/dev/null 2>&1; then
  if command -v tshark >/dev/null 2>&1; then
    python3 scripts/pcap_to_csv.py || echo "pcap->csv falhou"
  fi
fi

echo "Métricas: results/metrics_app.csv"
echo "Capturas: results/pcaps/"