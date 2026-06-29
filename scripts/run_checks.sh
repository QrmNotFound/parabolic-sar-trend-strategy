#!/usr/bin/env bash
set -euo pipefail

PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_sar_*.py'
PYTHONPATH=src python3 -m sar_project.pipeline all --offline-ok
