"""Event-log semantics, human-readable simulation time and audit utilities.

Numeric simulation_time is *always* elapsed hours. Calendar timestamps are
presentation-only, unless a future evidence-supported model explicitly uses
hour-of-day/week rules. Transactions occur only in DEMAND and
REPLENISHMENT_ARRIVAL rows. SHORTFALL and STATE_CHANGE are notifications.

The audit routines preserve recorded event order when checking chronology and
reorder timing. Display exports may be sorted by time, but an audit must never
sort away the defect it is trying to detect.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import math
from typing import Iterable

import numpy as np
import pandas as pd


TRANSACTION_EVENT_TYPES = frozenset({'DEMAND', 'REPLENISHMENT_ARRIVAL'})
DEMAND_COLUMNS = ('demand_quantity', 'fulfilled_quantity', 'unmet_quantity')


def elapsed_label(hours: float) -> str:
    if pd.isna(hours):
        return ''
    seconds = int(math.floor(float(hours) * 3600.0 + 0.5))
    sign = '-' if seconds < 0 else ''
    seconds = abs(seconds)
    days, sec = divmod(seconds, 86400)
    hh, sec = divmod(sec, 3600)
    mm, ss = divmod(sec, 60)
    return f'{sign}Day {days + 1}, {hh:02d}:{mm:02d}:{ss:02d}'


def timestamp_label(hours: float, origin: datetime | None) -> str:
    if origin is None or pd.isna(hours):
        return ''
    dt = origin + timedelta(seconds=round(float(hours) * 3600))
    return dt.isoformat(sep=' ', timespec='seconds')


def annotated_event_log(events, origin: datetime | None = None, *, sort_for_display: bool = True) -> pd.DataFrame:
    """Return a derived export without changing the supplied event values.

    ``sort_for_display=True`` retains the convenient chronological sorting used
    by CSV exports. Audits pass ``False`` so malformed timestamps cannot be
    hidden by sorting the corrupted rows into apparently valid order.

    Legacy SHORTFALL rows may repeat transaction values. We preserve the raw
    fields but derive transaction-only columns that exclude notifications.
    """
    df = events.copy() if isinstance(events, pd.DataFrame) else pd.DataFrame(events)
    if df.empty:
        return df
    if sort_for_display:
        sort_cols = [c for c in ('simulation_time', 'event_index') if c in df.columns]
        if sort_cols:
            df = df.sort_values(sort_cols, kind='stable').reset_index(drop=True)
    elif 'event_index' in df.columns:
        df = df.sort_values(['event_index'], kind='stable').reset_index(drop=True)
    else:
        df = df.reset_index(drop=True)

    df['simulation_time_unit'] = 'hours since simulation start'
    df['elapsed_time_readable'] = df.simulation_time.map(elapsed_label)
    df['simulated_datetime'] = df.simulation_time.map(lambda t: timestamp_label(t, origin))
    if 'scheduled_replenishment_time' in df.columns:
        df['scheduled_arrival_readable'] = df.scheduled_replenishment_time.map(elapsed_label)
        df['scheduled_arrival_datetime'] = df.scheduled_replenishment_time.map(lambda t: timestamp_label(t, origin))
    else:
        df['scheduled_arrival_readable'] = ''
        df['scheduled_arrival_datetime'] = ''
    is_demand = df.event_type.eq('DEMAND')
    is_replenishment = df.event_type.eq('REPLENISHMENT_ARRIVAL')
    df['is_demand_transaction'] = is_demand
    df['is_replenishment_transaction'] = is_replenishment
    for name in DEMAND_COLUMNS:
        source = pd.to_numeric(df[name] if name in df else pd.Series(0.0, index=df.index), errors='coerce').fillna(0.0)
        df[f'transaction_{name}'] = source.where(is_demand, 0.0)
    replenishment = pd.to_numeric(df['replenishment_quantity'] if 'replenishment_quantity' in df else pd.Series(0.0, index=df.index), errors='coerce').fillna(0.0)
    df['transaction_replenishment_quantity'] = replenishment.where(is_replenishment, 0.0)
    df['cumulative_unmet_delta'] = pd.to_numeric(df['cumulative_unmet'], errors='coerce').diff().fillna(pd.to_numeric(df['cumulative_unmet'], errors='coerce')).fillna(0.0)
    df['event_semantics'] = df.event_type.map({
        'PATIENT_ARRIVAL': 'SYNTHETIC WORKLOAD ARRIVAL; NOT A CLINICAL RECORD',
        'NO_RESOURCE_REQUEST': 'PATIENT ARRIVAL WITHOUT A RESOURCE REQUEST',
        'DEMAND': 'PRIMARY DEMAND TRANSACTION',
        'REPLENISHMENT_ARRIVAL': 'PRIMARY REPLENISHMENT TRANSACTION',
        'SHORTFALL': 'NOTIFICATION ONLY - DO NOT SUM AS NEW UNMET DEMAND',
        'STATE_CHANGE': 'NOTIFICATION ONLY',
        'STOCKOUT_START': 'NOTIFICATION ONLY',
        'RECOVERY': 'NOTIFICATION ONLY',
        'REORDER_INITIATED': 'ORDER INITIATION; NO STOCK ADDED YET',
        'INITIALISE': 'INITIAL STATE',
        'END': 'END OF SIMULATED HORIZON',
    }).fillna('AUXILIARY EVENT')
    leaders = ['event_index','simulation_time','elapsed_time_readable','simulated_datetime','simulation_time_unit',
               'scenario_id','replication_id','random_seed','demand_mode','patient_volume',
               'patient_demand_probability','configured_horizon_hours','event_type','event_semantics']
    return df[[c for c in leaders if c in df.columns] + [c for c in df.columns if c not in leaders]]


def audit_event_log(events, tolerance=1e-7) -> pd.DataFrame:
    """Return independent per-rule audit results in *recorded event order*.

    The function never mutates the caller's frame. Chronology, scheduled lead
    time, and duplicate-pending-order checks are evaluated from the recorded
    event sequence rather than from a display-sorted view.
    """
    source = events.copy() if isinstance(events, pd.DataFrame) else pd.DataFrame(events)
    if source.empty:
        raise ValueError('Cannot audit empty event log.')
    if 'event_index' in source.columns:
        source = source.sort_values(['event_index'], kind='stable').reset_index(drop=True)
    else:
        source = source.reset_index(drop=True)
    df = annotated_event_log(source, sort_for_display=False)
    demand = df[df.event_type == 'DEMAND']
    repl = df[df.event_type == 'REPLENISHMENT_ARRIVAL']
    errors = []

    def add(name, okay, details):
        errors.append({'audit_check': name, 'passed': bool(okay), 'evidence': str(details)})

    total_d = float(demand.transaction_demand_quantity.sum())
    total_f = float(demand.transaction_fulfilled_quantity.sum())
    total_u = float(demand.transaction_unmet_quantity.sum())
    cumulative = pd.to_numeric(df['cumulative_unmet'], errors='coerce').fillna(0.0)
    last_c = float(cumulative.iloc[-1])
    first_c = float(cumulative.iloc[0])

    add('Demand conservation', abs(total_d - total_f - total_u) < tolerance,
        f'requested={total_d:g}; fulfilled={total_f:g}; unmet={total_u:g}')

    if len(demand):
        row_residual = (pd.to_numeric(demand.demand_quantity, errors='coerce')
                        - pd.to_numeric(demand.fulfilled_quantity, errors='coerce')
                        - pd.to_numeric(demand.unmet_quantity, errors='coerce')).abs()
        row_ok = bool(row_residual.notna().all() and (row_residual < tolerance).all())
        max_residual = float(row_residual.max()) if row_residual.notna().any() else float('inf')
    else:
        row_ok = True
        max_residual = 0.0
    add('Per-demand demand conservation', row_ok,
        f'{len(demand)} demand transactions; largest |requested-fulfilled-unmet|={max_residual:.8g}')

    add('Cumulative unmet equals summed demand shortfalls',
        abs(last_c - first_c - total_u) < tolerance,
        f'cumulative delta={last_c-first_c:g}; demand-only unmet={total_u:g}')
    deltas = df.cumulative_unmet_delta.astype(float)
    mismatch = (deltas - df.transaction_unmet_quantity).abs()
    mismatch_ok = bool((mismatch < tolerance).all())
    add('Row-wise cumulative increment', mismatch_ok,
        f'largest delta discrepancy={mismatch.max():.8g}')
    add('Cumulative unmet never decreases', bool((deltas >= -tolerance).all()),
        f'minimum increment={deltas.min():g}')

    quantity = pd.to_numeric(df.quantity_after, errors='coerce')
    add('Non-negative stock', bool(quantity.notna().all() and (quantity >= -tolerance).all()),
        f'minimum stock={quantity.min():g}')

    if len(demand):
        demand_q = pd.to_numeric(demand.demand_quantity, errors='coerce')
        fulfilled_q = pd.to_numeric(demand.fulfilled_quantity, errors='coerce')
        unmet_q = pd.to_numeric(demand.unmet_quantity, errors='coerce')
        if 'quantity_before' in demand.columns:
            stock_before = pd.to_numeric(demand.quantity_before, errors='coerce')
            stock_bound = fulfilled_q <= stock_before + tolerance
        else:
            stock_bound = pd.Series(True, index=demand.index)
        bounds = (demand_q.notna() & fulfilled_q.notna() & unmet_q.notna()
                  & (demand_q >= -tolerance) & (fulfilled_q >= -tolerance)
                  & (unmet_q >= -tolerance) & (fulfilled_q <= demand_q + tolerance)
                  & stock_bound)
        add('Per-demand fulfilment bounds', bool(bounds.all()),
            f'{int(bounds.sum())}/{len(demand)} demand transactions within non-negative, request, and available-stock bounds')
        if 'quantity_before' in demand.columns:
            stock_before = pd.to_numeric(demand.quantity_before, errors='coerce')
            stock_after = pd.to_numeric(demand.quantity_after, errors='coerce')
            balance = (stock_before - fulfilled_q - stock_after).abs() < tolerance
            add('Per-demand stock decrement', bool(balance.all()),
                f'{int(balance.sum())}/{len(demand)} demand transactions matched')

    start_stock = float(pd.to_numeric(df.quantity_after, errors='coerce').iloc[0])
    end_stock = float(pd.to_numeric(df.quantity_after, errors='coerce').iloc[-1])
    replenished = float(repl.transaction_replenishment_quantity.sum())
    add('Inventory conservation', abs(start_stock + replenished - total_f - end_stock) < tolerance,
        f'initial={start_stock:g}; replenished={replenished:g}; fulfilled={total_f:g}; final={end_stock:g}')

    chronological = bool(pd.to_numeric(source.simulation_time, errors='coerce').notna().all()
                         and pd.to_numeric(source.simulation_time, errors='coerce').is_monotonic_increasing)
    add('Chronological event ordering', chronological,
        f'{len(source)} rows in recorded event-index order are nondecreasing in simulation_time')

    # Match each receipt to the expected timestamp carried by its pending order.
    # Orders still pending at the simulation horizon are allowed; a received
    # order must nevertheless arrive at the time scheduled when it was issued.
    pending_due = []
    duplicate_pending = False
    unexpected_arrival = False
    missing_schedule = False
    arrival_mismatches = []
    for row in source.itertuples(index=False):
        event_type = getattr(row, 'event_type', '')
        if event_type == 'REORDER_INITIATED':
            already_pending = bool(pending_due)
            if already_pending:
                duplicate_pending = True
            due = getattr(row, 'scheduled_replenishment_time', None)
            try:
                due_value = float(due)
            except (TypeError, ValueError):
                due_value = float('nan')
            if not math.isfinite(due_value):
                missing_schedule = True
            elif not already_pending:
                # Keep the first pending order as the receipt-matching reference.
                # A deliberately inserted duplicate should trip the duplicate
                # rule without shifting the receipt mapping for every later order.
                pending_due.append(due_value)
        elif event_type == 'REPLENISHMENT_ARRIVAL':
            if not pending_due:
                unexpected_arrival = True
            else:
                due_value = pending_due.pop(0)
                actual_value = float(getattr(row, 'simulation_time'))
                if abs(actual_value - due_value) >= tolerance:
                    arrival_mismatches.append((actual_value, due_value))
    timing_ok = (not missing_schedule and not unexpected_arrival and not arrival_mismatches)
    add('Replenishment arrival matches scheduled time', timing_ok,
        f'arrivals checked={len(repl)}; timestamp mismatches={arrival_mismatches}; '
        f'missing scheduled times={missing_schedule}; unexpected arrivals={unexpected_arrival}; '
        f'orders still pending at horizon={len(pending_due)}')
    add('No duplicate reorder while order pending', not duplicate_pending,
        f'duplicate order while an earlier order was pending={duplicate_pending}; '
        f'orders pending at horizon={len(pending_due)}')

    # Informational audit: transaction-only columns intentionally ignore
    # SHORTFALL notification rows, including legacy rows that duplicated values.
    naive = float(pd.to_numeric(df.unmet_quantity, errors='coerce').fillna(0).sum())
    add('Transaction-only shortfall accounting', True,
        f'raw all-row unmet sum={naive:g}; correct demand-transaction sum={total_u:g}; '
        'notification rows are excluded from transaction totals')
    return pd.DataFrame(errors)


def metadata_table(config, label: str, origin: datetime | None = None) -> pd.DataFrame:
    from dataclasses import asdict
    from datetime import datetime as dt
    fields = asdict(config)
    rows = [('scenario_label', label), ('parameter_evidence_status', 'ILLUSTRATIVE — NOT EMPIRICALLY PARAMETERISED'),
            ('simulation_time_unit', 'elapsed hours'),
            ('display_only_calendar_start', origin.isoformat(sep=' ') if origin else 'not selected'),
            ('calendar_affects_simulation_demand', 'NO'),
            ('generated_at_local', dt.now().isoformat(timespec='seconds'))]
    for k, v in fields.items():
        rows.append((k, repr(v)))
    return pd.DataFrame(rows, columns=['parameter_or_metadata', 'value'])
