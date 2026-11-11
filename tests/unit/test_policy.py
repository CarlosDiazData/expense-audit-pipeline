from datetime import date
from decimal import Decimal

from expense_audit.domain.models import (
    Category,
    CategoryLimit,
    ExtractedExpense,
    PolicyReason,
    PolicyStatus,
)
from expense_audit.domain.policy import evaluate_policy

TODAY = date(2026, 11, 11)

LIMITS = [
    CategoryLimit(
        category=Category.FOOD,
        per_expense_limit=Decimal("50.00"),
        monthly_limit=Decimal("500.00"),
    ),
    CategoryLimit(
        category=Category.TRANSPORT,
        per_expense_limit=Decimal("200.00"),
        monthly_limit=Decimal("2000.00"),
    ),
    CategoryLimit(
        category=Category.SOFTWARE,
        per_expense_limit=Decimal("500.00"),
        monthly_limit=Decimal("3000.00"),
    ),
    CategoryLimit(
        category=Category.LODGING,
        per_expense_limit=Decimal("300.00"),
        monthly_limit=Decimal("3000.00"),
    ),
    CategoryLimit(
        category=Category.OTHER,
        per_expense_limit=Decimal("100.00"),
        monthly_limit=Decimal("1000.00"),
    ),
]


def expense(**overrides) -> ExtractedExpense:
    base = {
        "rfc_emisor": "ABC010101AB1",
        "rfc_receptor": "XYZ010101XY2",
        "expense_date": date(2026, 11, 5),
        "subtotal": Decimal("40.00"),
        "iva": Decimal("6.40"),
        "total": Decimal("46.40"),
        "currency": "MXN",
        "category": Category.FOOD,
        "vendor_name": "Taqueria",
        "description": "Working lunch",
    }
    base.update(overrides)
    return ExtractedExpense(**base)


def evaluate(item, **kwargs):
    kwargs.setdefault("today", TODAY)
    kwargs.setdefault("limits", LIMITS)
    return evaluate_policy(item, **kwargs)


def test_clean_expense_is_valid():
    decision = evaluate(expense())
    assert decision.status == PolicyStatus.VALID
    assert decision.reasons == []
    assert decision.details == {}


def test_per_expense_limit_exceeded_is_suspicious():
    decision = evaluate(
        expense(total=Decimal("50.01"), subtotal=Decimal("43.11"), iva=Decimal("6.90"))
    )
    assert decision.status == PolicyStatus.SUSPICIOUS
    assert decision.reasons == [PolicyReason.PER_EXPENSE_LIMIT_EXCEEDED]
    assert decision.details["PER_EXPENSE_LIMIT_EXCEEDED"]["limit"] == "50.00"
    assert decision.details["PER_EXPENSE_LIMIT_EXCEEDED"]["observed"] == "50.01"


def test_limit_is_inclusive():
    decision = evaluate(
        expense(total=Decimal("50.00"), subtotal=Decimal("43.10"), iva=Decimal("6.90"))
    )
    assert decision.status == PolicyStatus.VALID


def test_monthly_budget_exceeded_is_suspicious():
    decision = evaluate(expense(), monthly_spend=Decimal("470.00"))
    assert decision.status == PolicyStatus.SUSPICIOUS
    assert PolicyReason.MONTHLY_BUDGET_EXCEEDED in decision.reasons
    detail = decision.details["MONTHLY_BUDGET_EXCEEDED"]
    assert detail["limit"] == "500.00"
    assert detail["spent"] == "470.00"
    assert detail["observed"] == "46.40"


def test_monthly_budget_is_inclusive_at_the_limit():
    decision = evaluate(expense(), monthly_spend=Decimal("453.60"))
    assert decision.status == PolicyStatus.VALID


def test_duplicate_expense_is_suspicious():
    decision = evaluate(expense(), duplicate_of="expense-123")
    assert decision.status == PolicyStatus.SUSPICIOUS
    assert PolicyReason.DUPLICATE_EXPENSE in decision.reasons
    assert decision.details["DUPLICATE_EXPENSE"]["expense_id"] == "expense-123"


def test_invalid_rfc_is_non_deductible_and_wins_precedence():
    decision = evaluate(
        expense(
            rfc_emisor="INVALIDO123",
            total=Decimal("999.00"),
            subtotal=Decimal("861.21"),
            iva=Decimal("137.79"),
        )
    )
    assert decision.status == PolicyStatus.NON_DEDUCTIBLE
    assert PolicyReason.INVALID_RFC in decision.reasons
    assert PolicyReason.PER_EXPENSE_LIMIT_EXCEEDED in decision.reasons


def test_missing_critical_fields_is_non_deductible():
    decision = evaluate(expense(rfc_receptor=None))
    assert decision.status == PolicyStatus.NON_DEDUCTIBLE
    assert PolicyReason.MISSING_CRITICAL_FIELDS in decision.reasons


def test_category_without_active_limit_is_non_deductible():
    limits = [limit for limit in LIMITS if limit.category != Category.FOOD]
    decision = evaluate(expense(), limits=limits)
    assert decision.status == PolicyStatus.NON_DEDUCTIBLE
    assert decision.reasons == [PolicyReason.NON_DEDUCTIBLE_CATEGORY]
    assert decision.details["NON_DEDUCTIBLE_CATEGORY"]["category"] == "FOOD"


def test_inactive_limit_counts_as_non_deductible_category():
    limits = [
        CategoryLimit(
            category=Category.FOOD,
            per_expense_limit=Decimal("50.00"),
            monthly_limit=Decimal("500.00"),
            active=False,
        )
    ]
    decision = evaluate(expense(), limits=limits)
    assert decision.status == PolicyStatus.NON_DEDUCTIBLE
    assert PolicyReason.NON_DEDUCTIBLE_CATEGORY in decision.reasons


def test_receptor_mismatch_is_non_deductible_when_company_is_configured():
    decision = evaluate(expense(), company_rfc="QWE010101QW3")
    assert decision.status == PolicyStatus.NON_DEDUCTIBLE
    assert decision.reasons == [PolicyReason.RECEPTOR_NOT_COMPANY]


def test_receptor_match_is_accepted():
    decision = evaluate(expense(), company_rfc="xyz010101xy2")
    assert decision.status == PolicyStatus.VALID


def test_non_mxn_skips_amount_limits():
    decision = evaluate(
        expense(
            currency="USD",
            total=Decimal("5000.00"),
            subtotal=Decimal("4310.34"),
            iva=Decimal("689.66"),
        ),
        monthly_spend=Decimal("100000.00"),
    )
    assert decision.status == PolicyStatus.SUSPICIOUS
    assert decision.reasons == [PolicyReason.CURRENCY_UNSUPPORTED]


def test_suspicious_findings_are_all_recorded():
    decision = evaluate(
        expense(
            total=Decimal("60.00"),
            subtotal=Decimal("51.72"),
            iva=Decimal("8.28"),
            expense_date=date(2026, 12, 1),
        ),
        duplicate_of="expense-9",
    )
    assert decision.status == PolicyStatus.SUSPICIOUS
    assert set(decision.reasons) == {
        PolicyReason.PER_EXPENSE_LIMIT_EXCEEDED,
        PolicyReason.DATE_IN_FUTURE,
        PolicyReason.DUPLICATE_EXPENSE,
    }
    assert set(decision.details) == {
        "PER_EXPENSE_LIMIT_EXCEEDED",
        "DATE_IN_FUTURE",
        "DUPLICATE_EXPENSE",
    }
