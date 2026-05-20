"""Transferência em modo TCP com quadros de aplicação (Stop-and-Wait na camada app)."""
from __future__ import annotations

import json
import os
import socket
import time
import logging
from typing import Callable

from .framing import MsgType, TcpStreamDecoder, pack_frame


CHUNK_SIZE = 32 * 1024


def _recv_until_ack(
    conn: socket.socket,
    dec: TcpStreamDecoder,
    matricula: str,
    nome: str,
    expect_seq: int,
) -> None:
    while True:
        raw = conn.recv(65536)
        if not raw:
            raise ConnectionError("conexão encerrada antes do ACK")
        for seq, typ, _payload in dec.feed(raw):
            if typ == MsgType.ACK and seq == expect_seq:
                return


def tcp_send_file(
    host: str,
    port: int,
    filepath: str,
    matricula: str,
    nome: str,
    progress: Callable[[str], None] | None = None,
) -> tuple[float, int]:
    """Envia arquivo; retorna (segundos, bytes totais enviados ao socket)."""
    size = os.path.getsize(filepath)
    basename = os.path.basename(filepath)
    t0 = time.monotonic()
    dec = TcpStreamDecoder(matricula, nome)
    bytes_sent = 0
    logger = logging.getLogger("transfers")
    logger.info(json.dumps({"ts": time.time(), "mode": "tcp", "role": "client", "event": "start", "peer": f"{host}:{port}"}))
    with socket.create_connection((host, port), timeout=30) as conn:
        conn.settimeout(300.0)

        # META seq 0
        meta = json.dumps({"name": basename, "size": size}, separators=(",", ":")).encode()
        frame = pack_frame(matricula, nome, 0, MsgType.META, meta)
        conn.sendall(frame)
        bytes_sent += len(frame)
        _recv_until_ack(conn, dec, matricula, nome, 0)
        logger.info(json.dumps({"ts": time.time(), "mode": "tcp", "role": "client", "event": "ack_received", "seq": 0}))
        if progress:
            progress("meta ok")

        sent_payload = 0
        seq = 1
        with open(filepath, "rb") as f:
            while True:
                block = f.read(CHUNK_SIZE)
                if not block:
                    break
                frame = pack_frame(matricula, nome, seq, MsgType.DATA, block)
                conn.sendall(frame)
                bytes_sent += len(frame)
                _recv_until_ack(conn, dec, matricula, nome, seq)
                logger.info(json.dumps({"ts": time.time(), "mode": "tcp", "role": "client", "event": "ack_received", "seq": seq}))
                sent_payload += len(block)
                seq += 1
                if progress:
                    progress(f"dados {sent_payload}/{size}")

        frame = pack_frame(matricula, nome, seq, MsgType.FIN, b"")
        conn.sendall(frame)
        bytes_sent += len(frame)
        _recv_until_ack(conn, dec, matricula, nome, seq)
        logger.info(json.dumps({"ts": time.time(), "mode": "tcp", "role": "client", "event": "ack_received", "seq": seq}))

    elapsed = time.monotonic() - t0
    logger.info(json.dumps({"ts": time.time(), "mode": "tcp", "role": "client", "event": "end", "bytes_app": bytes_sent, "duration_s": elapsed}))
    return elapsed, bytes_sent


def tcp_receive_loop(
    conn: socket.socket,
    matricula: str,
    nome: str,
    out_dir: str,
    progress: Callable[[str], None] | None = None,
) -> tuple[int, str]:
    """Recebe um arquivo por conexão TCP; retorna (bytes escritos, caminho salvo)."""
    dec = TcpStreamDecoder(matricula, nome)
    out_file = None
    path_saved = ""
    bytes_written = 0
    next_data_seq = 1
    meta_ok = False

    def handle(seq: int, typ: MsgType, payload: bytes) -> bool:
        nonlocal out_file, path_saved, bytes_written, next_data_seq, meta_ok
        logger = logging.getLogger("transfers")
        if typ == MsgType.META:
            meta = json.loads(payload.decode("utf-8"))
            safe = os.path.basename(meta["name"])
            path_saved = os.path.join(out_dir, safe)
            out_file = open(path_saved, "wb")
            meta_ok = True
            next_data_seq = 1
            conn.sendall(pack_frame(matricula, nome, seq, MsgType.ACK, b""))
            logger.info(json.dumps({"ts": time.time(), "mode": "tcp", "role": "server", "event": "recv", "seq": seq, "type": "META"}))
            logger.info(json.dumps({"ts": time.time(), "mode": "tcp", "role": "server", "event": "ack_sent", "seq": seq}))
            return False
        if typ == MsgType.DATA:
            if not meta_ok or out_file is None:
                raise RuntimeError("DATA antes de META")
            if seq == next_data_seq - 1:
                conn.sendall(pack_frame(matricula, nome, seq, MsgType.ACK, b""))
                logger.info(json.dumps({"ts": time.time(), "mode": "tcp", "role": "server", "event": "duplicate", "seq": seq}))
                logger.info(json.dumps({"ts": time.time(), "mode": "tcp", "role": "server", "event": "ack_sent", "seq": seq}))
                return False
            if seq != next_data_seq:
                raise RuntimeError(f"sequência inesperada: {seq} (esperado {next_data_seq})")
            out_file.write(payload)
            bytes_written += len(payload)
            next_data_seq += 1
            conn.sendall(pack_frame(matricula, nome, seq, MsgType.ACK, b""))
            logger.info(json.dumps({"ts": time.time(), "mode": "tcp", "role": "server", "event": "recv", "seq": seq, "type": "DATA", "payload_len": len(payload)}))
            logger.info(json.dumps({"ts": time.time(), "mode": "tcp", "role": "server", "event": "ack_sent", "seq": seq}))
            if progress:
                progress(f"recebido {bytes_written} B")
            return False
        if typ == MsgType.FIN:
            conn.sendall(pack_frame(matricula, nome, seq, MsgType.ACK, b""))
            logger.info(json.dumps({"ts": time.time(), "mode": "tcp", "role": "server", "event": "recv", "seq": seq, "type": "FIN"}))
            logger.info(json.dumps({"ts": time.time(), "mode": "tcp", "role": "server", "event": "ack_sent", "seq": seq}))
            return True
        raise RuntimeError(f"tipo inesperado: {typ}")

    while True:
        raw = conn.recv(65536)
        if not raw:
            break
        for seq, mtyp, payload in dec.feed(raw):
            done = handle(seq, mtyp, payload)
            if done:
                if out_file:
                    out_file.close()
                return bytes_written, path_saved

    if out_file:
        out_file.close()
    raise ConnectionError("fluxo incompleto")


def tcp_run_server(
    host: str,
    port: int,
    out_dir: str,
    matricula: str,
    nome: str,
) -> None:
    os.makedirs(out_dir, exist_ok=True)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, port))
        sock.listen(8)
        while True:
            conn, _addr = sock.accept()
            with conn:
                tcp_receive_loop(conn, matricula, nome, out_dir)