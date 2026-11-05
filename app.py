"""Norepinephrine inventory DES feasibility prototype.

The Streamlit GUI is a presentation layer over the simulation, analytics,
data-quality and verification modules. All default operational values are illustrative.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from analytics import as_dataframe, replication_summary, run_metrics, run_replications, state_duration_table
from config import PrototypeConfig
from core import InventoryThresholds
from data_quality import annotated_event_log, audit_event_log, metadata_table
from scenarios import SCENARIO_DESCRIPTIONS, scenario_config, scenario_id, comparison_baseline_config, mode_specific_preset_adjustments
from scenario_summary import scenario_card
from verification import run_verification_suite

try:
    from model_simpy import run as simpy_run
except ImportError as exc:
    st.error(f"SimPy unavailable. Install requirements.txt or run setup_windows.bat. Details: {exc}")
    st.stop()

st.set_page_config(page_title="Sepsis Care Inventory DES Prototype", layout="wide")
st.title("Sepsis Care Inventory DES Prototype")
st.caption("Bounded operational-resource simulation for feasibility testing (Using Norepinephrine)")
st.warning("Illustrative prototype: current values and scenarios are demonstration inputs, not hospital measurements or clinical recommendations.")


def _set_preset_values():
    mode = st.session_state.get("demand_mode", "patient_volume")
    cfg0 = scenario_config(st.session_state.get("preset_selector", "Illustrative baseline"), base=PrototypeConfig(demand_mode=mode))
    for key, value in {
        "p_initial": float(cfg0.initial_stock),
        "p_reorder": float(cfg0.reorder_threshold),
        "p_replenishment": float(cfg0.replenishment_quantity),
        "p_lead": float(cfg0.replenishment_lead_time_hours),
        "p_interarrival": float(cfg0.mean_interarrival_hours),
        "p_low": float(cfg0.thresholds.low),
        "p_critical": float(cfg0.thresholds.critical),
        "p_horizon": float(cfg0.horizon_hours),
        "p_seed": int(cfg0.seed),
        "p_partial": bool(cfg0.allow_partial_fulfilment),
        "p_patient_volume": int(cfg0.patient_volume),
        "p_patient_probability": float(cfg0.patient_demand_probability),
    }.items():
        st.session_state[key] = value


def _on_demand_mode_change():
    """Keep the Increased demand preset aligned with the selected demand mode."""
    label = st.session_state.get("demand_mode_label", "Patient-volume-driven")
    mode = "patient_volume" if label == "Patient-volume-driven" else "rate"
    st.session_state["demand_mode"] = mode
    # The preset is a doubling of one mode-specific parameter from the illustrative
    # default: request probability in patient mode, mean interarrival in rate mode.
    # Apply only that mode-specific preset adjustment; preserve other user inputs.
    preset = st.session_state.get("preset_selector", "Illustrative baseline")
    if preset == "Increased demand":
        defaults = PrototypeConfig()
        # Restore inactive/mode-specific fields to base before applying the stress
        # transformation for the newly selected demand mode.
        st.session_state["p_patient_probability"] = defaults.patient_demand_probability
        st.session_state["p_interarrival"] = defaults.mean_interarrival_hours
    for key, value in mode_specific_preset_adjustments(preset, mode).items():
        state_key = "p_patient_probability" if key == "patient_demand_probability" else "p_interarrival"
        st.session_state[state_key] = value


if "demand_mode" not in st.session_state:
    st.session_state["demand_mode"] = "patient_volume"
if "preset_selector" not in st.session_state:
    st.session_state["preset_selector"] = "Illustrative baseline"
    _set_preset_values()

with st.sidebar:
    st.header("Simulation controls")
    preset = st.selectbox(
        "Scenario preset",
        list(SCENARIO_DESCRIPTIONS),
        key="preset_selector",
        on_change=_set_preset_values,
    )
    st.caption(SCENARIO_DESCRIPTIONS[preset])
    demand_mode_label = st.selectbox(
        "Demand-generation mode",
        ["Patient-volume-driven", "Request-rate-driven"],
        index=0 if st.session_state.get("demand_mode", "patient_volume") == "patient_volume" else 1,
        key="demand_mode_label",
        on_change=_on_demand_mode_change,
    )
    st.session_state["demand_mode"] = "patient_volume" if demand_mode_label == "Patient-volume-driven" else "rate"
    calendar_date = st.date_input("Display calendar start date", value=date(2026, 10, 12))
    calendar_time = st.time_input("Display start time", value=time(0, 0))
    origin = datetime.combine(calendar_date, calendar_time)

    with st.expander("Model parameters", expanded=False):
        initial = st.number_input("Initial stock (illustrative units)", min_value=0.0, step=5.0, key="p_initial")
        reorder = st.number_input("Reorder threshold (units)", min_value=0.0, step=5.0, key="p_reorder")
        replenish = st.number_input("Replenishment quantity (units)", min_value=0.01, step=5.0, key="p_replenishment")
        lead = st.number_input("Replenishment lead time (hours)", min_value=0.0, step=1.0, key="p_lead")
        interarrival = st.number_input("Mean demand interarrival (hours; rate-driven mode)", min_value=0.01, step=0.5, key="p_interarrival")
        patient_volume = st.number_input("Number of simulated patients over the horizon", min_value=0, max_value=100000, step=10, key="p_patient_volume", help="Exactly this many synthetic workload entities arrive during patient-volume mode. It is not a forecast of real hospital census.")
        patient_probability = st.slider("Illustrative probability a patient generates a resource request", min_value=0.0, max_value=1.0, value=0.5, step=0.05, key="p_patient_probability")
        low = st.number_input("Low-state threshold", min_value=0.0, step=5.0, key="p_low")
        critical = st.number_input("Critical-state threshold", min_value=0.0, step=5.0, key="p_critical")
        horizon = st.number_input("Simulation horizon (hours)", min_value=1.0, step=24.0, key="p_horizon")
        seed = st.number_input("Random seed", min_value=0, step=1, key="p_seed")
        partial = st.checkbox("Allow partial fulfilment", key="p_partial")
        st.caption("Illustrative demand-size distribution: 5/10/15 units with probabilities 0.3/0.5/0.2. Patient volume, request probability, horizon and scenario parameters are user-adjustable; all values remain illustrative until RO1.")

cfg = PrototypeConfig(
    initial_stock=float(initial),
    reorder_threshold=float(reorder),
    replenishment_quantity=float(replenish),
    replenishment_lead_time_hours=float(lead),
    thresholds=InventoryThresholds(low=float(low), critical=float(critical)),
    allow_partial_fulfilment=bool(partial),
    mean_interarrival_hours=float(interarrival),
    demand_values=(5.0, 10.0, 15.0),
    demand_probabilities=(0.3, 0.5, 0.2),
    horizon_hours=float(horizon),
    seed=int(seed),
    demand_mode=st.session_state["demand_mode"],
    patient_volume=int(patient_volume),
    patient_demand_probability=float(patient_probability),
)
try:
    cfg.validate()
except ValueError as exc:
    st.error(f"Configuration invalid: {exc}")
    st.stop()

with st.expander("Model boundary", expanded=False):
    st.write(
        "The prototype can generate requests either from a request rate or from a specified patient volume over the selected simulation horizon. In patient-volume mode, each patient is assigned a random arrival time and may generate at most one inventory request under an explicitly illustrative probability. "
        "The model then represents demand, fulfilment/shortfall, stock state, reorder, lead time and replenishment. "
        "The patient-to-request linkage is a provisional modelling assumption, not a clinical estimate; it must be justified or replaced through RO1 evidence. The model does not diagnose sepsis, prescribe medication, model dose titration, or simulate whole-hospital patient flow."
    )


def export_csv(df):
    return df.to_csv(index=False).encode("utf-8-sig")


def config_snapshot(config, label, display_origin):
    return metadata_table(config, label, display_origin)


def metrics_bar(metrics):
    cols = st.columns(5)
    items = [
        ("Availability", f"{metrics['availability_percentage']:.1f}%"),
        ("Stock-out episodes", str(metrics["stockout_count"])),
        ("Unavailable duration", f"{metrics['stockout_duration_hours']:.1f} h"),
        ("Unmet demand", f"{metrics['unmet_demand']:.1f} units"),
        ("Demand fulfilled", f"{metrics['demand_fulfilment_percentage']:.1f}%"),
    ]
    for col, (name, value) in zip(cols, items):
        col.metric(name, value)


def inventory_plot(df, config):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.simulation_time, y=df.quantity_after, mode="lines+markers", line_shape="hv", name="Inventory"))
    for y, label, style in [
        (config.reorder_threshold, "Reorder trigger", "dash"),
        (config.thresholds.low, "Low threshold", "dot"),
        (config.thresholds.critical, "Critical threshold", "dot"),
    ]:
        fig.add_hline(y=y, line_dash=style, annotation_text=label)
    fig.update_layout(xaxis_title="Elapsed simulation hours", yaxis_title="Illustrative inventory units", height=420)
    return fig


tab1, tab2, tab3, tab4 = st.tabs(["Single Run", "Statistical Evaluation", "Verification", "Scenario Summary"])

with tab1:
    st.subheader("Single stochastic run")
    if st.button("Run scenario", key="run_one", type="primary"):
        raw = as_dataframe(simpy_run(cfg, scenario_id=scenario_id(preset), replication_id=1))
        st.session_state["single_result"] = (raw, replace(cfg), preset, origin)

    if "single_result" not in st.session_state:
        st.info("Run a scenario to view the trajectory, event log and data-quality checks.")
    else:
        raw, used_cfg, used_label, used_origin = st.session_state["single_result"]
        view = annotated_event_log(raw, used_origin)
        metrics = run_metrics(raw, used_cfg)
        st.caption(f"Scenario: {used_label} · seed {used_cfg.seed} · horizon {used_cfg.horizon_hours:g} hours · mode: {used_cfg.demand_mode} · patient volume: {used_cfg.patient_volume if used_cfg.demand_mode == 'patient_volume' else 'n/a'}")
        metrics_bar(metrics)
        if used_cfg.demand_mode == "patient_volume":
            st.markdown("**Workload-to-resource summary**")
            w1, w2, w3, w4, w5 = st.columns(5)
            w1.metric("Configured patients", f"{int(used_cfg.patient_volume):,}")
            w2.metric("Patient arrivals", f"{int(metrics['patient_arrival_count']):,}")
            w3.metric("Resource requests", f"{int(metrics['resource_request_count']):,}")
            w4.metric("Patients generating a request", f"{int(metrics['patients_generating_request_count']):,}")
            rp = metrics["realised_patient_request_percentage"]
            w5.metric("Realised request proportion", f"{rp:.1f}%" if pd.notna(rp) else "N/A")
            st.caption(f"Configured patient-to-request probability: {100.0 * used_cfg.patient_demand_probability:.1f}%. Both this value and all operational parameters remain illustrative until RO1 evidence justifies them.")
        st.plotly_chart(inventory_plot(raw, used_cfg), width="stretch")

        left, right = st.columns(2)
        with left:
            st.markdown("**Duration in each resource state**")
            st.dataframe(state_duration_table(raw, used_cfg.horizon_hours), width="stretch", hide_index=True)
        with right:
            st.markdown("**Event counts**")
            counts = view.event_type.value_counts().rename_axis("event_type").reset_index(name="count")
            st.dataframe(counts, width="stretch", hide_index=True)

        checks = audit_event_log(raw)
        st.markdown("**Event-log integrity checks**")
        st.dataframe(checks, width="stretch", hide_index=True)
        if not checks.passed.all():
            st.error("One or more event-log integrity checks failed.")

        st.markdown("**Event log**")
        display_cols = [
            "event_index", "elapsed_time_readable", "simulated_datetime", "event_type", "event_semantics",
            "quantity_before", "quantity_after", "resource_state",
            "transaction_demand_quantity", "transaction_fulfilled_quantity",
            "transaction_unmet_quantity", "cumulative_unmet", "order_pending",
            "scheduled_arrival_readable", "related_demand_event_index", "shortfall_reference_quantity", "patient_id",
        ]
        display_cols = [c for c in display_cols if c in view.columns]
        st.dataframe(view[display_cols], width="stretch", hide_index=True)

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.download_button("Event log CSV", export_csv(view), f"{scenario_id(used_label)}_event_log.csv", mime="text/csv")
        with c2:
            st.download_button("Integrity report CSV", export_csv(checks), f"{scenario_id(used_label)}_integrity_report.csv", mime="text/csv")
        with c3:
            st.download_button("Configuration CSV", export_csv(config_snapshot(used_cfg, used_label, used_origin)), f"{scenario_id(used_label)}_configuration.csv", mime="text/csv")
        with c4:
            with open("DATA_DICTIONARY.csv", encoding="utf-8-sig") as fh:
                dictionary = fh.read()
            st.download_button("Data dictionary", dictionary.encode("utf-8-sig"), "DATA_DICTIONARY.csv", mime="text/csv")

with tab2:
    st.subheader("Repeated-run statistical evaluation")
    n = st.slider("Number of replications", 10, 200, 30, 10, key="rep_n")
    if st.button("Run replications", key="run_replications"):
        reps = run_replications(simpy_run, cfg, n=n, scenario_id=scenario_id(preset))
        st.session_state["rep_result"] = (reps, replace(cfg), preset, origin)

    if "rep_result" in st.session_state:
        reps, used_cfg, used_label, used_origin = st.session_state["rep_result"]
        summary = replication_summary(reps)
        cols = st.columns(4)
        cols[0].metric("Replications", len(reps))
        cols[1].metric("Mean availability", f"{reps.availability_percentage.mean():.1f}%")
        cols[2].metric("Runs with stock-out", f"{reps.stockout_occurred.mean()*100:.1f}%")
        cols[3].metric("Median unmet demand", f"{reps.unmet_demand.median():.1f} units")
        measure = st.selectbox("Output", ["availability_percentage", "stockout_duration_hours", "unmet_demand", "time_to_first_stockout_hours", "final_stock"])
        st.plotly_chart(px.histogram(reps, x=measure, nbins=min(20, max(5, len(reps)//3)), marginal="box"), width="stretch")
        st.dataframe(summary, width="stretch", hide_index=True)
        a, b = st.columns(2)
        with a:
            st.download_button("Replication metrics CSV", export_csv(reps), f"{scenario_id(used_label)}_{len(reps)}_replications.csv", mime="text/csv")
        with b:
            st.download_button("Statistical summary CSV", export_csv(summary), f"{scenario_id(used_label)}_summary.csv", mime="text/csv")

    st.divider()
    st.markdown("### Baseline versus one stress condition")
    st.caption("The comparison restores the active sidebar preset's perturbed field to its illustrative base value, then applies the chosen stress condition. Other current settings, including patient volume and horizon, are retained. For a custom base value on the field being compared, choose Illustrative baseline in the sidebar and edit that value first.")
    comparison = st.selectbox("Stress condition", ["Delayed replenishment", "Increased demand", "Reduced initial stock"], key="stress_selector")
    n_cmp = st.slider("Replications per condition", 10, 100, 30, 10, key="cmp_n")
    if st.button("Run comparison", key="cmp_run"):
        canonical = comparison_baseline_config(cfg, preset)
        altered = scenario_config(comparison, base=canonical)
        normal = run_replications(simpy_run, canonical, n=n_cmp, scenario_id="illustrative_baseline")
        stress = run_replications(simpy_run, altered, n=n_cmp, scenario_id=scenario_id(comparison), seed_start=canonical.seed)
        st.session_state["stress_result"] = (pd.concat([normal, stress], ignore_index=True), canonical, altered, comparison, origin)

    if "stress_result" in st.session_state:
        comp, reference_cfg, stress_cfg, chosen, used_origin = st.session_state["stress_result"]
        before = config_snapshot(reference_cfg, "Illustrative baseline", used_origin).set_index("parameter_or_metadata")["value"]
        after = config_snapshot(stress_cfg, chosen, used_origin).set_index("parameter_or_metadata")["value"]
        delta = pd.DataFrame({"parameter": before.index, "baseline": before.values, "stress": after.reindex(before.index).values})
        changed = delta[delta.baseline != delta.stress]
        st.markdown("**Changed parameter(s)**")
        st.dataframe(changed, width="stretch", hide_index=True)
        group = comp.groupby("scenario_id").agg(
            mean_availability=("availability_percentage", "mean"),
            stockout_probability=("stockout_occurred", "mean"),
            median_stockout_hours=("stockout_duration_hours", "median"),
            median_unmet_demand=("unmet_demand", "median"),
            mean_resource_requests=("resource_request_count", "mean"),
            mean_patient_arrivals=("patient_arrival_count", "mean"),
            mean_patient_request_percentage=("realised_patient_request_percentage", "mean"),
        ).reset_index()
        group.stockout_probability = group.stockout_probability * 100.0
        st.dataframe(group, width="stretch", hide_index=True)
        metric = st.selectbox("Comparison output", ["availability_percentage", "stockout_duration_hours", "unmet_demand"], key="cmp_metric")
        st.plotly_chart(px.box(comp, x="scenario_id", y=metric, points="all"), width="stretch")
        a, b = st.columns(2)
        with a:
            st.download_button("Comparison rows CSV", export_csv(comp), f"baseline_vs_{scenario_id(chosen)}_replications.csv", mime="text/csv")
        with b:
            st.download_button("Comparison settings CSV", export_csv(delta), "comparison_parameters.csv", mime="text/csv")

with tab3:
    st.subheader("Technical verification")
    st.caption("These checks test implemented simulation rules and data consistency for the defined cases.")
    if st.button("Run verification suite", key="run_verification"):
        report = run_verification_suite(simpy_run, cfg)
        st.session_state["verification_result"] = (report, replace(cfg), preset, origin)

    if "verification_result" in st.session_state:
        report, used_cfg, used_label, used_origin = st.session_state["verification_result"]
        report = report.copy()
        report["status"] = report.passed.map({True: "PASS", False: "FAIL"})
        st.metric("Checks passing", f"{int(report.passed.sum())}/{len(report)}")
        st.dataframe(report[["test_id", "status", "verification_test", "expected_invariant", "evidence", "test_case"]], width="stretch", hide_index=True)
        if report.passed.all():
            st.success("All implemented verification checks passed for the tested cases.")
        else:
            st.error("Verification failed. Inspect the failed check(s) before interpreting outputs.")
        a, b = st.columns(2)
        with a:
            st.download_button("Verification report CSV", export_csv(report), f"{scenario_id(used_label)}_verification_report.csv", mime="text/csv")
        with b:
            st.download_button("Verification configuration CSV", export_csv(config_snapshot(used_cfg, used_label, used_origin)), "verification_configuration.csv", mime="text/csv")

with tab4:
    st.subheader("Scenario summary")
    if "single_result" not in st.session_state:
        st.info("Run a single scenario first.")
    else:
        raw, used_cfg, used_label, used_origin = st.session_state["single_result"]
        card = scenario_card(raw, used_cfg, label=used_label)
        card["Display calendar start"] = used_origin.isoformat(sep=" ")
        df = pd.DataFrame({"Field": list(card.keys()), "Value": list(card.values())})
        st.dataframe(df, width="stretch", hide_index=True)
        st.download_button("Scenario summary CSV", export_csv(df), f"{scenario_id(used_label)}_scenario_summary.csv", mime="text/csv")
