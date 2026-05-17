#!/usr/bin/env python3
"""
Gera CSV resumo a partir dos PCAPs em results/pcaps/<mode>/<scenario>/capture_...pcap
Produz: results/pcap_summary.csv
 
Requisitos: `tshark` disponível no PATH.
Uso:
  python3 scripts/pcap_to_csv.py
"""
from __future__ import annotations
 
import csv
import re
import subprocess
from pathlib import Path
from typing import List, Tuple
 
ROOT = Path("results/pcaps")
OUT = Path("results/pcap_summary.csv")
 
 
def run_tshark(pcap: Path, display_filter: str | None = None) -> List[Tuple[float, int]]:
    """Executa tshark e retorna lista de (time_epoch, frame.len).
 
    Se display_filter for None, usa filtro padrão para porta 9000 (ambas direções).
    """
    cmd = [
        "tshark",
        "-r", str(pcap),
        "-T", "fields",
        "-e", "frame.time_epoch",
        "-e", "frame.len",
        "-E", "separator=,",
    ]
    if display_filter:
        cmd.extend(["-Y", display_filter])
    else:
        cmd.extend(["-Y", "tcp.port==9000 || udp.port==9000"])
 
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        # Pcap vazio ou sem pacotes filtráveis não é erro fatal
        if "0 packets" in proc.stderr or "0 packets" in proc.stdout:
            return []
        raise RuntimeError(f"tshark falhou em {pcap}: {proc.stderr.strip()}")
    
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    out: List[Tuple[float, int]] = []
    for ln in lines:
        parts = ln.split(",", 1)
        if len(parts) < 2:
            continue
        try:
            t = float(parts[0].strip())
            b = int(parts[1].strip())
            out.append((t, b))
        except (ValueError, TypeError):
            continue
    return out
 
 
def _parse_metadata(pcap: Path) -> dict:
    """Extrai mode, scenario e run_id do caminho do pcap."""
    meta = {"mode": "", "scenario": "", "run_id": 0}
    try:
        parts = pcap.parts
        idx = parts.index("pcaps")
        meta["mode"] = parts[idx + 1] if idx + 1 < len(parts) else ""
        meta["scenario"] = parts[idx + 2] if idx + 2 < len(parts) else ""
    except (ValueError, IndexError):
        pass
    # Extrai run_id do nome do arquivo: capture_<scen>_<mode>_<run>.pcap
    match = re.search(r"_(\d+)\.pcap$", pcap.name)
    if match:
        meta["run_id"] = int(match.group(1))
    return meta
 
 
def analyze(pcap: Path):
    try:
        records_total = run_tshark(pcap, None)
        records_a2b = run_tshark(pcap, "tcp.dstport==9000 || udp.dstport==9000")
    except Exception as e:
        print(f"Pulando {pcap}: {e}")
        return None
 
    meta = _parse_metadata(pcap)
 
    if not records_total and not records_a2b:
        return {
            "pcap_path": str(pcap),
            **meta,
            "pkts_on_wire": 0,
            "bytes_on_wire": 0,
            "start_ts": "",
            "end_ts": "",
            "duration_s": 0.0,
            "throughput_mbps_on_wire": 0.0,
        }
 
    # Usa registros client->server (A->B) para métricas
    records = records_a2b if records_a2b else records_total
    times = [t for t, _ in records]
    bytes_sum = sum(b for _, b in records)
    start_ts = min(times) if times else None
    end_ts = max(times) if times else None
    duration_s = end_ts - start_ts if (start_ts is not None and end_ts is not None and end_ts > start_ts) else 0.0
    throughput = (bytes_sum * 8.0) / (duration_s * 1_000_000.0) if duration_s > 0 else 0.0
 
    return {
        "pcap_path": str(pcap),
        **meta,
        "pkts_on_wire": len(records),
        "bytes_on_wire": bytes_sum,
        "start_ts": f"{start_ts:.6f}" if start_ts is not None else "",
        "end_ts": f"{end_ts:.6f}" if end_ts is not None else "",
        "duration_s": round(duration_s, 6),
        "throughput_mbps_on_wire": round(throughput, 6),
    }
 
 
def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    if not ROOT.exists():
        print(f"Nenhum pcap: {ROOT} não existe")
        return
 
    pcaps = sorted(ROOT.rglob("*.pcap"))
    if not pcaps:
        print(f"Nenhum arquivo .pcap encontrado em {ROOT}")
        return
 
    for p in pcaps:
        res = analyze(p)
        if res:
            rows.append(res)
 
    if not rows:
        print("Nenhum pcap processado.")
        return
 
    rows.sort(key=lambda row: int(row.get("run_id", 0) or 0))
 
    fieldnames = [
        "run_id", "scenario", "mode", "pcap_path",
        "pkts_on_wire", "bytes_on_wire",
        "start_ts", "end_ts", "duration_s", "throughput_mbps_on_wire",
    ]
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})
 
    print(f"Escrito {OUT} ({len(rows)} entradas)")
 
 
if __name__ == "__main__":
    main()