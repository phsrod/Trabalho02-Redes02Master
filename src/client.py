"""Cliente: modo TCP ou R-UDP; registra métricas para análise estatística."""
from __future__ import annotations

import argparse
import os
import logging
import json
import time

from .config import require_identity
from .metrics_log import append_csv_row, build_row, log_json_line
from .http_rudp import rudp_send_file
from .http_tcp import tcp_send_file


def main() -> None:
    p = argparse.ArgumentParser(description="Cliente de transferência (TCP ou R-UDP).")
    p.add_argument("--mode", choices=("tcp", "rudp"), required=True)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=9000)
    p.add_argument("--file", required=True, help="Arquivo a enviar")
    p.add_argument("--csv", default="", help="Anexa métricas a este CSV")
    p.add_argument("--jsonl", default="", help="Anexa métricas a este JSONL")
    p.add_argument("--run-id", type=int, default=0)
    p.add_argument("--scenario", default="manual")
    p.add_argument("--rudp-timeout", type=float, default=2.0)
    args = p.parse_args()

    matricula, nome = require_identity()
    path = os.path.abspath(args.file)
    if not os.path.isfile(path):
        raise SystemExit(f"Arquivo inexistente: {path}")

    # initialize simple JSONL logger writing to transfers.log
    # prefer host-mounted /data when running in Docker (docker-compose mounts ./results -> /data)
    target_dir = os.environ.get("RESULTS_DIR") or ("/data" if os.path.isdir("/data") else "results")
    os.makedirs(target_dir, exist_ok=True)
    log_path = os.path.join(target_dir, "transfers.log")
    logger = logging.getLogger("transfers")
    if not logger.handlers:
        fh = logging.FileHandler(log_path)
        fh.setFormatter(logging.Formatter("%(message)s"))
        logger.setLevel(logging.INFO)
        logger.addHandler(fh)

    logger.info(json.dumps({
        "ts": time.time(),
        "run_id": args.run_id,
        "mode": args.mode,
        "scenario": args.scenario,
        "role": "client",
        "event": "start",
        "peer": f"{args.host}:{args.port}",
    }))

    if args.mode == "tcp":
        dur, nbytes = tcp_send_file(args.host, args.port, path, matricula, nome)
    else:
        dur, nbytes = rudp_send_file(
            args.host,
            args.port,
            path,
            matricula,
            nome,
            timeout_sec=args.rudp_timeout,
        )

    row = build_row(
        run_id=args.run_id,
        scenario=args.scenario,
        mode=args.mode,
        duration_sec=dur,
        bytes_file=nbytes,
        role="client",
    )
    print(
        f"OK bytes={nbytes} duration_s={dur:.4f} throughput_mbps={row['throughput_mbps']}"
    )
    if args.csv:
        append_csv_row(args.csv, row)
    if args.jsonl:
        log_json_line(args.jsonl, row)

    logger.info(json.dumps({
        "ts": time.time(),
        "run_id": args.run_id,
        "mode": args.mode,
        "scenario": args.scenario,
        "role": "client",
        "event": "end",
        "bytes_app": nbytes,
        "duration_s": dur,
    }))


if __name__ == "__main__":
    main()