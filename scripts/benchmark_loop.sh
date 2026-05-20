#!/bin/bash
# Executa rodadas (ex.: 10–20 por combinação cenário×modo). Requer Docker Compose v2.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export MATRICULA NOME_ALUNO

if [ -z "${MATRICULA:-}" ] || [ -z "${NOME_ALUNO:-}" ]; then
  echo "Defina MATRICULA e NOME_ALUNO no ambiente." >&2
  exit 1
fi

PER_COMBO="${1:-15}"
MODES="${MODES:-tcp rudp}"
SCENARIOS="${SCENARIOS:-A B C}"

mkdir -p results/inbox
mkdir -p results/pcaps
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
  TRANSFER_MODE="$mode" docker compose up -d --build --force-recreate server
  sleep 2
  
  # Instale tcpdump uma única vez por modo
  docker compose exec server bash -lc "apt-get update -qq && apt-get install -y -qq tcpdump" 2>/dev/null || true
  
  for scen in $SCENARIOS; do
    for _ in $(seq 1 "$PER_COMBO"); do
      run_id=$((run_id + 1))
      echo "=== cenário=$scen modo=$mode run_id=$run_id ==="
      
      # Inicia tcpdump dentro do container e captura o PID do processo dentro do container
          mkdir -p results/pcaps/${mode}/${scen}
          docker compose exec -T server bash -lc "mkdir -p /data/pcaps/${mode}/${scen}" 2>/dev/null || true
          TCPDUMP_PID=$(docker compose exec -T server bash -lc "tcpdump -i any -s 0 -w /data/pcaps/${mode}/${scen}/capture_${scen}_${mode}_${run_id}.pcap port 9000 >/dev/null 2>&1 & echo \$!")
      echo "tcpdump pid no container: ${TCPDUMP_PID}"
      sleep 0.5

      # Execute cliente
      docker exec \
        -e SCENARIO="$scen" \
        -e TRANSFER_MODE="$mode" \
        -e RUN_ID="$run_id" \
        -e HOST_SERVER="server" \
        "$CLIENT_NAME" \
        /bin/bash /app/scripts/docker_client_run.sh

      # Pare o tcpdump dentro do container pelo PID retornado e garanta limpeza
      sleep 0.5
      docker compose exec -T server bash -lc "kill ${TCPDUMP_PID} 2>/dev/null || true"
      # Se sobrar algum tcpdump, mate todos (força) para evitar interferência nas próximas rodadas
      docker compose exec -T server bash -lc "pgrep tcpdump >/dev/null 2>&1 && pkill -9 tcpdump || true"
    done
  done
done
 
# Gera resumo CSV a partir dos pcaps, se python3 e tshark estiverem disponíveis
if command -v python3 >/dev/null 2>&1; then
  if command -v tshark >/dev/null 2>&1; then
    echo "Gerando results/pcap_summary.csv a partir de results/pcaps/..."
    python3 scripts/pcap_to_csv.py || echo "pcap->csv falhou"
  else
    echo "tshark não encontrado; pulando geração de results/pcap_summary.csv"
  fi
else
  echo "python3 não encontrado; pulando geração de results/pcap_summary.csv"
fi

echo "Métricas: results/metrics_app.csv"
echo "Capturas: results/pcaps/"
