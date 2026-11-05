"""Logic-equivalent scheduler used for offline testing when SimPy is unavailable.

The RPD GUI is intended to run the SimPy engine. This module mirrors the event logic so
core analytics and verification can be exercised in constrained development environments.
"""
from __future__ import annotations

import heapq
import itertools
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from config import PrototypeConfig
from core import apply_replenishment, classify_state, fulfil_demand, should_reorder


def run_reference(cfg=None, scenario_id="illustrative_baseline", replication_id=1):
    """Run a heap-based reference implementation for both demand modes.

    The patient-volume path deliberately mirrors the SimPy generator's random-draw
    sequence: sample/sort the full arrival-time vector first, then make the request
    decision and (if applicable) sample quantity at each patient arrival.
    """
    cfg = cfg or PrototypeConfig()
    cfg.validate()
    rng = np.random.default_rng(cfg.seed)
    stock = float(cfg.initial_stock)
    pending = False
    unmet_total = 0.0
    rows = []
    q = []
    counter = itertools.count()
    event_index = 0

    def state():
        return classify_state(stock, cfg.thresholds)

    def log(t, event, demand=0.0, fulfilled=0.0, unmet=0.0, **extra):
        nonlocal event_index
        row = {
            "event_index": event_index,
            "simulation_time": float(t),
            "scenario_id": scenario_id,
            "replication_id": int(replication_id),
            "random_seed": int(cfg.seed),
            "demand_mode": cfg.demand_mode,
            "patient_volume": int(cfg.patient_volume) if cfg.demand_mode == "patient_volume" else None,
            "patient_demand_probability": float(cfg.patient_demand_probability) if cfg.demand_mode == "patient_volume" else None,
            "configured_horizon_hours": float(cfg.horizon_hours),
            "event_type": event,
            "quantity_after": float(stock),
            "resource_state": state(),
            "demand_quantity": float(demand),
            "fulfilled_quantity": float(fulfilled),
            "unmet_quantity": float(unmet),
            "cumulative_unmet": float(unmet_total),
            "order_pending": bool(pending),
        }
        row.update(extra)
        rows.append(row)
        event_index += 1

    def log_state_change(t, before_state, after_state, patient_id=None):
        if before_state != after_state:
            extra = {"patient_id": patient_id} if patient_id is not None else {}
            log(t, "STATE_CHANGE", state_before=before_state, state_after=after_state, **extra)

    def push(t, kind, payload=None):
        heapq.heappush(q, (float(t), next(counter), kind, payload))

    def schedule_replenishment(t, patient_id=None):
        nonlocal pending
        pending = True
        extra = {"patient_id": patient_id} if patient_id is not None else {}
        due = float(t) + cfg.replenishment_lead_time_hours
        log(t, "REORDER_INITIATED", reorder_threshold=cfg.reorder_threshold,
            scheduled_replenishment_time=due, **extra)
        push(due, "replenishment")

    def process_demand(t, demand, patient_id=None):
        nonlocal stock, unmet_total
        before_stock = stock
        before_state = state()
        fulfilled, unmet, stock = fulfil_demand(stock, float(demand), cfg.allow_partial_fulfilment)
        unmet_total += unmet
        after_state = state()
        extra = {"patient_id": patient_id} if patient_id is not None else {}
        demand_idx = event_index
        log(t, "DEMAND", float(demand), fulfilled, unmet,
            quantity_before=before_stock, quantity_after=stock,
            state_before=before_state, state_after=after_state, **extra)
        log_state_change(t, before_state, after_state, patient_id=patient_id)
        if unmet > 0:
            log(t, "SHORTFALL", 0.0, 0.0, 0.0,
                related_demand_event_index=demand_idx,
                shortfall_reference_quantity=float(unmet), **extra)
        if before_state != "UNAVAILABLE" and after_state == "UNAVAILABLE":
            log(t, "STOCKOUT_START", **extra)
        if should_reorder(stock, cfg.reorder_threshold, pending):
            schedule_replenishment(t, patient_id=patient_id)

    # Initial state and t=0 reorder match the SimPy model's constructor.
    log(0.0, "INITIALISE")
    if should_reorder(stock, cfg.reorder_threshold, pending):
        schedule_replenishment(0.0)

    if cfg.demand_enabled:
        if cfg.demand_mode == "patient_volume":
            horizon = float(cfg.horizon_hours)
            arrival_times = np.sort(rng.uniform(0.0, horizon, size=int(cfg.patient_volume)))
            for number, arrival_time in enumerate(arrival_times, start=1):
                push(float(arrival_time), "patient_arrival", f"P{number:05d}")
        else:
            push(float(rng.exponential(cfg.mean_interarrival_hours)), "demand")

    while q:
        t, _, kind, payload = heapq.heappop(q)
        # SimPy env.run(until=horizon) excludes events scheduled at the horizon.
        if t >= cfg.horizon_hours:
            break

        if kind == "patient_arrival":
            patient_id = str(payload)
            log(t, "PATIENT_ARRIVAL", patient_id=patient_id)
            if rng.random() >= cfg.patient_demand_probability:
                log(t, "NO_RESOURCE_REQUEST", patient_id=patient_id)
                continue
            demand = float(rng.choice(cfg.demand_values, p=cfg.demand_probabilities))
            process_demand(t, demand, patient_id=patient_id)

        elif kind == "demand":
            demand = float(rng.choice(cfg.demand_values, p=cfg.demand_probabilities))
            process_demand(t, demand)
            push(t + float(rng.exponential(cfg.mean_interarrival_hours)), "demand")

        else:  # replenishment
            before_stock = stock
            before_state = state()
            stock = apply_replenishment(stock, cfg.replenishment_quantity)
            pending = False
            after_state = state()
            log(t, "REPLENISHMENT_ARRIVAL",
                replenishment_quantity=cfg.replenishment_quantity,
                quantity_before=before_stock, quantity_after=stock,
                state_before=before_state, state_after=after_state)
            log_state_change(t, before_state, after_state)
            if before_state == "UNAVAILABLE" and after_state != "UNAVAILABLE":
                log(t, "RECOVERY")
            if should_reorder(stock, cfg.reorder_threshold, pending):
                schedule_replenishment(t)

    log(cfg.horizon_hours, "END")
    return pd.DataFrame(rows)


if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    out = root / "outputs"
    out.mkdir(exist_ok=True)
    df = run_reference()
    df.to_csv(out / "illustrative_reference_event_log.csv", index=False)

    plt.figure(figsize=(9, 4.8))
    plt.step(df["simulation_time"], df["quantity_after"], where="post")
    plt.xlabel("Simulation time (hours)")
    plt.ylabel("Illustrative inventory units")
    plt.title("Preliminary norepinephrine inventory feasibility run (illustrative values only)")
    plt.tight_layout()
    plt.savefig(out / "illustrative_inventory_trajectory.png", dpi=180)
    print(df.tail(15).to_string(index=False))
