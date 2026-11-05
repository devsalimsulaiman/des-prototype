"""Positive control and isolated mutation tests for audit/fault detection."""
import pandas as pd
import pytest

from config import PrototypeConfig
from data_quality import audit_event_log
from failure_detection import build_mutation_cases
from reference_scheduler import run_reference
from verification import run_verification_suite, verify_event_log


@pytest.fixture(scope='module')
def valid_event_log():
    # Deliberately dense synthetic trace exercises DEMAND, SHORTFALL, reorder,
    # replenishment, and end-of-horizon events. These are test values only.
    cfg = PrototypeConfig(
        initial_stock=100.0,
        reorder_threshold=30.0,
        replenishment_quantity=80.0,
        replenishment_lead_time_hours=24.0,
        horizon_hours=168.0,
        seed=20261008,
        demand_mode='patient_volume',
        patient_volume=100,
        patient_demand_probability=1.0,
    )
    events = pd.DataFrame(run_reference(cfg, scenario_id='mutation_test_valid_control', replication_id=1))
    return cfg, events


def test_valid_event_log_is_positive_control_and_all_v01_v16_pass(valid_event_log):
    cfg, events = valid_event_log
    audit = audit_event_log(events)
    checks = run_verification_suite(run_reference, cfg)
    assert audit['passed'].all(), audit.to_string(index=False)
    assert len(checks) == 16
    assert checks['passed'].all(), checks.to_string(index=False)
    assert (events['event_type'] == 'DEMAND').any()
    assert (events['event_type'] == 'REPLENISHMENT_ARRIVAL').any()


@pytest.mark.parametrize(
    'mutation_id',
    ['M01', 'M02', 'M03', 'M04', 'M05'],
    ids=[
        'fulfilled-greater-than-requested',
        'unmet-does-not-equal-request-minus-fulfilled',
        'cumulative-unmet-does-not-reconcile',
        'replenishment-arrives-before-scheduled-time',
        'duplicate-reorder-while-pending',
    ],
)
def test_controlled_mutation_is_detected_on_copy(mutation_id, valid_event_log):
    cfg, valid = valid_event_log
    original = valid.copy(deep=True)
    case = next(c for c in build_mutation_cases(valid) if c.mutation_id == mutation_id)
    mutated = case.mutate(valid)

    # The test must not modify the valid baseline object.
    assert valid.equals(original)

    audit = audit_event_log(mutated)
    verification = pd.DataFrame(verify_event_log(mutated, cfg))
    failed_audit = set(audit.loc[~audit['passed'], 'audit_check'].astype(str))
    failed_ids = set(verification.loc[~verification['passed'], 'test_id'].astype(str))

    audit_detected = any(name in failed_audit for name in case.expected_audit_checks)
    verification_detected = any(code in failed_ids for code in case.expected_verification_ids)
    assert audit_detected or verification_detected, (
        f'{case.description}\nExpected audit checks: {case.expected_audit_checks}\n'
        f'Expected verification IDs: {case.expected_verification_ids}\n'
        f'Audit report:\n{audit.to_string(index=False)}\n'
        f'Verification report:\n{verification.to_string(index=False)}'
    )
    assert valid.equals(original), 'The valid baseline event log was modified by the mutation test.'
