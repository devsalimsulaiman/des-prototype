# Start Here

1. Run `setup_windows.bat` once, then `launch_gui.bat`.
2. In the sidebar, select **Patient-volume-driven** mode, set the **number of simulated patients over the horizon** (e.g., 100) and the simulation horizon (e.g., 168 hours), then review the illustrative request probability.
3. Click **Run scenario**. Check the workload-to-resource summary: configured patients, recorded patient arrivals, resource requests, patients generating a request, and realised request proportion. Then inspect the inventory trajectory, event log, integrity checks, and CSV exports.
4. Run repeated replications and examine availability, stock-out duration, unmet-demand distributions, request counts, and realised patient-request proportions.
5. Select a stress preset or compare against one stress condition. Mode switching updates the Increased demand preset's relevant parameter; the comparison reports the changed parameter(s). For a custom base value on the parameter being compared, select Illustrative baseline first and edit it.
6. For examiner demonstration, double-click `run_checks.bat`. It streams every pytest test case in CMD, displays the detailed V01–V16 baseline checks, and then injects five known defects into separate in-memory copies to demonstrate failure detection. The command writes a timestamped log and CSV evidence under `outputs/`.
7. You can run `python run_fault_detection_demo.py` separately to repeat just the detailed positive-control and mutation demonstration. Run it from the project's activated `.venv` so the SimPy engine is used.
8. The reference scheduler and SimPy engine are cross-checked for both supported demand modes by automated integration tests.

The example of 100 simulated patients over 7 days is a workload scenario only. It does not imply that all patients require norepinephrine. Patient-to-request probability and all operational values are illustrative until RO1 evidence justifies or refines them. The request-rate-driven mode remains available as an explicit alternative demand abstraction. Patient-volume trace checks show whether the software implemented the configured rule; they do not establish the rule's clinical validity.
