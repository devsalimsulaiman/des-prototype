# Patient-volume mode hardening — 21 October 2026

## Changes

1. **Workload reporting:** the Single Run view and Scenario Summary report demand mode, configured patient count, patient arrivals, resource requests, number of patients generating a request, configured request probability, and realised patient-request proportion. Patient-only values show `Not applicable` in request-rate mode and the realised proportion is not reported where there were no patient arrivals.
2. **Event semantics:** `PATIENT_ARRIVAL` and `NO_RESOURCE_REQUEST` now have explicit semantic labels; workload/configuration metadata is written to event rows. Patient IDs are explicitly synthetic workload identifiers.
3. **Patient-volume reference implementation:** the independent heap-based reference scheduler now mirrors patient-arrival sampling, request-probability draws, and demand-size draws in patient-volume mode as well as in request-rate mode.
4. **Integration tests:** tests cover exact configured patient-arrival counts, request probabilities of 0 and 1, zero-patient workload, event-log audit, summary metrics, verification-suite results, and SimPy/reference trace equality in both demand modes.
5. **Scenario mode switching:** switching modes while `Increased demand` is selected now updates the active mode's stress parameter and resets the inactive mode-specific parameter to its illustrative base value.
6. **Scenario comparison baseline:** if the sidebar's active preset is itself a stress preset, the affected field is restored to its base value before the selected comparison stress is applied. Other current settings, including patient volume and horizon, are retained. The UI explains how to use a custom base value.
7. **Input wording and documentation:** the UI now says “Number of simulated patients over the horizon”; README, Start Here guide, and data dictionary describe the workload reporting and limitations.

## Verification run

The automated test suite completed with **38 passed, 0 failed, 0 skipped** in this build environment using SimPy 4.1.2 source included in the previously supplied full prototype environment. The portable package itself does not include a virtual environment; `setup_windows.bat` installs SimPy from `requirements.txt` and then runs the tests in the user's environment.

`app.py` passes Python syntax compilation. Streamlit is not installed in this build environment, so the graphical interface was not launched here; please run `setup_windows.bat` and then `launch_gui.bat` on Windows for the final interactive smoke test.

## Research boundary

All numeric operational settings and the patient-to-resource-request probability remain illustrative until RO1 evidence supports or revises them. Cross-implementation agreement and passing software tests establish technical consistency for the tested configurations, not clinical validation or empirical realism.


# Console verification and controlled fault detection — 29 October 2026

## Changes

1. Added `run_console_checks.py` and updated `run_checks.bat` to stream verbose per-test output into CMD and record a combined transcript. The setup script now invokes the same detailed runner after dependency installation.
2. Added `run_fault_detection_demo.py`, which displays all baseline audit checks and V01–V16 verification checks, then runs five controlled mutations on separate in-memory copies.
3. Added `failure_detection.py` and `tests/test_fault_injection.py` for a positive-control event log and five isolated defect-detection cases. The baseline is checked before and after mutation tests to confirm it remains unchanged.
4. Expanded the audit with per-demand conservation and fulfilment bounds, scheduled-arrival matching, and duplicate-pending-order checks. Audit/verification now preserves event-index order for chronology checks rather than sorting malformed events by timestamp before checking them. Display exports may still use chronological sorting.
5. Test records and README now distinguish the earlier 38-test result from the current 44 pytest cases and from the 16 named verification invariants V01–V16.

## Verification run

The expanded suite completed with **44 passed, 0 failed, 0 skipped** in the build environment using CPython 3.13.5, pytest 9.0.2, and SimPy 4.1.2. The standalone fault-detection demonstration also completed successfully: the baseline audit passed 13/13 checks, V01–V16 passed 16/16, and all five known mutations were detected by their expected audit and/or verification check. The duplicate reorder mutation was detected specifically by the pending-order check; the early-replenishment mutation was detected by scheduled-time matching and V04.

## Research boundary

The fault-injection exercise tests whether selected software audits detect known data defects. It is not clinical validation. The demonstration workload and all inventory parameters remain illustrative, and the live Streamlit GUI still requires a separate smoke test on the target Windows environment.
