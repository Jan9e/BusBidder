"""Shared fixtures for BusBidder tests."""

from __future__ import annotations

from datetime import date, time
from pathlib import Path

import pytest

from busbidder.models import Company, Destination, FareConditions, Offer


@pytest.fixture
def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


@pytest.fixture
def data_dir(project_root) -> Path:
    return project_root / "data"


@pytest.fixture
def sample_company() -> Company:
    return Company(name="TestCo", profile="testing", low_cost=False, eco_focus=False)


@pytest.fixture
def sample_origin() -> Destination:
    return Destination(name="Madrid", coastal=False)


@pytest.fixture
def sample_destination() -> Destination:
    return Destination(name="Malaga", coastal=True)


@pytest.fixture
def make_offer(sample_company, sample_origin, sample_destination):
    """Return a factory for Offer instances with sensible defaults."""
    def _make(**overrides) -> Offer:
        defaults = dict(
            offer_id="OFF-TES-MAL-0712-0900",
            company=sample_company,
            origin=sample_origin,
            destination=sample_destination,
            travel_date=date(2026, 7, 12),
            departure_time=time(9, 0),
            arrival_time=time(13, 0),
            duration_minutes=240,
            price_eur=30.0,
            transfers=0,
            luggage_kg=15,
            fare=FareConditions(changeable=True, refundable=True),
            available_seats=10,
            rating=4.0,
            emissions_kg=20.0,
        )
        defaults.update(overrides)
        return Offer(**defaults)
    return _make


@pytest.fixture
def make_fare():
    """Return a factory for FareConditions."""
    def _make(changeable=True, refundable=True, cf=0.0, rf=0.0):
        return FareConditions(
            changeable=changeable, refundable=refundable,
            change_fee_eur=cf, refund_fee_eur=rf,
        )
    return _make