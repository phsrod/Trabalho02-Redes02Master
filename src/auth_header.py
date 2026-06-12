"""Campo X-Custom-Auth: SHA-256(Matrícula + Nome) em hexadecimal (visível nos pacotes do Wireshark)."""
import hashlib

AUTH_PREFIX = b"X-Custom-Auth: "


def auth_token_hex(matricula: str, nome: str) -> bytes:
    raw = (matricula + nome).encode("utf-8")
    return hashlib.sha256(raw).hexdigest().encode("ascii")


def build_auth_line(matricula: str, nome: str) -> bytes:
    return AUTH_PREFIX + auth_token_hex(matricula, nome) + b"\r\n"


def verify_auth_line(line: bytes, matricula: str, nome: str) -> bool:
    expected = build_auth_line(matricula, nome)
    return line.rstrip(b"\r\n") == expected.rstrip(b"\r\n")