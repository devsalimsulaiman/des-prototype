"""SimPy feasibility prototype for norepinephrine inventory.

All operational values are illustrative until RO1 is frozen. The engine supports
rate-driven requests and a patient-volume-driven workload mode. In patient-volume
mode, patient arrivals are workload entities, not clinical records; each may generate
at most one inventory request under an illustrative probability rule.
"""
from __future__ import annotations

from typing import Dict, List
import numpy as np
import simpy

from config import PrototypeConfig
from core import apply_replenishment, classify_state, fulfil_demand, should_reorder


class NorepinephrineInventoryDES:
    def __init__(
        self,
        env: simpy.Environment,
        config: PrototypeConfig,
        scenario_id: str = "illustrative_baseline",
        replication_id: int = 1,
    ):
        config.validate()
        self.env = env
        self.cfg = config
        self.scenario_id = scenario_id
        self.replication_id = int(replication_id)
        self.rng = np.random.default_rng(config.seed)
        self.stock = float(config.initial_stock)
        self.order_pending = False
        self.cumulative_unmet = 0.0
        self.events: List[Dict] = []
        self._event_index = 0
        self._log("INITIALISE", demand=0.0, fulfilled=0.0, unmet=0.0)

        # Evaluate reorder eligibility at t=0, before demand generation begins.
        if should_reorder(self.stock, self.cfg.reorder_threshold, self.order_pending):
            self.order_pending = True
            self._log(
                "REORDER_INITIATED",
                demand=0.0,
                fulfilled=0.0,
                unmet=0.0,
                reorder_threshold=self.cfg.reorder_threshold,
                scheduled_replenishment_time=self.env.now + self.cfg.replenishment_lead_time_hours,
            )
            self.env.process(self.replenishment_process())

    def _state(self) -> str:
        return classify_state(self.stock, self.cfg.thresholds)

    def _log(self, event_type: str, demand: float, fulfilled: float, unmet: float, **extra):
        row = {
            "event_index": self._event_index,
            "simulation_time": float(self.env.now),
            "scenario_id": self.scenario_id,
            "replication_id": self.replication_id,
            "random_seed": int(self.cfg.seed),
            "demand_mode": self.cfg.demand_mode,
            "patient_volume": int(self.cfg.patient_volume) if self.cfg.demand_mode == "patient_volume" else None,
            "patient_demand_probability": float(self.cfg.patient_demand_probability) if self.cfg.demand_mode == "patient_volume" else None,
            "configured_horizon_hours": float(self.cfg.horizon_hours),
            "event_type": event_type,
            "quantity_after": float(self.stock),
            "resource_state": self._state(),
            "demand_quantity": float(demand),
            "fulfilled_quantity": float(fulfilled),
            "unmet_quantity": float(unmet),
            "cumulative_unmet": float(self.cumulative_unmet),
            "order_pending": bool(self.order_pending),
        }
        row.update(extra)
        self.events.append(row)
        self._event_index += 1

    def _log_state_change(self, before_state: str, after_state: str, patient_id: str | None = None):
        if before_state != after_state:
            extra = {"patient_id": patient_id} if patient_id is not None else {}
            self._log(
                "STATE_CHANGE",
                demand=0.0,
                fulfilled=0.0,
                unmet=0.0,
                state_before=before_state,
                state_after=after_state,
                **extra,
            )

    def _process_demand(self, demand: float, patient_id: str | None = None):
        """Apply one primary request transaction and schedule any resulting reorder."""
        before_stock = self.stock
        before_state = self._state()
        fulfilled, unmet, self.stock = fulfil_demand(
            self.stock, float(demand), self.cfg.allow_partial_fulfilment
        )
        self.cumulative_unmet += unmet
        after_state = self._state()
        patient_extra = {"patient_id": patient_id} if patient_id is not None else {}

        demand_event_index = self._event_index
        self._log(
            "DEMAND",
            demand=float(demand),
            fulfilled=fulfilled,
            unmet=unmet,
            quantity_before=before_stock,
            quantity_after=self.stock,
            state_before=before_state,
            state_after=after_state,
            **patient_extra,
        )
        self._log_state_change(before_state, after_state, patient_id=patient_id)

        if unmet > 0:
            # SHORTFALL is a notification linked to the originating DEMAND row.
            # It has zero transaction amounts to prevent double-counting.
            self._log(
                "SHORTFALL",
                demand=0.0,
                fulfilled=0.0,
                unmet=0.0,
                related_demand_event_index=demand_event_index,
                shortfall_reference_quantity=float(unmet),
                **patient_extra,
            )
        if before_state != "UNAVAILABLE" and after_state == "UNAVAILABLE":
            self._log("STOCKOUT_START", demand=0.0, fulfilled=0.0, unmet=0.0, **patient_extra)

        if should_reorder(self.stock, self.cfg.reorder_threshold, self.order_pending):
            self.order_pending = True
            self._log(
                "REORDER_INITIATED",
                demand=0.0,
                fulfilled=0.0,
                unmet=0.0,
                reorder_threshold=self.cfg.reorder_threshold,
                scheduled_replenishment_time=self.env.now + self.cfg.replenishment_lead_time_hours,
                **patient_extra,
            )
            self.env.process(self.replenishment_process())

    def demand_generator(self):
        """Generate resource requests at stochastic interarrival times."""
        while True:
            delay = float(self.rng.exponential(self.cfg.mean_interarrival_hours))
            yield self.env.timeout(delay)
            demand = float(self.rng.choice(self.cfg.demand_values, p=self.cfg.demand_probabilities))
            self._process_demand(demand)

    def patient_volume_generator(self):
        """Generate exactly the configured patient workload over the horizon.

        Arrival times are sampled uniformly over [0, horizon). Each synthetic patient
        may generate at most one request according to patient_demand_probability. This
        is an illustrative workload-to-request rule, not a clinical utilisation estimate.
        """
        horizon = float(self.cfg.horizon_hours)
        arrival_times = np.sort(self.rng.uniform(0.0, horizon, size=int(self.cfg.patient_volume)))
        for patient_number, arrival_time in enumerate(arrival_times, start=1):
            delay = max(0.0, float(arrival_time) - float(self.env.now))
            yield self.env.timeout(delay)
            patient_id = f"P{patient_number:05d}"
            self._log("PATIENT_ARRIVAL", demand=0.0, fulfilled=0.0, unmet=0.0, patient_id=patient_id)
            if self.rng.random() >= self.cfg.patient_demand_probability:
                self._log(
                    "NO_RESOURCE_REQUEST", demand=0.0, fulfilled=0.0, unmet=0.0,
                    patient_id=patient_id,
                )
                continue
            demand = float(self.rng.choice(self.cfg.demand_values, p=self.cfg.demand_probabilities))
            self._process_demand(demand, patient_id=patient_id)

    def replenishment_process(self):
        yield self.env.timeout(self.cfg.replenishment_lead_time_hours)
        before_stock = self.stock
        before_state = self._state()
        self.stock = apply_replenishment(self.stock, self.cfg.replenishment_quantity)
        self.order_pending = False
        after_state = self._state()
        self._log(
            "REPLENISHMENT_ARRIVAL",
            demand=0.0,
            fulfilled=0.0,
            unmet=0.0,
            replenishment_quantity=self.cfg.replenishment_quantity,
            quantity_before=before_stock,
            quantity_after=self.stock,
            state_before=before_state,
            state_after=after_state,
        )
        self._log_state_change(before_state, after_state)
        if before_state == "UNAVAILABLE" and after_state != "UNAVAILABLE":
            self._log("RECOVERY", demand=0.0, fulfilled=0.0, unmet=0.0)

        if should_reorder(self.stock, self.cfg.reorder_threshold, self.order_pending):
            self.order_pending = True
            self._log(
                "REORDER_INITIATED",
                demand=0.0,
                fulfilled=0.0,
                unmet=0.0,
                reorder_threshold=self.cfg.reorder_threshold,
                scheduled_replenishment_time=self.env.now + self.cfg.replenishment_lead_time_hours,
            )
            self.env.process(self.replenishment_process())


def run(
    config: PrototypeConfig | None = None,
    scenario_id: str = "illustrative_baseline",
    replication_id: int = 1,
):
    cfg = config or PrototypeConfig()
    cfg.validate()
    env = simpy.Environment()
    model = NorepinephrineInventoryDES(env, cfg, scenario_id=scenario_id, replication_id=replication_id)
    if cfg.demand_enabled:
        if cfg.demand_mode == "patient_volume":
            env.process(model.patient_volume_generator())
        else:
            env.process(model.demand_generator())
    env.run(until=cfg.horizon_hours)
    model._log("END", demand=0.0, fulfilled=0.0, unmet=0.0)
    return model.events
