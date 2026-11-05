"""Illustrative RPD scenario presets.

These presets are experimental demonstration conditions only. They are NOT estimates
of real-world prevalence or hospital-specific behaviour.
"""
from dataclasses import replace
from config import PrototypeConfig


SCENARIO_DESCRIPTIONS = {
    "Illustrative baseline": "Default feasibility configuration using illustrative values.",
    "Delayed replenishment": "Doubles the replenishment lead time from the current base setting.",
    "Increased demand": "Halves mean request interarrival in rate mode, or doubles patient-to-request probability (capped at 1.0) in patient-volume mode.",
    "Reduced initial stock": "Reduces initial stock by 40% from the current base setting.",
}


def scenario_config(name: str, base: PrototypeConfig | None = None) -> PrototypeConfig:
    cfg = base or PrototypeConfig()
    if name == "Illustrative baseline":
        return replace(cfg)
    if name == "Delayed replenishment":
        return replace(cfg, replenishment_lead_time_hours=cfg.replenishment_lead_time_hours * 2.0)
    if name == "Increased demand":
        if cfg.demand_mode == "patient_volume":
            return replace(cfg, patient_demand_probability=min(1.0, cfg.patient_demand_probability * 2.0))
        return replace(cfg, mean_interarrival_hours=max(0.01, cfg.mean_interarrival_hours / 2.0))
    if name == "Reduced initial stock":
        return replace(cfg, initial_stock=cfg.initial_stock * 0.6)
    raise ValueError(f"Unknown scenario: {name}")


def scenario_id(name: str) -> str:
    return name.lower().replace(" ", "_").replace("-", "_")


def comparison_baseline_config(current: PrototypeConfig, active_preset: str) -> PrototypeConfig:
    """Restore the active sidebar preset's perturbed field before a second comparison.

    Other current user-adjusted fields (including patient volume and horizon) are
    carried forward. This prevents a pre-selected stress preset from accidentally
    becoming the baseline for a second stress comparison. To use a custom value for
    the field being compared, select Illustrative baseline first and edit that value.
    """
    base = replace(current)
    defaults = PrototypeConfig(
        demand_mode=current.demand_mode,
        patient_volume=current.patient_volume,
        horizon_hours=current.horizon_hours,
        seed=current.seed,
    )
    if active_preset == "Delayed replenishment":
        base.replenishment_lead_time_hours = defaults.replenishment_lead_time_hours
    elif active_preset == "Increased demand":
        if current.demand_mode == "patient_volume":
            base.patient_demand_probability = defaults.patient_demand_probability
        else:
            base.mean_interarrival_hours = defaults.mean_interarrival_hours
    elif active_preset == "Reduced initial stock":
        base.initial_stock = defaults.initial_stock
    return base


def mode_specific_preset_adjustments(name: str, demand_mode: str) -> dict[str, float]:
    """Return the single mode-specific parameter changed by the Increased demand preset."""
    if name != "Increased demand":
        return {}
    defaults = PrototypeConfig()
    if demand_mode == "patient_volume":
        return {"patient_demand_probability": min(1.0, defaults.patient_demand_probability * 2.0)}
    if demand_mode == "rate":
        return {"mean_interarrival_hours": defaults.mean_interarrival_hours / 2.0}
    raise ValueError(f"Unknown demand mode: {demand_mode}")
