"""Demo: rank Madrid → Malaga offers under the default weights.

Run:  python3 scripts/demo_ranking.py
Outputs a table suitable for pasting into report Section 5.4.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from busbidder.data_loader import load_all
from busbidder.models import Weights
from busbidder.ranking import score_offers, domination_warning

DATA = Path(__file__).resolve().parent.parent / "data"


def main() -> None:
    result = load_all(DATA)
    print(result.summary(), "\n")

    offers = [o for o in result.offers if o.destination.name == "Malaga"]
    print(f"Madrid → Malaga offers in window: {len(offers)}\n")
    if not offers:
        print("No Malaga offers — widen the filter and rerun.")
        return

    weights = Weights(price=0.40, duration=0.25,
                      departure=0.15, flexibility=0.20)
    warn = domination_warning(weights)
    if warn:
        print(f"WARNING: {warn}\n")

    ranked = score_offers(offers, weights, preferred_departure="morning")

    header = (
        f"{'#':>2}  {'Company':<16} {'Date':<11} {'Dep':>5} "
        f"{'Dur':>5} {'Price':>7} {'Tr':>3} {'Flex':>5} "
        f"| {'P':>5} {'D':>5} {'T':>5} {'F':>5} | {'Total':>6}"
    )
    print(header)
    print("-" * len(header))
    for r in ranked:
        o = r.offer
        cs = r.criterion_scores
        print(
            f"{r.rank:>2}  {o.company.name:<16} "
            f"{o.travel_date.isoformat():<11} "
            f"{o.departure_time:%H:%M} ".rjust(6),
            f"{o.duration_minutes:>5} "
            f"{o.price_eur:>7.2f} "
            f"{o.transfers:>3} "
            f"{o.fare.flexibility_score():>5.0f} "
            f"| {cs.get('price',0):>5.1f} "
            f"{cs.get('duration',0):>5.1f} "
            f"{cs.get('departure',0):>5.1f} "
            f"{cs.get('flexibility',0):>5.1f} "
            f"| {r.total_score:>6.2f}"
        )
    print("\nLegend: P=price, D=duration, T=departure time, F=flexibility.")
    print("Raw values left of the bar; normalised scores (0-100) right.")


if __name__ == "__main__":
    main()