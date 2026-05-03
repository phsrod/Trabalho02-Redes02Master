"""Enquadramento de aplicação: linha X-Custom-Auth + cabeçalho binário + payload."""
 
from __future__ import annotations
 
import struct
import zlib
from enum import IntEnum
 
from .auth_header import AUTH_PREFIX, build_auth_line, verify_auth_line
 
STRUCT_HDR = struct.Struct("!I B H I")  # seq, typ, payload_len, crc32
HDR_LEN = STRUCT_HDR.size
 
 
class MsgType(IntEnum):
    DATA = 0
    ACK = 1
    FIN = 2
    META = 3
 
 
def crc32_payload(data: bytes) -> int:
    return zlib.crc32(data) & 0xFFFFFFFF
 
 
def pack_frame(matricula: str, nome: str, seq: int, typ: MsgType, payload: bytes) -> bytes:
    plen = len(payload)
    crc = crc32_payload(payload)
    auth = build_auth_line(matricula, nome)
    body = STRUCT_HDR.pack(seq, int(typ), plen, crc)
    return auth + body + payload
 
 
def parse_frame_verify(
    packet: bytes,
    matricula: str,
    nome: str,
    *,
    require_auth: bool = True,
) -> tuple[int, MsgType, bytes]:
    """Valida auth, checksum e extrai (seq, tipo, payload)."""
    if not packet.startswith(AUTH_PREFIX):
        raise ValueError("prefixo X-Custom-Auth ausente")
    end = packet.find(b"\r\n")
    if end < 0:
        raise ValueError("terminador da linha de auth ausente")
    auth_line = packet[: end + 2]
    rest = packet[end + 2 :]
    if require_auth and not verify_auth_line(auth_line, matricula, nome):
        raise ValueError("X-Custom-Auth inválido")
    if len(rest) < HDR_LEN:
        raise ValueError("cabeçalho binário incompleto")
    seq, typ, plen, crc_exp = STRUCT_HDR.unpack(rest[:HDR_LEN])
    payload = rest[HDR_LEN : HDR_LEN + plen]
    if len(payload) != plen:
        raise ValueError("payload truncado")
    if crc32_payload(payload) != crc_exp:
        raise ValueError("checksum/CRC32 divergente")
    return seq, MsgType(typ), payload