"""Registro de métricas para cruzamento com capturas (Wireshark/tcpdump)."""
 
from __future__ import annotations
 
import csv
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