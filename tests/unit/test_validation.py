from datetime import date
from decimal import Decimal

from expense_audit.domain.models import Category, ExtractedExpense, PolicyReason
from expense_audit.domain.validation import (
    is_valid_rfc,
    normalize_rfc,
    validate_extraction,
)

TODAY = date(2026, 11, 11)


def expense(**overrides) -> ExtractedExpense:
    base = {
        "rfc_emisor": "ABC010101AB1",
        "rfc_receptor": "XYZ010101XY2",
        "expense_date": date(2026, 11, 5),
        "subtotal": Decimal("100.00"),
        "iva": Decimal("16.00"),
        "total": Decimal("116.00"),
        "currency": "MXN",
        "category": Category.FOOD,
        "vendor_name": "Taqueria",
        "description": "Working lunch",
    }
    base.update(overrides)
    return ExtractedExpense(**base)


def codes(findings):
    return [finding.code for finding in findings]


def test_normalize_rfc_strips_spaces_and_uppercases():
    assert normalize_rfc(" abc 010101 ab1 ") == "ABC010101AB1"
    assert normalize_rfc(None) is None
    assert normalize_rfc("   ") is None


def test_is_valid_rfc_accepts_three_and_four_letter_prefixes():
    assert is_valid_rfc("ABC010101AB1")
    assert is_valid_rfc("ABCD010101AB1")
    assert is_valid_rfc("Ñ&X010101AB1")


def test_is_valid_rfc_rejects_wrong_shapes():
    assert not is_valid_rfc("AB010101AB1")
    assert not is_valid_rfc("INVALIDO123")
    assert not is_valid_rfc(None)
    assert not is_valid_rfc("ABC010101AB")


def test_clean_expense_has_no_findings():
    assert validate_extraction(expense(), TODAY) == []


def test_missing_critical_fields_are_reported_together():
    findings = validate_extraction(
        expense(rfc_emisor=None, rfc_receptor=None, expense_date=None, total=None),
        TODAY,
    )
    assert codes(findings) == [PolicyReason.MISSING_CRITICAL_FIELDS]
    assert findings[0].detail["missing"] == [
        "rfc_emisor",
        "rfc_receptor",
        "expense_date",
        "total",
    ]


def test_present_but_invalid_rfc_is_flagged():
    findings = validate_extraction(expense(rfc_emisor="INVALIDO123"), TODAY)
    assert codes(findings) == [PolicyReason.INVALID_RFC]
    assert findings[0].detail["fields"] == ["rfc_emisor"]


def test_totals_tolerance_boundary_is_inclusive():
    exact = expense(subtotal=Decimal("100.00"), iva=Decimal("16.00"), total=Decimal("117.00"))
    over = expense(subtotal=Decimal("100.00"), iva=Decimal("16.00"), total=Decimal("117.01"))
    assert codes(validate_extraction(exact, TODAY)) == []
    assert codes(validate_extraction(over, TODAY)) == [PolicyReason.TOTAL_MISMATCH]


def test_totals_are_not_checked_when_a_component_is_missing():
    assert validate_extraction(expense(iva=None), TODAY) == []


def test_future_date_is_flagged():
    findings = validate_extraction(expense(expense_date=date(2026, 11, 12)), TODAY)
    assert codes(findings) == [PolicyReason.DATE_IN_FUTURE]


def test_today_is_not_a_future_date():
    assert validate_extraction(expense(expense_date=TODAY), TODAY) == []


def test_zero_and_negative_totals_are_invalid_amounts():
    zero = validate_extraction(
        expense(subtotal=Decimal("0"), iva=Decimal("0"), total=Decimal("0")), TODAY
    )
    negative = validate_extraction(
        expense(subtotal=Decimal("-10"), iva=Decimal("0"), total=Decimal("-10")), TODAY
    )
    assert codes(zero) == [PolicyReason.INVALID_AMOUNT]
    assert codes(negative) == [PolicyReason.INVALID_AMOUNT]


def test_non_mxn_currency_is_flagged():
    findings = validate_extraction(expense(currency="USD"), TODAY)
    assert codes(findings) == [PolicyReason.CURRENCY_UNSUPPORTED]


def test_currency_is_compared_case_insensitively():
    assert validate_extraction(expense(currency="mxn"), TODAY) == []
