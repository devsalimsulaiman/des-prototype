from dataclasses import dataclass
from typing import Tuple

@dataclass(frozen=True)
class InventoryThresholds:
    low: float
    critical: float


def classify_state(stock: float, thresholds: InventoryThresholds) -> str:
    if stock <= 0:
        return "UNAVAILABLE"
    if stock <= thresholds.critical:
        return "CRITICAL"
    if stock <= thresholds.low:
        return "LOW"
    return "AVAILABLE"


def fulfil_demand(stock: float, demand: float, allow_partial: bool = True) -> Tuple[float, float, float]:
    if stock < 0 or demand < 0:
        raise ValueError("stock and demand must be non-negative")
    if allow_partial:
        fulfilled = min(stock, demand)
    else:
        fulfilled = demand if stock >= demand else 0.0
    unmet = demand - fulfilled
    new_stock = stock - fulfilled
    if new_stock < -1e-12:
        raise AssertionError("inventory became negative")
    return fulfilled, unmet, max(0.0, new_stock)


def should_reorder(stock: float, reorder_threshold: float, order_pending: bool) -> bool:
    if reorder_threshold < 0:
        raise ValueError("reorder_threshold must be non-negative")
    return (stock <= reorder_threshold) and (not order_pending)


def apply_replenishment(stock: float, quantity: float) -> float:
    if stock < 0 or quantity < 0:
        raise ValueError("stock and replenishment quantity must be non-negative")
    return stock + quantity
