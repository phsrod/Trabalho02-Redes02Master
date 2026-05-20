"""Servidor: modo TCP ou R-UDP."""
from __future__ import annotations

import argparse
import os
import logging
import json
import time

from .config import require_identity
from .rudp_mode import rudp_run_server
from .tcp_mode import tcp_run_server


def main() -> None:
    p = argparse.ArgumentParser(description="Servidor de transferência (TCP ou R-UDP).")
    p.add_argument("--mode", choices=("tcp", "rudp"), required=True)
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=9000)
    p.add_argument("--out", dest="out_dir", default="/tmp/received")
    args = p.parse_args()
    matricula, nome = require_identity()

    # initialize logger writing to transfers.log (shared file)
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
        "mode": args.mode,
        "role": "server",
        "event": "start",
        "peer": f"{args.host}:{args.port}",
    }))

    if args.mode == "tcp":
        tcp_run_server(args.host, args.port, args.out_dir, matricula, nome)
    else:
        rudp_run_server(args.host, args.port, args.out_dir, matricula, nome)


if __name__ == "__main__":
    main()