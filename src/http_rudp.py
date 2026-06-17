"""HTTP/1.1 sobre a camada R-UDP (Stop-and-Wait + X-Custom-Auth)."""
from __future__ import annotations

import json
import logging
import select
import socket
import time
from typing import Callable

from .framing import MsgType, pack_frame, parse_frame_verify
from .http_common import (
    build_get_request,
    build_response,
    guess_content_type,
    parse_request,
    parse_response,
    resolve_www_path,
    read_file_bytes,
)

CHUNK_SIZE = 1000


def _recv_until_ack_rudp(
    sock: socket.socket,
    matricula: str,
    nome: str,
    expect_seq: int,
    timeout_sec: float,
) -> None:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        ready, _, _ = select.select([sock], [], [], max(0.0, deadline - time.monotonic()))
        if not ready:
            continue
        data, _addr = sock.recvfrom(65535)
        try:
            seq, typ, _payload = parse_frame_verify(data, matricula, nome)
        except ValueError:
            continue
        if typ == MsgType.ACK and seq == expect_seq:
            return
    raise TimeoutError(f"ACK {expect_seq} não recebido")


def _send_sw(
    sock: socket.socket,
    addr: tuple[str, int],
    matricula: str,
    nome: str,
    seq: int,
    typ: MsgType,
    payload: bytes,
    timeout_sec: float,
    max_retries: int,
) -> None:
    packet = pack_frame(matricula, nome, seq, typ, payload)
    for attempt in range(max_retries):
        sock.sendto(packet, addr)
        try:
            _recv_until_ack_rudp(sock, matricula, nome, seq, timeout_sec)
            return
        except TimeoutError:
            if attempt == max_retries - 1:
                raise
            logging.getLogger("transfers").info(
                json.dumps({"mode": "rudp", "event": "retransmit", "seq": seq, "attempt": attempt + 1})
            )


def _recv_sw(
    sock: socket.socket,
    matricula: str,
    nome: str,
    expect_seq: int,
) -> tuple[int, MsgType, bytes, tuple[str, int]]:
    while True:
        data, addr = sock.recvfrom(65535)
        try:
            seq, typ, payload = parse_frame_verify(data, matricula, nome)
        except ValueError:
            continue
        if seq == expect_seq - 1 and typ != MsgType.ACK:
            sock.sendto(pack_frame(matricula, nome, seq, MsgType.ACK, b""), addr)
            continue
        if seq == expect_seq:
            return seq, typ, payload, addr


def http_rudp_get(
    host: str,
    port: int,
    path: str,
    domain: str,
    matricula: str,
    nome: str,
    timeout_sec: float = 0.5,
    max_retries: int = 1000,
) -> tuple[float, int, bytes, int]:
    """GET HTTP via R-UDP. Retorna (duracao_s, bytes_recebidos, corpo, status_code)."""
    request = build_get_request(path, domain, matricula, nome)
    t0 = time.monotonic()
    bytes_recv = 0

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setblocking(True)
        sock.settimeout(timeout_sec * max_retries)

        # Envia requisição HTTP no quadro META (seq=0)
        _send_sw(sock, (host, port), matricula, nome, 0, MsgType.META, request, timeout_sec, max_retries)

        # Recebe cabeçalhos HTTP no META (seq=1)
        _seq, _typ, header_payload, server_addr = _recv_sw(sock, matricula, nome, 1)
        bytes_recv += len(header_payload)
        sock.sendto(pack_frame(matricula, nome, 1, MsgType.ACK, b""), server_addr)

        body_parts: list[bytes] = [header_payload]
        next_seq = 2
        while True:
            seq, typ, payload, server_addr = _recv_sw(sock, matricula, nome, next_seq)
            bytes_recv += len(payload)
            sock.sendto(pack_frame(matricula, nome, seq, MsgType.ACK, b""), server_addr)
            if typ == MsgType.DATA:
                body_parts.append(payload)
                next_seq += 1
                continue
            if typ == MsgType.FIN:
                break
            raise RuntimeError(f"tipo inesperado na resposta HTTP/R-UDP: {typ}")

    raw = b"".join(body_parts)
    elapsed = time.monotonic() - t0
    response = parse_response(raw, matricula, nome)
    return elapsed, bytes_recv, response.body, response.status_code


def _serve_one_rudp(
    sock: socket.socket,
    matricula: str,
    nome: str,
    www_root: str,
    timeout_sec: float,
    max_retries: int,
) -> tuple[int, int]:
    seq, typ, payload, client_addr = _recv_sw(sock, matricula, nome, 0)
    if typ != MsgType.META:
        raise RuntimeError("esperado META com requisição HTTP")
    sock.sendto(pack_frame(matricula, nome, 0, MsgType.ACK, b""), client_addr)

    try:
        req = parse_request(payload, matricula, nome)
    except PermissionError:
        response = build_response(403, "Forbidden", b"auth invalid\n", matricula, nome, "text/plain")
        status = 403
    except ValueError:
        response = build_response(400, "Bad Request", b"bad request\n", matricula, nome, "text/plain")
        status = 400
    else:
        if req.method != "GET":
            response = build_response(405, "Method Not Allowed", b"only GET\n", matricula, nome, "text/plain")
            status = 405
        else:
            target = resolve_www_path(www_root, req.path)
            if target is None:
                response = build_response(404, "Not Found", b"404 Not Found\n", matricula, nome, "text/html")
                status = 404
            else:
                body = read_file_bytes(target)
                ctype = guess_content_type(str(target))
                response = build_response(200, "OK", body, matricula, nome, ctype)
                status = 200

    header_end = response.find(b"\r\n\r\n")
    if header_end < 0:
        raise RuntimeError("resposta HTTP malformada")
    headers = response[: header_end + 4]
    body = response[header_end + 4 :]

    bytes_sent = 0
    _send_sw(sock, client_addr, matricula, nome, 1, MsgType.META, headers, timeout_sec, max_retries)
    bytes_sent += len(headers)

    seq = 2
    offset = 0
    while offset < len(body):
        chunk = body[offset : offset + CHUNK_SIZE]
        _send_sw(sock, client_addr, matricula, nome, seq, MsgType.DATA, chunk, timeout_sec, max_retries)
        bytes_sent += len(chunk)
        offset += len(chunk)
        seq += 1

    _send_sw(sock, client_addr, matricula, nome, seq, MsgType.FIN, b"", timeout_sec, max_retries)
    return bytes_sent, status


def http_rudp_run_server(
    host: str,
    port: int,
    www_root: str,
    matricula: str,
    nome: str,
    timeout_sec: float = 0.5,
    max_retries: int = 1000,
    on_request: Callable[[int, int], None] | None = None,
) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind((host, port))
        while True:
            nbytes, status = _serve_one_rudp(sock, matricula, nome, www_root, timeout_sec, max_retries)
            if on_request:
                on_request(nbytes, status)