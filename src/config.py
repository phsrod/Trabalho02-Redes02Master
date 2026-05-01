"""Load student credentials from environment variables."""
 
import os
 
 
def get_matricula() -> str:
    return os.environ.get("MATRICULA", "").strip()
 
 
def get_nome() -> str:
    return os.environ.get("NOME_ALUNO", "").strip()