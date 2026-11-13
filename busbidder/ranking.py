"""ranking.py — weighted multi-criteria scoring for BusBidder Spain.

Design (report Section 5):
- Seven criteria; four mandatory (price, duration, departure, flexibility),
  three optional (transfers, rating, emissions).
- Every criterion is normalised to 0-100 before weighting so that euros,
  minutes, counts and categorical levels are comparable.
- Missing values drop the criterion for that offer and re-normalise the
  active weights — no penalty for absent optional data.
- A domination warning fires if any single weight exceeds 60%.

This module is pure: no file I/O, no printing. The CLI formats its output.
"""

from __future__ import annotations

import logging

from .models import Offer, RankedOffer, Weights

logger = logging.getLogger("busbidder.ranking")


CRITERIA = ("price", "duration", "departure", "flexibility",
            "transfers", "rating", "emissions")

LOWER_IS_BETTER = frozenset({"price", "duration", "transfers", "emissions"})

DEPARTURE_WINDOWS: dict[str, range] = {
    "morning":   range(6, 12),
    "afternoon": range(12, 18),
    "evening":   range(18, 23),
    "night":     range(23, 24),
}
WINDOW_ORDER = ("morning", "afternoon", "evening", "night")

MAX_SINGLE_WEIGHT = 0.60


# ---------------------------------------------------------------------------
# Normalisation primitives
# ---------------------------------------------------------------------------

def _min_max_lower(values: list[float]) -> list[float]:
    """Lower is better → best value gets 100, worst gets 0."""
    lo, hi = min(values), max(values)
    if hi == lo:
        return [100.0] * len(values)
    return [(hi - v) / (hi - lo) * 100.0 for v in values]


def _min_max_higher(values: list[float]) -> list[float]:
    """Higher is better → best value gets 100, worst gets 0."""
    lo, hi = min(values), max(values)
    if hi == lo:
        return [100.0] * len(values)
    return [(v - lo) / (hi - lo) * 100.0 for v in values]


def _departure_score(departure_hour: int, preferred: str) -> float:
    """100 in preferred window, 60 in an adjacent window, 20 otherwise."""
    if departure_hour in DEPARTURE_WINDOWS[preferred]:
        return 100.0
    dep_window = next(
        (w for w, hrs in DEPARTURE_WINDOWS.items() if departure_hour in hrs),
        None,
    )
    if dep_window is None:
        return 20.0
    distance = abs(WINDOW_ORDER.index(preferred) - WINDOW_ORDER.index(dep_window))
    return 60.0 if distance == 1 else 20.0


def _criterion_value(offer: Offer, criterion: str):
    if criterion == "price":
        return offer.price_eur
    if criterion == "duration":
        return offer.duration_minutes
    if criterion == "flexibility":
        return offer.fare.flexibility_score()
    if criterion == "transfers":
        return offer.transfers
    if criterion == "rating":
        return offer.rating
    if criterion == "emissions":
        return offer.emissions_kg
    raise ValueError(f"unknown criterion: {criterion}")


# ---------------------------------------------------------------------------
# Domination guard
# ---------------------------------------------------------------------------

def domination_warning(weights: Weights) -> str | None:
    """Return a warning string if any single weight exceeds 60%, else None."""
    wd = weights.as_dict()
    heaviest = max(wd, key=wd.get)
    if wd[heaviest] > MAX_SINGLE_WEIGHT:
        return (
            f"'{heaviest}' is weighted at {wd[heaviest]*100:.0f}%, "
            f"above the {MAX_SINGLE_WEIGHT*100:.0f}% guideline — "
            f"the ranking may be dominated by this one criterion."
        )
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_offers(
    offers: list[Offer],
    weights: Weights,
    preferred_departure: str,
) -> list[RankedOffer]:
    """Score and rank offers under the given weights.

    Raises WeightValidationError if weights are invalid.
    Returns an empty list for empty input.
    """
    weights.validate()
    if not offers:
        return []

    # 1. Gather raw values per criterion
    minmax_criteria = tuple(c for c in CRITERIA if c != "departure")
    raw: dict[str, dict[str, object]] = {c: {} for c in CRITERIA}
    for offer in offers:
        for c in minmax_criteria:
            raw[c][offer.offer_id] = _criterion_value(offer, c)
    # 2. Normalise each criterion to 0-100
    normalised: dict[str, dict[str, float | None]] = {}
    for c in CRITERIA:
        if c == "departure":
            normalised[c] = {
                o.offer_id: _departure_score(o.departure_hour(), preferred_departure)
                for o in offers
            }
            continue
        present = [raw[c][o.offer_id] for o in offers
                   if raw[c][o.offer_id] is not None]
        if not present:
            normalised[c] = {o.offer_id: None for o in offers}
            continue
        scores = (_min_max_lower(present) if c in LOWER_IS_BETTER
                  else _min_max_higher(present))
        mapping: dict[str, float | None] = {o.offer_id: None for o in offers}
        idx = 0
        for o in offers:
            if raw[c][o.offer_id] is not None:
                mapping[o.offer_id] = scores[idx]
                idx += 1
        normalised[c] = mapping

    # 3. Weight, sum, re-normalise per offer for missing criteria
    weight_dict = weights.as_dict()
    ranked: list[RankedOffer] = []
    for offer in offers:
        criterion_scores: dict[str, float] = {}
        active_weight = 0.0
        raw_total = 0.0
        for c in CRITERIA:
            w = weight_dict[c]
            if w == 0:
                continue
            s = normalised[c][offer.offer_id]
            if s is None:
                continue
            criterion_scores[c] = round(s, 2)
            active_weight += w
            raw_total += w * s
        total = (raw_total / active_weight) if active_weight > 0 else 0.0
        ranked.append(RankedOffer(
            offer=offer,
            criterion_scores=criterion_scores,
            total_score=round(total, 2),
        ))

    # 4. Deterministic sort
    ranked.sort(key=lambda r: (
        -r.total_score,
        r.offer.price_eur,
        -r.offer.rating,
        r.offer.offer_id,
    ))
    for position, r in enumerate(ranked, start=1):
        r.rank = position
    return ranked