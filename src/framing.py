"""Enquadramento de aplicação: linha X-Custom-Auth + cabeçalho binário + payload."""
from __future__ import annotations
 
import struct
import zlib
from enum import IntEnum
 
from .auth_header import AUTH_PREFIX, build_auth_line, verify_auth_line
 
STRUCT_HDR = struct.Struct("!I B H I")  # seq (4), typ (1), payload_len (2), crc32 (4)
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
    """Valida auth, checksum e extrai (seq, tipo, payload).
    
    Levanta ValueError se:
    - Pacote vazio ou muito curto
    - Prefixo X-Custom-Auth ausente
    - Linha de auth sem \\r\\n
    - Hash não corresponde (se require_auth=True)
    - Cabeçalho binário incompleto
    - Payload truncado
    - CRC32 não confere
    """
    if not packet or len(packet) < len(AUTH_PREFIX):
        raise ValueError("pacote vazio ou muito curto")
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
    
    if plen > 65535:  # uint16 max
        raise ValueError(f"payload_len absurdo: {plen}")
    
    payload = rest[HDR_LEN : HDR_LEN + plen]
    if len(payload) != plen:
        raise ValueError("payload truncado")
    if crc32_payload(payload) != crc_exp:
        raise ValueError("checksum/CRC32 divergente")
    
    return seq, MsgType(typ), payload
 
 
class TcpStreamDecoder:
    """Reconstitui quadros a partir de um stream TCP byte a byte."""
 
    def __init__(self, matricula: str, nome: str) -> None:
        self._matricula = matricula
        self._nome = nome
        self._buf = bytearray()
 
    def feed(self, chunk: bytes) -> list[tuple[int, MsgType, bytes]]:
        self._buf.extend(chunk)
        out: list[tuple[int, MsgType, bytes]] = []
        while True:
            if len(self._buf) < len(AUTH_PREFIX):
                break
            if not self._buf[: len(AUTH_PREFIX)] == AUTH_PREFIX:
                raise ValueError("stream TCP: esperado X-Custom-Auth")
            crlf = self._buf.find(b"\r\n", len(AUTH_PREFIX))
            if crlf < 0:
                break
            body_start = crlf + 2
            if len(self._buf) < body_start + HDR_LEN:
                break
            seq, typ, plen, _crc = STRUCT_HDR.unpack(
                bytes(self._buf[body_start : body_start + HDR_LEN])
            )
            total = body_start + HDR_LEN + plen
            if len(self._buf) < total:
                break
            frame = bytes(self._buf[:total])
            del self._buf[:total]
            seq, typ, payload = parse_frame_verify(
                frame, self._matricula, self._nome, require_auth=True
            )
            out.append((seq, typ, payload))
        return out