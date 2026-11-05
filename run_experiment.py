"""Optional command-line prototype run with transaction-safe exports."""
from datetime import datetime
from pathlib import Path
import pandas as pd

from analytics import as_dataframe, replication_summary, run_metrics, run_replications
from config import PrototypeConfig
from data_quality import annotated_event_log, audit_event_log, metadata_table
from model_simpy import run
from verification import run_verification_suite

OUT=Path(__file__).resolve().parent/'outputs'
OUT.mkdir(exist_ok=True)

if __name__=='__main__':
    cfg=PrototypeConfig()
    raw=as_dataframe(run(cfg,scenario_id='illustrative_baseline',replication_id=1))
    origin=datetime(2026,10,12,0,0) # display anchor, not a real hospital timestamp
    annotated_event_log(raw,origin).to_csv(OUT/'cli_baseline_readable_event_log.csv',index=False,encoding='utf-8-sig')
    audit_event_log(raw).to_csv(OUT/'cli_baseline_log_audit.csv',index=False,encoding='utf-8-sig')
    metadata_table(cfg,'Illustrative baseline',origin).to_csv(OUT/'cli_baseline_parameter_snapshot.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame([run_metrics(raw,cfg)]).to_csv(OUT/'cli_baseline_metrics.csv',index=False,encoding='utf-8-sig')
    reps=run_replications(run,cfg,n=30,scenario_id='illustrative_baseline')
    reps.to_csv(OUT/'cli_baseline_30_replications.csv',index=False,encoding='utf-8-sig')
    replication_summary(reps).to_csv(OUT/'cli_baseline_30_replication_summary.csv',index=False,encoding='utf-8-sig')
    report=run_verification_suite(run,cfg)
    report.to_csv(OUT/'cli_baseline_verification.csv',index=False,encoding='utf-8-sig')
    print(f'Core checks: {int(report.passed.sum())}/{len(report)} passed')
    print('Unmet demand (demand transactions):',run_metrics(raw,cfg)['unmet_demand'])
    print('Outputs:',OUT)
