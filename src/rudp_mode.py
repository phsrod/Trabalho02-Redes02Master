"""UDP confiável com Stop-and-Wait: ACK, timeout, retransmissão e CRC32 no payload."""
from __future__ import annotations
 
import json
import os
import select
import socket
import time
import logging
from typing import Callable
 
from .framing import MsgType, pack_frame, parse_frame_verify
 
# UDP: evitar fragmentação IP (MTU ~1500); margem para cabeçalhos IP/UDP e linha de auth.
UDP_PAYLOAD_MAX = 1200
CHUNK_SIZE = UDP_PAYLOAD_MAX - 200
 
 
def rudp_send_file(
    host: str,
    port: int,
    filepath: str,
    matricula: str,
    nome: str,
    timeout_sec: float = 2.0,
    max_retries: int = 1000,
    progress: Callable[[str], None] | None = None,
) -> tuple[float, int]:
    size = os.path.getsize(filepath)
    basename = os.path.basename(filepath)
    t0 = time.monotonic()
    bytes_sent = 0
 
    logger = logging.getLogger("transfers")
 
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setblocking(False)
 
        def send_sw(seq: int, typ: MsgType, payload: bytes) -> None:
            nonlocal bytes_sent
            pkt = pack_frame(matricula, nome, seq, typ, payload)
            if len(pkt) > 65507:
                raise ValueError("datagrama UDP excede limite prático")
            for attempt in range(max_retries):
                sock.sendto(pkt, (host, port))
                bytes_sent += len(pkt)
                deadline = time.monotonic() + timeout_sec
                while time.monotonic() < deadline:
                    r, _, _ = select.select([sock], [], [], max(0.0, deadline - time.monotonic()))
                    if not r:
                        continue
                    data, _addr = sock.recvfrom(65535)
                    try:
                        aseq, atyp, apay = parse_frame_verify(data, matricula, nome)
                    except ValueError:
                        continue
                    if atyp == MsgType.ACK and aseq == seq:
                        # ACK recebido para este seq
                        logger.info(json.dumps({"ts": time.time(), "mode": "rudp", "role": "client", "event": "ack_received", "seq": aseq}))
                        return
                # não recebeu ACK dentro do timeout -> vai retransmitir
                if attempt < max_retries - 1:
                    logger.info(json.dumps({"ts": time.time(), "mode": "rudp", "role": "client", "event": "retransmit", "seq": seq, "attempt": attempt + 1}))
                else:
                    logger.error(json.dumps({"ts": time.time(), "mode": "rudp", "role": "client", "event": "timeout", "seq": seq, "attempts": max_retries}))
                if progress and attempt % 10 == 0:
                    progress(f"retransmitindo seq={seq} tentativa={attempt+1}")
            raise TimeoutError(f"falha após retransmissões: seq={seq}")
 
        meta = json.dumps({"name": basename, "size": size}, separators=(",", ":")).encode()
        send_sw(0, MsgType.META, meta)
        if progress:
            progress("meta ok")
 
        seq = 1
        with open(filepath, "rb") as f:
            while True:
                block = f.read(CHUNK_SIZE)
                if not block:
                    break
                send_sw(seq, MsgType.DATA, block)
                seq += 1
                if progress:
                    progress(f"enviado até seq={seq-1}")
 
        send_sw(seq, MsgType.FIN, b"")
 
    elapsed = time.monotonic() - t0
    return elapsed, bytes_sent