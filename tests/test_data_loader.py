"""Integration tests for the CSV loader and validation pipeline. ~9 tests."""

import csv

import pytest

from busbidder.data_loader import (
    COMPANIES_HEADER,
    OFFERS_HEADER,
    _read_rows,
    load_all,
)
from busbidder.exceptions import DataError


class TestLoadReal:
    def test_loads_all_files(self, data_dir):
        """Normal: the shipped dataset loads cleanly."""
        result = load_all(data_dir)
        assert len(result.companies) == 5
        assert len(result.destinations) == 15
        assert len(result.offers) >= 90
        assert len(result.rejected) == 9

    def test_rejected_cover_all_categories(self, data_dir):
        """Normal: the nine seeded invalid rows span multiple error types."""
        result = load_all(data_dir)
        types = result.rejected_by_type()
        assert "InvalidValueError" in types
        assert "MissingDataError" in types
        assert "UnknownReferenceError" in types
        assert "InconsistentDataError" in types
        assert "SoldOut" in types


class TestHeaderValidation:
    def test_missing_file_raises(self, tmp_path):
        """Invalid: missing file raises DataError with clear message."""
        with pytest.raises(DataError, match="file not found"):
            _read_rows(tmp_path / "nope.csv", COMPANIES_HEADER)

    def test_wrong_header_raises(self, tmp_path):
        """Invalid: mismatched header rejected before any row parses."""
        bad = tmp_path / "bad.csv"
        bad.write_text("wrong,header\n1,2\n")
        with pytest.raises(DataError, match="header mismatch"):
            _read_rows(bad, COMPANIES_HEADER)

    def test_empty_file_raises(self, tmp_path):
        """Boundary: empty file → DataError, not StopIteration traceback."""
        empty = tmp_path / "empty.csv"
        empty.write_text("")
        with pytest.raises(DataError, match="empty file"):
            _read_rows(empty, COMPANIES_HEADER)


class TestOfferValidation:
    """Feed a single-row offers.csv and assert every rejection path."""

    def _write_offers(self, tmp_path, data_dir, row):
        header = OFFERS_HEADER
        with (tmp_path / "offers.csv").open("w", newline="") as f:
            w = csv.writer(f); w.writerow(header); w.writerow(row)
        # companies/destinations must be present for load_all
        (tmp_path / "companies.csv").write_bytes((data_dir / "companies.csv").read_bytes())
        (tmp_path / "destinations.csv").write_bytes((data_dir / "destinations.csv").read_bytes())

    BASE_ROW = [
        "OFF-SOL-MAL-0712-0900", "SolRuta", "Madrid", "Malaga", "2026-07-12",
        "09:00", "13:30", 270, "25.00", 0, 20, "True", "False", "0.00", "0.00",
        12, 4.2, "24.3", "2026-07-12",
    ]

    def test_baseline_row_loads(self, tmp_path, data_dir):
        """Normal: baseline row loads without rejection."""
        self._write_offers(tmp_path, data_dir, self.BASE_ROW)
        result = load_all(tmp_path)
        assert len(result.offers) == 1
        assert len(result.rejected) == 0

    def test_negative_price_rejected(self, tmp_path, data_dir):
        """Boundary: negative price — rejected at range check."""
        row = self.BASE_ROW.copy(); row[8] = "-15.00"
        self._write_offers(tmp_path, data_dir, row)
        result = load_all(tmp_path)
        assert len(result.offers) == 0
        assert "price_eur=-15.0" in result.rejected[0].reason

    def test_rating_out_of_range_rejected(self, tmp_path, data_dir):
        """Boundary: rating 6.0 exceeds scale — rejected."""
        row = self.BASE_ROW.copy(); row[16] = "6.0"
        self._write_offers(tmp_path, data_dir, row)
        result = load_all(tmp_path)
        assert len(result.offers) == 0
        assert "rating=6.0" in result.rejected[0].reason

    def test_unknown_destination_rejected(self, tmp_path, data_dir):
        """Invalid: unknown destination caught by reference check."""
        row = self.BASE_ROW.copy(); row[3] = "Atlantis"
        self._write_offers(tmp_path, data_dir, row)
        result = load_all(tmp_path)
        assert len(result.offers) == 0
        assert "Atlantis" in result.rejected[0].reason

    def test_arrival_inconsistent_rejected(self, tmp_path, data_dir):
        """Invalid: arrival before departure + duration caught."""
        row = self.BASE_ROW.copy(); row[6] = "10:00"
        self._write_offers(tmp_path, data_dir, row)
        result = load_all(tmp_path)
        assert len(result.offers) == 0
        assert "arrival inconsistent" in result.rejected[0].reason

    def test_empty_field_rejected(self, tmp_path, data_dir):
        """Missing: empty company rejected as MissingDataError."""
        row = self.BASE_ROW.copy(); row[1] = ""
        self._write_offers(tmp_path, data_dir, row)
        result = load_all(tmp_path)
        assert len(result.offers) == 0
        assert result.rejected[0].error_type == "MissingDataError"

    def test_bad_offer_id_rejected(self, tmp_path, data_dir):
        """Invalid: offer_id not matching OFF-CCC-DDD-MMDD-HHMM rejected."""
        row = self.BASE_ROW.copy(); row[0] = "BADID"
        self._write_offers(tmp_path, data_dir, row)
        result = load_all(tmp_path)
        assert len(result.offers) == 0
        assert "OFF-CCC-DDD-MMDD-HHMM" in result.rejected[0].reason