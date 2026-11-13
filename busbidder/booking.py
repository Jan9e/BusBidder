"""booking.py — booking creation, seat decrement, persistence."""

from __future__ import annotations

import json
import re
import secrets
import string
from datetime import datetime
from pathlib import Path

from .exceptions import BookingError
from .models import Booking, Offer

BOOKING_REF_RE = re.compile(r"^BB-[A-Z0-9]{6}$")
_ALPHABET = string.ascii_uppercase + string.digits


def _generate_reference() -> str:
    return "BB-" + "".join(secrets.choice(_ALPHABET) for _ in range(6))


def validate_reference(ref: str) -> bool:
    return bool(BOOKING_REF_RE.match(ref))


def create_booking(
    offer: Offer,
    traveller_name: str,
    existing: dict[str, Booking],
) -> Booking:
    if offer.available_seats <= 0:
        raise BookingError(f"offer {offer.offer_id} is sold out")
    name = traveller_name.strip()
    if not name:
        raise BookingError("traveller name is required")
    if len(name) > 80:
        raise BookingError("traveller name is too long")

    for _ in range(100):
        ref = _generate_reference()
        if ref not in existing and validate_reference(ref):
            break
    else:
        raise BookingError("could not generate a unique booking reference")

    booking = Booking(
        reference=ref,
        offer=offer,
        traveller_name=name,
        created_at=datetime.now(),
        payment_status="simulated-paid",
    )
    offer.available_seats -= 1
    existing[ref] = booking
    return booking


def append_booking(booking: Booking, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(booking.to_dict(), ensure_ascii=False) + "\n")