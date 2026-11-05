"""Read an event CSV and produce a non-destructive transaction-safe audit export.

Example: python audit_csv.py my_event_log.csv --start '2026-10-12 00:00:00'
"""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import pandas as pd

from data_quality import audit_event_log, annotated_event_log


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('csv_file',type=Path)
    parser.add_argument('--start',help='Optional DISPLAY-ONLY calendar origin, e.g. 2026-10-12 00:00:00')
    args=parser.parse_args()
    origin=datetime.fromisoformat(args.start) if args.start else None
    frame=pd.read_csv(args.csv_file)
    annotated=annotated_event_log(frame,origin)
    report=audit_event_log(frame)
    destination=args.csv_file.parent
    trace=destination/(args.csv_file.stem+'_annotated.csv')
    audit=destination/(args.csv_file.stem+'_audit.csv')
    annotated.to_csv(trace,index=False,encoding='utf-8-sig')
    report.to_csv(audit,index=False,encoding='utf-8-sig')
    print('Annotated CSV:',trace)
    print('Audit report:',audit)
    print(report[['audit_check','passed','evidence']].to_string(index=False))
    print('NOTE: the original CSV has not been changed. SHORTFALL rows may repeat quantities in legacy data; use transaction_unmet_quantity.')
    raise SystemExit(0 if report.passed.all() else 1)


if __name__=='__main__':main()
