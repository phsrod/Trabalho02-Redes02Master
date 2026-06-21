#!/usr/bin/env python3
"""
Calcula a taxa de erro real baseada em retransmissões.

TCP:   usa tshark (tcp.analysis.retransmission / tcp.analysis.fast_retransmission)
R-UDP: parseia o transfers.log — cada retransmissão do _send_sw() é logada
       por AMBOS os lados (cliente e servidor), independente do netem.

Uso:
    python scripts/calculate_error_rate.py ^
        --csv results/metrics_app.csv ^
        --transfers-log results/transfers.log ^
        --pcap-dir results/pcaps ^
        --out results/retransmission_rate.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

# ── Constantes ─────────────────────────────────────────────────────────────
CHUNK_SIZE = 1000  # bytes por quadro DATA no R-UDP

# Mapeamento size -> bytes esperados
FILE_SIZE_BYTES = {
    "100k": 100_000,
    "500k": 500_000,
    "1m": 1_000_000,
}


# ═══════════════════════════════════════════════════════════════════════════
#  Parte 1 — TCP via PCAP (tshark)
# ═══════════════════════════════════════════════════════════════════════════

def _extract_pcap_info(pcap_path: Path) -> dict[str, Any]:
    """Extrai mode, file_size, scenario, run_id do caminho do pcap."""
    info: dict[str, Any] = {"mode": "", "file_size": "", "scenario": "", "run_id": ""}
    parts = pcap_path.parts
    try:
        idx = parts.index("pcaps")
        info["mode"] = parts[idx + 1]
        if len(parts) > idx + 3 and parts[idx + 2] in {"100k", "500k", "1m"}:
            info["file_size"] = parts[idx + 2]
            info["scenario"] = parts[idx + 3]
        else:
            info["scenario"] = parts[idx + 2]
    except (ValueError, IndexError):
        pass
    name = pcap_path.stem
    toks = name.split("_")
    if toks and toks[-1].isdigit():
        info["run_id"] = int(toks[-1])
    return info


def _count_tcp_retransmissions(pcap: Path) -> dict[str, float | int] | None:
    """Conta pacotes totais e retransmissões TCP na porta 8080 com tshark."""
    try:
        r_total = subprocess.run(
            [
                "tshark", "-r", str(pcap),
                "-Y", "tcp.port==8080",
                "-T", "fields", "-e", "frame.number",
            ],
            capture_output=True, text=True, timeout=120,
        )
        if r_total.returncode != 0:
            return None
        total = len([ln for ln in r_total.stdout.splitlines() if ln.strip()])
        if total == 0:
            return {"total_packets": 0, "retransmissions": 0, "error_rate_pct": 0.0}

        r_retrans = subprocess.run(
            [
                "tshark", "-r", str(pcap),
                "-Y", (
                    "tcp.port==8080 and "
                    "(tcp.analysis.retransmission or "
                    " tcp.analysis.fast_retransmission)"
                ),
                "-T", "fields", "-e", "frame.number",
            ],
            capture_output=True, text=True, timeout=120,
        )
        if r_retrans.returncode != 0:
            return None
        retrans = len([ln for ln in r_retrans.stdout.splitlines() if ln.strip()])

        rate = (retrans / total) * 100.0 if total > 0 else 0.0
        return {
            "total_packets": total,
            "retransmissions": retrans,
            "error_rate_pct": round(rate, 4),
        }
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def analyze_tcp_pcaps(pcap_dir: str) -> list[dict[str, Any]]:
    """Processa pcaps TCP e retorna lista de resultados."""
    rows: list[dict[str, Any]] = []
    root = Path(pcap_dir)
    if not root.exists():
        print(f"Aviso: diretório de pcaps não encontrado: {root}", file=sys.stderr)
        return rows

    pcaps = sorted(root.rglob("*.pcap"))
    for pcap in pcaps:
        info = _extract_pcap_info(pcap)
        if info["mode"] != "tcp":
            continue

        stats = _count_tcp_retransmissions(pcap)
        if stats is None:
            print(f"  ⚠  erro ao processar {pcap.name}")
            continue

        rows.append({
            "run_id": info["run_id"],
            "scenario": info["scenario"],
            "mode": "tcp",
            "file_size": info["file_size"],
            "total_packets": stats["total_packets"],
            "retransmissions": stats["retransmissions"],
            "error_rate_pct": stats["error_rate_pct"],
            "source": pcap.name,
        })
        print(
            f"  TCP {pcap.name:45s}  "
            f"sc={info['scenario']}  "
            f"size={info['file_size'] or '-':>5}  "
            f"run={info['run_id']!s:>3}  "
            f"pkts={stats['total_packets']:>5}  "
            f"retrans={stats['retransmissions']:>4}  "
            f"erro={stats['error_rate_pct']:.2f}%"
        )
    return rows


# ═══════════════════════════════════════════════════════════════════════════
#  Parte 2 — R-UDP via transfers.log
# ═══════════════════════════════════════════════════════════════════════════

def _estimate_unique_packets(file_size_label: str) -> int:
    """Estima o número de pacotes R-UDP únicos para um dado tamanho de arquivo.

    Fórmula: 1 (META req cliente) + 1 (META resp servidor)
              + ceil(body_bytes / CHUNK_SIZE) (DATA)
              + 1 (FIN) = ceil(F / 1000) + 3
    """
    body = FILE_SIZE_BYTES.get(file_size_label, 500_000)
    data_pkts = math.ceil(body / CHUNK_SIZE)
    return data_pkts + 3  # META(req) + META(resp) + DATA * N + FIN


def analyze_rudp_via_transfers_log(
    csv_path: str,
    transfers_log_path: str,
) -> list[dict[str, Any]]:
    """Parseia o transfers.log e conta retransmissões R-UDP por run_id.

    Como o benchmark roda SEQUENCIALMENTE, cada evento 'dns_resolved'
    no log inicia um novo run, e o próximo 'http_done'/'http_failed'
    o finaliza. Retransmissões são contadas entre esses marcadores.
    """
    # ── 1. Carregar CSV na ordem dos runs ──
    df = pd.read_csv(csv_path)
    if "role" in df.columns:
        client = df[df["role"].astype(str).str.lower() == "client"]
        if not client.empty:
            df = client
    df = df.sort_values("run_id").reset_index(drop=True)
    total_runs = len(df)

    # ── 2. Parsear transfers.log ──
    log_path = Path(transfers_log_path)
    if not log_path.exists():
        print(f"Erro: transfers.log não encontrado: {log_path}", file=sys.stderr)
        return []

    entries: list[dict[str, Any]] = []
    with open(log_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    # ── 3. Caminhar pelos eventos, contando retransmissões por run ──
    results: list[dict[str, Any]] = []
    run_idx = 0
    counting = False
    retrans_count = 0

    for entry in entries:
        event = entry.get("event")

        if event == "dns_resolved":
            # Se já estávamos contando, o run anterior não teve http_done
            # (raro, mas pode acontecer se o script crashar)
            if counting and run_idx > 0 and run_idx <= total_runs:
                prev = df.iloc[run_idx - 1]
                if prev["mode"] == "rudp":
                    _save_rudp_result(results, prev, retrans_count)

            if run_idx < total_runs:
                counting = True
                retrans_count = 0
                run_idx += 1

        elif event == "retransmit" and counting and run_idx > 0:
            retrans_count += 1

        elif event in ("http_done", "http_failed") and counting and run_idx > 0:
            counting = False
            current = df.iloc[run_idx - 1]
            if current["mode"] == "rudp":
                _save_rudp_result(results, current, retrans_count)

    # ── Último run se não foi finalizado ──
    if counting and run_idx > 0 and run_idx <= total_runs:
        last = df.iloc[run_idx - 1]
        if last["mode"] == "rudp":
            _save_rudp_result(results, last, retrans_count)

    return results


def _save_rudp_result(
    results: list[dict[str, Any]],
    run: Any,  # row do DataFrame
    retransmissions: int,
) -> None:
    """Calcula a taxa e adiciona à lista de resultados."""
    file_size = str(run.get("file_size", ""))
    unique_pkts = _estimate_unique_packets(file_size)
    total_pkts = unique_pkts + retransmissions
    rate = (retransmissions / total_pkts * 100.0) if total_pkts > 0 else 0.0

    run_id = int(run["run_id"])  # pandas retorna numpy.int64; converter para Python int

    results.append({
        "run_id": run_id,
        "scenario": str(run["scenario"]),
        "mode": "rudp",
        "file_size": file_size,
        "total_packets": total_pkts,
        "retransmissions": retransmissions,
        "error_rate_pct": round(rate, 4),
        "source": "transfers.log",
    })

    print(
        f"  R-UDP run={run_id!s:>3}  "
        f"sc={run['scenario']}  "
        f"size={file_size or '-':>5}  "
        f"pkts={total_pkts:>5}  "
        f"retrans={retransmissions:>4}  "
        f"erro={rate:.2f}%"
    )


# ═══════════════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Calcula taxa de erro real baseada em retransmissões.\n"
            "TCP:   tshark nos pcaps\n"
            "R-UDP: transfers.log (retransmissões de AMBOS os lados)"
        )
    )
    parser.add_argument(
        "--csv", required=True,
        help="Caminho do metrics_app.csv (para obter run_id, mode, scenario, file_size)",
    )
    parser.add_argument(
        "--transfers-log", default="results/transfers.log",
        help="Caminho do transfers.log (para extrair retransmissões R-UDP)",
    )
    parser.add_argument(
        "--pcap-dir", default="results/pcaps",
        help="Diretório com pcaps organizados por mode/[size/]scenario/ (para análise TCP)",
    )
    parser.add_argument(
        "--out", default="results/retransmission_rate.csv",
        help="Caminho do CSV de saída",
    )
    args = parser.parse_args()

    all_rows: list[dict[str, Any]] = []

    # ── TCP: pcaps ──
    print("── Analisando TCP via pcaps (tshark) ──")
    tcp_rows = analyze_tcp_pcaps(args.pcap_dir)
    all_rows.extend(tcp_rows)

    # ── R-UDP: transfers.log ──
    print("\n── Analisando R-UDP via transfers.log ──")
    rudp_rows = analyze_rudp_via_transfers_log(args.csv, args.transfers_log)
    all_rows.extend(rudp_rows)

    if not all_rows:
        print("\nNenhum resultado obtido.")
        sys.exit(1)

    # ── Ordenar saída ──
    all_rows.sort(key=lambda r: (
        r["mode"],
        r["file_size"] or "",
        r["scenario"],
        int(r.get("run_id", 0) or 0),
    ))

    # ── Salvar CSV ──
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "run_id", "scenario", "mode", "file_size",
        "total_packets", "retransmissions", "error_rate_pct", "source",
    ]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(all_rows)

    # ── Agregados ──
    groups: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    for r in all_rows:
        key = (r["mode"], r["scenario"], r["file_size"] or "-")
        groups[key].append(r["error_rate_pct"])

    print("\n── Taxa de erro média por grupo ──")
    print(f"{'Modo':<6} {'Cen':<4} {'Tamanho':<8} {'média(%)':<10} {'min(%)':<10} {'max(%)':<10} {'amostras':<9}")
    print("-" * 61)
    for key in sorted(groups):
        vals = groups[key]
        avg = sum(vals) / len(vals)
        lo = min(vals)
        hi = max(vals)
        print(f"{key[0]:<6} {key[1]:<4} {key[2]:<8} {avg:<10.2f} {lo:<10.2f} {hi:<10.2f} {len(vals):<9}")

    print(f"\n✔ Resultados salvos em: {out_path}")
    print(f"  TCP: {len(tcp_rows)} runs   R-UDP: {len(rudp_rows)} runs")


if __name__ == "__main__":
    main()