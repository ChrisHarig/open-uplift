"""Tests for survey CLI validation helpers."""

import json
from unittest.mock import patch, MagicMock

import pytest

from open_uplift.cli.survey import _validate_number, _parse_number_input, _show_existing_response


class TestValidateNumber:
    def test_valid_number_in_range(self):
        assert _validate_number("3.5", {"min": 0, "max": 10}) is True

    def test_strips_x_suffix(self):
        assert _validate_number("3.5x", {"min": 0, "max": 10}) is True

    def test_strips_min_suffix(self):
        assert _validate_number("2min", {"min": 0, "max": 10}) is True

    def test_non_numeric_returns_error(self):
        result = _validate_number("abc", {})
        assert isinstance(result, str)
        assert "number" in result.lower()

    def test_empty_string_returns_error(self):
        result = _validate_number("", {})
        assert isinstance(result, str)

    def test_out_of_range_returns_error(self):
        result = _validate_number("11", {"min": 0, "max": 10})
        assert isinstance(result, str)
        assert "between" in result.lower()

    def test_too_many_decimals_returns_error(self):
        result = _validate_number("3.55", {"max_decimals": 1})
        assert isinstance(result, str)
        assert "decimal" in result.lower()

    def test_exact_boundary_values(self):
        assert _validate_number("0", {"min": 0, "max": 10}) is True
        assert _validate_number("10", {"min": 0, "max": 10}) is True

    def test_integer_no_decimal_check(self):
        """Integer values should pass decimal check."""
        assert _validate_number("5", {"max_decimals": 1}) is True


class TestParseNumberInput:
    def test_strips_x_suffix(self):
        assert _parse_number_input("3.5x") == 3.5

    def test_strips_min_suffix(self):
        assert _parse_number_input("2min") == 2.0

    def test_plain_number(self):
        assert _parse_number_input("7.2") == 7.2

    def test_with_whitespace(self):
        assert _parse_number_input("  5.0  ") == 5.0


class TestShowExistingResponse:
    def test_returns_true_when_response_exists(self, db, sample_session_with_results):
        """A session with survey response should return True."""
        # console and format_survey_results are imported lazily inside _show_existing_response
        with patch("open_uplift.cli.formatting.console") as mock_console, \
             patch("open_uplift.cli.formatting.format_survey_results", return_value="mocked"):
            result = _show_existing_response(db, sample_session_with_results, "survey-1")
        assert result is True

    def test_returns_false_when_no_response(self, db, sample_session):
        result = _show_existing_response(db, sample_session, "survey-1")
        assert result is False
