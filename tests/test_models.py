"""Unit tests for the domain model. ~6 tests."""

import pytest

from busbidder.exceptions import WeightValidationError
from busbidder.models import FareConditions, Weights


class TestWeights:
    def test_valid_weights_pass(self):
        """Normal: weights summing to 1.0 validate."""
        Weights(price=0.4, duration=0.25, departure=0.15, flexibility=0.2).validate()

    def test_sum_not_one_rejected(self):
        """Invalid: weights summing to 0.8 rejected."""
        with pytest.raises(WeightValidationError, match="sum to 0.8"):
            Weights(price=0.4, duration=0.2, departure=0.1, flexibility=0.1).validate()

    def test_negative_weight_rejected(self):
        """Invalid: negative weight rejected."""
        with pytest.raises(WeightValidationError, match="outside"):
            Weights(price=-0.1, duration=0.5, departure=0.3, flexibility=0.3).validate()

    def test_boundary_exact_zero_weight_ok(self):
        """Boundary: 0.0 is a legitimate weight (criterion ignored)."""
        Weights(price=1.0, duration=0.0, departure=0.0, flexibility=0.0).validate()


class TestFareConditions:
    @pytest.mark.parametrize("changeable,refundable,expected", [
        (True,  True,  100.0),
        (True,  False, 70.0),
        (False, True,  50.0),
        (False, False, 20.0),
    ])
    def test_flexibility_tiers(self, changeable, refundable, expected):
        """Normal: four fare combinations map to four scores."""
        fare = FareConditions(changeable=changeable, refundable=refundable)
        assert fare.flexibility_score() == expected