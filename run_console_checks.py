"""Run the expanded pytest suite and fault-detection demo with live CMD output.

Creates a timestamped transcript under outputs/ and also maintains a latest-log
copy for convenient examiner demonstrations. Existing prototype run data are
not opened or overwritten by the mutations; each demonstration is isolated.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
OUTPUTS = ROOT / 'outputs'


def stream_command(command: list[str], log_handle, title: str) -> int:
    print(f'\n$ {" ".join(command)}')
    log_handle.write(f'\n$ {" ".join(command)}\n')
    log_handle.flush()
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding='utf-8',
        errors='replace',
        bufsize=1,
    )
    assert process.stdout is not None
    for line in process.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
        log_handle.write(line)
        log_handle.flush()
    result = process.wait()
    line = f'[{title} EXIT CODE: {result}]\n'
    sys.stdout.write(line)
    sys.stdout.flush()
    log_handle.write(line)
    log_handle.flush()
    return result


def main() -> int:
    OUTPUTS.mkdir(exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    run_dir = OUTPUTS / f'console_checks_{stamp}'
    run_dir.mkdir(parents=True, exist_ok=False)
    log_path = run_dir / 'console_test_log.txt'

    print('=' * 78)
    print('SEPSIS-CARE DES — FULL CONSOLE TEST RUN')
    print('=' * 78)
    print(f'Timestamp: {datetime.now().isoformat(timespec="seconds")}')
    print(f'Python: {sys.executable}')
    print(f'Log copy: {log_path}')

    with log_path.open('w', encoding='utf-8', newline='\n') as log:
        log.write('=' * 78 + '\n')
        log.write('SEPSIS-CARE DES — FULL CONSOLE TEST RUN\n')
        log.write('=' * 78 + '\n')
        log.write(f'Timestamp: {datetime.now().isoformat(timespec="seconds")}\n')
        log.write(f'Python: {sys.executable}\n')
        log.write(f'Working directory: {ROOT}\n')

        pytest_code = stream_command(
            [sys.executable, '-u', '-m', 'pytest', '-vv', '-rA', '--color=no'],
            log,
            'PYTEST SUITE',
        )
        if pytest_code != 0:
            print('\nThe pytest suite failed; fault-injection demo was not run.')
            log.write('\nThe pytest suite failed; fault-injection demo was not run.\n')
            result_code = pytest_code
        else:
            demo_code = stream_command(
                [sys.executable, '-u', str(ROOT / 'run_fault_detection_demo.py')],
                log,
                'FAULT-DETECTION DEMO',
            )
            result_code = demo_code

        final_message = (
            f'\nCONSOLE RUN OVERALL RESULT: {"PASS" if result_code == 0 else "FAIL"}\n'
            f'Timestamped transcript: {log_path}\n'
        )
        print(final_message, end='')
        log.write(final_message)

    latest = OUTPUTS / 'RO3_console_test_log_latest.txt'
    shutil.copy2(log_path, latest)
    print(f'Latest transcript copy: {latest}')
    return result_code


if __name__ == '__main__':
    raise SystemExit(main())
