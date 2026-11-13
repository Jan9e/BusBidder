"""explain.py — plain-English explanation generated from ranking data."""

from __future__ import annotations

from .models import RankedOffer


def _fare_label(offer) -> str:
    f = offer.fare
    if f.changeable and f.refundable:
        return "fully flexible (changeable + refundable)"
    if f.changeable:
        return "changeable"
    if f.refundable:
        return "refundable only"
    return "non-changeable, non-refundable"


def explain(ranked: RankedOffer, all_ranked: list[RankedOffer]) -> str:
    offer = ranked.offer
    if not all_ranked:
        return f"{offer.company.name} offer for EUR {offer.price_eur:.2f}."

    best_price = min(r.offer.price_eur for r in all_ranked)
    best_duration = min(r.offer.duration_minutes for r in all_ranked)

    parts: list[str] = []

    if offer.price_eur == best_price:
        parts.append(f"cheapest at EUR {offer.price_eur:.2f}")
    else:
        parts.append(f"EUR {offer.price_eur - best_price:.2f} above the cheapest")

    if offer.duration_minutes == best_duration:
        parts.append(f"fastest at {offer.duration_minutes} min")
    else:
        parts.append(f"{offer.duration_minutes - best_duration} min longer than the fastest")

    parts.append(_fare_label(offer))

    parts.append("direct route" if offer.transfers == 0
                 else f"{offer.transfers} transfer(s)")

    return (
        f"Rank {ranked.rank} (score {ranked.total_score:.2f}/100): "
        f"{offer.company.name} departs {offer.departure_time:%H:%M} on "
        f"{offer.travel_date}; " + ", ".join(parts) + "."
    )