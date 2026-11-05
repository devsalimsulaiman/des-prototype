from datetime import datetime
from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

from config import PrototypeConfig
from scenarios import scenario_config
from reference_scheduler import run_reference
from data_quality import elapsed_label, annotated_event_log, audit_event_log, metadata_table
from verification import run_verification_suite, verify_event_log


def test_elapsed_hours_display_without_changing_numeric_time():
    assert elapsed_label(0) == 'Day 1, 00:00:00'
    assert elapsed_label(1.5) == 'Day 1, 01:30:00'
    assert elapsed_label(30.5) == 'Day 2, 06:30:00'
    assert elapsed_label(168) == 'Day 8, 00:00:00'  # 168 elapsed hours = 7 full days
    cfg=PrototypeConfig(horizon_hours=72)
    raw=run_reference(cfg)
    view=annotated_event_log(raw, datetime(2026,10,12,0,0))
    assert (view.simulation_time.values == raw.simulation_time.values).all()
    assert view.iloc[0].simulated_datetime == '2026-10-12 00:00:00'
    assert view.iloc[-1].simulated_datetime == '2026-10-15 00:00:00'


def test_shortfall_notifications_not_double_counted():
    cfg=scenario_config('Delayed replenishment')
    df=run_reference(cfg)
    short=df[df.event_type=='SHORTFALL']
    assert len(short)>0
    assert (short[['demand_quantity','fulfilled_quantity','unmet_quantity']]==0).all().all()
    assert (short.shortfall_reference_quantity>0).all()
    assert df.cumulative_unmet.iloc[-1] == pytest.approx(df.loc[df.event_type=='DEMAND','unmet_quantity'].sum())
    view=annotated_event_log(df)
    assert view.transaction_unmet_quantity.sum() == pytest.approx(df.cumulative_unmet.iloc[-1])
    assert view.cumulative_unmet_delta.sum() == pytest.approx(df.cumulative_unmet.iloc[-1])
    assert audit_event_log(df).passed.all()


def test_legacy_style_shortfall_row_is_not_double_counted():
    # A compact in-memory legacy log reproduces the old behavior in which a
    # SHORTFALL notification repeats values already recorded on the DEMAND row.
    raw = pd.DataFrame([
        {"event_index": 0, "simulation_time": 0.0, "event_type": "INITIALISE", "quantity_after": 10.0,
         "demand_quantity": 0.0, "fulfilled_quantity": 0.0, "unmet_quantity": 0.0, "cumulative_unmet": 0.0, "order_pending": False},
        {"event_index": 1, "simulation_time": 1.0, "event_type": "DEMAND", "quantity_before": 10.0, "quantity_after": 0.0,
         "demand_quantity": 10.0, "fulfilled_quantity": 10.0, "unmet_quantity": 0.0, "cumulative_unmet": 0.0, "order_pending": False},
        {"event_index": 2, "simulation_time": 2.0, "event_type": "DEMAND", "quantity_before": 0.0, "quantity_after": 0.0,
         "demand_quantity": 5.0, "fulfilled_quantity": 0.0, "unmet_quantity": 5.0, "cumulative_unmet": 5.0, "order_pending": False},
        {"event_index": 3, "simulation_time": 2.0, "event_type": "SHORTFALL", "quantity_after": 0.0,
         "demand_quantity": 5.0, "fulfilled_quantity": 0.0, "unmet_quantity": 5.0, "cumulative_unmet": 5.0, "order_pending": False},
        {"event_index": 4, "simulation_time": 3.0, "event_type": "END", "quantity_after": 0.0,
         "demand_quantity": 0.0, "fulfilled_quantity": 0.0, "unmet_quantity": 0.0, "cumulative_unmet": 5.0, "order_pending": False},
    ])
    corrected = annotated_event_log(raw)
    assert raw.unmet_quantity.sum() == 10.0  # naïve sum double-counts the SHORTFALL row
    assert corrected.transaction_unmet_quantity.sum() == 5.0
    assert raw.cumulative_unmet.iloc[-1] == 5.0
    assert audit_event_log(raw).passed.all()


def test_mutation_of_cumulative_unmet_fails_verification():
    cfg=scenario_config('Delayed replenishment')
    df=run_reference(cfg)
    idx=df.index[df.event_type=='DEMAND'][10]
    df.loc[idx,'cumulative_unmet']+=9
    results=verify_event_log(df,cfg)
    failures=[r['verification_test'] for r in results if not r['passed']]
    assert 'Row-wise cumulative increment' in failures


def test_wrong_stock_demand_balance_is_detected():
    cfg=PrototypeConfig()
    df=run_reference(cfg)
    idx=df.index[df.event_type=='DEMAND'][0]
    df.loc[idx,'quantity_after']+=50
    errs=audit_event_log(df)
    assert not errs.set_index('audit_check').loc['Per-demand stock decrement','passed']


def test_missing_reorder_detected_by_verification():
    cfg=PrototypeConfig()
    df=run_reference(cfg)
    idx=df.index[df.event_type=='REORDER_INITIATED'][0]
    df=df.drop(index=idx).reset_index(drop=True)
    checks=verify_event_log(df,cfg)
    assert any((not r['passed']) for r in checks)


def test_verification_trace_has_ids_and_metadata():
    cfg=PrototypeConfig(horizon_hours=48)
    report=run_verification_suite(run_reference,cfg)
    assert report.passed.all(),report.to_string(index=False)
    assert report.test_id.is_unique
    assert {'test_case','test_suite_version','runner_name','python_version','evidence_status'} <= set(report.columns)
    assert len(report)==16
