#!/usr/bin/env bash
set -euo pipefail
python -m pytest -q
python -m geoclimatebench demo --data-dir data --output results
python -m geoclimatebench grade --data-dir data --output results
