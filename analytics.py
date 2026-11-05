from __future__ import annotations

from dataclasses import replace
from math import sqrt
from statistics import NormalDist
from typing import Callable
import numpy as np
import pandas as pd

from config import PrototypeConfig


def as_dataframe(events) -> pd.DataFrame:
    if isinstance(events, pd.DataFrame):
        df = events.copy()
    else:
        df = pd.DataFrame(events)
    if df.empty:
        return df
    return df.sort_values(["simulation_time", "event_index"], kind="stable").reset_index(drop=True)


def state_duration_table(events, horizon_hours: float | None = None) -> pd.DataFrame:
    df = as_dataframe(events)
    if df.empty:
        return pd.DataFrame(columns=["resource_state", "duration_hours"])

    # The last logged row at each timestamp defines the state that persists until the next timestamp.
    snap = df.groupby("simulation_time", sort=True, as_index=False).tail(1)
    snap = snap.sort_values("simulation_time").reset_index(drop=True)
    horizon = float(horizon_hours if horizon_hours is not None else snap["simulation_time"].max())
    if snap.iloc[-1]["simulation_time"] < horizon:
        extra = snap.iloc[[-1]].copy()
        extra["simulation_time"] = horizon
        snap = pd.concat([snap, extra], ignore_index=True)

    snap["next_time"] = snap["simulation_time"].shift(-1)
    snap["duration_hours"] = (snap["next_time"] - snap["simulation_time"]).fillna(0.0).clip(lower=0.0)
    out = snap.groupby("resource_state", as_index=False)["duration_hours"].sum()
    return out


def run_metrics(events, cfg: PrototypeConfig) -> dict:
    df = as_dataframe(events)
    if df.empty:
        raise ValueError("events are empty")

    demand = df[df["event_type"] == "DEMAND"]
    state_durations = state_duration_table(df, cfg.horizon_hours)
    duration_map = dict(zip(state_durations["resource_state"], state_durations["duration_hours"]))
    unavailable_hours = float(duration_map.get("UNAVAILABLE", 0.0))
    horizon = float(cfg.horizon_hours)

    total_demand = float(demand["demand_quantity"].sum()) if not demand.empty else 0.0
    total_fulfilled = float(demand["fulfilled_quantity"].sum()) if not demand.empty else 0.0
    total_unmet = float(demand["unmet_quantity"].sum()) if not demand.empty else 0.0

    stockout_events = df[df["event_type"] == "STOCKOUT_START"]
    first_stockout = float(stockout_events["simulation_time"].iloc[0]) if len(stockout_events) else np.nan

    demand_mode = str(getattr(cfg, "demand_mode", "rate"))
    patient_arrival_count = int((df["event_type"] == "PATIENT_ARRIVAL").sum())
    if "patient_id" in demand.columns:
        patients_generating_request_count = int(demand["patient_id"].dropna().astype(str).nunique())
    else:
        patients_generating_request_count = 0
    if demand_mode == "patient_volume" and patient_arrival_count > 0:
        realised_patient_request_proportion = patients_generating_request_count / patient_arrival_count
        realised_patient_request_percentage = 100.0 * realised_patient_request_proportion
    else:
        realised_patient_request_proportion = np.nan
        realised_patient_request_percentage = np.nan

    result = {
        "availability_percentage": 100.0 * max(0.0, horizon - unavailable_hours) / horizon,
        "stockout_occurred": bool(len(stockout_events) > 0),
        "stockout_count": int(len(stockout_events)),
        "stockout_duration_hours": unavailable_hours,
        "unmet_demand": total_unmet,
        "time_to_first_stockout_hours": first_stockout,
        "replenishment_count": int((df["event_type"] == "REPLENISHMENT_ARRIVAL").sum()),
        "demand_event_count": int(len(demand)),
        "resource_request_count": int(len(demand)),
        "demand_fulfilment_percentage": 100.0 * total_fulfilled / total_demand if total_demand > 0 else 100.0,
        "time_available_hours": float(duration_map.get("AVAILABLE", 0.0)),
        "time_low_hours": float(duration_map.get("LOW", 0.0)),
        "time_critical_hours": float(duration_map.get("CRITICAL", 0.0)),
        "time_unavailable_hours": unavailable_hours,
        "final_stock": float(df.iloc[-1]["quantity_after"]),
        # Workload-to-request reporting is applicable only in patient-volume mode.
        "demand_mode": demand_mode,
        "configured_patient_volume": int(cfg.patient_volume) if demand_mode == "patient_volume" else np.nan,
        "configured_patient_request_probability": float(cfg.patient_demand_probability) if demand_mode == "patient_volume" else np.nan,
        "patient_arrival_count": patient_arrival_count if demand_mode == "patient_volume" else np.nan,
        "patients_generating_request_count": patients_generating_request_count if demand_mode == "patient_volume" else np.nan,
        "realised_patient_request_proportion": realised_patient_request_proportion,
        "realised_patient_request_percentage": realised_patient_request_percentage,
    }
    return result


def run_replications(
    runner: Callable,
    base_config: PrototypeConfig,
    n: int = 30,
    scenario_id: str = "illustrative_baseline",
    seed_start: int | None = None,
) -> pd.DataFrame:
    if n <= 0:
        raise ValueError("n must be positive")
    start = int(base_config.seed if seed_start is None else seed_start)
    rows = []
    for i in range(n):
        cfg = replace(base_config, seed=start + i)
        events = runner(cfg, scenario_id=scenario_id, replication_id=i + 1)
        m = run_metrics(events, cfg)
        m.update({"replication_id": i + 1, "seed": cfg.seed, "scenario_id": scenario_id})
        rows.append(m)
    return pd.DataFrame(rows)


def wilson_interval(successes: int, n: int, confidence: float = 0.95) -> tuple[float, float]:
    if n <= 0:
        return (np.nan, np.nan)
    z = NormalDist().inv_cdf(0.5 + confidence / 2.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * sqrt((p * (1 - p) + z * z / (4 * n)) / n) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def replication_summary(replications: pd.DataFrame) -> pd.DataFrame:
    numeric_metrics = [
        "availability_percentage",
        "stockout_count",
        "stockout_duration_hours",
        "unmet_demand",
        "time_to_first_stockout_hours",
        "replenishment_count",
        "demand_event_count",
        "resource_request_count",
        "patient_arrival_count",
        "patients_generating_request_count",
        "realised_patient_request_percentage",
        "demand_fulfilment_percentage",
        "final_stock",
    ]
    rows = []
    for metric in numeric_metrics:
        s = pd.to_numeric(replications[metric], errors="coerce").dropna()
        if len(s) == 0:
            continue
        mean = float(s.mean())
        sd = float(s.std(ddof=1)) if len(s) > 1 else 0.0
        z = NormalDist().inv_cdf(0.975)
        se = sd / sqrt(len(s)) if len(s) > 1 else 0.0
        rows.append({
            "metric": metric,
            "n": int(len(s)),
            "mean": mean,
            "sd": sd,
            "median": float(s.median()),
            "q1": float(s.quantile(0.25)),
            "q3": float(s.quantile(0.75)),
            "mean_95ci_low": mean - z * se,
            "mean_95ci_high": mean + z * se,
        })

    n = len(replications)
    successes = int(replications["stockout_occurred"].sum()) if n else 0
    lo, hi = wilson_interval(successes, n)
    rows.append({
        "metric": "stockout_probability_percentage",
        "n": n,
        "mean": 100.0 * successes / n if n else np.nan,
        "sd": np.nan,
        "median": np.nan,
        "q1": np.nan,
        "q3": np.nan,
        "mean_95ci_low": 100.0 * lo,
        "mean_95ci_high": 100.0 * hi,
    })
    return pd.DataFrame(rows)
