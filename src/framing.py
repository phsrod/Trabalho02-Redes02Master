"""Enquadramento de aplicação: linha X-Custom-Auth + cabeçalho binário + payload."""
 
from __future__ import annotations
 
import struct
import zlib
from enum import IntEnum
 
from .auth_header import AUTH_PREFIX, build_auth_line
 
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