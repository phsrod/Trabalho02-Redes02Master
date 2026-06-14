"""Servidor DNS minimalista: consultas tipo A a partir de hosts.txt."""
from __future__ import annotations

import argparse
import logging
import socket
from pathlib import Path

from .dns_protocol import pack_response, parse_query


def load_zone(path: str | Path) -> dict[str, str]:
    zone: dict[str, str] = {}
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) == 2 and "." in parts[0] and parts[0][0].isdigit():
            ip, name = parts
        elif len(parts) == 2:
            name, ip = parts
        else:
            continue
        zone[name.lower()] = ip
    return zone


def run_dns_server(host: str, port: int, zone_path: str) -> None:
    zone = load_zone(zone_path)
    logger = logging.getLogger("dns")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind((host, port))
        logger.info("DNS ouvindo em %s:%s (%d registros)", host, port, len(zone))
        while True:
            packet, addr = sock.recvfrom(4096)
            try:
                query_id, name = parse_query(packet)
                ip = zone.get(name.lower())
                if ip is None:
                    logger.warning("NXDOMAIN %s de %s", name, addr)
                    continue
                response = pack_response(query_id, name, ip)
                sock.sendto(response, addr)
                logger.info("RESOLVIDO %s -> %s (id=%s)", name, ip, query_id)
            except ValueError as exc:
                logger.warning("pacote inválido de %s: %s", addr, exc)


def main() -> None:
    p = argparse.ArgumentParser(description="Servidor DNS simplificado (UDP).")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=53)
    p.add_argument("--zone", default="/app/hosts.txt")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    run_dns_server(args.host, args.port, args.zone)


if __name__ == "__main__":
    main()
