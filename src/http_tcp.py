"""Miniservidor HTTP/1.1 sobre TCP nativo."""
from __future__ import annotations

import socket
import time
from typing import Callable

from .http_common import (
    build_get_request,
    build_response,
    guess_content_type,
    parse_request,
    parse_response,
    resolve_www_path,
    read_file_bytes,
)


def _recv_http_message(conn: socket.socket) -> bytes:
    chunks: list[bytes] = []
    while True:
        block = conn.recv(65536)
        if not block:
            break
        chunks.append(block)
        data = b"".join(chunks)
        if b"\r\n\r\n" in data:
            header_end = data.index(b"\r\n\r\n") + 4
            headers = data[: header_end - 4].decode("utf-8", errors="replace")
            content_length = 0
            for line in headers.split("\r\n"):
                if line.lower().startswith("content-length:"):
                    content_length = int(line.split(":", 1)[1].strip())
                    break
            if len(data) >= header_end + content_length:
                return data[: header_end + content_length]
    return b"".join(chunks)


def http_tcp_get(
    host: str,
    port: int,
    path: str,
    domain: str,
    matricula: str,
    nome: str,
) -> tuple[float, int, bytes, int]:
    """GET HTTP via TCP. Retorna (duracao_s, bytes_recebidos, corpo, status_code)."""
    request = build_get_request(path, domain, matricula, nome)
    t0 = time.monotonic()
    with socket.create_connection((host, port), timeout=30) as conn:
        conn.settimeout(120.0)
        conn.sendall(request)
        raw = _recv_http_message(conn)
    elapsed = time.monotonic() - t0
    response = parse_response(raw, matricula, nome)
    return elapsed, len(raw), response.body, response.status_code


def _handle_connection(
    conn: socket.socket,
    matricula: str,
    nome: str,
    www_root: str,
) -> tuple[int, int]:
    raw = _recv_http_message(conn)
    if not raw:
        return 0, 0
    try:
        req = parse_request(raw, matricula, nome)
    except PermissionError:
        payload = build_response(403, "Forbidden", b"auth invalid\n", matricula, nome, "text/plain")
        conn.sendall(payload)
        return len(payload), 403
    except ValueError as exc:
        payload = build_response(400, "Bad Request", str(exc).encode(), matricula, nome, "text/plain")
        conn.sendall(payload)
        return len(payload), 400

    if req.method != "GET":
        payload = build_response(405, "Method Not Allowed", b"only GET\n", matricula, nome, "text/plain")
        conn.sendall(payload)
        return len(payload), 405

    target = resolve_www_path(www_root, req.path)
    if target is None:
        payload = build_response(404, "Not Found", b"404 Not Found\n", matricula, nome, "text/html")
        conn.sendall(payload)
        return len(payload), 404

    body = read_file_bytes(target)
    ctype = guess_content_type(str(target))
    payload = build_response(200, "OK", body, matricula, nome, ctype)
    conn.sendall(payload)
    return len(payload), 200


def http_tcp_run_server(
    host: str,
    port: int,
    www_root: str,
    matricula: str,
    nome: str,
    on_request: Callable[[int, int], None] | None = None,
) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, port))
        sock.listen(16)
        while True:
            conn, _addr = sock.accept()
            with conn:
                nbytes, status = _handle_connection(conn, matricula, nome, www_root)
                if on_request:
                    on_request(nbytes, status)