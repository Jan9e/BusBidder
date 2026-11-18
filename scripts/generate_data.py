"""Generate a reproducible BusBidder dataset.

Run from project root:  python scripts/generate_data.py
Outputs: data/companies.csv, data/destinations.csv, data/offers.csv
The last rows are intentionally invalid for the validation demo.
"""

from __future__ import annotations

import csv
import random
from datetime import date, time, timedelta
from pathlib import Path

random.seed(42)

DATA = Path(__file__).resolve().parent.parent / "data"
DATA.mkdir(exist_ok=True)

COMPANIES = [
    ("SolRuta",          "Low-cost daytime services",                 True,  False),
    ("Camino Express",   "Fast direct connections between major cities", False, False),
    ("CostaLink",        "Strong coverage of coastal destinations",   False, False),
    ("VerdeBus",         "Environment-focused, modern vehicles",      False, True),
    ("NocheVia",         "Overnight and late-evening services",       False, False),
]

DESTINATIONS = [
    ("Barcelona", True), ("Valencia", True), ("Seville", True),
    ("Malaga", True), ("Granada", True), ("Alicante", True),
    ("Cadiz", True),
    ("Cordoba", False), ("Bilbao", False), ("San Sebastian", False),
    ("Murcia", False), ("Salamanca", False), ("Toledo", False),
    ("Zaragoza", False), ("Santiago de Compostela", False),
]

COASTAL = {n for n, c in DESTINATIONS if c}

DEPARTURE_WINDOWS = {
    "morning":   (6, 12),
    "afternoon": (12, 18),
    "evening":   (18, 23),
    "night":     (23, 24),
}

TRAVEL_DATES = [date(2026, 12, 13) + timedelta(days=i) for i in range(3)]


def write_csv(path: Path, header: list[str], rows: list[list]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def make_fare(company: str, low_cost: bool) -> tuple[bool, bool, float, float]:
    if company == "Camino Express":
        return True, True, 5.0, 10.0
    if company == "VerdeBus":
        return True, False, 8.0, 0.0
    if low_cost:
        return (random.random() < 0.35,
                random.random() < 0.20,
                15.0, 20.0)
    return (random.random() < 0.6,
            random.random() < 0.4,
            10.0, 15.0)


def make_offer(company, low_cost, eco, destination, coastal,
               travel_date, window_name) -> list:
    start_h, end_h = DEPARTURE_WINDOWS[window_name]
    dep_hour = random.randint(start_h, end_h - 1)
    dep_min = random.choice([0, 15, 30, 45])

    base = 240 if coastal else 200
    if company == "Camino Express":
        base -= 60
    if eco:
        base += 20
    if window_name == "night":
        base += 30
    duration = base + random.randint(-20, 40)

    dep = time(dep_hour, dep_min)
    arr_total_min = dep_hour * 60 + dep_min + duration
    arr_h = (arr_total_min // 60) % 24
    arr_m = arr_total_min % 60
    arr = time(arr_h, arr_m)
    arrival_date = travel_date + timedelta(days=arr_total_min // (24 * 60))

    if low_cost:
        price = 20 + random.uniform(0, 15)
    elif company == "Camino Express":
        price = 40 + random.uniform(0, 20)
    elif eco:
        price = 38 + random.uniform(0, 18)
    else:
        price = 28 + random.uniform(0, 20)
    if window_name == "night":
        price -= 5
    price = round(max(12.0, price), 2)

    transfers = 0 if company in ("Camino Express", "VerdeBus") \
                else random.choice([0, 0, 1, 1, 2])
    luggage = random.choice([10, 15, 20, 23])
    changeable, refundable, cf, rf = make_fare(company, low_cost)
    seats = random.randint(0 if random.random() < 0.05 else 3, 40)
    rating = round(random.uniform(3.0 if low_cost else 3.6, 4.9), 1)
    emissions = round(duration * 0.09 * (0.55 if eco else 1.0), 1) \
                if random.random() < 0.9 else ""

    offer_id = (f"OFF-{company[:3].upper()}-{destination[:3].upper()}-"
                f"{travel_date:%m%d}-{dep_hour:02d}{dep_min:02d}")

    return [
        offer_id, company, "Madrid", destination,
        travel_date.isoformat(),
        dep.strftime("%H:%M"), arr.strftime("%H:%M"),
        duration, f"{price:.2f}", transfers, luggage,
        str(changeable), str(refundable), f"{cf:.2f}", f"{rf:.2f}",
        seats, rating, emissions, arrival_date.isoformat(),
    ]


companies_rows = [[n, p, str(lc), str(e)] for n, p, lc, e in COMPANIES]
dest_rows = [[n, str(c)] for n, c in DESTINATIONS]

OFFER_HEADER = [
    "offer_id", "company", "origin", "destination", "travel_date",
    "departure_time", "arrival_time", "duration_minutes", "price_eur",
    "transfers", "luggage_kg", "changeable", "refundable",
    "change_fee_eur", "refund_fee_eur", "available_seats", "rating",
    "emissions_kg", "arrival_date",
]

offers: list[list] = []
for company, profile, low_cost, eco in COMPANIES:
    for dest_name, coastal in DESTINATIONS:
        if company == "CostaLink" and not coastal:
            continue
        windows = (["night"] if company == "NocheVia" and random.random() < 0.7
                   else random.sample(list(DEPARTURE_WINDOWS),
                                      k=random.choice([1, 2])))
        for window in windows:
            travel_date = random.choice(TRAVEL_DATES)
            offers.append(make_offer(
                company, low_cost, eco,
                dest_name, coastal, travel_date, window,
            ))

INVALID = [
    ["OFF-SOL-MAL-1231-0900", "SolRuta", "Madrid", "Malaga", "2026-12-31",
     "09:00", "13:30", 270, "-15.00", 0, 20, "True", "False", "0.00", "0.00",
     12, 4.2, "24.3", "2026-12-31"],
    ["OFF-SOL-ATL-1231-0900", "SolRuta", "Madrid", "Atlantis", "2026-12-31",
     "09:00", "13:30", 270, "25.00", 0, 20, "True", "False", "0.00", "0.00",
     12, 4.2, "24.3", "2026-12-31"],
    ["OFF-COS-VAL-1231-1500", "CostaLink", "Madrid", "Valencia", "2026-12-31",
     "15:00", "10:00", 300, "30.00", 0, 15, "True", "True", "5.00", "10.00",
     20, 4.0, "27.0", "2026-12-31"],
    ["OFF-VER-SEV-1231-0800", "VerdeBus", "Madrid", "Seville", "2026-12-31",
     "08:00", "14:00", 360, "42.00", 0, 20, "True", "False", "8.00", "0.00",
     10, "7.5", "32.4", "2026-12-31"],
    ["OFF-NOC-BAR-1231-2330", "NocheVia", "Madrid", "Barcelona", "2026-12-31",
     "23:30", "07:30", 480, "35.00", 0, 15, "False", "False", "15.00", "20.00",
     0, 3.8, "43.2", "2027-01-01"],
    ["OFF-CAM-TOL-1231-1000", "Camino Express", "Madrid", "Toledo", "not-a-date",
     "10:00", "11:30", 90, "45.00", 0, 20, "True", "True", "5.00", "10.00",
     8, 4.6, "8.1", "2026-12-31"],
    ["OFF-XXX-COR-1231-1100", "", "Madrid", "Cordoba", "2026-12-31",
     "11:00", "15:00", 240, "28.00", 1, 15, "False", "False", "15.00", "20.00",
     15, 3.5, "21.6", "2026-12-31"],
    ["OFF-COS-CAD-1231-0730", "CostaLink", "Madrid", "Cadiz", "2026-12-31",
     "07:30", "13:00", 330, "", 1, 15, "False", "False", "15.00", "20.00",
     20, 3.9, "29.7", "2026-12-31"],
    ["BADID-123", "SolRuta", "Madrid", "Granada", "2026-12-31",
     "10:00", "14:00", 240, "22.00", 0, 20, "True", "False", "0.00", "0.00",
     25, 4.1, "21.6", "2026-12-31"],
]

write_csv(DATA / "companies.csv",
          ["name", "profile", "low_cost", "eco_focus"], companies_rows)
write_csv(DATA / "destinations.csv", ["name", "coastal"], dest_rows)
write_csv(DATA / "offers.csv", OFFER_HEADER, offers + INVALID)

print(f"companies.csv      : {len(companies_rows)} rows")
print(f"destinations.csv   : {len(dest_rows)} rows")
print(f"offers.csv         : {len(offers)} valid + {len(INVALID)} invalid "
      f"= {len(offers)+len(INVALID)} rows")