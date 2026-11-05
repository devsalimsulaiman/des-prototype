# Running the RO3 verification and fault-detection demonstration

## Before the demonstration

1. Extract the project ZIP into a writable folder.
2. Double-click `setup_windows.bat` once. It creates `.venv`, installs the packages from `requirements.txt`, and executes the detailed test runner.
3. For a later live demonstration, double-click `run_checks.bat`. It activates the prepared virtual environment, runs `pytest -vv -rA`, and then runs the positive-control and fault-injection demonstration. Leave the CMD window open while presenting the output.

## What the console shows

- **44 named pytest cases** in the expanded suite, each with a PASSED/FAILED result.
- A valid synthetic event log with each audit check printed individually.
- Every technical verification check V01–V16, each with PASS/FAIL and evidence.
- Five controlled faults, one at a time. The mutated copy should show the intended invariant as `EXPECTED FAIL`, while the mutation test result should say `PASS — intended defect detected`.
- Confirmation that the original valid event log remained unchanged.

To repeat only the mutation demonstration, double-click `run_fault_detection_demo.bat` after setup. The command `python run_fault_detection_demo.py` also works inside the activated virtual environment.

## Output files

Every `run_checks.bat` call saves a timestamped transcript under `outputs/console_checks_<timestamp>/console_test_log.txt`, plus a convenience copy at `outputs/RO3_console_test_log_latest.txt`. The fault demonstration creates a separate timestamped folder containing:

- `valid_control_event_log.csv` — the intact synthetic baseline trace;
- `valid_control_audit_checks.csv` — every baseline data-audit result;
- `valid_control_V01_V16_checks.csv` — all 16 technical verification rows;
- `mutation_test_summary.csv` — one summary row per defect;
- `mutation_audit_check_details.csv` — every audit check for every mutated copy; and
- `mutation_event_log_verification_details.csv` — event-log V01–V13 results for each mutation. V14–V16 concern independent zero-demand, reproducibility, and initial-stock edge cases, so they are shown on the baseline suite rather than being re-run against corrupted logs.

## Interpretation

The baseline in this demonstration is generated from fully synthetic, illustrative inputs selected to exercise demand, shortage, reorder, replenishment, and recovery events. “Valid” here means that its recorded event log satisfies the implemented software invariants; it does not mean the scenario is clinically representative or validated against hospital data.

A `PASS` mutation result means the expected software detector correctly identified a known injected defect on a copy of the event log. The deliberately corrupted copy is not used to overwrite the baseline trace. These checks demonstrate testability of the audit and verification routines, not clinical validation, statistical input validity, or real-world parameter accuracy.

For screenshots, maximise CMD and capture the pytest section, the V01–V16 baseline section, and the five mutation sections as separate screenshots. The timestamped log provides the complete record if the console has scrolled past a section.
