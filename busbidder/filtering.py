"""filtering.py — hard-constraint filtering for BusBidder Spain.

Design (report Section 2.2 / 5.1):
- Hard constraints REMOVE offers before ranking. A violation is not
  "scored lower" — the offer becomes unacceptable.
- The HARD/SOFT split is documented in report Section 2.2. This module
  only implements the HARD side; soft preferences live in ranking.py.
- Every constraint is checked for every offer (no short-circuit) so the
  report can produce a per-constraint breakdown of why offers failed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .models import Offer, TravelRequest


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class FilteredOut:
    offer: Offer
    reasons: list[str]           # one entry per violated constraint


@dataclass
class FilterResult:
    passing: list[Offer]
    filtered: list[FilteredOut] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"{len(self.passing)} offer(s) pass all hard constraints; "
            f"{len(self.filtered)} filtered out"
        )

    def reason_counts(self) -> dict[str, int]:
        """Count how many offers were rejected per constraint label."""
        counts: dict[str, int] = {}
        for f in self.filtered:
            for reason in f.reasons:
                label = reason.split(":", 1)[0]
                counts[label] = counts.get(label, 0) + 1
        return counts


# ---------------------------------------------------------------------------
# Individual constraint checks
# Each returns None if satisfied, or a short reason string if violated.
# ---------------------------------------------------------------------------

def _check_origin(offer: Offer, request: TravelRequest) -> str | None:
    if offer.origin.name != request.origin:
        return f"origin: {offer.origin.name} != {request.origin}"
    return None


def _check_destination(offer: Offer, request: TravelRequest) -> str | None:
    if offer.destination.name != request.destination:
        return f"destination: {offer.destination.name} != {request.destination}"
    return None


def _check_travel_window(offer: Offer, request: TravelRequest) -> str | None:
    if not (request.window_start <= offer.travel_date <= request.window_end):
        return (
            f"travel window: {offer.travel_date} outside "
            f"[{request.window_start}, {request.window_end}]"
        )
    return None


def _check_budget(offer: Offer, request: TravelRequest) -> str | None:
    if offer.price_eur > request.max_budget_eur:
        return (
            f"budget: EUR {offer.price_eur:.2f} > "
            f"{request.max_budget_eur:.2f}"
        )
    return None


def _check_seats(offer: Offer, request: TravelRequest) -> str | None:
    if offer.available_seats <= 0:
        return f"seats: {offer.available_seats} <= 0"
    return None


def _check_transfers(offer: Offer, request: TravelRequest) -> str | None:
    if offer.transfers > request.max_transfers:
        return f"transfers: {offer.transfers} > {request.max_transfers}"
    return None


def _check_luggage(offer: Offer, request: TravelRequest) -> str | None:
    if offer.luggage_kg < request.min_luggage_kg:
        return (
            f"luggage: {offer.luggage_kg}kg < "
            f"{request.min_luggage_kg}kg"
        )
    return None


def _check_changeable(offer: Offer, request: TravelRequest) -> str | None:
    if request.requires_changeable and not offer.fare.changeable:
        return "changeable: ticket is not changeable"
    return None


def _check_max_duration(offer: Offer, request: TravelRequest) -> str | None:
    if request.max_duration_minutes is None:
        return None
    if offer.duration_minutes > request.max_duration_minutes:
        return (
            f"duration: {offer.duration_minutes}min > "
            f"{request.max_duration_minutes}min"
        )
    return None


CONSTRAINTS: tuple[Callable[[Offer, TravelRequest], str | None], ...] = (
    _check_origin,
    _check_destination,
    _check_travel_window,
    _check_budget,
    _check_seats,
    _check_transfers,
    _check_luggage,
    _check_changeable,
    _check_max_duration,
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def filter_offers(
    offers: list[Offer],
    request: TravelRequest,
) -> FilterResult:
    """Apply all hard constraints. Non-short-circuiting: record ALL failures."""
    passing: list[Offer] = []
    filtered: list[FilteredOut] = []
    for offer in offers:
        reasons = [r for check in CONSTRAINTS if (r := check(offer, request))]
        if reasons:
            filtered.append(FilteredOut(offer=offer, reasons=reasons))
        else:
            passing.append(offer)
    return FilterResult(passing=passing, filtered=filtered)