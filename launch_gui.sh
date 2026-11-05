#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
if [ -f .venv/bin/activate ]; then source .venv/bin/activate; fi
python -m streamlit run app.py
