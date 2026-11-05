from dataclasses import replace

from config import PrototypeConfig
from reference_scheduler import run_reference
from verification import run_verification_suite


def test_fixed_seed_reference_reproducible():
    cfg = PrototypeConfig(horizon_hours=72.0)
    a = run_reference(cfg)
    b = run_reference(cfg)
    assert a.equals(b)


def test_zero_demand_case_unchanged_when_reorder_not_triggered():
    cfg = PrototypeConfig(horizon_hours=24.0, demand_enabled=False, reorder_threshold=0.0)
    df = run_reference(cfg)
    assert (df.quantity_after == cfg.initial_stock).all()


def test_initial_reorder_when_starting_below_threshold():
    cfg = PrototypeConfig(
        initial_stock=20.0,
        reorder_threshold=30.0,
        replenishment_quantity=80.0,
        replenishment_lead_time_hours=4.0,
        horizon_hours=12.0,
        demand_enabled=False,
    )
    df = run_reference(cfg)
    t0 = df[(df.event_type == "REORDER_INITIATED") & (df.simulation_time == 0.0)]
    assert len(t0) == 1
    assert (df.event_type == "REPLENISHMENT_ARRIVAL").any()


def test_verification_suite_passes_reference_engine():
    cfg = PrototypeConfig(horizon_hours=168.0)
    checks = run_verification_suite(run_reference, cfg)
    assert checks.passed.all(), checks.to_string(index=False)
