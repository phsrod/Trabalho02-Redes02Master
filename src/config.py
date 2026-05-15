"""Credenciais de identificação e constantes compartilhadas entre módulos."""
import os
from pathlib import Path
 
from dotenv import load_dotenv
 
_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")
 
# ---------- constantes de transferência ----------
TCP_CHUNK_SIZE = 32 * 1024        # 32 KB por bloco TCP
RUDP_PAYLOAD_MAX = 1200           # limite UDP para evitar fragmentação IP
RUDP_CHUNK_SIZE = RUDP_PAYLOAD_MAX - 200  # margem para auth + cabeçalho
RUDP_TIMEOUT_DEFAULT = 2.0        # timeout padrão para Stop-and-Wait
RUDP_MAX_RETRIES = 1000           # retransmissões antes de falhar
SOCKET_BUFFER = 65536             # tamanho do buffer de socket
 
 
def get_matricula() -> str:
    return os.environ.get("MATRICULA", "").strip()
 
 
def get_nome() -> str:
    return os.environ.get("NOME_ALUNO", "").strip()
 
 
def require_identity() -> tuple[str, str]:
    m, n = get_matricula(), get_nome()
    if not m or not n:
        raise SystemExit(
            "Defina MATRICULA e NOME_ALUNO (variáveis de ambiente ou arquivo .env na raiz do projeto)."
        )
    return m, n