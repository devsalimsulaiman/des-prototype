from core import InventoryThresholds, apply_replenishment, classify_state, fulfil_demand, should_reorder


def test_partial_fulfilment_never_negative():
    f, u, q = fulfil_demand(5, 8, allow_partial=True)
    assert (f, u, q) == (5, 3, 0)


def test_all_or_none_fulfilment():
    f, u, q = fulfil_demand(5, 8, allow_partial=False)
    assert (f, u, q) == (0, 8, 5)


def test_state_boundaries():
    th = InventoryThresholds(low=40, critical=15)
    assert classify_state(50, th) == "AVAILABLE"
    assert classify_state(40, th) == "LOW"
    assert classify_state(15, th) == "CRITICAL"
    assert classify_state(0, th) == "UNAVAILABLE"


def test_reorder_suppression_when_pending():
    assert should_reorder(20, 30, False)
    assert not should_reorder(20, 30, True)
    assert not should_reorder(31, 30, False)


def test_replenishment_balance():
    assert apply_replenishment(12, 80) == 92


def test_state_unavailable_for_negative_or_zero_boundary_zero_only_used_normally():
    th = InventoryThresholds(low=40, critical=15)
    assert classify_state(0, th) == "UNAVAILABLE"


def test_invalid_inputs_raise():
    import pytest
    with pytest.raises(ValueError):
        fulfil_demand(-1, 2)
    with pytest.raises(ValueError):
        apply_replenishment(1, -2)


def test_patient_volume_configuration_validation():
    from config import PrototypeConfig
    cfg = PrototypeConfig(demand_mode="patient_volume", patient_volume=100, patient_demand_probability=0.5)
    cfg.validate()
    bad = PrototypeConfig(demand_mode="patient_volume", patient_volume=-1)
    try:
        bad.validate()
    except ValueError:
        pass
    else:
        raise AssertionError("negative patient volume should be rejected")
