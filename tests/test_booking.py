"""Tests for booking creation and persistence. ~6 tests."""

import json
from datetime import date, time

import pytest

from busbidder.booking import BOOKING_REF_RE, create_booking, validate_reference
from busbidder.exceptions import BookingError


class TestBooking:
    def test_creates_booking_with_valid_reference(self, make_offer):
        """Normal: booking has correct format reference."""
        offer = make_offer()
        booking = create_booking(offer, "Roshan", existing={})
        assert BOOKING_REF_RE.match(booking.reference)
        assert booking.reference.startswith("BB-")
        assert len(booking.reference) == 9

    def test_seat_decremented(self, make_offer):
        """Normal: booking reduces available_seats by 1."""
        offer = make_offer(available_seats=5)
        create_booking(offer, "Roshan", existing={})
        assert offer.available_seats == 4

    def test_sold_out_raises(self, make_offer):
        """Boundary: seat count 0 → BookingError."""
        offer = make_offer(available_seats=0)
        with pytest.raises(BookingError, match="sold out"):
            create_booking(offer, "Roshan", existing={})

    def test_empty_name_raises(self, make_offer):
        """Invalid: empty traveller name rejected."""
        offer = make_offer()
        with pytest.raises(BookingError, match="name is required"):
            create_booking(offer, "  ", existing={})

    def test_reference_unique_across_bookings(self, make_offer):
        """Normal: two bookings have distinct references."""
        offer = make_offer(available_seats=10)
        existing = {}
        b1 = create_booking(offer, "A", existing)
        b2 = create_booking(offer, "B", existing)
        assert b1.reference != b2.reference

    def test_validate_reference(self):
        """Unit: reference format check works both ways."""
        assert validate_reference("BB-ABC123")
        assert validate_reference("BB-000000")
        assert not validate_reference("BB-ABC12")    # too short
        assert not validate_reference("BB-abc123")   # lowercase
        assert not validate_reference("XX-ABC123")   # wrong prefix
        assert not validate_reference("BB_ABC123")   # wrong separator