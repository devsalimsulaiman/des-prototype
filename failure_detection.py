"""Safe in-memory mutation cases for testing event-log audit detectors.

Every mutation starts from a deep copy of a valid synthetic trace. The original
trace is not altered or written over. These tests assess whether selected
software checks detect known data defects; they are not clinical validation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd


@dataclass(frozen=True)
class MutationCase:
    mutation_id: str
    description: str
    mutated_field: str
    expected_audit_checks: tuple[str, ...]
    expected_verification_ids: tuple[str, ...]
    mutate: Callable[[pd.DataFrame], pd.DataFrame]


def _recorded_order(events: pd.DataFrame) -> pd.DataFrame:
    df = events.copy(deep=True)
    if 'event_index' in df.columns:
        df = df.sort_values('event_index', kind='stable').reset_index(drop=True)
    else:
        df = df.reset_index(drop=True)
    return df


def _first_demand_row(df: pd.DataFrame, offset: int = 0) -> int:
    idxs = df.index[df['event_type'].eq('DEMAND')].tolist()
    if len(idxs) <= offset:
        raise ValueError('The valid baseline trace needs at least two DEMAND rows for mutation testing.')
    return idxs[offset]


def _mutate_fulfilled_exceeds_request(events: pd.DataFrame) -> pd.DataFrame:
    df = _recorded_order(events)
    idx = _first_demand_row(df)
    requested = float(df.at[idx, 'demand_quantity'])
    df.at[idx, 'fulfilled_quantity'] = requested + 1.0
    return df


def _mutate_unmet_relation(events: pd.DataFrame) -> pd.DataFrame:
    df = _recorded_order(events)
    idx = _first_demand_row(df, offset=1)
    df.at[idx, 'unmet_quantity'] = float(df.at[idx, 'unmet_quantity']) + 1.0
    return df


def _mutate_cumulative_unmet(events: pd.DataFrame) -> pd.DataFrame:
    df = _recorded_order(events)
    # Change the terminal running total. Demand transactions remain unchanged.
    end_rows = df.index[df['event_type'].eq('END')].tolist()
    idx = end_rows[-1] if end_rows else df.index[-1]
    df.at[idx, 'cumulative_unmet'] = float(df.at[idx, 'cumulative_unmet']) + 1.0
    return df


def _mutate_arrival_early(events: pd.DataFrame) -> pd.DataFrame:
    df = _recorded_order(events)
    arrivals = df.index[df['event_type'].eq('REPLENISHMENT_ARRIVAL')].tolist()
    if not arrivals:
        raise ValueError('The valid baseline trace needs at least one REPLENISHMENT_ARRIVAL.')
    idx = arrivals[0]
    df.at[idx, 'simulation_time'] = float(df.at[idx, 'simulation_time']) - 1.0
    return df


def _mutate_duplicate_pending_order(events: pd.DataFrame) -> pd.DataFrame:
    df = _recorded_order(events)
    reorder_rows = df.index[df['event_type'].eq('REORDER_INITIATED')].tolist()
    if not reorder_rows:
        raise ValueError('The valid baseline trace needs at least one REORDER_INITIATED event.')
    insert_after = reorder_rows[0]

    # Insert a copied order record immediately after the original, before its
    # matching receipt. Re-index the copy without changing the original frame,
    # and remap related-demand references so the mutation remains isolated to
    # the duplicate-order defect.
    staged: list[tuple[dict, int | None]] = []
    first_reorder_old_index = int(df.at[insert_after, 'event_index']) if 'event_index' in df.columns else insert_after
    for position, (_, row) in enumerate(df.iterrows()):
        item = row.to_dict()
        old_index = int(item['event_index']) if 'event_index' in item and pd.notna(item['event_index']) else position
        staged.append((item, old_index))
        if position == insert_after:
            duplicate = item.copy()
            staged.append((duplicate, None))

    old_to_new: dict[int, int] = {}
    for new_index, (item, old_index) in enumerate(staged):
        item['event_index'] = new_index
        if old_index is not None:
            old_to_new[old_index] = new_index
    new_rows = [item for item, _ in staged]
    mutated = pd.DataFrame(new_rows)
    if 'related_demand_event_index' in mutated.columns:
        original_refs = mutated['related_demand_event_index'].copy()
        remapped = []
        for ref in original_refs:
            if pd.isna(ref):
                remapped.append(ref)
            else:
                remapped.append(old_to_new.get(int(ref), ref))
        mutated['related_demand_event_index'] = remapped
    return mutated.reset_index(drop=True)


def build_mutation_cases(events: pd.DataFrame) -> list[MutationCase]:
    """Return five targeted defect cases; each mutation gets its own copy."""
    return [
        MutationCase(
            mutation_id='M01',
            description='Fulfilled quantity greater than requested quantity',
            mutated_field='fulfilled_quantity on one DEMAND row',
            expected_audit_checks=('Per-demand fulfilment bounds', 'Per-demand demand conservation'),
            expected_verification_ids=('V03',),
            mutate=_mutate_fulfilled_exceeds_request,
        ),
        MutationCase(
            mutation_id='M02',
            description='Unmet quantity no longer equals requested minus fulfilled',
            mutated_field='unmet_quantity on one DEMAND row',
            expected_audit_checks=('Per-demand demand conservation',),
            expected_verification_ids=('V10',),
            mutate=_mutate_unmet_relation,
        ),
        MutationCase(
            mutation_id='M03',
            description='Terminal cumulative-unmet total does not reconcile',
            mutated_field='cumulative_unmet on END row',
            expected_audit_checks=('Cumulative unmet equals summed demand shortfalls',),
            expected_verification_ids=('V11',),
            mutate=_mutate_cumulative_unmet,
        ),
        MutationCase(
            mutation_id='M04',
            description='Replenishment arrives one hour earlier than scheduled',
            mutated_field='simulation_time on one REPLENISHMENT_ARRIVAL row',
            expected_audit_checks=('Replenishment arrival matches scheduled time',),
            expected_verification_ids=('V04',),
            mutate=_mutate_arrival_early,
        ),
        MutationCase(
            mutation_id='M05',
            description='Duplicate reorder inserted while the original order is pending',
            mutated_field='one duplicate REORDER_INITIATED event row',
            expected_audit_checks=('No duplicate reorder while order pending',),
            expected_verification_ids=('V05',),
            mutate=_mutate_duplicate_pending_order,
        ),
    ]
