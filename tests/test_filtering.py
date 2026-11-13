"""Tests for hard-constraint filtering. ~7 tests."""

from datetime import date

import pytest

from busbidder.filtering import filter_offers
from busbidder.models import TravelRequest, Weights


@pytest.fixture
def base_request():
    return TravelRequest(
        origin="Madrid", destination="Malaga",
        window_start=date(2026, 7, 12), window_end=date(2026, 7, 14),
        max_budget_eur=50.0, max_transfers=1, min_luggage_kg=0,
        requires_changeable=True, preferred_departure="morning",
        max_duration_minutes=None,
        weights=Weights(price=0.4, duration=0.25, departure=0.15, flexibility=0.2),
    )


class TestFiltering:
    def test_conforming_offer_passes(self, make_offer, base_request):
        """Normal: an offer satisfying every constraint passes."""
        offer = make_offer()
        result = filter_offers([offer], base_request)
        assert offer in result.passing
        assert len(result.filtered) == 0

    def test_over_budget_rejected(self, make_offer, base_request):
        """Boundary: price strictly greater than budget rejected."""
        offer = make_offer(price_eur=50.01)
        result = filter_offers([offer], base_request)
        assert offer not in result.passing
        assert any("budget" in r for r in result.filtered[0].reasons)

    def test_exact_budget_passes(self, make_offer, base_request):
        """Boundary: price == budget passes (<= comparison)."""
        offer = make_offer(price_eur=50.00)
        result = filter_offers([offer], base_request)
        assert offer in result.passing

    def test_wrong_destination_rejected(self, make_offer, base_request, sample_origin):
        """Invalid: destination mismatch rejected."""
        other = sample_origin  # Madrid as destination is not Malaga
        offer = make_offer(destination=other)
        result = filter_offers([offer], base_request)
        assert offer not in result.passing
        assert any("destination" in r for r in result.filtered[0].reasons)

    def test_non_changeable_rejected(self, make_offer, base_request, make_fare):
        """Invalid: non-changeable ticket rejected when required."""
        offer = make_offer(fare=make_fare(changeable=False))
        result = filter_offers([offer], base_request)
        assert offer not in result.passing

    def test_multiple_reasons_collected(self, make_offer, base_request, sample_origin,
                                        make_fare):
        """Normal: non-short-circuit design records every violation."""
        offer = make_offer(
            destination=sample_origin,      # wrong destination
            price_eur=100.0,                # over budget
            transfers=3,                    # too many transfers
            fare=make_fare(changeable=False),
        )
        result = filter_offers([offer], base_request)
        assert len(result.filtered) == 1
        assert len(result.filtered[0].reasons) >= 3

    def test_reason_counts(self, make_offer, base_request):
        """Normal: reason_counts() aggregates by constraint label."""
        offers = [
            make_offer(price_eur=100.0),
            make_offer(price_eur=80.0),
        ]
        result = filter_offers(offers, base_request)
        assert result.reason_counts().get("budget") == 2