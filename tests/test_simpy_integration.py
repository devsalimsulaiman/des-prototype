import pytest
pytest.importorskip("simpy")

import pandas as pd

from analytics import run_metrics
from config import PrototypeConfig
from data_quality import annotated_event_log, audit_event_log
from model_simpy import run as run_simpy
from reference_scheduler import run_reference
from scenario_summary import scenario_card
from scenarios import scenario_config
from verification import run_verification_suite


def test_simpy_verification_suite_passes_in_rate_mode():
    cfg = PrototypeConfig(demand_mode="rate", horizon_hours=168.0)
    checks = run_verification_suite(run_simpy, cfg)
    assert checks.passed.all(), checks.to_string(index=False)


def test_simpy_and_reference_traces_match_in_request_rate_mode():
    cfg = PrototypeConfig(demand_mode="rate", horizon_hours=168.0, seed=20261008)
    simpy_df = pd.DataFrame(run_simpy(cfg, scenario_id="rate_crosscheck", replication_id=1))
    reference_df = run_reference(cfg, scenario_id="rate_crosscheck", replication_id=1)
    pd.testing.assert_frame_equal(simpy_df, reference_df, check_dtype=False)


def test_patient_volume_generates_exact_patient_count_and_valid_arrivals():
    cfg = PrototypeConfig(
        demand_mode="patient_volume", patient_volume=100,
        patient_demand_probability=0.5, horizon_hours=168.0, seed=20261008,
    )
    df = pd.DataFrame(run_simpy(cfg, scenario_id="pv_integration"))
    arrivals = df[df.event_type == "PATIENT_ARRIVAL"]
    demand = df[df.event_type == "DEMAND"]
    assert len(arrivals) == cfg.patient_volume
    assert arrivals.patient_id.nunique() == cfg.patient_volume
    assert arrivals.simulation_time.ge(0).all()
    assert arrivals.simulation_time.lt(cfg.horizon_hours).all()
    assert len(demand) <= cfg.patient_volume
    assert demand.patient_id.notna().all()
    assert demand.patient_id.nunique() == len(demand)  # one request at most per patient
    assert set(df[df.event_type == "NO_RESOURCE_REQUEST"].patient_id).isdisjoint(set(demand.patient_id))
    assert audit_event_log(df).passed.all()


def test_probability_zero_produces_no_requests_but_all_arrivals():
    cfg = PrototypeConfig(
        demand_mode="patient_volume", patient_volume=25,
        patient_demand_probability=0.0, horizon_hours=72.0, seed=1234,
    )
    df = pd.DataFrame(run_simpy(cfg))
    assert (df.event_type == "PATIENT_ARRIVAL").sum() == 25
    assert (df.event_type == "NO_RESOURCE_REQUEST").sum() == 25
    assert (df.event_type == "DEMAND").sum() == 0


def test_probability_one_gives_one_request_per_patient():
    cfg = PrototypeConfig(
        demand_mode="patient_volume", patient_volume=10,
        patient_demand_probability=1.0, horizon_hours=48.0, seed=1234,
    )
    df = pd.DataFrame(run_simpy(cfg))
    arrivals = df[df.event_type == "PATIENT_ARRIVAL"]
    demand = df[df.event_type == "DEMAND"]
    assert len(arrivals) == 10
    assert len(demand) == 10
    assert demand.patient_id.nunique() == 10
    assert not (df.event_type == "NO_RESOURCE_REQUEST").any()


@pytest.mark.parametrize("volume,probability,horizon", [(100, 0.5, 168.0), (50, 1.0, 48.0), (50, 0.0, 48.0), (0, 0.5, 48.0)])
def test_patient_volume_simpy_and_reference_traces_match(volume, probability, horizon):
    cfg = PrototypeConfig(
        demand_mode="patient_volume", patient_volume=volume,
        patient_demand_probability=probability, horizon_hours=horizon, seed=20261008,
    )
    simpy_df = pd.DataFrame(run_simpy(cfg, scenario_id="crosscheck", replication_id=1))
    reference_df = run_reference(cfg, scenario_id="crosscheck", replication_id=1)
    pd.testing.assert_frame_equal(simpy_df, reference_df, check_dtype=False)


def test_patient_volume_metrics_and_summary_expose_workload_to_request_link():
    cfg = PrototypeConfig(
        demand_mode="patient_volume", patient_volume=100,
        patient_demand_probability=0.5, horizon_hours=168.0, seed=20261008,
    )
    df = pd.DataFrame(run_simpy(cfg, scenario_id="summary_test"))
    metrics = run_metrics(df, cfg)
    arrivals = int((df.event_type == "PATIENT_ARRIVAL").sum())
    requests = int((df.event_type == "DEMAND").sum())
    requesting_patients = int(df.loc[df.event_type == "DEMAND", "patient_id"].nunique())
    assert metrics["configured_patient_volume"] == 100
    assert metrics["patient_arrival_count"] == arrivals == 100
    assert metrics["resource_request_count"] == requests
    assert metrics["patients_generating_request_count"] == requesting_patients
    assert metrics["realised_patient_request_proportion"] == pytest.approx(requesting_patients / arrivals)
    card = scenario_card(df, cfg, label="Patient-volume test")
    assert card["Number of simulated patients over horizon"] == 100
    assert card["Patient arrivals recorded"] == 100
    assert card["Resource requests generated"] == requests
    assert card["Patients generating a request"] == requesting_patients
    assert card["Realised proportion of patients generating a request"].endswith("%")
    view = annotated_event_log(df)
    assert "SYNTHETIC WORKLOAD ARRIVAL; NOT A CLINICAL RECORD" in set(view.event_semantics)
    assert "PATIENT ARRIVAL WITHOUT A RESOURCE REQUEST" in set(view.event_semantics)


def test_zero_patient_volume_reports_proportion_as_not_applicable():
    cfg = PrototypeConfig(demand_mode="patient_volume", patient_volume=0, horizon_hours=24.0)
    df = pd.DataFrame(run_simpy(cfg))
    metrics = run_metrics(df, cfg)
    assert metrics["patient_arrival_count"] == 0
    assert pd.isna(metrics["realised_patient_request_proportion"])
    card = scenario_card(df, cfg)
    assert card["Realised proportion of patients generating a request"] == "Not applicable"


def test_patient_volume_verification_suite_passes():
    cfg = PrototypeConfig(
        demand_mode="patient_volume", patient_volume=100,
        patient_demand_probability=0.5, horizon_hours=168.0, seed=20261008,
    )
    checks = run_verification_suite(run_simpy, cfg)
    assert checks.passed.all(), checks.to_string(index=False)
