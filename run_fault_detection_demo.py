"""Print per-check verification and controlled fault-detection evidence to CMD."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys

import pandas as pd

from config import PrototypeConfig
from data_quality import audit_event_log
from failure_detection import build_mutation_cases
from reference_scheduler import run_reference
from verification import run_verification_suite, verify_event_log

ROOT = Path(__file__).resolve().parent


def choose_runner():
    try:
        from model_simpy import run as run_simpy
        import simpy  # noqa: F401
        return run_simpy, 'SimPy engine'
    except ImportError:
        return run_reference, 'independent heap-based reference scheduler (SimPy not installed)'


def print_check_rows(title: str, report: pd.DataFrame, *, id_column: str, name_column: str, evidence_column: str):
    print(f'\n{title}')
    print('-' * len(title))
    for _, row in report.iterrows():
        status = 'PASS' if bool(row['passed']) else 'FAIL'
        identifier = str(row[id_column]) if id_column in report.columns else 'AUDIT'
        name = str(row[name_column])
        evidence = str(row[evidence_column])
        print(f'[{status}] {identifier} | {name}')
        print(f'       Evidence: {evidence}')


def main() -> int:
    outputs = ROOT / 'outputs'
    outputs.mkdir(exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    run_dir = outputs / f'RO3_fault_detection_{stamp}'
    run_dir.mkdir(parents=True, exist_ok=False)

    # A purposely well-populated, fully synthetic workload is used only to
    # exercise inventory event types. These values are not hospital estimates.
    cfg = PrototypeConfig(
        initial_stock=100.0,
        reorder_threshold=30.0,
        replenishment_quantity=80.0,
        replenishment_lead_time_hours=24.0,
        horizon_hours=168.0,
        seed=20261008,
        demand_mode='patient_volume',
        patient_volume=100,
        patient_demand_probability=1.0,
    )
    runner, runner_name = choose_runner()
    print('=' * 78)
    print('RO3 TECHNICAL VERIFICATION + CONTROLLED FAULT-INJECTION DEMONSTRATION')
    print('=' * 78)
    print(f'Run timestamp : {datetime.now().isoformat(timespec="seconds")}')
    print(f'Python        : {sys.version.split()[0]}')
    print(f'Engine        : {runner_name}')
    print(f'Config        : mode={cfg.demand_mode}; workload={cfg.patient_volume}; horizon={cfg.horizon_hours:g} h; seed={cfg.seed}')
    print('Evidence limit: software verification/audit detection only; not clinical validation.')
    print('Mutation scope: every defect is applied to a deep in-memory copy; baseline log is never overwritten.')

    valid = pd.DataFrame(runner(cfg, scenario_id='fault_detection_valid_control', replication_id=1))
    valid_snapshot = valid.copy(deep=True)
    baseline_audit = audit_event_log(valid)
    # run_verification_suite reports the full V01-V16 set. It generates its
    # own baseline and edge-case traces using the same configured runner.
    baseline_verification = run_verification_suite(runner, cfg)
    valid_control_passed = bool(baseline_audit['passed'].all() and baseline_verification['passed'].all())

    print_check_rows('POSITIVE CONTROL — VALID EVENT LOG AUDIT', baseline_audit,
                     id_column='audit_check', name_column='audit_check', evidence_column='evidence')
    print_check_rows('POSITIVE CONTROL — V01–V16 TECHNICAL VERIFICATION', baseline_verification,
                     id_column='test_id', name_column='verification_test', evidence_column='evidence')
    print(f'\nVALID CONTROL RESULT: {"PASS" if valid_control_passed else "FAIL"} '
          f'| audit checks {int(baseline_audit.passed.sum())}/{len(baseline_audit)} pass '
          f'| verification checks {int(baseline_verification.passed.sum())}/{len(baseline_verification)} pass')

    mutation_summary = []
    all_audit_details = []
    all_verification_details = []
    all_mutations_detected = True

    for case in build_mutation_cases(valid):
        mutated = case.mutate(valid)
        # Demonstrate isolation: constructing the case must not modify valid.
        baseline_unchanged = valid.equals(valid_snapshot)
        audit = audit_event_log(mutated)
        verification = pd.DataFrame(verify_event_log(mutated, cfg))
        audit_failures = audit.loc[~audit['passed'], 'audit_check'].astype(str).tolist()
        verification_failures = verification.loc[~verification['passed'], 'test_id'].astype(str).tolist()
        audit_expected = [name for name in case.expected_audit_checks if name in audit_failures]
        verification_expected = [code for code in case.expected_verification_ids if code in verification_failures]
        detection_passed = bool(audit_expected or verification_expected)
        case_passed = detection_passed and baseline_unchanged
        all_mutations_detected = all_mutations_detected and case_passed

        print('\n' + '=' * 78)
        print(f'{case.mutation_id} — {case.description}')
        print(f'Mutated copy field: {case.mutated_field}')
        print(f'Expected detector : audit {list(case.expected_audit_checks)} and/or verification {list(case.expected_verification_ids)}')
        print('Audit checks on the corrupted copy (expected failures are deliberate):')
        for _, check_row in audit.iterrows():
            check_status = 'PASS' if bool(check_row['passed']) else 'EXPECTED FAIL'
            print(f'  [{check_status}] {check_row["audit_check"]} | {check_row["evidence"]}')
        print('Event-log V01–V13 checks on the corrupted copy (V14–V16 are separate scenario/reproducibility cases):')
        for _, check_row in verification.iterrows():
            check_status = 'PASS' if bool(check_row['passed']) else 'EXPECTED FAIL'
            print(f'  [{check_status}] {check_row["test_id"]} {check_row["verification_test"]} | {check_row["evidence"]}')
        print(f'Actual audit failures: {audit_failures or "none"}')
        print(f'Actual V-check failures: {verification_failures or "none"}')
        print(f'Expected detector triggered: {"YES" if detection_passed else "NO"}')
        print(f'Original valid log unchanged: {"YES" if baseline_unchanged else "NO"}')
        print(f'MUTATION TEST RESULT: {"PASS — intended defect detected" if case_passed else "FAIL — detection control did not behave as expected"}')

        mutation_summary.append({
            'mutation_id': case.mutation_id,
            'injected_defect': case.description,
            'mutated_field': case.mutated_field,
            'expected_audit_checks': '; '.join(case.expected_audit_checks),
            'expected_verification_ids': '; '.join(case.expected_verification_ids),
            'failed_audit_checks': '; '.join(audit_failures),
            'failed_verification_ids': '; '.join(verification_failures),
            'expected_detector_triggered': detection_passed,
            'baseline_original_unchanged': baseline_unchanged,
            'test_passed': case_passed,
        })
        audit_export = audit.copy()
        audit_export.insert(0, 'mutation_id', case.mutation_id)
        audit_export.insert(1, 'injected_defect', case.description)
        all_audit_details.append(audit_export)
        verification_export = verification.copy()
        verification_export.insert(0, 'mutation_id', case.mutation_id)
        verification_export.insert(1, 'injected_defect', case.description)
        all_verification_details.append(verification_export)

    # Re-check positive control after all copy mutations.
    baseline_final_check = valid.equals(valid_snapshot) and audit_event_log(valid)['passed'].all()
    overall = valid_control_passed and all_mutations_detected and baseline_final_check
    pd.DataFrame(valid).to_csv(run_dir / 'valid_control_event_log.csv', index=False, encoding='utf-8-sig')
    baseline_audit.to_csv(run_dir / 'valid_control_audit_checks.csv', index=False, encoding='utf-8-sig')
    baseline_verification.to_csv(run_dir / 'valid_control_V01_V16_checks.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(mutation_summary).to_csv(run_dir / 'mutation_test_summary.csv', index=False, encoding='utf-8-sig')
    pd.concat(all_audit_details, ignore_index=True).to_csv(run_dir / 'mutation_audit_check_details.csv', index=False, encoding='utf-8-sig')
    pd.concat(all_verification_details, ignore_index=True).to_csv(run_dir / 'mutation_event_log_verification_details.csv', index=False, encoding='utf-8-sig')

    print('\n' + '=' * 78)
    print(f'FINAL RESULT: {"PASS" if overall else "FAIL"}')
    print(f'  Valid positive control : {"PASS" if valid_control_passed else "FAIL"}')
    print(f'  Mutations detected     : {sum(bool(x["test_passed"]) for x in mutation_summary)}/{len(mutation_summary)}')
    print(f'  Original log preserved : {"YES" if baseline_final_check else "NO"}')
    print(f'  Result files           : {run_dir}')
    print('Reminder: controlled software fault detection is not clinical validation.')
    if not overall:
        print('ERROR: at least one positive-control or mutation-detection assertion failed.')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
