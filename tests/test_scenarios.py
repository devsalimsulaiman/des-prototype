from config import PrototypeConfig
from scenarios import (
    comparison_baseline_config,
    mode_specific_preset_adjustments,
    scenario_config,
)


def test_increased_demand_mode_switch_adjustments_are_mode_specific():
    patient = mode_specific_preset_adjustments("Increased demand", "patient_volume")
    rate = mode_specific_preset_adjustments("Increased demand", "rate")
    assert patient == {"patient_demand_probability": 1.0}
    assert rate == {"mean_interarrival_hours": 3.0}
    assert mode_specific_preset_adjustments("Delayed replenishment", "patient_volume") == {}


def test_comparison_restores_delayed_replenishment_axis_and_preserves_workload():
    base = PrototypeConfig(demand_mode="patient_volume", patient_volume=125, horizon_hours=96.0)
    active = scenario_config("Delayed replenishment", base)
    restored = comparison_baseline_config(active, "Delayed replenishment")
    assert active.replenishment_lead_time_hours == 48.0
    assert restored.replenishment_lead_time_hours == 24.0
    assert restored.patient_volume == 125
    assert restored.horizon_hours == 96.0


def test_comparison_restores_increased_demand_axis_in_both_modes():
    base_patient = PrototypeConfig(demand_mode="patient_volume", patient_volume=100, patient_demand_probability=0.5)
    stress_patient = scenario_config("Increased demand", base_patient)
    restored_patient = comparison_baseline_config(stress_patient, "Increased demand")
    assert stress_patient.patient_demand_probability == 1.0
    assert restored_patient.patient_demand_probability == 0.5

    base_rate = PrototypeConfig(demand_mode="rate", mean_interarrival_hours=6.0)
    stress_rate = scenario_config("Increased demand", base_rate)
    restored_rate = comparison_baseline_config(stress_rate, "Increased demand")
    assert stress_rate.mean_interarrival_hours == 3.0
    assert restored_rate.mean_interarrival_hours == 6.0


def test_comparison_restores_reduced_stock_axis_and_preserves_other_settings():
    base = PrototypeConfig(patient_volume=130, horizon_hours=144.0, initial_stock=100.0, replenishment_lead_time_hours=12.0)
    stress = scenario_config("Reduced initial stock", base)
    restored = comparison_baseline_config(stress, "Reduced initial stock")
    assert stress.initial_stock == 60.0
    assert restored.initial_stock == 100.0
    assert restored.patient_volume == 130
    assert restored.horizon_hours == 144.0
    assert restored.replenishment_lead_time_hours == 12.0
