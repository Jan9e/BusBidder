# BusBidder Spain

A flexible bus-booking and weighted offer-ranking platform, developed for
ACIT4420 Problem-solving with scripting (OsloMet, 2026).

Given a traveller's hard constraints and soft preferences, the application
filters simulated bus offers from five fictional companies, ranks what
remains using a transparent weighted multi-criteria model, and produces
an explainable recommendation and a simulated booking.

---

## Quick start

**Run the application** (from the project root):

```bash
python3 -m busbidder
```

**Run the test suite:**

```bash
python3 -m pytest tests/ -v
```

The rest of this file documents requirements, structure, and design
decisions in more detail.

---

## Requirements

| Requirement | Version | Notes |
|---|---|---|
| **Python** | **3.10 or newer** | Uses PEP 604 (`int \| None`) type unions |
| **pytest** | 7.4 or newer | Only required for the test suite |

Runtime dependencies are **standard library only** — no third-party
packages are required to run the application. Modules used:
`csv`, `json`, `re`, `logging`, `dataclasses`, `secrets`, `datetime`,
`pathlib`, `typing`.

Install the test dependency once:

```bash
python3 -m pip install --user pytest
```

A pinned dependency list is provided in `requirements.txt`.

---

## Program entry point

The application entry point is `busbidder/__main__.py`, which delegates
to `busbidder/cli.py:main()`. Running:

```bash
python3 -m busbidder
```

is the **only** supported way to launch the application. There is no
`main.py` in the project root — the package's `__main__` module is the
canonical entry point, per Python convention.

---

## Running the application

From the project root:

```bash
python3 -m busbidder
```

The CLI presents four preset traveller profiles (Budget, Business,
Flexibility, Environment) plus a **Custom request** path where the
traveller sets every constraint and rates each criterion 0–10.

The application loads source data from `data/` at startup. Rejected rows
are logged to `logs/app.log` and do not block the load.

**Example session:**

```text
Choice: 1
  → Budget traveller profile
  → Accept defaults: y
  → Destination: Malaga
  → Travel window: 2026-07-12 to 2026-07-14
  → Ranked offers shown, rank 1 has an explanation
  → Book rank 1, enter traveller name
  → Confirmation with reference BB-XXXXXX
```

---

## Running the tests

From the project root:

```bash
python3 -m pytest tests/ -v
```

**Expected result:** `45 passed`.

The suite covers four required case types across every layer:

| Case type | Examples |
|---|---|
| **Normal** | valid loads, conforming offers, sorted rankings, bookings |
| **Invalid** | unknown destination, negative price, bad offer ID, bad weights |
| **Missing** | absent file, empty field, empty CSV |
| **Boundary** | price == budget, one offer, all-identical offers, zero seats |

Captured output is stored in `evidence/06_tests.txt`.

---

## Input file locations

All input data lives under `data/`, relative to the project root:

| File | Purpose |
|---|---|
| `data/companies.csv` | Five fictional bus companies (name, profile, low_cost, eco_focus) |
| `data/destinations.csv` | Fifteen destinations reachable from Madrid (name, coastal) |
| `data/offers.csv` | 99 valid offers + 9 deliberately invalid rows |
| `data/profiles.json` | Four preset traveller profiles with weights and constraints |
| `data/bookings.jsonl` | Append-only log of simulated bookings (created at first booking) |

## Output file locations

| File | Purpose |
|---|---|
| `logs/app.log` | Structured log of every load, validation and booking |
| `evidence/*.txt` | Captured outputs used as evidence in the project report |

---

## Regenerating the dataset

The shipped CSVs were produced by a seeded generator and are fully
reproducible:

```bash
python3 scripts/generate_data.py
```

`random.seed(42)` makes the output deterministic — the same 99 valid
offers and 9 intentionally invalid rows are regenerated on every run.

The last nine rows of `offers.csv` are seeded defects, one per validation
rule:

| Line | Defect | Expected rejection |
|---|---|---|
| 101 | Negative price | `InvalidValueError` |
| 102 | Unknown destination | `UnknownReferenceError` |
| 103 | Arrival inconsistent with departure + duration | `InconsistentDataError` |
| 104 | Rating outside 1–5 | `InvalidValueError` |
| 105 | Zero seats | `SoldOut` |
| 106 | Unparseable date | `InvalidValueError` |
| 107 | Empty company | `MissingDataError` |
| 108 | Missing price | `MissingDataError` |
| 109 | Malformed offer ID | `InvalidValueError` |

---

## Project structure

```text
busbidder/
├── busbidder/
│   ├── __init__.py
│   ├── __main__.py         # python3 -m busbidder entry point
│   ├── exceptions.py       # custom exception hierarchy
│   ├── models.py           # domain model (Offer, Booking, Weights, ...)
│   ├── data_loader.py      # CSV loading and validation
│   ├── filtering.py        # hard-constraint filtering
│   ├── ranking.py          # normalisation and weighted scoring
│   ├── explain.py          # explanation generator
│   ├── booking.py          # booking creation and persistence
│   └── cli.py              # command-line interface
├── scripts/
│   ├── generate_data.py    # deterministic dataset generator
│   ├── demo_ranking.py     # demo: rank Madrid → Malaga offers
│   └── demo_filtering.py   # demo: apply hard constraints
├── data/
│   ├── companies.csv
│   ├── destinations.csv
│   ├── offers.csv
│   ├── profiles.json
│   └── bookings.jsonl      # created on first booking
├── tests/
│   ├── conftest.py
│   ├── test_models.py
│   ├── test_data_loader.py
│   ├── test_filtering.py
│   ├── test_ranking.py
│   └── test_booking.py
├── evidence/               # captured outputs used in the report
├── logs/
│   └── app.log             # created on first run
├── requirements.txt
└── README.md
```

---

## Design notes

**The domain layer knows nothing about files, CLI, or logging.**
`models.py` imports only `exceptions.py`. This separation makes the
ranking engine unit-testable without constructing a CLI session, and
would allow a web or GUI adapter to be added later without touching the
ranking logic.

**Hard constraints vs soft preferences.** Hard constraints are enforced
in `filtering.py` **before** ranking — an offer that violates one is
removed, not merely scored lower. Soft preferences influence ranking
through the `Weights` object. The split is documented in report §2.2.
Changeability is a good example: it is a **soft preference** via
`FareConditions.flexibility_score()` (20/50/70/100) and a **hard
constraint** via `_check_changeable` — both, depending on what the
traveller requires.

**Weighted scoring.** Criteria are normalised to 0–100 with min-max
scaling and per-criterion direction (lower-is-better for price, duration,
transfers, emissions; higher-is-better for rating and flexibility).
Weights are validated to sum to 1.0 ± 1e-6 by `Weights.validate()`
**before** scoring. The domination guard warns (without blocking) if any
single weight exceeds 60%.

**Metaprogramming.** `ranking.CONSTRAINTS` is a tuple of pure functions
that act as a lightweight registry — adding a new hard constraint is a
one-function change plus one tuple entry, with no edits to
`filter_offers`. This is a deliberate design choice for extensibility.

---

## Reproducing report findings

The `evidence/` folder contains the captured outputs referenced in the
report:

| File | Captured from | Report section |
|---|---|---|
| `01_loader_rejections.txt` | `python3 -m busbidder.data_loader` | §4.7 |
| `02_ranking_table.txt` | `python3 scripts/demo_ranking.py` | §5.4 |
| `03_filtering_passes.txt` | `python3 scripts/demo_filtering.py` | §2.2, §5.1 |
| `05_cli_full_run.txt` | `python3 -m busbidder` | §5.3, §6.4, §6.5, §8 |
| `06_tests.txt` | `python3 -m pytest tests/ -v` | §7.2, §7.3 |
| `07_app_log.txt` | `cp logs/app.log evidence/` | §4.6 |

To regenerate any capture:

```bash
# loader rejections
python3 -m busbidder.data_loader > evidence/01_loader_rejections.txt 2>&1

# ranking table
python3 scripts/demo_ranking.py | tee evidence/02_ranking_table.txt

# filtering
python3 scripts/demo_filtering.py | tee evidence/03_filtering_passes.txt

# CLI (interactive — use tee to capture)
python3 -m busbidder | tee evidence/05_cli_full_run.txt

# tests
python3 -m pytest tests/ -v | tee evidence/06_tests.txt

# log file
cp logs/app.log evidence/07_app_log.txt
```

---

## Limitations

- **Simulated marketplace.** All five companies, offers, prices and
  schedules are fictional and generated deterministically. No real
  booking system is contacted.
- **Simulated payment.** No real payment information is collected or
  processed. `payment_status` is always `"simulated-paid"`.
- **Single-hub routing.** The data models Madrid as the only departure
  hub, per the specification. Multi-hub routes are not modelled.
- **No persistence of in-memory bookings across sessions.** Bookings are
  appended to `data/bookings.jsonl`, but the seat count in `offers.csv`
  is not rewritten — a fresh run starts from the seeded state. This is
  deliberate (the dataset is treated as immutable input) but means
  "seats remaining" reflects the original CSV, not cumulative bookings.
