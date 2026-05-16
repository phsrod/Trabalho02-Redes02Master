#!/bin/bash
# Executa rodadas (ex.: 10-20 por combinação cenário×modo). Requer Docker Compose v2.
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
  echo "Limpando containers..."
  docker rm -f "$CLIENT_NAME" >/dev/null 2>&1 || true
  docker compose down >/dev/null 2>&1 || true
  # Mata qualquer tcpdump residual dentro dos containers
  docker ps -q --filter "name=bench" 2>/dev/null | while read cid; do
    docker exec "$cid" bash -c "pkill -9 tcpdump 2>/dev/null; pkill -9 tshark 2>/dev/null" || true
  done
  echo "Limpeza concluída."
}
trap cleanup EXIT
 
# Pré-sobe o container cliente em background (vai ser reutilizado)
docker rm -f "$CLIENT_NAME" >/dev/null 2>&1 || true
docker compose run -d --name "$CLIENT_NAME" client sleep infinity >/dev/null
echo "Container cliente '$CLIENT_NAME' pronto."
 
run_id=0
for mode in $MODES; do
  echo "=========================================="
  echo "Iniciando benchmark para MODO=$mode"
  echo "=========================================="
 
  TRANSFER_MODE="$mode" docker compose up -d --build --force-recreate server
  sleep 3
 
  # Instala tcpdump no servidor uma única vez
  echo "Instalando tcpdump no servidor..."
  docker compose exec server bash -lc "apt-get update -qq && apt-get install -y -qq tcpdump" 2>/dev/null || true
 
  for scen in $SCENARIOS; do
    echo "--- Cenário $scen / Modo $mode ---"
    for i in $(seq 1 "$PER_COMBO"); do
      run_id=$((run_id + 1))
      echo "  Rodada $run_id (i=$i)"
 
      # Cria diretório do pcap no volume compartilhado
      docker compose exec -T server bash -lc "mkdir -p /data/pcaps/${mode}/${scen}" 2>/dev/null || true
 
      # Inicia tcpdump em background e captura PID
      docker compose exec -T server bash -lc "
        pkill -9 tcpdump 2>/dev/null || true
        tcpdump -i any -s 0 -w /data/pcaps/${mode}/${scen}/capture_${scen}_${mode}_${run_id}.pcap port 9000 >/dev/null 2>&1 &
        echo \$!" > /tmp/tcpdump_pid_${run_id}.txt
      sleep 0.5
 
      # Executa o cliente
      docker exec \
        -e SCENARIO="$scen" \
        -e TRANSFER_MODE="$mode" \
        -e RUN_ID="$run_id" \
        -e HOST_SERVER="server" \
        "$CLIENT_NAME" \
        /bin/bash /app/scripts/docker_client_run.sh
 
      # Para o tcpdump
      sleep 0.5
      docker compose exec -T server bash -lc "pkill -9 tcpdump 2>/dev/null || true"
      echo "  Pcap salvo: results/pcaps/${mode}/${scen}/capture_${scen}_${mode}_${run_id}.pcap"
    done
  done
 
  docker compose down >/dev/null 2>&1 || true
  echo "Servidor modo=$mode finalizado."
done
 
# Gera resumo CSV a partir dos pcaps (opcional)
if command -v python3 >/dev/null 2>&1 && command -v tshark >/dev/null 2>&1; then
  echo "Gerando results/pcap_summary.csv a partir de results/pcaps/..."
  python3 scripts/pcap_to_csv.py || echo "pcap->csv falhou (ignorando)"
else
  echo "tshark ou python3 não encontrados; pulando geração de pcap_summary.csv"
fi
 
echo ""
echo "=== Benchmark concluído ==="
echo "Métricas: results/metrics_app.csv"
echo "Capturas: results/pcaps/"
echo "Total de rodadas: $run_id"