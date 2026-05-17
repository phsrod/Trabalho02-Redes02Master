#!/bin/bash
set -euo pipefail
 
IFACE="${IFACE:-eth0}"
SCEN_U=$(echo "${SCENARIO:-A}" | tr "[:lower:]" "[:upper:]")
 
# Aplica regras de simulação de rede com tc
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
 
echo "tc aplicado: delay $(tc qdisc show dev "$IFACE" | grep -oP 'delay \S+' || echo '?')"
sleep 2
 
HOST_SERVER="${HOST_SERVER:-server}"
TRANSFER_MODE="${TRANSFER_MODE:-tcp}"
RUN_ID="${RUN_ID:-0}"
PAYLOAD="/data/payload.bin"
 
# Gera payload se não existir ou estiver vazio
if [ ! -s "$PAYLOAD" ]; then
  echo "Gerando payload de 1MB em $PAYLOAD..."
  dd if=/dev/urandom of="$PAYLOAD" bs=1M count=1 status=none 2>/dev/null || {
    echo "Falha ao gerar payload; tentando método alternativo..."
    python3 -c "
import os
with open('$PAYLOAD', 'wb') as f:
    f.write(os.urandom(1024 * 1024))
"
  }
fi
 
# Verifica integridade do payload
if [ ! -f "$PAYLOAD" ]; then
  echo "ERRO: payload não foi criado" >&2
  exit 1
fi
PAYLOAD_SIZE=$(stat -c%s "$PAYLOAD" 2>/dev/null || python3 -c "import os; print(os.path.getsize('$PAYLOAD'))")
echo "Payload: $PAYLOAD ($PAYLOAD_SIZE bytes)"
 
# Verifica conectividade com o servidor
if ! timeout 3 python3 -c "import socket; s=socket.socket(); s.settimeout(2); s.connect(('$HOST_SERVER', 9000)); s.close()" 2>/dev/null; then
  if [ "$TRANSFER_MODE" = "tcp" ]; then
    echo "AVISO: servidor TCP não respondeu ao teste de conexão (continuando...)"
  fi
fi
 
python3 -m src.client \
  --mode "$TRANSFER_MODE" \
  --host "$HOST_SERVER" \
  --port 9000 \
  --file "$PAYLOAD" \
  --csv /data/metrics_app.csv \
  --run-id "$RUN_ID" \
  --scenario "$SCEN_U"