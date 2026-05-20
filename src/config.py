"""Credenciais de identificação (Matrícula + Nome) para o hash de autenticação."""
import os
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")


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