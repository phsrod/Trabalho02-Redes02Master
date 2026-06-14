"""DNS simplificado: campos ID, Name e IP (consulta/resposta tipo A)."""
from __future__ import annotations

import socket
import struct

QUERY = 0
RESPONSE = 1

_FMT = struct.Struct("!H B")  # id, name_len


def pack_query(query_id: int, name: str) -> bytes:
    encoded = name.encode("utf-8")
    if not (1 <= len(encoded) <= 255):
        raise ValueError("nome DNS inválido")
    return _FMT.pack(query_id & 0xFFFF, len(encoded)) + encoded


def pack_response(query_id: int, name: str, ipv4: str) -> bytes:
    encoded = name.encode("utf-8")
    if not (1 <= len(encoded) <= 255):
        raise ValueError("nome DNS inválido")
    ip_bytes = socket.inet_aton(ipv4)
    return _FMT.pack(query_id & 0xFFFF, len(encoded)) + encoded + ip_bytes


def parse_query(packet: bytes) -> tuple[int, str]:
    if len(packet) < _FMT.size + 1:
        raise ValueError("pacote DNS de consulta incompleto")
    query_id, name_len = _FMT.unpack(packet[: _FMT.size])
    start = _FMT.size
    end = start + name_len
    if len(packet) < end:
        raise ValueError("nome DNS truncado")
    return query_id, packet[start:end].decode("utf-8")


def parse_response(packet: bytes) -> tuple[int, str, str]:
    if len(packet) < _FMT.size + 1 + 4:
        raise ValueError("pacote DNS de resposta incompleto")
    query_id, name_len = _FMT.unpack(packet[: _FMT.size])
    start = _FMT.size
    end = start + name_len
    if len(packet) < end + 4:
        raise ValueError("resposta DNS truncada")
    name = packet[start:end].decode("utf-8")
    ipv4 = socket.inet_ntoa(packet[end : end + 4])
    return query_id, name, ipv4
