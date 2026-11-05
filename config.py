from dataclasses import dataclass
from core import InventoryThresholds


@dataclass
class PrototypeConfig:
    """Configuration for the RPD feasibility prototype.

    IMPORTANT: All default operational values are illustrative feasibility values only.
    They are NOT thesis parameter estimates and must be replaced/justified after RO1.
    """

    initial_stock: float = 100.0
    reorder_threshold: float = 30.0
    replenishment_quantity: float = 80.0
    replenishment_lead_time_hours: float = 24.0
    thresholds: InventoryThresholds = InventoryThresholds(low=40.0, critical=15.0)
    allow_partial_fulfilment: bool = True
    mean_interarrival_hours: float = 6.0
    demand_values: tuple = (5.0, 10.0, 15.0)
    demand_probabilities: tuple = (0.3, 0.5, 0.2)
    horizon_hours: float = 168.0
    seed: int = 20261008
    # Debug/verification control, not an operational parameter.
    demand_enabled: bool = True
    # Optional workload-driven mode: each simulated patient may generate one request.
    demand_mode: str = "rate"  # "rate" or "patient_volume"
    patient_volume: int = 100
    patient_demand_probability: float = 0.5

    def validate(self) -> None:
        if self.initial_stock < 0:
            raise ValueError("initial_stock must be non-negative")
        if self.reorder_threshold < 0:
            raise ValueError("reorder_threshold must be non-negative")
        if self.replenishment_quantity <= 0:
            raise ValueError("replenishment_quantity must be > 0 for this prototype")
        if self.replenishment_lead_time_hours < 0:
            raise ValueError("replenishment_lead_time_hours must be non-negative")
        if self.demand_mode not in {"rate", "patient_volume"}:
            raise ValueError("demand_mode must be rate or patient_volume")
        if self.patient_volume < 0:
            raise ValueError("patient_volume must be non-negative")
        if not 0 <= self.patient_demand_probability <= 1:
            raise ValueError("patient_demand_probability must be between 0 and 1")
        if self.mean_interarrival_hours <= 0:
            raise ValueError("mean_interarrival_hours must be > 0")
        if self.horizon_hours <= 0:
            raise ValueError("horizon_hours must be > 0")
        if self.thresholds.critical < 0 or self.thresholds.low < 0:
            raise ValueError("state thresholds must be non-negative")
        if self.thresholds.critical > self.thresholds.low:
            raise ValueError("critical threshold cannot exceed low threshold")
        if len(self.demand_values) == 0:
            raise ValueError("demand_values cannot be empty")
        if len(self.demand_values) != len(self.demand_probabilities):
            raise ValueError("demand_values and demand_probabilities must have equal length")
        if any(v < 0 for v in self.demand_values):
            raise ValueError("demand values must be non-negative")
        if any(p < 0 for p in self.demand_probabilities):
            raise ValueError("demand probabilities must be non-negative")
        total = float(sum(self.demand_probabilities))
        if abs(total - 1.0) > 1e-9:
            raise ValueError("demand probabilities must sum to 1")
