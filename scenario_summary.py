"""Compact scenario summary for the prototype UI and exports."""
from __future__ import annotations
from typing import Any
import math
from analytics import as_dataframe, run_metrics
from config import PrototypeConfig


def _percentage(value) -> str:
    try:
        if value is None or math.isnan(float(value)):
            return "Not applicable"
        return f"{float(value):.1f}%"
    except (TypeError, ValueError):
        return "Not applicable"


def scenario_card(events, cfg: PrototypeConfig, label: str = "Illustrative scenario") -> dict[str, Any]:
    df = as_dataframe(events)
    if df.empty:
        raise ValueError("events are empty")
    metrics = run_metrics(df, cfg)
    last = df.iloc[-1]
    patient_mode = cfg.demand_mode == "patient_volume"
    return {
        "Scenario": label,
        "Resource": "Norepinephrine inventory",
        "Demand generation mode": "Patient-volume-driven" if patient_mode else "Request-rate-driven",
        "Simulation horizon": f"{cfg.horizon_hours:.0f} hours",
        "Initial stock": f"{cfg.initial_stock:.1f} illustrative units",
        "Final stock": f"{metrics['final_stock']:.1f} illustrative units",
        "Final resource state": str(last["resource_state"]),
        "Time-based availability": f"{metrics['availability_percentage']:.1f}%",
        "Stock-out episodes": int(metrics["stockout_count"]),
        "Unavailable duration": f"{metrics['stockout_duration_hours']:.1f} hours",
        "Unmet demand": f"{metrics['unmet_demand']:.1f} illustrative units",
        "Demand fulfilled": f"{metrics['demand_fulfilment_percentage']:.1f}%",
        "Replenishments received": int(metrics["replenishment_count"]),
        "Order pending at end": "Yes" if bool(last.get("order_pending", False)) else "No",
        "Random seed": int(cfg.seed),
        "Number of simulated patients over horizon": int(cfg.patient_volume) if patient_mode else "Not applicable",
        "Patient arrivals recorded": int(metrics["patient_arrival_count"]) if patient_mode else "Not applicable",
        "Resource requests generated": int(metrics["resource_request_count"]),
        "Patients generating a request": int(metrics["patients_generating_request_count"]) if patient_mode else "Not applicable",
        "Configured patient-to-request probability": _percentage(100.0 * cfg.patient_demand_probability) if patient_mode else "Not applicable",
        "Realised proportion of patients generating a request": _percentage(metrics["realised_patient_request_percentage"]),
    }
