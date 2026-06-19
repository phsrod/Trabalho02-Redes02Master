#!/bin/bash
# Gera arquivos estáticos de benchmark em www/files/
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIR="$ROOT/www/files"
mkdir -p "$DIR"

dd if=/dev/urandom of="$DIR/test_100k.bin" bs=1024 count=100 status=none 2>/dev/null \
  || dd if=/dev/urandom of="$DIR/test_100k.bin" bs=1024 count=100
dd if=/dev/urandom of="$DIR/test_500k.bin" bs=1024 count=500 status=none 2>/dev/null \
  || dd if=/dev/urandom of="$DIR/test_500k.bin" bs=1024 count=500
dd if=/dev/urandom of="$DIR/test_1m.bin" bs=1M count=1 status=none 2>/dev/null \
  || dd if=/dev/urandom of="$DIR/test_1m.bin" bs=1M count=1

echo "Arquivos gerados em $DIR"
