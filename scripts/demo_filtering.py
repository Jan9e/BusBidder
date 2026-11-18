"""Demo: apply hard constraints for Madrid → Malaga, 12-14 July, budget 50.

Run:  python3 scripts/demo_filtering.py
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from busbidder.data_loader import load_all
from busbidder.filtering import filter_offers
from busbidder.models import TravelRequest, Weights

DATA = Path(__file__).resolve().parent.parent / "data"


def main() -> None:
    result = load_all(DATA)
    print(result.summary(), "\n")

    request = TravelRequest(
        origin="Madrid",
        destination="Malaga",
        window_start=date(2026, 12, 13),
        window_end=date(2026, 12, 15),
        max_budget_eur=50.0,
        max_transfers=1,
        min_luggage_kg=0,
        requires_changeable=True,
        preferred_departure="morning",
        max_duration_minutes=None,
        weights=Weights(price=0.40, duration=0.25,
                        departure=0.15, flexibility=0.20),
    )
    request.validate()
    print(
        f"Request: {request.origin} -> {request.destination}, "
        f"{request.window_start} to {request.window_end}, "
        f"budget EUR {request.max_budget_eur:.2f}, "
        f"max transfers {request.max_transfers}, "
        f"changeable={'required' if request.requires_changeable else 'optional'}\n"
    )

    fr = filter_offers(result.offers, request)
    print(fr.summary(), "\n")

    print("Passing offers:")
    header = (
        f"  {'Company':<16} {'Date':<11} {'Dep':>5} {'Dur':>5} "
        f"{'Price':>7} {'Tr':>3} {'Lug':>4} {'Chg':>4}"
    )
    print(header)
    print("  " + "-" * (len(header) - 2))
    for o in fr.passing:
        dep = o.departure_time.strftime("%H:%M")
        print(
            f"  {o.company.name:<16} {o.travel_date.isoformat():<11} "
            f"{dep:>5} {o.duration_minutes:>5} "
            f"{o.price_eur:>7.2f} {o.transfers:>3} "
            f"{o.luggage_kg:>4} {str(o.fare.changeable):>4}"
        )

    if fr.filtered:
        print("\nRejections by constraint:")
        for label, count in sorted(fr.reason_counts().items()):
            print(f"  {label:<15} {count:>3}")

        print("\nRejected offers:")
        for f in fr.filtered:
            print(f"  {f.offer.offer_id}  ({f.offer.company.name})")
            for r in f.reasons:
                print(f"    - {r}")


if __name__ == "__main__":
    main()