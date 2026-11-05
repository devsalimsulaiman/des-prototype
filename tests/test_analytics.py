from config import PrototypeConfig
from reference_scheduler import run_reference
from analytics import run_metrics, run_replications, replication_summary, state_duration_table


def test_state_durations_sum_to_horizon():
    cfg = PrototypeConfig(horizon_hours=48.0)
    df = run_reference(cfg)
    dur = state_duration_table(df, cfg.horizon_hours)
    assert abs(dur.duration_hours.sum() - cfg.horizon_hours) < 1e-9


def test_metrics_are_bounded_and_balance_like():
    cfg = PrototypeConfig(horizon_hours=72.0)
    df = run_reference(cfg)
    m = run_metrics(df, cfg)
    assert 0 <= m["availability_percentage"] <= 100
    assert 0 <= m["demand_fulfilment_percentage"] <= 100
    assert m["unmet_demand"] >= 0
    assert m["stockout_duration_hours"] >= 0


def test_replication_output_and_summary():
    cfg = PrototypeConfig(horizon_hours=24.0)
    reps = run_replications(run_reference, cfg, n=5, scenario_id="test")
    assert len(reps) == 5
    summary = replication_summary(reps)
    assert "stockout_probability_percentage" in set(summary.metric)
