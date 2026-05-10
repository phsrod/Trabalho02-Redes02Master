#!/usr/bin/env python3
"""Converte .pcap para CSV sumarizado (tshark necessário)."""
from __future__ import annotations
 
import csv
import glob
import os
import subprocess
import sys
import re
 
PCAP_DIR = "results/pcaps"
OUT = "results/pcap_summary.csv"
 
TSHARK_FIELDS = [
    "frame.time_epoch",
    "frame.len",
    "ip.src",
    "ip.dst",
    "udp.srcport",
    "udp.dstport",
    "tcp.srcport",
    "tcp.dstport",
]
 
 
def run_tshark(pcap: str) -> list[dict[str, str]]:
    if not shutil.which("tshark"):
        print("tshark not found. Install it with: sudo apt install tshark", file=sys.stderr)
        return []
    cmd = ["tshark", "-r", pcap, "-T", "fields"]
    for f in TSHARK_FIELDS:
        cmd.extend(["-e", f])
    cmd.extend(["--header", "y"])
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True)
    except subprocess.CalledProcessError:
        return []
    lines = out.strip().splitlines()
    if len(lines) < 2:
        return []
    headers = lines[0].split("\t")
    rows = []
    for line in lines[1:]:
        vals = line.split("\t")
        rows.append(dict(zip(headers, vals)))
    return rows
 
 
def _parse_pcap_name(name: str) -> dict:
    m = re.match(r"(\w+)_(\w+)_run(\d+)", name)
    if m:
        return {"scenario": m.group(1), "mode": m.group(2), "run_id": int(m.group(3))}
    return {}
 
 
def main() -> None:
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    pattern = os.path.join(PCAP_DIR, "*.pcap")
    all_rows = []
    for pcap in sorted(glob.glob(pattern)):
        base = os.path.splitext(os.path.basename(pcap))[0]
        meta = _parse_pcap_name(base)
        frames = run_tshark(pcap)
        if not frames:
            continue
        first = frames[0]
        last = frames[-1]
        total_bytes = sum(int(f.get("frame.len", 0) or 0) for f in frames)
        start_ts = float(first.get("frame.time_epoch", 0))
        end_ts = float(last.get("frame.time_epoch", 0))
        dur = end_ts - start_ts
        mbps = (total_bytes * 8.0) / (dur * 1_000_000.0) if dur > 0 else 0.0
        row = {
            "run_id": meta.get("run_id", ""),
            "scenario": meta.get("scenario", ""),
            "mode": meta.get("mode", ""),
            "pcap_path": pcap,
            "pkts_on_wire": len(frames),
            "bytes_on_wire": total_bytes,
            "start_ts": start_ts,
            "end_ts": end_ts,
            "duration_s": round(dur, 6),
            "throughput_mbps_on_wire": round(mbps, 6),
        }
        all_rows.append(row)
        print(f"  {base}: {len(frames)} pkts, {mbps:.2f} mbps")
 
    if not all_rows:
        print("No pcap files found.")
        return
 
    fields = [
        "run_id", "scenario", "mode", "pcap_path",
        "pkts_on_wire", "bytes_on_wire", "start_ts", "end_ts",
        "duration_s", "throughput_mbps_on_wire",
    ]
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in all_rows:
            w.writerow({k: r.get(k, "") for k in fields})
 
    print(f"Wrote {OUT} ({len(all_rows)} entries)")
 
 
if __name__ == "__main__":
    main()