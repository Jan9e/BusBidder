"""data_loader.py — file I/O and validation for BusBidder source data.

Responsibility (report Section 3.2): read the three CSVs, convert every
field to the correct type, validate ranges and cross-field consistency,
and return typed domain objects. No filtering, no ranking, no CLI.

Invalid-record policy (Section 4.7): QUARANTINE. Any row that fails a
validation rule is logged, appended to the returned `rejected` list, and
skipped. Valid rows load normally — one corrupt row never blocks the load.

Regex (Section 4.5): the `offer_id` is a structured identifier with a
fixed `OFF-CCC-DDD-MMDD-HHMM` format. Regex is the right tool here.
Free-text fields (company, destination) are validated by exact lookup,
not regex, because that gives better error messages.
"""

from __future__ import annotations

import csv
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path

from .exceptions import (
    DataError,
    InconsistentDataError,
    InvalidValueError,
    MissingDataError,
    UnknownReferenceError,
)
from .models import Company, Destination, FareConditions, Offer

logger = logging.getLogger("busbidder.data_loader")


OFFER_ID_RE = re.compile(r"^OFF-[A-Z]{3}-[A-Z]{3}-\d{4}-\d{4}$")
RATING_MIN, RATING_MAX = 1.0, 5.0

HUB = "Madrid"
_HUB_DESTINATION = Destination(name=HUB, coastal=False)

COMPANIES_HEADER    = ["name", "profile", "low_cost", "eco_focus"]
DESTINATIONS_HEADER = ["name", "coastal"]
OFFERS_HEADER = [
    "offer_id", "company", "origin", "destination", "travel_date",
    "departure_time", "arrival_time", "duration_minutes", "price_eur",
    "transfers", "luggage_kg", "changeable", "refundable",
    "change_fee_eur", "refund_fee_eur", "available_seats", "rating",
    "emissions_kg", "arrival_date",
]


@dataclass
class RejectedRow:
    line_number: int
    offer_id: str
    error_type: str
    reason: str


@dataclass
class LoadResult:
    companies: dict[str, Company]
    destinations: dict[str, Destination]
    offers: list[Offer]
    rejected: list[RejectedRow] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"loaded {len(self.companies)} companies, "
            f"{len(self.destinations)} destinations, "
            f"{len(self.offers)} offers; "
            f"rejected {len(self.rejected)} row(s)"
        )

    def rejected_by_type(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for r in self.rejected:
            counts[r.error_type] = counts.get(r.error_type, 0) + 1
        return counts


def configure_logging(log_path: Path, level: int = logging.INFO) -> None:
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    base = logging.getLogger("busbidder")
    base.setLevel(level)
    existing = {h.get_name() for h in base.handlers}
    if "busbidder-file" not in existing:
        fh = logging.FileHandler(log_path, mode="a", encoding="utf-8")
        fh.set_name("busbidder-file")
        fh.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
        ))
        base.addHandler(fh)
    if "busbidder-stderr" not in existing:
        sh = logging.StreamHandler()
        sh.set_name("busbidder-stderr")
        sh.setFormatter(logging.Formatter("%(levelname)-7s %(message)s"))
        sh.setLevel(logging.WARNING)
        base.addHandler(sh)


def _require(value, field_name: str, line: int) -> str:
    if value is None or str(value).strip() == "":
        raise MissingDataError(f"line {line}: '{field_name}' is required")
    return str(value).strip()


def _parse_bool(value, field_name: str, line: int) -> bool:
    v = _require(value, field_name, line).lower()
    if v in {"true", "1", "yes", "y"}:
        return True
    if v in {"false", "0", "no", "n"}:
        return False
    raise InvalidValueError(
        f"line {line}: '{field_name}'={value!r} is not a boolean"
    )


def _parse_int(value, field_name: str, line: int) -> int:
    v = _require(value, field_name, line)
    try:
        return int(v)
    except ValueError as e:
        raise InvalidValueError(
            f"line {line}: '{field_name}'={value!r} is not an integer"
        ) from e


def _parse_float(value, field_name: str, line: int, *, allow_blank: bool = False):
    if allow_blank and (value is None or str(value).strip() == ""):
        return None
    v = _require(value, field_name, line)
    try:
        return float(v)
    except ValueError as e:
        raise InvalidValueError(
            f"line {line}: '{field_name}'={value!r} is not a number"
        ) from e


def _parse_date(value, field_name: str, line: int) -> date:
    v = _require(value, field_name, line)
    try:
        return date.fromisoformat(v)
    except ValueError as e:
        raise InvalidValueError(
            f"line {line}: '{field_name}'={value!r} is not YYYY-MM-DD"
        ) from e


def _parse_time(value, field_name: str, line: int) -> time:
    v = _require(value, field_name, line)
    try:
        return time.fromisoformat(v)
    except ValueError as e:
        raise InvalidValueError(
            f"line {line}: '{field_name}'={value!r} is not HH:MM"
        ) from e


def _read_rows(path: Path, expected_header: list[str]) -> list[tuple[int, dict]]:
    path = Path(path)
    if not path.exists():
        raise DataError(f"file not found: {path}")
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            raise DataError(f"empty file: {path}")
        if header != expected_header:
            raise DataError(
                f"{path.name}: header mismatch\n"
                f"  expected: {expected_header}\n"
                f"  found:    {header}"
            )
        rows: list[tuple[int, dict]] = []
        for line_num, row in enumerate(reader, start=2):
            if len(row) != len(expected_header):
                raise DataError(
                    f"{path.name} line {line_num}: "
                    f"expected {len(expected_header)} columns, found {len(row)}"
                )
            rows.append((line_num, dict(zip(expected_header, row))))
        return rows


def _build_offer(
    row: dict,
    companies: dict[str, Company],
    destinations: dict[str, Destination],
    line: int,
    seen_ids: set[str],
) -> Offer:
    offer_id     = _require(row.get("offer_id"), "offer_id", line)
    company_name = _require(row.get("company"), "company", line)
    origin_name  = _require(row.get("origin"), "origin", line)
    dest_name    = _require(row.get("destination"), "destination", line)
    travel_date  = _parse_date(row.get("travel_date"), "travel_date", line)
    departure    = _parse_time(row.get("departure_time"), "departure_time", line)
    arrival      = _parse_time(row.get("arrival_time"), "arrival_time", line)
    duration     = _parse_int(row.get("duration_minutes"), "duration_minutes", line)
    price        = _parse_float(row.get("price_eur"), "price_eur", line)
    transfers    = _parse_int(row.get("transfers"), "transfers", line)
    luggage      = _parse_int(row.get("luggage_kg"), "luggage_kg", line)
    changeable   = _parse_bool(row.get("changeable"), "changeable", line)
    refundable   = _parse_bool(row.get("refundable"), "refundable", line)
    change_fee   = _parse_float(row.get("change_fee_eur"), "change_fee_eur", line)
    refund_fee   = _parse_float(row.get("refund_fee_eur"), "refund_fee_eur", line)
    seats        = _parse_int(row.get("available_seats"), "available_seats", line)
    rating       = _parse_float(row.get("rating"), "rating", line)
    emissions    = _parse_float(row.get("emissions_kg"), "emissions_kg", line,
                                allow_blank=True)
    arrival_date = _parse_date(row.get("arrival_date"), "arrival_date", line)

    if not OFFER_ID_RE.match(offer_id):
        raise InvalidValueError(
            f"line {line}: offer_id {offer_id!r} does not match "
            f"OFF-CCC-DDD-MMDD-HHMM"
        )
    if offer_id in seen_ids:
        raise InconsistentDataError(
            f"line {line}: duplicate offer_id {offer_id!r}"
        )

    if duration <= 0:
        raise InvalidValueError(f"line {line}: duration_minutes={duration} must be > 0")
    if price <= 0:
        raise InvalidValueError(f"line {line}: price_eur={price} must be > 0")
    if transfers < 0:
        raise InvalidValueError(f"line {line}: transfers={transfers} must be >= 0")
    if luggage < 0:
        raise InvalidValueError(f"line {line}: luggage_kg={luggage} must be >= 0")
    if seats < 0:
        raise InvalidValueError(f"line {line}: available_seats={seats} must be >= 0")
    if not (RATING_MIN <= rating <= RATING_MAX):
        raise InvalidValueError(
            f"line {line}: rating={rating} outside [{RATING_MIN}, {RATING_MAX}]"
        )
    if change_fee < 0 or refund_fee < 0:
        raise InvalidValueError(f"line {line}: change/refund fee cannot be negative")
    if emissions is not None and emissions < 0:
        raise InvalidValueError(f"line {line}: emissions_kg={emissions} must be >= 0")

    if company_name not in companies:
        raise UnknownReferenceError(f"line {line}: unknown company {company_name!r}")
    if origin_name != HUB and origin_name not in destinations:
        raise UnknownReferenceError(f"line {line}: unknown origin {origin_name!r}")
    if dest_name not in destinations:
        raise UnknownReferenceError(f"line {line}: unknown destination {dest_name!r}")

    expected = datetime.combine(travel_date, departure) + timedelta(minutes=duration)
    actual   = datetime.combine(arrival_date, arrival)
    if expected != actual:
        raise InconsistentDataError(
            f"line {line}: arrival inconsistent with departure+duration — "
            f"expected {expected:%Y-%m-%d %H:%M}, got {actual:%Y-%m-%d %H:%M}"
        )

    return Offer(
        offer_id=offer_id,
        company=companies[company_name],
        origin=destinations.get(origin_name, _HUB_DESTINATION),
        destination=destinations[dest_name],
        travel_date=travel_date,
        departure_time=departure,
        arrival_time=arrival,
        duration_minutes=duration,
        price_eur=price,
        transfers=transfers,
        luggage_kg=luggage,
        fare=FareConditions(
            changeable=changeable, refundable=refundable,
            change_fee_eur=change_fee, refund_fee_eur=refund_fee,
        ),
        available_seats=seats,
        rating=rating,
        emissions_kg=emissions,
    )


def load_companies(path: Path) -> dict[str, Company]:
    rows = _read_rows(path, COMPANIES_HEADER)
    companies: dict[str, Company] = {}
    for line, row in rows:
        try:
            name = _require(row["name"], "name", line)
            if name in companies:
                raise InconsistentDataError(
                    f"line {line}: duplicate company {name!r}"
                )
            companies[name] = Company(
                name=name,
                profile=_require(row["profile"], "profile", line),
                low_cost=_parse_bool(row["low_cost"], "low_cost", line),
                eco_focus=_parse_bool(row["eco_focus"], "eco_focus", line),
            )
        except DataError as e:
            logger.warning("companies.csv %s", e)
    logger.info("loaded %d companies from %s", len(companies), path)
    return companies


def load_destinations(path: Path) -> dict[str, Destination]:
    rows = _read_rows(path, DESTINATIONS_HEADER)
    dests: dict[str, Destination] = {}
    for line, row in rows:
        try:
            name = _require(row["name"], "name", line)
            if name in dests:
                raise InconsistentDataError(
                    f"line {line}: duplicate destination {name!r}"
                )
            dests[name] = Destination(
                name=name,
                coastal=_parse_bool(row["coastal"], "coastal", line),
            )
        except DataError as e:
            logger.warning("destinations.csv %s", e)
    logger.info("loaded %d destinations from %s", len(dests), path)
    return dests


def load_offers(
    path: Path,
    companies: dict[str, Company],
    destinations: dict[str, Destination],
) -> tuple[list[Offer], list[RejectedRow]]:
    rows = _read_rows(path, OFFERS_HEADER)
    offers: list[Offer] = []
    rejected: list[RejectedRow] = []
    seen_ids: set[str] = set()

    for line, row in rows:
        raw_id = (row.get("offer_id") or "").strip()
        try:
            offer = _build_offer(row, companies, destinations, line, seen_ids)
        except DataError as e:
            logger.warning("offers.csv %s", e)
            rejected.append(RejectedRow(
                line_number=line, offer_id=raw_id,
                error_type=type(e).__name__, reason=str(e),
            ))
            continue

        if offer.available_seats == 0:
            logger.info(
                "offers.csv line %d: sold-out offer %s excluded",
                line, offer.offer_id,
            )
            rejected.append(RejectedRow(
                line_number=line, offer_id=offer.offer_id,
                error_type="SoldOut",
                reason="available_seats=0 — sold out, not bookable",
            ))
            continue

        offers.append(offer)
        seen_ids.add(offer.offer_id)

    logger.info(
        "loaded %d offers from %s; rejected %d row(s)",
        len(offers), path, len(rejected),
    )
    return offers, rejected


def load_all(data_dir: Path) -> LoadResult:
    data_dir = Path(data_dir)
    companies    = load_companies(data_dir / "companies.csv")
    destinations = load_destinations(data_dir / "destinations.csv")
    offers, rejected = load_offers(
        data_dir / "offers.csv", companies, destinations,
    )
    return LoadResult(
        companies=companies, destinations=destinations,
        offers=offers, rejected=rejected,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)-7s | %(name)s | %(message)s")
    data_dir = Path(__file__).resolve().parent.parent / "data"
    result = load_all(data_dir)
    print(result.summary())
    for r in result.rejected:
        print(f"  line {r.line_number:>3} | {r.error_type:<24} | {r.reason}")
    print("\nRejected by type:", result.rejected_by_type())