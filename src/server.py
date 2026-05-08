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
 
    if args.mode == "tcp":
        tcp_run_server(args.host, args.port, args.out_dir, matricula, nome)
    else:
        rudp_run_server(args.host, args.port, args.out_dir, matricula, nome)
 
 
if __name__ == "__main__":
    main()