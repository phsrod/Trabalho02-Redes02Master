"""Cliente DNS minimalista com timeout e retransmissão na camada de aplicação."""
from __future__ import annotations

import logging
import random
import select
import socket
import time

from .dns_protocol import pack_query, parse_response


def resolve_a_record(
    dns_host: str,
    dns_port: int,
    name: str,
    *,
    timeout_sec: float = 2.0,
    max_retries: int = 5,
) -> tuple[str, float, int]:
    """
    Resolve nome -> IPv4.
    Retorna (ip, duracao_segundos, tentativas_usadas).
    """
    logger = logging.getLogger("dns")
    query_id = random.randint(0, 0xFFFF)
    packet = pack_query(query_id, name)
    t0 = time.monotonic()

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setblocking(False)
        for attempt in range(1, max_retries + 1):
            sock.sendto(packet, (dns_host, dns_port))
            deadline = time.monotonic() + timeout_sec
            while time.monotonic() < deadline:
                ready, _, _ = select.select([sock], [], [], max(0.0, deadline - time.monotonic()))
                if not ready:
                    continue
                data, _addr = sock.recvfrom(4096)
                try:
                    rid, rname, ip = parse_response(data)
                except ValueError:
                    continue
                if rid != query_id or rname.lower() != name.lower():
                    continue
                if ip == "0.0.0.0":
                    raise LookupError(f"nome não encontrado: {name}")
                elapsed = time.monotonic() - t0
                logger.info(
                    "DNS OK %s -> %s em %.4fs (tentativa %d)",
                    name,
                    ip,
                    elapsed,
                    attempt,
                )
                return ip, elapsed, attempt
            logger.warning("timeout DNS para %s (tentativa %d/%d)", name, attempt, max_retries)

    raise TimeoutError(f"falha ao resolver {name} após {max_retries} tentativas")