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
import subprocess
from pathlib import Path
from typing import List, Tuple

ROOT = Path("results/pcaps")
OUT = Path("results/pcap_summary.csv")


def run_tshark(pcap: Path, display_filter: str | None = None) -> List[Tuple[float, int]]:
    """Run tshark and return list of (time_epoch, frame.len) tuples.

    If display_filter is None, defaults to DNS (53) e HTTP (8080).
    """
    cmd = [
        "tshark",
        "-r",
        str(pcap),
        "-T",
        "fields",
        "-e",
        "frame.time_epoch",
        "-e",
        "frame.len",
        "-E",
        "separator=,",
    ]
    if display_filter:
        cmd.extend(["-Y", display_filter])
    else:
        cmd.extend(["-Y", "udp.port==53 || tcp.port==8080 || udp.port==8080"])

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"tshark failed on {pcap}: {proc.stderr.strip()}")
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    out: List[Tuple[float, int]] = []
    for ln in lines:
        parts = ln.split(",", 1)
        if len(parts) < 2:
            continue
        try:
            t = float(parts[0].strip())
            b = int(parts[1].strip())
        except Exception:
            continue
        out.append((t, b))
    return out


def analyze(pcap: Path):
    try:
        # records for any packet touching port 9000 (both directions)
        records_total = run_tshark(pcap, None)
        # records for client->server direction: destination port 9000
        records_a2b = run_tshark(
            pcap, "udp.dstport==53 || tcp.dstport==8080 || udp.dstport==8080"
        )
    except Exception as e:
        print(f"pular {pcap}: {e}")
        return None

    if not records_total and not records_a2b:
        return {
            "pcap_path": str(pcap),
            "mode": "",
            "scenario": "",
            "run_id": "",
            "pkts_on_wire": 0,
            "bytes_on_wire": 0,
            "start_ts": "",
            "end_ts": "",
            "duration_s": 0.0,
            "throughput_mbps_on_wire": 0.0,
            "pkts_a_to_b": 0,
            "bytes_a_to_b": 0,
            "start_ts_a_to_b": "",
            "end_ts_a_to_b": "",
            "duration_s_a_to_b": 0.0,
            "throughput_mbps_a_to_b": 0.0,
        }

    # totals (both directions)
    times_total = [t for t, _ in records_total] if records_total else []
    bytes_sum_total = sum(b for _, b in records_total) if records_total else 0
    start_total = min(times_total) if times_total else None
    end_total = max(times_total) if times_total else None
    duration_total = end_total - start_total if (start_total is not None and end_total is not None and end_total > start_total) else 0.0
    throughput_total = (bytes_sum_total * 8.0) / (duration_total * 1_000_000.0) if duration_total > 0 else 0.0

    # client -> server (A->B)
    times_a2b = [t for t, _ in records_a2b] if records_a2b else []
    bytes_sum_a2b = sum(b for _, b in records_a2b) if records_a2b else 0
    start_a2b = min(times_a2b) if times_a2b else None
    end_a2b = max(times_a2b) if times_a2b else None
    duration_a2b = end_a2b - start_a2b if (start_a2b is not None and end_a2b is not None and end_a2b > start_a2b) else 0.0
    throughput_a2b = (bytes_sum_a2b * 8.0) / (duration_a2b * 1_000_000.0) if duration_a2b > 0 else 0.0

    # parse mode/size/scenario/run from path:
    # results/pcaps/<mode>/<size>/<scenario>/capture_..._<run>.pcap
    parts = pcap.parts
    mode = ""
    file_size = ""
    scenario = ""
    run_id = ""
    try:
        idx = parts.index("pcaps")
        mode = parts[idx + 1]
        if len(parts) > idx + 3 and parts[idx + 2] in {"100k", "500k", "1m"}:
            file_size = parts[idx + 2]
            scenario = parts[idx + 3]
        else:
            scenario = parts[idx + 2]
    except Exception:
        pass
    name = pcap.stem
    toks = name.split("_")
    if toks and toks[-1].isdigit():
        run_id = int(toks[-1])

    # Use client->server (A->B) metrics for the CSV fields so they match the
    # application-side throughput (metrics_app.csv). Do not add extra columns.
    return {
        "pcap_path": str(pcap),
        "mode": mode,
        "file_size": file_size,
        "scenario": scenario,
        "run_id": run_id,
        "pkts_on_wire": len(records_a2b) if records_a2b else 0,
        "bytes_on_wire": bytes_sum_a2b,
        "start_ts": f"{start_a2b:.6f}" if start_a2b is not None else "",
        "end_ts": f"{end_a2b:.6f}" if end_a2b is not None else "",
        "duration_s": round(duration_a2b, 6),
        "throughput_mbps_on_wire": round(throughput_a2b, 6),
    }


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    if not ROOT.exists():
        print(f"Nenhum pcap: {ROOT} não existe")
        return
    for p in sorted(ROOT.rglob("*.pcap")):
        res = analyze(p)
        if res:
            rows.append(res)

    if not rows:
        print("Nenhum pcap processado.")
        return

    rows.sort(key=lambda row: int(row.get("run_id", 0) or 0))

    with open(OUT, "w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "run_id",
            "scenario",
            "mode",
            "file_size",
            "pcap_path",
            "pkts_on_wire",
            "bytes_on_wire",
            "start_ts",
            "end_ts",
            "duration_s",
            "throughput_mbps_on_wire",
        ]
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})

    print(f"Wrote {OUT} ({len(rows)} entries)")


if __name__ == "__main__":
    main()
