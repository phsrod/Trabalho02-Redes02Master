"""Registro de métricas para cruzamento com capturas (Wireshark/tcpdump)."""
 
from __future__ import annotations
 
import csv
import json
import os
import time
from typing import Any
 
 
def throughput_mbps(num_bytes: int, seconds: float) -> float:
    if seconds <= 0:
        return 0.0
    return (num_bytes * 8.0) / (seconds * 1_000_000.0)
 
 
CSV_FIELDS = [
    "ts_iso",
    "run_id",
    "scenario",
    "mode",
    "role",
    "duration_sec",
    "bytes_app",
    "throughput_mbps",
]
 
 
def append_csv_row(path: str, row: dict[str, Any]) -> None:
    d = os.path.dirname(os.path.abspath(path))
    if d:
        os.makedirs(d, exist_ok=True)
    file_exists = os.path.isfile(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        if not file_exists:
            w.writeheader()
        w.writerow(row)
 
 
def log_json_line(path: str, obj: dict[str, Any]) -> None:
    d = os.path.dirname(os.path.abspath(path))
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")
 
 
def build_row(
    *,
    run_id: int,
    scenario: str,
    mode: str,
    duration_sec: float,
    bytes_file: int,
    role: str,
) -> dict[str, Any]:
    return {
        "ts_iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
        "run_id": run_id,
        "scenario": scenario,
        "mode": mode,
        "role": role,
        "duration_sec": round(duration_sec, 6),
        "bytes_app": bytes_file,
        "throughput_mbps": round(throughput_mbps(bytes_file, duration_sec), 6),
    }