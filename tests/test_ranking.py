"""Tests for the weighted scoring engine. ~9 tests."""

from datetime import time

import pytest

from busbidder.exceptions import WeightValidationError
from busbidder.models import Weights
from busbidder.ranking import _departure_score, score_offers


WEIGHTS = Weights(price=0.4, duration=0.25, departure=0.15, flexibility=0.2)


class TestRanking:
    def test_returns_sorted_by_total_desc(self, make_offer):
        """Normal: results are sorted with rank 1 having the highest total."""
        offers = [
            make_offer(offer_id="OFF-A", price_eur=50.0),
            make_offer(offer_id="OFF-B", price_eur=20.0),
            make_offer(offer_id="OFF-C", price_eur=35.0),
        ]
        ranked = score_offers(offers, WEIGHTS, "morning")
        assert [r.rank for r in ranked] == [1, 2, 3]
        assert ranked[0].total_score >= ranked[-1].total_score

    def test_all_scores_in_range(self, make_offer):
        """Boundary: every normalised score in [0, 100]."""
        offers = [make_offer(price_eur=p) for p in (15.0, 30.0, 55.0)]
        ranked = score_offers(offers, WEIGHTS, "morning")
        for r in ranked:
            for score in r.criterion_scores.values():
                assert 0.0 <= score <= 100.0
            assert 0.0 <= r.total_score <= 100.0

    def test_empty_list_returns_empty(self):
        """Boundary: empty input → empty output, no exception."""
        assert score_offers([], WEIGHTS, "morning") == []

    def test_single_offer_all_100(self, make_offer):
        """Boundary: min==max for every criterion → all scores 100."""
        ranked = score_offers([make_offer()], WEIGHTS, "morning")
        assert len(ranked) == 1
        assert ranked[0].total_score == 100.0

    def test_identical_offers_all_100(self, make_offer):
        """Boundary: identical offers all score 100, tie-break applied."""
        offers = [make_offer(offer_id=f"OFF-{i}") for i in range(3)]
        ranked = score_offers(offers, WEIGHTS, "morning")
        assert all(r.total_score == 100.0 for r in ranked)
        # tie-break: cheaper first — all equal here, so offer_id orders them
        assert [r.offer.offer_id for r in ranked] == sorted(r.offer.offer_id
                                                            for r in ranked)

    def test_invalid_weights_raise(self, make_offer):
        """Invalid: weights summing to 0.5 rejected before scoring."""
        bad = Weights(price=0.2, duration=0.1, departure=0.1, flexibility=0.1)
        with pytest.raises(WeightValidationError):
            score_offers([make_offer()], bad, "morning")

    def test_cheaper_offer_scores_higher_price(self, make_offer):
        """Normal: lower price produces a higher price score."""
        cheap = make_offer(offer_id="OFF-CHEAP", price_eur=15.0)
        dear = make_offer(offer_id="OFF-DEAR", price_eur=50.0)
        ranked = score_offers([cheap, dear], WEIGHTS, "morning")
        by_id = {r.offer.offer_id: r.criterion_scores["price"] for r in ranked}
        assert by_id["OFF-CHEAP"] == 100.0
        assert by_id["OFF-DEAR"] == 0.0

    def test_missing_emissions_renormalised(self, make_offer):
        """Boundary: offer with emissions=None skips criterion, reweights."""
        with_em = make_offer(offer_id="OFF-WITH", emissions_kg=10.0)
        without_em = make_offer(offer_id="OFF-WITHOUT", emissions_kg=None)
        weights = Weights(price=0.4, duration=0.2, departure=0.2,
                          flexibility=0.0, emissions=0.2)
        ranked = score_offers([with_em, without_em], weights, "morning")
        for r in ranked:
            # emissions active for one, absent for the other
            assert "emissions" in r.criterion_scores or r.offer.emissions_kg is None


class TestDepartureScore:
    @pytest.mark.parametrize("hour,expected", [
        (8, 100.0),    # in morning window
        (14, 60.0),    # adjacent (afternoon)
        (19, 20.0),    # far (evening)
        (23, 20.0),    # far (night)
    ])
    def test_morning_preference(self, hour, expected):
        """Normal: preferred=morning scores 100/60/20 by window distance."""
        assert _departure_score(hour, "morning") == expected