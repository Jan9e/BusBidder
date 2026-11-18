"""Domain model for BusBidder Spain.

DESIGN (report Section 3.3):
- Frozen dataclasses for value objects (FareConditions, Weights) and
  stateful dataclasses for entities (Offer, Booking).
- COMPOSITION over inheritance: an Offer *has* FareConditions; a Booking
  *has* an Offer snapshot. No subclassing — offer types differ only in
  data, not behaviour, so inheritance would add no value (justified in 3.3.2).
- The domain layer knows nothing about files, CLI, or logging. That keeps
  it unit-testable and lets a web/GUI adapter be added later.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date, datetime, time
from typing import Optional

from .exceptions import WeightValidationError


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FareConditions:
    """Immutable bundle of ticket rules attached to every offer."""
    changeable: bool
    refundable: bool
    change_fee_eur: float = 0.0
    refund_fee_eur: float = 0.0

    def flexibility_score(self) -> float:
        """Categorical → 0-100 flexibility, used by the ranking engine."""
        if self.changeable and self.refundable:
            return 100.0
        if self.changeable:
            return 70.0
        if self.refundable:
            return 50.0
        return 20.0


@dataclass(frozen=True)
class Weights:
    """Traveller's relative importance for each scoring criterion.

    DESIGN: stored as fractions in [0,1] summing to 1.0. Validation lives
    here, not in the CLI, so any caller is protected.
    """
    price: float
    duration: float
    departure: float
    flexibility: float
    transfers: float = 0.0
    rating: float = 0.0
    emissions: float = 0.0

    TOLERANCE = 1e-6

    def as_dict(self) -> dict[str, float]:
        return {
            "price": self.price,
            "duration": self.duration,
            "departure": self.departure,
            "flexibility": self.flexibility,
            "transfers": self.transfers,
            "rating": self.rating,
            "emissions": self.emissions,
        }

    def validate(self) -> None:
        values = self.as_dict()
        for name, w in values.items():
            if not (0.0 <= w <= 1.0):
                raise WeightValidationError(
                    f"Weight '{name}' = {w} is outside [0, 1]."
                )
        total = sum(values.values())
        if abs(total - 1.0) > self.TOLERANCE:
            raise WeightValidationError(
                f"Weights sum to {total:.6f}, expected 1.0 (±{self.TOLERANCE})."
            )


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Destination:
    name: str
    coastal: bool


@dataclass(frozen=True)
class Company:
    name: str
    profile: str
    low_cost: bool
    eco_focus: bool


@dataclass
class Offer:
    """A single sellable offer from one company."""
    offer_id: str
    company: Company
    origin: Destination
    destination: Destination
    travel_date: date
    departure_time: time
    arrival_time: time
    duration_minutes: int
    price_eur: float
    transfers: int
    luggage_kg: int
    fare: FareConditions
    available_seats: int
    rating: float
    emissions_kg: Optional[float]

    def departure_hour(self) -> int:
        return self.departure_time.hour

    def __repr__(self) -> str:
        return (
            f"Offer({self.offer_id}, {self.company.name}, "
            f"{self.travel_date} {self.departure_time:%H:%M}, "
            f"EUR {self.price_eur:.2f})"
        )


@dataclass
class TravelRequest:
    """Everything the traveller asked for — constraints *and* preferences."""
    origin: str
    destination: str
    window_start: date
    window_end: date
    max_budget_eur: float
    max_transfers: int
    min_luggage_kg: int
    requires_changeable: bool
    preferred_departure: str
    max_duration_minutes: Optional[int]
    weights: Weights

    def validate(self) -> None:
        if self.window_end < self.window_start:
            raise WeightValidationError("Travel window end precedes start.")
        if self.max_budget_eur <= 0:
            raise WeightValidationError("Budget must be positive.")
        if self.preferred_departure not in {"morning", "afternoon", "evening", "night"}:
            raise WeightValidationError(
                f"Unknown preferred_departure '{self.preferred_departure}'."
            )
        self.weights.validate()


@dataclass
class RankedOffer:
    offer: Offer
    criterion_scores: dict[str, float]
    total_score: float
    rank: int = 0


@dataclass
class Booking:
    reference: str
    offer: Offer
    traveller_name: str
    created_at: datetime
    payment_status: str = "simulated-paid"
    status: str = "confirmed"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["offer"]["travel_date"] = self.offer.travel_date.isoformat()
        d["offer"]["departure_time"] = self.offer.departure_time.isoformat()
        d["offer"]["arrival_time"] = self.offer.arrival_time.isoformat()
        d["offer"]["available_seats"] = self.offer.available_seats  
        d["created_at"] = self.created_at.isoformat()
        return d