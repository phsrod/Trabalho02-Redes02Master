"""Transferência em modo TCP com quadros de aplicação (Stop-and-Wait na camada app)."""
 
from __future__ import annotations
 
import json
import os
import socket
import time
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
 
    with socket.create_connection((host, port), timeout=30) as conn:
        conn.settimeout(300.0)
 
        # META seq 0
        meta = json.dumps({"name": basename, "size": size}, separators=(",", ":")).encode()
        frame = pack_frame(matricula, nome, 0, MsgType.META, meta)
        conn.sendall(frame)
        bytes_sent += len(frame)
        _recv_until_ack(conn, dec, matricula, nome, 0)
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
                sent_payload += len(block)
                seq += 1
                if progress:
                    progress(f"dados {sent_payload}/{size}")
 
        frame = pack_frame(matricula, nome, seq, MsgType.FIN, b"")
        conn.sendall(frame)
        bytes_sent += len(frame)
        _recv_until_ack(conn, dec, matricula, nome, seq)
 
    elapsed = time.monotonic() - t0
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
        if typ == MsgType.META:
            meta = json.loads(payload.decode("utf-8"))
            safe = os.path.basename(meta["name"])
            path_saved = os.path.join(out_dir, safe)
            out_file = open(path_saved, "wb")
            meta_ok = True
            next_data_seq = 1
            conn.sendall(pack_frame(matricula, nome, seq, MsgType.ACK, b""))
            return False
        if typ == MsgType.DATA:
            if not meta_ok or out_file is None:
                raise RuntimeError("DATA antes de META")
            if seq == next_data_seq - 1:
                conn.sendall(pack_frame(matricula, nome, seq, MsgType.ACK, b""))
                return False
            if seq != next_data_seq:
                raise RuntimeError(f"sequência inesperada: {seq} (esperado {next_data_seq})")
            out_file.write(payload)
            bytes_written += len(payload)
            next_data_seq += 1
            conn.sendall(pack_frame(matricula, nome, seq, MsgType.ACK, b""))
            if progress:
                progress(f"recebido {bytes_written} B")
            return False
        if typ == MsgType.FIN:
            conn.sendall(pack_frame(matricula, nome, seq, MsgType.ACK, b""))
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