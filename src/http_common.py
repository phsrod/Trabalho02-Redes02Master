"""Utilitários HTTP/1.1 simplificado com X-Custom-Auth."""
from __future__ import annotations

import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path

from .auth_header import auth_token_hex

HTTP_VERSION = "HTTP/1.1"
CRLF = "\r\n"


@dataclass
class HttpRequest:
    method: str
    path: str
    host: str
    headers: dict[str, str]


@dataclass
class HttpResponse:
    status_code: int
    reason: str
    headers: dict[str, str]
    body: bytes


def guess_content_type(path: str) -> str:
    ctype, _ = mimetypes.guess_type(path)
    return ctype or "application/octet-stream"


def build_auth_header_value(matricula: str, nome: str) -> str:
    return auth_token_hex(matricula, nome).decode("ascii")


def verify_auth_header(value: str, matricula: str, nome: str) -> bool:
    expected = build_auth_header_value(matricula, nome)
    return value.strip() == expected


def build_get_request(
    path: str,
    host: str,
    matricula: str,
    nome: str,
    extra_headers: dict[str, str] | None = None,
) -> bytes:
    if not path.startswith("/"):
        path = "/" + path
    lines = [
        f"GET {path} {HTTP_VERSION}",
        f"Host: {host}",
        f"X-Custom-Auth: {build_auth_header_value(matricula, nome)}",
        "Connection: close",
    ]
    if extra_headers:
        for key, value in extra_headers.items():
            lines.append(f"{key}: {value}")
    lines.append("")
    lines.append("")
    return CRLF.join(lines).encode("utf-8")


def build_response(
    status_code: int,
    reason: str,
    body: bytes,
    matricula: str,
    nome: str,
    content_type: str,
) -> bytes:
    headers = [
        f"{HTTP_VERSION} {status_code} {reason}",
        f"Content-Type: {content_type}",
        f"Content-Length: {len(body)}",
        f"X-Custom-Auth: {build_auth_header_value(matricula, nome)}",
        "Connection: close",
        "",
        "",
    ]
    return CRLF.join(headers).encode("utf-8") + body


def parse_request(raw: bytes, matricula: str, nome: str) -> HttpRequest:
    header_end = raw.find(b"\r\n\r\n")
    if header_end < 0:
        raise ValueError("cabeçalhos HTTP incompletos")
    header_text = raw[:header_end].decode("utf-8", errors="replace")
    lines = header_text.split("\r\n")
    if not lines:
        raise ValueError("requisição HTTP vazia")
    parts = lines[0].split()
    if len(parts) < 3:
        raise ValueError("linha de requisição inválida")
    method, path = parts[0].upper(), parts[1]
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        headers[key.strip().lower()] = value.strip()
    auth = headers.get("x-custom-auth", "")
    if not verify_auth_header(auth, matricula, nome):
        raise PermissionError("X-Custom-Auth inválido")
    host = headers.get("host", "")
    return HttpRequest(method=method, path=path, host=host, headers=headers)


def parse_response(raw: bytes, matricula: str, nome: str) -> HttpResponse:
    header_end = raw.find(b"\r\n\r\n")
    if header_end < 0:
        raise ValueError("cabeçalhos HTTP incompletos")
    header_text = raw[:header_end].decode("utf-8", errors="replace")
    body = raw[header_end + 4 :]
    lines = header_text.split("\r\n")
    if not lines:
        raise ValueError("resposta HTTP vazia")
    status_parts = lines[0].split(None, 2)
    if len(status_parts) < 2:
        raise ValueError("linha de status inválida")
    status_code = int(status_parts[1])
    reason = status_parts[2] if len(status_parts) > 2 else ""
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        headers[key.strip().lower()] = value.strip()
    auth = headers.get("x-custom-auth", "")
    if not verify_auth_header(auth, matricula, nome):
        raise PermissionError("X-Custom-Auth inválido na resposta")
    content_length = int(headers.get("content-length", str(len(body))))
    if len(body) > content_length:
        body = body[:content_length]
    elif len(body) < content_length:
        raise ValueError("corpo HTTP incompleto")
    return HttpResponse(status_code=status_code, reason=reason, headers=headers, body=body)


def resolve_www_path(www_root: str, url_path: str) -> Path | None:
    clean = url_path.split("?", 1)[0]
    if clean in ("", "/"):
        clean = "/index.html"
    rel = clean.lstrip("/")
    root = Path(www_root).resolve()
    candidate = (root / rel).resolve()
    if not str(candidate).startswith(str(root)):
        return None
    if candidate.is_file():
        return candidate
    return None


def read_file_bytes(path: Path) -> bytes:
    return path.read_bytes()


def file_size(path: str) -> int:
    return os.path.getsize(path)