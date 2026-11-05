"""Executable RO3 technical verification with traceable checks and evidence.

Passing these tests is limited software-correctness evidence, not clinical validation.
"""
from __future__ import annotations

from dataclasses import replace
import platform

import numpy as np
import pandas as pd

from analytics import as_dataframe
from config import PrototypeConfig
from core import classify_state
from data_quality import audit_event_log

TEST_VERSION = 'RPD_V5_FAULT_DETECTION_2026-10-29'


def _result(code, name, passed, evidence, expected, case='base run'):
    return {
        'test_id':code,'verification_test':name,'passed':bool(passed),
        'expected_invariant':expected,'evidence':str(evidence),'test_case':case,
        'test_suite_version':TEST_VERSION,
    }


def verify_event_log(events, cfg: PrototypeConfig) -> list[dict]:
    # Preserve recorded event order. Sorting by simulation time before V04 would
    # hide a corrupted timestamp and make chronology verification meaningless.
    df = events.copy() if isinstance(events, pd.DataFrame) else pd.DataFrame(events)
    if df.empty:
        raise ValueError('Cannot verify an empty event log')
    if 'event_index' in df.columns:
        df = df.sort_values(['event_index'], kind='stable').reset_index(drop=True)
    else:
        df = df.reset_index(drop=True)
    demand=df[df.event_type=='DEMAND']
    repl=df[df.event_type=='REPLENISHMENT_ARRIVAL']
    orders=df[df.event_type=='REORDER_INITIATED']
    out=[]
    # Transaction conservation
    f=float(demand.fulfilled_quantity.sum())
    r=float(repl.replenishment_quantity.fillna(0).sum()) if 'replenishment_quantity' in repl else 0.0
    final=float(df.iloc[-1].quantity_after)
    expected=cfg.initial_stock+r-f
    out.append(_result('V01','Inventory balance',abs(final-expected)<1e-7,
                       f'final={final:g}; initial({cfg.initial_stock:g})+received({r:g})-fulfilled({f:g})={expected:g}',
                       'Ending stock equals opening stock plus replenishment received minus demand fulfilled.'))
    out.append(_result('V02','Non-negative stock',bool((df.quantity_after >= -1e-9).all()),
                       f'lowest logged stock={df.quantity_after.min():g}', 'Inventory never falls below zero.'))
    bound=True
    if len(demand):
        bound=bool(((demand.fulfilled_quantity >= -1e-9) &
                    (demand.fulfilled_quantity <= demand.demand_quantity + 1e-9) &
                    (demand.fulfilled_quantity <= demand.quantity_before + 1e-9)).all())
    out.append(_result('V03','Fulfilment bounds',bound,f'{len(demand)} demand transactions checked',
                       'Fulfilled quantity is between zero and both requested and available quantities.'))

    chronology=bool(df.simulation_time.is_monotonic_increasing)
    # A pending order must have its configured arrival time; arrivals within the horizon
    # must match their scheduling time. Orders beyond horizon may remain pending.
    active_due=None; duplicate=False; timing_ok=True; n_due=0
    for _,row in df.iterrows():
        if row.event_type=='REORDER_INITIATED':
            if active_due is not None: duplicate=True
            due=float(row.scheduled_replenishment_time)
            if abs(due-(float(row.simulation_time)+cfg.replenishment_lead_time_hours))>1e-7:
                timing_ok=False
            active_due=due; n_due+=1
        elif row.event_type=='REPLENISHMENT_ARRIVAL':
            if active_due is None or abs(float(row.simulation_time)-active_due)>1e-7:
                timing_ok=False
            active_due=None
    out.append(_result('V04','Event chronology / lead time',chronology and timing_ok,
                       f'nondecreasing={chronology}; scheduled arrivals matched={timing_ok}; orders={n_due}',
                       'Events are time-ordered and every received replenishment matches its scheduled lead time.'))
    out.append(_result('V05','Duplicate-order suppression',not duplicate,
                       f'duplicate order while pending={duplicate}',
                       'Only one replenishment order is outstanding at a time.'))

    reorder_legal=True
    for _,row in orders.iterrows():
        if float(row.quantity_after)>cfg.reorder_threshold+1e-9:reorder_legal=False
    # Also catch failure to initiate an order after an eligible stock change.
    missing=[]
    for _,row in df[df.event_type.isin(['DEMAND','REPLENISHMENT_ARRIVAL'])].iterrows():
        if float(row.quantity_after)<=cfg.reorder_threshold+1e-9 and not bool(row.order_pending):
            later_same_time=df[(df.simulation_time==row.simulation_time) & (df.event_index>row.event_index)]
            if not (later_same_time.event_type=='REORDER_INITIATED').any():missing.append(int(row.event_index))
    out.append(_result('V06','Reorder trigger completeness',reorder_legal and len(missing)==0,
                       f'{len(orders)} orders; illegal trigger={not reorder_legal}; eligible events with no reorder={missing}',
                       'Reorders occur only at/below threshold and eligible stock changes initiate a reorder.'))

    repl_ok=True
    if len(repl):
        repl_ok=bool(((repl.quantity_after-repl.quantity_before-repl.replenishment_quantity).abs()<1e-7).all())
    out.append(_result('V07','Replenishment balance',repl_ok,f'{len(repl)} arrival(s) checked',
                       'Stock increases by exactly the received replenishment quantity.'))

    # State labels and notification consistency
    states_correct=all(str(row.resource_state)==classify_state(float(row.quantity_after),cfg.thresholds) for _,row in df.iterrows())
    out.append(_result('V08','Resource-state classification',states_correct,
                       f'{len(df)} rows inspected', 'Stock-state label agrees with the configured threshold logic.'))
    active=False; stockout_correct=True
    for _,row in df.iterrows():
        if row.event_type=='STOCKOUT_START':
            if active or row.resource_state!='UNAVAILABLE':stockout_correct=False
            active=True
        elif row.event_type=='RECOVERY':
            if not active or row.resource_state=='UNAVAILABLE':stockout_correct=False
            active=False
    out.append(_result('V09','Stock-out/recovery notifications',stockout_correct,
                       f'stockout_starts={int((df.event_type=="STOCKOUT_START").sum())}; recoveries={int((df.event_type=="RECOVERY").sum())}; stock-out pending at horizon={active}',
                       'Stock-out and recovery notifications follow the corresponding state changes.'))

    audited=audit_event_log(df)
    for code,audit_name in [('V10','Demand conservation'),('V11','Cumulative unmet equals summed demand shortfalls'),('V12','Row-wise cumulative increment')]:
        v=audited[audited.audit_check==audit_name].iloc[0]
        out.append(_result(code,audit_name,bool(v.passed),v.evidence,
                           'Demand-only transactional values and cumulative increments must reconcile.'))
    shortfall=df[df.event_type=='SHORTFALL']
    no_duplicate=shortfall.empty or bool((shortfall[['demand_quantity','fulfilled_quantity','unmet_quantity']].fillna(0).abs()<1e-9).all().all())
    out.append(_result('V13','SHORTFALL notification is nontransactional',no_duplicate,
                       f'{len(shortfall)} SHORTFALL rows; demand/fulfilled/unmet should all be zero',
                       'SHORTFALL notifications do not duplicate DEMAND transaction quantities.'))
    return out


def run_verification_suite(runner,base_cfg: PrototypeConfig|None=None) -> pd.DataFrame:
    cfg=base_cfg or PrototypeConfig()
    events=runner(cfg,scenario_id='verification_default',replication_id=1)
    results=verify_event_log(events,cfg)

    zero_cfg=replace(cfg,demand_enabled=False,initial_stock=max(cfg.initial_stock,1.0),reorder_threshold=0.0)
    zero=as_dataframe(runner(zero_cfg,scenario_id='verification_zero_demand',replication_id=1))
    okay=bool((zero.quantity_after==zero_cfg.initial_stock).all())
    results.append(_result('V14','Zero-demand/no-reorder',okay,f'initial={zero_cfg.initial_stock:g}; observed stock min/max={zero.quantity_after.min():g}/{zero.quantity_after.max():g}',
                           'With demand disabled and no reorder trigger, inventory remains constant.',case='deterministic zero-demand edge case'))

    a=as_dataframe(runner(cfg,scenario_id='verification_repro',replication_id=1))
    b=as_dataframe(runner(cfg,scenario_id='verification_repro',replication_id=1))
    results.append(_result('V15','Fixed-seed reproducibility',a.equals(b),f'config seed={cfg.seed}; byte-equivalent DataFrame={a.equals(b)}',
                           'Same code/configuration/seed yields the same event trace.',case='paired identical-seed runs'))

    # Guaranteed threshold edge case
    threshold=max(1.,float(cfg.reorder_threshold))
    tcfg=replace(cfg,initial_stock=max(0.,threshold-0.5),reorder_threshold=threshold,demand_enabled=False,
                 horizon_hours=max(cfg.horizon_hours,cfg.replenishment_lead_time_hours+1))
    trace=as_dataframe(runner(tcfg,scenario_id='verification_initial_reorder',replication_id=1))
    hits=trace[(trace.event_type=='REORDER_INITIATED') & (trace.simulation_time==0.0)]
    results.append(_result('V16','Initial-stock reorder at t=0',len(hits)==1,
                           f'{len(hits)} initial reorder event(s); opening stock={tcfg.initial_stock:g}; threshold={tcfg.reorder_threshold:g}',
                           'Initial stock at/below threshold initiates a single order immediately.',case='initial below-threshold edge case'))

    report=pd.DataFrame(results)
    report['runner_name']=getattr(runner,'__name__',runner.__class__.__name__)
    report['python_version']=platform.python_version()
    report['base_seed']=cfg.seed
    report['base_horizon_hours']=cfg.horizon_hours
    report['evidence_status']='ILLUSTRATIVE PARAMETERS — SOFTWARE VERIFICATION ONLY'
    return report
