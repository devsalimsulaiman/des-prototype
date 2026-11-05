# Sepsis-Care Operational-Resource DES Prototype

A bounded feasibility prototype for a single provisional norepinephrine-inventory case. It demonstrates event-driven inventory dynamics, transparent event/state logging, repeated-run analysis, controlled scenario comparisons, and technical checks. It is not the final thesis model.

## Workload and time inputs

The GUI allows the user to set the simulation horizon in hours and select either:

- **Patient-volume-driven mode:** specify the number of simulated patient workload entities and a probability that each generates one inventory request. Exactly the configured number of patient arrivals are generated at sampled times across the horizon. The Single Run KPI panel and Scenario Summary report configured workload, patient arrivals, resource requests, patients generating requests, configured probability, and the realised patient-request proportion. This is deliberately a simple illustrative linkage, not a clinically established utilisation model; RO1 must justify or refine it before thesis findings are produced.
- **Request-rate-driven mode:** requests arrive according to the configured mean interarrival time, preserving the original prototype mechanism.

Patients are workload drivers only; this prototype does not model beds, queues, length of stay, prescribing, dose titration, treatment decisions, or patient outcomes. It does not assume every patient requires norepinephrine.

## Scenario presets and user controls

Presets provide transparent starting conditions, not fixed immutable scenarios. After choosing a preset, users can edit parameters in the sidebar. Switching the demand-generation mode while Increased demand is selected updates the relevant mode-specific stress parameter automatically. Statistical comparison restores the active sidebar preset's perturbed field to its illustrative base value, carries other current settings (including patient volume and horizon), and then applies one explicit comparison perturbation. To use a custom base value for the field being compared, select Illustrative baseline, edit that value, and run the comparison:

- **Illustrative baseline:** no stress perturbation.
- **Delayed replenishment:** doubles the current lead-time value.
- **Increased demand:** halves mean interarrival time in request-rate mode; in patient-volume mode it doubles the current patient-to-request probability, capped at 1.0.
- **Reduced initial stock:** multiplies the current initial inventory by 0.6.

All values are illustrative unless separately supported by evidence and approved for the final study. Scenario changes are experimental perturbations, not claims about observed hospital conditions.

## What the prototype does

1. **Single Run** — trajectory, event log, state durations, integrity checks, and CSV exports.
2. **Statistical Evaluation** — repeated replications, distributions, summary statistics, and baseline-versus-stress comparisons.
3. **Verification** — traceable executable checks of inventory/event-log invariants.
4. **Scenario Summary** — concise output summary.

## Examiner-facing CMD verification and fault detection

After setup, double-click `run_checks.bat` or run `python run_console_checks.py` from the activated project environment. The command streams the named pytest cases and then runs a detailed RO3 check demonstration in the console. It prints each baseline audit check, all V01–V16 verification results, each injected defect, the detector expected to find it, all failed checks on the corrupted copy, and whether the original event log remained unchanged.

The controlled fault-injection demonstration includes a positive control (an internally consistent synthetic event log must pass the audit) and five independent, in-memory mutation cases:

1. fulfilled quantity is greater than requested;
2. unmet quantity no longer equals requested minus fulfilled;
3. cumulative unmet does not reconcile;
4. a replenishment timestamp is one hour earlier than its scheduled time; and
5. a duplicate reorder is inserted while an order is pending.

The mutation outputs are expected to show failed invariants on the deliberately corrupted copy; the **mutation test itself should report PASS** when the intended detector fails it. The valid baseline is kept unchanged. This evaluates the software's ability to detect selected data defects; it is not clinical validation and does not establish that the illustrative parameters reflect hospital practice.

Each invocation creates a timestamped folder under `outputs/` containing the valid baseline event log, baseline audit results, V01–V16 results, a mutation summary, and detailed CSVs for every audit/verification check on each mutated copy. A combined live console transcript is saved as `outputs/console_checks_<timestamp>/console_test_log.txt`; a convenience copy is kept at `outputs/RO3_console_test_log_latest.txt`. These records can be reopened for review or the demonstration can be run again live in CMD.

The earlier 38-test result referred to the previous suite. The expanded suite now contains **44 pytest test cases**: the prior 38 plus one positive-control test and five targeted mutation tests. Do not confuse the pytest case count with the 16 named verification invariants (V01–V16).

## Install on Windows

1. Extract the ZIP.
2. Double-click `setup_windows.bat` once.
3. After setup succeeds, double-click `launch_gui.bat`.

## Important research boundary

The current parameters are feasibility settings, not hospital measurements. The final thesis model requires RO1 confirmation of the process boundary, units, patient-to-resource linkage (if retained), operational rules, and parameter provenance. Technical verification does not replace repeated-run statistical evaluation or structured clinician/domain-expert assessment after required approvals.

## Key files

- `app.py` — Streamlit interface and editable controls
- `config.py` — configuration and validation
- `model_simpy.py` — SimPy event engine
- `scenarios.py` — preset perturbations
- `analytics.py` — run metrics and repeated-run summaries
- `verification.py` — executable verification suite
- `data_quality.py` — event-log audit and metadata
- `reference_scheduler.py` — independent reference implementation for both request-rate and patient-volume modes; cross-checked with the SimPy engine in automated integration tests
- `DATA_DICTIONARY.csv` — output data dictionary
- `audit_csv.py` — exported-log audit utility

## Patient-volume integration and cross-checks

Automated tests cover exact patient-arrival counts, probability 0 and 1 edge cases, zero-patient handling, workload/request summary metrics, event-log integrity, verification-suite execution, and equality of representative SimPy/reference-scheduler traces in patient-volume mode. These are software checks only; they do not validate the clinical appropriateness of the configured patient-to-resource-request probability.
