"""Servidor Web HTTP/1.1 sobre TCP ou R-UDP."""
from __future__ import annotations

import argparse
import json
import logging
import os
import time

from .config import require_identity
from .http_rudp import http_rudp_run_server
from .http_tcp import http_tcp_run_server


def main() -> None:
    p = argparse.ArgumentParser(description="Miniservidor Web HTTP/1.1 (TCP ou R-UDP).")
    p.add_argument("--mode", choices=("tcp", "rudp"), required=True)
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--www", default="/app/www")
    p.add_argument("--rudp-timeout", type=float, default=0.5)
    args = p.parse_args()

    matricula, nome = require_identity()
    target_dir = os.environ.get("RESULTS_DIR") or ("/data" if os.path.isdir("/data") else "results")
    os.makedirs(target_dir, exist_ok=True)
    log_path = os.path.join(target_dir, "transfers.log")
    logger = logging.getLogger("transfers")
    if not logger.handlers:
        fh = logging.FileHandler(log_path)
        fh.setFormatter(logging.Formatter("%(message)s"))
        logger.setLevel(logging.INFO)
        logger.addHandler(fh)

    def on_request(nbytes: int, status: int) -> None:
        logger.info(
            json.dumps(
                {
                    "ts": time.time(),
                    "mode": args.mode,
                    "role": "server",
                    "event": "served",
                    "bytes_sent": nbytes,
                    "status": status,
                }
            )
        )

    logger.info(
        json.dumps(
            {
                "ts": time.time(),
                "mode": args.mode,
                "role": "server",
                "event": "start",
                "peer": f"{args.host}:{args.port}",
                "www": args.www,
            }
        )
    )

    if args.mode == "tcp":
        http_tcp_run_server(args.host, args.port, args.www, matricula, nome, on_request)
    else:
        http_rudp_run_server(
            args.host,
            args.port,
            args.www,
            matricula,
            nome,
            timeout_sec=args.rudp_timeout,
            on_request=on_request,
        )


if __name__ == "__main__":
    main()