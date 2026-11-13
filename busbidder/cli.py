"""cli.py — interactive command-line interface for BusBidder Spain."""

from __future__ import annotations

import json
import logging
import sys
from datetime import date
from pathlib import Path

from .booking import append_booking, create_booking
from .data_loader import LoadResult, configure_logging, load_all
from .exceptions import BookingError, WeightValidationError
from .explain import explain
from .filtering import filter_offers
from .models import Booking, TravelRequest, Weights
from .ranking import domination_warning, score_offers

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
LOG_PATH = PROJECT_ROOT / "logs" / "app.log"
BOOKINGS_PATH = DATA_DIR / "bookings.jsonl"
PROFILES_PATH = DATA_DIR / "profiles.json"

WEIGHT_KEYS = ("price", "duration", "departure", "flexibility",
               "transfers", "rating", "emissions")


# ---------- prompt helpers ----------

def _prompt(prompt: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default is not None and default != "" else ""
    raw = input(f"{prompt}{suffix}: ").strip()
    if not raw and default is not None:
        return default
    return raw


def _prompt_int(prompt, default=None, minimum=None, maximum=None):
    while True:
        raw = _prompt(prompt, str(default) if default is not None else None)
        try:
            v = int(raw)
        except ValueError:
            print("  please enter an integer"); continue
        if minimum is not None and v < minimum:
            print(f"  must be >= {minimum}"); continue
        if maximum is not None and v > maximum:
            print(f"  must be <= {maximum}"); continue
        return v


def _prompt_float(prompt, default=None, minimum=None, maximum=None):
    while True:
        raw = _prompt(prompt, f"{default:g}" if default is not None else None)
        try:
            v = float(raw)
        except ValueError:
            print("  please enter a number"); continue
        if minimum is not None and v < minimum:
            print(f"  must be >= {minimum}"); continue
        if maximum is not None and v > maximum:
            print(f"  must be <= {maximum}"); continue
        return v


def _prompt_bool(prompt, default=None):
    opts = {True: "Y/n", False: "y/N", None: "y/n"}[default]
    while True:
        raw = _prompt(f"{prompt} ({opts})")
        if not raw and default is not None:
            return default
        if raw.lower() in ("y", "yes"): return True
        if raw.lower() in ("n", "no"):  return False
        print("  please answer y or n")


def _prompt_date(prompt, default=None):
    while True:
        raw = _prompt(prompt, default.isoformat() if default else None)
        try:
            return date.fromisoformat(raw)
        except ValueError:
            print("  format must be YYYY-MM-DD")


def _prompt_choice(prompt, choices, default=None):
    print(prompt)
    for i, c in enumerate(choices, 1):
        marker = " (default)" if c == default else ""
        print(f"  {i}) {c}{marker}")
    while True:
        raw = _prompt("number")
        if not raw and default is not None:
            return default
        if raw.isdigit() and 1 <= int(raw) <= len(choices):
            return choices[int(raw) - 1]
        print("  invalid choice")


def _prompt_destination(destinations: dict, default=None) -> str:
    return _prompt_choice("Destination:", sorted(destinations.keys()), default=default)


def _prompt_weights(defaults: dict) -> Weights:
    """Rate each criterion 0-10; normalise to 1.0 automatically."""
    suggested = {k: round(defaults.get(k, 0.0) * 10) for k in WEIGHT_KEYS}

    print("\nRate how much each criterion matters to you.")
    print("  0 = don't care,  10 = crucial,  Enter = keep the suggestion.\n")
    print("  Suggested ratings:")
    for k in WEIGHT_KEYS:
        print(f"    {k:<12} {suggested[k]}")
    print()

    relative: dict[str, float] = {}
    for k in WEIGHT_KEYS:
        while True:
            raw = input(f"  {k:<12}: ").strip()
            if raw == "":
                v = float(suggested[k])
            else:
                try:
                    v = float(raw)
                except ValueError:
                    print("    enter a whole number 0-10"); continue
                if not (0 <= v <= 10):
                    print("    must be between 0 and 10"); continue
            relative[k] = v
            break

    total = sum(relative.values())
    if total <= 0:
        print("\n  All ratings are zero — using defaults instead.\n")
        return Weights(**defaults)

    normalised = {k: relative[k] / total for k in WEIGHT_KEYS}

    print("\nYour preference weights:")
    for k in WEIGHT_KEYS:
        bar = "█" * int(round(normalised[k] * 40))
        print(f"  {k:<12} {normalised[k]*100:5.1f}%  {bar}")
    print(f"  {'─' * 50}")
    print(f"  {'total':<12} 100.0%")

    w = Weights(**normalised)
    w.validate()
    return w


# ---------- request builders ----------

def _build_request(base_constraints, base_weights, destinations) -> TravelRequest | None:
    destination = _prompt_destination(destinations, default="Malaga")
    ws = _prompt_date("Travel window start (YYYY-MM-DD)", date(2026, 7, 12))
    we = _prompt_date("Travel window end (YYYY-MM-DD)",   date(2026, 7, 14))
    budget = _prompt_float("Maximum budget (EUR)",
                           base_constraints.get("max_budget_eur", 50.0), minimum=1.0)
    transfers = _prompt_int("Maximum transfers",
                            base_constraints.get("max_transfers", 1), minimum=0, maximum=5)
    luggage = _prompt_int("Minimum luggage (kg)",
                          base_constraints.get("min_luggage_kg", 0), minimum=0, maximum=50)
    requires_changeable = _prompt_bool("Changeable ticket required?",
                                       base_constraints.get("requires_changeable", False))
    preferred = _prompt_choice("Preferred departure window:",
                               ["morning", "afternoon", "evening", "night"],
                               default=base_constraints.get("preferred_departure", "morning"))
    dur_raw = _prompt("Maximum duration in minutes (blank = any)",
                      str(base_constraints.get("max_duration_minutes") or ""))
    max_duration = int(dur_raw) if dur_raw else None

    weights = _prompt_weights(base_weights)

    req = TravelRequest(
        origin="Madrid", destination=destination,
        window_start=ws, window_end=we,
        max_budget_eur=budget, max_transfers=transfers,
        min_luggage_kg=luggage, requires_changeable=requires_changeable,
        preferred_departure=preferred, max_duration_minutes=max_duration,
        weights=weights,
    )
    try:
        req.validate()
    except WeightValidationError as e:
        print(f"\n  invalid request: {e}")
        print("  (returning to menu)")
        return None
    return req


def _request_from_profile(profile, destinations) -> TravelRequest | None:
    try:
        print(f"\nProfile: {profile['label']}")
        print(f"  {profile['description']}")
        c, w = profile["constraints"], profile["weights"]
        print(f"  Max budget: EUR {c['max_budget_eur']:.2f}")
        print(f"  Max transfers: {c['max_transfers']}")
        print(f"  Luggage >= {c['min_luggage_kg']} kg")
        print(f"  Changeable required: {c['requires_changeable']}")
        print(f"  Preferred departure: {c['preferred_departure']}")
        print("  Weights: " + " ".join(f"{k}={w[k]:.2f}" for k in WEIGHT_KEYS if w.get(k)))

        if not _prompt_bool("Accept these defaults and continue?", default=True):
            return _build_request(c, w, destinations)

        destination = _prompt_destination(destinations, default="Malaga")
        ws = _prompt_date("Travel window start", date(2026, 7, 12))
        we = _prompt_date("Travel window end",   date(2026, 7, 14))

        req = TravelRequest(
            origin="Madrid", destination=destination,
            window_start=ws, window_end=we,
            max_budget_eur=c["max_budget_eur"],
            max_transfers=c["max_transfers"],
            min_luggage_kg=c["min_luggage_kg"],
            requires_changeable=c["requires_changeable"],
            preferred_departure=c["preferred_departure"],
            max_duration_minutes=c["max_duration_minutes"],
            weights=Weights(**w),
        )
        req.validate()
        return req
    except (KeyboardInterrupt, EOFError):
        print("\n(cancelled — returning to menu)")
        return None


def _request_custom(destinations) -> TravelRequest | None:
    defaults = {
        "max_budget_eur": 50.0, "max_transfers": 1, "min_luggage_kg": 0,
        "requires_changeable": False, "preferred_departure": "morning",
        "max_duration_minutes": None,
    }
    weights = {"price": 0.40, "duration": 0.25, "departure": 0.15,
               "flexibility": 0.20, "transfers": 0.0, "rating": 0.0, "emissions": 0.0}
    try:
        return _build_request(defaults, weights, destinations)
    except (KeyboardInterrupt, EOFError):
        print("\n(cancelled — returning to menu)")
        return None


# ---------- display ----------

def _show_ranked(request: TravelRequest, data: LoadResult,
                 bookings: dict[str, Booking]) -> None:
    fr = filter_offers(data.offers, request)
    print(f"\n{fr.summary()}")
    if not fr.passing:
        print("No offers passed all hard constraints. Loosen your request and retry.")
        return

    print("\nRejections by constraint:")
    for label, count in sorted(fr.reason_counts().items()):
        print(f"  {label:<15} {count:>3}")

    warn = domination_warning(request.weights)
    if warn:
        print(f"\nWARNING: {warn}")

    ranked = score_offers(fr.passing, request.weights, request.preferred_departure)

    print(f"\nRanked offers ({len(ranked)}):\n")
    header = (f"{'#':>2}  {'Company':<16} {'Date':<11} {'Dep':^5} "
              f"{'Dur':>5} {'Price':>7} {'Tr':>3} {'Chg':>3} {'Ref':>3} {'Flx':>4} | {'Total':>6}")
    print(header); print("-" * len(header))
    for r in ranked:
        o = r.offer
        chg = "Y" if o.fare.changeable else "N"
        ref = "Y" if o.fare.refundable else "N"
        print(f"{r.rank:>2}  {o.company.name:<16} {o.travel_date.isoformat():<11} "
              f"{o.departure_time:%H:%M} {o.duration_minutes:>5} "
              f"{o.price_eur:>7.2f} {o.transfers:>3} "
              f"{chg:>3} {ref:>3} {o.fare.flexibility_score():>4.0f} | {r.total_score:>6.2f}")

    print("\nExplanation for rank 1:")
    print(f"  {explain(ranked[0], ranked)}")

    try:
        while True:
            ans = _prompt("\nBook one of these offers? Enter rank number, or 'n' to skip", "n")
            if ans.lower() == "n":
                return
            if not ans.isdigit() or not (1 <= int(ans) <= len(ranked)):
                print("  enter a rank number, or 'n'"); continue
            chosen = ranked[int(ans) - 1].offer
            name = _prompt("Traveller name")
            try:
                booking = create_booking(chosen, name, bookings)
            except BookingError as e:
                print(f"  booking failed: {e}"); continue
            append_booking(booking, BOOKINGS_PATH)
            _print_confirmation(booking)
            return
    except (KeyboardInterrupt, EOFError):
        print("\n(booking cancelled)")
        return


def _print_confirmation(booking: Booking) -> None:
    o = booking.offer
    print("\n" + "=" * 56)
    print("  BOOKING CONFIRMED")
    print("=" * 56)
    print(f"  Reference:    {booking.reference}")
    print(f"  Traveller:    {booking.traveller_name}")
    print(f"  Company:      {o.company.name}")
    print(f"  Route:        {o.origin.name} -> {o.destination.name}")
    print(f"  Date:         {o.travel_date}  {o.departure_time:%H:%M} - {o.arrival_time:%H:%M}")
    print(f"  Duration:     {o.duration_minutes} min")
    print(f"  Price:        EUR {o.price_eur:.2f}")
    print(f"  Fare:         changeable={o.fare.changeable} refundable={o.fare.refundable}")
    print(f"  Transfers:    {o.transfers}")
    print(f"  Luggage:      {o.luggage_kg} kg")
    print(f"  Payment:      {booking.payment_status}")
    print(f"  Status:       {booking.status}")
    print(f"  Created:      {booking.created_at:%Y-%m-%d %H:%M:%S}")
    print("=" * 56)


# ---------- entry point ----------

def main() -> int:
    configure_logging(LOG_PATH, level=logging.INFO)
    try:
        data = load_all(DATA_DIR)
        profiles = json.loads(PROFILES_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"startup failed: {e}")
        return 1

    print("=" * 56)
    print("  BusBidder Spain")
    print("=" * 56)
    print(f"  Loaded: {data.summary()}")

    bookings: dict[str, Booking] = {}
    profile_keys = list(profiles.keys())

    while True:
        print("\nHow do you want to start?")
        for i, key in enumerate(profile_keys, 1):
            print(f"  {i}) {profiles[key]['label']}")
        print(f"  {len(profile_keys)+1}) Custom request")
        print("  0) Quit")

        try:
            choice = _prompt("\nChoice")
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye.")
            return 0

        if choice == "0":
            print("Goodbye."); return 0
        if not choice.isdigit():
            print("  enter a number"); continue
        n = int(choice)
        if 1 <= n <= len(profile_keys):
            req = _request_from_profile(profiles[profile_keys[n-1]], data.destinations)
        elif n == len(profile_keys) + 1:
            req = _request_custom(data.destinations)
        else:
            print("  invalid choice"); continue

        if req is None:
            continue
        _show_ranked(req, data, bookings)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrupted. Goodbye.")
        sys.exit(130)