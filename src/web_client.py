"""Cliente Web: resolve DNS obrigatoriamente e faz GET HTTP (TCP ou R-UDP)."""
from __future__ import annotations

import argparse
import json
import logging
import os
import time

from .config import require_identity
from .dns_client import resolve_a_record
from .http_rudp import http_rudp_get
from .http_tcp import http_tcp_get
from .metrics_log import append_csv_row, build_row, log_json_line


def main() -> None:
    p = argparse.ArgumentParser(description="Cliente Web: DNS + HTTP GET (TCP ou R-UDP).")
    p.add_argument("--mode", choices=("tcp", "rudp"), required=True)
    p.add_argument("--domain", required=True, help="Nome a resolver via DNS (sem IP direto)")
    p.add_argument("--path", default="/index.html", help="Caminho HTTP (ex.: /files/test_1mb.bin)")
    p.add_argument("--dns-host", default="dns")
    p.add_argument("--dns-port", type=int, default=53)
    p.add_argument("--http-port", type=int, default=8080)
    p.add_argument("--dns-timeout", type=float, default=2.0)
    p.add_argument("--dns-retries", type=int, default=5)
    p.add_argument("--rudp-timeout", type=float, default=0.5)
    p.add_argument("--out", default="", help="Salva corpo da resposta neste arquivo")
    p.add_argument("--csv", default="")
    p.add_argument("--jsonl", default="")
    p.add_argument("--run-id", type=int, default=0)
    p.add_argument("--scenario", default="manual")
    p.add_argument("--file-size", default="", help="Rótulo do arquivo (100k, 500k, 1m)")
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

    success = True
    error_reason = ""
    body = b""
    ip = ""
    dns_dur = 0.0
    dns_attempts = 0
    http_dur = 0.0
    nbytes = 0
    status = 0

    t_total = time.monotonic()
    try:
        ip, dns_dur, dns_attempts = resolve_a_record(
            args.dns_host,
            args.dns_port,
            args.domain,
            timeout_sec=args.dns_timeout,
            max_retries=args.dns_retries,
        )
        logger.info(
            json.dumps(
                {
                    "event": "dns_resolved",
                    "domain": args.domain,
                    "ip": ip,
                    "dns_duration_s": dns_dur,
                    "dns_attempts": dns_attempts,
                }
            )
        )

        if args.mode == "tcp":
            http_dur, nbytes, body, status = http_tcp_get(
                ip, args.http_port, args.path, args.domain, matricula, nome
            )
        else:
            http_dur, nbytes, body, status = http_rudp_get(
                ip,
                args.http_port,
                args.path,
                args.domain,
                matricula,
                nome,
                timeout_sec=args.rudp_timeout,
            )

        if status != 200:
            raise SystemExit(f"HTTP {status} para {args.path}")

        if args.out:
            os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
            with open(args.out, "wb") as f:
                f.write(body)

    except BaseException as exc:
        success = False
        if isinstance(exc, SystemExit):
            error_reason = str(exc) if str(exc) else "exit"
        else:
            error_reason = type(exc).__name__
            if str(exc):
                error_reason += ": " + str(exc)

    total_dur = time.monotonic() - t_total

    row = build_row(
        run_id=args.run_id,
        scenario=args.scenario,
        mode=args.mode,
        duration_sec=total_dur,
        bytes_file=len(body),
        role="client",
        dns_duration_sec=dns_dur,
        http_duration_sec=http_dur,
        dns_attempts=dns_attempts,
        file_size=args.file_size or args.path,
        domain=args.domain,
        success=int(success),
        error_reason=error_reason,
    )

    if success:
        print(
            f"OK domain={args.domain} ip={ip} status={status} bytes={len(body)} "
            f"dns_s={dns_dur:.4f} http_s={http_dur:.4f} total_s={total_dur:.4f} "
            f"throughput_mbps={row['throughput_mbps']}"
        )
    else:
        print(f"FAIL domain={args.domain} run_id={args.run_id} reason={error_reason} total_s={total_dur:.4f}")

    if args.csv:
        append_csv_row(args.csv, row)
    if args.jsonl:
        log_json_line(args.jsonl, row)

    if success:
        logger.info(
            json.dumps(
                {
                    "event": "http_done",
                    "mode": args.mode,
                    "status": status,
                    "bytes_body": len(body),
                    "dns_duration_s": dns_dur,
                    "http_duration_s": http_dur,
                    "total_duration_s": total_dur,
                }
            )
        )
    else:
        logger.info(
            json.dumps(
                {
                    "event": "http_failed",
                    "mode": args.mode,
                    "error": error_reason,
                    "dns_duration_s": dns_dur,
                    "http_duration_s": http_dur,
                    "total_duration_s": total_dur,
                }
            )
        )
        sys.exit(1)


if __name__ == "__main__":
    main()